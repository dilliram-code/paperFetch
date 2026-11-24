"""PaperFetch Application Configuration."""
from pathlib import Path
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    PROJECT_NAME: str = "PaperFetch"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    CORS_ORIGINS: List[str] = ["*"]

    # Storage Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage" / "downloads"
    TEMP_DIR: Path = BASE_DIR / "storage" / "temp"
    DATABASE_PATH: Path = BASE_DIR / "storage" / "paperfetch.db"
    DATABASE_URL: str = f"sqlite+aiosqlite:///{DATABASE_PATH}"

    # Academic API Keys & Credentials
    UNPAYWALL_EMAIL: Optional[str] = "researcher@paperfetch.app"
    CROSSREF_MAILTO: Optional[str] = "researcher@paperfetch.app"
    SEMANTIC_SCHOLAR_API_KEY: Optional[str] = None
    OPENALEX_EMAIL: Optional[str] = "researcher@paperfetch.app"

    # Engine Limits
    MAX_BATCH_SIZE: int = 10
    MAX_CONCURRENT_DOWNLOADS: int = 10
    DOWNLOAD_TIMEOUT_SECONDS: int = 60
    MAX_FILE_SIZE_MB: int = 200
    CHUNK_SIZE_BYTES: int = 262144  # 256 KB high-speed streaming buffer

    # Render Free Tier Storage Quota & Auto-Flush
    MAX_STORAGE_MB: int = 500  # Cap storage at 500 MB for Render Free Tier
    AUTO_FLUSH_INTERVAL_MINUTES: int = 30  # Run periodic flush every 30 minutes
    STORAGE_RETENTION_HOURS: int = 24  # Flush files older than 24 hours if storage is near cap
    AUTO_CLEANUP_ENABLED: bool = True  # Enable automatic background cleanup

    # Default Preferences
    DEFAULT_FILENAME_PATTERN: str = "{year}_{first_author}_{title}"
    DUPLICATE_ACTION: str = "warn"  # "warn", "skip", "overwrite"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def setup_directories(self) -> None:
        """Ensure all storage directories exist."""
        self.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.TEMP_DIR.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.setup_directories()
