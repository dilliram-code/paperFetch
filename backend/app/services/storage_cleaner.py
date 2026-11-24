"""Automated Storage Flush and Disk Quota Manager for Render Free Tier."""
import asyncio
from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, Optional
from sqlalchemy import desc, select, update

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal
from backend.app.models import Paper

logger = logging.getLogger(__name__)

_cleanup_task: Optional[asyncio.Task] = None


def get_current_storage_usage() -> Dict[str, Any]:
    """Calculate current disk usage for downloads, temp files, and database."""
    downloads_bytes = 0
    temp_bytes = 0

    if settings.STORAGE_DIR.exists():
        downloads_bytes = sum(
            f.stat().st_size for f in settings.STORAGE_DIR.glob("*") if f.is_file()
        )

    if settings.TEMP_DIR.exists():
        temp_bytes = sum(
            f.stat().st_size for f in settings.TEMP_DIR.glob("*") if f.is_file()
        )

    total_bytes = downloads_bytes + temp_bytes
    return {
        "downloads_bytes": downloads_bytes,
        "temp_bytes": temp_bytes,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "limit_mb": settings.MAX_STORAGE_MB,
        "usage_percent": round((total_bytes / (settings.MAX_STORAGE_MB * 1024 * 1024)) * 100, 1)
        if settings.MAX_STORAGE_MB > 0
        else 0.0,
    }


def cleanup_temp_and_orphan_files(max_age_seconds: int = 1800) -> Dict[str, int]:
    """Delete temporary ZIP files and orphaned .part files older than max_age_seconds."""
    now = time.time()
    deleted_count = 0
    freed_bytes = 0

    # Clean storage/temp
    if settings.TEMP_DIR.exists():
        for f in settings.TEMP_DIR.glob("*"):
            if f.is_file():
                try:
                    if now - f.stat().st_mtime > max_age_seconds:
                        size = f.stat().st_size
                        f.unlink()
                        deleted_count += 1
                        freed_bytes += size
                except Exception as e:
                    logger.debug(f"Failed to delete temp file {f}: {e}")

    # Clean orphaned .part files in storage/downloads
    if settings.STORAGE_DIR.exists():
        for f in settings.STORAGE_DIR.glob("*.part"):
            if f.is_file():
                try:
                    if now - f.stat().st_mtime > max_age_seconds:
                        size = f.stat().st_size
                        f.unlink()
                        deleted_count += 1
                        freed_bytes += size
                except Exception as e:
                    logger.debug(f"Failed to delete orphaned part file {f}: {e}")

    return {"deleted_files": deleted_count, "freed_bytes": freed_bytes}


async def flush_storage_if_needed(
    force_flush: bool = False,
    target_max_mb: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Check current disk usage against MAX_STORAGE_MB and retention policies.
    If storage exceeds threshold, flushes oldest downloaded files from disk while
    preserving all bibliographic metadata, BibTeX citations, and history records.
    """
    limit_mb = target_max_mb or settings.MAX_STORAGE_MB
    limit_bytes = limit_mb * 1024 * 1024
    target_recovery_bytes = int(limit_bytes * 0.7)  # Flush down to 70% of limit

    # Step 1: Clean temp and orphaned part files first
    temp_result = cleanup_temp_and_orphan_files(max_age_seconds=900)
    freed_bytes = temp_result["freed_bytes"]

    # Step 2: Calculate total downloads usage
    usage = get_current_storage_usage()
    current_total_bytes = usage["total_bytes"]

    retention_cutoff = None
    if settings.STORAGE_RETENTION_HOURS > 0:
        retention_cutoff = datetime.utcnow() - timedelta(hours=settings.STORAGE_RETENTION_HOURS)

    should_flush = force_flush or (current_total_bytes > limit_bytes)
    papers_flushed = 0

    async with AsyncSessionLocal() as db:
        # Check if any papers exceed retention hours
        if retention_cutoff and not should_flush:
            old_papers_res = await db.execute(
                select(Paper)
                .where(Paper.local_path.isnot(None))
                .where(Paper.created_at < retention_cutoff)
            )
            if old_papers_res.scalars().first():
                should_flush = True

        if should_flush:
            logger.info(
                f"Auto-flush triggered! Current storage: {usage['total_mb']}MB / Limit: {limit_mb}MB"
            )

            # Query completed papers ordered by created_at ascending (LRU / oldest first)
            res = await db.execute(
                select(Paper)
                .where(Paper.local_path.isnot(None))
                .order_by(Paper.created_at.asc())
            )
            papers = list(res.scalars().all())

            for paper in papers:
                # Stop if usage dropped below recovery threshold and retention cutoff is satisfied
                if (
                    not force_flush
                    and (current_total_bytes - freed_bytes <= target_recovery_bytes)
                    and (not retention_cutoff or (paper.created_at and paper.created_at >= retention_cutoff))
                ):
                    break

                if paper.local_path:
                    try:
                        p = Path(paper.local_path)
                        if p.exists():
                            f_size = p.stat().st_size
                            p.unlink(missing_ok=True)
                            freed_bytes += f_size
                    except Exception as e:
                        logger.warning(f"Error unlinking paper file {paper.local_path}: {e}")

                    # Update paper record: keep metadata intact, clear local file path
                    paper.local_path = None
                    paper.status = "archived"
                    papers_flushed += 1

            if papers_flushed > 0:
                await db.commit()
                logger.info(
                    f"Auto-flush complete: archived {papers_flushed} paper(s), freed {round(freed_bytes / (1024 * 1024), 2)}MB"
                )

    new_usage = get_current_storage_usage()
    return {
        "flushed": should_flush,
        "papers_archived": papers_flushed,
        "freed_bytes": freed_bytes,
        "freed_mb": round(freed_bytes / (1024 * 1024), 2),
        "current_storage_mb": new_usage["total_mb"],
        "temp_files_cleaned": temp_result["deleted_files"],
    }


async def _periodic_flush_worker() -> None:
    """Background task executing automated storage flush periodically."""
    interval_seconds = max(settings.AUTO_FLUSH_INTERVAL_MINUTES, 5) * 60
    logger.info(
        f"Automated storage cleaner active. Interval: {settings.AUTO_FLUSH_INTERVAL_MINUTES}m, Max: {settings.MAX_STORAGE_MB}MB, Retention: {settings.STORAGE_RETENTION_HOURS}h"
    )

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            if settings.AUTO_CLEANUP_ENABLED:
                await flush_storage_if_needed()
        except asyncio.CancelledError:
            logger.info("Storage cleanup background worker stopped.")
            break
        except Exception as e:
            logger.error(f"Error in periodic storage cleanup worker: {e}")
            await asyncio.sleep(60)


def start_storage_cleaner_task() -> Optional[asyncio.Task]:
    """Start background periodic storage flush task."""
    global _cleanup_task
    if _cleanup_task is None or _cleanup_task.done():
        _cleanup_task = asyncio.create_task(_periodic_flush_worker())
    return _cleanup_task


def stop_storage_cleaner_task() -> None:
    """Stop background periodic storage flush task."""
    global _cleanup_task
    if _cleanup_task and not _cleanup_task.done():
        _cleanup_task.cancel()
        _cleanup_task = None
