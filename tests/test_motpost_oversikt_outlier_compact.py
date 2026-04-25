import pandas as pd

from src.audit_actions.motpost.konto_core import build_motpost_data
from src.audit_actions.motpost.konto_core import build_motpost_excel_workbook


def _find_cell(ws, text: str):
    for row in range(1, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            if ws.cell(row=row, column=col).value == text:
                return row, col
    raise AssertionError(f"Fant ikke {text!r} i arket {ws.title!r}")


def test_oversikt_outlier_table_has_compact_link_column_width():
    df = pd.DataFrame(
        [
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "3000",
                "Kontonavn": "Salg",
                "Beløp": -1000.0,
            },
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "1500",
                "Kontonavn": "Kundefordringer",
                "Beløp": 1000.0,
            },
        ]
    )

    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})

    ws = wb["Oversikt"]

    # Finn header-cellen "Fane" i outlier-tabellen (hyperlink-kolonne)
    _, doc_col_idx = _find_cell(ws, "Fane")
    col_letter = chr(ord("A") + doc_col_idx - 1)
    width = ws.column_dimensions[col_letter].width

    # Bredden skal være satt, og ikke bli «gigantisk» pga. hyperlink-formel.
    assert width is not None
    assert width <= 20
