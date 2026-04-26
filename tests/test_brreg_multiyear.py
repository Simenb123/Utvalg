"""Tester for flerårs-fetch og cache-schema v4 i brreg_client."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.shared.brreg.client as _bc


def _mk_entry(
    aar: int,
    *,
    driftsinntekter: float = 1_000_000.0,
    driftskostnader: float = 800_000.0,
    aarsresultat: float = 150_000.0,
    sum_eiendeler: float = 500_000.0,
    sum_egenkapital: float = 200_000.0,
    salgsinntekt: float | None = 950_000.0,
    annen_driftsinntekt: float | None = 50_000.0,
    varekostnad: float | None = 400_000.0,
    loennskostnad: float | None = 250_000.0,
    avskrivning: float | None = 80_000.0,
    nedskrivning: float | None = None,
    annen_driftskostnad: float | None = 70_000.0,
) -> dict:
    """Bygger en syntetisk BRREG-regnskapspost for gitt år."""
    drifts_inn: dict[str, float] = {"sumDriftsinntekter": driftsinntekter}
    if salgsinntekt is not None:
        drifts_inn["salgsinntekt"] = salgsinntekt
    if annen_driftsinntekt is not None:
        drifts_inn["annenDriftsinntekt"] = annen_driftsinntekt

    drifts_kost: dict[str, float] = {"sumDriftskostnad": driftskostnader}
    if varekostnad is not None:
        drifts_kost["varekostnad"] = varekostnad
    if loennskostnad is not None:
        drifts_kost["loennskostnad"] = loennskostnad
    if avskrivning is not None:
        drifts_kost["avskrivningVarigeDriftsmidlerImmatrielleEiendeler"] = avskrivning
    if nedskrivning is not None:
        drifts_kost["nedskrivningVarigeDriftsmidlerImmatrielleEiendeler"] = nedskrivning
    if annen_driftskostnad is not None:
        drifts_kost["annenDriftskostnad"] = annen_driftskostnad

    return {
        "regnskapsperiode": {"fraDato": f"{aar}-01-01", "tilDato": f"{aar}-12-31"},
        "resultatregnskapResultat": {
            "driftsresultat": {
                "driftsinntekter": drifts_inn,
                "driftskostnad": drifts_kost,
                "driftsresultat": driftsinntekter - driftskostnader,
            },
            "finansresultat": {},
            "aarsresultat": aarsresultat,
        },
        "eiendeler": {
            "anleggsmidler": {"sumAnleggsmidler": 300_000.0},
            "omloepsmidler": {"sumOmloepsmidler": sum_eiendeler - 300_000.0},
            "sumEiendeler": sum_eiendeler,
        },
        "egenkapitalGjeld": {
            "egenkapital": {"sumEgenkapital": sum_egenkapital},
            "gjeldOversikt": {"sumGjeld": sum_eiendeler - sum_egenkapital},
            "sumEgenkapitalGjeld": sum_eiendeler,
        },
        "revisjon": {},
        "valuta": "NOK",
        "regnskapstype": "SELSKAP",
    }


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Isoler cache til tmp_path så testene ikke lekker til ~/.utvalg/."""
    cache_file = tmp_path / "brreg_cache.json"
    monkeypatch.setattr(_bc, "_cache_path", lambda: cache_file)
    return cache_file


def test_fetch_regnskap_returns_multiyear_structure(isolated_cache, monkeypatch) -> None:
    """3 år i respons → years-dict, available_years synkende, toppnivå = nyeste."""
    response = [_mk_entry(2024), _mk_entry(2023), _mk_entry(2022)]
    monkeypatch.setattr(_bc, "_get_json", lambda url: response)

    out = _bc.fetch_regnskap("123456789")
    assert out is not None

    # Toppnivå (bakoverkompat): nyeste år
    assert out["regnskapsaar"] == "2024"
    assert "linjer" in out
    assert "driftsinntekter" in out["linjer"]

    # Nye flerårs-felter
    assert out["available_years"] == [2024, 2023, 2022]
    assert set(out["years"].keys()) == {2024, 2023, 2022}
    assert isinstance(list(out["years"].keys())[0], int)

    # Hvert år har egen linjer-dict
    for aar in (2024, 2023, 2022):
        year_data = out["years"][aar]
        assert year_data["regnskapsaar"] == str(aar)
        assert "linjer" in year_data
        assert year_data["linjer"]["driftsinntekter"] == 1_000_000.0


def test_fetch_regnskap_caches_with_current_schema(isolated_cache, monkeypatch) -> None:
    """Ny cache-skriving bruker regnskap_v{_REGNSKAP_SCHEMA_VERSION}:{orgnr}-nøkkel."""
    monkeypatch.setattr(_bc, "_get_json", lambda url: [_mk_entry(2024)])
    _bc.fetch_regnskap("123456789")

    cache_contents = json.loads(isolated_cache.read_text(encoding="utf-8"))
    current_key = f"regnskap_v{_bc._REGNSKAP_SCHEMA_VERSION}:123456789"
    assert current_key in cache_contents
    # Eldre schema-versjoner skal ikke brukes for nye skrivinger
    for old in ("3", "4"):
        if old != _bc._REGNSKAP_SCHEMA_VERSION:
            assert f"regnskap_v{old}:123456789" not in cache_contents


