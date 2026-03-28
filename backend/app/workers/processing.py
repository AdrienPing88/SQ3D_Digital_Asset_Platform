"""
Processing job dispatcher.
Routes asset types to the appropriate Celery worker task.

Handles:
  - Creating a ProcessingJob record in the database
  - Dispatching the correct Celery task based on asset type
  - Updating the celery_task_id for tracking
  - Error handling and status updates on dispatch failure
"""

import logging

from app.core.database import AsyncSessionLocal
from app.models.asset import Asset, AssetStatus
from app.models.processing_job import ProcessingJob

logger = logging.getLogger(__name__)

ASSET_TYPE_TO_JOB = {
    "las": "tile_point_cloud",
    "laz": "tile_point_cloud",
    "e57": "tile_point_cloud",
    "orthomosaic": "generate_thumbnail",
    "geotiff": "generate_thumbnail",
    "pdf": "generate_thumbnail",
    "dwg": "generate_thumbnail",
    "dxf": "generate_thumbnail",
    "rvt": "convert_to_glb",
    "ifc": "convert_to_glb",
    "obj": "generate_thumbnail",
    "fbx": "convert_to_glb",
    "glb": "generate_thumbnail",
    "gltf": "generate_thumbnail",
}


async def dispatch_processing_job(asset: Asset):
    """
    Create a processing_job record and enqueue the Celery task.

    Raises on failure so the caller can decide whether to retry or
    leave the asset in PROCESSING state.
    """
    job_type = ASSET_TYPE_TO_JOB.get(asset.asset_type, "extract_metadata")

    logger.info(
        "Dispatching processing job: asset=%s type=%s job_type=%s",
        asset.id, asset.asset_type, job_type,
    )

    # Create the processing job record
    async with AsyncSessionLocal() as db:
        job = ProcessingJob(
            asset_id=asset.id,
            job_type=job_type,
            status="pending",
            progress_pct=0,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    logger.info("Created ProcessingJob %s for asset %s", job_id, asset.id)

    # Enqueue the appropriate Celery task
    try:
        if job_type == "tile_point_cloud":
            from app.workers.tile_point_cloud import tile_point_cloud
            result = tile_point_cloud.delay(str(asset.id))
        else:
            # For MVP, only point cloud tiling is fully implemented.
            # Other job types use a generic metadata extraction stub.
            from app.workers.generic_worker import process_generic
            result = process_generic.delay(str(asset.id), job_type)

        logger.info(
            "Enqueued Celery task %s (task_id=%s) for asset %s",
            job_type, result.id, asset.id,
        )
    except Exception as exc:
        logger.error(
            "Failed to enqueue Celery task for asset %s: %s",
            asset.id, exc,
        )
        # Mark job as failed since we could not enqueue
        async with AsyncSessionLocal() as db:
            job_record = await db.get(ProcessingJob, job_id)
            if job_record:
                job_record.status = "failed"
                await db.commit()
        raise

    # Update the celery_task_id on the job record for tracking
    async with AsyncSessionLocal() as db:
        job_record = await db.get(ProcessingJob, job_id)
        if job_record:
            job_record.celery_task_id = result.id
            job_record.status = "queued"
            await db.commit()
            logger.info(
                "Updated ProcessingJob %s with celery_task_id=%s",
                job_id, result.id,
            )
