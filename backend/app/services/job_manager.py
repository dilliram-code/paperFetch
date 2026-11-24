"""Job Manager coordinating concurrent downloads, SSE broadcasting, and job states."""
import asyncio
from datetime import datetime
import json
import logging
import uuid
from typing import AsyncGenerator, Dict, List, Optional, Set
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import AsyncSessionLocal
from backend.app.models import DownloadJob, Paper
from backend.app.services.downloader import download_pdf_stream
from backend.app.services.filename_generator import generate_paper_filename

logger = logging.getLogger(__name__)


class JobManager:
    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_DOWNLOADS)
        self._active_tasks: Dict[str, asyncio.Task] = {}
        self._cancel_events: Dict[str, asyncio.Event] = {}
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._global_subscribers: Set[asyncio.Queue] = set()
        self._cached_jobs: Dict[str, Dict] = {}

    def set_max_concurrency(self, concurrency: int) -> None:
        """Update concurrency semaphore limit."""
        if 1 <= concurrency <= 10:
            self._semaphore = asyncio.Semaphore(concurrency)

    async def broadcast_update(self, job_dict: Dict) -> None:
        """Send job update to active SSE listener queues."""
        job_id = job_dict.get("id")
        self._cached_jobs[job_id] = job_dict
        message = json.dumps(job_dict)

        # Notify specific job subscribers
        if job_id in self._subscribers:
            for q in list(self._subscribers[job_id]):
                try:
                    q.put_nowait(message)
                except Exception:
                    pass

        # Notify global subscribers
        for q in list(self._global_subscribers):
            try:
                q.put_nowait(message)
            except Exception:
                pass

    async def subscribe(self, job_id: Optional[str] = None) -> AsyncGenerator[str, None]:
        """Subscribe to real-time SSE stream of download progress."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        if job_id:
            if job_id not in self._subscribers:
                self._subscribers[job_id] = set()
            self._subscribers[job_id].add(queue)
            # Send current state immediately if cached
            if job_id in self._cached_jobs:
                await queue.put(json.dumps(self._cached_jobs[job_id]))
        else:
            self._global_subscribers.add(queue)
            # Send all active jobs initially
            for j in self._cached_jobs.values():
                await queue.put(json.dumps(j))

        try:
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            pass
        finally:
            if job_id and job_id in self._subscribers:
                self._subscribers[job_id].discard(queue)
            else:
                self._global_subscribers.discard(queue)

    async def run_download_task(self, job_id: str, paper_id: str) -> None:
        """Worker task executing under concurrency semaphore."""
        cancel_event = self._cancel_events.get(job_id)

        async with self._semaphore:
            if cancel_event and cancel_event.is_set():
                return

            async with AsyncSessionLocal() as db:
                # Fetch paper details
                res = await db.execute(select(Paper).where(Paper.id == paper_id))
                paper = res.scalars().first()
                if not paper or not paper.pdf_url:
                    await self._fail_job(job_id, paper_id, "No accessible PDF URL found")
                    return

                # Ensure filename is properly generated
                if not paper.filename:
                    paper.filename = generate_paper_filename(
                        title=paper.title,
                        authors=paper.authors,
                        year=paper.year,
                        doi=paper.doi,
                        destination_dir=settings.STORAGE_DIR,
                    )
                    await db.commit()

                # Update job to downloading
                started_at = datetime.utcnow()
                await db.execute(
                    update(DownloadJob)
                    .where(DownloadJob.id == job_id)
                    .values(status="downloading", started_at=started_at)
                )
                await db.execute(
                    update(Paper).where(Paper.id == paper_id).values(status="downloading")
                )
                await db.commit()

                job_info = {
                    "id": job_id,
                    "paper_id": paper_id,
                    "title": paper.title,
                    "filename": paper.filename,
                    "status": "downloading",
                    "progress_percent": 0.0,
                    "downloaded_bytes": 0,
                    "total_bytes": 0,
                    "speed_bytes_per_sec": 0.0,
                    "eta_seconds": 0.0,
                }
                await self.broadcast_update(job_info)

            # Define callback for download progress
            def on_progress(downloaded: int, total: int, speed: float, eta: float) -> None:
                percent = (downloaded / total * 100) if total > 0 else 0.0
                job_info.update({
                    "progress_percent": round(percent, 2),
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed_bytes_per_sec": round(speed, 2),
                    "eta_seconds": round(eta, 1),
                })
                # Broadcast non-blocking
                asyncio.create_task(self.broadcast_update(job_info))

            # Run actual streaming download
            success, err, final_path, file_hash, file_size, page_count = await download_pdf_stream(
                url=paper.pdf_url,
                target_filename=paper.filename,
                progress_callback=on_progress,
                cancel_event=cancel_event,
            )

            # If primary download failed (e.g. 403 or HTML), attempt open-access mirror fallback
            if not success and not (cancel_event and cancel_event.is_set()):
                from backend.app.services.doi_resolver import resolve_doi
                from backend.app.services.academic_sources import search_paper_by_title

                alt_url = None
                if paper.doi:
                    doi_res = await resolve_doi(paper.doi)
                    if doi_res and doi_res.get("pdf_url") and doi_res["pdf_url"] != paper.pdf_url:
                        alt_url = doi_res["pdf_url"]

                if not alt_url and paper.title:
                    title_res = await search_paper_by_title(paper.title)
                    if title_res and title_res.get("pdf_url") and title_res["pdf_url"] != paper.pdf_url:
                        alt_url = title_res["pdf_url"]

                if alt_url:
                    logger.info(f"Primary download failed ({err}). Retrying with open-access mirror: {alt_url}")
                    success, err, final_path, file_hash, file_size, page_count = await download_pdf_stream(
                        url=alt_url,
                        target_filename=paper.filename,
                        progress_callback=on_progress,
                        cancel_event=cancel_event,
                    )
                    if success:
                        async with AsyncSessionLocal() as update_db:
                            await update_db.execute(
                                update(Paper).where(Paper.id == paper_id).values(pdf_url=alt_url)
                            )
                            await update_db.commit()

            async with AsyncSessionLocal() as db:
                if success and final_path:
                    completed_at = datetime.utcnow()
                    await db.execute(
                        update(DownloadJob)
                        .where(DownloadJob.id == job_id)
                        .values(
                            status="completed",
                            progress_percent=100.0,
                            downloaded_bytes=file_size,
                            total_bytes=file_size,
                            completed_at=completed_at,
                        )
                    )
                    await db.execute(
                        update(Paper)
                        .where(Paper.id == paper_id)
                        .values(
                            status="completed",
                            local_path=str(final_path),
                            file_hash=file_hash,
                            file_size_bytes=file_size,
                            page_count=page_count,
                            updated_at=completed_at,
                        )
                    )
                    await db.commit()

                    job_info.update({
                        "status": "completed",
                        "progress_percent": 100.0,
                        "downloaded_bytes": file_size,
                        "total_bytes": file_size,
                        "completed_at": completed_at.isoformat(),
                    })
                    await self.broadcast_update(job_info)
                elif cancel_event and cancel_event.is_set():
                    await self._cancel_job_db(job_id, paper_id)
                else:
                    await self._fail_job(job_id, paper_id, err or "Unknown download failure")

        # Cleanup active task references
        self._active_tasks.pop(job_id, None)
        self._cancel_events.pop(job_id, None)

    async def _fail_job(self, job_id: str, paper_id: str, error_msg: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(DownloadJob)
                .where(DownloadJob.id == job_id)
                .values(status="failed", error_message=error_msg)
            )
            await db.execute(
                update(Paper)
                .where(Paper.id == paper_id)
                .values(status="failed", error_message=error_msg)
            )
            await db.commit()

        job_info = {
            "id": job_id,
            "paper_id": paper_id,
            "status": "failed",
            "error_message": error_msg,
            "progress_percent": 0.0,
        }
        await self.broadcast_update(job_info)

    async def _cancel_job_db(self, job_id: str, paper_id: str) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(DownloadJob)
                .where(DownloadJob.id == job_id)
                .values(status="cancelled", error_message="Cancelled by user")
            )
            await db.execute(
                update(Paper)
                .where(Paper.id == paper_id)
                .values(status="cancelled", error_message="Cancelled by user")
            )
            await db.commit()

        job_info = {
            "id": job_id,
            "paper_id": paper_id,
            "status": "cancelled",
            "progress_percent": 0.0,
        }
        await self.broadcast_update(job_info)

    async def create_download_jobs(
        self, paper_ids: List[str], db: AsyncSession, force_download: bool = False
    ) -> List[Dict]:
        """Create and schedule download jobs concurrently for specified paper IDs."""
        jobs_created = []
        limited_ids = paper_ids[: settings.MAX_BATCH_SIZE]

        # Fetch all requested papers in a single query
        res = await db.execute(select(Paper).where(Paper.id.in_(limited_ids)))
        papers_map = {p.id: p for p in res.scalars().all()}

        tasks_to_spawn = []
        for paper_id in limited_ids:
            paper = papers_map.get(paper_id)
            if not paper:
                continue

            job_id = str(uuid.uuid4())
            cancel_event = asyncio.Event()
            self._cancel_events[job_id] = cancel_event

            new_job = DownloadJob(
                id=job_id,
                paper_id=paper.id,
                status="waiting",
                progress_percent=0.0,
                downloaded_bytes=0,
                total_bytes=0,
                speed_bytes_per_sec=0.0,
                eta_seconds=0.0,
            )
            db.add(new_job)

            job_dict = new_job.to_dict()
            job_dict["title"] = paper.title
            job_dict["filename"] = paper.filename
            jobs_created.append(job_dict)
            tasks_to_spawn.append((job_id, paper.id))

        if jobs_created:
            await db.commit()
            for job_id, pid in tasks_to_spawn:
                task = asyncio.create_task(self.run_download_task(job_id, pid))
                self._active_tasks[job_id] = task

        return jobs_created

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a single active job."""
        if job_id in self._cancel_events:
            self._cancel_events[job_id].set()
        if job_id in self._active_tasks:
            self._active_tasks[job_id].cancel()
            return True
        return False

    def cancel_all_jobs(self) -> int:
        """Cancel all running jobs."""
        count = 0
        for job_id, event in self._cancel_events.items():
            event.set()
        for job_id, task in list(self._active_tasks.items()):
            task.cancel()
            count += 1
        return count


job_manager = JobManager()
