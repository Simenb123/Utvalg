# -*- coding: utf-8 -*-
"""
excel_importer.py
-----------------
Robust Excel-innlesing for Utvalg (hovedbok / transaksjoner).

Ansvar:
- Fil-IO mot Excel via pandas/openpyxl
- Autodetektere ark (sheet) og header-rad
- Returnere DataFrame med normaliserte kolonnenavn (stabil mapping i UI)

Heuristikkene ligger i excel_import_heuristics.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple
import os

import pandas as pd

from .import_heuristics import (
    ACCOUNT_PATTERNS,
    AMOUNT_PATTERNS,
    DATE_PATTERNS,
    VOUCHER_PATTERNS,
    clean_header_cell,
    detect_header_row_df,
    first_non_empty_row,
    infer_missing_konto_headers,
    norm_token,
    row_contains_patterns,
    is_empty_header,
)

try:
    from logger import get_logger  # type: ignore
except Exception:  # pragma: no cover
    import logging

    def get_logger():  # type: ignore
        return logging.getLogger(__name__)

log = get_logger()

_EXCEL_EXTS = (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls")


@dataclass(frozen=True)
class ExcelLayout:
    sheet_name: str | int
    header_row: int
    columns: List[str]
    score: int


def infer_excel_sheet_and_headers(
    path: str,
    desired_columns: Optional[Sequence[str]] = None,
    *,
    preferred_sheet: Optional[str | int] = None,
    preferred_header_row: Optional[int] = None,
    max_scan_rows: int = 60,
    max_sheets: int = 12,
) -> Tuple[str | int, int, List[str]]:
    """
    Autodetekter hvilket ark og hvilken rad som er header i en Excel-fil.

    Returns:
        (sheet_name, header_row_index, columns)

    NB: Ved feil returnerer vi (0, 0, []) slik at kallende kode kan
    falle tilbake til standard innlesing.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in _EXCEL_EXTS:
        return 0, 0, []

    desired_norm = set()
    if desired_columns:
        desired_norm = {norm_token(c) for c in desired_columns if str(c).strip() != ""}

    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        sheet_names: List[str] = list(xls.sheet_names)
    except Exception as e:  # pragma: no cover
        log.info("ExcelFile feilet, faller tilbake: %s", e)
        return 0, 0, []

    if preferred_sheet is not None:
        if isinstance(preferred_sheet, int):
            try:
                sheet_names = [sheet_names[int(preferred_sheet)]]
            except Exception:
                sheet_names = sheet_names[:1]
        else:
            sheet_names = [s for s in sheet_names if s == preferred_sheet] or sheet_names[:1]

    best: Optional[ExcelLayout] = None

    for sheet in sheet_names[:max_sheets]:
        try:
            df_raw = pd.read_excel(
                path,
                sheet_name=sheet,
                header=None,
                nrows=max_scan_rows,
                engine="openpyxl",
                dtype=object,
            )
        except Exception:
            continue

        if df_raw is None or df_raw.empty:
            continue

        header_idx = preferred_header_row if preferred_header_row is not None else detect_header_row_df(df_raw)
        if header_idx is None:
            header_idx = first_non_empty_row(df_raw)

        raw_header = df_raw.iloc[int(header_idx)].tolist()
        cols = [clean_header_cell(v, i) for i, v in enumerate(raw_header)]

        df_candidate = df_raw.iloc[int(header_idx) + 1 :].copy()
        df_candidate.columns = cols
        df_candidate = df_candidate.dropna(axis=1, how="all").dropna(how="all")
        df_candidate = infer_missing_konto_headers(df_candidate)
        cols2 = [str(c) for c in df_candidate.columns]

        # Pattern-score (hvor "hovedbok"-aktig)
        pattern_score = 0
        if row_contains_patterns(raw_header, ACCOUNT_PATTERNS, strict_equals="konto"):
            pattern_score += 4
        if row_contains_patterns(raw_header, VOUCHER_PATTERNS):
            pattern_score += 3
        if row_contains_patterns(raw_header, AMOUNT_PATTERNS):
            pattern_score += 3
        if row_contains_patterns(raw_header, DATE_PATTERNS):
            pattern_score += 1

        match_count = 0
        if desired_norm:
            col_norms = {norm_token(c) for c in cols2}
            match_count = len(desired_norm.intersection(col_norms))

        non_empty_headers = sum(0 if is_empty_header(c) else 1 for c in cols2)

        score = match_count * 1000 + pattern_score * 10 + non_empty_headers
        layout = ExcelLayout(sheet_name=sheet, header_row=int(header_idx), columns=cols2, score=score)

        if best is None or layout.score > best.score:
            best = layout

    if best is None:
        return 0, 0, []
    log.info("Excel autodetektert ark/header: ark=%s, header_row=%s, score=%s", best.sheet_name, best.header_row, best.score)
    return best.sheet_name, best.header_row, best.columns


def read_excel_robust(
    path: str,
    desired_columns: Optional[Sequence[str]] = None,
    *,
    excel_sheet_name: Optional[str | int] = None,
    excel_header_row: Optional[int] = None,
) -> pd.DataFrame:
    """
    Leser Excel på en robust måte (ark + header autodetekteres).

    desired_columns:
        Liste over kildenavn vi ønsker å lese (fra mapping). Brukes både til
        å velge riktig ark og for å begrense kolonner ved innlesing.
    """
    sheet_name, header_row, columns = infer_excel_sheet_and_headers(
        path,
        desired_columns=desired_columns,
        preferred_sheet=excel_sheet_name,
        preferred_header_row=excel_header_row,
    )

    # Hvis heuristikken feilet, fall tilbake til standard pd.read_excel
    if columns == [] and excel_sheet_name is None and excel_header_row is None:
        log.info("Excel header-detektering feilet; faller tilbake til standard innlesing.")
        try:
            return pd.read_excel(path, engine="openpyxl", dtype=object)
        except Exception:
            return pd.read_excel(path, dtype=object)

    # Map desired columns -> indeks (0-basert)
    usecols_idx: Optional[List[int]] = None
    if desired_columns:
        desired_norm = [norm_token(c) for c in desired_columns if str(c).strip() != ""]
        col_norm = [norm_token(c) for c in columns]
        idxs: List[int] = []
        for d in desired_norm:
            try:
                idxs.append(col_norm.index(d))
            except ValueError:
                continue
        if idxs:
            usecols_idx = sorted(set(idxs))

    try:
        df = pd.read_excel(
            path,
            sheet_name=sheet_name,
            header=header_row,
            engine="openpyxl",
            usecols=usecols_idx,
            dtype=object,
        )
    except Exception as e:
        log.info("Robust Excel read feilet (%s). Faller tilbake til full lesing.", e)
        df = pd.read_excel(path, sheet_name=sheet_name, header=header_row, engine="openpyxl", dtype=object)

    # Normaliser kolonnenavn slik at de matcher det UI viser
    df.columns = [clean_header_cell(c, i) for i, c in enumerate(list(df.columns))]

    # Heuristikk for manglende kontoheaders (best effort)
    try:
        df = infer_missing_konto_headers(df)
    except Exception:
        pass

    # Rydd vekk helt tomme rader/kolonner
    df = df.dropna(how="all").dropna(axis=1, how="all")

    return df
