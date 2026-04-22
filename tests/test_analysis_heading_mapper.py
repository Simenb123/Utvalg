"""Tester at den felles label-mapperen for Analyse gir konsistente
brukerrettete overskrifter på tvers av venstre pivot og høyre SB-tree.
"""
from __future__ import annotations

import pytest

import page_analyse_columns as _cols


def test_ub_takes_active_year():
    assert _cols.analysis_heading("Sum", year=2024) == "UB 2024"
    assert _cols.analysis_heading("UB", year=2024) == "UB 2024"


def test_ub_fjor_takes_prev_year():
    assert _cols.analysis_heading("UB_fjor", year=2024) == "UB 2023"


def test_fallback_labels_without_year():
    assert _cols.analysis_heading("Sum") == "UB"
    assert _cols.analysis_heading("UB_fjor") == "UB i fjor"


def test_year_over_year_labels_with_year_use_compact_endr_format():
    # Med år: 2-sifret endringsformat
    assert _cols.analysis_heading("Endring_fjor", year=2025) == "Δ UB 25/24"
    assert _cols.analysis_heading("Endring_pct", year=2025) == "Δ % UB 25/24"


def test_year_over_year_labels_without_year_fall_back_to_static():
    # Uten år: kortere fallback-labels (fortsatt Δ-prefiks)
    assert _cols.analysis_heading("Endring_fjor") == "Δ UB"
    assert _cols.analysis_heading("Endring_pct") == "Δ % UB"


def test_period_activity_label():
    # Intern "Endring" = periode-bevegelse (UB-IB)
    assert _cols.analysis_heading("Endring", year=2025) == "Δ UB-IB 25"
    assert _cols.analysis_heading("Endring") == "Δ UB-IB"


def test_passthrough_for_unknown_column_ids():
    assert _cols.analysis_heading("Konto") == "Konto"
    assert _cols.analysis_heading("Kontonavn") == "Kontonavn"
    assert _cols.analysis_heading("Antall") == "Antall"
    assert _cols.analysis_heading("XYZ") == "XYZ"


def test_sb_default_visible_matches_canonical_set():
    from page_analyse_sb import SB_DEFAULT_VISIBLE

    assert SB_DEFAULT_VISIBLE == (
        "Konto",
        "Kontonavn",
        "UB",
        "UB_fjor",
        "Endring_fjor",
        "Endring_pct",
        "Antall",
    )


def test_sb_cols_contains_canonical_extras():
    from page_analyse_sb import SB_COLS

    for col in ("Endring_fjor", "Endring_pct"):
        assert col in SB_COLS, f"{col} mangler i SB_COLS"
