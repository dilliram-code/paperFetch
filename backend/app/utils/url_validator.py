"""URL and DOI validation, normalization, and classification utilities."""
import re
from typing import Optional, Tuple
from urllib.parse import urlparse

# Standard DOI pattern matching 10.xxxx/...
DOI_REGEX = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)\b", re.IGNORECASE)

# arXiv identifier pattern (e.g. 2301.12345 or math.PR/0501234)
ARXIV_ID_REGEX = re.compile(
    r"(?:arxiv:)?((?:\d{4}\.\d{4,5}(?:v\d+)?)|(?:[a-z\-]+(?:\.[A-Z]{2})?/\d{7}))",
    re.IGNORECASE,
)


def extract_doi(input_str: str) -> Optional[str]:
    """Extract and normalize DOI from a raw string, DOI URL, or text."""
    if not input_str:
        return None
    cleaned = input_str.strip()
    # Check for doi.org URL format
    if "doi.org/" in cleaned:
        cleaned = cleaned.split("doi.org/")[-1].strip()
    elif "dx.doi.org/" in cleaned:
        cleaned = cleaned.split("dx.doi.org/")[-1].strip()
    elif cleaned.lower().startswith("doi:"):
        cleaned = cleaned[4:].strip()

    match = DOI_REGEX.search(cleaned)
    if match:
        doi = match.group(1).rstrip(".")
        return doi.lower()
    return None


def extract_arxiv_id(input_str: str) -> Optional[str]:
    """Extract arXiv ID from URL or raw identifier."""
    if not input_str:
        return None
    cleaned = input_str.strip()
    if "arxiv.org/abs/" in cleaned:
        cleaned = cleaned.split("arxiv.org/abs/")[-1]
    elif "arxiv.org/pdf/" in cleaned:
        cleaned = cleaned.split("arxiv.org/pdf/")[-1].replace(".pdf", "")
    
    match = ARXIV_ID_REGEX.search(cleaned)
    if match:
        return match.group(1)
    return None


def classify_input(input_str: str) -> Tuple[str, str]:
    """
    Classify input as 'doi', 'arxiv', 'direct_pdf', or 'webpage'.
    Returns (classification, normalized_value).
    """
    cleaned = input_str.strip()

    # Check DOI first
    doi = extract_doi(cleaned)
    if doi and (not cleaned.startswith("http") or "doi.org" in cleaned):
        return "doi", doi

    # Check arXiv
    arxiv_id = extract_arxiv_id(cleaned)
    if arxiv_id and ("arxiv.org" in cleaned or cleaned.lower().startswith("arxiv:")):
        return "arxiv", arxiv_id

    # Check if valid URL
    if not cleaned.startswith(("http://", "https://")):
        # If it matches DOI pattern without scheme
        if doi:
            return "doi", doi
        cleaned = "https://" + cleaned

    parsed = urlparse(cleaned)
    path = parsed.path.lower()

    if path.endswith(".pdf") or "pdf" in parsed.query.lower():
        return "direct_pdf", cleaned

    if doi:
        return "doi", doi

    return "webpage", cleaned
