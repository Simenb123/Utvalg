import pandas as pd

from page_utvalg import filter_utvalg_dataframe


def _make_df():
    """Lager et lite, oversiktlig datasett for filtreringstester."""
    data = [
        {
            "Bilag": 1,
            "Konto": 1000,
            "Kontonavn": "Bankinnskudd",
            "Dato": "2024-01-01",
            "Beløp": 1000.0,
            "Tekst": "Innbetaling fra kunde A",
        },
        {
            "Bilag": 2,
            "Konto": 3000,
            "Kontonavn": "Salgsinntekt",
            "Dato": "2024-01-02",
            "Beløp": -500.0,
            "Tekst": "Faktura til kunde B",
        },
        {
            "Bilag": 3,
            "Konto": 5000,
            "Kontonavn": "Varekostnad",
            "Dato": "2024-01-03",
            "Beløp": -200.0,
            "Tekst": "Varekjøp leverandør C",
        },
        {
            "Bilag": 4,
            "Konto": 1000,
            "Kontonavn": "Bankinnskudd",
            "Dato": "2024-01-04",
            "Beløp": 300.0,
            "Tekst": "Renteinntekt",
        },
    ]
    return pd.DataFrame(data)


def test_filter_utvalg_search_matches_text_or_kontonavn():
    df = _make_df()

    # Søk etter "kunde" skal treffe bilag 1 og 2 (Tekst inneholder "kunde")
    result = filter_utvalg_dataframe(
        df_all=df,
        query="kunde",
        dir_value="Alle",
        selected_series=[],
    )

    bilag_shown = set(result["Bilag"].tolist())
    assert bilag_shown == {1, 2}


def test_filter_utvalg_debet_only():
    df = _make_df()

    result = filter_utvalg_dataframe(
        df_all=df,
        query="",
        dir_value="Debet",
        selected_series=[],
    )

    bilag_shown = set(result["Bilag"].tolist())
    assert bilag_shown == {1, 4}


def test_filter_utvalg_kredit_only():
    df = _make_df()

    result = filter_utvalg_dataframe(
        df_all=df,
        query="",
        dir_value="Kredit",
        selected_series=[],
    )

    bilag_shown = set(result["Bilag"].tolist())
    assert bilag_shown == {2, 3}


def test_filter_utvalg_kontoserie_1_only():
    df = _make_df()

    # Kontoserie 1 = kontonummer som starter med "1" (1000)
    result = filter_utvalg_dataframe(
        df_all=df,
        query="",
        dir_value="Alle",
        selected_series=[1],
    )

    bilag_shown = set(result["Bilag"].tolist())
    assert bilag_shown == {1, 4}


def test_filter_utvalg_combined_search_dir_and_series():
    df = _make_df()

    # Kombinert filter:
    # - søk "kunde" (bilag 1 og 2)
    # - Kredit (bilag 2 og 3)
    # - kontoserie 3 (konto 3000 = bilag 2)
    result = filter_utvalg_dataframe(
        df_all=df,
        query="kunde",
        dir_value="Kredit",
        selected_series=[3],
    )

    bilag_shown = set(result["Bilag"].tolist())
    assert bilag_shown == {2}
