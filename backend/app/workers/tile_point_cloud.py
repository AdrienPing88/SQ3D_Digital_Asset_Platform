"""
Point Cloud Processing Worker
Runs as a Celery task. Triggered by asset upload confirmation.

Pipeline:
  1. Download from S3 to ephemeral local storage
  2. Validate format and CRS via PDAL
  3. Run Potree tiler to generate LOD octree
  4. Upload tile tree back to S3
  5. Extract spatial metadata (bbox, point count, density, CRS)
  6. Update asset record in DB
  7. Publish completion event to Redis pubsub
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import boto3
import pdal
import redis

from app.celery_app import celery
from app.core.config import settings
from app.core.database import sync_engine
from app.models.asset import Asset, AssetStatus


r = redis.from_url(settings.REDIS_URL)


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def tile_point_cloud(self, asset_id: str):
    """
    Tiles a LAZ/LAS/E57 file into a Potree-compatible LOD octree.
    Uploads the tile tree to S3 and updates the asset record.
    """
    from sqlalchemy.orm import Session
    with Session(sync_engine) as db:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        _update_job_progress(db, asset_id, "tile_point_cloud", 5)

        with tempfile.TemporaryDirectory() as tmpdir:
            local_input = Path(tmpdir) / asset.name
            tile_output_dir = Path(tmpdir) / "tiles"
            tile_output_dir.mkdir()

            # ─ Step 1: Download from S3 ─────────────────────────
            s3 = boto3.client("s3")
            s3.download_file(asset.storage_bucket, asset.storage_key, str(local_input))
            _update_job_progress(db, asset_id, "tile_point_cloud", 20)

            # ─ Step 2: Validate + extract metadata via PDAL ─────
            pipeline_json = json.dumps({
                "pipeline": [
                    {"type": "readers.las", "filename": str(local_input)},
                    {"type": "filters.info"},
                ]
            })
            pipeline = pdal.Pipeline(pipeline_json)
            pipeline.execute()
            metadata = pipeline.metadata

            point_count = metadata["metadata"]["readers.las"]["count"]
            minx = metadata["metadata"]["readers.las"]["minx"]
            miny = metadata["metadata"]["readers.las"]["miny"]
            minz = metadata["metadata"]["readers.las"]["minz"]
            maxx = metadata["metadata"]["readers.las"]["maxx"]
            maxy = metadata["metadata"]["readers.las"]["maxy"]
            maxz = metadata["metadata"]["readers.las"]["maxz"]
            srs = metadata["metadata"]["readers.las"]["spatialreference"]

            _update_job_progress(db, asset_id, "tile_point_cloud", 35)

            # ─ Step 3: Run PotreeConverter ───────────────────────
            result = subprocess.run(
                [
                    "PotreeConverter",
                    str(local_input),
                    "-o", str(tile_output_dir),
                    "--output-format", "LAZ",
                    "--generate-page", "false",
                ],
                capture_output=True,
                text=True,
                timeout=3600,  # 1-hour timeout for large files
            )
            if result.returncode != 0:
                raise RuntimeError(f"PotreeConverter failed: {result.stderr}")

            _update_job_progress(db, asset_id, "tile_point_cloud", 70)

            # ─ Step 4: Upload tile tree to S3 ────────────────────
            tile_s3_prefix = (
                f"orgs/{asset.project.org_id}/projects/{asset.project_id}"
                f"/tiles/{asset_id}/"
            )
            for tile_file in tile_output_dir.rglob("*"):
                if tile_file.is_file():
                    relative = tile_file.relative_to(tile_output_dir)
                    s3.upload_file(
                        str(tile_file),
                        settings.S3_BUCKET,
                        tile_s3_prefix + str(relative),
                    )

            _update_job_progress(db, asset_id, "tile_point_cloud", 90)

            # ─ Step 5: Update asset record ───────────────────────
            asset.tile_root_key = tile_s3_prefix + "cloud.js"
            asset.status = AssetStatus.READY
            asset.spatial_metadata = {
                "point_count": point_count,
                "bbox": {
                    "minx": minx, "miny": miny, "minz": minz,
                    "maxx": maxx, "maxy": maxy, "maxz": maxz,
                },
                "srs": srs,
                "tile_root_key": asset.tile_root_key,
            }
            db.commit()

            _update_job_progress(db, asset_id, "tile_point_cloud", 100, status="complete")

            # ─ Step 6: Publish completion event ──────────────────
            r.publish(
                f"project:{asset.project_id}:events",
                json.dumps({
                    "type": "asset.processing_complete",
                    "asset_id": asset_id,
                    "status": "ready",
                    "tile_root_key": asset.tile_root_key,
                }),
            )


def _update_job_progress(db, asset_id: str, job_type: str, progress: int, status: str = "running"):
    from app.models.processing_job import ProcessingJob
    job = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.asset_id == asset_id,
            ProcessingJob.job_type == job_type,
        )
        .first()
    )
    if job:
        job.progress_pct = progress
        job.status = status
        db.commit()
