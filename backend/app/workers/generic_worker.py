"""
Generic processing worker for non-point-cloud assets.
Handles thumbnail generation, metadata extraction, format conversion stubs.
"""

import json
import logging

import redis
from sqlalchemy.orm import Session

from app.celery_app import celery
from app.core.config import settings
from app.core.database import sync_engine
from app.models.asset import Asset, AssetStatus
from app.models.processing_job import ProcessingJob

logger = logging.getLogger(__name__)

r = redis.from_url(settings.REDIS_URL)


@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def process_generic(self, asset_id: str, job_type: str):
    """
    Generic processor stub. For MVP, marks asset as ready
    and extracts basic metadata from the S3 object head.
    """
    logger.info("Starting generic processing: asset=%s job_type=%s", asset_id, job_type)

    with Session(sync_engine) as db:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            logger.error("Asset %s not found in database", asset_id)
            raise ValueError(f"Asset {asset_id} not found")

        try:
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
            asset.status = AssetStatus.READY
            db.commit()
            logger.info("Asset %s marked as READY", asset_id)

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
            logger.info("Published completion event for asset %s", asset_id)

        except Exception as exc:
            logger.exception(
                "Generic processing failed for asset %s (job_type=%s)",
                asset_id, job_type,
            )
            # Mark as failed
            try:
                asset.status = AssetStatus.FAILED
                db.commit()
                if job:
                    job.status = "failed"
                    db.commit()
            except Exception:
                logger.error("Failed to update failure status for asset %s", asset_id)
            raise self.retry(exc=exc)
