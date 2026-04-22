"""Tester for src/shared/columns_vocabulary.py.

Den eldre tests/test_analysis_heading_mapper.py dekker analysis_heading()
i page_analyse_columns (som nå er tynn wrapper). Denne testen verifiserer
direkte den nye, delte funksjonen.
"""

from __future__ import annotations

from src.shared.columns_vocabulary import LABELS_STATIC, heading


def test_ub_with_year_renders_as_ub_year() -> None:
    assert heading("UB", year=2025) == "UB 2025"
    assert heading("Sum", year=2025) == "UB 2025"


def test_ub_without_year_renders_as_ub() -> None:
    assert heading("UB") == "UB"
    assert heading("Sum") == "UB"


def test_ub_fjor_subtracts_one_from_year() -> None:
    assert heading("UB_fjor", year=2025) == "UB 2024"


def test_ub_fjor_without_year_is_textual() -> None:
    assert heading("UB_fjor") == "UB i fjor"


def test_brreg_with_year_renders_brreg_year() -> None:
    assert heading("BRREG", brreg_year=2024) == "BRREG 2024"
    assert heading("BRREG") == "BRREG"


def test_periode_vs_aar_over_aar_har_distinkte_labels() -> None:
    """Endring (periode) og Endring_fjor (år-over-år) MÅ ha ulik tekst."""
    assert heading("Endring") == "Bevegelse i år"
    assert heading("Endring_fjor") == "Endring"
    assert heading("Endring") != heading("Endring_fjor")


def test_static_labels_for_basic_ids() -> None:
    assert heading("Konto") == "Konto"
    assert heading("Kontonavn") == "Kontonavn"
    assert heading("Antall") == "Antall"
    assert heading("Antall_bilag") == "Antall bilag"
    assert heading("IB") == "IB"


def test_unknown_id_returns_self() -> None:
    assert heading("UkjentKolonne") == "UkjentKolonne"


def test_labels_static_contains_expected_keys() -> None:
    """Vern mot at noen ved et uhell sletter en kanonisk ID."""
    required = {"Konto", "Kontonavn", "IB", "Endring", "Endring_fjor",
                "Endring_pct", "Antall", "Antall_bilag"}
    assert required.issubset(LABELS_STATIC.keys())


def test_old_alias_in_page_analyse_columns_still_works() -> None:
    """Bakoverkompatibilitet: analysis_heading() i page_analyse_columns
    skal være en tynn wrapper over heading()."""
    import page_analyse_columns as _cols

    assert _cols.analysis_heading("UB", year=2025) == "UB 2025"
    assert _cols.analysis_heading("UB_fjor", year=2025) == "UB 2024"
    assert _cols.analysis_heading("Endring") == "Bevegelse i år"
    # Den gamle dict-en re-eksporteres også
    assert _cols._ANALYSIS_HEADINGS_STATIC is LABELS_STATIC
