import pandas as pd

from motpost.konto_core import build_motpost_data
from motpost_konto_core import build_motpost_excel_workbook


def _find_row(ws, text: str) -> int:
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == text:
            return row
    raise AssertionError(f"Fant ikke rad med {text!r}")


def test_outlier_detail_has_bilagsoppsummering_with_amounts_per_bilag():
    df = pd.DataFrame(
        [
            # Bilag 1: kun kredit på valgt konto (3000)
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "3000",
                "Kontonavn": "Salg",
                "Beløp": -300.0,
            },
            {
                "Bilag": 1,
                "Dato": "2025-01-01",
                "Tekst": "Utgående faktura",
                "Konto": "1500",
                "Kontonavn": "Kundefordringer",
                "Beløp": 300.0,
            },
            # Bilag 2: både kredit og debet på valgt konto (netto != sum kredit)
            {
                "Bilag": 2,
                "Dato": "2025-01-02",
                "Tekst": "Utgående faktura",
                "Konto": "3000",
                "Kontonavn": "Salg",
                "Beløp": -200.0,
            },
            {
                "Bilag": 2,
                "Dato": "2025-01-02",
                "Tekst": "Utgående faktura",
                "Konto": "3000",
                "Kontonavn": "Salg",
                "Beløp": 50.0,
            },
            {
                "Bilag": 2,
                "Dato": "2025-01-02",
                "Tekst": "Utgående faktura",
                "Konto": "1500",
                "Kontonavn": "Kundefordringer",
                "Beløp": 150.0,
            },
        ]
    )

    data = build_motpost_data(df, {"3000"}, selected_direction="Kredit")

    # Kombinasjonen i dette datasettet blir "1500".
    wb = build_motpost_excel_workbook(data, combo_status_map={"1500": "outlier"})
    ws = wb["#2"]

    # Finn bilagsoppsummering og les ut kolonner
    title_row = _find_row(ws, "Bilagsoppsummering (B)")
    header_row = title_row + 2  # tittelrad + tom rad + header
    data_row = title_row + 3

    headers = [ws.cell(row=header_row, column=c).value for c in range(1, 20)]
    assert "Bilag" in headers
    sum_label = "Sum valgte kontoer (Kredit)"
    assert sum_label in headers
    assert "Netto valgte kontoer" in headers
    assert "Bilagslinjer" in headers

    col_sum = headers.index(sum_label) + 1
    col_netto = headers.index("Netto valgte kontoer") + 1
    col_link = headers.index("Bilagslinjer") + 1

    # Rad 1 = bilag 1
    assert ws.cell(row=data_row, column=1).value == "1"
    assert ws.cell(row=data_row, column=col_sum).value == -300.0
    assert ws.cell(row=data_row, column=col_netto).value == -300.0

    # Rad 2 = bilag 2
    assert ws.cell(row=data_row + 1, column=1).value == "2"
    assert ws.cell(row=data_row + 1, column=col_sum).value == -200.0
    assert ws.cell(row=data_row + 1, column=col_netto).value == -150.0

    # Link-kolonnen skal være hyperlink-formel (ikke lang tekst)
    link_val = ws.cell(row=data_row, column=col_link).value
    assert isinstance(link_val, str)
    assert link_val.startswith("=HYPERLINK(")

    # Beløpsformat på sum/netto
    assert ws.cell(row=data_row, column=col_sum).number_format == "#,##0.00"
    assert ws.cell(row=data_row, column=col_netto).number_format == "#,##0.00"
