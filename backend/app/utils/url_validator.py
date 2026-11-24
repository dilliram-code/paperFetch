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
    """Extract arXiv ID from URL, DOI, or raw identifier."""
    if not input_str:
        return None
    cleaned = input_str.strip()

    # Handle various arXiv URL patterns and DOI prefixes
    for prefix in [
        "arxiv.org/abs/",
        "arxiv.org/pdf/",
        "arxiv.org/html/",
        "arxiv.org/format/",
        "10.48550/arxiv.",
        "10.48550/arXiv.",
    ]:
        if prefix.lower() in cleaned.lower():
            idx = cleaned.lower().find(prefix.lower())
            cleaned = cleaned[idx + len(prefix):]
            break

    cleaned = cleaned.replace(".pdf", "")
    if "?" in cleaned:
        cleaned = cleaned.split("?")[0]
    cleaned = cleaned.rstrip("/")
    
    match = ARXIV_ID_REGEX.search(cleaned)
    if match:
        return match.group(1)
    return None


def extract_title_from_url(url: str) -> Optional[str]:
    """
    Extract a potential paper title from an academic URL slug (e.g. ResearchGate, Academia).
    Handles direct publication pages as well as deep links ending in /download, /link, /pdf, etc.
    Example:
      https://www.researchgate.net/publication/319164243_Natural_language_processing_state_of_the_art_current_trends_and_challenges/link/5ac0c514aca27222c75a72ad/download
      -> 'Natural language processing state of the art current trends and challenges'
    """
    if not url:
        return None
    try:
        from urllib.parse import unquote
        parsed = urlparse(url)
        path = unquote(parsed.path).strip("/")
        parts = [p for p in path.split("/") if p]
        if not parts:
            return None

        # Common non-title path segments in academic URLs to ignore
        skip_words = {
            "download", "link", "fulltext", "pdf", "file", "content",
            "view", "assets", "publication", "publications", "article",
            "articles", "paper", "papers", "document", "documents", "epdf"
        }

        # Inspect segments in reverse order (closest content slug first)
        for part in reversed(parts):
            if part.lower() in skip_words:
                continue
            # Skip hexadecimal hashes (e.g. 5ac0c514aca27222c75a72ad)
            if re.match(r"^[0-9a-f]{16,64}$", part, re.I):
                continue
            # Remove leading ID numbers like 319164243_ or 12345-
            cleaned_part = re.sub(r"^\d+[\-_]", "", part)
            # Remove common web/file extensions
            cleaned_part = re.sub(r"\.(html|htm|php|asp|aspx|pdf)$", "", cleaned_part, flags=re.I)
            # Convert separators to spaces
            candidate = re.sub(r"[\-_+]+", " ", cleaned_part).strip()
            # Only return if it resembles a multi-word paper title (at least 2 words and >= 12 chars)
            if len(candidate) >= 12 and " " in candidate:
                return candidate

        return None
    except Exception:
        return None


def classify_input(input_str: str) -> Tuple[str, str]:
    """
    Classify input as 'doi', 'arxiv', 'direct_pdf', or 'webpage'.
    Returns (classification, normalized_value).
    """
    cleaned = input_str.strip()

    # Check arXiv first if it's explicitly an arXiv URL, DOI, or identifier
    arxiv_id = extract_arxiv_id(cleaned)
    if arxiv_id and (
        "arxiv.org" in cleaned.lower()
        or "10.48550/arxiv" in cleaned.lower()
        or cleaned.lower().startswith("arxiv:")
        or re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", cleaned)
    ):
        return "arxiv", arxiv_id

    # Check DOI
    doi = extract_doi(cleaned)
    if doi and (not cleaned.startswith("http") or "doi.org" in cleaned):
        return "doi", doi

    # Check if valid URL
    if not cleaned.startswith(("http://", "https://")):
        if doi:
            return "doi", doi
        if arxiv_id:
            return "arxiv", arxiv_id
        cleaned = "https://" + cleaned

    parsed = urlparse(cleaned)
    path = parsed.path.lower()

    if path.endswith(".pdf") or "pdf" in parsed.query.lower():
        return "direct_pdf", cleaned

    if doi:
        return "doi", doi

    return "webpage", cleaned
