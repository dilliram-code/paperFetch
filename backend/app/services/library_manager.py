"""Library management service for searching, filtering, and organizing research papers."""
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import DownloadJob, Paper


async def get_library_papers(
    db: AsyncSession,
    query: Optional[str] = None,
    year: Optional[int] = None,
    journal: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> Tuple[List[Paper], int]:
    """
    Query library papers with full-text search, filters, sorting, and pagination.
    Returns: (papers_list, total_matching_count)
    """
    stmt = select(Paper)

    # Search filter across title, authors_json, doi, journal_or_conference
    if query and query.strip():
        term = f"%{query.strip()}%"
        stmt = stmt.where(
            or_(
                Paper.title.ilike(term),
                Paper.authors_json.ilike(term),
                Paper.doi.ilike(term),
                Paper.journal_or_conference.ilike(term),
            )
        )

    if year:
        stmt = stmt.where(Paper.year == year)

    if journal and journal.strip():
        stmt = stmt.where(Paper.journal_or_conference.ilike(f"%{journal.strip()}%"))

    if status and status.strip():
        stmt = stmt.where(Paper.status == status.strip())

    # Total count query
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count = (await db.execute(count_stmt)).scalar() or 0

    # Sorting
    sort_column = Paper.created_at
    if sort_by == "year":
        sort_column = Paper.year
    elif sort_by == "title":
        sort_column = Paper.title

    if order.lower() == "asc":
        stmt = stmt.order_by(sort_column.asc())
    else:
        stmt = stmt.order_by(sort_column.desc())

    stmt = stmt.limit(limit).offset(offset)
    res = await db.execute(stmt)
    papers = list(res.scalars().all())

    return papers, total_count


async def delete_paper_from_library(db: AsyncSession, paper_id: str) -> bool:
    """
    Delete a paper record and its physical PDF file from storage.
    """
    res = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = res.scalars().first()
    if not paper:
        return False

    # Remove physical file if present
    if paper.local_path:
        file_path = Path(paper.local_path)
        if file_path.exists():
            try:
                file_path.unlink()
            except Exception:
                pass

    await db.delete(paper)
    await db.commit()
    return True


async def get_dashboard_statistics(db: AsyncSession) -> Dict[str, Any]:
    """Calculate dashboard metrics and recent activity."""
    # Total papers in library
    total_papers = (await db.execute(select(func.count(Paper.id)))).scalar() or 0

    # Successful downloads
    completed_downloads = (
        await db.execute(select(func.count(Paper.id)).where(Paper.status == "completed"))
    ).scalar() or 0

    # Failed downloads
    failed_downloads = (
        await db.execute(select(func.count(Paper.id)).where(Paper.status == "failed"))
    ).scalar() or 0

    # Total storage used
    storage_bytes = (
        await db.execute(select(func.sum(Paper.file_size_bytes)).where(Paper.status == "completed"))
    ).scalar() or 0

    # Recent downloads (last 5 completed or attempted)
    recent_stmt = (
        select(Paper)
        .order_by(desc(Paper.created_at))
        .limit(5)
    )
    recent_res = await db.execute(recent_stmt)
    recent_papers = [p.to_dict() for p in recent_res.scalars().all()]

    return {
        "total_papers": total_papers,
        "completed_downloads": completed_downloads,
        "failed_downloads": failed_downloads,
        "storage_used_bytes": storage_bytes,
        "storage_used_mb": round(storage_bytes / (1024 * 1024), 2),
        "recent_papers": recent_papers,
    }
