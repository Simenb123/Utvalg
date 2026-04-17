"""Fase C — integrasjonstest for fjorårsflyten.

Bekrefter at kjeden henger sammen:
  1. Maestro-lignende 2024-SB importeres via read_trial_balance
  2. client_store har aktiv 2024-versjon
  3. load_previous_year_sb("X", 2025) finner den via client_store
  4. add_previous_year_columns populerer UB_fjor/Endring_fjor/Endring_pct

Ingen ny fjorårs-arkitektur — bruker eksisterende
previous_year_comparison.load_previous_year_sb() som autoritativ entry.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


def _write_maestro_like_sb(path: Path, ub_2024: float, ib_2023: float) -> None:
    """Skriv en Maestro-lignende SB med tittelrad, Endelig 2024 + Saldo 2023."""
    raw = [
        ["Foretaksrapport — Saldobalanse", None, None, None, None],
        ["Klient X | Periode 2024", None, None, None, None],
        [None, None, None, None, None],
        ["Kontonr", "Kontobetegnelse", "Saldo 2023", "Endelig 2024", "Endring fra fjoråret"],
        [3000, "Salgsinntekt", ib_2023, ub_2024, ub_2024 - ib_2023],
        [1500, "Kundefordringer", 10000.0, 15000.0, 5000.0],
    ]
    pd.DataFrame(raw).to_excel(path, index=False, header=False)


def test_previous_year_sb_loaded_via_client_store(tmp_path: Path, monkeypatch):
    sb_path = tmp_path / "sb_2024.xlsx"
    _write_maestro_like_sb(sb_path, ub_2024=-100000.0, ib_2023=-80000.0)

    # Mock client_store til å returnere denne filen for year=2024, dtype=sb
    def _get_active(client, *, year, dtype):
        assert client == "Klient X"
        assert year == "2024"
        assert dtype == "sb"
        return SimpleNamespace(path=str(sb_path))

    fake_client_store = SimpleNamespace(get_active_version=_get_active)
    monkeypatch.setitem(__import__("sys").modules, "client_store", fake_client_store)

    from previous_year_comparison import load_previous_year_sb

    # Året som åpnes er 2025 → skal se etter 2024-SB
    prev_df = load_previous_year_sb("Klient X", 2025)

    assert prev_df is not None, "load_previous_year_sb returnerte None"
    assert not prev_df.empty
    assert set(["konto", "kontonavn", "ib", "ub"]).issubset(prev_df.columns)

    salg = prev_df.loc[prev_df["konto"] == "3000"]
    assert not salg.empty
    # Kritisk: UB (fjor) skal være eksplisitt fra "Endelig 2024"
    assert salg["ub"].iloc[0] == pytest.approx(-100000.0)
    # IB (fjor-IB) skal være fra "Saldo 2023"
    assert salg["ib"].iloc[0] == pytest.approx(-80000.0)


def test_previous_year_returns_none_when_no_active_version(monkeypatch):
    fake_client_store = SimpleNamespace(
        get_active_version=lambda client, *, year, dtype: None
    )
    monkeypatch.setitem(__import__("sys").modules, "client_store", fake_client_store)

    from previous_year_comparison import load_previous_year_sb

    assert load_previous_year_sb("Ukjent AS", 2025) is None


def test_previous_year_returns_none_when_file_missing(tmp_path: Path, monkeypatch):
    missing = tmp_path / "does_not_exist.xlsx"

    fake_client_store = SimpleNamespace(
        get_active_version=lambda client, *, year, dtype: SimpleNamespace(path=str(missing))
    )
    monkeypatch.setitem(__import__("sys").modules, "client_store", fake_client_store)

    from previous_year_comparison import load_previous_year_sb

    assert load_previous_year_sb("Klient X", 2025) is None


def test_add_previous_year_columns_populates_ub_fjor(tmp_path: Path, monkeypatch):
    """End-to-end: aggregering inn i RL-pivot får UB_fjor utfylt."""
    sb_path = tmp_path / "sb_2024.xlsx"
    _write_maestro_like_sb(sb_path, ub_2024=-100000.0, ib_2023=-80000.0)

    fake_client_store = SimpleNamespace(
        get_active_version=lambda client, *, year, dtype: SimpleNamespace(path=str(sb_path))
    )
    monkeypatch.setitem(__import__("sys").modules, "client_store", fake_client_store)

    from previous_year_comparison import load_previous_year_sb, add_previous_year_columns

    sb_prev = load_previous_year_sb("Klient X", 2025)
    assert sb_prev is not None

    # Minimal regnskapslinje/interval-struktur: én linje som dekker konto 3000
    intervals = pd.DataFrame([
        {"regnr": 10, "fra": 3000, "til": 3999},
    ])
    regnskapslinjer = pd.DataFrame([
        {"regnr": 10, "regnskapslinje": "Salgsinntekter", "sumpost": False},
    ])
    pivot = pd.DataFrame([
        {"regnr": 10, "regnskapslinje": "Salgsinntekter",
         "IB": 0.0, "Endring": -100000.0, "UB": -100000.0, "Antall": 1},
    ])

    result = add_previous_year_columns(
        pivot, sb_prev, intervals, regnskapslinjer,
    )

    assert "UB_fjor" in result.columns
    assert "Endring_fjor" in result.columns
    row = result.loc[result["regnr"] == 10].iloc[0]
    # Salgsinntekt 3000: UB_fjor = -100000.0 (fra Endelig 2024 som ble 2024-UB,
    # som i denne testen brukes som "fjoråret" fordi vi åpner 2025).
    assert row["UB_fjor"] == pytest.approx(-100000.0)
    # Endring i år (UB) - fjor (UB_fjor) = 0 siden UB og UB_fjor er samme her
    assert row["Endring_fjor"] == pytest.approx(0.0)
