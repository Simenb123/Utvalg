# excel_formatting.py
from __future__ import annotations

from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet


def _autosize_columns(ws: Worksheet, max_rows_scan: int = 200) -> None:
    """
    Grov autosize av kolonner basert på innhold.
    - Skanner maks `max_rows_scan` rader for å unngå treghet på store ark.
    """
    # openpyxl har ingen "auto-fit" i Excel-forstand, så vi estimerer bredde.
    max_row = min(ws.max_row or 1, max_rows_scan)
    max_col = ws.max_column or 1

    for col in range(1, max_col + 1):
        letter = get_column_letter(col)
        max_len = 0
        for row in range(1, max_row + 1):
            cell = ws.cell(row=row, column=col)
            v = cell.value
            if v is None:
                continue
            s = str(v)
            if len(s) > max_len:
                max_len = len(s)

        # Litt padding – og cap så det ikke blir ekstremt bredt
        ws.column_dimensions[letter].width = min(max(10, max_len + 2), 60)


def _format_number_columns(ws: Worksheet) -> None:
    """
    Setter Excel number_format på kolonner som ser numeriske ut.
    Dette er best-effort (ingen hard feiling).
    """
    try:
        header_row = 1
        max_col = ws.max_column or 1
        max_row = ws.max_row or 1

        # Finn kandidater: kolonner der majoriteten av de første N radene er tall
        scan_rows = min(max_row, 200)
        for col in range(1, max_col + 1):
            numeric_hits = 0
            total = 0
            for row in range(header_row + 1, scan_rows + 1):
                v = ws.cell(row=row, column=col).value
                if v is None or v == "":
                    continue
                total += 1
                if isinstance(v, (int, float)):
                    numeric_hits += 1
            if total == 0:
                continue

            ratio = numeric_hits / total
            if ratio >= 0.8:
                # Standard norsk-lignende: tusenskiller + 2 desimaler
                for row in range(header_row + 1, max_row + 1):
                    ws.cell(row=row, column=col).number_format = "#,##0.00"
    except Exception:
        # Best-effort – aldri krasj eksport pga format
        return


def polish_sheet(ws: Worksheet) -> None:
    """
    Polerer ETT worksheet (til bruk i controller_export).
    Dette var tidligere en manglende funksjon og ga ImportError i pytest.
    """
    try:
        # Lås topp-rad
        ws.freeze_panes = "A2"
    except Exception:
        pass

    _autosize_columns(ws)
    _format_number_columns(ws)


def polish_excel_writer(writer) -> None:
    """
    Polerer alle sheets i en pandas.ExcelWriter (openpyxl engine).
    """
    try:
        for _name, ws in getattr(writer, "sheets", {}).items():
            if isinstance(ws, Worksheet):
                polish_sheet(ws)
    except Exception:
        # Best-effort
        return
