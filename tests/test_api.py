"""Tests for FastAPI endpoints."""
import io
import uuid
import zipfile
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.config import settings
from backend.app.database import AsyncSessionLocal, init_db
from backend.app.models import Paper
from backend.app.main import app


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["version"] == "2.0.0"


@pytest.mark.asyncio
async def test_detect_validation_error():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Empty inputs list
        res = await ac.post("/api/papers/detect", json={"inputs": []})
        assert res.status_code == 422

        # More than 10 inputs
        res2 = await ac.post("/api/papers/detect", json={"inputs": [f"http://test{i}.com" for i in range(12)]})
        assert res2.status_code == 422


@pytest.mark.asyncio
async def test_library_and_history_empty():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/library")
        assert res.status_code == 200
        data = res.json()
        assert "items" in data
        assert "total" in data

        res2 = await ac.get("/api/history")
        assert res2.status_code == 200
        assert "history" in res2.json()


@pytest.mark.asyncio
async def test_settings_get_and_patch():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/settings")
        assert res.status_code == 200
        data = res.json()
        assert "max_concurrent_downloads" in data
        assert "theme" in data

        # Patch setting concurrency and theme
        res_patch = await ac.patch("/api/settings", json={"max_concurrent_downloads": 10, "theme": "light"})
        assert res_patch.status_code == 200
        patch_data = res_patch.json()
        assert patch_data["max_concurrent_downloads"] == 10
        assert patch_data["theme"] == "light"


@pytest.mark.asyncio
async def test_create_download_jobs_api(monkeypatch):
    from backend.app.models import DownloadJob
    from backend.app.services.job_manager import job_manager

    # Avoid spawning real background downloader in unit test
    async def noop_run_task(job_id, paper_id):
        pass
    monkeypatch.setattr(job_manager, "run_download_task", noop_run_task)

    # Test to_dict on job with None fields
    job_empty = DownloadJob(id="test-job-empty")
    d = job_empty.to_dict()
    assert d["speed_bytes_per_sec"] == 0.0
    assert d["eta_seconds"] == 0.0
    assert d["progress_percent"] == 0.0

    # Test POST /api/jobs with a real paper
    test_pid = f"paper-job-test-{uuid.uuid4().hex[:8]}"
    paper = Paper(
        id=test_pid,
        title="Test Job Creation Paper",
        pdf_url="https://example.com/test.pdf",
        status="awaiting_confirmation",
    )
    async with AsyncSessionLocal() as db:
        db.add(paper)
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post("/api/jobs", json={"paper_ids": [test_pid]})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 1
        assert data[0]["paper_id"] == test_pid
        assert data[0]["status"] == "waiting"
        assert data[0]["speed_bytes_per_sec"] == 0.0


@pytest.mark.asyncio
async def test_downloads_zip_batch_filtering(tmp_path):
    # Setup two completed papers with mock PDFs
    pdf1 = tmp_path / "paper_prev.pdf"
    pdf1.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
    pdf2 = tmp_path / "paper_current.pdf"
    pdf2.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")

    p1_id = f"prev-{uuid.uuid4().hex[:8]}"
    p2_id = f"curr-{uuid.uuid4().hex[:8]}"

    p1 = Paper(
        id=p1_id,
        title="Previously Downloaded Paper",
        filename="prev_paper.pdf",
        local_path=str(pdf1),
        status="completed",
    )
    p2 = Paper(
        id=p2_id,
        title="Current Batch Paper",
        filename="current_paper.pdf",
        local_path=str(pdf2),
        status="completed",
    )

    async with AsyncSessionLocal() as db:
        db.add_all([p1, p2])
        await db.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Download ZIP filtering ONLY p2_id (current batch)
        res = await ac.get(f"/api/downloads/zip?paper_ids={p2_id}")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/zip"
        
        # Verify ZIP contains only current_paper.pdf and NOT prev_paper.pdf
        with zipfile.ZipFile(io.BytesIO(res.content)) as zf:
            file_names = zf.namelist()
            assert "current_paper.pdf" in file_names
            assert "prev_paper.pdf" not in file_names

        # 2. Comma-separated query param test
        res_both = await ac.get(f"/api/downloads/zip?paper_ids={p1_id},{p2_id}")
        assert res_both.status_code == 200
        with zipfile.ZipFile(io.BytesIO(res_both.content)) as zf:
            names = zf.namelist()
            assert "prev_paper.pdf" in names
            assert "current_paper.pdf" in names

        # 3. Non-existent batch paper ID returns 404
        res_none = await ac.get("/api/downloads/zip?paper_ids=non-existent-id")
        assert res_none.status_code == 404
