# PaperFetch V2 — Intelligent Research Paper Downloader & Library Manager

PaperFetch V2 is an intelligent academic research productivity web application built with **FastAPI**, **Vanilla Modern JavaScript (ES6+)**, and **Server-Sent Events (SSE)**. It discovers, validates, downloads, organizes, and manages academic research papers in PDF format.

Researchers can paste direct PDF URLs, DOIs, arXiv links, or academic publisher webpages. The system validates sources, extracts complete bibliographic metadata via official academic APIs (Crossref, OpenAlex, Unpaywall, arXiv) and HTML meta tags, checks PDF accessibility, performs multi-tier duplicate detection, previews metadata for editing, and streams concurrent downloads (up to 10 papers) with real-time progress.

---

## Key Features

1. **Intelligent Paper & PDF Discovery**:
   - Direct PDF URLs: Header sniffing, magic byte (`%PDF-`) detection, and PyMuPDF structural validation.
   - DOI Resolution: Automatic resolution through Crossref, OpenAlex, and Unpaywall.
   - Academic Webpages: BeautifulSoup extraction of Highwire Press (`citation_*`), Dublin Core (`DC.*`), OpenGraph, JSON-LD (`ScholarlyArticle`), and heuristic PDF download links.
   - arXiv Integration: Direct mapping of abs/pdf URLs and arXiv export API integration.

2. **Metadata Preview & Editing**:
   - Preview cards showing title, full author list, publication year, DOI, venue, and publisher.
   - Distinction between accessible PDFs, paywalled articles, and duplicate entries.
   - In-app modal for manual metadata corrections before or after download.

3. **High-Speed Asynchronous Downloader**:
   - Up to 10 concurrent streaming downloads managed via `asyncio.Semaphore`.
   - Chunk-based writing (64 KB) with memory efficiency.
   - Resumable downloads via HTTP `Range` headers.
   - Exponential backoff retries for unstable connections.
   - Real-time progress broadcasting via Server-Sent Events (SSE) reporting actual bytes, speed, and ETA.

4. **Standardized Academic Filename System**:
   - Automatically names files using: `Year_FirstAuthor_ShortTitle.pdf` (e.g. `2024_Smith_Machine_Learning_for_Physics.pdf`).
   - Removes illegal characters, handles duplicate filenames, and provides safe fallbacks.

5. **Multi-Tier Duplicate Detection**:
   - Exact DOI matching (case-insensitive normalization).
   - Exact file hash matching (SHA-256).
   - Fuzzy metadata similarity matching (normalized title & author surname).
   - Checks both current batch and persistent library history.

6. **BibTeX Citation Studio**:
   - Automatic standard BibTeX generation (`@article`, `@inproceedings`, `@misc`).
   - Special LaTeX character escaping (`&`, `%`, `$`, `#`, `_`, `{`, `}`, `~`, `^`).
   - Copy to clipboard, single `.bib` download, or batch-combined `.bib` export.

7. **Persistent Research Library & History**:
   - SQLite persistence via SQLAlchemy 2.0 and aiosqlite.
   - Full search by title, author, DOI, or journal.
   - Filtering by publication year and venue.
   - Safe deletion removing database records and deleting physical PDFs from disk.
   - Bulk ZIP archive download for completed papers.

8. **Hardened Security & SSRF Protection**:
   - Strict IP validation blocking loopback, private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local, carrier NAT, and cloud metadata (`169.254.169.254`, `metadata.google.internal`).
   - Re-validates resolved DNS addresses for every redirect.
   - Restricts protocols strictly to `http` and `https`.
   - Path traversal prevention on all file operations.

---

## Project Structure

