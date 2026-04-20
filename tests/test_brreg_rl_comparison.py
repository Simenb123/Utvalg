from __future__ import annotations

import pandas as pd
import pytest

import brreg_rl_comparison as _brc


def _regnskapslinjer_df() -> pd.DataFrame:
    # Hovedlinjer som matcher BRREG-nøkler + noen leaf-linjer
    return pd.DataFrame(
        {
            "nr": [10, 19, 20, 79, 80, 665, 715, 820],
            "regnskapslinje": [
                "Salgsinntekt",           # leaf — ingen BRREG-match
                "Sum driftsinntekter",    # sumpost → driftsinntekter
                "Varekostnad",            # leaf
                "Sum driftskostnader",    # sumpost → driftskostnader
                "Driftsresultat",         # sumpost → driftsresultat
                "Sum eiendeler",          # sumpost → sum_eiendeler
                "Sum egenkapital",        # sumpost → sum_egenkapital
                "Sum gjeld",              # sumpost → sum_gjeld
            ],
            "sumpost": ["nei", "ja", "nei", "ja", "ja", "ja", "ja", "ja"],
        }
    )


def _pivot_df_sample() -> pd.DataFrame:
    # UB i RL-konvensjon: inntekter/EK/gjeld negativt, kostnader/eiendeler positivt
    return pd.DataFrame(
        {
            "regnr": [10, 19, 20, 79, 80, 665, 715, 820],
            "regnskapslinje": [
                "Salgsinntekt", "Sum driftsinntekter", "Varekostnad",
                "Sum driftskostnader", "Driftsresultat",
                "Sum eiendeler", "Sum egenkapital", "Sum gjeld",
            ],
            "UB": [-1_000_000, -1_000_000, 600_000, 900_000, -100_000,
                   800_000, -300_000, -500_000],
        }
    )


def _brreg_sample() -> dict:
    return {
        "regnskapsaar": "2024",
        "driftsinntekter": 950_000.0,
        "driftskostnader": 850_000.0,
        "driftsresultat": 100_000.0,
        "sum_eiendeler": 750_000.0,
        "sum_egenkapital": 280_000.0,
        "sum_gjeld": 470_000.0,
    }


def test_build_brreg_by_regnr_maps_labels() -> None:
    regn = _regnskapslinjer_df()
    out = _brc.build_brreg_by_regnr(regn, _brreg_sample())
    # Kun sumposter matches
    assert set(out.keys()) == {19, 79, 80, 665, 715, 820}


def test_build_brreg_by_regnr_normalizes_signs() -> None:
    out = _brc.build_brreg_by_regnr(_regnskapslinjer_df(), _brreg_sample())
    # Inntekter → negativt
    assert out[19] == -950_000.0
    # Kostnader → positivt
    assert out[79] == 850_000.0
    # Driftsresultat (RL konvensjon = negativ for overskudd) → negativt
    assert out[80] == -100_000.0
    # Eiendeler → positivt
    assert out[665] == 750_000.0
    # EK → negativt
    assert out[715] == -280_000.0
    # Gjeld → negativt
    assert out[820] == -470_000.0


def test_build_brreg_by_regnr_skips_missing_keys() -> None:
    brreg = {"driftsinntekter": 100.0}  # kun én nøkkel
    out = _brc.build_brreg_by_regnr(_regnskapslinjer_df(), brreg)
    assert set(out.keys()) == {19}


def test_build_brreg_by_regnr_empty_when_no_brreg() -> None:
    assert _brc.build_brreg_by_regnr(_regnskapslinjer_df(), {}) == {}
    assert _brc.build_brreg_by_regnr(_regnskapslinjer_df(), None) == {}


