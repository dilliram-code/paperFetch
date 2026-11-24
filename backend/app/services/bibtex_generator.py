"""BibTeX citation generation and formatting service."""
import re
from typing import Any, Dict, List, Optional
from backend.app.services.filename_generator import extract_surname

STOP_WORDS = {"a", "an", "the", "and", "or", "in", "on", "at", "to", "for", "of", "with", "by", "is", "are"}


def escape_latex(text: Optional[str]) -> str:
    """Escape special LaTeX characters in BibTeX values."""
    if not text:
        return ""
    # Map special characters to escaped LaTeX sequences
    text = str(text)
    # Order matters: escape backslash first if needed, but in standard BibTeX strings:
    text = text.replace("\\", "\\textbackslash{}")
    text = text.replace("&", r"\&")
    text = text.replace("%", r"\%")
    text = text.replace("$", r"\$")
    text = text.replace("#", r"\#")
    text = text.replace("_", r"\_")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    text = text.replace("~", r"\textasciitilde{}")
    text = text.replace("^", r"\textasciicircum{}")
    return text


def generate_citation_key(
    first_author: Optional[str] = None,
    year: Optional[int] = None,
    title: Optional[str] = None,
) -> str:
    """Generate clean citation key like 'smith2024machine'."""
    author_part = "paper"
    if first_author:
        surname = extract_surname(first_author).lower()
        if surname and surname != "unknown":
            author_part = re.sub(r"[^a-z0-9]", "", surname)

    year_part = str(year) if year else "nodate"

    title_part = ""
    if title:
        words = re.findall(r"[a-zA-Z0-9]+", title.lower())
        for w in words:
            if w not in STOP_WORDS and len(w) > 2:
                title_part = w
                break
        if not title_part and words:
            title_part = words[0]

    return f"{author_part}{year_part}{title_part}"


def generate_bibtex_entry(paper_data: Dict[str, Any]) -> str:
    """
    Generate standard BibTeX entry for a paper dict/model.
    Omit missing fields rather than inventing placeholders.
    """
    title = paper_data.get("title")
    authors = paper_data.get("authors") or []
    first_author = paper_data.get("first_author") or (authors[0] if authors else None)
    year = paper_data.get("year")
    doi = paper_data.get("doi")
    journal = paper_data.get("journal_or_conference")
    publisher = paper_data.get("publisher")
    volume = paper_data.get("volume")
    issue = paper_data.get("issue")
    pages = paper_data.get("pages")
    url = paper_data.get("original_url") or paper_data.get("pdf_url")

    # Determine entry type
    entry_type = "article"
    if journal and any(k in journal.lower() for k in ("conference", "proceedings", "symposium", "workshop", "ieee", "acm")):
        entry_type = "inproceedings"
    elif not journal and doi and "arxiv" in str(doi).lower():
        entry_type = "article"
    elif not journal:
        entry_type = "misc"

    cite_key = generate_citation_key(first_author, year, title)

    lines = [f"@{entry_type}{{{cite_key},"]

    if title:
        lines.append(f"  title = {{{escape_latex(title)}}},")

    if authors:
        # BibTeX author format: "Author One and Author Two and Author Three"
        author_str = " and ".join(escape_latex(a) for a in authors if a)
        lines.append(f"  author = {{{author_str}}},")

    if entry_type == "article" and journal:
        lines.append(f"  journal = {{{escape_latex(journal)}}},")
    elif entry_type == "inproceedings" and journal:
        lines.append(f"  booktitle = {{{escape_latex(journal)}}},")

    if year:
        lines.append(f"  year = {{{year}}},")

    if volume:
        lines.append(f"  volume = {{{escape_latex(volume)}}},")

    if issue:
        lines.append(f"  number = {{{escape_latex(issue)}}},")

    if pages:
        lines.append(f"  pages = {{{escape_latex(pages)}}},")

    if publisher:
        lines.append(f"  publisher = {{{escape_latex(publisher)}}},")

    if doi:
        lines.append(f"  doi = {{{doi}}},")

    if url and not doi:
        lines.append(f"  url = {{{url}}},")

    # Remove trailing comma on last line if any, or BibTeX standard permits trailing comma
    lines.append("}")

    return "\n".join(lines)


def combine_bibtex_entries(entries: List[str]) -> str:
    """Combine multiple BibTeX entries into a single file string separated by blank lines."""
    valid_entries = [e.strip() for e in entries if e and e.strip()]
    return "\n\n".join(valid_entries) + ("\n" if valid_entries else "")
