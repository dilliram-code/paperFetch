"""PDF file validation, magic byte checking, and metadata inspection."""
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
import fitz  # PyMuPDF

from backend.app.utils.url_validator import DOI_REGEX


def is_valid_pdf_bytes(first_bytes: bytes) -> bool:
    """Check if bytes contain standard PDF magic signature '%PDF-' anywhere in first 4KB."""
    return b"%PDF-" in first_bytes[:4096]


def validate_pdf_file(file_path: Path) -> Tuple[bool, Optional[str], int, Dict[str, Any]]:
    """
    Validate a local PDF file using PyMuPDF.
    Returns:
        (is_valid, error_message, page_count, metadata_dict)
    """
    if not file_path.exists() or file_path.stat().st_size == 0:
        return False, "File is empty or does not exist", 0, {}

    try:
        with open(file_path, "rb") as f:
            header = f.read(4096)

        header_lower = header[:1024].lower().strip()
        # Explicitly detect HTML landing or error pages
        if (
            header_lower.startswith((b"<!doctype html", b"<html", b"<?xml", b"<head", b"<body"))
            or (b"<html" in header_lower and b"%PDF-" not in header)
        ):
            return (
                False,
                "Downloaded file is an HTML webpage rather than a PDF (the publisher page may be paywalled or require institutional access)",
                0,
                {},
            )

        # PyMuPDF verification
        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            if not is_valid_pdf_bytes(header):
                return False, "Invalid PDF header signature (not a valid PDF)", 0, {}
            return False, f"Corrupted or invalid PDF: {str(e)}", 0, {}

        page_count = len(doc)
        if page_count == 0:
            doc.close()
            return False, "PDF has 0 pages", 0, {}

        # Safely extract document metadata
        meta = doc.metadata or {}
        extracted_info = {
            "title": meta.get("title") or None,
            "author": meta.get("author") or None,
            "subject": meta.get("subject") or None,
            "creator": meta.get("creator") or None,
            "creation_date": meta.get("creationDate") or None,
        }

        # If title or author is missing or generic, inspect first page text
        if (not extracted_info["title"] or "untitled" in str(extracted_info["title"]).lower()) and page_count > 0:
            first_page = doc[0]
            text = first_page.get_text("text")[:3000]
            lines = [l.strip() for l in text.split("\n") if l.strip()]
            if lines:
                # Heuristic: the first prominent non-header line is often the title
                for candidate in lines[:5]:
                    if len(candidate) > 10 and not candidate.lower().startswith(("http", "doi", "issn", "volume", "arxiv")):
                        extracted_info["text_title"] = candidate
                        break
            # Look for DOI on first page
            doi_match = DOI_REGEX.search(text)
            if doi_match:
                extracted_info["doi"] = doi_match.group(1).rstrip(".")

        doc.close()
        return True, None, page_count, extracted_info

    except Exception as e:
        return False, f"Corrupted or invalid PDF: {str(e)}", 0, {}
