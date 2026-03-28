"""
Generic processing worker for non-point-cloud assets.
Handles thumbnail generation, metadata extraction, format conversion stubs.
"""

import json

import redis

from app.celery_app import celery
from app.core.config import settings
from app.core.database import sync_engine
from app.models.asset import Asset, AssetStatus
from app.models.processing_job import ProcessingJob

from sqlalchemy.orm import Session

r = redis.from_url(settings.REDIS_URL)


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def process_generic(self, asset_id: str, job_type: str):
    """
    Generic processor stub. For MVP, marks asset as ready
    and extracts basic metadata from the S3 object head.
    """
    with Session(sync_engine) as db:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            raise ValueError(f"Asset {asset_id} not found")

        # Update job progress
        job = (
            db.query(ProcessingJob)
            .filter(
                ProcessingJob.asset_id == asset_id,
                ProcessingJob.job_type == job_type,
            )
            .first()
        )
        if job:
            job.status = "running"
            job.progress_pct = 50
            db.commit()

        # Mark asset as ready (full processing to be implemented per type)
        asset.status = AssetStatus.READY.value
        db.commit()

        if job:
            job.status = "complete"
            job.progress_pct = 100
            db.commit()

        # Publish completion event
        r.publish(
            f"project:{asset.project_id}:events",
            json.dumps({
                "type": "asset.processing_complete",
                "asset_id": asset_id,
                "status": "ready",
                "job_type": job_type,
            }),
        )
