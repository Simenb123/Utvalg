"""Tester for mva_melding_parser — parsing av Altinn MVA-melding JSON."""
from __future__ import annotations

import json

import pytest

from src.pages.mva.backend.melding_parser import (
    MvaMeldingData,
    parse_mva_melding,
    parse_mva_melding_dict,
)


class TestParseDict:
    def test_basic_fields(self):
        data = {
            "aar": 2025,
            "termin": 1,
            "organisasjonsnummer": "999999999",
            "post1_grunnlag_25": 1_000_000.0,
            "post1_avgift_25": 250_000.0,
            "post17_inngaende_25": 180_000.0,
            "sum_netto_skyldig": 70_000.0,
        }
        result = parse_mva_melding_dict(data)
        assert result.år == 2025
        assert result.termin == 1
        assert result.organisasjonsnummer == "999999999"
        assert result.post1_avgift_25 == 250_000.0
        assert result.post17_inngaende_25 == 180_000.0
        assert result.sum_netto_skyldig == 70_000.0

    def test_sum_utgaaende_og_inngaaende(self):
        data = {
            "aar": 2025,
            "termin": 2,
            "post1_avgift_25": 100.0,
            "post11_avgift_15": 20.0,
            "post12_avgift_12": 10.0,
            "post14_avgift_omvendt": 5.0,
            "post17_inngaende_25": 50.0,
            "post18_inngaende_15": 10.0,
            "post19_inngaende_12": 5.0,
        }
        result = parse_mva_melding_dict(data)
        assert result.sum_utgaaende() == 135.0
        assert result.sum_inngaaende() == 65.0

    def test_tolerant_aliaser(self):
        data = {"år": 2024, "periode": 3}
        result = parse_mva_melding_dict(data)
        assert result.år == 2024
        assert result.termin == 3

    def test_manglende_felt_blir_null(self):
        data = {"termin": 4, "aar": 2025}
        result = parse_mva_melding_dict(data)
        assert result.post1_avgift_25 == 0.0
        assert result.sum_inngaaende() == 0.0

    def test_ugyldig_termin_gir_feil(self):
        data = {"termin": 7, "aar": 2025}
        with pytest.raises(ValueError):
            parse_mva_melding_dict(data)

    def test_ikke_dict_gir_feil(self):
        with pytest.raises(ValueError):
            parse_mva_melding_dict("ikke en dict")  # type: ignore[arg-type]


class TestRoundtrip:
    def test_to_from_dict(self):
        original = MvaMeldingData(
            år=2025, termin=1, organisasjonsnummer="123456789",
            post1_avgift_25=250.0, post17_inngaende_25=100.0,
        )
        d = original.to_dict()
        restored = MvaMeldingData.from_dict(d)
        assert restored.år == 2025
        assert restored.termin == 1
        assert restored.post1_avgift_25 == 250.0
        assert restored.post17_inngaende_25 == 100.0


class TestParseFile:
    def test_parse_json_fil(self, tmp_path):
        payload = {
            "aar": 2025, "termin": 1,
            "post1_avgift_25": 100.0, "post17_inngaende_25": 40.0,
        }
        p = tmp_path / "mva.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        result = parse_mva_melding(p)
        assert result.termin == 1
        assert result.post1_avgift_25 == 100.0

    def test_parse_json_med_wrapper(self, tmp_path):
        payload = {
            "skjema": {
                "aar": 2025, "termin": 2,
                "post1_avgift_25": 50.0,
            }
        }
        p = tmp_path / "mva_wrap.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        result = parse_mva_melding(p)
        assert result.termin == 2
        assert result.post1_avgift_25 == 50.0

    def test_parse_json_liste(self, tmp_path):
        payload = [{"aar": 2025, "termin": 3, "post1_avgift_25": 12.0}]
        p = tmp_path / "mva_list.json"
        p.write_text(json.dumps(payload), encoding="utf-8")
        result = parse_mva_melding(p)
        assert result.termin == 3

    def test_ikke_stottet_filtype(self, tmp_path):
        p = tmp_path / "mva.xml"
        p.write_text("<xml/>", encoding="utf-8")
        with pytest.raises(ValueError):
            parse_mva_melding(p)

    def test_manglende_fil(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_mva_melding(tmp_path / "finnes_ikke.json")
