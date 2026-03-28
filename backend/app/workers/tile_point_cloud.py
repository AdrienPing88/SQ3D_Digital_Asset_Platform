"""
Point Cloud Processing Worker
Runs as a Celery task. Triggered by asset upload confirmation.

Pipeline:
  1. Download from S3 to ephemeral local storage
  2. Validate format and extract metadata (PDAL preferred, laspy fallback)
  3. Run Potree tiler to generate LOD octree (PotreeConverter preferred, Python fallback)
  4. Upload tile tree back to S3
  5. Update asset record in DB
  6. Publish completion event to Redis pubsub
"""

import json
import logging
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional

import boto3
import numpy as np
import redis

from app.celery_app import celery
from app.core.config import settings
from app.core.database import sync_engine
from app.models.asset import Asset, AssetStatus

logger = logging.getLogger(__name__)

r = redis.from_url(settings.REDIS_URL)

# ── Dependency checks at module load ──────────────────────────────────

_HAS_PDAL = False
try:
    import pdal
    _HAS_PDAL = True
    logger.info("PDAL is available — will use for metadata extraction.")
except ImportError:
    logger.warning(
        "PDAL Python bindings not available. "
        "Falling back to laspy for LAS/LAZ reading."
    )

_HAS_LASPY = False
try:
    import laspy
    _HAS_LASPY = True
    logger.info("laspy is available — Python-native LAS/LAZ support enabled.")
except ImportError:
    logger.warning("laspy is not installed. LAS/LAZ fallback will not work.")

_HAS_POTREE_CONVERTER = shutil.which("PotreeConverter") is not None
if _HAS_POTREE_CONVERTER:
    logger.info("PotreeConverter found on PATH — will use for tiling.")
else:
    logger.warning(
        "PotreeConverter not found on PATH. "
        "Will use Python-native fallback tiler (reduced quality)."
    )


# ── Celery task ──────────────────────────────────────────────────────

@celery.task(bind=True, max_retries=3, default_retry_delay=30)
def tile_point_cloud(self, asset_id: str):
    """
    Tiles a LAZ/LAS/E57 file into a Potree-compatible LOD octree.
    Uploads the tile tree to S3 and updates the asset record.
    """
    from sqlalchemy.orm import Session

    logger.info("Starting tile_point_cloud for asset %s", asset_id)

    with Session(sync_engine) as db:
        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            logger.error("Asset %s not found in database", asset_id)
            raise ValueError(f"Asset {asset_id} not found")

        try:
            _update_job_progress(db, asset_id, "tile_point_cloud", 5)

            with tempfile.TemporaryDirectory() as tmpdir:
                local_input = Path(tmpdir) / asset.name
                tile_output_dir = Path(tmpdir) / "tiles"
                tile_output_dir.mkdir()

                # -- Step 1: Download from S3 ----------------------------------
                logger.info("Downloading asset %s from S3: %s/%s",
                            asset_id, asset.storage_bucket, asset.storage_key)

                s3_kwargs = dict(
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_REGION,
                )
                if settings.S3_ENDPOINT_URL:
                    s3_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
                s3 = boto3.client("s3", **s3_kwargs)

                try:
                    s3.download_file(
                        asset.storage_bucket,
                        asset.storage_key,
                        str(local_input),
                    )
                except Exception as exc:
                    logger.error("S3 download failed for asset %s: %s", asset_id, exc)
                    _fail_asset(db, asset, asset_id, f"S3 download failed: {exc}")
                    raise self.retry(exc=exc)

                file_size = local_input.stat().st_size
                logger.info("Downloaded %s (%.2f MB)", asset.name, file_size / 1e6)
                _update_job_progress(db, asset_id, "tile_point_cloud", 20)

                # -- Step 2: Extract metadata ----------------------------------
                logger.info("Extracting metadata for asset %s", asset_id)
                try:
                    metadata = _extract_metadata(str(local_input))
                except Exception as exc:
                    logger.error("Metadata extraction failed for asset %s: %s", asset_id, exc)
                    _fail_asset(db, asset, asset_id, f"Metadata extraction failed: {exc}")
                    raise

                logger.info(
                    "Metadata: %d points, bbox=[%.2f,%.2f,%.2f]-[%.2f,%.2f,%.2f]",
                    metadata["point_count"],
                    metadata["bbox"]["minx"], metadata["bbox"]["miny"], metadata["bbox"]["minz"],
                    metadata["bbox"]["maxx"], metadata["bbox"]["maxy"], metadata["bbox"]["maxz"],
                )
                _update_job_progress(db, asset_id, "tile_point_cloud", 35)

                # -- Step 3: Tile the point cloud ------------------------------
                logger.info("Tiling point cloud for asset %s", asset_id)
                try:
                    tile_root_file = _tile_point_cloud(
                        str(local_input), str(tile_output_dir), metadata
                    )
                except Exception as exc:
                    logger.error("Tiling failed for asset %s: %s", asset_id, exc)
                    _fail_asset(db, asset, asset_id, f"Tiling failed: {exc}")
                    raise

                _update_job_progress(db, asset_id, "tile_point_cloud", 70)

                # -- Step 4: Upload tile tree to S3 ----------------------------
                tile_s3_prefix = (
                    f"orgs/{asset.project.org_id}/projects/{asset.project_id}"
                    f"/tiles/{asset_id}/"
                )
                logger.info("Uploading tiles to S3 prefix: %s", tile_s3_prefix)

                tile_count = 0
                for tile_file in tile_output_dir.rglob("*"):
                    if tile_file.is_file():
                        relative = tile_file.relative_to(tile_output_dir)
                        s3_key = tile_s3_prefix + str(relative).replace("\\", "/")
                        try:
                            s3.upload_file(str(tile_file), settings.S3_BUCKET, s3_key)
                            tile_count += 1
                        except Exception as exc:
                            logger.error(
                                "Failed to upload tile %s for asset %s: %s",
                                relative, asset_id, exc,
                            )
                            raise

                logger.info("Uploaded %d tile files for asset %s", tile_count, asset_id)
                _update_job_progress(db, asset_id, "tile_point_cloud", 90)

                # -- Step 5: Update asset record -------------------------------
                tile_root_key = tile_s3_prefix + tile_root_file
                asset.tile_root_key = tile_root_key
                asset.status = AssetStatus.READY
                asset.spatial_metadata = {
                    "point_count": metadata["point_count"],
                    "bbox": metadata["bbox"],
                    "srs": metadata.get("srs", ""),
                    "tile_root_key": tile_root_key,
                }
                db.commit()
                logger.info("Asset %s marked READY, tile_root_key=%s", asset_id, tile_root_key)

                _update_job_progress(db, asset_id, "tile_point_cloud", 100, status="complete")

                # -- Step 6: Publish completion event --------------------------
                r.publish(
                    f"project:{asset.project_id}:events",
                    json.dumps({
                        "type": "asset.processing_complete",
                        "asset_id": asset_id,
                        "status": "ready",
                        "tile_root_key": tile_root_key,
                    }),
                )
                logger.info("Published completion event for asset %s", asset_id)

        except Exception as exc:
            logger.exception("tile_point_cloud failed for asset %s", asset_id)
            # Ensure the asset is marked as failed if not already
            try:
                db.refresh(asset)
                if asset.status != AssetStatus.FAILED:
                    _fail_asset(db, asset, asset_id, str(exc))
            except Exception:
                pass
            raise


