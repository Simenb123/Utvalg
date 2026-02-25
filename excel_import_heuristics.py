# -*- coding: utf-8 -*-
"""
excel_import_heuristics.py
--------------------------
Interne heuristikker for robust Excel-import i Utvalg.

Denne modulen er bevisst uten sideeffekter (ingen fil-IO). Den brukes av
excel_importer.py til å:
- finne header-rad (hvis ikke første rad)
- normalisere kolonnenavn
- (best effort) inferere manglende Konto/Kontonavn når header er tom/"Unnamed"

Inspirert av IBUB-prosjektet (SaldoMatcher) – tilpasset Utvalg.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence
import re

import pandas as pd

# Typiske ord som forekommer i hovedbok-eksport
ACCOUNT_PATTERNS = [
    "konto",
    "kontonr",
    "konto nr",
    "kontonummer",
    "account",
    "accountno",
    "account no",
    "acct",
]

NAME_PATTERNS = [
    "kontonavn",
    "konto navn",
    "account name",
    "description",
    "navn",
]

VOUCHER_PATTERNS = [
    "bilag",
    "bilagsnr",
    "bilagsnummer",
    "voucher",
    "document",
    "journal",
]

AMOUNT_PATTERNS = [
    "beløp",
    "belop",
    "amount",
    "sum",
    "bokført",
    "bokfort",
    "debet",
    "kredit",
    "debit",
    "credit",
]

DATE_PATTERNS = [
    "dato",
    "bilagsdato",
    "date",
]

TEXT_PATTERNS = [
    "tekst",
    "beskrivelse",
    "text",
]


def norm_token(value: Any) -> str:
    """Normaliser token for heuristikk (ikke for visning)."""
    return str(value).strip().lower().replace(" ", "").replace("_", "")


def row_contains_patterns(
    cells: Sequence[Any],
    patterns: Sequence[str],
    *,
    strict_equals: Optional[str] = None,
) -> bool:
    norms = [norm_token(c) for c in cells]
    for pat in patterns:
        p = norm_token(pat)
        if not p:
            continue
        if strict_equals is not None and p == norm_token(strict_equals):
            # 'konto' er typisk et eget header-ord. Unngå f.eks. 'sparekonto'
            if p in norms:
                return True
        else:
            for v in norms:
                if p in v:
                    return True
    return False


def detect_header_row_df(df_raw: pd.DataFrame, max_scan: int = 40) -> Optional[int]:
    """Finn sannsynlig header-rad i et rått (header=None) DataFrame."""
    best_idx: Optional[int] = None
    best_score: float = 0.0

    n_rows = min(len(df_raw), max_scan)
    for idx in range(n_rows):
        row = df_raw.iloc[idx]
        vals = [v for v in row.tolist() if pd.notna(v) and str(v).strip() != ""]
        if len(vals) < 2:
            continue

        ser = pd.Series(vals)
        num_frac = pd.to_numeric(ser, errors="coerce").notna().mean()

        # Header-rad bør ikke være nesten bare tall
        if num_frac > 0.85:
            continue

        cells = row.tolist()

        score = 0.0
        if row_contains_patterns(cells, ACCOUNT_PATTERNS, strict_equals="konto"):
            score += 6.0
        if row_contains_patterns(cells, VOUCHER_PATTERNS):
            score += 5.0
        if row_contains_patterns(cells, AMOUNT_PATTERNS):
            score += 5.0
        if row_contains_patterns(cells, DATE_PATTERNS):
            score += 2.0
        if row_contains_patterns(cells, TEXT_PATTERNS):
            score += 1.0
        if row_contains_patterns(cells, NAME_PATTERNS):
            score += 1.0

        if num_frac < 0.4:
            score += 1.0

        score += min(len(vals), 12) / 12.0

        if score > best_score:
            best_score = score
            best_idx = idx

    return best_idx if best_score > 0 else None


def first_non_empty_row(df_raw: pd.DataFrame, max_scan: int = 80) -> int:
    n_rows = min(len(df_raw), max_scan)
    for i in range(n_rows):
        try:
            if df_raw.iloc[i].notna().any():
                return i
        except Exception:
            continue
    return 0


def clean_header_cell(value: Any, idx: int) -> str:
    """Normaliser kolonnenavn til stabilt (strippet) navn."""
    if value is None:
        return f"Unnamed: {idx}"
    if isinstance(value, float) and value != value:  # NaN
        return f"Unnamed: {idx}"
    s = str(value)
    s = s.replace("\u00a0", " ").replace("\n", " ").replace("\r", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if s == "" or s.lower() in {"nan", "none"}:
        return f"Unnamed: {idx}"
    return s


def is_empty_header(col_name: str) -> bool:
    s = str(col_name).strip().lower()
    if s in {"", "nan", "none"}:
        return True
    return s.startswith("unnamed")


def looks_like_kontonr(value: Any) -> bool:
    """Heuristikk: 3–8 siffer (med ev. mellomrom)."""
    s = str(value).strip().replace("\u00a0", " ")
    if not s:
        return False
    s = s.replace(" ", "")
    m = re.search(r"\d+", s)
    if not m:
        return False
    digits = m.group(0)
    return 3 <= len(digits) <= 8


def infer_missing_konto_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Best-effort heuristikk for ark der kontokolonner mangler headernavn ("Unnamed").

    Vi gjør kun inngrep hvis vi ikke allerede har en tydelig konto-kolonne.
    """
    cols = list(df.columns)
    has_konto = any(norm_token(c) in {"konto", "kontonr", "kontonummer"} for c in cols)
    if has_konto:
        return df

    empty_indices = [i for i, c in enumerate(cols) if is_empty_header(str(c))]
    konto_idx: Optional[int] = None

    for idx in empty_indices:
        s = df.iloc[:, idx].dropna()
        if len(s) < 5:
            continue
        matches = s.astype(str).map(looks_like_kontonr)
        if matches.mean() >= 0.8:
            konto_idx = idx
            break

    if konto_idx is None:
        return df

    df2 = df.copy()
    new_cols = list(df2.columns)
    new_cols[konto_idx] = "Konto"

    kandidat_indices: List[int] = []
    if konto_idx - 1 >= 0:
        kandidat_indices.append(konto_idx - 1)
    if konto_idx + 1 < len(new_cols):
        kandidat_indices.append(konto_idx + 1)

    best_idx: Optional[int] = None
    best_text_frac = 0.0

    for idx in kandidat_indices:
        s = df2.iloc[:, idx].dropna()
        if len(s) < 5:
            continue
        as_num = pd.to_numeric(s, errors="coerce")
        text_frac = as_num.isna().mean()
        if text_frac > best_text_frac:
            best_text_frac = text_frac
            best_idx = idx

    if best_idx is not None and is_empty_header(str(new_cols[best_idx])):
        new_cols[best_idx] = "Kontonavn"

    df2.columns = new_cols
    return df2
