from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side


_TITLE_FILL = PatternFill("solid", fgColor="DDEBF7")
_HEADER_FILL = PatternFill("solid", fgColor="E2F0D9")
_SUM_FILL = PatternFill("solid", fgColor="F3F6F9")
_THIN_SIDE = Side(style="thin", color="D9D9D9")
_BORDER = Border(left=_THIN_SIDE, right=_THIN_SIDE, top=_THIN_SIDE, bottom=_THIN_SIDE)
_AMOUNT_FMT = '#,##0.00;[Red]-#,##0.00'
_INT_FMT = '#,##0'


def build_regnskapsoppstilling_workbook(
    rl_df: pd.DataFrame,
    *,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    transactions_df: Optional[pd.DataFrame] = None,
    client: str | None = None,
    year: str | int | None = None,
) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "Regnskapsoppstilling"

    title_parts = ["Regnskapsoppstilling"]
    if client:
        title_parts.append(str(client))
    if year not in {None, ""}:
        title_parts.append(str(year))
    title = " - ".join(title_parts)

    ws.merge_cells("A1:F1")
    ws["A1"] = title
    ws["A1"].font = Font(size=14, bold=True)
    ws["A1"].alignment = Alignment(horizontal="left")
    ws["A1"].fill = _TITLE_FILL

    ws.merge_cells("A2:F2")
    ws["A2"] = f"Generert {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    ws["A2"].font = Font(italic=True, color="666666")
    ws["A2"].alignment = Alignment(horizontal="left")

    headers = ["Nr", "Regnskapslinje", "IB", "Endring", "UB", "Antall"]
    header_row = 4
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center")

    sum_regnr = _sumline_regnr(regnskapslinjer)
    data_row = header_row + 1
    for _, row in rl_df.iterrows():
        regnr = _safe_int(row.get("regnr"))
        values = [
            regnr,
            str(row.get("regnskapslinje", "") or ""),
            _safe_float(row.get("IB")),
            _safe_float(row.get("Endring")),
            _safe_float(row.get("UB")),
            _safe_int(row.get("Antall")),
        ]
        is_sum = regnr in sum_regnr
        for col_idx, value in enumerate(values, start=1):
            cell = ws.cell(row=data_row, column=col_idx, value=value)
            cell.border = _BORDER
            if col_idx == 2:
                cell.alignment = Alignment(horizontal="left")
            else:
                cell.alignment = Alignment(horizontal="right")
            if col_idx in {3, 4, 5}:
                cell.number_format = _AMOUNT_FMT
            elif col_idx == 6:
                cell.number_format = _INT_FMT
            if is_sum:
                cell.font = Font(bold=True)
                cell.fill = _SUM_FILL
        data_row += 1

    ws.freeze_panes = "A5"
    ws.auto_filter.ref = f"A4:F{max(data_row - 1, 4)}"
    for col, width in {"A": 8, "B": 40, "C": 16, "D": 16, "E": 16, "F": 10}.items():
        ws.column_dimensions[col].width = width

    if isinstance(transactions_df, pd.DataFrame) and not transactions_df.empty:
        _append_transactions_sheet(wb, transactions_df)

    return wb


def save_regnskapsoppstilling_workbook(
    path: str | Path,
    *,
    rl_df: pd.DataFrame,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    transactions_df: Optional[pd.DataFrame] = None,
    client: str | None = None,
    year: str | int | None = None,
) -> str:
    out = Path(path)
    if out.suffix.lower() != ".xlsx":
        out = out.with_suffix(".xlsx")
    out.parent.mkdir(parents=True, exist_ok=True)

    wb = build_regnskapsoppstilling_workbook(
        rl_df,
        regnskapslinjer=regnskapslinjer,
        transactions_df=transactions_df,
        client=client,
        year=year,
    )
    wb.save(out)
    return str(out)


def _append_transactions_sheet(wb: Workbook, df: pd.DataFrame) -> None:
    ws = wb.create_sheet("Transaksjoner")
    headers = [str(c) for c in df.columns]
    for col_idx, header in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = Font(bold=True)
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center")

    for row_idx, (_, row) in enumerate(df.iterrows(), start=2):
        for col_idx, header in enumerate(headers, start=1):
            value = row.get(header)
            cell = ws.cell(row=row_idx, column=col_idx, value=None if pd.isna(value) else value)
            cell.border = _BORDER
            if header in {"Beløp", "MVA-beløp", "Valutabeløp"}:
                cell.number_format = _AMOUNT_FMT
                cell.alignment = Alignment(horizontal="right")
            else:
                cell.alignment = Alignment(horizontal="left")

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{_excel_col(len(headers))}{max(len(df.index) + 1, 1)}"
    widths = _suggest_widths(df)
    for idx, header in enumerate(headers, start=1):
        ws.column_dimensions[_excel_col(idx)].width = widths.get(header, 16)


def _sumline_regnr(regnskapslinjer: Optional[pd.DataFrame]) -> set[int]:
    if regnskapslinjer is None or regnskapslinjer.empty:
        return set()
    try:
        from regnskap_mapping import normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception:
        return set()
    return {int(v) for v in regn.loc[regn["sumpost"], "regnr"].astype(int).tolist()}


def _safe_float(value: object) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def _safe_int(value: object) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _excel_col(idx: int) -> str:
    out = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out or "A"


def _suggest_widths(df: pd.DataFrame) -> dict[str, float]:
    widths: dict[str, float] = {}
    for col in df.columns:
        header = str(col)
        max_len = len(header)
        sample = df[col].head(200).tolist()
        for value in sample:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                continue
            max_len = max(max_len, len(str(value)))
        widths[header] = float(max(10, min(max_len + 2, 40)))
    return widths
