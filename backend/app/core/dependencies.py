"""
FastAPI dependencies for auth, database sessions, and permission checks.
"""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User
from app.models.project import Project
from app.models.project_permission import ProjectPermission

security_scheme = HTTPBearer()


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
    """Dependency factory: require the user to have one of the given project roles."""
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
