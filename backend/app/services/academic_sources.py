"""Academic metadata APIs: Crossref, OpenAlex, Unpaywall, arXiv, and Semantic Scholar."""
import logging
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import httpx

from backend.app.config import settings
from backend.app.utils.security import validate_target_url

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": f"PaperFetch/{settings.VERSION} (mailto:{settings.CROSSREF_MAILTO})",
    "Accept": "application/json",
}


async def fetch_arxiv_metadata(arxiv_id: str) -> Optional[Dict[str, Any]]:
    """Query the official arXiv API for paper metadata."""
    clean_id = arxiv_id.strip()
    api_url = f"https://export.arxiv.org/api/query?id_list={clean_id}"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(api_url, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]})
            if resp.status_code != 200:
                return None

            root = ET.fromstring(resp.text)
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "arxiv": "http://arxiv.org/schemas/atom",
            }
            entry = root.find("atom:entry", ns)
            if entry is None:
                return None

            title_elem = entry.find("atom:title", ns)
            title = title_elem.text.strip().replace("\n", " ") if title_elem is not None and title_elem.text else "Untitled"

            summary_elem = entry.find("atom:summary", ns)
            abstract = summary_elem.text.strip() if summary_elem is not None and summary_elem.text else None

            published_elem = entry.find("atom:published", ns)
            year = int(published_elem.text[:4]) if published_elem is not None and published_elem.text else None

            authors = []
            for author_node in entry.findall("atom:author", ns):
                name_node = author_node.find("atom:name", ns)
                if name_node is not None and name_node.text:
                    authors.append(name_node.text.strip())

            doi_elem = entry.find("arxiv:doi", ns)
            doi = doi_elem.text.strip() if doi_elem is not None and doi_elem.text else None

            journal_elem = entry.find("arxiv:journal_ref", ns)
            journal = journal_elem.text.strip() if journal_elem is not None and journal_elem.text else "arXiv Preprint"

            # Direct PDF url for arXiv
            pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

            return {
                "title": title,
                "authors": authors,
                "first_author": authors[0] if authors else None,
                "year": year,
                "doi": doi or f"10.48550/arXiv.{clean_id}",
                "journal_or_conference": journal,
                "publisher": "arXiv",
                "abstract": abstract,
                "original_url": f"https://arxiv.org/abs/{clean_id}",
                "pdf_url": pdf_url,
                "access_type": "open_access",
                "metadata_source": "arxiv",
            }
    except Exception as e:
        logger.warning(f"Error fetching arXiv metadata for {arxiv_id}: {e}")
        return None


async def fetch_crossref_metadata(doi: str) -> Optional[Dict[str, Any]]:
    """Query Crossref REST API for structured citation metadata."""
    clean_doi = doi.strip().lower()
    api_url = f"https://api.crossref.org/works/{clean_doi}"

    headers = {
        **DEFAULT_HEADERS,
        "User-Agent": f"PaperFetch/{settings.VERSION} (mailto:{settings.CROSSREF_MAILTO})",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=headers)
            if resp.status_code != 200:
                return None

            data = resp.json().get("message", {})
            title = data.get("title", [""])[0] if data.get("title") else "Untitled"

            authors = []
            for a in data.get("author", []):
                given = a.get("given", "").strip()
                family = a.get("family", "").strip()
                if family and given:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)
                elif a.get("name"):
                    authors.append(a.get("name").strip())

            # Extract year from published date parts
            year = None
            date_parts = data.get("published-print", {}).get("date-parts") or data.get("published-online", {}).get("date-parts") or data.get("created", {}).get("date-parts")
            if date_parts and len(date_parts[0]) > 0:
                year = date_parts[0][0]

            journal = data.get("container-title", [""])[0] if data.get("container-title") else None
            publisher = data.get("publisher")
            volume = data.get("volume")
            issue = data.get("issue")
            pages = data.get("page")
            abstract = data.get("abstract")
            # Strip simple JATS XML tags if present in abstract
            if abstract:
                import re
                abstract = re.sub(r"<[^>]+>", "", abstract).strip()

            pdf_url = None
            for link in data.get("link", []):
                content_type = link.get("content-type", "").lower()
                if "pdf" in content_type:
                    candidate_pdf = link.get("URL")
                    if candidate_pdf and candidate_pdf.startswith("http"):
                        pdf_url = candidate_pdf
                        break

            return {
                "title": title,
                "authors": authors,
                "first_author": authors[0] if authors else None,
                "year": year,
                "doi": clean_doi,
                "journal_or_conference": journal,
                "publisher": publisher,
                "volume": volume,
                "issue": issue,
                "pages": pages,
                "abstract": abstract,
                "original_url": f"https://doi.org/{clean_doi}",
                "pdf_url": pdf_url,
                "access_type": "open_access" if pdf_url else "unknown",
                "metadata_source": "crossref",
            }
    except Exception as e:
        logger.warning(f"Error fetching Crossref metadata for {doi}: {e}")
        return None


