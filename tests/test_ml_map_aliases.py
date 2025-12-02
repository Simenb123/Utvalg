"""
Tests for the extended alias matching in ml_map_utils.py.

These tests exercise the suggest_mapping() function with header lists
containing various synonyms that are not present in the original Utvalg
alias dictionary. The goal is to verify that the new synonyms added in
our custom ml_map_utils.py are correctly recognised and mapped to the
appropriate canonical fields.

The tests avoid any external dependencies and do not read/write any
files. They simply call suggest_mapping() with mock header lists and
assert on the returned mapping.
"""

import ml_map_utils as mm


def test_bokfort_belop_maps_to_belop() -> None:
    """Ensure that 'Bokført beløp' (and variations) map to the canonical field 'Beløp'."""
    headers = ["Kontonr", "Bilagsnr", "Bokført beløp", "Bilagsdato"]
    mapping = mm.suggest_mapping(headers)
    assert mapping is not None
    # The mapping should associate the canonical 'Beløp' with the actual header 'Bokført beløp'
    assert mapping.get("Beløp") == "Bokført beløp"


def test_iso_kode_maps_to_valuta() -> None:
    """Ensure that ISO codes are recognised as currency fields (Valuta)."""
    headers = ["ISO-kode", "Beløp"]
    mapping = mm.suggest_mapping(headers)
    assert mapping is not None
    assert mapping.get("Valuta") == "ISO-kode"


def test_belap_i_valuta_maps_to_valutabelop() -> None:
    """Ensure that various forms of 'beløp i valuta' map to 'Valutabeløp'."""
    headers = ["Belap i valuta", "Bokfort belop"]
    mapping = mm.suggest_mapping(headers)
    assert mapping is not None
    assert mapping.get("Valutabeløp") == "Belap i valuta"


def test_avg_kode_and_mva_sats() -> None:
    """Check that both MVA-kode and MVA-prosent are matched via new aliases."""
    headers = ["Avg kode", "Mva-sats"]
    mapping = mm.suggest_mapping(headers)
    assert mapping is not None
    assert mapping.get("MVA-kode") == "Avg kode"
    assert mapping.get("MVA-prosent") == "Mva-sats"