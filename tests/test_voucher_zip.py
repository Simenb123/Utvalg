"""Tester for document_engine.voucher_zip (PowerOffice GO bilag-eksport).

PowerOffice GO eksporterer bilag som ZIP-arkiver der hver fil heter
``<bilag_nr>-<beskrivelse>.pdf``. Disse testene bekrefter at:
- ZIP-format gjenkjennes
- Filnavnene parses til VoucherEntry
- Ekstraksjon plukker ut riktig fil
- Cache-roundtrip (to_dict / from_dict) bevarer pdf_in_zip-attributtet
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from document_engine.voucher_pdf import VoucherEntry
from document_engine.voucher_zip import (
    extract_bilag_from_zip,
    extract_entry,
    is_powereoffice_zip,
    scan_voucher_zip,
)


def _make_zip(tmp_path: Path, files: dict[str, bytes]) -> Path:
    """Hjelpefunksjon: lag en ZIP med gitte (filnavn → innhold)-par."""
    zip_path = tmp_path / "test_bilag.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for name, content in files.items():
            z.writestr(name, content)
    return zip_path


# ---------------------------------------------------------------------------
# Format-deteksjon
# ---------------------------------------------------------------------------

def test_is_powereoffice_zip_detects_valid(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Faktura 1234 fra Eksempel AS.pdf": b"%PDF-1.4\n",
        "1001-Manuelt.pdf": b"%PDF-1.4\n",
    })
    assert is_powereoffice_zip(zp) is True


def test_is_powereoffice_zip_rejects_random_zip(tmp_path):
    zp = _make_zip(tmp_path, {
        "readme.txt": b"hello",
        "data.json": b"{}",
    })
    assert is_powereoffice_zip(zp) is False


def test_is_powereoffice_zip_rejects_missing_file(tmp_path):
    assert is_powereoffice_zip(tmp_path / "finnes_ikke.zip") is False


def test_is_powereoffice_zip_rejects_pdf_extension(tmp_path):
    fake = tmp_path / "ikke_zip.pdf"
    fake.write_bytes(b"%PDF-1.4")
    assert is_powereoffice_zip(fake) is False


def test_is_powereoffice_zip_ignores_subfolder_files(tmp_path):
    """Filer i undermapper teller ikke som PowerOffice-format."""
    zp = _make_zip(tmp_path, {
        "subdir/1000-Faktura.pdf": b"%PDF-1.4\n",
    })
    assert is_powereoffice_zip(zp) is False


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def test_scan_voucher_zip_returns_one_entry_per_pdf(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Faktura 1234 fra Eg Prosjekt AS.pdf": b"%PDF-1.4\n",
        "1001-Manuelt.pdf": b"%PDF-1.4\n",
        "1026-Bank.pdf": b"%PDF-1.4\n",
    })
    entries = scan_voucher_zip(zp, year="2025")
    assert len(entries) == 3
    assert {e.bilag_nr for e in entries} == {"1000", "1001", "1026"}


def test_scan_voucher_zip_extracts_description_from_filename(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Faktura 2834 fra Eg Prosjekt AS.pdf": b"%PDF-1.4\n",
    })
    entries = scan_voucher_zip(zp, year="2025")
    assert entries[0].description == "Faktura 2834 fra Eg Prosjekt AS"


def test_scan_voucher_zip_marks_entries_as_zip(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4\n"})
    entries = scan_voucher_zip(zp)
    assert entries[0].is_zip is True
    assert entries[0].pdf_in_zip == "1000-Test.pdf"
    # Side-felt er 0 for ZIP-baserte entries
    assert entries[0].start_page == 0
    assert entries[0].end_page == 0


def test_scan_voucher_zip_sets_year_from_argument(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4\n"})
    entries = scan_voucher_zip(zp, year="2026")
    assert entries[0].year == "2026"


def test_scan_voucher_zip_skips_non_matching_files(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Faktura.pdf": b"%PDF-1.4\n",
        "readme.txt": b"hello",
        "uten_prefix.pdf": b"%PDF-1.4\n",
        "abc-ikke_tall.pdf": b"%PDF-1.4\n",
    })
    entries = scan_voucher_zip(zp)
    assert len(entries) == 1
    assert entries[0].bilag_nr == "1000"


def test_scan_voucher_zip_skips_subfolder_files(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Top.pdf": b"%PDF-1.4\n",
        "underkatalog/2000-Skjult.pdf": b"%PDF-1.4\n",
    })
    entries = scan_voucher_zip(zp)
    assert len(entries) == 1
    assert entries[0].bilag_nr == "1000"


def test_scan_voucher_zip_returns_empty_for_missing_file(tmp_path):
    assert scan_voucher_zip(tmp_path / "ikke_eksisterer.zip") == []


def test_scan_voucher_zip_returns_empty_for_corrupt_zip(tmp_path):
    bad = tmp_path / "corrupt.zip"
    bad.write_bytes(b"not a zip file at all")
    assert scan_voucher_zip(bad) == []


# ---------------------------------------------------------------------------
# Ekstraksjon
# ---------------------------------------------------------------------------

def test_extract_bilag_from_zip_writes_file(tmp_path):
    zp = _make_zip(tmp_path, {
        "1000-Test.pdf": b"%PDF-1.4 INNHOLD\n",
    })
    out = tmp_path / "extracted" / "1000.pdf"
    result = extract_bilag_from_zip(zp, "1000-Test.pdf", out)
    assert result == out
    assert out.exists()
    assert out.read_bytes() == b"%PDF-1.4 INNHOLD\n"


def test_extract_bilag_from_zip_creates_parent_dir(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4\n"})
    out = tmp_path / "deep" / "nested" / "out.pdf"
    extract_bilag_from_zip(zp, "1000-Test.pdf", out)
    assert out.exists()


def test_extract_bilag_from_zip_raises_for_missing_zip(tmp_path):
    with pytest.raises(RuntimeError, match="finnes ikke"):
        extract_bilag_from_zip(
            tmp_path / "missing.zip", "1000-Test.pdf", tmp_path / "out.pdf",
        )


def test_extract_bilag_from_zip_raises_for_missing_pdf_in_zip(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4\n"})
    with pytest.raises(RuntimeError, match="finnes ikke i"):
        extract_bilag_from_zip(zp, "9999-Mangler.pdf", tmp_path / "out.pdf")


def test_extract_entry_works_for_zip_entry(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4 OK\n"})
    entries = scan_voucher_zip(zp)
    out = tmp_path / "out.pdf"
    extract_entry(entries[0], out)
    assert out.read_bytes() == b"%PDF-1.4 OK\n"


def test_extract_entry_raises_for_non_zip_entry():
    """Tripletex-entries (uten pdf_in_zip) skal ikke håndteres her."""
    tripletex = VoucherEntry(
        bilag_nr="1000", year="2025",
        start_page=0, end_page=2,
        source_pdf="/some/big.pdf",
    )
    with pytest.raises(ValueError, match="ikke fra et ZIP"):
        extract_entry(tripletex, "/tmp/out.pdf")


# ---------------------------------------------------------------------------
# Cache-roundtrip via VoucherEntry
# ---------------------------------------------------------------------------

def test_voucher_entry_to_dict_includes_pdf_in_zip(tmp_path):
    zp = _make_zip(tmp_path, {"1000-Test.pdf": b"%PDF-1.4\n"})
    entry = scan_voucher_zip(zp, year="2025")[0]
    d = entry.to_dict()
    assert d["pdf_in_zip"] == "1000-Test.pdf"
    assert d["bilag_nr"] == "1000"


def test_voucher_entry_from_dict_restores_pdf_in_zip():
    d = {
        "bilag_nr": "1000",
        "year": "2025",
        "start_page": 0,
        "end_page": 0,
        "date": "",
        "description": "Test",
        "source_pdf": "/path/to.zip",
        "pdf_in_zip": "1000-Test.pdf",
    }
    e = VoucherEntry.from_dict(d)
    assert e.is_zip is True
    assert e.pdf_in_zip == "1000-Test.pdf"


def test_voucher_entry_to_dict_omits_pdf_in_zip_for_tripletex():
    """Tripletex-entries skal IKKE ha pdf_in_zip-felt i cache (clean dict)."""
    tx = VoucherEntry(
        bilag_nr="1000", year="2025",
        start_page=5, end_page=10,
        source_pdf="/big.pdf",
    )
    d = tx.to_dict()
    assert "pdf_in_zip" not in d
