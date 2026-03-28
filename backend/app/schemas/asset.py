"""Asset request/response schemas."""

from typing import Dict, Optional

from pydantic import BaseModel


class AssetPresignRequest(BaseModel):
    filename: str
    file_size_bytes: int
    checksum_sha256: str
    content_type: Optional[str] = None


class AssetPresignResponse(BaseModel):
    asset_id: str
    upload_url: str
    upload_fields: Dict[str, str]
    storage_key: str
    expires_in: int


class AssetConfirmRequest(BaseModel):
    etag: Optional[str] = None


class AssetResponse(BaseModel):
    id: str
    project_id: str
    uploaded_by: str
    name: str
    asset_type: str
    file_size_bytes: int
    status: str
    spatial_metadata: Dict
    version: int
    thumbnail_url: Optional[str] = None
    tile_root_url: Optional[str] = None
    annotation_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    metadata: Optional[Dict] = None
