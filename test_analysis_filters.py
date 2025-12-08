"""
Unit tests for ``analysis_filters``.

These tests cover the parsing and filtering functions used in the
analysis page.  They ensure that numeric strings are parsed
correctly and that filtering by search text, debit/credit direction
and absolute amounts behaves as expected.  The tests are light on
pandas usage and should execute quickly.
"""

import pandas as pd

from analysis_filters import parse_amount, filter_dataset


def test_parse_amount_none_and_empty() -> None:
    """parse_amount should return None for empty or whitespace only strings."""
    assert parse_amount("") is None
    assert parse_amount("   \t\n") is None
    assert parse_amount(None) is None  # type: ignore[arg-type]


def test_parse_amount_simple() -> None:
    """parse_amount should convert common numeric formats to float."""
    assert parse_amount("123") == 123.0
    assert parse_amount("1 234") == 1234.0
    assert parse_amount("1\u00a0234,5") == 1234.5  # NBSP and comma as decimal
    assert parse_amount("1,5") == 1.5
    assert parse_amount("2.5") == 2.5
    # Invalid returns None
    assert parse_amount("not a number") is None


def _make_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Konto": ["1000", "2000", "3000", "2000"],
        "Kontonavn": ["Bank A", "Bank B", "Something", "Another"],
        "Beløp": [100.0, -50.0, 150.0, -200.0],
        "Bilag": ["1", "2", "3", "4"],
    })


def test_filter_dataset_search() -> None:
    """Filter by search text should match Konto and Kontonavn case-insensitively."""
    df = _make_df()
    out = filter_dataset(df, search="bank")
    # Should include both Bank A and Bank B
    assert set(out["Konto"]) == {"1000", "2000"}
    # Search by kontonummer
    out2 = filter_dataset(df, search="2000")
    assert set(out2["Kontonavn"]) == {"Bank B", "Another"}


def test_filter_dataset_direction() -> None:
    """Filter by debit/credit direction should include appropriate signs."""
    df = _make_df()
    debit = filter_dataset(df, direction="Debet")
    assert set(debit["Konto"]) == {"1000", "3000"}
    credit = filter_dataset(df, direction="Kredit")
    assert set(credit["Konto"]) == {"2000"}
    # Default/unknown direction yields all rows
    all_rows = filter_dataset(df, direction="Unknown")
    assert len(all_rows) == len(df)


def test_filter_dataset_min_max_amount() -> None:
    """Filter by minimum and maximum absolute amount."""
    df = _make_df()
    # Min 120: should keep 150 and -200
    out_min = filter_dataset(df, min_amount=120.0)
    assert set(out_min["Beløp"]) == {150.0, -200.0}
    # Max 100: should keep 100 and -50
    out_max = filter_dataset(df, max_amount=100.0)
    assert set(out_max["Beløp"]) == {100.0, -50.0}
    # Combined
    out_both = filter_dataset(df, min_amount=80.0, max_amount=120.0)
    # When both bounds are set, negative values are only constrained by the
    # maximum threshold.  -50 should therefore be included along with 100.
    assert set(out_both["Beløp"]) == {100.0, -50.0}