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
    """
    Resolve arXiv paper metadata with multi-tier cascading strategy:
    1. Direct abstract page HTML parse (fast Highwire Press tags in ~1s)
    2. Academic DOI resolution (Crossref / OpenAlex for 10.48550/arXiv.{id})
    3. Official export.arxiv.org XML API (as fallback)
    """
    clean_id = arxiv_id.strip()
    if clean_id.lower().startswith("arxiv:"):
        clean_id = clean_id[6:].strip()

    doi = f"10.48550/arXiv.{clean_id}"
    abs_url = f"https://arxiv.org/abs/{clean_id}"
    pdf_url = f"https://arxiv.org/pdf/{clean_id}.pdf"

    result: Dict[str, Any] = {
        "title": None,
        "authors": [],
        "first_author": None,
        "year": None,
        "doi": doi,
        "journal_or_conference": "arXiv Preprint",
        "publisher": "arXiv",
        "abstract": None,
        "original_url": abs_url,
        "pdf_url": pdf_url,
        "access_type": "open_access",
        "metadata_source": "arxiv",
    }

    # 1. Fetch arXiv abstract webpage (very fast and reliable)
    from backend.app.services.metadata_extractor import extract_from_webpage
    try:
        web_meta = await extract_from_webpage(abs_url)
        if web_meta:
            if web_meta.get("title") and "untitled" not in web_meta["title"].lower():
                result["title"] = web_meta["title"]
            if web_meta.get("authors"):
                result["authors"] = web_meta["authors"]
                result["first_author"] = web_meta.get("first_author")
            if web_meta.get("year"):
                result["year"] = web_meta["year"]
            if web_meta.get("abstract"):
                result["abstract"] = web_meta["abstract"]
    except Exception as e:
        logger.warning(f"Error scraping arXiv webpage for {clean_id}: {e}")

    # 2. Query DOI resolver (Crossref / OpenAlex) for the arXiv DOI
    from backend.app.services.doi_resolver import resolve_doi
    try:
        doi_meta = await resolve_doi(doi)
        if doi_meta:
            if (not result["title"] or "untitled" in result["title"].lower()) and doi_meta.get("title"):
                result["title"] = doi_meta["title"]
            if (not result["authors"] or len(result["authors"]) == 0) and doi_meta.get("authors"):
                result["authors"] = doi_meta["authors"]
                result["first_author"] = doi_meta.get("first_author")
            if not result["year"] and doi_meta.get("year"):
                result["year"] = doi_meta["year"]
            if not result["abstract"] and doi_meta.get("abstract"):
                result["abstract"] = doi_meta["abstract"]
            if doi_meta.get("journal_or_conference") and doi_meta["journal_or_conference"] != "arXiv":
                result["journal_or_conference"] = doi_meta["journal_or_conference"]
    except Exception as e:
        logger.warning(f"Error resolving arXiv DOI {doi}: {e}")

    # 3. Fallback to export.arxiv.org XML API if title is still missing
    if not result["title"] or "untitled" in result["title"].lower():
        api_url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
        try:
            async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
                resp = await client.get(api_url, headers={"User-Agent": DEFAULT_HEADERS["User-Agent"]})
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
                    entry = root.find("atom:entry", ns)
                    if entry is not None:
                        t_elem = entry.find("atom:title", ns)
                        if t_elem is not None and t_elem.text:
                            result["title"] = t_elem.text.strip().replace("\n", " ")
                        sum_elem = entry.find("atom:summary", ns)
                        if sum_elem is not None and sum_elem.text and not result["abstract"]:
                            result["abstract"] = sum_elem.text.strip()
                        pub_elem = entry.find("atom:published", ns)
                        if pub_elem is not None and pub_elem.text and not result["year"]:
                            result["year"] = int(pub_elem.text[:4])
                        if not result["authors"]:
                            for a_node in entry.findall("atom:author", ns):
                                n_node = a_node.find("atom:name", ns)
                                if n_node is not None and n_node.text:
                                    result["authors"].append(n_node.text.strip())
        except Exception as e:
            logger.warning(f"Error fetching from export.arxiv.org for {clean_id}: {e}")

    if not result["title"]:
        result["title"] = f"arXiv:{clean_id}"

    if result["authors"] and not result["first_author"]:
        result["first_author"] = result["authors"][0]

    return result


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


async def search_paper_by_title(title_query: str) -> Optional[Dict[str, Any]]:
    """
    Search academic databases (OpenAlex and Crossref) by paper title.
    Used as an intelligent fallback when academic profile pages (e.g. ResearchGate,
    Academia.edu, SSRN) block direct web scraping or lack direct PDF links.
    """
    if not title_query or len(title_query.strip()) < 8:
        return None

    clean_query = title_query.strip()
    from backend.app.services.duplicate_detector import titles_are_similar
    from backend.app.services.doi_resolver import resolve_doi

    # 1. Search OpenAlex
    try:
        headers = {
            **DEFAULT_HEADERS,
            "User-Agent": f"PaperFetch/{settings.VERSION} (mailto:{settings.OPENALEX_EMAIL})",
        }
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.openalex.org/works",
                params={"search": clean_query, "per_page": 3},
                headers=headers,
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                for item in results:
                    candidate_title = item.get("title")
                    if candidate_title and titles_are_similar(candidate_title, clean_query, threshold=0.65):
                        doi = item.get("doi")
                        if doi:
                            clean_doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").strip()
                            resolved = await resolve_doi(clean_doi)
                            if resolved:
                                return resolved

                        # Build from OpenAlex if DOI resolution was incomplete
                        pdf_url = item.get("open_access", {}).get("oa_url") or item.get("primary_location", {}).get("pdf_url")
                        authors = [
                            a.get("author", {}).get("display_name")
                            for a in item.get("authorships", [])
                            if a.get("author", {}).get("display_name")
                        ]
                        return {
                            "title": candidate_title,
                            "authors": authors,
                            "first_author": authors[0] if authors else None,
                            "year": item.get("publication_year"),
                            "doi": item.get("doi"),
                            "journal_or_conference": (item.get("primary_location") or {}).get("source", {}).get("display_name"),
                            "pdf_url": pdf_url,
                            "access_type": "open_access" if pdf_url else "unknown",
                            "metadata_source": "openalex_search",
                        }
    except Exception as e:
        logger.warning(f"OpenAlex title search failed for '{clean_query}': {e}")

    # 2. Search Crossref
    try:
        headers = {
            **DEFAULT_HEADERS,
            "User-Agent": f"PaperFetch/{settings.VERSION} (mailto:{settings.CROSSREF_MAILTO})",
        }
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(
                "https://api.crossref.org/works",
                params={"query.bibliographic": clean_query, "rows": 3},
                headers=headers,
            )
            if resp.status_code == 200:
                items = resp.json().get("message", {}).get("items", [])
                for it in items:
                    titles = it.get("title", [])
                    candidate_title = titles[0] if titles else None
                    if candidate_title and titles_are_similar(candidate_title, clean_query, threshold=0.65):
                        doi = it.get("DOI")
                        if doi:
                            resolved = await resolve_doi(doi)
                            if resolved:
                                return resolved
    except Exception as e:
        logger.warning(f"Crossref title search failed for '{clean_query}': {e}")

    return None
