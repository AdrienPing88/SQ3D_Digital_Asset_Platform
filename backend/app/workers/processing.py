"""
Processing job dispatcher.
Routes asset types to the appropriate Celery worker task.
"""

from app.models.asset import Asset
from app.models.processing_job import ProcessingJob
from app.core.database import AsyncSessionLocal


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
    """Create a processing_job record and enqueue the Celery task."""
    job_type = ASSET_TYPE_TO_JOB.get(asset.asset_type, "extract_metadata")

    async with AsyncSessionLocal() as db:
        job = ProcessingJob(
            asset_id=asset.id,
            job_type=job_type,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)

    # Enqueue Celery task
    from app.workers.tile_point_cloud import tile_point_cloud

    if job_type == "tile_point_cloud":
        result = tile_point_cloud.delay(str(asset.id))
    else:
        # For MVP, only point cloud tiling is fully implemented.
        # Other job types will use a generic metadata extraction stub.
        from app.workers.generic_worker import process_generic
        result = process_generic.delay(str(asset.id), job_type)

    # Update celery_task_id
    async with AsyncSessionLocal() as db:
        job_record = await db.get(ProcessingJob, job.id)
        if job_record:
            job_record.celery_task_id = result.id
            await db.commit()
