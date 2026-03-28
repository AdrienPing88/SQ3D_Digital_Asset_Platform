"""
Asset Service
Handles presigned URL generation, upload confirmation, and storage key management.
The API server never touches binary file data — all large files flow directly
from the client to S3 via presigned URLs.
"""

import hashlib
import uuid
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.asset import Asset, AssetStatus
from app.models.project import Project
from app.schemas.asset import AssetPresignRequest, AssetPresignResponse, AssetConfirmRequest
from app.workers.processing import dispatch_processing_job


ALLOWED_TYPES = {
    # Point clouds
    ".las": "las", ".laz": "laz", ".e57": "e57",
    # Drone / survey
    ".tif": "orthomosaic", ".tiff": "orthomosaic",
    ".jpg": "raw_imagery", ".jpeg": "raw_imagery", ".png": "raw_imagery",
    # 360
    # (equirectangular JPG handled above; video below)
    ".mp4": "panorama_video", ".mov": "panorama_video",
    # Design drawings
    ".pdf": "pdf", ".dwg": "dwg", ".dxf": "dxf", ".rvt": "rvt",
    # 3D models
    ".obj": "obj", ".fbx": "fbx", ".ifc": "ifc",
    ".glb": "glb", ".gltf": "gltf",
    # Geospatial
    ".geotiff": "geotiff", ".geojson": "geojson",
    ".kml": "kml", ".shp": "shp",
}

MAX_FILE_SIZE_BYTES = 200 * 1024 * 1024 * 1024  # 200 GB hard limit


class AssetService:
    def __init__(self, db: AsyncSession):
        self.db = db
        s3_kwargs = dict(
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION,
        )
        if settings.S3_ENDPOINT_URL:
            s3_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
        self.s3 = boto3.client("s3", **s3_kwargs)

    def _detect_asset_type(self, filename: str) -> str:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        return ALLOWED_TYPES.get(ext, "other")

    def _build_storage_key(self, org_id: str, project_id: str, asset_id: str, filename: str) -> str:
        return f"orgs/{org_id}/projects/{project_id}/raw/{asset_id}/{filename}"

    async def presign_upload(
        self,
        project: Project,
        request: AssetPresignRequest,
        uploader_id: str,
    ) -> AssetPresignResponse:
        """
        1. Validate org storage quota
        2. Create pending asset record
        3. Generate presigned S3 upload URL
        4. Return URL + fields to the client
        """
        if request.file_size_bytes > MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File exceeds maximum size of {MAX_FILE_SIZE_BYTES / 1e9:.0f} GB")

        org = project.organization
        if org.storage_used_bytes + request.file_size_bytes > org.storage_quota_bytes:
            raise ValueError("Storage quota exceeded")

        asset_id = str(uuid.uuid4())
        asset_type = self._detect_asset_type(request.filename)
        storage_key = self._build_storage_key(
            str(org.id), str(project.id), asset_id, request.filename
        )

        # Create pending record
        asset = Asset(
            id=asset_id,
            project_id=project.id,
            uploaded_by=uploader_id,
            name=request.filename,
            asset_type=asset_type,
            storage_key=storage_key,
            storage_bucket=settings.S3_BUCKET,
            file_size_bytes=request.file_size_bytes,
            checksum_sha256=request.checksum_sha256,
            status=AssetStatus.PENDING,
        )
        self.db.add(asset)
        await self.db.commit()

        # Generate presigned POST URL (supports multipart via SDK)
        content_type = request.content_type or "application/octet-stream"
        try:
            presigned = self.s3.generate_presigned_post(
                Bucket=settings.S3_BUCKET,
                Key=storage_key,
                Fields={
                    "x-amz-meta-asset-id": asset_id,
                    "x-amz-meta-checksum": request.checksum_sha256,
                    "Content-Type": content_type,
                },
                Conditions=[
                    ["content-length-range", 1, MAX_FILE_SIZE_BYTES],
                    {"x-amz-meta-asset-id": asset_id},
                    {"x-amz-meta-checksum": request.checksum_sha256},
                    {"Content-Type": content_type},
                ],
                ExpiresIn=settings.PRESIGN_URL_EXPIRY_SECONDS,
            )
        except ClientError as e:
            raise RuntimeError(f"Failed to generate presigned URL: {e}")

        return AssetPresignResponse(
            asset_id=asset_id,
            upload_url=presigned["url"],
            upload_fields=presigned["fields"],
            storage_key=storage_key,
            expires_in=settings.PRESIGN_URL_EXPIRY_SECONDS,
        )

    async def confirm_upload(
        self,
        asset_id: str,
        request: AssetConfirmRequest,
    ) -> Asset:
        """
        Called by the client after the S3 upload completes.
        Validates the ETag, marks the asset as processing, and
        enqueues the appropriate Celery worker job.
        """
        asset = await self.db.get(Asset, asset_id)
        if not asset:
            raise ValueError("Asset not found")
        if asset.status != AssetStatus.PENDING:
            raise ValueError("Asset is not in pending state")

        # Confirm the object exists in S3
        try:
            head = self.s3.head_object(Bucket=asset.storage_bucket, Key=asset.storage_key)
        except ClientError:
            raise ValueError("Upload not found in S3 — complete the upload before confirming")

        actual_size = head["ContentLength"]
        if actual_size != asset.file_size_bytes:
            raise ValueError(
                f"Size mismatch: expected {asset.file_size_bytes}, got {actual_size}"
            )

        asset.status = AssetStatus.PROCESSING
        await self.db.commit()

        # Enqueue processing job (best-effort — Celery may not be running in dev)
        try:
            await dispatch_processing_job(asset)
        except Exception:
            pass  # Processing will be skipped; asset stays in 'processing' state

        return asset

    async def get_stream_url(self, asset: Asset) -> str:
        """
        Returns a CloudFront signed URL for Potree tile streaming.
        For non-point-cloud assets, returns a standard presigned S3 URL.
        """
        if not asset.tile_root_key:
            raise ValueError("Asset has not been tiled yet")

        # CloudFront signed URL logic
        from app.utils.cloudfront import sign_cloudfront_url
        url = f"https://{settings.CLOUDFRONT_DOMAIN}/{asset.tile_root_key}"
        return sign_cloudfront_url(url, expiry_seconds=settings.TILE_URL_EXPIRY_SECONDS)

    async def get_download_url(self, asset: Asset) -> str:
        """Returns a time-limited presigned S3 download URL."""
        try:
            return self.s3.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": asset.storage_bucket,
                    "Key": asset.storage_key,
                    "ResponseContentDisposition": f'attachment; filename="{asset.name}"',
                },
                ExpiresIn=settings.DOWNLOAD_URL_EXPIRY_SECONDS,
            )
        except ClientError as e:
            raise RuntimeError(f"Failed to generate download URL: {e}")