def test_add_brreg_columns_computes_avvik() -> None:
    result = _brc.add_brreg_columns(
        _pivot_df_sample(), _regnskapslinjer_df(), _brreg_sample(),
    )
    # Kolonnene finnes
    assert {"BRREG", "Avvik_brreg", "Avvik_brreg_pct"}.issubset(result.columns)

    # Sum driftsinntekter (regnr 19): UB=-1_000_000, BRREG=-950_000 → avvik=-50_000
    row = result.loc[result["regnr"] == 19].iloc[0]
    assert row["BRREG"] == pytest.approx(-950_000.0)
    assert row["Avvik_brreg"] == pytest.approx(-50_000.0)
    # Avvik % = (-50_000) / abs(-950_000) * 100 ≈ -5.26
    assert row["Avvik_brreg_pct"] == pytest.approx(-50_000 / 950_000 * 100)


def test_add_brreg_columns_sign_consistency() -> None:
    """Avvik skal være null når RL og BRREG er konsistente i fortegn."""
    pivot = pd.DataFrame(
        {
            "regnr": [19, 715],
            "regnskapslinje": ["Sum driftsinntekter", "Sum egenkapital"],
            "UB": [-950_000.0, -280_000.0],
        }
    )
    result = _brc.add_brreg_columns(pivot, _regnskapslinjer_df(), _brreg_sample())
    for regnr in (19, 715):
        row = result.loc[result["regnr"] == regnr].iloc[0]
        assert row["Avvik_brreg"] == pytest.approx(0.0)


def test_add_brreg_columns_leaves_none_for_unmatched() -> None:
    result = _brc.add_brreg_columns(
        _pivot_df_sample(), _regnskapslinjer_df(), _brreg_sample(),
    )
    # Leaf-linjer (Salgsinntekt regnr 10) har ingen BRREG-match
    row = result.loc[result["regnr"] == 10].iloc[0]
    assert row["BRREG"] is None or pd.isna(row["BRREG"])
    assert row["Avvik_brreg"] is None or pd.isna(row["Avvik_brreg"])
    assert row["Avvik_brreg_pct"] is None or pd.isna(row["Avvik_brreg_pct"])


def test_add_brreg_columns_no_data_adds_empty_cols() -> None:
    result = _brc.add_brreg_columns(
        _pivot_df_sample(), _regnskapslinjer_df(), None,
    )
    assert "BRREG" in result.columns
    assert result["BRREG"].isna().all()
    assert result["Avvik_brreg"].isna().all()
    assert result["Avvik_brreg_pct"].isna().all()


def test_add_brreg_columns_zero_brreg_gives_none_pct() -> None:
    brreg = {"driftsinntekter": 0.0}
    pivot = pd.DataFrame({"regnr": [19], "regnskapslinje": ["Sum driftsinntekter"], "UB": [-500.0]})
    result = _brc.add_brreg_columns(pivot, _regnskapslinjer_df(), brreg)
    row = result.iloc[0]
    assert row["Avvik_brreg_pct"] is None or pd.isna(row["Avvik_brreg_pct"])


def test_opptjent_ek_derives_from_innskutt_and_total() -> None:
    """sum_opptjent_egenkapital = sum_egenkapital - sum_innskutt_egenkapital."""
    regn = pd.DataFrame(
        {
            "nr": [700, 710, 720],
            "regnskapslinje": [
                "Sum innskutt egenkapital",
                "Sum opptjent egenkapital",
                "Sum egenkapital",
            ],
            "sumpost": ["ja", "ja", "ja"],
        }
    )
    brreg = {
        "sum_innskutt_egenkapital": 100_000.0,
        "sum_egenkapital": 350_000.0,
        # sum_opptjent_egenkapital mangler → skal utledes fra formel
    }
    out = _brc.build_brreg_by_regnr(regn, brreg)
    # Innskutt og sum_egenkapital matches direkte (RL-fortegn negativt)
    assert out[700] == pytest.approx(-100_000.0)
    assert out[720] == pytest.approx(-350_000.0)
    # Opptjent utledes: total - innskutt = 250_000, med sign -1 → -250_000
    assert out[710] == pytest.approx(-250_000.0)


