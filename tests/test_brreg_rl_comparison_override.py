"""Tester for eksplisitt BRREG→regnr overstyring via rl_mapping-argument."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import brreg_rl_comparison as _brc
import brreg_mapping_config
import classification_config


@pytest.fixture(autouse=True)
def _tmp_repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isoler mapping-fil til tmp_path for alle tester."""
    monkeypatch.setattr(classification_config, "repo_dir", lambda: tmp_path)
    yield


def _regn_df_without_alias_hits() -> pd.DataFrame:
    """RL-struktur med labels som IKKE matcher noen BRREG-alias."""
    return pd.DataFrame(
        {
            "nr": [615, 618, 670],
            "regnskapslinje": [
                "Andre kortsiktige fordringer",   # ingen alias-match
                "Kortsiktig lån i konsern",       # ingen alias-match
                "Aksjekapital",                   # ingen alias-match
            ],
            "sumpost": ["nei", "nei", "nei"],
        }
    )


def _regn_df_alias_hits() -> pd.DataFrame:
    """RL-struktur hvor "Sum driftsinntekter" matcher driftsinntekter-alias."""
    return pd.DataFrame(
        {
            "nr": [19, 99],
            "regnskapslinje": ["Sum driftsinntekter", "Annen post"],
            "sumpost": ["ja", "nei"],
        }
    )


def test_mapping_fills_row_that_alias_would_miss() -> None:
    """Hvis RL-label ikke ville matche via alias, skal mapping fylle regnr direkte."""
    brreg = {"sum_eiendeler": 750_000.0}
    # Uten mapping: regnr 615 ("Andre kortsiktige fordringer") matcher ikke alias
    baseline = _brc.build_brreg_by_regnr(_regn_df_without_alias_hits(), brreg)
    assert 615 not in baseline

    # Med mapping: sum_eiendeler → regnr 615
    out = _brc.build_brreg_by_regnr(
        _regn_df_without_alias_hits(), brreg,
        rl_mapping={"sum_eiendeler": 615},
    )
    # Eiendeler → positivt fortegn i RL-konvensjon
    assert out[615] == pytest.approx(750_000.0)


def test_mapping_overrides_alias_when_both_hit() -> None:
    """Mapping vinner: BRREG-nøkkel havner kun på mapped regnr, ikke alias-regnr."""
    brreg = {"driftsinntekter": 950_000.0}
    # Uten mapping ville regnr 19 fått verdien via alias "Sum driftsinntekter"
    baseline = _brc.build_brreg_by_regnr(_regn_df_alias_hits(), brreg)
    assert baseline[19] == pytest.approx(-950_000.0)

    # Med mapping flyttes verdien til regnr 99, og regnr 19 står tomt
    out = _brc.build_brreg_by_regnr(
        _regn_df_alias_hits(), brreg,
        rl_mapping={"driftsinntekter": 99},
    )
    assert out[99] == pytest.approx(-950_000.0)
    assert 19 not in out


def test_empty_mapping_behaves_like_before() -> None:
    brreg = {"driftsinntekter": 950_000.0}
    out_with_empty = _brc.build_brreg_by_regnr(
        _regn_df_alias_hits(), brreg, rl_mapping={},
    )
    out_without = _brc.build_brreg_by_regnr(_regn_df_alias_hits(), brreg)
    assert out_with_empty == out_without


def test_mapping_ignores_unknown_brreg_keys() -> None:
    """Ugyldig BRREG-nøkkel i mapping skal ikke bryte kjøringen."""
    out = _brc.build_brreg_by_regnr(
        _regn_df_without_alias_hits(), {"sum_eiendeler": 750_000.0},
        rl_mapping={"finnes_ikke_som_brreg_nokkel": 615},
    )
    # Mapping med ukjent nøkkel ignoreres; regnr 615 har ingen alias-match
    assert 615 not in out


def test_add_brreg_columns_loads_mapping_from_config() -> None:
    """Når rl_mapping ikke sendes, skal add_brreg_columns laste fra JSON."""
    brreg_mapping_config.save_brreg_rl_mapping({"sum_eiendeler": 615})
    brreg = {"sum_eiendeler": 750_000.0}
    pivot = pd.DataFrame(
        {
            "regnr": [615],
            "regnskapslinje": ["Andre kortsiktige fordringer"],
            "UB": [750_000.0],
        }
    )
    result = _brc.add_brreg_columns(
        pivot, _regn_df_without_alias_hits(), brreg,
    )
    row = result.loc[result["regnr"] == 615].iloc[0]
    assert row["BRREG"] == pytest.approx(750_000.0)
    assert row["Avvik_brreg"] == pytest.approx(0.0)


def test_mapping_none_disables_alias_fallback() -> None:
    """``None`` som regnr skal skrus av alias-fallback for denne nøkkelen."""
    brreg = {"driftsinntekter": 950_000.0}
    # Uten mapping: regnr 19 fylles via alias "Sum driftsinntekter"
    baseline = _brc.build_brreg_by_regnr(_regn_df_alias_hits(), brreg)
    assert baseline[19] == pytest.approx(-950_000.0)

    # Med None-mapping: alias skal ikke plassere verdien noe sted
    out = _brc.build_brreg_by_regnr(
        _regn_df_alias_hits(), brreg,
        rl_mapping={"driftsinntekter": None},
    )
    assert 19 not in out


def test_add_brreg_columns_explicit_empty_disables_mapping() -> None:
    """rl_mapping={} skal ikke laste fra JSON."""
    brreg_mapping_config.save_brreg_rl_mapping({"sum_eiendeler": 615})
    brreg = {"sum_eiendeler": 750_000.0}
    pivot = pd.DataFrame(
        {
            "regnr": [615],
            "regnskapslinje": ["Andre kortsiktige fordringer"],
            "UB": [750_000.0],
        }
    )
    result = _brc.add_brreg_columns(
        pivot, _regn_df_without_alias_hits(), brreg, rl_mapping={},
    )
    row = result.loc[result["regnr"] == 615].iloc[0]
    # Uten mapping har "Andre kortsiktige fordringer" ingen alias-match
    assert row["BRREG"] is None or pd.isna(row["BRREG"])
