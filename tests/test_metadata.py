"""Tests for HTML metadata parsing from academic webpages."""
import pytest
from backend.app.services.metadata_extractor import parse_html_metadata


def test_parse_highwire_press_html():
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="citation_title" content="Attention Is All You Need">
      <meta name="citation_author" content="Vaswani, Ashish">
      <meta name="citation_author" content="Shazeer, Noam">
      <meta name="citation_publication_date" content="2017/12/06">
      <meta name="citation_journal_title" content="Advances in Neural Information Processing Systems">
      <meta name="citation_pdf_url" content="https://arxiv.org/pdf/1706.03762.pdf">
      <meta name="citation_doi" content="10.48550/arXiv.1706.03762">
    </head>
    <body>
      <h1>Article Page</h1>
    </body>
    </html>
    """
    data = parse_html_metadata(sample_html, "https://arxiv.org/abs/1706.03762")
    assert data["title"] == "Attention Is All You Need"
    assert "Vaswani, Ashish" in data["authors"]
    assert "Shazeer, Noam" in data["authors"]
    assert data["year"] == 2017
    assert data["journal_or_conference"] == "Advances in Neural Information Processing Systems"
    assert data["pdf_url"] == "https://arxiv.org/pdf/1706.03762.pdf"
    assert data["doi"] == "10.48550/arxiv.1706.03762"


def test_parse_dublin_core_html():
    sample_html = """
    <!DOCTYPE html>
    <html>
    <head>
      <meta name="DC.title" content="A Study of Quantum Superposition">
      <meta name="DC.creator" content="Erwin Schrodinger">
      <meta name="DC.date" content="1935">
      <meta name="DC.identifier" content="10.1007/BF01491891">
    </head>
    <body></body>
    </html>
    """
    data = parse_html_metadata(sample_html, "https://example.com/quantum")
    assert data["title"] == "A Study of Quantum Superposition"
    assert "Erwin Schrodinger" in data["authors"]
    assert data["year"] == 1935
    assert data["doi"] == "10.1007/bf01491891"


def test_parse_pdf_link_fallback():
    sample_html = """
    <html>
    <body>
      <h1>Machine Learning Paper</h1>
      <a href="/downloads/full-article.pdf">Download PDF</a>
    </body>
    </html>
    """
    data = parse_html_metadata(sample_html, "https://example.com/paper/123")
    assert data["pdf_url"] == "https://example.com/downloads/full-article.pdf"