def test_extract_entry_fields_includes_detail_lines(isolated_cache, monkeypatch) -> None:
    """linjer-dict skal inneholde detaljposter (salgsinntekt, varekostnad, ...)."""
    monkeypatch.setattr(_bc, "_get_json", lambda url: [_mk_entry(2024)])
    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    linjer = out["linjer"]
    assert linjer["salgsinntekt"] == 950_000.0
    assert linjer["annen_driftsinntekt"] == 50_000.0
    assert linjer["varekostnad"] == 400_000.0
    assert linjer["loennskostnad"] == 250_000.0
    assert linjer["avskrivning"] == 80_000.0
    assert linjer["annen_driftskostnad"] == 70_000.0
    # nedskrivning=None → utelatt fra linjer (None-filter i _extract_entry_fields)
    assert "nedskrivning" not in linjer


def test_extract_entry_fields_omits_missing_detail_lines(isolated_cache, monkeypatch) -> None:
    """Detalj-felter som mangler i BRREG-respons skal utelates fra linjer."""
    monkeypatch.setattr(
        _bc, "_get_json",
        lambda url: [_mk_entry(
            2024,
            salgsinntekt=None,
            annen_driftsinntekt=None,
            varekostnad=None,
            loennskostnad=None,
            avskrivning=None,
            annen_driftskostnad=None,
        )],
    )
    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    linjer = out["linjer"]
    # Aggregat bevares
    assert "driftsinntekter" in linjer
    assert "driftskostnader" in linjer
    # Detaljposter utelates når manglende
    for k in (
        "salgsinntekt", "annen_driftsinntekt",
        "varekostnad", "loennskostnad",
        "avskrivning", "nedskrivning", "annen_driftskostnad",
    ):
        assert k not in linjer


def test_fetch_regnskap_respects_max_years_cap(isolated_cache, monkeypatch) -> None:
    """Respons med >5 år skal kuttes til _MAX_YEARS."""
    assert _bc._MAX_YEARS == 5
    response = [_mk_entry(y) for y in (2024, 2023, 2022, 2021, 2020, 2019, 2018)]
    monkeypatch.setattr(_bc, "_get_json", lambda url: response)

    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    assert len(out["available_years"]) == 5
    assert out["available_years"] == [2024, 2023, 2022, 2021, 2020]


def test_cache_roundtrip_preserves_int_year_keys(isolated_cache, monkeypatch) -> None:
    """Etter JSON-cache-load skal years-nøkler fortsatt være int."""
    monkeypatch.setattr(_bc, "_get_json", lambda url: [_mk_entry(2024), _mk_entry(2023)])
    _bc.fetch_regnskap("123456789")  # primer cache

    # Ny fetch leser fra cache (ingen HTTP-kall nå)
    monkeypatch.setattr(_bc, "_get_json", lambda url: pytest.fail("skal ikke kalles"))
    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    assert set(out["years"].keys()) == {2024, 2023}
    assert all(isinstance(k, int) for k in out["years"].keys())


def test_fetch_regnskap_backwards_compatible_topkeys(isolated_cache, monkeypatch) -> None:
    """Eksisterende topp-nivå-nøkler (linjer, regnskapsaar, driftsinntekter, ...) bevart."""
    monkeypatch.setattr(_bc, "_get_json", lambda url: [_mk_entry(2024)])
    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    # Eksisterende kode leser disse — må virke uendret
    for key in (
        "fra_dato", "til_dato", "regnskapsaar", "linjer",
        "driftsinntekter", "driftskostnader", "aarsresultat",
        "sum_eiendeler", "sum_egenkapital",
        "valuta", "regnskapstype", "revisorberetning",
    ):
        assert key in out, f"manglet bakoverkompatibel nøkkel: {key}"


def test_fetch_regnskap_empty_response_returns_none(isolated_cache, monkeypatch) -> None:
    """Tom liste eller None fra HTTP → result = None."""
    monkeypatch.setattr(_bc, "_get_json", lambda url: [])
    assert _bc.fetch_regnskap("123456789") is None

    # Ny cache må tømmes for at neste call ikke returnerer cached None-entry
    monkeypatch.setattr(_bc, "_get_json", lambda url: None)
    assert _bc.fetch_regnskap("987654321") is None


def test_fetch_regnskap_skips_entry_without_year(isolated_cache, monkeypatch) -> None:
    """Poster uten tolkbar fraDato hoppes over (ikke krasj)."""
    bad_entry = {"regnskapsperiode": {"fraDato": ""}, "resultatregnskapResultat": {}}
    response = [_mk_entry(2024), bad_entry, _mk_entry(2022)]
    monkeypatch.setattr(_bc, "_get_json", lambda url: response)

    out = _bc.fetch_regnskap("123456789")
    assert out is not None
    assert out["available_years"] == [2024, 2022]
