"""Asset endpoints: presign upload, confirm, list, detail, download."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, get_project_with_access
from app.models.annotation import Annotation
from app.models.asset import Asset, AssetStatus
from app.models.project import Project
from app.models.user import User
from app.schemas.asset import (
    AssetConfirmRequest,
    AssetPresignRequest,
    AssetPresignResponse,
    AssetResponse,
    AssetUpdate,
)
from app.schemas.common import PaginatedResponse
from app.services.asset_service import AssetService

router = APIRouter()


def _asset_to_response(asset: Asset, annotation_count: int = 0) -> AssetResponse:
    return AssetResponse(
        id=str(asset.id),
        project_id=str(asset.project_id),
        uploaded_by=str(asset.uploaded_by),
        name=asset.name,
        asset_type=asset.asset_type,
        file_size_bytes=asset.file_size_bytes,
        status=asset.status,
        spatial_metadata=asset.spatial_metadata,
        version=asset.version,
        thumbnail_url=None,
        tile_root_url=None,
        annotation_count=annotation_count,
        created_at=asset.created_at.isoformat(),
        updated_at=asset.updated_at.isoformat(),
    )


@router.get("/projects/{project_id}/assets", response_model=PaginatedResponse[AssetResponse])
async def list_assets(
    project: Project = Depends(get_project_with_access),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List assets in a project."""
    base = select(Asset).where(Asset.project_id == project.id)
    if asset_type:
        base = base.where(Asset.asset_type == asset_type)
    if status:
        base = base.where(Asset.status == status)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar() or 0
    assets = (
        await db.execute(
            base.order_by(Asset.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    items = []
    for a in assets:
        ann_count = (
            await db.execute(select(func.count()).where(Annotation.asset_id == a.id))
        ).scalar() or 0
        items.append(_asset_to_response(a, ann_count))

    return PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size,
        has_more=(page * page_size) < total,
    )


@router.post("/projects/{project_id}/assets/presign", response_model=AssetPresignResponse)
async def presign_upload(
    req: AssetPresignRequest,
    project: Project = Depends(get_project_with_access),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a presigned S3 upload URL and create a pending asset record."""
    # Eagerly load organization for quota check (async session can't lazy-load)
    await db.refresh(project, ["organization"])
    service = AssetService(db)
    try:
        return await service.presign_upload(project, req, str(user.id))
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/assets/confirm", response_model=AssetResponse)
async def confirm_upload(
    req: AssetConfirmRequest,
    asset_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Confirm upload completion and trigger processing."""
    service = AssetService(db)
    try:
        asset = await service.confirm_upload(asset_id, req)
        return _asset_to_response(asset)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/assets/{asset_id}", response_model=AssetResponse)
async def get_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get asset details."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    ann_count = (
        await db.execute(select(func.count()).where(Annotation.asset_id == asset.id))
    ).scalar() or 0

    return _asset_to_response(asset, ann_count)


@router.patch("/assets/{asset_id}", response_model=AssetResponse)
async def update_asset(
    asset_id: UUID,
    req: AssetUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update asset name or metadata."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    if req.name is not None:
        asset.name = req.name
    if req.metadata is not None:
        asset.spatial_metadata = req.metadata
    await db.commit()
    await db.refresh(asset)

    return _asset_to_response(asset)


@router.delete("/assets/{asset_id}")
async def delete_asset(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Soft-delete an asset (archive)."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    asset.status = AssetStatus.ARCHIVED.value
    await db.commit()
    return {"message": "Asset archived"}


@router.get("/assets/{asset_id}/download")
async def get_download_url(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get a time-limited download URL."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    service = AssetService(db)
    try:
        url = await service.get_download_url(asset)
        return {"download_url": url}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/assets/{asset_id}/stream")
async def get_stream_url(
    asset_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get CloudFront signed URL for tile streaming."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    service = AssetService(db)
    try:
        url = await service.get_stream_url(asset)
        return {"stream_url": url}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