# ── Metadata extraction ──────────────────────────────────────────────

def _extract_metadata(filepath: str) -> dict[str, Any]:
    """
    Extract point cloud metadata. Uses PDAL if available, falls back to laspy.
    """
    if _HAS_PDAL:
        return _extract_metadata_pdal(filepath)
    elif _HAS_LASPY:
        return _extract_metadata_laspy(filepath)
    else:
        raise RuntimeError(
            "Neither PDAL nor laspy is available. "
            "Install at least one to process point cloud files."
        )


def _extract_metadata_pdal(filepath: str) -> dict[str, Any]:
    """Extract metadata using PDAL pipeline."""
    pipeline_json = json.dumps({
        "pipeline": [
            {"type": "readers.las", "filename": filepath},
            {"type": "filters.info"},
        ]
    })
    pipeline = pdal.Pipeline(pipeline_json)
    pipeline.execute()
    meta = pipeline.metadata

    reader_meta = meta["metadata"]["readers.las"]
    return {
        "point_count": reader_meta["count"],
        "bbox": {
            "minx": reader_meta["minx"],
            "miny": reader_meta["miny"],
            "minz": reader_meta["minz"],
            "maxx": reader_meta["maxx"],
            "maxy": reader_meta["maxy"],
            "maxz": reader_meta["maxz"],
        },
        "srs": reader_meta.get("spatialreference", ""),
    }


def _extract_metadata_laspy(filepath: str) -> dict[str, Any]:
    """Extract metadata using laspy (Python-native fallback)."""
    with laspy.open(filepath) as f:
        header = f.header
        return {
            "point_count": header.point_count,
            "bbox": {
                "minx": float(header.mins[0]),
                "miny": float(header.mins[1]),
                "minz": float(header.mins[2]),
                "maxx": float(header.maxs[0]),
                "maxy": float(header.maxs[1]),
                "maxz": float(header.maxs[2]),
            },
            "srs": _extract_srs_from_laspy(header),
        }


