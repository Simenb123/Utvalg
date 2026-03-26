"""Tester for mva_system_defaults – per-system standard MVA-mapping."""

from __future__ import annotations

import mva_codes
import mva_system_defaults


def test_get_default_mapping_returns_dict():
    for system in mva_system_defaults.supported_systems():
        mapping = mva_system_defaults.get_default_mapping(system)
        assert isinstance(mapping, dict), f"Forventet dict for {system}"
        assert len(mapping) > 0, f"Tom mapping for {system}"


def test_all_mapped_values_are_valid_standard_codes():
    valid_codes = {c["code"] for c in mva_codes.get_standard_codes()}
    for system in mva_system_defaults.supported_systems():
        mapping = mva_system_defaults.get_default_mapping(system)
        for client_code, saft_code in mapping.items():
            assert saft_code in valid_codes, (
                f"System {system}: klientkode {client_code!r} mapper til "
                f"ugyldig SAF-T-kode {saft_code!r}"
            )


def test_identity_mapping_for_saft_standard():
    mapping = mva_system_defaults.get_default_mapping("SAF-T Standard")
    for code, saft_code in mapping.items():
        assert code == saft_code, f"SAF-T Standard skal ha 1:1-mapping, men {code!r} -> {saft_code!r}"


def test_unknown_system_returns_identity():
    mapping = mva_system_defaults.get_default_mapping("UkjentSystem123")
    assert len(mapping) > 0
    for code, saft_code in mapping.items():
        assert code == saft_code


def test_empty_system_returns_identity():
    mapping = mva_system_defaults.get_default_mapping("")
    assert len(mapping) > 0


def test_supported_systems_matches_accounting_systems():
    assert mva_system_defaults.supported_systems() == mva_codes.ACCOUNTING_SYSTEMS


def test_has_custom_defaults():
    assert not mva_system_defaults.has_custom_defaults("SAF-T Standard")
    assert not mva_system_defaults.has_custom_defaults("")
