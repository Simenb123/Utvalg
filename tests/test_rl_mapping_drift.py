"""Tester for rl_mapping_drift.detect_mapping_drift."""

from __future__ import annotations

import pandas as pd

import rl_mapping_drift as drift


def _intervals() -> pd.DataFrame:
    return pd.DataFrame({"fra": [1000, 3000], "til": [1999, 3999], "regnr": [10, 20]})


def _regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame({
        "nr": [10, 20],
        "regnskapslinje": ["Eiendeler", "Inntekter"],
        "sumpost": ["nei", "nei"],
        "Formel": ["", ""],
    })


def _sb(kontoer_ub: dict[str, float]) -> pd.DataFrame:
    rows = []
    for konto, ub in kontoer_ub.items():
        rows.append({"konto": konto, "kontonavn": f"Navn {konto}", "ib": 0.0, "ub": ub, "netto": ub})
    return pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["konto", "kontonavn", "ib", "ub", "netto"]
    )


def test_no_drift_when_mappings_match() -> None:
    sb = _sb({"1000": 100.0, "3000": -500.0})
    sb_prev = _sb({"1000": 90.0, "3000": -400.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert result == []


def test_changed_mapping_via_override() -> None:
    """Konto 3000: override flytter fra RL 20 i fjor til RL 10 i år."""
    sb = _sb({"3000": -1000.0})
    sb_prev = _sb({"3000": -800.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={"3000": 10},
        prior_overrides={},
    )
    assert len(result) == 1
    d = result[0]
    assert d.konto == "3000"
    assert d.kind == drift.DRIFT_CHANGED
    assert d.regnr_aar == 10
    assert d.regnr_fjor == 20
    assert d.ub_aar == -1000.0
    assert d.ub_fjor == -800.0
    assert abs(d.materialitet - 1000.0) < 1e-9


def test_new_mapped_account_is_not_flagged_as_drift() -> None:
    """Nye kontoer som er korrekt mappet i år er ikke drift — bare nye kontoer."""
    sb = _sb({"1000": 500.0})
    sb_prev = _sb({})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert result == []


def test_only_current_when_new_account_is_unmapped() -> None:
    """Ny konto uten mapping i år er reelt problem — flagges som DRIFT_ONLY_CURRENT."""
    sb = _sb({"9999": 500.0})  # ingen interval matcher 9999
    sb_prev = _sb({})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert len(result) == 1
    d = result[0]
    assert d.konto == "9999"
    assert d.kind == drift.DRIFT_ONLY_CURRENT
    assert d.regnr_aar is None


def test_disappeared_mapped_account_is_not_flagged() -> None:
    """Avsluttede kontoer som var riktig mappet i fjor er ikke drift."""
    sb = _sb({})
    sb_prev = _sb({"3000": -700.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert result == []


def test_only_prior_when_unmapped_account_disappeared() -> None:
    """Forsvunnet konto uten mapping i fjor flagges fortsatt."""
    sb = _sb({})
    sb_prev = _sb({"9999": -700.0})  # ingen interval matcher 9999
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert len(result) == 1
    d = result[0]
    assert d.konto == "9999"
    assert d.kind == drift.DRIFT_ONLY_PRIOR
    assert d.regnr_fjor is None


def test_only_prior_with_zero_ub_is_ignored() -> None:
    """Konto med UB==0 i fjor er ikke reell drift."""
    sb = _sb({})
    sb_prev = _sb({"3000": 0.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    assert result == []


def test_drifts_sorted_by_materialitet_desc() -> None:
    # Umappede kontoer (9xxx matcher ingen interval) blir flagget.
    sb = _sb({"9500": 100.0})
    sb_prev = _sb({"9000": -9_000.0, "9800": -500.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={}, prior_overrides={},
    )
    kinds = [d.kind for d in result]
    assert all(k != drift.DRIFT_CHANGED for k in kinds)
    # Sortert synkende på materialitet
    assert [d.konto for d in result] == ["9000", "9800", "9500"]


def test_summary_text_empty() -> None:
    assert drift.summary_text([]) == ""


def test_summary_text_changed_only() -> None:
    d = drift.MappingDrift(
        konto="3000", kontonavn="Salg",
        regnr_aar=10, rl_navn_aar="Eiendeler", ub_aar=-1_200_000.0,
        regnr_fjor=20, rl_navn_fjor="Inntekter", ub_fjor=-800_000.0,
        kind=drift.DRIFT_CHANGED,
    )
    txt = drift.summary_text([d])
    assert "1 kontoer endret RL-mapping" in txt
    assert "MNOK" in txt


def test_accepted_drift_filters_out_matching_pair() -> None:
    sb = _sb({"3000": -1000.0})
    sb_prev = _sb({"3000": -800.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={"3000": 10}, prior_overrides={},
        accepted_drift={"3000": {"regnr_cur": 10, "regnr_prev": 20}},
    )
    assert result == []


def test_accepted_drift_does_not_filter_if_pair_changes() -> None:
    sb = _sb({"3000": -1000.0})
    sb_prev = _sb({"3000": -800.0})
    result = drift.detect_mapping_drift(
        client=None, year="2025",
        sb_df=sb, sb_prev_df=sb_prev,
        intervals=_intervals(), regnskapslinjer=_regnskapslinjer(),
        current_overrides={"3000": 10}, prior_overrides={},
        accepted_drift={"3000": {"regnr_cur": 99, "regnr_prev": 20}},
    )
    assert len(result) == 1
    assert result[0].konto == "3000"


def test_apply_use_prior_mapping_writes_current_override(tmp_path, monkeypatch) -> None:
    import app_paths as _ap
    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_ap, "data_dir", lambda: tmp_path)

    drifts = [drift.MappingDrift(
        konto="3000", kontonavn="Salg",
        regnr_aar=10, rl_navn_aar="Eiendeler", ub_aar=-1000.0,
        regnr_fjor=20, rl_navn_fjor="Inntekter", ub_fjor=-800.0,
        kind=drift.DRIFT_CHANGED,
    )]
    n = drift.apply_use_prior_mapping(client="TestAS", year="2025", drifts=drifts)
    assert n == 1
    loaded = _rco.load_account_overrides("TestAS", year="2025")
    assert loaded.get("3000") == 20


def test_apply_use_current_mapping_writes_prior_override(tmp_path, monkeypatch) -> None:
    import app_paths as _ap
    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_ap, "data_dir", lambda: tmp_path)

    drifts = [drift.MappingDrift(
        konto="3000", kontonavn="Salg",
        regnr_aar=10, rl_navn_aar="Eiendeler", ub_aar=-1000.0,
        regnr_fjor=20, rl_navn_fjor="Inntekter", ub_fjor=-800.0,
        kind=drift.DRIFT_CHANGED,
    )]
    n = drift.apply_use_current_mapping(client="TestAS", year="2025", drifts=drifts)
    assert n == 1
    loaded = _rco.load_account_overrides("TestAS", year="2024")
    assert loaded.get("3000") == 10


def test_apply_accept_drift_persists_pair(tmp_path, monkeypatch) -> None:
    import app_paths as _ap
    import regnskap_client_overrides as _rco
    monkeypatch.setattr(_ap, "data_dir", lambda: tmp_path)

    drifts = [drift.MappingDrift(
        konto="3000", kontonavn="Salg",
        regnr_aar=10, rl_navn_aar="Eiendeler", ub_aar=-1000.0,
        regnr_fjor=20, rl_navn_fjor="Inntekter", ub_fjor=-800.0,
        kind=drift.DRIFT_CHANGED,
    )]
    n = drift.apply_accept_drift(client="TestAS", year="2025", drifts=drifts)
    assert n == 1
    accepted = _rco.load_accepted_mapping_drift("TestAS", "2025", "2024")
    assert accepted.get("3000") == {"regnr_cur": 10, "regnr_prev": 20}
