"""Project request/response schemas."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    coordinate_system: str = "EPSG:4326"
    metadata: Dict = {}


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    coordinate_system: Optional[str] = None
    metadata: Optional[Dict] = None
    archived: Optional[bool] = None


class ProjectResponse(BaseModel):
    id: str
    org_id: str
    name: str
    description: Optional[str] = None
    coordinate_system: str
    metadata: Dict
    archived: bool
    asset_count: int = 0
    member_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ProjectMemberAdd(BaseModel):
    email: str
    role: str = "collaborator"


class ProjectMemberUpdate(BaseModel):
    role: str


class ProjectMemberResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    role: str
    granted_at: str
