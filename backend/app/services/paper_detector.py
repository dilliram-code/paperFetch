"""High-level Paper Detection service handling URLs, DOIs, arXiv, and direct PDFs."""
import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.models import Paper
from backend.app.services.academic_sources import fetch_arxiv_metadata
from backend.app.services.bibtex_generator import generate_bibtex_entry
from backend.app.services.doi_resolver import resolve_doi
from backend.app.services.duplicate_detector import (
    check_batch_duplicates,
    check_duplicate_in_db,
)
from backend.app.services.filename_generator import generate_paper_filename
from backend.app.services.metadata_extractor import USER_AGENT, extract_from_webpage
from backend.app.utils.security import validate_target_url
from backend.app.utils.url_validator import (
    classify_input,
    extract_arxiv_id,
    extract_doi,
    extract_title_from_url,
)

logger = logging.getLogger(__name__)


async def check_pdf_accessibility(pdf_url: Optional[str]) -> bool:
    """Check whether a PDF URL is publicly accessible without full download."""
    if not pdf_url:
        return False

    # arXiv PDFs are guaranteed to be publicly accessible
    if "arxiv.org/pdf/" in pdf_url.lower():
        return True

    try:
        validate_target_url(pdf_url)
        headers = {
            "User-Agent": USER_AGENT,
            "Range": "bytes=0-1023",
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0), follow_redirects=True) as client:
            # Try fast HEAD first (short 1.5s timeout)
            try:
                head_resp = await client.head(pdf_url, headers=headers, timeout=1.5)
                if head_resp.status_code in (200, 206):
                    ct = head_resp.headers.get("content-type", "").lower()
                    if "pdf" in ct or "octet-stream" in ct or pdf_url.lower().endswith(".pdf"):
                        return True
            except Exception:
                pass

            # Fast GET with Range request
            get_resp = await client.get(pdf_url, headers=headers, timeout=4.0)
            if get_resp.status_code in (200, 206):
                # Verify magic bytes or content type
                if get_resp.content.startswith(b"%PDF-") or b"%PDF-" in get_resp.content[:1024]:
                    return True
                ct = get_resp.headers.get("content-type", "").lower()
                if "pdf" in ct:
                    return True
        return False
    except Exception as e:
        logger.debug(f"PDF accessibility check failed for {pdf_url}: {e}")
        return False