async def fetch_openalex_metadata(doi: str) -> Optional[Dict[str, Any]]:
    """Query OpenAlex for open-access PDF links and paper metadata."""
    clean_doi = doi.strip().lower()
    api_url = f"https://api.openalex.org/works/https://doi.org/{clean_doi}"

    headers = {
        **DEFAULT_HEADERS,
        "User-Agent": f"PaperFetch/{settings.VERSION} (mailto:{settings.OPENALEX_EMAIL})",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=headers)
            if resp.status_code != 200:
                return None

            data = resp.json()
            title = data.get("title") or "Untitled"
            year = data.get("publication_year")

            authors = []
            for authorship in data.get("authorships", []):
                author_obj = authorship.get("author", {})
                name = author_obj.get("display_name")
                if name:
                    authors.append(name.strip())

            journal = None
            primary_loc = data.get("primary_location") or {}
            source = primary_loc.get("source") or {}
            if source:
                journal = source.get("display_name")

            open_access = data.get("open_access", {})
            is_oa = open_access.get("is_oa", False)
            pdf_url = open_access.get("oa_url") or primary_loc.get("pdf_url")

            # Check best_oa_location if still no pdf
            if not pdf_url:
                best_oa = data.get("best_oa_location") or {}
                pdf_url = best_oa.get("pdf_url")

            return {
                "title": title,
                "authors": authors,
                "first_author": authors[0] if authors else None,
                "year": year,
                "doi": clean_doi,
                "journal_or_conference": journal,
                "publisher": source.get("host_organization_name"),
                "original_url": f"https://doi.org/{clean_doi}",
                "pdf_url": pdf_url,
                "access_type": "open_access" if is_oa or pdf_url else "restricted",
                "metadata_source": "openalex",
            }
    except Exception as e:
        logger.warning(f"Error fetching OpenAlex metadata for {doi}: {e}")
        return None


async def fetch_unpaywall_metadata(doi: str) -> Optional[Dict[str, Any]]:
    """Query Unpaywall API for legitimate legal open-access PDF links."""
    clean_doi = doi.strip().lower()
    email = settings.UNPAYWALL_EMAIL or "user@example.com"
    api_url = f"https://api.unpaywall.org/v2/{clean_doi}?email={email}"

    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(api_url, headers=DEFAULT_HEADERS)
            if resp.status_code != 200:
                return None

            data = resp.json()
            title = data.get("title")
            year = data.get("year")
            journal = data.get("journal_name")
            publisher = data.get("publisher")
            is_oa = data.get("is_oa", False)

            best_oa = data.get("best_oa_location") or {}
            pdf_url = best_oa.get("url_for_pdf") or best_oa.get("url")

            authors = []
            for z_author in data.get("z_authors", []):
                given = z_author.get("given", "").strip()
                family = z_author.get("family", "").strip()
                if family and given:
                    authors.append(f"{given} {family}")
                elif family:
                    authors.append(family)

            return {
                "title": title,
                "authors": authors,
                "first_author": authors[0] if authors else None,
                "year": year,
                "doi": clean_doi,
                "journal_or_conference": journal,
                "publisher": publisher,
                "original_url": f"https://doi.org/{clean_doi}",
                "pdf_url": pdf_url if (pdf_url and ("pdf" in pdf_url.lower() or is_oa)) else None,
                "access_type": "open_access" if is_oa else "restricted",
                "metadata_source": "unpaywall",
            }
    except Exception as e:
        logger.warning(f"Error fetching Unpaywall metadata for {doi}: {e}")
        return None
