"""
Unit tests for analyse_model functions.

These tests validate the behaviour of build_pivot_by_account and
build_summary using small in‑memory DataFrames. They check that
aggregations are computed correctly and that edge cases (empty DataFrame
or missing columns) are handled gracefully.
"""

import pandas as pd

from analyse_model import build_pivot_by_account, build_summary, filter_by_accounts


def test_build_pivot_by_account_basic() -> None:
    """Pivot should group by Konto and Kontonavn, summing Beløp and counting Bilag."""
    df = pd.DataFrame({
        "Konto": [1000, 1000, 2000],
        "Kontonavn": ["Bank", "Bank", "Kasse"],
        "Beløp": [100.0, 200.0, -50.0],
        "Bilag": ["1", "2", "3"],
    })
    pivot = build_pivot_by_account(df)
    # to_dict for easier assertions
    rows = {row["Konto"]: row for _, row in pivot.set_index("Konto").iterrows()}
    assert len(rows) == 2, "Pivot should produce two rows for two accounts"
    # Konto 1000
    r1000 = rows[1000]
    assert r1000["Sum beløp"] == 300.0
    assert r1000["Antall bilag"] == 2
    # Konto 2000
    r2000 = rows[2000]
    assert r2000["Sum beløp"] == -50.0
    assert r2000["Antall bilag"] == 1


def test_build_pivot_without_optional_columns() -> None:
    """Pivot should return unique konto when Beløp/Bilag are missing."""
    df = pd.DataFrame({
        "Konto": [1, 2, 2, 3],
        "Kontonavn": ["A", "B", "B", "C"],
    })
    pivot = build_pivot_by_account(df)
    assert list(pivot["Konto"]) == [1, 2, 3]


def test_build_summary() -> None:
    """Summary should compute total rows, sum of Beløp and min/max dates."""
    df = pd.DataFrame({
        "Beløp": [10, -5, 3],
        "Dato": ["01.01.2020", "15.02.2020", "02.01.2020"],
    })
    summary = build_summary(df)
    assert summary["rows"] == 3
    assert summary["sum_amount"] == 8.0
    assert str(summary["min_date"])[:10] == "2020-01-01"
    assert str(summary["max_date"])[:10] == "2020-02-15"


def test_filter_by_accounts() -> None:
    """filter_by_accounts should return rows for specified accounts as strings."""
    df = pd.DataFrame({
        "Konto": ["100", 200, 100, "300"],
        "Value": [1, 2, 3, 4],
    })
    out = filter_by_accounts(df, [100, "300"])
    # Should include rows where Konto equals "100" or 100 and "300"
    assert list(out["Konto"]) == ["100", 100, "300"]