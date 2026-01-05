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
            "Tekst": ["foo", "bar", "baz", "foo again"],
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

    # Min 120: should keep 150 and -200 (abs >= 120)
    out_min = filter_dataset(df, min_amount=120.0)
    assert set(out_min["Beløp"]) == {150.0, -200.0}

    # Max 100: should keep 100 and -50 (abs <= 100)
    out_max = filter_dataset(df, max_amount=100.0)
    assert set(out_max["Beløp"]) == {100.0, -50.0}

    # Combined:
    # - positive must be in [80, 120] => keep 100
    # - negative only constrained by max => keep -50 (abs 50 <= 120), drop -200
    out_both = filter_dataset(df, min_amount=80.0, max_amount=120.0)
    assert set(out_both["Beløp"]) == {100.0, -50.0}


def test_filter_dataset_accounts_exact() -> None:
    df = _make_df()
    out = filter_dataset(df, accounts=[1000, 3000])
    assert set(out["Konto"]) == {1000, 3000}


def test_filter_dataset_account_series_first_digit() -> None:
    df = _make_df()
    # account series 1 and 3 should keep konto 1000, 1500 and 3000
    out = filter_dataset(df, konto_series=[1, 3])
    assert set(out["Konto"]) == {1000, 1500, 3000}

    # If series digits are provided via `accounts`, they should be interpreted as series,
    # not as exact konto numbers.
    out2 = filter_dataset(df, accounts=[1, 3])
    assert set(out2["Konto"]) == {1000, 1500, 3000}
