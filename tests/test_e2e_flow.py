"""End-to-End integration test covering detection, editing, downloading, library, and ZIP export."""
from pathlib import Path
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.main import app
from backend.app.models import Paper
from backend.app.services.zip_service import create_papers_zip


@pytest.fixture(autouse=True)
async def setup_test_db():
    await init_db()


@pytest.mark.asyncio
async def test_full_detection_and_library_flow(tmp_path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # 1. Test health check
        health_res = await ac.get("/api/health")
        assert health_res.status_code == 200

        # 2. Test metadata detection with DOI
        detect_res = await ac.post("/api/papers/detect", json={
            "inputs": ["10.1038/s41586-023-06747-5"]
        })
        assert detect_res.status_code == 200
        data = detect_res.json()
        assert len(data["papers"]) == 1
        paper = data["papers"][0]
        paper_id = paper["id"]
        assert paper["doi"] == "10.1038/s41586-023-06747-5"

        # 3. Test metadata patch / edit
        patch_res = await ac.patch(f"/api/papers/{paper_id}", json={
            "title": "Edited Paper Title for Testing",
            "year": 2024,
            "journal_or_conference": "Nature Machine Intelligence",
        })
        assert patch_res.status_code == 200
        updated = patch_res.json()
        assert updated["title"] == "Edited Paper Title for Testing"
        assert updated["year"] == 2024
        assert "Edited Paper Title for Testing" in updated["bibtex"]
        assert updated["filename"].startswith("2024_")

        # 4. Test BibTeX export endpoint
        bib_res = await ac.get(f"/api/citations/paper/{paper_id}")
        assert bib_res.status_code == 200
        assert "Edited Paper Title for Testing" in bib_res.text

        # 5. Test batch BibTeX export
        batch_bib_res = await ac.post("/api/citations/export", json={"paper_ids": [paper_id]})
        assert batch_bib_res.status_code == 200
        assert "@" in batch_bib_res.text

        # 6. Test library search
        search_res = await ac.get("/api/library?q=Edited")
        assert search_res.status_code == 200
        assert search_res.json()["total"] >= 1

        # 7. Test mock PDF creation and ZIP export service
        fake_pdf = tmp_path / "test_paper.pdf"
        fake_pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
        
        mock_paper = Paper(
            id="mock-zip-paper",
            title="ZIP Test Paper",
            filename="2024_Test_Paper.pdf",
            local_path=str(fake_pdf),
            status="completed",
        )
        zip_path = create_papers_zip([mock_paper])
        assert zip_path is not None
        assert zip_path.exists()
        assert zip_path.suffix == ".zip"
        zip_path.unlink()  # cleanup

        # 8. Test deletion from library
        del_res = await ac.delete(f"/api/library/{paper_id}")
        assert del_res.status_code == 200
        assert del_res.json()["id"] == paper_id

        # Verify paper is no longer in library
        after_del = await ac.get(f"/api/papers/{paper_id}")
        assert after_del.status_code == 404
