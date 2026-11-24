"""Tests for BibTeX generation and formatting."""
import pytest
from backend.app.services.bibtex_generator import (
    combine_bibtex_entries,
    escape_latex,
    generate_bibtex_entry,
    generate_citation_key,
)


def test_escape_latex():
    raw = "Analysis of 100% of & and $ and _ and {testing} with ~ and ^"
    escaped = escape_latex(raw)
    assert r"\%" in escaped
    assert r"\&" in escaped
    assert r"\$" in escaped
    assert r"\_" in escaped
    assert r"\{" in escaped
    assert r"\}" in escaped
    assert r"\textasciitilde{}" in escaped
    assert r"\textasciicircum{}" in escaped


def test_generate_citation_key():
    key = generate_citation_key(first_author="Alice Smith", year=2024, title="Machine Learning for Physics")
    assert key == "smith2024machine"

    key2 = generate_citation_key(first_author="Brown, Bob", year=2023, title="The Quantum Algorithm")
    assert key2 == "brown2023quantum"


def test_generate_bibtex_article():
    paper = {
        "title": "Machine Learning for Scientific Discovery",
        "authors": ["John Smith", "Alice Brown"],
        "first_author": "John Smith",
        "year": 2024,
        "journal_or_conference": "Journal of Computational Physics",
        "publisher": "Elsevier",
        "volume": "123",
        "issue": "2",
        "pages": "100--120",
        "doi": "10.1016/j.jcp.2024.12345",
    }
    entry = generate_bibtex_entry(paper)
    assert "@article{smith2024machine," in entry
    assert "title = {Machine Learning for Scientific Discovery}," in entry
    assert "author = {John Smith and Alice Brown}," in entry
    assert "journal = {Journal of Computational Physics}," in entry
    assert "year = {2024}," in entry
    assert "doi = {10.1016/j.jcp.2024.12345}," in entry


def test_generate_bibtex_missing_fields():
    paper = {
        "title": "Minimal Paper Title",
        "authors": ["Jane Doe"],
        "year": None,
    }
    entry = generate_bibtex_entry(paper)
    assert "@misc{doe" in entry
    assert "year =" not in entry
    assert "doi =" not in entry


def test_combine_bibtex_entries():
    e1 = "@article{one, title={Paper One}}"
    e2 = "@article{two, title={Paper Two}}"
    combined = combine_bibtex_entries([e1, e2])
    assert "@article{one" in combined
    assert "@article{two" in combined
    assert "\n\n" in combined
