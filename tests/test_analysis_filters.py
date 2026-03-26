from __future__ import annotations

import pandas as pd

from analysis_filters import filter_dataset, parse_amount


def test_parse_amount_none_and_empty() -> None:
    assert parse_amount(None) is None
    assert parse_amount("") is None
    assert parse_amount("   ") is None


def test_parse_amount_numbers_and_strings() -> None:
    assert parse_amount(123) == 123.0
    assert parse_amount(12.5) == 12.5
    assert parse_amount("1 234,50") == 1234.50
    assert parse_amount("-1 234,50") == -1234.50
    assert parse_amount("1234.50") == 1234.50


def _make_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Konto": [1000, 2000, 3000, 1500],
            "Kontonavn": ["A", "B", "C", "D"],
            "Beløp": [100.0, -50.0, 150.0, -200.0],
            "Bilag": [1, 2, 3, 4],
            "Dato": ["02.01.2025", "10.01.2025", "20.01.2025", "31.01.2025"],
            "Tekst": ["foo", "bar", "baz", "foo again"],
            "Kundenavn": ["ACME", "", "Nord AS", ""],
            "Leverandørnavn": ["", "Tryg", "", "Leverandør X"],
            "MVA-kode": ["1", "", "3", "4"],
            "MVA-beløp": [25.0, 0.0, 37.5, 0.0],
        }
    )


def test_filter_dataset_search_alias_query() -> None:
    df = _make_df()
    out1 = filter_dataset(df, search="foo")
    out2 = filter_dataset(df, query="foo")
    assert out1.reset_index(drop=True).equals(out2.reset_index(drop=True))
    assert set(out1["Bilag"]) == {1, 4}


def test_filter_dataset_direction_debet_kredit() -> None:
    df = _make_df()
    out_debet = filter_dataset(df, direction="Debet")
    assert set(out_debet["Beløp"]) == {100.0, 150.0}

    out_kredit = filter_dataset(df, direction="Kredit")
    assert set(out_kredit["Beløp"]) == {-50.0, -200.0}


def test_filter_dataset_min_max_amount() -> None:
    """Filter by minimum and maximum absolute amount."""
    df = _make_df()

    out_min = filter_dataset(df, min_amount=120.0)
    assert set(out_min["Beløp"]) == {150.0, -200.0}

    out_max = filter_dataset(df, max_amount=100.0)
    assert set(out_max["Beløp"]) == {100.0, -50.0}

    out_both = filter_dataset(df, min_amount=80.0, max_amount=120.0)
    assert set(out_both["Beløp"]) == {100.0, -50.0}


def test_filter_dataset_accounts_exact() -> None:
    df = _make_df()
    out = filter_dataset(df, accounts=[1000, 3000])
    assert set(out["Konto"]) == {1000, 3000}


def test_filter_dataset_account_series_first_digit() -> None:
    df = _make_df()
    out = filter_dataset(df, konto_series=[1, 3])
    assert set(out["Konto"]) == {1000, 1500, 3000}

    out2 = filter_dataset(df, accounts=[1, 3])
    assert set(out2["Konto"]) == {1000, 1500, 3000}


def test_filter_dataset_mva_code_and_mode_filters() -> None:
    df = _make_df()

    out_code = filter_dataset(df, mva_code="1,3")
    assert set(out_code["Bilag"]) == {1, 3}

    out_with_code = filter_dataset(df, mva_mode="Med MVA-kode")
    assert set(out_with_code["Bilag"]) == {1, 3, 4}

    out_without_code = filter_dataset(df, mva_mode="Uten MVA-kode")
    assert set(out_without_code["Bilag"]) == {2}

    out_with_amount = filter_dataset(df, mva_mode="Med MVA-beløp")
    assert set(out_with_amount["Bilag"]) == {1, 3}

    out_deviation = filter_dataset(df, mva_mode="MVA-avvik")
    assert set(out_deviation["Bilag"]) == {4}


def test_filter_dataset_bilag_and_motpart_filters() -> None:
    df = _make_df()

    out_bilag = filter_dataset(df, bilag="3")
    assert set(out_bilag["Bilag"]) == {3}

    out_customer = filter_dataset(df, motpart="acme")
    assert set(out_customer["Bilag"]) == {1}

    out_supplier = filter_dataset(df, motpart="tryg")
    assert set(out_supplier["Bilag"]) == {2}


def test_filter_dataset_date_range_filters() -> None:
    df = _make_df()

    out_mid_month = filter_dataset(df, date_from="10.01.2025", date_to="20.01.2025")
    assert set(out_mid_month["Bilag"]) == {2, 3}

    out_from = filter_dataset(df, date_from="20.01.2025")
    assert set(out_from["Bilag"]) == {3, 4}


def test_filter_dataset_period_filters() -> None:
    df = pd.DataFrame(
        {
            "Konto": [1000, 1000, 1000, 1000],
            "Beløp": [10.0, 20.0, 30.0, 40.0],
            "Bilag": [1, 2, 3, 4],
            "Dato": ["15.01.2025", "10.02.2025", "20.03.2025", "05.04.2025"],
        }
    )

    out_from = filter_dataset(df, period_from="2")
    assert set(out_from["Bilag"]) == {2, 3, 4}

    out_to = filter_dataset(df, period_to="3")
    assert set(out_to["Bilag"]) == {1, 2, 3}

    out_range = filter_dataset(df, period_from="2", period_to="3")
    assert set(out_range["Bilag"]) == {2, 3}
