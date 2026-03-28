"""Annotation and comment endpoints."""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.comment import Comment
from app.models.user import User
from app.schemas.annotation import (
    AnnotationCreate,
    AnnotationResponse,
    AnnotationUpdate,
    CommentCreate,
    CommentResponse,
    CommentUpdate,
)

router = APIRouter()


def _annotation_response(ann: Annotation, creator_name: str = "", comment_count: int = 0) -> AnnotationResponse:
    return AnnotationResponse(
        id=str(ann.id),
        asset_id=str(ann.asset_id),
        created_by=str(ann.created_by),
        creator_name=creator_name,
        annotation_type=ann.annotation_type,
        position_data=ann.position_data,
        content=ann.content,
        resolved=ann.resolved,
        resolved_by=str(ann.resolved_by) if ann.resolved_by else None,
        resolved_at=ann.resolved_at.isoformat() if ann.resolved_at else None,
        comment_count=comment_count,
        created_at=ann.created_at.isoformat(),
        updated_at=ann.updated_at.isoformat(),
    )


@router.get("/assets/{asset_id}/annotations", response_model=list[AnnotationResponse])
async def list_annotations(
    asset_id: UUID,
    annotation_type: str = None,
    resolved: bool = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List annotations on an asset."""
    base = select(Annotation, User).join(User, Annotation.created_by == User.id).where(Annotation.asset_id == asset_id)
    if annotation_type:
        base = base.where(Annotation.annotation_type == annotation_type)
    if resolved is not None:
        base = base.where(Annotation.resolved == resolved)

    result = await db.execute(base.order_by(Annotation.created_at.desc()))
    items = []
    for ann, creator in result.all():
        cc = (await db.execute(select(func.count()).where(Comment.annotation_id == ann.id))).scalar() or 0
        items.append(_annotation_response(ann, creator.display_name, cc))
    return items


@router.post("/assets/{asset_id}/annotations", response_model=AnnotationResponse, status_code=201)
async def create_annotation(
    asset_id: UUID,
    req: AnnotationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a spatial annotation on an asset."""
    asset = await db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    ann = Annotation(
        asset_id=asset_id,
        created_by=user.id,
        annotation_type=req.annotation_type,
        position_data=req.position_data,
        content=req.content,
    )
    db.add(ann)
    await db.commit()
    await db.refresh(ann)

    return _annotation_response(ann, user.display_name, 0)


@router.patch("/annotations/{annotation_id}", response_model=AnnotationResponse)
async def update_annotation(
    annotation_id: UUID,
    req: AnnotationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update annotation content or resolve it."""
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    if req.content is not None:
        ann.content = req.content
    if req.resolved is not None:
        ann.resolved = req.resolved
        if req.resolved:
            ann.resolved_by = user.id
            ann.resolved_at = datetime.now(timezone.utc)
        else:
            ann.resolved_by = None
            ann.resolved_at = None

    await db.commit()
    await db.refresh(ann)

    return _annotation_response(ann, "", 0)


@router.delete("/annotations/{annotation_id}")
async def delete_annotation(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete an annotation (creator or admin only)."""
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")
    if ann.created_by != user.id and user.global_role != "org_admin":
        raise HTTPException(status_code=403, detail="Not authorized")

    await db.delete(ann)
    await db.commit()
    return {"message": "Annotation deleted"}


# ── Comments ──────────────────────────────

@router.get("/annotations/{annotation_id}/comments", response_model=list[CommentResponse])
async def list_comments(
    annotation_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List comments on an annotation."""
    result = await db.execute(
        select(Comment, User)
        .join(User, Comment.author_id == User.id)
        .where(Comment.annotation_id == annotation_id)
        .order_by(Comment.created_at.asc())
    )
    return [
        CommentResponse(
            id=str(c.id),
            annotation_id=str(c.annotation_id),
            author_id=str(c.author_id),
            author_name=u.display_name,
            content=c.content,
            edited=c.edited,
            created_at=c.created_at.isoformat(),
        )
        for c, u in result.all()
    ]


@router.post("/annotations/{annotation_id}/comments", response_model=CommentResponse, status_code=201)
async def create_comment(
    annotation_id: UUID,
    req: CommentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Add a comment to an annotation."""
    ann = await db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="Annotation not found")

    comment = Comment(
        annotation_id=annotation_id,
        author_id=user.id,
        content=req.content,
    )
    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=str(comment.id),
        annotation_id=str(comment.annotation_id),
        author_id=str(comment.author_id),
        author_name=user.display_name,
        content=comment.content,
        edited=comment.edited,
        created_at=comment.created_at.isoformat(),
    )


@router.patch("/comments/{comment_id}", response_model=CommentResponse)
async def edit_comment(
    comment_id: UUID,
    req: CommentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Edit a comment."""
    comment = await db.get(Comment, comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if comment.author_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    comment.content = req.content
    comment.edited = True
    await db.commit()
    await db.refresh(comment)

    return CommentResponse(
        id=str(comment.id),
        annotation_id=str(comment.annotation_id),
        author_id=str(comment.author_id),
        author_name=user.display_name,
        content=comment.content,
        edited=comment.edited,
        created_at=comment.created_at.isoformat(),
    )
