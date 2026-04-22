"""Tester for src/shared/columns_vocabulary.py.

Den eldre tests/test_analysis_heading_mapper.py dekker analysis_heading()
i page_analyse_columns (som nå er tynn wrapper). Denne testen verifiserer
direkte den nye, delte funksjonen.

Format-konvensjon (etter "alltid år"-oppdatering):
    Rene verdier (UB, IB, HB, UB_fjor) → 4-sifret år, f.eks. "UB 2025".
    Endrings-kolonner                  → 2-sifret år, f.eks. "Endr UB 25/24".
"""

from __future__ import annotations

from src.shared.columns_vocabulary import LABELS_STATIC, heading


# ---------------------------------------------------------------------------
# Rene verdier: 4-sifret år
# ---------------------------------------------------------------------------

def test_ub_with_year_renders_as_ub_4digit_year() -> None:
    assert heading("UB", year=2025) == "UB 2025"
    assert heading("Sum", year=2025) == "UB 2025"


def test_ub_without_year_renders_as_ub() -> None:
    assert heading("UB") == "UB"
    assert heading("Sum") == "UB"


def test_ub_fjor_subtracts_one_from_year() -> None:
    assert heading("UB_fjor", year=2025) == "UB 2024"


def test_ub_fjor_without_year_is_textual() -> None:
    assert heading("UB_fjor") == "UB i fjor"


def test_ib_with_year_renders_as_ib_4digit_year() -> None:
    assert heading("IB", year=2025) == "IB 2025"


def test_ib_without_year_renders_as_ib() -> None:
    assert heading("IB") == "IB"


def test_hb_with_year_renders_as_hb_4digit_year() -> None:
    assert heading("HB", year=2025) == "HB 2025"


def test_hb_without_year_renders_as_hb() -> None:
    assert heading("HB") == "HB"


def test_brreg_with_year_renders_brreg_year() -> None:
    assert heading("BRREG", brreg_year=2024) == "BRREG 2024"
    assert heading("BRREG") == "BRREG"


# ---------------------------------------------------------------------------
# Endrings-kolonner: 2-sifret år, "Endr"-prefiks
# ---------------------------------------------------------------------------

def test_endring_with_year_is_periode_diff_2digit() -> None:
    """Endring (periode) → 'Endr UB-IB <yy>'"""
    assert heading("Endring", year=2025) == "Endr UB-IB 25"


def test_endring_fjor_with_year_is_yoy_2digit() -> None:
    """Endring_fjor (år-over-år) → 'Endr UB <yy>/<yy-1>'"""
    assert heading("Endring_fjor", year=2025) == "Endr UB 25/24"


def test_endring_pct_with_year_is_pct_yoy_2digit() -> None:
    assert heading("Endring_pct", year=2025) == "Endr % 25/24"


def test_endring_columns_have_distinct_labels_with_year() -> None:
    """De tre endringskolonnene MÅ ha ulik tekst når år er kjent."""
    a = heading("Endring", year=2025)
    b = heading("Endring_fjor", year=2025)
    c = heading("Endring_pct", year=2025)
    assert len({a, b, c}) == 3


def test_endring_century_rollover_uses_two_digits_correctly() -> None:
    """Verifiser at år 2099/2100-overgang gir riktig 2-sifret format."""
    assert heading("Endring_fjor", year=2100) == "Endr UB 00/99"
    assert heading("Endring", year=2099) == "Endr UB-IB 99"


def test_endring_without_year_falls_back_to_static_labels() -> None:
    """Uten år: bruk fallback-labels (kompakt og lesbar)."""
    assert heading("Endring") == "Endr UB-IB"
    assert heading("Endring_fjor") == "Endring"
    assert heading("Endring_pct") == "Endring %"


# ---------------------------------------------------------------------------
# Statiske / metadata-kolonner
# ---------------------------------------------------------------------------

def test_static_labels_for_basic_ids() -> None:
    assert heading("Konto") == "Konto"
    assert heading("Kontonavn") == "Kontonavn"
    assert heading("Antall") == "Antall"
    assert heading("Antall_bilag") == "Antall bilag"


def test_unknown_id_returns_self() -> None:
    assert heading("UkjentKolonne") == "UkjentKolonne"


def test_labels_static_contains_expected_keys() -> None:
    """Vern mot at noen ved et uhell sletter en kanonisk ID."""
    required = {"Konto", "Kontonavn", "IB", "HB", "Endring", "Endring_fjor",
                "Endring_pct", "Antall", "Antall_bilag"}
    assert required.issubset(LABELS_STATIC.keys())


# ---------------------------------------------------------------------------
# Bakoverkompatibilitet
# ---------------------------------------------------------------------------

def test_old_alias_in_page_analyse_columns_still_works() -> None:
    """Bakoverkompatibilitet: analysis_heading() i page_analyse_columns
    skal være en tynn wrapper over heading()."""
    import page_analyse_columns as _cols

    assert _cols.analysis_heading("UB", year=2025) == "UB 2025"
    assert _cols.analysis_heading("UB_fjor", year=2025) == "UB 2024"
    assert _cols.analysis_heading("IB", year=2025) == "IB 2025"
    assert _cols.analysis_heading("Endring", year=2025) == "Endr UB-IB 25"
    # Den gamle dict-en re-eksporteres også
    assert _cols._ANALYSIS_HEADINGS_STATIC is LABELS_STATIC
