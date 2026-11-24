"""Tests for automated storage cleaner and disk quota management."""
from datetime import datetime, timedelta
import os
from pathlib import Path
import time
import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, init_db
from backend.app.main import app
from backend.app.models import Paper
from backend.app.services.storage_cleaner import (
    cleanup_temp_and_orphan_files,
    flush_storage_if_needed,
    get_current_storage_usage,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


@pytest.mark.asyncio
async def test_get_storage_usage():
    usage = get_current_storage_usage()
    assert "total_bytes" in usage
    assert "total_mb" in usage
    assert "limit_mb" in usage
    assert "usage_percent" in usage
    assert usage["limit_mb"] == settings.MAX_STORAGE_MB


@pytest.mark.asyncio
async def test_cleanup_temp_and_orphan_files(tmp_path):
    # Create test temp file and old part file
    test_temp = settings.TEMP_DIR / "test_old_temp.zip"
    test_temp.write_bytes(b"dummy zip data" * 100)

    test_part = settings.STORAGE_DIR / "test_orphan.part"
    test_part.write_bytes(b"partial download data" * 100)

    # Set mtime back by 2 hours
    old_time = time.time() - 7200
    os.utime(test_temp, (old_time, old_time))
    os.utime(test_part, (old_time, old_time))

    res = cleanup_temp_and_orphan_files(max_age_seconds=1800)
    assert res["deleted_files"] >= 2
    assert not test_temp.exists()
    assert not test_part.exists()


@pytest.mark.asyncio
async def test_flush_storage_removes_physical_file_and_preserves_metadata():
    paper_id = "test_flush_paper_1"
    pdf_filename = f"{paper_id}.pdf"
    pdf_file_path = settings.STORAGE_DIR / pdf_filename
    pdf_file_path.write_bytes(b"%PDF-1.4 sample paper data" * 500)

    async with AsyncSessionLocal() as db:
        paper = Paper(
            id=paper_id,
            title="Important Deep Learning Paper",
            first_author="LeCun",
            year=2024,
            doi="10.1234/deeplearning.2024",
            original_url="https://example.com/paper",
            pdf_url="https://example.com/paper.pdf",
            local_path=str(pdf_file_path),
            filename=pdf_filename,
            status="completed",
            bibtex="@article{lecun2024, title={Important Deep Learning Paper}}",
        )
        db.add(paper)
        await db.commit()

    assert pdf_file_path.exists()

    # Trigger force flush
    result = await flush_storage_if_needed(force_flush=True)
    assert result["flushed"] is True
    assert result["papers_archived"] >= 1

    # Check physical file deleted
    assert not pdf_file_path.exists()

    # Check paper in database still exists and retains all bibliographic metadata!
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        res = await db.execute(select(Paper).where(Paper.id == paper_id))
        saved_paper = res.scalars().first()
        assert saved_paper is not None
        assert saved_paper.title == "Important Deep Learning Paper"
        assert saved_paper.bibtex is not None
        assert saved_paper.doi == "10.1234/deeplearning.2024"
        assert saved_paper.local_path is None
        assert saved_paper.status == "archived"


@pytest.mark.asyncio
async def test_flushed_paper_download_redirects_to_pdf_url():
    paper_id = "test_flushed_redirect"
    async with AsyncSessionLocal() as db:
        paper = Paper(
            id=paper_id,
            title="Online Paper",
            original_url="https://example.com/online-paper",
            pdf_url="https://example.com/online-paper.pdf",
            local_path=None,  # Flushed / archived
            status="archived",
        )
        db.add(paper)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False) as ac:
        res = await ac.get(f"/api/papers/{paper_id}/download")
        assert res.status_code in (302, 307)
        assert res.headers["location"] == "https://example.com/online-paper.pdf"


@pytest.mark.asyncio
async def test_storage_settings_api_endpoints():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Check storage-stats
        res_stats = await ac.get("/api/settings/storage-stats")
        assert res_stats.status_code == 200
        stats = res_stats.json()
        assert "total_mb" in stats
        assert "limit_mb" in stats

        # Check flush-storage
        res_flush = await ac.post("/api/settings/flush-storage")
        assert res_flush.status_code == 200
        flush_data = res_flush.json()
        assert "flushed" in flush_data
        assert "freed_bytes" in flush_data
