"""Tests for FastAPI endpoints."""
import pytest
from httpx import ASGITransport, AsyncClient
from backend.app.database import init_db
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

        # Patch setting
        res_patch = await ac.patch("/api/settings", json={"max_concurrent_downloads": 4})
        assert res_patch.status_code == 200
        assert res_patch.json()["max_concurrent_downloads"] == 4
