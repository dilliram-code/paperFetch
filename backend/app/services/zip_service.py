"""ZIP bundling service for bulk downloading papers."""
import asyncio
import os
from pathlib import Path
from typing import List, Optional
import uuid
import zipfile

from backend.app.config import settings
from backend.app.models import Paper


def create_papers_zip(papers: List[Paper], zip_filename: Optional[str] = None) -> Optional[Path]:
    """
    Bundle multiple paper PDFs into a zip archive stored in TEMP_DIR.
    Returns the path to the created zip file.
    """
    if not papers:
        return None

    settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    if not zip_filename:
        zip_filename = f"paperfetch_batch_{uuid.uuid4().hex[:8]}.zip"

    zip_path = settings.TEMP_DIR / zip_filename

    valid_files_added = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for paper in papers:
            if paper.local_path:
                src_file = Path(paper.local_path)
                if src_file.exists():
                    arcname = paper.filename or src_file.name
                    zf.write(src_file, arcname=arcname)
                    valid_files_added += 1

    if valid_files_added == 0:
        if zip_path.exists():
            zip_path.unlink()
        return None

    return zip_path
