"""Tests for duplicate paper detection logic."""
import pytest
from backend.app.services.duplicate_detector import (
    check_batch_duplicates,
    normalize_title,
    titles_are_similar,
)


def test_normalize_title():
    t1 = "Machine Learning for Physics: A Comprehensive Survey!"
    assert normalize_title(t1) == "machine learning for physics a comprehensive survey"


def test_titles_are_similar():
    t1 = "Deep Learning Methods for Medical Image Segmentation"
    t2 = "Deep Learning Methods for Medical Image Segmentation."
    assert titles_are_similar(t1, t2) is True

    t3 = "Completely Different Physics Topic"
    assert titles_are_similar(t1, t3) is False


def test_batch_duplicate_doi_detection():
    batch = [
        {"id": "1", "title": "Paper One", "doi": "10.1038/s41586-023-0001"},
        {"id": "2", "title": "Paper Two", "doi": "10.1038/s41586-023-0002"},
        {"id": "3", "title": "Paper One Again", "doi": "10.1038/s41586-023-0001"},
    ]
    checked = check_batch_duplicates(batch)
    assert checked[0].get("duplicate_info", {}).get("is_duplicate") is not True
    assert checked[2].get("duplicate_info", {}).get("is_duplicate") is True
    assert checked[2]["duplicate_info"]["match_type"] == "doi"


def test_batch_duplicate_title_detection():
    batch = [
        {"id": "1", "title": "Quantum Computing Architecture for Cryptography", "doi": None},
        {"id": "2", "title": "Quantum Computing Architecture for Cryptography!", "doi": None},
    ]
    checked = check_batch_duplicates(batch)
    assert checked[1].get("duplicate_info", {}).get("is_duplicate") is True
    assert checked[1]["duplicate_info"]["match_type"] == "title_author"
