"""
excel_formatting.py
-------------------
Lett etterbehandling av Excel-filer skrevet via pandas + openpyxl:

- Frys topprekke
- Auto-kolonnebredde (basert på et utvalg rader)
- Tallformat på beløpslignende kolonner
"""

from __future__ import annotations
from typing import Iterable

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


def _autosize(ws: Worksheet, sample_rows: int = 400) -> None:
    dims = {}
    max_r = min(ws.max_row, sample_rows)
    for row in ws.iter_rows(min_row=1, max_row=max_r, values_only=True):
        for i, v in enumerate(row, 1):
            l = len(str(v)) if v is not None else 0
            dims[i] = max(dims.get(i, 0), l)
    for i, w in dims.items():
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(65, w + 2))


def _format_number_columns(ws: Worksheet) -> None:
    # Finn kolonner som sannsynligvis er beløp/summer
    header = [c.value for c in ws[1]]
    num_cols = set()
    patterns = ("beløp", "belop", "amount", "sum", "debet", "debit", "kredit", "credit", "saldo", "value")
    for j, name in enumerate(header, start=1):
        if isinstance(name, str) and any(p in name.lower() for p in patterns):
            num_cols.add(j)
    # suppler med faktisk numeriske verdier i noen rader
    for j in range(1, ws.max_column + 1):
        for r in range(2, min(ws.max_row, 100) + 1):
            v = ws.cell(row=r, column=j).value
            if isinstance(v, (int, float)):
                num_cols.add(j)
                break

    # Excel håndterer lokal desimal/gruppe-separator automatisk.
    # '#,##0.00' i norsk Excel vises som '# ##0,00'.
    fmt = '#,##0.00'
    for j in num_cols:
        for r in range(2, ws.max_row + 1):
            cell = ws.cell(row=r, column=j)
            if isinstance(cell.value, (int, float)):
                cell.number_format = fmt


def polish_excel_writer(writer) -> None:
    """Kall dette inne i with pd.ExcelWriter(...) som 'best effort polish'."""
    wb = writer.book
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        _autosize(ws)
        _format_number_columns(ws)