def _extract_srs_from_laspy(header) -> str:
    """Attempt to extract SRS/CRS string from laspy header VLRs."""
    try:
        for vlr in header.vlrs:
            # GeoTIFF GeoKeyDirectoryTag or WKT
            if vlr.record_id in (2112, 34735):
                return vlr.record_data.decode("utf-8", errors="replace")
    except Exception:
        pass
    return ""


# ── Tiling ───────────────────────────────────────────────────────────

def _tile_point_cloud(
    input_path: str,
    output_dir: str,
    metadata: dict[str, Any],
) -> str:
    """
    Tile the point cloud. Uses PotreeConverter if available,
    otherwise falls back to a Python-native octree builder.

    Returns the name of the root tile file (relative to output_dir).
    """
    if _HAS_POTREE_CONVERTER:
        return _tile_with_potree_converter(input_path, output_dir)
    else:
        logger.info("Using Python-native fallback tiler.")
        return _tile_with_python_fallback(input_path, output_dir, metadata)


def _tile_with_potree_converter(input_path: str, output_dir: str) -> str:
    """Run PotreeConverter as a subprocess."""
    logger.info("Running PotreeConverter on %s", input_path)

    try:
        result = subprocess.run(
            [
                "PotreeConverter",
                input_path,
                "-o", output_dir,
                "--output-format", "LAZ",
                "--generate-page", "false",
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("PotreeConverter timed out after 1 hour")
    except FileNotFoundError:
        raise RuntimeError(
            "PotreeConverter binary not found. "
            "Ensure it is installed and on PATH."
        )

    if result.returncode != 0:
        logger.error("PotreeConverter stderr: %s", result.stderr)
        raise RuntimeError(f"PotreeConverter failed (exit {result.returncode}): {result.stderr}")

    logger.info("PotreeConverter stdout: %s", result.stdout[-500:] if result.stdout else "(empty)")
    return "cloud.js"


def _tile_with_python_fallback(
    input_path: str,
    output_dir: str,
    metadata: dict[str, Any],
) -> str:
    """
    Python-native fallback tiler using laspy.

    Generates a simple octree-style tiled output that the frontend can load:
    - metadata.json: bounding box, point count, hierarchy info
    - octree/r.bin: root node binary point data
    - octree/r0.bin ... r7.bin: child nodes (one level of subdivision)

    Binary format per point: float32 x, y, z, uint8 r, g, b, a (16 bytes/point)
    This is directly loadable as a Three.js BufferGeometry.
    """
    if not _HAS_LASPY:
        raise RuntimeError("laspy is required for Python-native fallback tiling.")

    logger.info("Reading point cloud with laspy: %s", input_path)
    las = laspy.read(input_path)

    # Extract XYZ coordinates
    points_x = np.array(las.x, dtype=np.float64)
    points_y = np.array(las.y, dtype=np.float64)
    points_z = np.array(las.z, dtype=np.float64)
    n_points = len(points_x)
    logger.info("Read %d points from file.", n_points)

    # Extract color if available, otherwise use intensity or white
    colors_r, colors_g, colors_b = _extract_colors(las)

    # Build a simple single-level octree
    bbox = metadata["bbox"]
    cx = (bbox["minx"] + bbox["maxx"]) / 2.0
    cy = (bbox["miny"] + bbox["maxy"]) / 2.0
    cz = (bbox["minz"] + bbox["maxz"]) / 2.0

    # Create output directories
    octree_dir = Path(output_dir) / "octree"
    octree_dir.mkdir(parents=True, exist_ok=True)

    # Assign each point to one of 8 octants
    octant_x = (points_x >= cx).astype(np.int32)
    octant_y = (points_y >= cy).astype(np.int32)
    octant_z = (points_z >= cz).astype(np.int32)
    octant_indices = octant_x * 4 + octant_y * 2 + octant_z

    # For the root node, subsample to at most 50k points for quick loading
    max_root_points = 50_000
    hierarchy = {}

    if n_points <= max_root_points:
        # Small file: everything goes in root
        _write_binary_points(
            octree_dir / "r.bin",
            points_x, points_y, points_z,
            colors_r, colors_g, colors_b,
        )
        hierarchy["r"] = n_points
    else:
        # Subsample for root node (every Nth point)
        step = max(1, n_points // max_root_points)
        root_mask = np.zeros(n_points, dtype=bool)
        root_mask[::step] = True

        _write_binary_points(
            octree_dir / "r.bin",
            points_x[root_mask], points_y[root_mask], points_z[root_mask],
            colors_r[root_mask], colors_g[root_mask], colors_b[root_mask],
        )
        hierarchy["r"] = int(root_mask.sum())

        # Write child nodes (octants)
        for octant in range(8):
            mask = octant_indices == octant
            if not mask.any():
                continue

            node_name = f"r{octant}"
            _write_binary_points(
                octree_dir / f"{node_name}.bin",
                points_x[mask], points_y[mask], points_z[mask],
                colors_r[mask], colors_g[mask], colors_b[mask],
            )
            hierarchy[node_name] = int(mask.sum())

    # Write metadata JSON
    tile_metadata = {
        "version": "1.0",
        "generator": "sq3d-python-fallback",
        "point_count": n_points,
        "bbox": bbox,
        "srs": metadata.get("srs", ""),
        "point_format": {
            "bytes_per_point": 16,
            "attributes": [
                {"name": "x", "type": "float32", "offset": 0},
                {"name": "y", "type": "float32", "offset": 4},
                {"name": "z", "type": "float32", "offset": 8},
                {"name": "rgba", "type": "uint8x4", "offset": 12},
            ],
        },
        "hierarchy": hierarchy,
        "octree": {
            "center": [cx, cy, cz],
            "half_size": [
                (bbox["maxx"] - bbox["minx"]) / 2.0,
                (bbox["maxy"] - bbox["miny"]) / 2.0,
                (bbox["maxz"] - bbox["minz"]) / 2.0,
            ],
        },
    }

    metadata_path = Path(output_dir) / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(tile_metadata, f, indent=2)

    logger.info(
        "Python fallback tiler complete: %d nodes, %d total points",
        len(hierarchy), n_points,
    )
    return "metadata.json"


def _extract_colors(las) -> tuple:
    """Extract RGB colors from a laspy point cloud, with fallbacks."""
    n_points = las.header.point_count

    # Try RGB fields (common in LAS format 2, 3, 7, 8)
    try:
        # LAS stores 16-bit colors; scale to 8-bit
        r = (np.array(las.red, dtype=np.float64) / 256.0).clip(0, 255).astype(np.uint8)
        g = (np.array(las.green, dtype=np.float64) / 256.0).clip(0, 255).astype(np.uint8)
        b = (np.array(las.blue, dtype=np.float64) / 256.0).clip(0, 255).astype(np.uint8)
        if r.max() > 0 or g.max() > 0 or b.max() > 0:
            return r, g, b
    except Exception:
        pass

    # Fallback: use intensity mapped to grayscale
    try:
        intensity = np.array(las.intensity, dtype=np.float64)
        i_max = intensity.max()
        if i_max > 0:
            gray = (intensity / i_max * 255.0).clip(0, 255).astype(np.uint8)
            return gray, gray, gray
    except Exception:
        pass

    # Last resort: white
    white = np.full(n_points, 255, dtype=np.uint8)
    return white, white, white


def _write_binary_points(
    filepath: Path,
    x: np.ndarray,
    y: np.ndarray,
    z: np.ndarray,
    r: np.ndarray,
    g: np.ndarray,
    b: np.ndarray,
):
    """
    Write points as a flat binary buffer: [float32 x, y, z, uint8 r, g, b, a] per point.
    16 bytes per point, directly usable as a Three.js BufferGeometry data source.
    """
    n = len(x)
    buf = bytearray(n * 16)

    x32 = x.astype(np.float32)
    y32 = y.astype(np.float32)
    z32 = z.astype(np.float32)
    alpha = np.full(n, 255, dtype=np.uint8)

    # Pack as interleaved array: x,y,z (float32 each) + r,g,b,a (uint8 each)
    # Use numpy structured array for efficient packing
    dtype = np.dtype([
        ("x", np.float32),
        ("y", np.float32),
        ("z", np.float32),
        ("r", np.uint8),
        ("g", np.uint8),
        ("b", np.uint8),
        ("a", np.uint8),
    ])
    packed = np.empty(n, dtype=dtype)
    packed["x"] = x32
    packed["y"] = y32
    packed["z"] = z32
    packed["r"] = r
    packed["g"] = g
    packed["b"] = b
    packed["a"] = alpha

    with open(filepath, "wb") as f:
        f.write(packed.tobytes())

    logger.debug("Wrote %d points (%.2f KB) to %s", n, len(packed.tobytes()) / 1024, filepath)


# ── Helpers ──────────────────────────────────────────────────────────

def _fail_asset(db, asset, asset_id: str, error_msg: str):
    """Mark an asset as FAILED and update the processing job."""
    try:
        asset.status = AssetStatus.FAILED
        db.commit()
        _update_job_progress(db, asset_id, "tile_point_cloud", -1, status="failed")
        logger.error("Asset %s marked as FAILED: %s", asset_id, error_msg)
    except Exception as inner_exc:
        logger.error("Failed to mark asset %s as FAILED: %s", asset_id, inner_exc)


def _update_job_progress(
    db, asset_id: str, job_type: str, progress: int, status: str = "running"
):
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
