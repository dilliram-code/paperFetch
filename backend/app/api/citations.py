"""BibTeX citation generation and batch export endpoints."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Paper
from backend.app.schemas import BibtexExportRequest
from backend.app.services.bibtex_generator import combine_bibtex_entries, generate_bibtex_entry

router = APIRouter(prefix="/api/citations", tags=["Citations"])


@router.get("/paper/{paper_id}")
async def get_single_bibtex(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve BibTeX citation for a single paper."""
    res = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = res.scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    bibtex = paper.bibtex or generate_bibtex_entry(paper.to_dict())
    return Response(content=bibtex, media_type="text/plain; charset=utf-8")


@router.post("/export")
async def export_selected_bibtex(req: BibtexExportRequest, db: AsyncSession = Depends(get_db)):
    """Export selected papers as a combined .bib file."""
    if not req.paper_ids:
        raise HTTPException(status_code=400, detail="No paper IDs selected")

    res = await db.execute(select(Paper).where(Paper.id.in_(req.paper_ids)))
    papers = res.scalars().all()

    entries = []
    for p in papers:
        entry = p.bibtex or generate_bibtex_entry(p.to_dict())
        if entry:
            entries.append(entry)

    combined = combine_bibtex_entries(entries)
    return Response(
        content=combined,
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="citations.bib"'},
    )


@router.get("/export/all")
async def export_all_bibtex(db: AsyncSession = Depends(get_db)):
    """Export all papers in library as a single .bib file."""
    res = await db.execute(select(Paper))
    papers = res.scalars().all()

    entries = [p.bibtex or generate_bibtex_entry(p.to_dict()) for p in papers if p.title]
    combined = combine_bibtex_entries(entries)
    return Response(
        content=combined,
        media_type="application/x-bibtex; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="paperfetch_library.bib"'},
    )
