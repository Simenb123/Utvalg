"""
Enhetstester for analyse_model.

Disse testene verifiserer at pivotfunksjonen og hjelpefunksjonene i
analyse_model fungerer som forventet. Det testes både "happy path" og
kanttilfeller, slik at koden tåler tomme data eller manglende kolonner.
"""

from __future__ import annotations

import pandas as pd

from analyse_model import build_pivot_by_account, build_summary, filter_by_accounts


def test_build_pivot_by_account_basic() -> None:
    """Pivot skal gruppere på Konto (og Kontonavn) og summere Beløp/telle Bilag."""
    df = pd.DataFrame({
        "Konto": [1000, 1000, 2000],
        "Kontonavn": ["Bank", "Bank", "Kasse"],
        "Beløp": [100.0, 200.0, -50.0],
        "Bilag": ["1", "2", "3"],
    })
    pivot = build_pivot_by_account(df)
    # Kontroller at pivot har forventede kolonner
    expected_cols = {"Konto", "Kontonavn", "Sum beløp", "Antall bilag"}
    assert expected_cols.issubset(set(pivot.columns))
    # Konverter til dictionary for enkel sjekk
    rows = {int(row["Konto"]): row for _, row in pivot.set_index("Konto").iterrows()}
    assert len(rows) == 2
    # Konto 1000
    r1000 = rows[1000]
    assert r1000["Sum beløp"] == 300.0
    assert r1000["Antall bilag"] == 2
    # Konto 2000
    r2000 = rows[2000]
    assert r2000["Sum beløp"] == -50.0
    assert r2000["Antall bilag"] == 1


def test_build_pivot_without_belop_or_bilag() -> None:
    """Når Beløp og Bilag mangler, skal pivot returnere unike kontoer."""
    df = pd.DataFrame({
        "Konto": [1, 2, 2, 3],
        "Kontonavn": ["A", "B", "B", "C"],
    })
    pivot = build_pivot_by_account(df)
    assert list(pivot["Konto"]) == [1, 2, 3]


def test_build_summary() -> None:
    """Oppsummering skal gi antall rader, sum beløp og min/max dato."""
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
    """filter_by_accounts skal returnere rader for spesifiserte kontoer."""
    df = pd.DataFrame({
        "Konto": ["100", 200, 100, "300"],
        "Value": [1, 2, 3, 4],
    })
    out = filter_by_accounts(df, [100, "300"])
    # Skal inkludere rader der Konto er "100"/100 eller "300"
    assert list(out["Konto"]) == ["100", 100, "300"]