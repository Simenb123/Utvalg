"""Field-value normalizers: canonical forms for invoice fields.

Normalizers convert raw extracted text fragments into the stable
representations used internally and stored in :class:`FieldEvidence`.
Examples:

  * ``"1 175,00"`` / ``"1,175.00"`` → ``"1175.00"`` (via format_utils)
  * ``"2025-06-01"`` → ``"01.06.2025"``
  * ``"NO 965 004 211 MVA"`` → ``"965004211"``

The orchestrator in :mod:`document_engine.engine` picks a normalizer
per field via :func:`_normalize_field_value`.

Supplier-name normalisation lives in :mod:`document_engine.supplier`
because it is tightly coupled to the supplier-extraction prioritisation
logic there.
"""
from __future__ import annotations

import re
from typing import Any

from .extractors import _normalize_whitespace
from .supplier import _normalize_supplier_name
from .format_utils import (
    normalize_amount_text as _format_normalize_amount_text,
    parse_amount_flexible as _format_parse_amount,
)


_MONTH_NAME_TO_NUM: dict[str, int] = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "october": 10, "december": 12,
}


def _normalize_compact_text(value: str) -> str:
    return _normalize_whitespace(value).strip(":.- ")


def _normalize_currency_text(value: str) -> str:
    return _normalize_whitespace(value).upper()


def _normalize_orgnr(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    return digits[:9] if len(digits) >= 9 else digits


_TEXT_DATE_NORM_RE = re.compile(
    r"(\d{1,2})\.?\s*(" + "|".join(_MONTH_NAME_TO_NUM.keys()) + r")\s+(\d{4})",
    re.IGNORECASE,
)


def _normalize_date_text(value: str) -> str:
    text = _normalize_whitespace(value)

    # Try text-month format first (e.g. "5. desember 2025")
    m = _TEXT_DATE_NORM_RE.search(text)
    if m:
        day_s, month_name, year_s = m.group(1), m.group(2).lower(), m.group(3)
        month_num = _MONTH_NAME_TO_NUM.get(month_name)
        if month_num:
            return f"{int(day_s):02d}.{month_num:02d}.{int(year_s):04d}"

    text = text.replace("/", ".").replace("-", ".")
    parts = text.split(".")
    if len(parts) != 3:
        return text
    if len(parts[0]) == 4:
        year, month, day = parts
    else:
        day, month, year = parts
    if len(year) == 2:
        year = f"20{year}"
    try:
        day_int = int(day)
        month_int = int(month)
        year_int = int(year)
    except Exception:
        return text
    return f"{day_int:02d}.{month_int:02d}.{year_int:04d}"


def _normalize_amount_text(value: str) -> str:
    return _format_normalize_amount_text(value)


def _parse_amount(value: Any) -> float | None:
    return _format_parse_amount(value)


def _normalize_field_value(field_name: str, value: str) -> str:
    if field_name == "supplier_name":
        return _normalize_supplier_name(value)
    if field_name == "supplier_orgnr":
        return _normalize_orgnr(value)
    if field_name == "invoice_number":
        return _normalize_compact_text(value)
    if field_name in {"invoice_date", "due_date"}:
        return _normalize_date_text(value)
    if field_name in {"subtotal_amount", "vat_amount", "total_amount"}:
        return _normalize_amount_text(value)
    if field_name == "currency":
        return _normalize_currency_text(value)
    if field_name in {"description", "period"}:
        return _normalize_whitespace(value)
    return _normalize_whitespace(value)
