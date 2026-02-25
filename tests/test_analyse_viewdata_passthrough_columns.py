import pandas as pd

import analyse_viewdata


def test_build_transactions_view_df_passthrough_extra_col_present():
    df = pd.DataFrame(
        {
            "Konto": [1000, 2000],
            "Kontonavn": ["A", "B"],
            "Bilag": [1, 2],
            "Beløp": [10.0, -5.0],
            "Dato": ["01.01.2025", "02.01.2025"],
            "Tekst": ["T1", "T2"],
            "Avdeling": [1, 2],
        }
    )

    tx_cols = ["Konto", "Kontonavn", "Avdeling", "Beløp", "Bilag"]
    out = analyse_viewdata.build_transactions_view_df(df, tx_cols=tx_cols)

    assert list(out.columns) == tx_cols
    # Avdeling should be populated (stringified) instead of blank
    assert out["Avdeling"].tolist() == ["1", "2"]


def test_build_transactions_view_df_passthrough_extra_col_missing_becomes_blank():
    df = pd.DataFrame(
        {
            "Konto": [1000],
            "Kontonavn": ["A"],
            "Bilag": [1],
            "Beløp": [10.0],
            "Dato": ["01.01.2025"],
            "Tekst": ["T1"],
        }
    )

    tx_cols = ["Konto", "Kontonavn", "Prosjekt", "Beløp", "Bilag"]
    out = analyse_viewdata.build_transactions_view_df(df, tx_cols=tx_cols)

    assert list(out.columns) == tx_cols
    assert out.loc[0, "Prosjekt"] == ""
