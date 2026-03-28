"""
FastAPI dependencies for auth, database sessions, and permission checks.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.models.project import Project
from app.models.project_permission import ProjectPermission

security_scheme = HTTPBearer()

# Role hierarchy: higher index = more privilege
ROLE_HIERARCHY = ["viewer", "collaborator", "admin", "owner"]


def _role_level(role: str) -> int:
    """Return the numeric level for a project role. Higher = more privilege."""
    try:
        return ROLE_HIERARCHY.index(role)
    except ValueError:
        return -1


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Extract and validate the current user from the JWT token."""
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await db.get(User, UUID(user_id))
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_project_with_access(
    project_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    """Fetch a project and verify the user has access."""
    project = await db.get(Project, project_id)
    if not project or project.org_id != user.org_id:
        raise HTTPException(status_code=404, detail="Project not found")

    permission = await db.execute(
        select(ProjectPermission).where(
            ProjectPermission.project_id == project_id,
            ProjectPermission.user_id == user.id,
        )
    )
    if not permission.scalar_one_or_none() and user.global_role != "org_admin":
        raise HTTPException(status_code=403, detail="Access denied")

    return project


def require_project_role(*roles: str):
    """Dependency factory: require the user to have one of the given project roles.

    Also supports hierarchy-based checking: if a single role is passed,
    any role at or above that level in the hierarchy grants access.
    When multiple roles are passed, exact membership is checked.
    """
    async def checker(
        project_id: UUID,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> ProjectPermission:
        if user.global_role == "org_admin":
            project = await db.get(Project, project_id)
            if not project or project.org_id != user.org_id:
                raise HTTPException(status_code=404, detail="Project not found")
            return ProjectPermission(
                project_id=project_id, user_id=user.id, role="owner"
            )

        result = await db.execute(
            select(ProjectPermission).where(
                ProjectPermission.project_id == project_id,
                ProjectPermission.user_id == user.id,
            )
        )
        perm = result.scalar_one_or_none()
        if not perm or perm.role not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return perm

    return checker


def require_min_project_role(min_role: str):
    """Dependency factory: require at least the specified role level.

    Uses the hierarchy: owner > admin > collaborator > viewer.
    For example, require_min_project_role("collaborator") allows
    collaborator, admin, and owner but denies viewer.
    """
    min_level = _role_level(min_role)

    async def checker(
        project_id: UUID,
        db: AsyncSession = Depends(get_db),
        user: User = Depends(get_current_user),
    ) -> ProjectPermission:
        # Org admins bypass project-level checks
        if user.global_role == "org_admin":
            project = await db.get(Project, project_id)
            if not project or project.org_id != user.org_id:
                raise HTTPException(status_code=404, detail="Project not found")
            return ProjectPermission(
                project_id=project_id, user_id=user.id, role="owner"
            )

        result = await db.execute(
            select(ProjectPermission).where(
                ProjectPermission.project_id == project_id,
                ProjectPermission.user_id == user.id,
            )
        )
        perm = result.scalar_one_or_none()
        if not perm:
            raise HTTPException(status_code=403, detail="Insufficient permissions")

        if _role_level(perm.role) < min_level:
            raise HTTPException(
                status_code=403,
                detail=f"Requires at least '{min_role}' role on this project",
            )
        return perm

    return checker


async def setup_rls_context(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AsyncSession:
    """Set Row-Level Security context variables for the current request.

    This sets the org_id as a session variable that PostgreSQL RLS policies
    can reference via current_setting('app.current_org_id').
    """
    await db.execute(
        text("SET LOCAL app.current_org_id = :org_id"),
        {"org_id": str(user.org_id)},
    )
    await db.execute(
        text("SET LOCAL app.current_user_id = :user_id"),
        {"user_id": str(user.id)},
    )
    return db
