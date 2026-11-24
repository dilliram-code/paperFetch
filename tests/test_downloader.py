"""Tests for PDF validation and safe local resolution."""
from pathlib import Path
import pytest
from backend.app.services.pdf_validator import is_valid_pdf_bytes, validate_pdf_file
from backend.app.utils.security import safe_resolve_path


def test_is_valid_pdf_bytes():
    assert is_valid_pdf_bytes(b"%PDF-1.4\n") is True
    assert is_valid_pdf_bytes(b"<!DOCTYPE html><html>") is False
    assert is_valid_pdf_bytes(b"random content") is False


def test_safe_resolve_path(tmp_path):
    base = tmp_path / "storage"
    base.mkdir()

    # Normal filename
    res = safe_resolve_path(base, "2024_Smith_Paper.pdf")
    assert res == base / "2024_Smith_Paper.pdf"

    # Directory traversal attempt should be safely stripped to basename
    res2 = safe_resolve_path(base, "../../etc/passwd.pdf")
    assert res2 == base / "passwd.pdf"
    assert str(res2).startswith(str(base))
