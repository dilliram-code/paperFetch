"""Tests for PDF validation and safe local resolution."""
import hashlib
from pathlib import Path
import pytest
from httpx import Response
from backend.app.config import settings
from backend.app.services.downloader import download_pdf_stream
from backend.app.services.pdf_validator import is_valid_pdf_bytes, validate_pdf_file
from backend.app.utils.security import safe_resolve_path


def test_is_valid_pdf_bytes():
    assert is_valid_pdf_bytes(b"%PDF-1.4\n") is True
    assert is_valid_pdf_bytes(b"<!DOCTYPE html><html>") is False
    assert is_valid_pdf_bytes(b"random content") is False


def test_safe_resolve_path(tmp_path):
    base = tmp_path / "storage"
    base.mkdir()

    # Normal filename
    res = safe_resolve_path(base, "2024_Smith_Paper.pdf")
    assert res == base / "2024_Smith_Paper.pdf"

    # Directory traversal attempt should be safely stripped to basename
    res2 = safe_resolve_path(base, "../../etc/passwd.pdf")
    assert res2 == base / "passwd.pdf"
    assert str(res2).startswith(str(base))


@pytest.mark.asyncio
async def test_download_pdf_stream_hashing_and_speed(monkeypatch, tmp_path):
    # Setup test storage dir
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path)

    # Valid minimal PDF payload
    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    )
    expected_hash = hashlib.sha256(pdf_bytes).hexdigest()

    # Mock client stream response
    class MockStreamResponse:
        def __init__(self):
            self.status_code = 200
            self.headers = {"content-length": str(len(pdf_bytes))}
            self.url = "https://example.com/fast_test.pdf"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_bytes(self, chunk_size):
            yield pdf_bytes

    class MockClient:
        def stream(self, method, url, headers=None):
            return MockStreamResponse()

    monkeypatch.setattr("backend.app.services.downloader.validate_target_url", lambda u: None)
    monkeypatch.setattr("backend.app.services.downloader.get_download_client", lambda: MockClient())

    progress_events = []
    def on_prog(downloaded, total, speed, eta):
        progress_events.append((downloaded, total))

    success, err, dest_path, file_hash, file_size, page_count = await download_pdf_stream(
        url="https://example.com/fast_test.pdf",
        target_filename="fast_test.pdf",
        progress_callback=on_prog,
    )

    assert success is True
    assert err is None
    assert dest_path.exists()
    assert file_hash == expected_hash
    assert file_size == len(pdf_bytes)
    assert page_count >= 1


@pytest.mark.asyncio
async def test_download_html_redirects_to_embedded_pdf(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "STORAGE_DIR", tmp_path)
    monkeypatch.setattr("backend.app.services.downloader.validate_target_url", lambda u: None)

    pdf_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000009 00000 n \n0000000052 00000 n \n0000000101 00000 n \n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF\n"
    )

    html_content = b'<html><head><meta name="citation_pdf_url" content="https://example.com/real.pdf"></head><body>Loading...</body></html>'

    class MockHtmlOrPdfStreamResponse:
        def __init__(self, target_url):
            self.target_url = target_url
            if "real.pdf" in target_url:
                self.status_code = 200
                self.headers = {"content-type": "application/pdf", "content-length": str(len(pdf_bytes))}
                self.url = target_url
            else:
                self.status_code = 200
                self.headers = {"content-type": "text/html"}
                self.url = target_url

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def aiter_bytes(self, chunk_size):
            if "real.pdf" in self.target_url:
                yield pdf_bytes
            else:
                yield html_content

        async def aread(self):
            return html_content

    class DynamicMockClient:
        def stream(self, method, url, headers=None):
            return MockHtmlOrPdfStreamResponse(url)

    monkeypatch.setattr("backend.app.services.downloader.get_download_client", lambda: DynamicMockClient())

    success, err, dest_path, file_hash, file_size, page_count = await download_pdf_stream(
        url="https://example.com/article_landing_page",
        target_filename="redirect_test.pdf",
    )

    assert success is True
    assert err is None
    assert dest_path.exists()
    assert file_size == len(pdf_bytes)


def test_validate_pdf_file_html_detection(tmp_path):
    fake_html = tmp_path / "fake.pdf"
    fake_html.write_bytes(b"<!DOCTYPE html><html><body>Access Denied - Paywall</body></html>")
    is_valid, err, page_count, _ = validate_pdf_file(fake_html)
    assert is_valid is False
    assert "HTML webpage rather than a PDF" in err
