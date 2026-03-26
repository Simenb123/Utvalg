"""Tester for mva_codes – referansedata for norske SAF-T MVA-koder."""

from __future__ import annotations

import mva_codes


def test_standard_codes_not_empty():
    codes = mva_codes.get_standard_codes()
    assert len(codes) > 20, "Forventet minst 20 standard MVA-koder"


def test_all_entries_have_required_fields():
    for entry in mva_codes.get_standard_codes():
        assert "code" in entry
        assert "description" in entry
        assert "rate" in entry
        assert "direction" in entry
        assert isinstance(entry["code"], str)
        assert isinstance(entry["rate"], (int, float))


def test_no_duplicate_codes():
    codes = [c["code"] for c in mva_codes.get_standard_codes()]
    assert len(codes) == len(set(codes)), f"Duplikater: {[c for c in codes if codes.count(c) > 1]}"


def test_get_code_info_known():
    info = mva_codes.get_code_info("1")
    assert info is not None
    assert info["rate"] == 25.0
    assert "utgående" in info["direction"].lower()


def test_get_code_info_unknown():
    assert mva_codes.get_code_info("9999") is None


def test_get_code_info_strips_whitespace():
    assert mva_codes.get_code_info(" 1 ") is not None


def test_standard_code_choices_format():
    choices = mva_codes.standard_code_choices()
    assert len(choices) == len(mva_codes.get_standard_codes())
    for choice in choices:
        assert " - " in choice, f"Ugyldig format: {choice!r}"


def test_accounting_systems_not_empty():
    assert len(mva_codes.ACCOUNTING_SYSTEMS) >= 5


def test_key_codes_present():
    """Sjekk at de viktigste kodene er definert."""
    codes = {c["code"] for c in mva_codes.get_standard_codes()}
    expected = {"0", "1", "3", "5", "6", "7", "8", "11", "13", "14", "15"}
    missing = expected - codes
    assert not missing, f"Manglende nøkkelkoder: {missing}"


def test_rates_non_negative():
    for entry in mva_codes.get_standard_codes():
        assert entry["rate"] >= 0.0, f"Negativ sats for kode {entry['code']}"
