"""Automatic standardized academic PDF filename generator."""
import re
from pathlib import Path
from typing import List, Optional
from backend.app.utils.security import sanitize_filename


def extract_surname(author_name: str) -> str:
    """Extract clean surname from an author name string."""
    if not author_name:
        return "Unknown"
    cleaned = author_name.strip()
    # Check "Lastname, Firstname" format
    if "," in cleaned:
        surname = cleaned.split(",")[0].strip()
    else:
        # "Firstname Lastname" format
        parts = cleaned.split()
        surname = parts[-1] if parts else "Unknown"
    # Remove initials, dots, and illegal characters
    surname = re.sub(r"[^A-Za-z0-9\-]", "", surname)
    return surname if surname else "Unknown"


def clean_title_slug(title: str, max_words: int = 6) -> str:
    """Create a concise, clean slug from paper title."""
    if not title:
        return "Untitled_Paper"
    # Remove common punctuation
    cleaned = re.sub(r"[^\w\s\-]", "", title)
    words = cleaned.split()
    if not words:
        return "Untitled_Paper"
    slug_words = words[:max_words]
    # Capitalize for standard Camel/Pascal-like readability
    slug = "_".join(w.capitalize() for w in slug_words)
    # Truncate if excessively long
    if len(slug) > 60:
        slug = slug[:60].rstrip("_")
    return slug


def generate_paper_filename(
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    year: Optional[int] = None,
    doi: Optional[str] = None,
    destination_dir: Optional[Path] = None,
) -> str:
    """
    Generate standard filename: Year_FirstAuthor_ShortTitle.pdf
    Ensures uniqueness if destination_dir is provided.
    """
    # 1. Year part
    year_part = str(year) if year and 1800 <= year <= 2100 else "UnknownYear"

    # 2. First author part
    first_author_str = "Unknown"
    if authors and len(authors) > 0 and authors[0]:
        first_author_str = extract_surname(authors[0])

    # 3. Title slug
    title_slug = clean_title_slug(title or "")
    if title_slug == "Untitled_Paper" and doi:
        # Use sanitized DOI part as fallback
        doi_suffix = doi.split("/")[-1] if "/" in doi else doi
        title_slug = re.sub(r"[^\w\-]", "_", doi_suffix)

    candidate = f"{year_part}_{first_author_str}_{title_slug}.pdf"
    clean_name = sanitize_filename(candidate)

    # 4. Handle duplicates if target folder provided
    if destination_dir and destination_dir.exists():
        target = destination_dir / clean_name
        counter = 1
        stem = clean_name[:-4]  # remove .pdf
        while target.exists():
            clean_name = f"{stem}_{counter}.pdf"
            target = destination_dir / clean_name
            counter += 1

    return clean_name
