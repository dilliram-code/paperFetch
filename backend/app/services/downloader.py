"""Asynchronous high-speed streaming PDF downloader with resume and retry support."""
import asyncio
import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional, Tuple
from urllib.parse import urljoin
import aiofiles
from bs4 import BeautifulSoup
import httpx

from backend.app.config import settings
from backend.app.services.metadata_extractor import USER_AGENT
from backend.app.services.pdf_validator import validate_pdf_file
from backend.app.utils.security import safe_resolve_path, validate_target_url

logger = logging.getLogger(__name__)

_download_client: Optional[httpx.AsyncClient] = None


def get_download_client() -> httpx.AsyncClient:
    """Singleton high-performance HTTP client with connection pooling and HTTP/2."""
    global _download_client
    if _download_client is None or _download_client.is_closed:
        _download_client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.DOWNLOAD_TIMEOUT_SECONDS, connect=10.0, read=settings.DOWNLOAD_TIMEOUT_SECONDS),
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=60.0),
            http2=True,
        )
    return _download_client


async def close_download_client() -> None:
    """Close the singleton HTTP client."""
    global _download_client
    if _download_client is not None and not _download_client.is_closed:
        await _download_client.aclose()
        _download_client = None


async def download_pdf_stream(
    url: str,
    target_filename: str,
    progress_callback: Optional[Callable[[int, int, float, float], None]] = None,
    cancel_event: Optional[asyncio.Event] = None,
    max_retries: int = 3,
) -> Tuple[bool, Optional[str], Optional[Path], Optional[str], int, int]:
    """
    Download a PDF file using streaming, supporting HTTP Range resume, exponential backoff,
    real-time progress calculation, and PyMuPDF validation.
    
    Returns:
        (success, error_message, final_path, sha256_hash, file_size_bytes, page_count)
    """
    validate_target_url(url)
    dest_path = safe_resolve_path(settings.STORAGE_DIR, target_filename)
    part_path = dest_path.with_suffix(".part")

    max_size_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    chunk_size = settings.CHUNK_SIZE_BYTES

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/pdf,application/octet-stream,*/*",
    }

    retries = 0
    start_time = time.time()
    last_calc_time = start_time
    last_bytes = 0

    while retries <= max_retries:
        if cancel_event and cancel_event.is_set():
            if part_path.exists():
                part_path.unlink(missing_ok=True)
            return False, "Download cancelled by user", None, None, 0, 0

        # Check existing partial size for resuming
        downloaded_bytes = part_path.stat().st_size if part_path.exists() else 0
        req_headers = dict(headers)
        if downloaded_bytes > 0:
            req_headers["Range"] = f"bytes={downloaded_bytes}-"

        try:
            client = get_download_client()
            async with client.stream("GET", url, headers=req_headers) as resp:
                validate_target_url(str(resp.url))

                # Check status code
                if resp.status_code not in (200, 206):
                    # If range was not satisfiable, restart from 0
                    if resp.status_code == 416 and downloaded_bytes > 0:
                        if part_path.exists():
                            part_path.unlink()
                        downloaded_bytes = 0
                        retries += 1
                        continue
                    raise Exception(f"HTTP status {resp.status_code}: {resp.reason_phrase}")

                # Check if server returned HTML landing page instead of PDF
                ct = resp.headers.get("content-type", "").lower()
                if "text/html" in ct:
                    html_bytes = await resp.aread()
                    html_text = html_bytes.decode("utf-8", errors="ignore")
                    soup = BeautifulSoup(html_text, "html.parser")

                    candidate_pdf = None
                    meta_pdf = soup.find("meta", attrs={"name": re.compile(r"^citation_pdf_url$", re.I)})
                    if meta_pdf and meta_pdf.get("content"):
                        candidate_pdf = urljoin(str(resp.url), meta_pdf["content"].strip())

                    if not candidate_pdf:
                        link_pdf = soup.find("link", attrs={"type": re.compile(r"pdf", re.I)})
                        if link_pdf and link_pdf.get("href"):
                            candidate_pdf = urljoin(str(resp.url), link_pdf["href"].strip())

                    if not candidate_pdf:
                        for a in soup.find_all("a", href=True):
                            href = a["href"].strip()
                            t = a.get_text().strip().lower()
                            if href.lower().endswith(".pdf") or "download pdf" in t or "view pdf" in t:
                                candidate_pdf = urljoin(str(resp.url), href)
                                break

                    if candidate_pdf and candidate_pdf != url:
                        logger.info(f"HTML response resolved to embedded PDF URL: {candidate_pdf}")
                        url = candidate_pdf
                        retries += 1
                        continue

                    if part_path.exists():
                        part_path.unlink(missing_ok=True)
                    return (
                        False,
                        "Target URL returned an HTML page (paywalled, captcha, or login required) instead of a PDF document",
                        None,
                        None,
                        0,
                        0,
                    )

                # Determine total size
                content_length = resp.headers.get("content-length")
                total_bytes = 0
                if content_length:
                    try:
                        if resp.status_code == 206:
                            total_bytes = downloaded_bytes + int(content_length)
                        else:
                            total_bytes = int(content_length)
                    except ValueError:
                        total_bytes = 0

                if total_bytes > max_size_bytes:
                    raise Exception(f"File size exceeds maximum allowed ({settings.MAX_FILE_SIZE_MB}MB)")

                # Write mode: append if 206 Partial Content, else overwrite
                write_mode = "ab" if resp.status_code == 206 and downloaded_bytes > 0 else "wb"
                if write_mode == "wb":
                    downloaded_bytes = 0

                sha256 = hashlib.sha256()
                if write_mode == "ab" and part_path.exists():
                    with open(part_path, "rb") as existing_f:
                        while prev_chunk := existing_f.read(chunk_size):
                            sha256.update(prev_chunk)

                first_chunk = True
                html_redirect_url = None
                async with aiofiles.open(part_path, write_mode) as f:
                    async for chunk in resp.aiter_bytes(chunk_size):
                        if cancel_event and cancel_event.is_set():
                            raise asyncio.CancelledError()

                        # Check first chunk for raw HTML signatures
                        if first_chunk and write_mode == "wb":
                            first_chunk = False
                            peek = chunk[:1024].lstrip().lower()
                            if (
                                peek.startswith((b"<!doctype html", b"<html", b"<?xml", b"<head", b"<body"))
                                or (b"<html" in peek and b"%pdf-" not in peek)
                            ):
                                html_rest = await resp.aread()
                                full_html = (chunk + html_rest).decode("utf-8", errors="ignore")
                                soup = BeautifulSoup(full_html, "html.parser")
                                candidate_pdf = None
                                meta_pdf = soup.find("meta", attrs={"name": re.compile(r"^citation_pdf_url$", re.I)})
                                if meta_pdf and meta_pdf.get("content"):
                                    candidate_pdf = urljoin(str(resp.url), meta_pdf["content"].strip())
                                if not candidate_pdf:
                                    for a in soup.find_all("a", href=True):
                                        href = a["href"].strip()
                                        t = a.get_text().strip().lower()
                                        if href.lower().endswith(".pdf") or "download pdf" in t or "view pdf" in t:
                                            candidate_pdf = urljoin(str(resp.url), href)
                                            break
                                if candidate_pdf and candidate_pdf != url:
                                    html_redirect_url = candidate_pdf
                                    break
                                if part_path.exists():
                                    part_path.unlink(missing_ok=True)
                                return (
                                    False,
                                    "Target URL returned an HTML webpage (paywalled or login required) instead of a PDF document",
                                    None,
                                    None,
                                    0,
                                    0,
                                )

                        await f.write(chunk)
                        sha256.update(chunk)
                        downloaded_bytes += len(chunk)

                        if downloaded_bytes > max_size_bytes:
                            raise Exception(f"File size exceeded {settings.MAX_FILE_SIZE_MB}MB during download")

                        # Calculate speed and ETA
                        now = time.time()
                        elapsed = now - last_calc_time
                        if elapsed >= 0.35 or (total_bytes and downloaded_bytes >= total_bytes):
                            speed = (downloaded_bytes - last_bytes) / elapsed if elapsed > 0 else 0.0
                            eta = (total_bytes - downloaded_bytes) / speed if speed > 0 and total_bytes > downloaded_bytes else 0.0
                            last_calc_time = now
                            last_bytes = downloaded_bytes

                            if progress_callback:
                                progress_callback(downloaded_bytes, total_bytes, speed, eta)

                if html_redirect_url:
                    url = html_redirect_url
                    retries += 1
                    if part_path.exists():
                        part_path.unlink(missing_ok=True)
                    continue

                # Finished streaming current response successfully
                file_hash = sha256.hexdigest()
                break

        except asyncio.CancelledError:
            if part_path.exists():
                part_path.unlink(missing_ok=True)
            return False, "Download cancelled by user", None, None, 0, 0

        except Exception as e:
            retries += 1
            logger.warning(f"Download attempt {retries}/{max_retries} failed for {url}: {e}")
            if retries > max_retries:
                if part_path.exists():
                    part_path.unlink(missing_ok=True)
                return False, f"Download failed after {max_retries} retries: {str(e)}", None, None, 0, 0
            # Exponential backoff
            await asyncio.sleep(min(2 ** retries, 10))

    # Move part file to final destination
    if not part_path.exists():
        return False, "Downloaded file does not exist", None, None, 0, 0

    if dest_path.exists():
        dest_path.unlink()
    part_path.rename(dest_path)

    # Validate PDF structure and integrity using PyMuPDF
    is_valid, val_err, page_count, _ = validate_pdf_file(dest_path)
    if not is_valid:
        dest_path.unlink(missing_ok=True)
        return False, f"Downloaded file is not a valid PDF: {val_err}", None, None, 0, 0

    file_size = dest_path.stat().st_size
    if not file_hash:
        # Fallback in case hash wasn't captured
        sha256 = hashlib.sha256()
        with open(dest_path, "rb") as f:
            while c := f.read(chunk_size):
                sha256.update(c)
        file_hash = sha256.hexdigest()

    return True, None, dest_path, file_hash, file_size, page_count
