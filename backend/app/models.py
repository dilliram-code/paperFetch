"""SQLAlchemy models for PaperFetch."""
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from backend.app.database import Base


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String(500), nullable=False, default="Untitled Paper")
    authors_json = Column(Text, nullable=False, default="[]")
    first_author = Column(String(150), nullable=True)
    year = Column(Integer, nullable=True, index=True)
    doi = Column(String(200), nullable=True, index=True)
    journal_or_conference = Column(String(300), nullable=True)
    publisher = Column(String(200), nullable=True)
    volume = Column(String(50), nullable=True)
    issue = Column(String(50), nullable=True)
    pages = Column(String(50), nullable=True)
    abstract = Column(Text, nullable=True)
    issn = Column(String(100), nullable=True)
    original_url = Column(String(1000), nullable=True)
    pdf_url = Column(String(1000), nullable=True)
    access_type = Column(String(50), default="unknown")  # open_access, restricted, unknown
    
    filename = Column(String(300), nullable=True)
    local_path = Column(String(500), nullable=True)
    file_hash = Column(String(64), nullable=True, index=True)  # SHA-256
    file_size_bytes = Column(BigInteger, nullable=True, default=0)
    page_count = Column(Integer, nullable=True)
    
    status = Column(String(50), default="detected")
    # detected, awaiting_confirmation, downloading, completed, failed, cancelled, duplicate
    error_message = Column(Text, nullable=True)
    bibtex = Column(Text, nullable=True)
    metadata_source = Column(String(100), nullable=True)  # crossref, openalex, unpaywall, arxiv, webpage_html, pdf_metadata, manual
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    jobs = relationship("DownloadJob", back_populates="paper", cascade="all, delete-orphan")

    @property
    def authors(self) -> List[str]:
        try:
            return json.loads(self.authors_json) if self.authors_json else []
        except Exception:
            return []

    @authors.setter
    def authors(self, value: List[str]) -> None:
        if isinstance(value, list):
            self.authors_json = json.dumps(value)
            if value and not self.first_author:
                # Extract first author surname if possible
                first = value[0].strip()
                self.first_author = first.split()[-1] if first else "Unknown"
        else:
            self.authors_json = "[]"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "authors": self.authors,
            "first_author": self.first_author,
            "year": self.year,
            "doi": self.doi,
            "journal_or_conference": self.journal_or_conference,
            "publisher": self.publisher,
            "volume": self.volume,
            "issue": self.issue,
            "pages": self.pages,
            "abstract": self.abstract,
            "issn": self.issn,
            "original_url": self.original_url,
            "pdf_url": self.pdf_url,
            "access_type": self.access_type,
            "filename": self.filename,
            "local_path": self.local_path,
            "file_hash": self.file_hash,
            "file_size_bytes": self.file_size_bytes,
            "page_count": self.page_count,
            "status": self.status,
            "error_message": self.error_message,
            "bibtex": self.bibtex,
            "metadata_source": self.metadata_source,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DownloadJob(Base):
    __tablename__ = "download_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    paper_id = Column(String(36), ForeignKey("papers.id", ondelete="CASCADE"), nullable=True, index=True)
    status = Column(String(50), default="waiting")
    # waiting, detecting, extracting_metadata, searching_pdf, awaiting_confirmation, downloading, paused, resuming, validating, completed, duplicate, failed, cancelled
    
    progress_percent = Column(Float, default=0.0)
    downloaded_bytes = Column(BigInteger, default=0)
    total_bytes = Column(BigInteger, default=0)
    speed_bytes_per_sec = Column(Float, default=0.0)
    eta_seconds = Column(Float, default=0.0)
    
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)

    paper = relationship("Paper", back_populates="jobs")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "paper_id": self.paper_id,
            "status": self.status,
            "progress_percent": round(self.progress_percent, 2) if self.progress_percent is not None else 0.0,
            "downloaded_bytes": self.downloaded_bytes if self.downloaded_bytes is not None else 0,
            "total_bytes": self.total_bytes if self.total_bytes is not None else 0,
            "speed_bytes_per_sec": round(self.speed_bytes_per_sec, 2) if self.speed_bytes_per_sec is not None else 0.0,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else 0.0,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String(100), primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
