"""consolidation.export -- Excel-eksport for konsolidering.

Produserer en arbeidsbok med:
  1. Konsernoppstilling (hoveddataark)
  2. Elimineringer (per-journal breakdown)
  3. TB - {selskap} (ett ark per selskap, mapped)
  4. Kontrollark (metadata, balansesjekk, hash)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from consolidation.elimination import journals_to_dataframe
from consolidation.models import CompanyTB, EliminationJournal, RunResult

logger = logging.getLogger(__name__)

# Stiler (same as analyse_regnskapsoppstilling_excel.py)
_TITLE_FILL = PatternFill("solid", fgColor="DDEBF7")
_HEADER_FILL = PatternFill("solid", fgColor="E2F0D9")
_SUM_FILL = PatternFill("solid", fgColor="F3F6F9")
_THIN_SIDE = Side(style="thin", color="D9D9D9")
_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)
_AMOUNT_FMT = "#,##0.00;[Red]-#,##0.00"


def _excel_col(idx: int) -> str:
    """1-indexed kolonne -> bokstav (1=A, 27=AA)."""
    result = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def build_consolidation_workbook(
    result_df: pd.DataFrame,
    companies: list[CompanyTB],
    eliminations: list[EliminationJournal],
    mapped_tbs: dict[str, pd.DataFrame],
    run_result: RunResult,
    *,
    client: str | None = None,
    year: str | None = None,
) -> Workbook:
    """Bygg komplett konsoliderings-arbeidsbok."""
    wb = Workbook()

    _build_konsernoppstilling(wb, result_df, client=client, year=year)
    _build_elimineringer(wb, eliminations)
    _build_company_sheets(wb, companies, mapped_tbs)
    _build_kontrollark(wb, run_result, companies, eliminations, client=client, year=year)

    return wb


def save_consolidation_workbook(
    path: str | Path,
    *,
    result_df: pd.DataFrame,
    companies: list[CompanyTB],
    eliminations: list[EliminationJournal],
    mapped_tbs: dict[str, pd.DataFrame],
    run_result: RunResult,
    client: str | None = None,
    year: str | None = None,
) -> str:
    """Bygg og lagre arbeidsbok. Returnerer filstien."""
    wb = build_consolidation_workbook(
        result_df, companies, eliminations, mapped_tbs, run_result,
        client=client, year=year,
    )
    p = Path(path)
    if p.suffix.lower() != ".xlsx":
        p = p.with_suffix(".xlsx")
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(p))
    logger.info("Saved consolidation workbook -> %s", p)
    return str(p)


# ---------------------------------------------------------------------------
# Ark 1: Konsernoppstilling
# ---------------------------------------------------------------------------

def _build_konsernoppstilling(
    wb: Workbook,
    result_df: pd.DataFrame,
    *,
    client: str | None = None,
    year: str | None = None,
) -> None:
    ws = wb.active
    ws.title = "Konsernoppstilling"

    # Tittel
    title_parts = ["Konsernoppstilling"]
    if client:
        title_parts.append(str(client))
    if year:
        title_parts.append(str(year))
    title = " - ".join(title_parts)

    # Finn alle kolonner
    meta_cols = {"regnr", "regnskapslinje", "sumpost", "formel"}
    data_cols = [c for c in result_df.columns if c not in meta_cols]
    all_headers = ["Nr", "Regnskapslinje"] + data_cols
    total_cols = len(all_headers)
    last_col_letter = _excel_col(total_cols)

    # Tittelrad
    ws.merge_cells(f"A1:{last_col_letter}1")
    ws["A1"] = title
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = Alignment(horizontal="left")
    ws["A1"].fill = _TITLE_FILL

    ws.merge_cells(f"A2:{last_col_letter}2")
    ws["A2"] = f"Generert {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    ws["A2"].font = Font(italic=True, color="666666")

    # Headers (rad 4)
    header_row = 4
    for col_idx, header in enumerate(all_headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center")

    # Data
    data_row = header_row + 1
    for _, row in result_df.iterrows():
        regnr = int(row.get("regnr", 0))
        is_sum = bool(row.get("sumpost", False))
        values = [regnr, str(row.get("regnskapslinje", "") or "")]
        for dc in data_cols:
            values.append(_safe_float(row.get(dc)))

        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=data_row, column=col_idx, value=value)
            cell.border = _BORDER
            if col_idx == 2:
                cell.alignment = Alignment(horizontal="left")
            else:
                cell.alignment = Alignment(horizontal="right")
            if col_idx >= 3:
                cell.number_format = _AMOUNT_FMT
            if is_sum:
                cell.font = Font(bold=True)
                cell.fill = _SUM_FILL

        data_row += 1

    # Freeze + filter
    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:{last_col_letter}{max(data_row - 1, 4)}"

    # Kolonnebredder
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 40
    for i in range(3, total_cols + 1):
        ws.column_dimensions[_excel_col(i)].width = 16


# ---------------------------------------------------------------------------
# Ark 2: Elimineringer
# ---------------------------------------------------------------------------

def _build_elimineringer(
    wb: Workbook,
    eliminations: list[EliminationJournal],
) -> None:
    ws = wb.create_sheet("Elimineringer")

    if not eliminations:
        ws["A1"] = "Ingen elimineringer registrert."
        return

    headers = ["Journal", "Regnr", "Selskap", "Beloep", "Beskrivelse"]
    row = 1

    for journal in eliminations:
        # Journalnavn som header
        cell = ws.cell(row=row, column=1, value=journal.name)
        cell.font = Font(bold=True, size=12)
        balanced_text = "Balansert" if journal.is_balanced else f"UBALANSE ({journal.net:.2f})"
        ws.cell(row=row, column=3, value=balanced_text)
        row += 1

        # Kolonneheaders
        for col_idx, h in enumerate(headers, start=1):
            cell = ws.cell(row=row, column=col_idx, value=h)
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.border = _BORDER
        row += 1

        # Linjer
        for line in journal.lines:
            ws.cell(row=row, column=1, value=journal.name).border = _BORDER
            ws.cell(row=row, column=2, value=line.regnr).border = _BORDER
            ws.cell(row=row, column=3, value=line.company_id).border = _BORDER
            c = ws.cell(row=row, column=4, value=line.amount)
            c.number_format = _AMOUNT_FMT
            c.border = _BORDER
            ws.cell(row=row, column=5, value=line.description).border = _BORDER
            row += 1

        row += 1  # blank linje mellom journaler

    for col, w in {"A": 20, "B": 10, "C": 20, "D": 16, "E": 30}.items():
        ws.column_dimensions[col].width = w


# ---------------------------------------------------------------------------
# Ark 3..N: TB per selskap
# ---------------------------------------------------------------------------

def _build_company_sheets(
    wb: Workbook,
    companies: list[CompanyTB],
    mapped_tbs: dict[str, pd.DataFrame],
) -> None:
    for company in companies:
        tb = mapped_tbs.get(company.company_id)
        if tb is None or tb.empty:
            continue

        sheet_name = f"TB - {company.name}"[:31]  # Excel 31-char limit
        ws = wb.create_sheet(sheet_name)

        # Velg relevante kolonner
        show_cols = []
        for c in ["konto", "kontonavn", "regnr", "ib", "ub", "netto"]:
            if c in tb.columns:
                show_cols.append(c)

        # Headers
        for col_idx, col in enumerate(show_cols, start=1):
            cell = ws.cell(row=1, column=col_idx, value=col.capitalize())
            cell.font = Font(bold=True)
            cell.fill = _HEADER_FILL
            cell.border = _BORDER

        # Data
        for row_idx, (_, row) in enumerate(tb.iterrows(), start=2):
            for col_idx, col in enumerate(show_cols, start=1):
                val = row.get(col)
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.border = _BORDER
                if col in ("ib", "ub", "netto"):
                    cell.number_format = _AMOUNT_FMT

        ws.freeze_panes = "A2"

        # Kolonnebredder
        for i, col in enumerate(show_cols, start=1):
            if col == "kontonavn":
                ws.column_dimensions[_excel_col(i)].width = 35
            elif col in ("ib", "ub", "netto"):
                ws.column_dimensions[_excel_col(i)].width = 16
            else:
                ws.column_dimensions[_excel_col(i)].width = 12


# ---------------------------------------------------------------------------
# Ark N+1: Kontrollark
# ---------------------------------------------------------------------------

def _build_kontrollark(
    wb: Workbook,
    run_result: RunResult,
    companies: list[CompanyTB],
    eliminations: list[EliminationJournal],
    *,
    client: str | None = None,
    year: str | None = None,
) -> None:
    ws = wb.create_sheet("Kontrollark")

    rows = [
        ("Klient", client or ""),
        ("Aar", year or ""),
        ("Kjoert", datetime.fromtimestamp(run_result.run_at).strftime("%d.%m.%Y %H:%M:%S")),
        ("Run ID", run_result.run_id),
        ("Antall selskaper", len(run_result.company_ids)),
        ("Selskaper", ", ".join(c.name for c in companies if c.company_id in run_result.company_ids)),
        ("Antall elimineringer", len(eliminations)),
        ("", ""),
    ]

    # Balansesjekk per journal
    for j in eliminations:
        status = "Balansert" if j.is_balanced else f"UBALANSE ({j.net:.2f})"
        rows.append((f"Eliminering: {j.name}", status))

    rows.append(("", ""))
    rows.append(("Resultat-hash (SHA256)", run_result.result_hash))

    # Advarsler
    if run_result.warnings:
        rows.append(("", ""))
        rows.append(("Advarsler", ""))
        for w in run_result.warnings:
            rows.append(("", w))

    for row_idx, (key, value) in enumerate(rows, start=1):
        cell_key = ws.cell(row=row_idx, column=1, value=key)
        cell_key.font = Font(bold=True) if key else Font()
        ws.cell(row=row_idx, column=2, value=value)

    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 60


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(v: object) -> float:
    try:
        f = float(v)
        return f if f == f else 0.0  # NaN check
    except (TypeError, ValueError):
        return 0.0
