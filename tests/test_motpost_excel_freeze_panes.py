import pandas as pd

from motpost.konto_core import build_motpost_data
from src.audit_actions.motpost.konto_core import build_motpost_excel_workbook


def test_freeze_panes_on_main_sheets():
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

    assert wb["Data"].freeze_panes == "A4"
    assert wb["Outlier - alle transaksjoner"].freeze_panes == "A4"

    # Oversikt: standard frys etter rad 1
    assert wb["Oversikt"].freeze_panes == "A2"

    # Detaljarket (kombinasjon #...): standard frys etter rad 1
    ws_detail = wb["#2"]
    assert ws_detail.freeze_panes == "A2"
