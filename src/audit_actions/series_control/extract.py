from __future__ import annotations

import re
from typing import Iterable

import pandas as pd

from .models import SeriesFieldOption


AUTO_FIELD_KEY = "auto"
REFERENCE_FIELD_KEY = "reference"
DOCUMENT_NO_FIELD_KEY = "document_no"
BILAG_FIELD_KEY = "bilag"
TEXT_INVOICE_FIELD_KEY = "text_invoice_no"
CUSTOM_COLUMN_PREFIX = "column:"

_TARGETED_TEXT_PATTERNS = (
    re.compile(r"\b(?:faktura|invoice)\s*(?:nummer|number|nr\.?)?\s*[:#-]?\s*([A-Za-z0-9-]+)\b", re.I),
    re.compile(r"\b(?:kreditnota|credit\s*note)\s*(?:nummer|number|nr\.?)?\s*[:#-]?\s*([A-Za-z0-9-]+)\b", re.I),
)
_NUMERIC_TAIL_RE = re.compile(r"^(.*?)(\d+)$")

_REFERENCE_COLUMNS = ("Referanse", "ReferenceNumber", "Referansenummer")
_DOCUMENT_COLUMNS = ("Dokumentnr", "Dokumentnummer", "DocumentNumber", "Doknr")
_TEXT_COLUMNS = ("Tekst", "Description", "Beskrivelse")


def custom_column_field_key(column_name: str) -> str:
    return f"{CUSTOM_COLUMN_PREFIX}{column_name}"


def is_custom_column_field_key(field_key: str) -> bool:
    return str(field_key or "").startswith(CUSTOM_COLUMN_PREFIX)


def custom_column_name_from_key(field_key: str) -> str:
    if not is_custom_column_field_key(field_key):
        return ""
    return str(field_key)[len(CUSTOM_COLUMN_PREFIX) :]


def _first_present_column(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    if df is None or not isinstance(df, pd.DataFrame):
        return None
    for name in names:
        if name in df.columns:
            return str(name)
    return None


def _non_empty_fraction(series: pd.Series) -> float:
    if series is None or len(series.index) == 0:
        return 0.0
    text = series.astype("string").fillna("").str.strip()
    return float((text != "").mean())


def list_series_field_options(df: pd.DataFrame) -> list[SeriesFieldOption]:
    options: list[SeriesFieldOption] = [SeriesFieldOption(key=AUTO_FIELD_KEY, label="Auto", structured=True)]

    ref_col = _first_present_column(df, _REFERENCE_COLUMNS)
    if ref_col is not None and _non_empty_fraction(df[ref_col]) > 0:
        options.append(SeriesFieldOption(key=REFERENCE_FIELD_KEY, label="Referanse", source_column=ref_col, structured=True))

    doc_col = _first_present_column(df, _DOCUMENT_COLUMNS)
    if doc_col is not None and _non_empty_fraction(df[doc_col]) > 0:
        options.append(SeriesFieldOption(key=DOCUMENT_NO_FIELD_KEY, label="Dokumentnr", source_column=doc_col, structured=True))

    if "Bilag" in df.columns and _non_empty_fraction(df["Bilag"]) > 0:
        options.append(SeriesFieldOption(key=BILAG_FIELD_KEY, label="Bilag", source_column="Bilag", structured=True))

    text_col = _first_present_column(df, _TEXT_COLUMNS)
    if text_col is not None and _non_empty_fraction(df[text_col]) > 0:
        options.append(
            SeriesFieldOption(key=TEXT_INVOICE_FIELD_KEY, label="Tekst-ekstrahert", source_column=text_col, structured=False)
        )

    for column in df.columns:
        col = str(column)
        if col in {opt.source_column for opt in options if opt.source_column}:
            continue
        if _non_empty_fraction(df[col]) <= 0:
            continue
        options.append(SeriesFieldOption(key=custom_column_field_key(col), label=col, source_column=col, structured=False))

    return options


def resolve_field_option(df: pd.DataFrame, field_key: str) -> SeriesFieldOption | None:
    if field_key == AUTO_FIELD_KEY:
        return SeriesFieldOption(key=AUTO_FIELD_KEY, label="Auto", structured=True)

    for option in list_series_field_options(df):
        if option.key == field_key:
            return option

    if is_custom_column_field_key(field_key):
        col = custom_column_name_from_key(field_key)
        if col and col in df.columns:
            return SeriesFieldOption(key=field_key, label=col, source_column=col, structured=False)
    return None


def extract_text_invoice_number(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for pattern in _TARGETED_TEXT_PATTERNS:
        match = pattern.search(text)
        if match:
            return str(match.group(1) or "").strip()
    return ""


def _normalise_token(value: object) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", "", text)


def _derive_components(value: object) -> tuple[str, str, int | None, int | None, str]:
    raw = str(value or "").strip()
    if not raw:
        return ("", "", None, None, "")

    cleaned = _normalise_token(raw)
    if not cleaned:
        return ("", "", None, None, "")

    match = _NUMERIC_TAIL_RE.match(cleaned)
    if not match:
        return (raw, "", None, None, "")

    prefix = match.group(1) or ""
    digits = match.group(2) or ""
    try:
        number = int(digits)
    except Exception:
        return (raw, "", None, None, "")

    width = len(digits)
    family_key = f"{prefix}|{width}"
    return (raw, prefix, number, width, family_key)


def build_series_rows(df: pd.DataFrame, field_key: str) -> tuple[SeriesFieldOption, pd.DataFrame]:
    option = resolve_field_option(df, field_key)
    if option is None or option.source_column is None:
        raise KeyError(f"Fant ikke series-felt for key={field_key!r}")

    series = df[option.source_column]
    if field_key == TEXT_INVOICE_FIELD_KEY:
        raw_values = series.map(extract_text_invoice_number)
    else:
        raw_values = series.astype("string").fillna("").astype(str)

    rows: list[dict[str, object]] = []
    for idx, raw_value in raw_values.items():
        raw, prefix, number, width, family_key = _derive_components(raw_value)
        if not raw or number is None or family_key == "":
            continue
        rows.append(
            {
                "row_index": idx,
                "source_column": option.source_column,
                "field_key": option.key,
                "field_label": option.label,
                "raw_value": raw,
                "prefix": prefix,
                "number": int(number),
                "width": int(width) if width is not None else None,
                "family_key": family_key,
            }
        )

    return (option, pd.DataFrame(rows))
