from __future__ import annotations

from datetime import datetime

import pandas as pd

from motpost_konto_core import build_motpost_data, build_motpost_excel_workbook


def _find_table_by_required_headers(ws, required_headers: set[str]):
    """Find the first openpyxl Table whose header row contains all required_headers."""

    for table in ws.tables.values():
        ref = table.ref
        start_cell, end_cell = ref.split(":")
        start_row = ws[start_cell].row
        start_col = ws[start_cell].column
        end_row = ws[end_cell].row
        end_col = ws[end_cell].column

        headers = [ws.cell(row=start_row, column=c).value for c in range(start_col, end_col + 1)]
        header_set = {str(h) for h in headers if h is not None}
        if required_headers.issubset(header_set):
            return table

    raise AssertionError(f"Fant ingen tabell med headers: {required_headers}")


def _table_bounds(ws, table):
    start_cell, end_cell = table.ref.split(":")
    sr = ws[start_cell].row
    sc = ws[start_cell].column
    er = ws[end_cell].row
    ec = ws[end_cell].column
    return sr, sc, er, ec


def test_excel_workbook_data_sheet_has_summary_rows_and_selected_account_splits():
    """Arbeidspapir-eksporten skal ha summeringsrad og Kredit/Debet/Netto i Data-arket."""

    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 1, 2, 2],
            "Dato": [
                datetime(2025, 1, 1),
                datetime(2025, 1, 1),
                datetime(2025, 1, 1),
                datetime(2025, 1, 2),
                datetime(2025, 1, 2),
            ],
            "Tekst": ["", "", "", "", ""],
            "Konto": [3000, 3000, 1500, 3000, 2700],
            "Kontonavn": ["Salg", "Salg", "Kundefordringer", "Salg", "MVA"],
            "Beløp": [-1000.0, 200.0, 800.0, -500.0, 500.0],
        }
    )

    data = build_motpost_data(df, ["3000"], selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data)

    assert "Oversikt" in wb.sheetnames
    assert "Data" in wb.sheetnames
    assert "Outlier - alle transaksjoner" in wb.sheetnames
    assert "Kombinasjoner" not in wb.sheetnames

    ws = wb["Data"]

    # --- Valgte kontoer (populasjon) ---
    table_sel = _find_table_by_required_headers(ws, {"Konto", "Kredit", "Debet", "Netto"})
    sr, sc, er, ec = _table_bounds(ws, table_sel)
    header_row = sr

    headers = [ws.cell(row=header_row, column=c).value for c in range(sc, ec + 1)]
    header_to_col = {str(h): c for h, c in zip(headers, range(sc, ec + 1)) if h is not None}

    # Finn rad for konto 3000
    konto_col = header_to_col["Konto"]
    row_3000 = None
    for r in range(sr + 1, er + 1):
        if str(ws.cell(row=r, column=konto_col).value) == "3000":
            row_3000 = r
            break
    assert row_3000 is not None

    assert ws.cell(row=row_3000, column=header_to_col["Kredit"]).value == -1500.0
    assert ws.cell(row=row_3000, column=header_to_col["Debet"]).value == 200.0
    assert ws.cell(row=row_3000, column=header_to_col["Netto"]).value == -1300.0

    # Summeringsrad ligger under tabellen
    summary_row = er + 1
    # Tabellenavn på Data-arket første tabell er TData
    assert ws.cell(row=summary_row, column=header_to_col["Kredit"]).value == "=SUBTOTAL(109,TData[Kredit])"
    assert ws.cell(row=summary_row, column=header_to_col["Debet"]).value == "=SUBTOTAL(109,TData[Debet])"
    assert ws.cell(row=summary_row, column=header_to_col["Netto"]).value == "=SUBTOTAL(109,TData[Netto])"

    # --- Statusoppsummering ---
    # Net-kolonnen i statusoppsummeringen skal hete "Netto kredit" når retning=Kredit.
    table_status = _find_table_by_required_headers(ws, {"Status", "Sum valgte kontoer", "Antall kombinasjoner"})
    sr2, sc2, er2, ec2 = _table_bounds(ws, table_status)
    status_headers = [ws.cell(row=sr2, column=c).value for c in range(sc2, ec2 + 1)]
    assert "Netto kredit" in {str(h) for h in status_headers if h is not None}
