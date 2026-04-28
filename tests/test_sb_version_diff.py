"""Tester for SB versjonsdiff."""
from __future__ import annotations

import pandas as pd

import src.audit_actions.diff.sb_engine as sb_version_diff


def _make_sb(rows):
    return pd.DataFrame(rows, columns=["konto", "kontonavn", "ib", "ub"])


def test_diff_returns_added_removed_changed():
    a = _make_sb([
        ("1500", "Kundefordringer", 100.0, 200.0),
        ("2400", "Leverandørgjeld", -50.0, -100.0),
        ("3000", "Salgsinntekt",   0.0,   -1500.0),
    ])
    b = _make_sb([
        ("1500", "Kundefordringer", 100.0, 250.0),  # endret UB
        ("3000", "Salgsinntekt",    0.0,   -1500.0),  # uendret
        ("3500", "Annen inntekt",   0.0,    -200.0),  # ny
    ])
    res = sb_version_diff.diff_sb_versions(a, b)

    # Nye konti: kun 3500
    assert list(res.added["konto"]) == ["3500"]
    # Fjernede konti: kun 2400
    assert list(res.removed["konto"]) == ["2400"]
    # Endrede saldoer: kun 1500
    assert list(res.changed["konto"]) == ["1500"]
    assert res.changed.iloc[0]["diff_ub"] == 50.0
    # Uendrede: 1 (3000)
    assert res.unchanged_count == 1


def test_diff_summary_totals():
    a = _make_sb([("1500", "X", 0, 100.0)])
    b = _make_sb([("1500", "X", 0, 150.0), ("2000", "Y", 0, 50.0)])
    res = sb_version_diff.diff_sb_versions(a, b)
    s = res.summary
    assert s["konti_a_total"] == 1
    assert s["konti_b_total"] == 2
    assert s["nye_konti"] == 1
    assert s["fjernede_konti"] == 0
    assert s["endrede_konti"] == 1
    assert s["sum_ub_a"] == 100.0
    assert s["sum_ub_b"] == 200.0


def test_diff_tolerance_ignores_small_difference():
    # Avvik på øre regnes som uendret (default tolerance=0.01)
    a = _make_sb([("1500", "X", 0, 100.005)])
    b = _make_sb([("1500", "X", 0, 100.000)])
    res = sb_version_diff.diff_sb_versions(a, b)
    assert res.changed.empty
    assert res.unchanged_count == 1


def test_diff_handles_missing_columns_gracefully():
    """Dersom IB mangler i fila, skal den behandles som 0.0."""
    a = pd.DataFrame({"konto": ["1500"], "kontonavn": ["X"], "ub": [100.0]})
    b = pd.DataFrame({"konto": ["1500"], "kontonavn": ["X"], "ub": [150.0]})
    res = sb_version_diff.diff_sb_versions(a, b)
    assert len(res.changed) == 1
    assert res.changed.iloc[0]["diff_ub"] == 50.0
