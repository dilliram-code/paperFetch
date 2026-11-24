"""Webpage HTML metadata extraction and academic citation parsing."""
import json
import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import httpx

from backend.app.utils.security import validate_target_url
from backend.app.utils.url_validator import extract_doi

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 PaperFetch/2.0"


def parse_html_metadata(html_content: str, base_url: str) -> Dict[str, Any]:
    """
    Parse academic meta tags (Highwire Press, Dublin Core, OpenGraph, JSON-LD) from HTML.
    """
    soup = BeautifulSoup(html_content, "html.parser")
    result: Dict[str, Any] = {
        "title": None,
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
        "pdf_url": None,
        "original_url": base_url,
        "metadata_source": "webpage_html",
    }

    # 1. Highwire Press / Google Scholar citation tags
    citation_title = soup.find("meta", attrs={"name": re.compile(r"^citation_title$", re.I)})
    if citation_title and citation_title.get("content"):
        result["title"] = citation_title["content"].strip()

    citation_authors = soup.find_all("meta", attrs={"name": re.compile(r"^citation_author$", re.I)})
    for author_meta in citation_authors:
        author_name = author_meta.get("content", "").strip()
        if author_name and author_name not in result["authors"]:
            result["authors"].append(author_name)

    citation_date = soup.find("meta", attrs={"name": re.compile(r"^citation_publication_date$|^citation_date$|^citation_year$", re.I)})
    if citation_date and citation_date.get("content"):
        match = re.search(r"\b(19\d{2}|20\d{2})\b", citation_date["content"])
        if match:
            result["year"] = int(match.group(1))

    citation_doi = soup.find("meta", attrs={"name": re.compile(r"^citation_doi$", re.I)})
    if citation_doi and citation_doi.get("content"):
        doi = extract_doi(citation_doi["content"])
        if doi:
            result["doi"] = doi

    citation_pdf = soup.find("meta", attrs={"name": re.compile(r"^citation_pdf_url$", re.I)})
    if citation_pdf and citation_pdf.get("content"):
        raw_pdf_url = citation_pdf["content"].strip()
        result["pdf_url"] = urljoin(base_url, raw_pdf_url)

    citation_journal = soup.find("meta", attrs={"name": re.compile(r"^citation_journal_title$", re.I)})
    if citation_journal and citation_journal.get("content"):
        result["journal_or_conference"] = citation_journal["content"].strip()

    citation_publisher = soup.find("meta", attrs={"name": re.compile(r"^citation_publisher$", re.I)})
    if citation_publisher and citation_publisher.get("content"):
        result["publisher"] = citation_publisher["content"].strip()

    citation_abstract = soup.find("meta", attrs={"name": re.compile(r"^citation_abstract$", re.I)})
    if citation_abstract and citation_abstract.get("content"):
        result["abstract"] = citation_abstract["content"].strip()

    citation_volume = soup.find("meta", attrs={"name": re.compile(r"^citation_volume$", re.I)})
    if citation_volume and citation_volume.get("content"):
        result["volume"] = citation_volume["content"].strip()

    citation_issue = soup.find("meta", attrs={"name": re.compile(r"^citation_issue$", re.I)})
    if citation_issue and citation_issue.get("content"):
        result["issue"] = citation_issue["content"].strip()

    first_page = soup.find("meta", attrs={"name": re.compile(r"^citation_firstpage$", re.I)})
    last_page = soup.find("meta", attrs={"name": re.compile(r"^citation_lastpage$", re.I)})
    if first_page and first_page.get("content"):
        fp = first_page["content"].strip()
        lp = last_page["content"].strip() if last_page and last_page.get("content") else ""
        result["pages"] = f"{fp}--{lp}" if lp else fp

    # 2. Dublin Core Tags (DC.title, DC.creator, DC.date, DC.identifier)
    if not result["title"]:
        dc_title = soup.find("meta", attrs={"name": re.compile(r"^dc\.title$", re.I)})
        if dc_title and dc_title.get("content"):
            result["title"] = dc_title["content"].strip()

    if not result["authors"]:
        dc_creators = soup.find_all("meta", attrs={"name": re.compile(r"^dc\.creator$", re.I)})
        for dc_c in dc_creators:
            c_name = dc_c.get("content", "").strip()
            if c_name and c_name not in result["authors"]:
                result["authors"].append(c_name)

    if not result["year"]:
        dc_date = soup.find("meta", attrs={"name": re.compile(r"^dc\.date$", re.I)})
        if dc_date and dc_date.get("content"):
            match = re.search(r"\b(19\d{2}|20\d{2})\b", dc_date["content"])
            if match:
                result["year"] = int(match.group(1))

    if not result["doi"]:
        dc_identifier = soup.find("meta", attrs={"name": re.compile(r"^dc\.identifier$", re.I)})
        if dc_identifier and dc_identifier.get("content"):
            doi = extract_doi(dc_identifier["content"])
            if doi:
                result["doi"] = doi

    # 3. JSON-LD Structured Data
    for script_tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            raw_text = script_tag.string or script_tag.text
            if not raw_text:
                continue
            data = json.loads(raw_text)
            if isinstance(data, list):
                data = data[0] if data else {}
            if isinstance(data, dict):
                t = data.get("@type", "")
                if any(x in str(t).lower() for x in ("scholarlyarticle", "article", "medicalwebpage")):
                    if not result["title"] and data.get("headline"):
                        result["title"] = data["headline"].strip()
                    elif not result["title"] and data.get("name"):
                        result["title"] = data["name"].strip()

                    if not result["authors"] and data.get("author"):
                        authors_data = data["author"]
                        if isinstance(authors_data, dict):
                            authors_data = [authors_data]
                        if isinstance(authors_data, list):
                            for a in authors_data:
                                if isinstance(a, dict) and a.get("name"):
                                    result["authors"].append(a["name"].strip())
                                elif isinstance(a, str):
                                    result["authors"].append(a.strip())

                    if not result["abstract"] and data.get("description"):
                        result["abstract"] = data["description"].strip()
        except Exception:
            pass

    # Abstract HTML block fallback (e.g. arXiv blockquote.abstract)
    if not result["abstract"]:
        abs_block = soup.find("blockquote", class_=re.compile(r"abstract", re.I))
        if abs_block:
            abs_text = abs_block.get_text().strip()
            if abs_text.lower().startswith("abstract:"):
                abs_text = abs_text[9:].strip()
            result["abstract"] = abs_text

    # 4. OpenGraph fallbacks
    if not result["title"]:
        og_title = soup.find("meta", attrs={"property": "og:title"})
        if og_title and og_title.get("content"):
            result["title"] = og_title["content"].strip()
    if not result["title"] and soup.title and soup.title.string:
        result["title"] = soup.title.string.strip()

    # 5. Search for direct PDF link in HTML if citation_pdf_url wasn't found
    if not result["pdf_url"]:
        # Find links ending with .pdf or containing download/pdf
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            text = (a_tag.get_text() or "").lower()
            rel = (a_tag.get("rel") or "")
            class_attr = str(a_tag.get("class") or "").lower()

            is_pdf_href = href.lower().endswith(".pdf") or "/pdf/" in href.lower()
            is_pdf_text = "download pdf" in text or "full text pdf" in text or "view pdf" in text or "pdf" == text.strip()
            
            if is_pdf_href or is_pdf_text:
                # Do not choose unrelated PDF links (e.g. privacy policy, license, guidelines)
                if any(x in href.lower() or x in text for x in ("privacy", "term", "cookie", "guide", "manual", "instruction")):
                    continue
                result["pdf_url"] = urljoin(base_url, href)
                break

    if result["authors"] and not result["first_author"]:
        result["first_author"] = result["authors"][0]

    return result


async def extract_from_webpage(url: str) -> Optional[Dict[str, Any]]:
    """Fetch academic webpage with SSRF protection and extract metadata and PDF links."""
    validate_target_url(url)

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            # Re-validate final URL after redirects for SSRF
            validate_target_url(str(resp.url))

            content_type = resp.headers.get("content-type", "").lower()
            if "pdf" in content_type:
                # The URL actually redirected or returned a direct PDF!
                return {
                    "is_direct_pdf": True,
                    "pdf_url": str(resp.url),
                    "original_url": url,
                    "title": "Direct PDF Document",
                }

            if resp.status_code != 200:
                logger.warning(f"Webpage fetch returned status {resp.status_code} for {url}")
                return None

            metadata = parse_html_metadata(resp.text, str(resp.url))
            return metadata
    except Exception as e:
        logger.warning(f"Failed to extract metadata from webpage {url}: {e}")
        return None
