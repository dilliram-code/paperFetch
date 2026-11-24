"""DOI resolution engine aggregating Crossref, OpenAlex, and Unpaywall."""
import logging
from typing import Any, Dict, Optional

from backend.app.services.academic_sources import (
    fetch_crossref_metadata,
    fetch_openalex_metadata,
    fetch_unpaywall_metadata,
)

logger = logging.getLogger(__name__)


async def resolve_doi(doi: str) -> Optional[Dict[str, Any]]:
    """
    Resolve DOI by combining Crossref, OpenAlex, and Unpaywall.
    Ensures high-fidelity metadata and finds open access PDF if available.
    """
    clean_doi = doi.strip().lower()

    # 1. Start with Crossref (gold standard for bibliographic data)
    crossref_data = await fetch_crossref_metadata(clean_doi)
    
    # 2. Query OpenAlex (excellent for open-access links and venues)
    openalex_data = await fetch_openalex_metadata(clean_doi)

    # 3. Query Unpaywall (best for finding direct legal OA PDFs)
    unpaywall_data = await fetch_unpaywall_metadata(clean_doi)

    if not crossref_data and not openalex_data and not unpaywall_data:
        return None

    # Base record from Crossref or OpenAlex or Unpaywall
    base = crossref_data or openalex_data or unpaywall_data or {}
    record = dict(base)

    # Enrich authors if missing
    if not record.get("authors"):
        for source in (openalex_data, unpaywall_data):
            if source and source.get("authors"):
                record["authors"] = source["authors"]
                record["first_author"] = source.get("first_author")
                break

    # Enrich year if missing
    if not record.get("year"):
        for source in (openalex_data, unpaywall_data):
            if source and source.get("year"):
                record["year"] = source["year"]
                break

    # Enrich journal if missing
    if not record.get("journal_or_conference"):
        for source in (openalex_data, unpaywall_data):
            if source and source.get("journal_or_conference"):
                record["journal_or_conference"] = source["journal_or_conference"]
                break

    # Enrich PDF URL (prioritizing Unpaywall -> OpenAlex -> Crossref)
    pdf_url = None
    if unpaywall_data and unpaywall_data.get("pdf_url"):
        pdf_url = unpaywall_data["pdf_url"]
        record["access_type"] = "open_access"
    elif openalex_data and openalex_data.get("pdf_url"):
        pdf_url = openalex_data["pdf_url"]
        record["access_type"] = "open_access"
    elif crossref_data and crossref_data.get("pdf_url"):
        pdf_url = crossref_data["pdf_url"]

    if pdf_url:
        record["pdf_url"] = pdf_url

    return record
