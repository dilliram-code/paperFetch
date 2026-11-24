"""Duplicate research paper detection using DOI, SHA-256, and metadata matching."""
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Paper
from backend.app.services.filename_generator import extract_surname


def compute_file_sha256(file_path: Path) -> str:
    """Calculate SHA-256 hash of a file efficiently using 64KB blocks."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


def normalize_title(title: Optional[str]) -> str:
    """Normalize title for fuzzy/metadata comparison."""
    if not title:
        return ""
    # Lowercase, remove all non-alphanumeric characters, and collapse spaces
    cleaned = re.sub(r"[^a-z0-9]", " ", title.lower())
    return " ".join(cleaned.split())


def titles_are_similar(t1: str, t2: str, threshold: float = 0.85) -> bool:
    """Compare two normalized titles using token Jaccard similarity."""
    s1 = set(normalize_title(t1).split())
    s2 = set(normalize_title(t2).split())
    if not s1 or not s2:
        return False
    intersection = len(s1 & s2)
    union = len(s1 | s2)
    if union == 0:
        return False
    similarity = intersection / union
    return similarity >= threshold


async def check_duplicate_in_db(
    db: AsyncSession,
    doi: Optional[str] = None,
    file_hash: Optional[str] = None,
    title: Optional[str] = None,
    first_author: Optional[str] = None,
    exclude_paper_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[Paper]]:
    """
    Check if a paper is already in the database.
    Returns: (is_duplicate, match_type, existing_paper)
    match_type can be 'doi', 'file_hash', 'title_author'
    """
    # 1. Exact DOI check
    if doi:
        clean_doi = doi.strip().lower()
        stmt = select(Paper).where(Paper.doi == clean_doi)
        if exclude_paper_id:
            stmt = stmt.where(Paper.id != exclude_paper_id)
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return True, "doi", existing

    # 2. Exact file hash check
    if file_hash:
        stmt = select(Paper).where(Paper.file_hash == file_hash)
        if exclude_paper_id:
            stmt = stmt.where(Paper.id != exclude_paper_id)
        res = await db.execute(stmt)
        existing = res.scalars().first()
        if existing:
            return True, "file_hash", existing

    # 3. Metadata matching (Title + First Author)
    if title and len(title.strip()) > 10:
        norm_t = normalize_title(title)
        # Fetch papers with non-empty titles
        stmt = select(Paper).where(Paper.title.isnot(None))
        if exclude_paper_id:
            stmt = stmt.where(Paper.id != exclude_paper_id)
        res = await db.execute(stmt)
        candidates = res.scalars().all()
        for cand in candidates:
            if titles_are_similar(title, cand.title or ""):
                # If author provided, check author similarity too
                if first_author and cand.first_author:
                    s1 = extract_surname(first_author).lower()
                    s2 = extract_surname(cand.first_author).lower()
                    if s1 == s2:
                        return True, "title_author", cand
                else:
                    return True, "title_author", cand

    return False, None, None


def check_batch_duplicates(papers_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Check duplicate relationships within the current submitted batch.
    Updates each paper's duplicate_info dictionary.
    """
    seen_dois: Dict[str, int] = {}
    seen_titles: Dict[str, int] = {}

    for idx, p in enumerate(papers_metadata):
        doi = (p.get("doi") or "").strip().lower()
        title = normalize_title(p.get("title") or "")

        if doi and doi in seen_dois:
            prior_idx = seen_dois[doi]
            p["duplicate_info"] = {
                "is_duplicate": True,
                "match_type": "doi",
                "existing_paper_id": papers_metadata[prior_idx].get("id"),
                "existing_title": papers_metadata[prior_idx].get("title"),
                "message": f"Duplicate DOI in this batch (matches item #{prior_idx + 1}).",
            }
            continue
        elif doi:
            seen_dois[doi] = idx

        if title and len(title) > 10:
            found_prior = False
            for prev_title, prev_idx in seen_titles.items():
                if titles_are_similar(title, prev_title):
                    p["duplicate_info"] = {
                        "is_duplicate": True,
                        "match_type": "title_author",
                        "existing_paper_id": papers_metadata[prev_idx].get("id"),
                        "existing_title": papers_metadata[prev_idx].get("title"),
                        "message": f"Similar title to item #{prev_idx + 1} in this batch.",
                    }
                    found_prior = True
                    break
            if not found_prior:
                seen_titles[title] = idx

    return papers_metadata
