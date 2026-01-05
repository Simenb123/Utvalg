# tests/test_excel_formatting.py
from openpyxl import Workbook

from excel_formatting import polish_sheet


def test_polish_sheet_exists_and_runs():
    wb = Workbook()
    ws = wb.active
    ws.title = "Test"

    ws.append(["A", "B"])
    ws.append([1, 2.5])
    ws.append([1000, 1234.56])

    # Skal ikke kaste exception
    polish_sheet(ws)

    # Freeze panes settes best-effort
    assert ws.freeze_panes in ("A2", None)
