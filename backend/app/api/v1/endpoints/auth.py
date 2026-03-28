"""Authentication endpoints: login, register, refresh, logout, OAuth2 PKCE."""

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.oauth import generate_pkce_pair, get_oauth_provider
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.organization import Organization
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    OAuthAuthorizeResponse,
    OAuthCallbackRequest,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)

router = APIRouter()

# In-memory store for PKCE verifiers (keyed by state).
# In production, use Redis or a database-backed session store.
_pkce_store: dict[str, str] = {}


@router.post("/register", response_model=LoginResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user and organization."""
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    org = Organization(name=req.org_name or f"{req.display_name}'s Organization")
    db.add(org)
    await db.flush()

    user = User(
        org_id=org.id,
        email=req.email,
        display_name=req.display_name,
        hashed_password=hash_password(req.password),
        global_role="org_admin",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(str(user.id), str(user.org_id), user.global_role)
    return LoginResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Authenticate with email + password, return JWT."""
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    access = create_access_token(str(user.id), str(user.org_id), user.global_role)
    refresh = create_refresh_token(str(user.id))

    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        samesite="strict",
        secure=settings.ENV != "development",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return LoginResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Rotate access token using refresh cookie."""
    from fastapi import Cookie
    # In practice the cookie is extracted via dependency; simplified here
    raise HTTPException(status_code=501, detail="Refresh token flow — use login endpoint for MVP")


@router.post("/logout")
async def logout(response: Response):
    """Clear refresh token cookie."""
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}


@router.get("/me", response_model=UserResponse)
async def get_me(user: User = Depends(get_current_user)):
    """Return the current authenticated user."""
    return UserResponse.model_validate(user)


# ── OAuth2 PKCE Endpoints ──────────────────────────────


@router.get("/oauth/{provider}/authorize", response_model=OAuthAuthorizeResponse)
async def oauth_authorize(provider: str):
    """Generate an OAuth2 authorization URL with PKCE challenge.

    Supported providers: google, microsoft.
    The frontend should redirect the user to the returned URL.
    """
    try:
        oauth = get_oauth_provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    # Store the verifier so we can use it during callback
    _pkce_store[state] = code_verifier

    authorization_url = oauth.get_authorization_url(code_challenge, state)

    return OAuthAuthorizeResponse(
        authorization_url=authorization_url,
        state=state,
    )


@router.post("/oauth/{provider}/callback", response_model=LoginResponse)
async def oauth_callback(
    provider: str,
    req: OAuthCallbackRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth2 callback: exchange code for tokens, create or link user.

    The frontend sends the authorization code and state received from the provider.
    """
    try:
        oauth = get_oauth_provider(provider)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    # Retrieve and consume the PKCE verifier
    code_verifier = _pkce_store.pop(req.state, None)
    if not code_verifier:
        raise HTTPException(status_code=400, detail="Invalid or expired state parameter")

    # Exchange code for tokens
    try:
        token_data = await oauth.exchange_code(req.code, code_verifier)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")

    provider_access_token = token_data.get("access_token")
    if not provider_access_token:
        raise HTTPException(status_code=400, detail="No access token in provider response")

    # Fetch user info from provider
    try:
        user_info = await oauth.get_user_info(provider_access_token)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to fetch user info from provider")

    if not user_info.email:
        raise HTTPException(status_code=400, detail="OAuth provider did not return an email address")

    # Look up existing user
    result = await db.execute(select(User).where(User.email == user_info.email))
    user = result.scalar_one_or_none()

    if not user:
        # First-time OAuth login: check if an org with a matching email domain exists
        email_domain = user_info.email.split("@")[1]
        org = None

        # Try to find an existing organization by matching user email domains
        domain_user_result = await db.execute(
            select(User).where(User.email.ilike(f"%@{email_domain}"))
        )
        domain_user = domain_user_result.scalars().first()
        if domain_user:
            org = await db.get(Organization, domain_user.org_id)

        if not org:
            # Create a new organization for this user
            org = Organization(name=f"{user_info.display_name}'s Organization")
            db.add(org)
            await db.flush()

        user = User(
            org_id=org.id,
            email=user_info.email,
            display_name=user_info.display_name,
            avatar_url=user_info.avatar_url,
            hashed_password=None,  # OAuth users don't have a password
            global_role="org_admin" if not domain_user else "member",
            last_login=datetime.now(timezone.utc),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    else:
        # Existing user: update last login and avatar if missing
        user.last_login = datetime.now(timezone.utc)
        if user_info.avatar_url and not user.avatar_url:
            user.avatar_url = user_info.avatar_url
        await db.commit()

    # Issue our own JWT tokens
    access = create_access_token(str(user.id), str(user.org_id), user.global_role)
    refresh = create_refresh_token(str(user.id))

    response.set_cookie(
        key="refresh_token",
        value=refresh,
        httponly=True,
        samesite="strict",
        secure=settings.ENV != "development",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return LoginResponse(
        access_token=access,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )
