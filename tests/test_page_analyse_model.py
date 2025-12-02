import types
import sys

import pandas as pd

import page_analyse_model as model


def _make_dummy_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Konto": ["3000", "3000", "4000"],
            "Kontonavn": ["Salg", "Salg", "Annen inntekt"],
            "Bilag": [1, 2, 3],
            "Beløp": [1000.0, 200.0, 500.0],
            "Dato": ["01.01.2024", "02.01.2024", "03.01.2024"],
            "Tekst": ["Faktura 1", "Faktura 2", "Faktura 3"],
        }
    )


def test_build_pivot_by_account_sums_and_counts() -> None:
    df = _make_dummy_df()

    pivot = model.build_pivot_by_account(df)

    # Forvent én rad per konto
    assert set(pivot["Konto"]) == {"3000", "4000"}
    # Sjekk at summeringen stemmer for 3000
    row_3000 = pivot[pivot["Konto"] == "3000"].iloc[0]
    assert row_3000["Sum beløp"] == 1200.0
    # Hvis Bilag-kolonnen finnes, bør vi ha et antall
    if "Antall bilag" in pivot.columns:
        assert row_3000["Antall bilag"] == 2


def test_build_summary_uses_amount_and_date() -> None:
    df = _make_dummy_df()

    summary = model.build_summary(df)

    assert summary["rows"] == 3
    # Summen av 1000 + 200 + 500 = 1700
    assert summary["sum_amount"] == 1700.0
    # Min/max-dato bør settes
    assert summary["min_date"] is not None
    assert summary["max_date"] is not None
    assert summary["min_date"] <= summary["max_date"]


def test_filter_by_search_text_matches_multiple_columns() -> None:
    df = _make_dummy_df()

    # Søk på "faktura 2" skal treffe kun rad 2
    filtered = model.filter_by_search_text(df, "faktura 2")
    assert len(filtered) == 1
    assert filtered.iloc[0]["Bilag"] == 2

    # Tomt søk skal returnere originalen
    filtered_all = model.filter_by_search_text(df, "")
    assert len(filtered_all) == len(df)


def test_filter_by_accounts_filters_on_konto_column() -> None:
    df = _make_dummy_df()

    filtered = model.filter_by_accounts(df, ["4000"])
    assert len(filtered) == 1
    assert set(filtered["Konto"]) == {"4000"}

    # Ukjente kontoer -> tomt resultat
    filtered_none = model.filter_by_accounts(df, ["9999"])
    assert len(filtered_none) == 0


def test_load_state_from_analysis_pkg_uses_df_from_module(monkeypatch) -> None:
    """
    Vi simulerer at analysis_pkg har fått satt et dataset via set_dataset,
    ved å monkeypatche sys.modules["analysis_pkg"] til et enkelt objekt
    med en DataFrame-attributt.
    """
    df = _make_dummy_df()

    dummy_mod = types.SimpleNamespace()
    # Simuler at analysis_pkg har en modulvariabel som peker på df
    dummy_mod.dataset = df

    monkeypatch.setitem(sys.modules, "analysis_pkg", dummy_mod)

    state = model.load_state_from_analysis_pkg()
    assert isinstance(state.df, pd.DataFrame)
    assert len(state.df) == len(df)
    # Ikke krav om .equals, men vi forventer i praksis en kopi
    assert state.df["Konto"].tolist() == df["Konto"].tolist()