```
paperFetch/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI application & route mounting
│   │   ├── config.py               # Pydantic application settings
│   │   ├── database.py             # SQLAlchemy 2.0 async engine & session
│   │   ├── models.py               # Database models (Paper, DownloadJob, AppSetting)
│   │   ├── schemas.py              # Pydantic schemas
│   │   ├── api/
│   │   │   ├── papers.py           # Detection, preview & metadata endpoints
│   │   │   ├── downloads.py        # Job management, SSE stream & ZIP export
│   │   │   ├── library.py          # Research library & history
│   │   │   ├── citations.py        # BibTeX citations
│   │   │   └── settings_api.py     # Configuration API
│   │   ├── services/
│   │   │   ├── paper_detector.py   # High-level paper detection
│   │   │   ├── doi_resolver.py     # Crossref, OpenAlex & Unpaywall aggregator
│   │   │   ├── metadata_extractor.py # HTML meta & JSON-LD parser
│   │   │   ├── academic_sources.py # Academic API connectors
│   │   │   ├── pdf_validator.py    # PyMuPDF integrity verification
│   │   │   ├── downloader.py       # Asynchronous streaming downloader
│   │   │   ├── job_manager.py      # Concurrency & SSE broadcasting
│   │   │   ├── duplicate_detector.py # DOI, SHA-256 & title matching
│   │   │   ├── filename_generator.py # Year_Author_Title naming
│   │   │   ├── bibtex_generator.py # BibTeX formatting & escaping
│   │   │   ├── library_manager.py  # Library queries & disk file deletion
│   │   │   └── zip_service.py      # Batch ZIP creation
│   │   └── utils/
│   │       ├── security.py         # SSRF guards & path traversal validation
│   │       └── url_validator.py    # URL/DOI pattern classifiers
│   └── requirements.txt
├── frontend/
│   ├── index.html                  # Main workspace & downloader
│   ├── library.html                # Searchable research library
│   ├── history.html                # Download history & audit log
│   ├── citations.html              # BibTeX citation studio
│   ├── settings.html               # Engine preferences
│   ├── css/
│   │   ├── style.css               # Design system & glassmorphism
│   │   ├── dashboard.css           # Cards, progress bars & tables
│   │   └── responsive.css          # Mobile layouts (360px - 1440px)
│   └── js/
│       ├── api.js                  # Central API client
│       ├── app.js                  # Utilities & navigation
│       ├── detector.js             # Detection & preview cards
│       ├── progress.js             # SSE real-time download dashboard
│       ├── library.js              # Library table & deletion
│       └── citations.js            # BibTeX viewer & export
├── storage/
│   ├── downloads/                  # Downloaded PDFs
│   └── temp/                       # Temporary ZIP bundles
├── tests/                          # Pytest test suite
├── render.yaml                     # Render deployment configuration
├── vercel.json                     # Vercel deployment configuration
└── README.md
```

---

## Getting Started

### Prerequisites
- Python 3.11+
- Virtual environment tool (`venv` or `uv`)

### Installation & Local Run

1. **Clone the repository**:
   ```bash
   git clone https://github.com/dilliram-code/paperFetch.git
   cd paperFetch
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Run the FastAPI development server**:
   ```bash
   uvicorn backend.app.main:app --reload --port 8000
   ```

5. **Open in browser**:
   Navigate to [http://localhost:8000](http://localhost:8000)

---

## Running Tests

Run the test suite using `pytest`:
```bash
pytest -v
```

Tests cover:
- URL, DOI, and arXiv detection
- Highwire Press & Dublin Core HTML metadata extraction
- Standard academic filename generation
- Duplicate DOI, SHA-256, and metadata matching
- BibTeX syntax and LaTeX character escaping
- SSRF and private IP blocking
- FastAPI REST endpoints and validation

---

## Deployment

### Render (Single Service Deployment)
The repository includes a ready `render.yaml` blueprint with persistent disk storage for downloaded papers:
1. Connect your GitHub repository to Render.
2. Select "New > Blueprint" and choose this repository.
3. Render automatically provisions the web service and attaches persistent disk storage at `/opt/render/project/src/storage`.

### Vercel (Frontend Deployment)
A `vercel.json` is provided to host the frontend on Vercel and route API calls to your hosted backend.

---

## License
MIT License. Built for researchers and academic productivity.
