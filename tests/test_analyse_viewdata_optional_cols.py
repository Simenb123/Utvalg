from __future__ import annotations

import pandas as pd

import analyse_viewdata


def test_build_transactions_view_df_includes_optional_mva_and_currency_columns() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [101, 102],
            "Beløp": [1000.0, -50.0],
            "Tekst": ["Salg", "Kjøp"],
            "Konto": ["3000", "2400"],
            "Kontonavn": ["Salg", "Leverandørgjeld"],
            "Dato": ["2025-01-02", "03.01.2025"],
            "MVA-kode": [1, 0],
            "MVA-beløp": [250.0, None],
            "MVA-prosent": [0.25, 25],  # støtt både brøk og «25»
            "Valuta": ["nok", "EUR"],
            "Valutabeløp": [1000.0, -50.0],
        }
    )

    tx_cols = list(analyse_viewdata.DEFAULT_TX_COLS) + [
        "MVA-kode",
        "MVA-beløp",
        "MVA-prosent",
        "Valuta",
        "Valutabeløp",
    ]

    out = analyse_viewdata.build_transactions_view_df(df, tx_cols=tx_cols)

    assert list(out.columns) == tx_cols

    assert out.loc[0, "MVA-kode"] == "1"
    assert float(out.loc[0, "MVA-beløp"]) == 250.0
    assert float(out.loc[0, "MVA-prosent"]) == 0.25
    assert out.loc[0, "Valuta"] == "NOK"
    assert float(out.loc[0, "Valutabeløp"]) == 1000.0

    # Rad 2: MVA-beløp mangler => NaN/NA OK
    assert out.loc[1, "MVA-kode"] == "0"
    assert out.loc[1, "Valuta"] == "EUR"


def test_build_transactions_view_df_falls_back_to_mva_column_when_mva_kode_missing() -> None:
    # Noen regneark har bare en generisk «Mva»-kolonne
    df = pd.DataFrame(
        {
            "Bilag": [1],
            "Beløp": [100.0],
            "Tekst": ["Test"],
            "Konto": ["3000"],
            "Kontonavn": ["Salg"],
            "Dato": ["01.01.2025"],
            "mva": [3],
        }
    )

    tx_cols = list(analyse_viewdata.DEFAULT_TX_COLS) + ["MVA-kode"]

    out = analyse_viewdata.build_transactions_view_df(df, tx_cols=tx_cols)

    assert out.loc[0, "MVA-kode"] == "3"
