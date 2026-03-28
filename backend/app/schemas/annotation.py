"""Annotation and comment request/response schemas."""

from typing import Dict, Optional

from pydantic import BaseModel


class AnnotationCreate(BaseModel):
    annotation_type: str
    position_data: Dict
    content: Optional[str] = None


class AnnotationUpdate(BaseModel):
    content: Optional[str] = None
    resolved: Optional[bool] = None


class AnnotationResponse(BaseModel):
    id: str
    asset_id: str
    created_by: str
    creator_name: str = ""
    annotation_type: str
    position_data: Dict
    content: Optional[str] = None
    resolved: bool
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    comment_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class CommentCreate(BaseModel):
    content: str


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: str
    annotation_id: str
    author_id: str
    author_name: str = ""
    content: str
    edited: bool
    created_at: str

    model_config = {"from_attributes": True}
