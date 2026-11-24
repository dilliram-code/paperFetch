"""Pydantic schemas for request validation and response serialization."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator


class DetectRequest(BaseModel):
    inputs: List[str] = Field(..., max_length=10, description="List of up to 10 URLs or DOIs")

    @field_validator("inputs")
    @classmethod
    def validate_inputs(cls, v: List[str]) -> List[str]:
        cleaned = [item.strip() for item in v if item and item.strip()]
        if not cleaned:
            raise ValueError("At least one valid URL or DOI must be provided.")
        if len(cleaned) > 10:
            raise ValueError("Maximum 10 items allowed per batch.")
        return cleaned


class DuplicateInfo(BaseModel):
    is_duplicate: bool = False
    match_type: Optional[str] = None  # "doi", "file_hash", "title_author"
    existing_paper_id: Optional[str] = None
    existing_title: Optional[str] = None
    message: Optional[str] = None


class PaperBase(BaseModel):
    title: str = "Untitled Paper"
    authors: List[str] = []
    first_author: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal_or_conference: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    abstract: Optional[str] = None
    issn: Optional[str] = None
    original_url: Optional[str] = None
    pdf_url: Optional[str] = None
    access_type: str = "unknown"
    metadata_source: Optional[str] = None


class PaperUpdate(BaseModel):
    title: Optional[str] = None
    authors: Optional[List[str]] = None
    first_author: Optional[str] = None
    year: Optional[int] = None
    doi: Optional[str] = None
    journal_or_conference: Optional[str] = None
    publisher: Optional[str] = None
    volume: Optional[str] = None
    issue: Optional[str] = None
    pages: Optional[str] = None
    abstract: Optional[str] = None
    pdf_url: Optional[str] = None


class PaperDetectionResponse(PaperBase):
    id: str
    filename: Optional[str] = None
    pdf_accessible: bool = False
    duplicate_info: DuplicateInfo = Field(default_factory=DuplicateInfo)
    status: str = "detected"
    bibtex: Optional[str] = None
    error: Optional[str] = None


class DetectBatchResponse(BaseModel):
    papers: List[PaperDetectionResponse]
    total: int
    accessible_count: int
    duplicate_count: int


class PaperResponse(PaperBase):
    id: str
    filename: Optional[str] = None
    local_path: Optional[str] = None
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = 0
    page_count: Optional[int] = None
    status: str
    error_message: Optional[str] = None
    bibtex: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DownloadJobsCreateRequest(BaseModel):
    paper_ids: List[str] = Field(..., max_length=10)
    force_download: bool = False  # Download even if duplicate


class JobResponse(BaseModel):
    id: str
    paper_id: Optional[str] = None
    status: str
    progress_percent: float
    downloaded_bytes: int
    total_bytes: int
    speed_bytes_per_sec: float
    eta_seconds: float
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    paper: Optional[PaperResponse] = None


class BibtexExportRequest(BaseModel):
    paper_ids: List[str] = Field(..., description="List of paper IDs to export as BibTeX")


class SettingsResponse(BaseModel):
    filename_pattern: str
    max_concurrent_downloads: int
    unpaywall_email: Optional[str]
    crossref_mailto: Optional[str]
    duplicate_action: str
    theme: str = "dark"


class SettingsUpdate(BaseModel):
    filename_pattern: Optional[str] = None
    max_concurrent_downloads: Optional[int] = Field(None, ge=1, le=10)
    unpaywall_email: Optional[str] = None
    crossref_mailto: Optional[str] = None
    duplicate_action: Optional[str] = None
    theme: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
    environment: str
    storage_ok: bool
    db_ok: bool