def test_sum_gjeld_derives_from_lang_and_kortsiktig() -> None:
    regn = pd.DataFrame(
        {
            "nr": [800, 810, 820],
            "regnskapslinje": [
                "Sum langsiktig gjeld",
                "Sum kortsiktig gjeld",
                "Sum gjeld",
            ],
            "sumpost": ["ja", "ja", "ja"],
        }
    )
    brreg = {
        "langsiktig_gjeld": 200_000.0,
        "kortsiktig_gjeld": 150_000.0,
        # sum_gjeld mangler → skal summeres fra formel
    }
    out = _brc.build_brreg_by_regnr(regn, brreg)
    assert out[800] == pytest.approx(-200_000.0)
    assert out[810] == pytest.approx(-150_000.0)
    assert out[820] == pytest.approx(-350_000.0)


def test_detail_lines_match_directly() -> None:
    """Salgsinntekt, varekostnad, lønnskostnad etc. skal matche BRREG-detaljposter."""
    regn = pd.DataFrame(
        {
            "nr": [10, 20, 30, 40, 50, 60],
            "regnskapslinje": [
                "Salgsinntekt",
                "Varekostnad",
                "Lønnskostnad",
                "Avskrivning",
                "Nedskrivning",
                "Annen driftskostnad",
            ],
            "sumpost": ["nei"] * 6,
        }
    )
    brreg = {
        "salgsinntekt": 950_000.0,
        "varekostnad": 400_000.0,
        "loennskostnad": 250_000.0,
        "avskrivning": 80_000.0,
        "nedskrivning": 10_000.0,
        "annen_driftskostnad": 70_000.0,
    }
    out = _brc.build_brreg_by_regnr(regn, brreg)
    # Inntekter → negativt (RL-konvensjon)
    assert out[10] == pytest.approx(-950_000.0)
    # Kostnader → positivt
    assert out[20] == pytest.approx(400_000.0)
    assert out[30] == pytest.approx(250_000.0)
    assert out[40] == pytest.approx(80_000.0)
    assert out[50] == pytest.approx(10_000.0)
    assert out[60] == pytest.approx(70_000.0)


def test_detail_lines_missing_stays_blank() -> None:
    """Detaljposter uten BRREG-verdi skal utelates (blank i GUI)."""
    regn = pd.DataFrame(
        {
            "nr": [10, 20],
            "regnskapslinje": ["Salgsinntekt", "Varekostnad"],
            "sumpost": ["nei", "nei"],
        }
    )
    # Kun aggregat, ingen detaljer
    brreg = {"driftsinntekter": 950_000.0, "driftskostnader": 800_000.0}
    out = _brc.build_brreg_by_regnr(regn, brreg)
    assert 10 not in out
    assert 20 not in out


def test_sum_driftsinntekter_still_matches_with_detail_present() -> None:
    """Direkte-match av aggregat bevares selv om detaljposter også finnes."""
    regn = pd.DataFrame(
        {
            "nr": [10, 19],
            "regnskapslinje": ["Salgsinntekt", "Sum driftsinntekter"],
            "sumpost": ["nei", "ja"],
        }
    )
    brreg = {
        "driftsinntekter": 1_000_000.0,
        "salgsinntekt": 950_000.0,
    }
    out = _brc.build_brreg_by_regnr(regn, brreg)
    assert out[10] == pytest.approx(-950_000.0)
    assert out[19] == pytest.approx(-1_000_000.0)


def test_norske_diakritika_matches() -> None:
    """Etiketter med æ/ø/å skal matche aliaser uten å kreve ASCII-varianter."""
    regn = pd.DataFrame(
        {
            "nr": [10, 20],
            "regnskapslinje": ["Sum omløpsmidler", "Årsresultat"],
            "sumpost": ["ja", "ja"],
        }
    )
    brreg = {"sum_omloepsmidler": 500_000.0, "aarsresultat": 42_000.0}
    out = _brc.build_brreg_by_regnr(regn, brreg)
    assert out[10] == pytest.approx(500_000.0)
    assert out[20] == pytest.approx(-42_000.0)
