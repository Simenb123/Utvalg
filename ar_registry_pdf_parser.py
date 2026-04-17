"""Parser for RF-1086 Aksjonærregisteroppgaven (PDF).

Extracts company header and per-shareholder data from the Skatteetaten
RF-1086 PDF form using pdfplumber text extraction and regex parsing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Transaction:
    direction: str = ""      # "tilgang" | "avgang"
    trans_type: str = ""     # "Kjøp", "Salg", "Stiftelse", etc.
    shares: int = 0
    date: str = ""           # "01.11.2025"
    amount: float = 0.0      # anskaffelsesverdi / vederlag


@dataclass
class ShareholderRecord:
    shareholder_id: str = ""
    shareholder_name: str = ""
    shareholder_kind: str = ""  # "person" | "company"
    land: str = ""
    address: str = ""
    postal_code: str = ""
    postal_place: str = ""
    shares_start: int = 0
    shares_end: int = 0
    transactions: list[Transaction] = field(default_factory=list)
    page_number: int = 0


@dataclass
class CompanyHeader:
    company_orgnr: str = ""
    company_name: str = ""
    antall_aksjer_start: int = 0
    antall_aksjer_end: int = 0
    year: str = ""


@dataclass
class ParseResult:
    header: CompanyHeader = field(default_factory=CompanyHeader)
    shareholders: list[ShareholderRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_int(text: str) -> int:
    """Parse an integer from text like '2 250' or '225 000,00'."""
    if not text:
        return 0
    cleaned = text.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return 0


def _extract_two_numbers(text: str) -> tuple[int, int]:
    """Extract two numbers from a string like '2 250           2 250'."""
    # Split on 3+ whitespace to separate the two number groups
    parts = re.split(r"\s{3,}", text.strip())
    if len(parts) >= 2:
        return _parse_int(parts[0]), _parse_int(parts[1])
    if len(parts) == 1:
        return _parse_int(parts[0]), 0
    return 0, 0


def _clean_text(text: str) -> str:
    """Replace common encoding artifacts."""
    return (
        text.replace("\u00e6", "æ")
        .replace("\u00f8", "ø")
        .replace("\u00e5", "å")
        .replace("\u00c6", "Æ")
        .replace("\u00d8", "Ø")
        .replace("\u00c5", "Å")
    )


# ---------------------------------------------------------------------------
# Year detection
# ---------------------------------------------------------------------------

_RE_YEAR = re.compile(r"[Aa]ksjon.rregisteroppgaven\s+(20\d{2})", re.IGNORECASE)


def detect_year(text: str) -> str:
    m = _RE_YEAR.search(text)
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# Company header (page 1)
# ---------------------------------------------------------------------------

_RE_ORGNR_NAME = re.compile(
    r"organisasjonsnummer.*?Selskapets\s+navn\s*\n\s*(\d{9})\s+(.+)",
    re.IGNORECASE,
)

_RE_ANTALL_AKSJER = re.compile(
    r"4\s+Antall\s+aksjer\s+i\s+denne\s+aksjeklassen\s{2,}(.+)",
    re.IGNORECASE,
)


def parse_company_header(text: str) -> CompanyHeader:
    header = CompanyHeader()
    header.year = detect_year(text)

    m = _RE_ORGNR_NAME.search(text)
    if m:
        header.company_orgnr = m.group(1).strip()
        header.company_name = m.group(2).strip()

    m = _RE_ANTALL_AKSJER.search(text)
    if m:
        nums = _extract_two_numbers(m.group(1))
        header.antall_aksjer_start = nums[0]
        header.antall_aksjer_end = nums[1]

    return header


# ---------------------------------------------------------------------------
# Shareholder block splitting
# ---------------------------------------------------------------------------

_RE_AKSJONAER_ID = re.compile(
    r"Aksjon.ridentifikasjon\s*\(.*?\)\s*\n\s*(\d{9,11})",
    re.IGNORECASE | re.DOTALL,
)


def split_shareholder_blocks(
    page_texts: list[str],
) -> list[tuple[str, int]]:
    """Group page texts into shareholder blocks.

    Returns list of (combined_text, first_page_number) where page_number
    is 1-based.
    """
    blocks: list[tuple[str, int]] = []
    current_text = ""
    current_page = 0

    for page_idx, text in enumerate(page_texts):
        if page_idx == 0:
            continue  # skip company header page

        page_nr = page_idx + 1  # 1-based
        m = _RE_AKSJONAER_ID.search(text)

        if m:
            # New shareholder block
            if current_text:
                blocks.append((current_text, current_page))
            current_text = text
            current_page = page_nr
        elif current_text:
            # Continuation of previous shareholder (multi-page transactions)
            current_text += "\n" + text

    if current_text:
        blocks.append((current_text, current_page))

    return blocks


# ---------------------------------------------------------------------------
# Single shareholder parsing
# ---------------------------------------------------------------------------

_RE_NAME_LAND = re.compile(
    r"Navn\s+Land\s*\n\s*(.+?)\s{3,}(\S+)",
)

_RE_ADDRESS = re.compile(
    r"Adresse\s+Postnummer\s+Poststed\s*\n\s*(.+?)\s{3,}(\d{4})\s+(.+)",
)

_RE_POST20 = re.compile(
    r"Post\s+20\s+Antall\s+aksjer\s+per\s*\n\s*aksjon.r\s+(.+)",
    re.IGNORECASE,
)

# Matches transaction lines like:
#   Kjøp                          30 01.11.2025      01:00:00
#   Salg                         150 01.09.2025      00:00:00
_RE_TRANSACTION = re.compile(
    r"(Kj.p|Salg|Stiftelse|Gave|Arv|Fusjon|Fisjon|Splitt|Spleis|Fondsemisjon|Rettet\s+emisjon|Emisjon)"
    r"\s+(\d[\d\s]*?)\s+(\d{2}\.\d{2}\.\d{4})",
    re.IGNORECASE,
)

# Amount: find the first standalone number on a line after the transaction header
# Works for both "Total anskaffelsesverdi..." and "Totalt vederlag/Utbetalt av..."
_RE_AMOUNT_LINE = re.compile(
    r"^\s+([\d][\d\s]*[,.]\d{2})\s*$",
    re.MULTILINE,
)

_RE_POST23 = re.compile(r"Post\s+23\s+Aksjer\s+i\s+tilgang", re.IGNORECASE)
_RE_POST25 = re.compile(r"Post\s+25\s+Aksjer\s+i\s+avgang", re.IGNORECASE)


def _parse_amount(text: str) -> float:
    """Parse a Norwegian-formatted amount like '7 530,30'."""
    cleaned = text.replace("\u00a0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def _parse_transactions(text: str) -> list[Transaction]:
    """Extract all transactions (Post 23 tilgang + Post 25 avgang)."""
    transactions: list[Transaction] = []

    # Find Post 23 and Post 25 boundaries
    m23 = _RE_POST23.search(text)
    m25 = _RE_POST25.search(text)

    sections: list[tuple[str, str]] = []  # (direction, section_text)
    if m23:
        end_23 = m25.start() if m25 else len(text)
        sections.append(("tilgang", text[m23.start():end_23]))
    if m25:
        sections.append(("avgang", text[m25.start():]))

    for direction, section in sections:
        # Collect all transaction matches
        tx_matches = list(_RE_TRANSACTION.finditer(section))
        for i, m in enumerate(tx_matches):
            t = Transaction(
                direction=direction,
                trans_type=m.group(1).strip(),
                shares=_parse_int(m.group(2)),
                date=m.group(3).strip(),
            )
            # Look for amount between this transaction and the next
            end_search = tx_matches[i + 1].start() if i + 1 < len(tx_matches) else len(section)
            between = section[m.end():end_search]
            amt_match = _RE_AMOUNT_LINE.search(between)
            if amt_match:
                t.amount = _parse_amount(amt_match.group(1))
            transactions.append(t)

    return transactions


def parse_shareholder_block(
    text: str, page_number: int
) -> ShareholderRecord | None:
    rec = ShareholderRecord(page_number=page_number)

    # Shareholder ID
    m = _RE_AKSJONAER_ID.search(text)
    if not m:
        return None
    rec.shareholder_id = m.group(1).strip()
    digits = len(rec.shareholder_id)
    rec.shareholder_kind = "person" if digits >= 11 else "company"

    # Name and land
    m = _RE_NAME_LAND.search(text)
    if m:
        rec.shareholder_name = m.group(1).strip()
        rec.land = m.group(2).strip()

    # Address
    m = _RE_ADDRESS.search(text)
    if m:
        rec.address = m.group(1).strip()
        rec.postal_code = m.group(2).strip()
        rec.postal_place = m.group(3).strip()

    # Shares (Post 20)
    m = _RE_POST20.search(text)
    if m:
        nums = _extract_two_numbers(m.group(1))
        rec.shares_start = nums[0]
        rec.shares_end = nums[1]

    # Transactions (Post 23/25)
    rec.transactions = _parse_transactions(text)

    return rec


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def parse_rf1086_pdf(path: str | Path) -> ParseResult:
    """Parse an RF-1086 PDF and return structured shareholder data."""
    import pdfplumber

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Fant ikke filen: {file_path}")

    result = ParseResult()

    with pdfplumber.open(str(file_path)) as pdf:
        page_texts = [
            page.extract_text(layout=True) or "" for page in pdf.pages
        ]

    if not page_texts:
        result.warnings.append("PDF-en inneholder ingen sider.")
        return result

    # Company header from page 1
    result.header = parse_company_header(page_texts[0])
    if not result.header.company_orgnr:
        result.warnings.append("Kunne ikke lese selskapets org.nr fra side 1.")
    if not result.header.year:
        result.warnings.append("Kunne ikke detektere registerår fra PDF-en.")

    # Shareholder blocks
    blocks = split_shareholder_blocks(page_texts)
    for block_text, page_nr in blocks:
        rec = parse_shareholder_block(block_text, page_nr)
        if rec and rec.shareholder_name:
            result.shareholders.append(rec)
        elif rec:
            result.warnings.append(
                f"Side {page_nr}: Fant aksjonær-ID {rec.shareholder_id} men mangler navn."
            )
        else:
            result.warnings.append(f"Side {page_nr}: Kunne ikke parse aksjonærblokk.")

    return result
