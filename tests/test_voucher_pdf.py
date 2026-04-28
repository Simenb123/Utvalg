"""Tests for document_engine.voucher_pdf — scanner and extractor."""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from document_engine.voucher_pdf import (
    VoucherEntry,
    _normalize_nr,
    scan_voucher_pdf,
    extract_bilag_pages,
)


# ---------------------------------------------------------------------------
# _normalize_nr
# ---------------------------------------------------------------------------

def test_normalize_nr_strips_excel_suffix():
    assert _normalize_nr("67.0") == "67"

def test_normalize_nr_plain_integer():
    assert _normalize_nr("223754") == "223754"

def test_normalize_nr_leading_zeros():
    assert _normalize_nr("007") == "7"


# ---------------------------------------------------------------------------
# VoucherEntry
# ---------------------------------------------------------------------------

def test_voucher_entry_bilag_key_normalises():
    e = VoucherEntry(bilag_nr="67.0", year="2025", start_page=0, end_page=2)
    assert e.bilag_key == "67"

def test_voucher_entry_page_count():
    e = VoucherEntry(bilag_nr="67", year="2025", start_page=4, end_page=6)
    assert e.page_count == 3

def test_voucher_entry_roundtrip():
    e = VoucherEntry(
        bilag_nr="67",
        year="2025",
        start_page=1038,
        end_page=1040,
        date="2025-02-11",
        description="Test AS | 123456789",
        source_pdf="/tmp/voucher.pdf",
    )
    restored = VoucherEntry.from_dict(e.to_dict())
    assert restored.bilag_nr == e.bilag_nr
    assert restored.year == e.year
    assert restored.start_page == e.start_page
    assert restored.end_page == e.end_page
    assert restored.date == e.date
    assert restored.source_pdf == e.source_pdf


# ---------------------------------------------------------------------------
# scan_voucher_pdf — unit test with mocked PyMuPDF
# ---------------------------------------------------------------------------

def _make_fake_doc(pages: list[str]):
    """Return a minimal mock fitz.Document with given page texts."""
    fake_pages = []
    for text in pages:
        p = MagicMock()
        p.get_text.return_value = text
        fake_pages.append(p)

    doc = MagicMock()
    doc.__len__ = lambda self: len(fake_pages)
    doc.__iter__ = lambda self: iter(fake_pages)
    doc.__getitem__ = lambda self, i: fake_pages[i]
    doc.__enter__ = lambda self: self
    doc.__exit__ = MagicMock(return_value=False)
    return doc


@patch("document_engine.voucher_pdf.Path.exists", return_value=True)
def test_scan_voucher_pdf_finds_cover_pages(mock_exists, tmp_path, monkeypatch):
    page_texts = [
        "Bilag nummer 67-2025\nBilag nummer 67-2025\nFirma:\nSpor AS\nDato:\n2025-02-11\nKonteringssammendrag",
        "FAKTURA side 1",
        "FAKTURA side 2",
        "Bilag nummer 68-2025\nBilag nummer 68-2025\nFirma:\nSpor AS\nDato:\n2025-02-15",
        "Fakturadetaljer",
    ]

    fake_doc = _make_fake_doc(page_texts)

    import fitz as _fitz
    monkeypatch.setattr(_fitz, "open", lambda *a, **kw: fake_doc)

    pdf_path = tmp_path / "voucher.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")  # dummy content

    entries = scan_voucher_pdf(pdf_path)

    assert len(entries) == 2
    e0, e1 = entries
    assert e0.bilag_nr == "67"
    assert e0.year == "2025"
    assert e0.start_page == 0
    assert e0.end_page == 2  # covers pages 0-2
    assert e0.date == "2025-02-11"

    assert e1.bilag_nr == "68"
    assert e1.start_page == 3
    assert e1.end_page == 4  # last page


@patch("document_engine.voucher_pdf.Path.exists", return_value=True)
def test_scan_voucher_pdf_returns_empty_when_no_cover_pages(mock_exists, tmp_path, monkeypatch):
    fake_doc = _make_fake_doc(["Normal PDF page", "Another page"])

    import fitz as _fitz
    monkeypatch.setattr(_fitz, "open", lambda *a, **kw: fake_doc)

    pdf_path = tmp_path / "not_a_voucher.pdf"
    pdf_path.write_bytes(b"%PDF-1.4")

    entries = scan_voucher_pdf(pdf_path)
    assert entries == []


def test_scan_voucher_pdf_returns_empty_when_file_missing():
    entries = scan_voucher_pdf("/nonexistent/path/voucher.pdf")
    assert entries == []


# ---------------------------------------------------------------------------
# document_control_voucher_index integration
# ---------------------------------------------------------------------------

def test_find_and_extract_bilag_returns_none_when_no_vouchers(tmp_path, monkeypatch):
    import src.shared.document_control.voucher_index as idx

    # Point search dirs to an empty temp directory
    monkeypatch.setattr(idx, "get_voucher_search_dirs", lambda *a, **kw: [tmp_path])
    monkeypatch.setattr(idx, "_cache_path", lambda *a, **kw: tmp_path / "cache.json")

    result = idx.find_and_extract_bilag("67", client=None, year="2025")
    assert result is None
