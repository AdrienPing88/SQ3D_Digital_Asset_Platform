"""
OAuth2 PKCE provider abstractions for Google and Microsoft.
Handles authorization URL generation, code exchange, and user info retrieval.
"""

import hashlib
import secrets
import base64
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


class OAuthUserInfo:
    """Normalized user info returned from any OAuth provider."""

    def __init__(
        self,
        email: str,
        display_name: str,
        avatar_url: Optional[str] = None,
        provider: str = "",
        provider_user_id: str = "",
    ):
        self.email = email
        self.display_name = display_name
        self.avatar_url = avatar_url
        self.provider = provider
        self.provider_user_id = provider_user_id


class OAuthProvider:
    """Base class for OAuth2 PKCE providers."""

    name: str = ""
    authorize_url: str = ""
    token_url: str = ""
    userinfo_url: str = ""
    scopes: list[str] = []

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorization_url(self, code_challenge: str, state: str) -> str:
        """Build the authorization URL with PKCE challenge."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        params.update(self._extra_auth_params())
        return f"{self.authorize_url}?{urlencode(params)}"

    def _extra_auth_params(self) -> dict:
        """Override to add provider-specific authorization params."""
        return {}

    async def exchange_code(self, code: str, code_verifier: str) -> dict:
        """Exchange authorization code for tokens using PKCE verifier."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "code_verifier": code_verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": self.redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        """Fetch user profile from the provider. Must be implemented by subclass."""
        raise NotImplementedError


class GoogleOAuthProvider(OAuthProvider):
    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    scopes = ["openid", "email", "profile"]

    def _extra_auth_params(self) -> dict:
        return {"access_type": "offline", "prompt": "consent"}

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            return OAuthUserInfo(
                email=data["email"],
                display_name=data.get("name", data["email"].split("@")[0]),
                avatar_url=data.get("picture"),
                provider="google",
                provider_user_id=data.get("id", ""),
            )


class MicrosoftOAuthProvider(OAuthProvider):
    name = "microsoft"
    authorize_url = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    userinfo_url = "https://graph.microsoft.com/v1.0/me"
    scopes = ["openid", "email", "profile", "User.Read"]

    def _extra_auth_params(self) -> dict:
        return {"response_mode": "query"}

    async def get_user_info(self, access_token: str) -> OAuthUserInfo:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.userinfo_url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            data = response.json()
            email = data.get("mail") or data.get("userPrincipalName", "")
            return OAuthUserInfo(
                email=email,
                display_name=data.get("displayName", email.split("@")[0]),
                avatar_url=None,
                provider="microsoft",
                provider_user_id=data.get("id", ""),
            )


def get_oauth_provider(provider_name: str) -> OAuthProvider:
    """Factory: return the configured OAuth provider instance."""
    providers = {
        "google": lambda: GoogleOAuthProvider(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        ),
        "microsoft": lambda: MicrosoftOAuthProvider(
            client_id=settings.MICROSOFT_CLIENT_ID,
            client_secret=settings.MICROSOFT_CLIENT_SECRET,
            redirect_uri=settings.MICROSOFT_REDIRECT_URI,
        ),
    }
    factory = providers.get(provider_name)
    if not factory:
        raise ValueError(f"Unsupported OAuth provider: {provider_name}")
    return factory()
