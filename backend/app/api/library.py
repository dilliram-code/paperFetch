"""Library, dashboard metrics, and download history endpoints."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import DownloadJob, Paper
from backend.app.schemas import JobResponse, PaperResponse
from backend.app.services.library_manager import (
    delete_paper_from_library,
    get_dashboard_statistics,
    get_library_papers,
)

router = APIRouter(tags=["Library"])


@router.get("/api/library")
async def list_library_papers(
    q: Optional[str] = Query(None, description="Search across title, author, DOI, journal"),
    year: Optional[int] = Query(None, description="Filter by year"),
    journal: Optional[str] = Query(None, description="Filter by journal"),
    status: Optional[str] = Query(None, description="Filter by status (e.g. completed)"),
    sort_by: str = Query("created_at", regex="^(created_at|year|title)$"),
    order: str = Query("desc", regex="^(asc|desc)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Search and browse all research papers in the library."""
    papers, total_count = await get_library_papers(
        db=db,
        query=q,
        year=year,
        journal=journal,
        status=status,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return {
        "items": [PaperResponse(**p.to_dict()) for p in papers],
        "total": total_count,
        "limit": limit,
        "offset": offset,
    }


@router.delete("/api/library/{paper_id}")
async def remove_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a research paper record and its local PDF file."""
    deleted = await delete_paper_from_library(db, paper_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Paper not found in library")
    return {"message": "Paper and file deleted successfully", "id": paper_id}


@router.get("/api/history")
async def get_download_history(
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full chronological download history."""
    stmt = (
        select(DownloadJob, Paper)
        .outerjoin(Paper, DownloadJob.paper_id == Paper.id)
        .order_by(desc(DownloadJob.started_at))
        .limit(limit)
    )
    res = await db.execute(stmt)
    records = []
    for job, paper in res.all():
        job_data = job.to_dict()
        if paper:
            job_data["paper"] = paper.to_dict()
        records.append(job_data)

    return {"history": records}


@router.get("/api/dashboard/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Retrieve overview metrics for the main dashboard."""
    stats = await get_dashboard_statistics(db)
    return stats
