"""Tests for URL, DOI, and paper input detection & classification."""
import pytest
from backend.app.services.filename_generator import (
    clean_title_slug,
    extract_surname,
    generate_paper_filename,
)
from backend.app.utils.security import is_ip_allowed, sanitize_filename
from backend.app.utils.url_validator import (
    classify_input,
    extract_arxiv_id,
    extract_doi,
)


def test_extract_doi():
    assert extract_doi("10.1038/s41586-023-06747-5") == "10.1038/s41586-023-06747-5"
    assert extract_doi("https://doi.org/10.1145/3372278.3390678") == "10.1145/3372278.3390678"
    assert extract_doi("doi:10.1016/j.cell.2021.05.001") == "10.1016/j.cell.2021.05.001"
    assert extract_doi("random string without doi") is None


def test_extract_arxiv_id():
    assert extract_arxiv_id("https://arxiv.org/abs/2301.12345") == "2301.12345"
    assert extract_arxiv_id("https://arxiv.org/pdf/2301.12345.pdf") == "2301.12345"
    assert extract_arxiv_id("arXiv:2106.09685v2") == "2106.09685v2"


def test_classify_input():
    assert classify_input("10.1038/nature1234")[0] == "doi"
    assert classify_input("https://arxiv.org/abs/2301.12345")[0] == "arxiv"
    assert classify_input("https://example.com/papers/paper.pdf")[0] == "direct_pdf"
    assert classify_input("https://nature.com/articles/s41586-023")[0] == "webpage"


def test_extract_surname():
    assert extract_surname("John Smith") == "Smith"
    assert extract_surname("Smith, John") == "Smith"
    assert extract_surname("Alice B. Johnson") == "Johnson"
    assert extract_surname("") == "Unknown"


def test_clean_title_slug():
    slug = clean_title_slug("Machine Learning: Modern Approaches & Algorithms")
    assert slug == "Machine_Learning_Modern_Approaches_Algorithms"


def test_generate_paper_filename():
    fn = generate_paper_filename(
        title="Physics Informed Neural Networks",
        authors=["George Karniadakis"],
        year=2021,
    )
    assert fn == "2021_Karniadakis_Physics_Informed_Neural_Networks.pdf"


def test_ssrf_ip_blocking():
    # Private / loopback / cloud metadata IPs MUST be rejected
    assert is_ip_allowed("127.0.0.1") is False
    assert is_ip_allowed("10.0.0.1") is False
    assert is_ip_allowed("192.168.1.1") is False
    assert is_ip_allowed("172.16.0.5") is False
    assert is_ip_allowed("169.254.169.254") is False  # AWS/GCP metadata
    assert is_ip_allowed("::1") is False

    # Public valid IPs must be allowed
    assert is_ip_allowed("8.8.8.8") is True
    assert is_ip_allowed("1.1.1.1") is True


def test_sanitize_filename():
    bad_name = "../../etc/passwd.pdf"
    clean = sanitize_filename(bad_name)
    assert ".." not in clean
    assert "/" not in clean
    assert clean.endswith(".pdf")
