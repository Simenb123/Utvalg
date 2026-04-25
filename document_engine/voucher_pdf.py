"""document_engine.voucher_pdf

Scan Tripletex-style voucher bundle PDFs and extract individual bilag pages.

Tripletex exports one large PDF per batch of vouchers.  Each bilag starts with
a cover page whose first text block is exactly:

    Bilag nummer <bilag_nr>-<year>
    Bilag nummer <bilag_nr>-<year>

The bilag_nr is the sequential voucher number in the fiscal year and matches
the bilag number used in SAF-T / the accounting system.

Usage::

    from document_engine.voucher_pdf import scan_voucher_pdf, extract_bilag_pages

    entries = scan_voucher_pdf("path/to/voucher 1-500.pdf")
    for e in entries:
        print(e.bilag_nr, e.year, e.start_page, e.end_page)

    path = extract_bilag_pages("path/to/voucher 1-500.pdf", 5, 8, "/tmp/bilag_67.pdf")
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class VoucherEntry:
    """One bilag block — kan komme fra to kilder:

    - Tripletex: én stor PDF der hver bilag dekker et side-spenn
      (``source_pdf`` + ``start_page``/``end_page``).
    - PowerOffice GO: ZIP-arkiv der hver bilag er en separat PDF inne i
      arkivet (``source_pdf`` peker til ZIP-en, ``pdf_in_zip`` er den
      relative stien til PDF-en inne i arkivet, og side-feltene er 0).

    ``pdf_in_zip`` er tomt for Tripletex-entries, og fylt for PowerOffice.
    """
    bilag_nr: str           # e.g. "67" or "223754"
    year: str               # e.g. "2025"
    start_page: int         # 0-indexed, inclusive (Tripletex)
    end_page: int           # 0-indexed, inclusive (Tripletex)
    date: str = ""          # "YYYY-MM-DD" if found on cover page
    description: str = ""   # first meaningful text from cover page
    source_pdf: str = ""    # absolute path to source PDF or ZIP
    pdf_in_zip: str = ""    # relativ sti i ZIP — kun satt for PowerOffice

    @property
    def bilag_key(self) -> str:
        """Normalised bilag key matching normalize_bilag_key()."""
        return _normalize_nr(self.bilag_nr)

    @property
    def page_count(self) -> int:
        return self.end_page - self.start_page + 1

    @property
    def is_zip(self) -> bool:
        """True hvis denne kommer fra en ZIP (PowerOffice GO)."""
        return bool(self.pdf_in_zip)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "bilag_nr": self.bilag_nr,
            "year": self.year,
            "start_page": self.start_page,
            "end_page": self.end_page,
            "date": self.date,
            "description": self.description,
            "source_pdf": self.source_pdf,
        }
        if self.pdf_in_zip:
            d["pdf_in_zip"] = self.pdf_in_zip
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "VoucherEntry":
        return cls(
            bilag_nr=str(d.get("bilag_nr", "")),
            year=str(d.get("year", "")),
            start_page=int(d.get("start_page", 0)),
            end_page=int(d.get("end_page", 0)),
            date=str(d.get("date", "")),
            description=str(d.get("description", "")),
            source_pdf=str(d.get("source_pdf", "")),
            pdf_in_zip=str(d.get("pdf_in_zip", "")),
        )


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

_COVER_RE = re.compile(
    r"Bilag\s+nummer\s+(\d+)-(\d{4})",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"Dato:\s*\n?\s*(\d{4}-\d{2}-\d{2})")


def scan_voucher_pdf(pdf_path: str | Path) -> list[VoucherEntry]:
    """Scan a Tripletex voucher bundle PDF and return one VoucherEntry per bilag.

    Returns an empty list if the file is not a recognisable Tripletex voucher
    bundle or if PyMuPDF is not installed.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []

    pdf_path = Path(pdf_path).expanduser().resolve()
    if not pdf_path.exists():
        return []

    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return []

    cover_positions: list[tuple[int, str, str]] = []  # (page_index, bilag_nr, year)

    with doc:
        n_pages = len(doc)
        for i in range(n_pages):
            try:
                text = doc[i].get_text()
            except Exception:
                continue

            # Cover pages start with "Bilag nummer X-YYYY" (possibly duplicated)
            stripped = text.strip()
            m = _COVER_RE.match(stripped)
            if m:
                cover_positions.append((i, m.group(1), m.group(2)))

        if not cover_positions:
            return []

        entries: list[VoucherEntry] = []
        for idx, (page_i, bilag_nr, year) in enumerate(cover_positions):
            end_page = (
                cover_positions[idx + 1][0] - 1
                if idx + 1 < len(cover_positions)
                else n_pages - 1
            )

            # Extract date and description from cover text
            try:
                cover_text = doc[page_i].get_text()
            except Exception:
                cover_text = ""

            date = ""
            m_date = _DATE_RE.search(cover_text)
            if m_date:
                date = m_date.group(1)

            description = _extract_description(cover_text)

            entries.append(
                VoucherEntry(
                    bilag_nr=bilag_nr,
                    year=year,
                    start_page=page_i,
                    end_page=end_page,
                    date=date,
                    description=description,
                    source_pdf=str(pdf_path),
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def extract_bilag_pages(
    pdf_path: str | Path,
    start_page: int,
    end_page: int,
    output_path: str | Path,
) -> Path:
    """Extract pages [start_page, end_page] (0-indexed, inclusive) to a new PDF.

    Returns the output path.  Raises RuntimeError if PyMuPDF is not available
    or the extraction fails.
    """
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF (fitz) is required for PDF extraction.") from exc

    pdf_path = Path(pdf_path).expanduser().resolve()
    output_path = Path(output_path).expanduser()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    src = fitz.open(str(pdf_path))
    with src:
        dst = fitz.open()
        dst.insert_pdf(src, from_page=start_page, to_page=end_page)
        dst.save(str(output_path))
        dst.close()

    return output_path


def extract_entry(entry: VoucherEntry, output_path: str | Path) -> Path:
    """Convenience wrapper: extract the pages described by a VoucherEntry."""
    return extract_bilag_pages(
        entry.source_pdf,
        entry.start_page,
        entry.end_page,
        output_path,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_nr(bilag_nr: str) -> str:
    """Strip leading zeros and trailing Excel suffixes (.0)."""
    text = str(bilag_nr or "").strip()
    text = re.sub(r"\.0+$", "", text)
    try:
        return str(int(text))
    except ValueError:
        return text


def _extract_description(cover_text: str) -> str:
    """Pull a short readable description from a cover page."""
    lines = [line.strip() for line in cover_text.splitlines() if line.strip()]
    # Skip the repeated "Bilag nummer X-YYYY" lines and metadata
    skip_prefixes = (
        "Bilag nummer",
        "Firma:",
        "Org.nr.:",
        "Bilag",
        "Nummer:",
        "Dato:",
        "Opprettet:",
        "Sist endret:",
        "\xa0",
    )
    useful: list[str] = []
    for line in lines:
        if any(line.startswith(p) for p in skip_prefixes):
            continue
        if re.match(r"^\d{4}-\d{2}-\d{2}", line):
            continue
        useful.append(line)
        if len(useful) >= 3:
            break
    return " | ".join(useful)
