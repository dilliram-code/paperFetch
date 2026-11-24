"""Paper detection and metadata management endpoints."""
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models import Paper
from backend.app.schemas import (
    DetectBatchResponse,
    DetectRequest,
    PaperDetectionResponse,
    PaperResponse,
    PaperUpdate,
)
from backend.app.services.bibtex_generator import generate_bibtex_entry
from backend.app.services.filename_generator import generate_paper_filename
from backend.app.services.paper_detector import detect_papers_batch

router = APIRouter(prefix="/api/papers", tags=["Papers"])


@router.post("/detect", response_model=DetectBatchResponse)
async def detect_papers(req: DetectRequest, db: AsyncSession = Depends(get_db)):
    """
    Intelligently discover and extract bibliographic metadata for up to 10 URLs/DOIs.
    Checks PDF availability and identifies duplicate records.
    """
    detected_list = await detect_papers_batch(req.inputs, db=db)

    persisted_papers = []
    accessible_count = 0
    duplicate_count = 0

    for item in detected_list:
        paper_id = item["id"]
        # Save detected paper to database so it can be previewed/edited
        paper = Paper(
            id=paper_id,
            title=item.get("title") or "Untitled Paper",
            first_author=item.get("first_author"),
            year=item.get("year"),
            doi=item.get("doi"),
            journal_or_conference=item.get("journal_or_conference"),
            publisher=item.get("publisher"),
            volume=item.get("volume"),
            issue=item.get("issue"),
            pages=item.get("pages"),
            abstract=item.get("abstract"),
            issn=item.get("issn"),
            original_url=item.get("original_url"),
            pdf_url=item.get("pdf_url"),
            access_type=item.get("access_type", "unknown"),
            filename=item.get("filename"),
            bibtex=item.get("bibtex"),
            metadata_source=item.get("metadata_source"),
            status="detected" if item.get("pdf_accessible") else "pdf_unavailable",
        )
        paper.authors = item.get("authors", [])
        db.add(paper)

        if item.get("pdf_accessible"):
            accessible_count += 1
        if item.get("duplicate_info", {}).get("is_duplicate"):
            duplicate_count += 1

        persisted_papers.append(
            PaperDetectionResponse(
                id=paper.id,
                title=paper.title,
                authors=paper.authors,
                first_author=paper.first_author,
                year=paper.year,
                doi=paper.doi,
                journal_or_conference=paper.journal_or_conference,
                publisher=paper.publisher,
                volume=paper.volume,
                issue=paper.issue,
                pages=paper.pages,
                abstract=paper.abstract,
                issn=paper.issn,
                original_url=paper.original_url,
                pdf_url=paper.pdf_url,
                access_type=paper.access_type,
                filename=paper.filename,
                pdf_accessible=item.get("pdf_accessible", False),
                duplicate_info=item.get("duplicate_info"),
                status=paper.status,
                bibtex=paper.bibtex,
                metadata_source=paper.metadata_source,
                error=item.get("error"),
            )
        )

    await db.commit()

    return DetectBatchResponse(
        papers=persisted_papers,
        total=len(persisted_papers),
        accessible_count=accessible_count,
        duplicate_count=duplicate_count,
    )


@router.get("/{paper_id}", response_model=PaperResponse)
async def get_paper(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve detailed metadata for a specific paper."""
    res = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = res.scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return PaperResponse(**paper.to_dict())


@router.patch("/{paper_id}", response_model=PaperResponse)
async def update_paper_metadata(paper_id: str, update_data: PaperUpdate, db: AsyncSession = Depends(get_db)):
    """
    Allow users to manually edit extracted metadata before or after download.
    Automatically regenerates BibTeX and standardized filename.
    """
    res = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = res.scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    fields = update_data.model_dump(exclude_unset=True)
    if "authors" in fields:
        paper.authors = fields.pop("authors")

    for k, v in fields.items():
        setattr(paper, k, v)

    # Regenerate filename and BibTeX with user edits
    paper.filename = generate_paper_filename(
        title=paper.title,
        authors=paper.authors,
        year=paper.year,
        doi=paper.doi,
    )
    paper.bibtex = generate_bibtex_entry(paper.to_dict())
    paper.metadata_source = "manual_edit"

    await db.commit()
    await db.refresh(paper)
    return PaperResponse(**paper.to_dict())


@router.get("/{paper_id}/download")
async def download_paper_pdf(paper_id: str, db: AsyncSession = Depends(get_db)):
    """Serve the local PDF file with standardized academic filename, or redirect to source if flushed."""
    res = await db.execute(select(Paper).where(Paper.id == paper_id))
    paper = res.scalars().first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    if not paper.local_path:
        if paper.pdf_url:
            return RedirectResponse(url=paper.pdf_url)
        raise HTTPException(status_code=404, detail="Paper PDF not found or not yet downloaded")

    pdf_path = Path(paper.local_path)
    if not pdf_path.exists():
        if paper.pdf_url:
            return RedirectResponse(url=paper.pdf_url)
        raise HTTPException(status_code=404, detail="Physical PDF file missing on disk")

    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=paper.filename or pdf_path.name,
    )
