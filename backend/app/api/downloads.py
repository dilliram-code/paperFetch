"""Download job orchestration, SSE progress streaming, and ZIP bundling."""
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import DownloadJob, Paper
from backend.app.schemas import DownloadJobsCreateRequest, JobResponse
from backend.app.services.job_manager import job_manager
from backend.app.services.zip_service import create_papers_zip

router = APIRouter(tags=["Downloads"])


@router.post("/api/jobs", response_model=List[JobResponse])
async def create_download_jobs(
    req: DownloadJobsCreateRequest, db: AsyncSession = Depends(get_db)
):
    """Confirm metadata preview and schedule downloads for up to 10 papers."""
    if not req.paper_ids:
        raise HTTPException(status_code=400, detail="No paper IDs provided")

    jobs = await job_manager.create_download_jobs(
        paper_ids=req.paper_ids, db=db, force_download=req.force_download
    )
    return [JobResponse(**j) for j in jobs]


@router.get("/api/jobs", response_model=List[JobResponse])
async def list_jobs(db: AsyncSession = Depends(get_db)):
    """Retrieve list of active and recently created download jobs."""
    res = await db.execute(
        select(DownloadJob).order_by(desc(DownloadJob.started_at)).limit(50)
    )
    jobs = res.scalars().all()
    return [JobResponse(**j.to_dict()) for j in jobs]


@router.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve individual download job details."""
    res = await db.execute(select(DownloadJob).where(DownloadJob.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**job.to_dict())


@router.get("/api/jobs/{job_id}/progress")
async def stream_job_progress(job_id: str):
    """Server-Sent Events (SSE) stream for live single-job download progress."""
    async def event_generator():
        async for data in job_manager.subscribe(job_id=job_id):
            yield {"event": "progress", "data": data}

    return EventSourceResponse(event_generator())


@router.get("/api/jobs/stream/all")
async def stream_all_jobs_progress():
    """Server-Sent Events (SSE) stream for all concurrent download jobs."""
    async def event_generator():
        async for data in job_manager.subscribe(job_id=None):
            yield {"event": "progress", "data": data}

    return EventSourceResponse(event_generator())


@router.post("/api/jobs/{job_id}/retry")
async def retry_failed_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Retry a failed or cancelled download job."""
    res = await db.execute(select(DownloadJob).where(DownloadJob.id == job_id))
    job = res.scalars().first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    new_jobs = await job_manager.create_download_jobs(
        paper_ids=[job.paper_id], db=db, force_download=True
    )
    if not new_jobs:
        raise HTTPException(status_code=500, detail="Could not restart download")
    return JobResponse(**new_jobs[0])


@router.delete("/api/jobs/{job_id}")
async def cancel_job(job_id: str):
    """Cancel an active download job in real time."""
    cancelled = job_manager.cancel_job(job_id)
    return {"cancelled": cancelled, "job_id": job_id}


@router.delete("/api/jobs")
async def cancel_all_jobs():
    """Cancel all running download jobs."""
    count = job_manager.cancel_all_jobs()
    return {"cancelled_count": count}


@router.get("/api/downloads/zip")
async def download_papers_zip(
    background_tasks: BackgroundTasks,
    paper_ids: Optional[List[str]] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Download specified papers (or all completed papers) as a single ZIP archive.
    Cleans up temporary ZIP file automatically in background after sending.
    """
    stmt = select(Paper).where(Paper.status == "completed")
    if paper_ids:
        stmt = stmt.where(Paper.id.in_(paper_ids))

    res = await db.execute(stmt)
    papers = list(res.scalars().all())

    if not papers:
        raise HTTPException(status_code=404, detail="No completed papers found to archive")

    zip_file = create_papers_zip(papers)
    if not zip_file or not zip_file.exists():
        raise HTTPException(status_code=500, detail="Failed to create ZIP archive")

    # Schedule temporary ZIP deletion after response is transmitted
    def cleanup_file(path_to_clean: Path):
        try:
            if path_to_clean.exists():
                path_to_clean.unlink()
        except Exception:
            pass

    background_tasks.add_task(cleanup_file, zip_file)

    return FileResponse(
        path=zip_file,
        media_type="application/zip",
        filename="PaperFetch_Batch.zip",
    )