async def detect_single_paper(raw_input: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """
    Process a single input string (URL, DOI, arXiv) and extract metadata and PDF status.
    """
    input_type, target = classify_input(raw_input)
    paper_data: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": "Untitled Paper",
        "authors": [],
        "first_author": None,
        "year": None,
        "doi": None,
        "journal_or_conference": None,
        "publisher": None,
        "volume": None,
        "issue": None,
        "pages": None,
        "abstract": None,
        "issn": None,
        "original_url": target if target.startswith("http") else f"https://doi.org/{target}",
        "pdf_url": None,
        "access_type": "unknown",
        "metadata_source": "detection",
        "pdf_accessible": False,
        "duplicate_info": {"is_duplicate": False},
        "status": "detected",
    }

    try:
        if input_type == "arxiv":
            arxiv_meta = await fetch_arxiv_metadata(target)
            if arxiv_meta:
                paper_data.update(arxiv_meta)

        elif input_type == "doi":
            doi_meta = await resolve_doi(target)
            if doi_meta:
                paper_data.update(doi_meta)
            else:
                paper_data["doi"] = target

        elif input_type == "direct_pdf":
            validate_target_url(target)
            paper_data["pdf_url"] = target
            paper_data["title"] = target.split("/")[-1].replace(".pdf", "").replace("_", " ").title()
            paper_data["metadata_source"] = "direct_pdf"

        elif input_type == "webpage":
            web_meta = await extract_from_webpage(target)
            if web_meta:
                if web_meta.get("is_direct_pdf"):
                    paper_data["pdf_url"] = web_meta["pdf_url"]
                    paper_data["metadata_source"] = "direct_pdf"
                else:
                    paper_data.update({k: v for k, v in web_meta.items() if v is not None})
                    # If DOI was found in HTML meta tags, enrich with academic APIs
                    if paper_data.get("doi"):
                        api_meta = await resolve_doi(paper_data["doi"])
                        if api_meta:
                            # Enrich missing fields without overwriting explicit webpage values
                            for k, v in api_meta.items():
                                if not paper_data.get(k) and v:
                                    paper_data[k] = v

            # Intelligent academic fallback if scraping was blocked (e.g. ResearchGate/Academia 403) or PDF was not found
            if not paper_data.get("pdf_url") or not paper_data.get("title") or paper_data.get("title") == "Untitled Paper":
                from backend.app.services.academic_sources import search_paper_by_title
                candidate_title = None
                if paper_data.get("title") and paper_data.get("title") != "Untitled Paper":
                    candidate_title = paper_data.get("title")
                else:
                    candidate_title = extract_title_from_url(target)

                if candidate_title:
                    searched_meta = await search_paper_by_title(candidate_title)
                    if searched_meta:
                        orig = paper_data.get("original_url") or target
                        for k, v in searched_meta.items():
                            if v and (not paper_data.get(k) or k in ("pdf_url", "doi", "title", "authors", "year", "journal_or_conference", "publisher", "access_type")):
                                paper_data[k] = v
                        paper_data["original_url"] = orig

    except Exception as e:
        logger.error(f"Detection failed for input '{raw_input}': {e}")
        paper_data["error"] = str(e)
        paper_data["status"] = "failed"

    # Verify PDF accessibility
    if paper_data.get("pdf_url"):
        paper_data["pdf_accessible"] = await check_pdf_accessibility(paper_data["pdf_url"])
        if paper_data["pdf_accessible"]:
            paper_data["access_type"] = "open_access"
        else:
            logger.info(f"Primary PDF URL is inaccessible ({paper_data['pdf_url']}); searching for open-access mirror...")

    # If PDF is inaccessible or missing, find legitimate open-access mirror via DOI or title
    if not paper_data.get("pdf_accessible") or not paper_data.get("pdf_url"):
        from backend.app.services.academic_sources import search_paper_by_title
        from backend.app.services.doi_resolver import resolve_doi

        alt_meta = None
        if paper_data.get("doi"):
            alt_meta = await resolve_doi(paper_data["doi"])

        if not alt_meta or not alt_meta.get("pdf_url"):
            candidate_title = paper_data.get("title")
            if not candidate_title or candidate_title == "Untitled Paper":
                candidate_title = extract_title_from_url(raw_input)
            if candidate_title and candidate_title != "Untitled Paper":
                alt_meta = await search_paper_by_title(candidate_title)

        if alt_meta and alt_meta.get("pdf_url"):
            if await check_pdf_accessibility(alt_meta["pdf_url"]):
                logger.info(f"Resolved accessible open-access PDF: {alt_meta['pdf_url']}")
                paper_data["pdf_url"] = alt_meta["pdf_url"]
                paper_data["pdf_accessible"] = True
                paper_data["access_type"] = "open_access"
                for k in ("title", "authors", "first_author", "year", "doi", "journal_or_conference", "publisher"):
                    if alt_meta.get(k) and (not paper_data.get(k) or paper_data.get(k) == "Untitled Paper"):
                        paper_data[k] = alt_meta[k]

    # Generate standard filename
    paper_data["filename"] = generate_paper_filename(
        title=paper_data.get("title"),
        authors=paper_data.get("authors"),
        year=paper_data.get("year"),
        doi=paper_data.get("doi"),
    )

    # Generate initial BibTeX citation
    paper_data["bibtex"] = generate_bibtex_entry(paper_data)

    # Check for duplicate in database if session provided
    if db:
        is_dup, match_type, existing = await check_duplicate_in_db(
            db=db,
            doi=paper_data.get("doi"),
            title=paper_data.get("title"),
            first_author=paper_data.get("first_author"),
        )
        if is_dup and existing:
            paper_data["duplicate_info"] = {
                "is_duplicate": True,
                "match_type": match_type,
                "existing_paper_id": existing.id,
                "existing_title": existing.title,
                "message": f"Matches existing library paper ({match_type}).",
            }

    return paper_data


async def detect_papers_batch(
    inputs: List[str], db: Optional[AsyncSession] = None
) -> List[Dict[str, Any]]:
    """Detect up to 10 papers concurrently with duplicate checking."""
    limited_inputs = inputs[: settings.MAX_BATCH_SIZE]
    tasks = [detect_single_paper(raw_input, db) for raw_input in limited_inputs]
    results = await asyncio.gather(*tasks)

    # Run inter-batch duplicate checks
    results_list = list(results)
    check_batch_duplicates(results_list)

    return results_list
