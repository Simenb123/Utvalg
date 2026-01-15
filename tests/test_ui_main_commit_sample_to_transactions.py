from __future__ import annotations

import pandas as pd

from ui_main import expand_bilag_sample_to_transactions


def test_expand_bilag_sample_to_transactions_filters_and_merges_meta() -> None:
    df_all = pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 1000, "Beløp": 10.0},
            {"Bilag": 1, "Konto": 2000, "Beløp": -10.0},
            {"Bilag": 2, "Konto": 1000, "Beløp": 20.0},
            {"Bilag": 3, "Konto": 3000, "Beløp": 30.0},
        ]
    )

    # Sample fra SelectionStudio er typisk 1 rad per bilag.
    # Vi bruker bevisst blandede typer for Bilag ("3.0") for å teste normalisering.
    df_sample = pd.DataFrame(
        {
            "Bilag": ["1", "3.0"],
            "Gruppe": [2, 1],
            "Intervall": ["[0, 100]", "[100, 200]"],
            "SumBeløp": [0.0, 30.0],
        }
    )

    out = expand_bilag_sample_to_transactions(df_sample_bilag=df_sample, df_transactions=df_all)

    # Forventer transaksjonsrader kun for bilag 1 og 3
    assert set(out["Bilag"].astype(int).unique().tolist()) == {1, 3}
    assert len(out) == 3

    # Metadata skal være med som prefiksede kolonner
    assert "Utvalg_Gruppe" in out.columns
    assert "Utvalg_Intervall" in out.columns
    assert "Utvalg_SumBilag" in out.columns

    # Gruppe/interval skal være korrekt mappet til alle rader i bilaget
    grp_by_bilag = out.groupby("Bilag")["Utvalg_Gruppe"].unique().to_dict()
    assert grp_by_bilag[1].tolist() == [2]
    assert grp_by_bilag[3].tolist() == [1]

    # Intervall og sum fra sample skal også mappes korrekt per bilag
    intervall_by_bilag = out.groupby("Bilag")["Utvalg_Intervall"].unique().to_dict()
    assert intervall_by_bilag[1].tolist() == ["[0, 100]"]
    assert intervall_by_bilag[3].tolist() == ["[100, 200]"]

    sum_by_bilag = out.groupby("Bilag")["Utvalg_SumBilag"].unique().to_dict()
    assert sum_by_bilag[1].tolist() == [0.0]
    assert sum_by_bilag[3].tolist() == [30.0]


def test_expand_bilag_sample_to_transactions_empty_sample_returns_empty() -> None:
    df_all = pd.DataFrame(
        [
            {"Bilag": 1, "Konto": 1000, "Beløp": 10.0},
            {"Bilag": 2, "Konto": 1000, "Beløp": 20.0},
        ]
    )
    df_sample = pd.DataFrame(columns=["Bilag", "SumBeløp"])

    out = expand_bilag_sample_to_transactions(df_sample_bilag=df_sample, df_transactions=df_all)

    assert out.empty
    # Vi returnerer et tomt utsnitt av df_all (samme kolonner)
    assert list(out.columns) == list(df_all.columns)


def test_expand_bilag_sample_to_transactions_missing_bilag_column_returns_empty() -> None:
    df_all = pd.DataFrame(
        [
            {"Konto": 1000, "Beløp": 10.0},
        ]
    )
    df_sample = pd.DataFrame({"Bilag": ["1"], "SumBeløp": [10.0]})

    out = expand_bilag_sample_to_transactions(df_sample_bilag=df_sample, df_transactions=df_all)
    assert out.empty
