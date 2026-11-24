"""PaperFetch FastAPI application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.app.api.citations import router as citations_router
from backend.app.api.downloads import router as downloads_router
from backend.app.api.library import router as library_router
from backend.app.api.papers import router as papers_router
from backend.app.api.settings_api import router as settings_router
from backend.app.config import settings
from backend.app.database import init_db
from backend.app.schemas import HealthResponse
from backend.app.services.downloader import close_download_client
from backend.app.services.storage_cleaner import (
    get_current_storage_usage,
    start_storage_cleaner_task,
    stop_storage_cleaner_task,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure directories and database tables exist
    settings.setup_directories()
    await init_db()
    # Start automated background storage flush worker
    start_storage_cleaner_task()
    yield
    # Shutdown logic
    stop_storage_cleaner_task()
    await close_download_client()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Intelligent Academic Research Paper Downloader & Library Manager",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(papers_router)
app.include_router(downloads_router)
app.include_router(library_router)
app.include_router(citations_router)
app.include_router(settings_router)


@app.get("/api/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """System health and storage diagnostics."""
    storage_ok = settings.STORAGE_DIR.exists() and settings.TEMP_DIR.exists()
    return HealthResponse(
        status="ok",
        version=settings.VERSION,
        environment=settings.ENVIRONMENT,
        storage_ok=storage_ok,
        db_ok=True,
        storage_usage=get_current_storage_usage(),
    )


# Frontend static files and routes
frontend_dir = settings.BASE_DIR / "frontend"

if frontend_dir.exists():
    app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        return FileResponse(frontend_dir / "index.html")

    @app.get("/library", include_in_schema=False)
    async def serve_library():
        return FileResponse(frontend_dir / "library.html")

    @app.get("/history", include_in_schema=False)
    async def serve_history():
        return FileResponse(frontend_dir / "history.html")

    @app.get("/citations", include_in_schema=False)
    async def serve_citations():
        return FileResponse(frontend_dir / "citations.html")

    @app.get("/settings", include_in_schema=False)
    async def serve_settings():
        return FileResponse(frontend_dir / "settings.html")
