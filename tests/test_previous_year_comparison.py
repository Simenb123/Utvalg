"""Tester for fjorårssammenligning."""

from __future__ import annotations

import pandas as pd
import pytest

import previous_year_comparison


def _make_pivot_df() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 20, 40],
        "regnskapslinje": ["Salgsinntekt", "Varekostnad", "Lønn"],
        "IB": [0.0, 0.0, 0.0],
        "Endring": [-500_000.0, 200_000.0, 150_000.0],
        "UB": [-500_000.0, 200_000.0, 150_000.0],
        "Antall": [451, 109, 452],
    })


def _make_sb_prev() -> pd.DataFrame:
    """Fjorårets SB med konto → regnr mapping allerede aggregert."""
    return pd.DataFrame({
        "konto": ["3000", "4000", "5000"],
        "kontonavn": ["Salgsinntekter", "Varekostnad", "Lønn"],
        "ib": [0.0, 0.0, 0.0],
        "ub": [-400_000.0, 150_000.0, 120_000.0],
        "netto": [-400_000.0, 150_000.0, 120_000.0],
    })


def _make_intervals() -> pd.DataFrame:
    return pd.DataFrame({
        "fra": [3000, 4000, 5000],
        "til": [3999, 4999, 5999],
        "regnr": [10, 20, 40],
    })


def _make_regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame({
        "nr": [10, 20, 40],
        "regnskapslinje": ["Salgsinntekt", "Varekostnad", "Lønn"],
        "sumpost": ["nei", "nei", "nei"],
        "Formel": ["", "", ""],
    })


def test_add_previous_year_columns_basic() -> None:
    pivot = _make_pivot_df()
    sb_prev = _make_sb_prev()
    intervals = _make_intervals()
    regnskapslinjer = _make_regnskapslinjer()

    result = previous_year_comparison.add_previous_year_columns(
        pivot, sb_prev, intervals, regnskapslinjer,
    )

    assert "UB_fjor" in result.columns
    assert "Endring_fjor" in result.columns
    assert "Endring_pct" in result.columns
    assert len(result) == 3

    salg = result.loc[result["regnr"] == 10].iloc[0]
    assert salg["UB_fjor"] == pytest.approx(-400_000.0)
    assert salg["Endring_fjor"] == pytest.approx(-100_000.0)  # -500k - (-400k)
    assert salg["Endring_pct"] == pytest.approx(-25.0)  # -100k / 400k * 100


def test_add_previous_year_columns_empty_prev() -> None:
    pivot = _make_pivot_df()
    result = previous_year_comparison.add_previous_year_columns(
        pivot, pd.DataFrame(), _make_intervals(), _make_regnskapslinjer(),
    )
    assert "UB_fjor" in result.columns
    assert result["UB_fjor"].isna().all()


def test_add_previous_year_columns_none_prev() -> None:
    pivot = _make_pivot_df()
    result = previous_year_comparison.add_previous_year_columns(
        pivot, None, _make_intervals(), _make_regnskapslinjer(),
    )
    assert result["UB_fjor"].isna().all()
    assert result["Endring_pct"].isna().all()


def test_pct_avoids_division_by_zero() -> None:
    pivot = pd.DataFrame({
        "regnr": [10],
        "regnskapslinje": ["Ny post"],
        "IB": [0.0],
        "Endring": [-100.0],
        "UB": [-100.0],
        "Antall": [5],
    })
    sb_prev = pd.DataFrame({
        "konto": ["3000"],
        "kontonavn": ["Salg"],
        "ib": [0.0],
        "ub": [0.0],  # UB_fjor = 0 → pct skal bli None
        "netto": [0.0],
    })
    result = previous_year_comparison.add_previous_year_columns(
        pivot, sb_prev, _make_intervals(), _make_regnskapslinjer(),
    )
    assert result.iloc[0]["Endring_pct"] is None or pd.isna(result.iloc[0]["Endring_pct"])
