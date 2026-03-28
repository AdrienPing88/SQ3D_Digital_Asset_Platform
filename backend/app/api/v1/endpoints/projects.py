"""Project CRUD endpoints + member management."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import (
    get_current_user,
    get_project_with_access,
    require_min_project_role,
    require_project_role,
)
from app.models.asset import Asset
from app.models.project import Project
from app.models.project_permission import ProjectPermission
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.project import (
    ProjectCreate,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectMemberUpdate,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter()


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    archived: Optional[bool] = None,
    search: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List projects the user has access to within their org."""
    base = select(Project).where(Project.org_id == user.org_id)

    if archived is not None:
        base = base.where(Project.archived == archived)
    else:
        base = base.where(Project.archived == False)

    if search:
        base = base.where(Project.name.ilike(f"%{search}%"))

    if user.global_role != "org_admin":
        base = base.where(
            Project.id.in_(
                select(ProjectPermission.project_id).where(ProjectPermission.user_id == user.id)
            )
        )

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    projects = (
        await db.execute(
            base.order_by(Project.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = []
    for p in projects:
        asset_count = (
            await db.execute(
                select(func.count()).where(Asset.project_id == p.id)
            )
        ).scalar() or 0
        member_count = (
            await db.execute(
                select(func.count()).where(ProjectPermission.project_id == p.id)
            )
        ).scalar() or 0
        items.append(
            ProjectResponse(
                id=str(p.id),
                org_id=str(p.org_id),
                name=p.name,
                description=p.description,
                coordinate_system=p.coordinate_system,
                metadata=p.project_metadata,
                archived=p.archived,
                asset_count=asset_count,
                member_count=member_count,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat(),
            )
        )

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    req: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new project and assign creator as owner."""
    project = Project(
        org_id=user.org_id,
        created_by=user.id,
        name=req.name,
        description=req.description,
        coordinate_system=req.coordinate_system,
        project_metadata=req.metadata,
    )
    db.add(project)
    await db.flush()

    perm = ProjectPermission(
        project_id=project.id,
        user_id=user.id,
        role="owner",
        granted_by=user.id,
    )
    db.add(perm)
    await db.commit()
    await db.refresh(project)

    return ProjectResponse(
        id=str(project.id),
        org_id=str(project.org_id),
        name=project.name,
        description=project.description,
        coordinate_system=project.coordinate_system,
        metadata=project.project_metadata,
        archived=project.archived,
        asset_count=0,
        member_count=1,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project: Project = Depends(get_project_with_access),
    db: AsyncSession = Depends(get_db),
):
    """Get project details. Requires at least viewer access."""
    asset_count = (
        await db.execute(select(func.count()).where(Asset.project_id == project.id))
    ).scalar() or 0
    member_count = (
        await db.execute(select(func.count()).where(ProjectPermission.project_id == project.id))
    ).scalar() or 0

    return ProjectResponse(
        id=str(project.id),
        org_id=str(project.org_id),
        name=project.name,
        description=project.description,
        coordinate_system=project.coordinate_system,
        metadata=project.project_metadata,
        archived=project.archived,
        asset_count=asset_count,
        member_count=member_count,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    req: ProjectUpdate,
    project: Project = Depends(get_project_with_access),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_min_project_role("admin")),
):
    """Update project fields. Requires admin or owner role."""
    for field, value in req.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    await db.commit()
    await db.refresh(project)

    asset_count = (
        await db.execute(select(func.count()).where(Asset.project_id == project.id))
    ).scalar() or 0
    member_count = (
        await db.execute(select(func.count()).where(ProjectPermission.project_id == project.id))
    ).scalar() or 0

    return ProjectResponse(
        id=str(project.id),
        org_id=str(project.org_id),
        name=project.name,
        description=project.description,
        coordinate_system=project.coordinate_system,
        metadata=project.project_metadata,
        archived=project.archived,
        asset_count=asset_count,
        member_count=member_count,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
    )


@router.delete("/{project_id}")
async def delete_project(
    project: Project = Depends(get_project_with_access),
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_project_role("owner")),
):
    """Soft-delete a project (archive). Requires owner role."""
    project.archived = True
    await db.commit()
    return {"message": "Project archived"}


# ── Members ──────────────────────────────────

@router.get("/{project_id}/members", response_model=list[ProjectMemberResponse])
async def list_members(
    project: Project = Depends(get_project_with_access),
    db: AsyncSession = Depends(get_db),
):
    """List project members with roles. Requires viewer access or above."""
    result = await db.execute(
        select(ProjectPermission, User)
        .join(User, ProjectPermission.user_id == User.id)
        .where(ProjectPermission.project_id == project.id)
    )
    members = []
    for perm, u in result.all():
        members.append(
            ProjectMemberResponse(
                user_id=str(u.id),
                email=u.email,
                display_name=u.display_name,
                avatar_url=u.avatar_url,
                role=perm.role,
                granted_at=perm.granted_at.isoformat(),
            )
        )
    return members


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=201)
async def add_member(
    project_id: UUID,
    req: ProjectMemberAdd,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    _perm=Depends(require_min_project_role("admin")),
):
    """Invite a member to the project by email. Requires admin or owner role."""
    result = await db.execute(select(User).where(User.email == req.email, User.org_id == user.org_id))
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found in your organization")

    existing = await db.execute(
        select(ProjectPermission).where(
            ProjectPermission.project_id == project_id,
            ProjectPermission.user_id == target.id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="User already a member")

    perm = ProjectPermission(
        project_id=project_id,
        user_id=target.id,
        role=req.role,
        granted_by=user.id,
    )
    db.add(perm)
    await db.commit()

    return ProjectMemberResponse(
        user_id=str(target.id),
        email=target.email,
        display_name=target.display_name,
        avatar_url=target.avatar_url,
        role=perm.role,
        granted_at=perm.granted_at.isoformat(),
    )


@router.put("/{project_id}/members/{user_id}")
async def update_member_role(
    project_id: UUID,
    user_id: UUID,
    req: ProjectMemberUpdate,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_min_project_role("admin")),
):
    """Change a member's role. Requires admin or owner role."""
    result = await db.execute(
        select(ProjectPermission).where(
            ProjectPermission.project_id == project_id,
            ProjectPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Member not found")

    if perm.role == "owner" and req.role != "owner":
        raise HTTPException(status_code=400, detail="Cannot demote the project owner")

    perm.role = req.role
    await db.commit()
    return {"message": "Role updated"}


@router.delete("/{project_id}/members/{user_id}")
async def remove_member(
    project_id: UUID,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    _perm=Depends(require_min_project_role("admin")),
):
    """Remove a member from the project. Requires admin or owner role."""
    result = await db.execute(
        select(ProjectPermission).where(
            ProjectPermission.project_id == project_id,
            ProjectPermission.user_id == user_id,
        )
    )
    perm = result.scalar_one_or_none()
    if not perm:
        raise HTTPException(status_code=404, detail="Member not found")
    if perm.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot remove project owner")

    await db.delete(perm)
    await db.commit()
    return {"message": "Member removed"}
