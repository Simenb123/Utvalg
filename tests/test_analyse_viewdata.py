from __future__ import annotations

import warnings

import pandas as pd

import analyse_viewdata


def test_first_nonempty_series_picks_first_non_empty_and_normalizes_tokens() -> None:
    df = pd.DataFrame(
        {
            "Kundenavn": [" ACME ", "", None, "nan", "None"],
            "Kunde": [None, "Per", "  ", "Kari", "Ola"],
            "Motpart": ["", "", "ZZ", "", ""],
        }
    )

    s = analyse_viewdata.first_nonempty_series(df, ["Kundenavn", "Kunde", "Motpart"])

    assert s.tolist() == [
        "ACME",  # fra Kundenavn (strip)
        "Per",  # Kundenavn tom -> Kunde
        "ZZ",  # Kundenavn None + Kunde whitespace -> Motpart
        "Kari",  # Kundenavn 'nan' token -> Kunde
        "Ola",  # Kundenavn 'None' token -> Kunde
    ]


def test_first_nonempty_series_no_futurewarning() -> None:
    df = pd.DataFrame(
        {
            "Kunde": ["nan", "None", ""],
            "Motpart": ["A", "B", "C"],
        }
    )

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _ = analyse_viewdata.first_nonempty_series(df, ["Kunde", "Motpart"])

    # Vi ønsker ikke FutureWarning fra pandas replace/downcasting.
    assert not any(isinstance(x.message, FutureWarning) for x in w)


def test_build_transactions_view_df_builds_canonical_columns_and_formats_date() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [101.0, 102.0],
            "Beløp": ["1000", "-50.5"],
            "Tekst": ["Salg", None],
            "Kundenavn": ["ACME", ""],
            "Konto": [3000.0, "1500"],
            "Kontonavn": ["Salg", "Kundefordringer"],
            "Dato": ["2025-01-02", "03.01.2025"],
        }
    )

    out = analyse_viewdata.build_transactions_view_df(df)

    assert list(out.columns) == list(analyse_viewdata.DEFAULT_TX_COLS)
    assert out.loc[0, "Bilag"] == "101"
    assert out.loc[1, "Bilag"] == "102"

    # Beløp blir numerisk
    assert float(out.loc[0, "Beløp"]) == 1000.0
    assert float(out.loc[1, "Beløp"]) == -50.5

    # Tekst/strings blir tom streng for None
    assert out.loc[0, "Tekst"] == "Salg"
    assert out.loc[1, "Tekst"] == ""

    # Kunde fra Kundenavn
    assert out.loc[0, "Kunder"] == "ACME"
    assert out.loc[1, "Kunder"] == ""

    # Konto normaliseres
    assert out.loc[0, "Konto"] == "3000"
    assert out.loc[1, "Konto"] == "1500"

    # Dato formateres dd.mm.yyyy
    assert out.loc[0, "Dato"] == "02.01.2025"
    assert out.loc[1, "Dato"] == "03.01.2025"


def test_compute_selected_transactions_filters_and_limits_rows() -> None:
    df = pd.DataFrame(
        {
            "Konto": ["3000", "3000", "1500"],
            "Beløp": [1, 2, 3],
            "Bilag": [1, 2, 3],
        }
    )

    df_all, df_show = analyse_viewdata.compute_selected_transactions(df, ["3000"], max_rows=1)

    assert len(df_all) == 2
    assert len(df_show) == 1
    assert set(df_all["Konto"].astype(str).tolist()) == {"3000"}


def test_prepare_transactions_export_sheets_returns_two_sheets_when_truncated() -> None:
    df = pd.DataFrame(
        {
            "Konto": ["3000", "3000", "3000"],
            "Beløp": [1, 2, 3],
            "Bilag": [10, 11, 12],
            "Dato": ["01.01.2025", "02.01.2025", "03.01.2025"],
        }
    )

    sheets = analyse_viewdata.prepare_transactions_export_sheets(df, ["3000"], max_rows=2)

    assert analyse_viewdata.SHEET_TX_SHOWN in sheets
    assert analyse_viewdata.SHEET_TX_ALL in sheets
    assert len(sheets[analyse_viewdata.SHEET_TX_SHOWN]) == 2
    assert len(sheets[analyse_viewdata.SHEET_TX_ALL]) == 3


def test_prepare_pivot_export_sheets_builds_pivot_when_not_given() -> None:
    df = pd.DataFrame(
        {
            "Konto": ["3000", "3000", "1500"],
            "Kontonavn": ["Salg", "Salg", "Kundefordringer"],
            "Beløp": [100, 50, -20],
            "Bilag": [1, 2, 3],
        }
    )

    sheets = analyse_viewdata.prepare_pivot_export_sheets(df)

    assert analyse_viewdata.SHEET_PIVOT in sheets
    pivot = sheets[analyse_viewdata.SHEET_PIVOT]
    assert "Konto" in pivot.columns
    assert "Sum beløp" in pivot.columns
    assert "Antall bilag" in pivot.columns


def test_merge_sheet_maps_suffixes_duplicates() -> None:
    df = pd.DataFrame({"A": [1]})
    out = analyse_viewdata.merge_sheet_maps(
        {"Ark": df},
        {"Ark": df},
        {"Ark": df},
    )

    assert list(out.keys()) == ["Ark", "Ark (2)", "Ark (3)"]
