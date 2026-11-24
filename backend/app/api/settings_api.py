"""Application settings and user preferences API."""
import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import settings
from backend.app.database import get_db
from backend.app.models import AppSetting
from backend.app.schemas import SettingsResponse, SettingsUpdate
from backend.app.services.job_manager import job_manager
from backend.app.services.storage_cleaner import flush_storage_if_needed, get_current_storage_usage

router = APIRouter(prefix="/api/settings", tags=["Settings"])


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    """Retrieve active user configuration."""
    res = await db.execute(select(AppSetting))
    settings_rows = {row.key: row.value for row in res.scalars().all()}

    return SettingsResponse(
        filename_pattern=settings_rows.get("filename_pattern", settings.DEFAULT_FILENAME_PATTERN),
        max_concurrent_downloads=int(
            settings_rows.get("max_concurrent_downloads", str(settings.MAX_CONCURRENT_DOWNLOADS))
        ),
        unpaywall_email=settings_rows.get("unpaywall_email", settings.UNPAYWALL_EMAIL),
        crossref_mailto=settings_rows.get("crossref_mailto", settings.CROSSREF_MAILTO),
        duplicate_action=settings_rows.get("duplicate_action", settings.DUPLICATE_ACTION),
        theme=settings_rows.get("theme", "dark"),
    )


@router.patch("", response_model=SettingsResponse)
async def update_settings(update_data: SettingsUpdate, db: AsyncSession = Depends(get_db)):
    """Update user configuration and apply engine changes."""
    updates = update_data.model_dump(exclude_unset=True)

    for k, v in updates.items():
        if v is not None:
            res = await db.execute(select(AppSetting).where(AppSetting.key == k))
            setting_obj = res.scalars().first()
            if not setting_obj:
                setting_obj = AppSetting(key=k, value=str(v))
                db.add(setting_obj)
            else:
                setting_obj.value = str(v)

            # Apply runtime engine changes if concurrency updated
            if k == "max_concurrent_downloads":
                job_manager.set_max_concurrency(int(v))
            elif k == "unpaywall_email":
                settings.UNPAYWALL_EMAIL = str(v)
            elif k == "crossref_mailto":
                settings.CROSSREF_MAILTO = str(v)

    await db.commit()
    return await get_settings(db)


@router.get("/storage-stats")
async def get_storage_stats():
    """Get real-time storage disk usage statistics."""
    return get_current_storage_usage()


@router.post("/flush-storage")
async def trigger_storage_flush():
    """Manually trigger storage cleanup and return updated usage statistics."""
    return await flush_storage_if_needed(force_flush=True)

