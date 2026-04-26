"""Tester for ``regnskapslinje_mapping_service`` (kanonisk RL-mapping).

Dekker:
- ``load_rl_mapping_context`` (injisert + tom)
- ``resolve_accounts_to_rl`` (interval / override / unmapped / sumline)
- ``build_rl_mapping_issues`` (HB+SB, AO_ONLY, sumline)
- ``problem_rl_mapping_issues`` + ``summarize_rl_mapping_issues``
- ``summarize_rl_status``
- backwards-compat alias ``UnmappedAccountIssue``
"""

from __future__ import annotations

import pandas as pd

import regnskapslinje_mapping_service as svc


def _intervals_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fra": [1000, 3000, 8800],
            "til": [1999, 3999, 9999],
            "regnr": [10, 50, 350],
        }
    )


def _regnskapslinjer_df(*, sumline_regnr: int | None = None) -> pd.DataFrame:
    rows = [
        {"regnr": 10, "regnskapslinje": "Eiendeler", "sumpost": False},
        {"regnr": 50, "regnskapslinje": "Salgsinntekt", "sumpost": False},
        {"regnr": 165, "regnskapslinje": "Skattekostnad", "sumpost": False},
    ]
    if sumline_regnr is not None:
        rows.append(
            {"regnr": sumline_regnr, "regnskapslinje": "Sumlinje", "sumpost": True}
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# load_rl_mapping_context
# ---------------------------------------------------------------------------


def test_load_rl_mapping_context_normalizes_inputs_and_indexes_sumlines() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"4001": 50, "5000": 165},
    )

    assert not ctx.is_empty
    assert ctx.account_overrides == {"4001": 50, "5000": 165}
    assert ctx.rl_name_by_regnr[10] == "Eiendeler"
    assert ctx.rl_name_by_regnr[350] == "Sumlinje"
    assert 350 in ctx.sumline_regnr
    assert 10 not in ctx.sumline_regnr


def test_load_rl_mapping_context_with_empty_inputs_is_empty() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=pd.DataFrame(),
        regnskapslinjer=pd.DataFrame(),
        account_overrides={},
    )
    assert ctx.is_empty
    assert ctx.intervals.empty
    assert ctx.regnskapslinjer.empty
    assert ctx.account_overrides == {}


# ---------------------------------------------------------------------------
# resolve_accounts_to_rl
# ---------------------------------------------------------------------------


def test_resolve_accounts_classifies_interval_override_unmapped_and_sumline() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"3000": 165},  # override fra 50 til 165 (leaf)
    )
    out = svc.resolve_accounts_to_rl(["1500", "3000", "8800", "9999999"], context=ctx)
    by_konto = {row["konto"]: row for _, row in out.iterrows()}

    # Intervalltreff: 1500 -> 10 (Eiendeler)
    assert by_konto["1500"]["regnr"] == 10
    assert by_konto["1500"]["mapping_status"] == "interval"
    assert by_konto["1500"]["source"] == "interval"
    assert by_konto["1500"]["regnskapslinje"] == "Eiendeler"

    # Override: 3000 var i 50, men override sender den til 165
    assert by_konto["3000"]["regnr"] == 165
    assert by_konto["3000"]["mapping_status"] == "override"
    assert by_konto["3000"]["source"] == "override"

    # Sumline: 8800 -> 350 som er sumpost
    assert by_konto["8800"]["regnr"] == 350
    assert by_konto["8800"]["mapping_status"] == "sumline"

    # Unmapped: 9999999 utenfor alle intervaller
    assert pd.isna(by_konto["9999999"]["regnr"])
    assert by_konto["9999999"]["mapping_status"] == "unmapped"
    assert by_konto["9999999"]["source"] == ""


def test_resolve_accounts_with_empty_context_marks_all_unmapped() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=pd.DataFrame(),
        regnskapslinjer=pd.DataFrame(),
    )
    out = svc.resolve_accounts_to_rl(["1000", "2000"], context=ctx)
    assert list(out["mapping_status"]) == ["unmapped", "unmapped"]


def test_resolve_accounts_uses_overrides_even_when_intervals_empty() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=pd.DataFrame(),
        regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={"1500": 10},
    )
    out = svc.resolve_accounts_to_rl(["1500", "9999"], context=ctx)
    by_konto = {row["konto"]: row for _, row in out.iterrows()}

    assert by_konto["1500"]["regnr"] == 10
    assert by_konto["1500"]["mapping_status"] == "override"
    assert by_konto["1500"]["source"] == "override"
    assert by_konto["1500"]["regnskapslinje"] == "Eiendeler"
    assert pd.isna(by_konto["9999"]["regnr"])
    assert by_konto["9999"]["mapping_status"] == "unmapped"


def test_resolve_accounts_marks_sumline_via_override_separately_from_interval() -> None:
    ctx_via_interval = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
    )
    out_iv = svc.resolve_accounts_to_rl(["8800"], context=ctx_via_interval)
    row_iv = out_iv.iloc[0]
    assert row_iv["mapping_status"] == "sumline"
    assert row_iv["source"] == "interval"

    ctx_via_override = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"1500": 350},  # override som peker p\u00e5 sumlinje
    )
    out_ov = svc.resolve_accounts_to_rl(["1500"], context=ctx_via_override)
    row_ov = out_ov.iloc[0]
    assert row_ov["mapping_status"] == "sumline"
    assert row_ov["source"] == "override"


def test_resolve_accounts_dedupes_input() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df()
    )
    out = svc.resolve_accounts_to_rl(["1500", "1500", "1500"], context=ctx)
    assert len(out) == 1
    assert out.iloc[0]["konto"] == "1500"


# ---------------------------------------------------------------------------
# build_rl_mapping_issues
# ---------------------------------------------------------------------------


def test_build_rl_mapping_issues_marks_ao_only_unmapped() -> None:
    hb_df = pd.DataFrame(
        {"Konto": ["1000"], "Kontonavn": ["Bank"], "Beløp": [100.0]}
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["1000", "9999"],
            "kontonavn": ["Bank", "AO-konto"],
            "ib": [0.0, 0.0],
            "ub": [100.0, 250.0],
        }
    )
    ctx = svc.load_rl_mapping_context(
        intervals=pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]}),
        regnskapslinjer=_regnskapslinjer_df(),
    )

    issues = svc.build_rl_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        context=ctx,
        include_ao=True,
    )
    by_konto = {issue.konto: issue for issue in issues}

    assert by_konto["1000"].mapping_status == "interval"
    assert by_konto["1000"].kilde == "HB"
    assert by_konto["9999"].kilde == "AO_ONLY"
    assert by_konto["9999"].mapping_status == "unmapped"
    assert by_konto["9999"].belop == 250.0


def test_build_rl_mapping_issues_flags_sumline_status() -> None:
    hb_df = pd.DataFrame(
        {"Konto": ["8800"], "Kontonavn": ["Skatt"], "Beløp": [12_000.0]}
    )
    effective_sb_df = pd.DataFrame(
        {"konto": ["8800"], "kontonavn": ["Skatt"], "ib": [0.0], "ub": [12_000.0]}
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
    )

    issues = svc.build_rl_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        context=ctx,
        include_ao=False,
    )
    assert len(issues) == 1
    assert issues[0].mapping_status == "sumline"
    assert issues[0].is_problem is True


def test_build_rl_mapping_issues_preserves_mapping_source_for_interval_and_override() -> None:
    hb_df = pd.DataFrame(
        {
            "Konto": ["1500", "3000"],
            "Kontonavn": ["Kunde", "Salg"],
            "Bel\u00f8p": [1_000.0, -2_000.0],
        }
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["1500", "3000"],
            "kontonavn": ["Kunde", "Salg"],
            "ib": [0.0, 0.0],
            "ub": [1_000.0, -2_000.0],
        }
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={"3000": 165},
    )

    issues = svc.build_rl_mapping_issues(
        hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx
    )
    by_konto = {issue.konto: issue for issue in issues}

    assert by_konto["1500"].mapping_status == "interval"
    assert by_konto["1500"].mapping_source == "interval"
    assert by_konto["3000"].mapping_status == "override"
    assert by_konto["3000"].mapping_source == "override"
    assert by_konto["3000"].regnr == 165


def test_build_rl_mapping_issues_uses_hb_sum_as_effective_ub_for_hb_only_accounts() -> None:
    # Konto finnes kun i HB (ikke i SB) – ``ub`` skal falle tilbake p\u00e5 hb_sum.
    hb_df = pd.DataFrame(
        {"Konto": ["1500"], "Kontonavn": ["Kunde"], "Bel\u00f8p": [1_500.0]}
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": pd.Series([], dtype=str),
            "kontonavn": pd.Series([], dtype=str),
            "ib": pd.Series([], dtype=float),
            "ub": pd.Series([], dtype=float),
        }
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df()
    )

    issues = svc.build_rl_mapping_issues(
        hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx
    )
    assert len(issues) == 1
    issue = issues[0]
    assert issue.konto == "1500"
    assert issue.kilde == "HB"
    # Effektiv UB = hb_sum n\u00e5r kontoen ikke finnes i SB.
    assert issue.ub == 1_500.0
    assert issue.belop == 1_500.0


def test_build_rl_mapping_issues_uses_sb_ub_when_account_in_sb() -> None:
    hb_df = pd.DataFrame(
        {"Konto": ["1500"], "Kontonavn": ["Kunde"], "Bel\u00f8p": [1_500.0]}
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["1500"],
            "kontonavn": ["Kunde"],
            "ib": [200.0],
            "ub": [1_700.0],
        }
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df()
    )

    issues = svc.build_rl_mapping_issues(
        hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx
    )
    assert len(issues) == 1
    issue = issues[0]
    # SB-konto: ub skal v\u00e6re sb_ub (1_700) – ikke hb_sum (1_500).
    assert issue.ub == 1_700.0
    assert issue.belop == 1_700.0
    assert issue.ib == 200.0


def test_build_rl_mapping_issues_empty_inputs_return_empty_list() -> None:
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df()
    )
    assert svc.build_rl_mapping_issues(hb_df=None, effective_sb_df=None, context=ctx) == []


# ---------------------------------------------------------------------------
# build_admin_rl_rows
# ---------------------------------------------------------------------------


def test_build_admin_rl_rows_carries_baseline_override_and_effective_separately() -> None:
    hb_df = pd.DataFrame(
        {
            "Konto": ["1500", "3000", "7000"],
            "Kontonavn": ["Kunde", "Salg", "Ukjent"],
            "Bel\u00f8p": [1_000.0, 500.0, 250.0],
        }
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["1500", "3000", "7000"],
            "kontonavn": ["Kunde", "Salg", "Ukjent"],
            "ib": [0.0, 0.0, 0.0],
            "ub": [1_000.0, 500.0, 250.0],
        }
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"3000": 165},  # override fra baseline 50 til 165
    )

    rows = svc.build_admin_rl_rows(hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx)
    by_konto = {row.konto: row for row in rows}

    # Konto 1500 — kun baseline-treff (ingen override)
    assert by_konto["1500"].interval_regnr == 10
    assert by_konto["1500"].override_regnr is None
    assert by_konto["1500"].effective_regnr == 10
    assert by_konto["1500"].mapping_status == "interval"
    assert by_konto["1500"].mapping_source == "interval"
    assert by_konto["1500"].is_sumline is False

    # Konto 3000 — baseline OG override; override vinner
    assert by_konto["3000"].interval_regnr == 50
    assert by_konto["3000"].override_regnr == 165
    assert by_konto["3000"].effective_regnr == 165
    assert by_konto["3000"].mapping_status == "override"
    assert by_konto["3000"].mapping_source == "override"

    # Konto 7000 — verken baseline eller override (utenfor alle intervaller)
    assert by_konto["7000"].interval_regnr is None
    assert by_konto["7000"].override_regnr is None
    assert by_konto["7000"].effective_regnr is None
    assert by_konto["7000"].mapping_status == "unmapped"


def test_build_admin_rl_rows_marks_sumline_via_override() -> None:
    hb_df = pd.DataFrame({"Konto": ["1500"], "Kontonavn": ["Kunde"], "Bel\u00f8p": [1_000.0]})
    effective_sb_df = pd.DataFrame(
        {"konto": ["1500"], "kontonavn": ["Kunde"], "ib": [0.0], "ub": [1_000.0]}
    )
    ctx = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"1500": 350},  # override peker pÃ¥ sumlinje
    )

    rows = svc.build_admin_rl_rows(hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx)
    assert len(rows) == 1
    row = rows[0]
    assert row.interval_regnr == 10  # baseline traff fortsatt
    assert row.override_regnr == 350
    assert row.effective_regnr == 350
    assert row.mapping_status == "sumline"
    assert row.mapping_source == "override"
    assert row.is_sumline is True


def test_build_admin_rl_rows_falls_back_to_baseline_when_override_removed() -> None:
    hb_df = pd.DataFrame({"Konto": ["1500"], "Kontonavn": ["Kunde"], "Bel\u00f8p": [1_000.0]})
    effective_sb_df = pd.DataFrame(
        {"konto": ["1500"], "kontonavn": ["Kunde"], "ib": [0.0], "ub": [1_000.0]}
    )

    ctx_with_override = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={"1500": 165},
    )
    rows_with = svc.build_admin_rl_rows(
        hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx_with_override
    )
    assert rows_with[0].effective_regnr == 165
    assert rows_with[0].mapping_status == "override"

    ctx_without = svc.load_rl_mapping_context(
        intervals=_intervals_df(), regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={},
    )
    rows_without = svc.build_admin_rl_rows(
        hb_df=hb_df, effective_sb_df=effective_sb_df, context=ctx_without
    )
    assert rows_without[0].effective_regnr == 10  # tilbake til baseline
    assert rows_without[0].override_regnr is None
    assert rows_without[0].mapping_status == "interval"


# ---------------------------------------------------------------------------
# Override-mutasjoner via service
# ---------------------------------------------------------------------------


def test_set_account_override_via_service_persists_through_loader(tmp_path, monkeypatch) -> None:
    import app_paths
    import src.shared.regnskap.client_overrides as overrides_module

    monkeypatch.setattr(app_paths, "data_dir", lambda: tmp_path)

    svc.set_account_override("Klient AS", "1500", 165, year="2026")

    loaded = overrides_module.load_account_overrides("Klient AS", year="2026")
    assert loaded == {"1500": 165}


def test_clear_account_override_via_service_removes_entry(tmp_path, monkeypatch) -> None:
    import app_paths
    import src.shared.regnskap.client_overrides as overrides_module

    monkeypatch.setattr(app_paths, "data_dir", lambda: tmp_path)
    overrides_module.set_account_override("Klient AS", "1500", 165, year="2026")
    overrides_module.set_account_override("Klient AS", "3000", 50, year="2026")

    svc.clear_account_override("Klient AS", "1500", year="2026")

    loaded = overrides_module.load_account_overrides("Klient AS", year="2026")
    assert loaded == {"3000": 50}


# ---------------------------------------------------------------------------
# problem / summarize / status
# ---------------------------------------------------------------------------


def test_problem_and_summary_only_include_nonzero_problems() -> None:
    issues = [
        svc.RLMappingIssue("1000", "Bank", "HB", 100.0, 10, "Eiendeler", "interval"),
        svc.RLMappingIssue("9999", "AO", "AO_ONLY", 250.0, None, "", "unmapped"),
        svc.RLMappingIssue("3500", "Sum", "HB", 0.0, 350, "Sumlinje", "sumline"),
    ]
    problems = svc.problem_rl_mapping_issues(issues)
    assert [issue.konto for issue in problems] == ["9999"]
    assert svc.get_problem_rl_accounts(issues) == ["9999"]
    assert "9999" in svc.summarize_rl_mapping_issues(issues)


def test_summarize_rl_status_counts_by_mapping_status() -> None:
    issues = [
        svc.RLMappingIssue("1000", "Bank", "HB", 100.0, 10, "Eiendeler", "interval"),
        svc.RLMappingIssue("3000", "Salg", "HB", 500.0, 50, "Salg", "override"),
        svc.RLMappingIssue("9999", "AO", "HB", 250.0, None, "", "unmapped",
                           suggested_regnr=10, suggested_regnskapslinje="Eiendeler"),
        svc.RLMappingIssue("3500", "Sum", "HB", 12.0, 350, "Sumlinje", "sumline"),
    ]
    s = svc.summarize_rl_status(issues)
    assert s.total == 4
    assert s.interval_count == 1
    assert s.override_count == 1
    assert s.unmapped_count == 1
    assert s.sumline_count == 1
    assert s.problem_count == 2  # unmapped + sumline
    assert s.suggestion_count == 1


# ---------------------------------------------------------------------------
# build_page_admin_rl_rows — kanonisk delegering
# ---------------------------------------------------------------------------


def test_build_page_admin_rl_rows_delegates_to_build_admin_rl_rows(monkeypatch) -> None:
    """build_page_admin_rl_rows skal delegere row-assembly til den kanoniske
    build_admin_rl_rows, slik at baseline/override/effektiv-regnr ikke
    rekonstrueres i to spor.
    """
    from types import SimpleNamespace
    import regnskapslinje_suggest

    hb_df = pd.DataFrame(
        {
            "Konto": ["1500", "3000"],
            "Kontonavn": ["Kunde", "Salg"],
            "Bel\u00f8p": [1_000.0, 500.0],
        }
    )
    sb_df = pd.DataFrame(
        {
            "konto": ["1500", "3000"],
            "kontonavn": ["Kunde", "Salg"],
            "ib": [0.0, 0.0],
            "ub": [1_000.0, 500.0],
        }
    )

    fake_context = svc.load_rl_mapping_context(
        intervals=_intervals_df(),
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={"3000": 165},  # override baseline 50 -> 165
    )

    monkeypatch.setattr(svc, "context_from_page", lambda _page: fake_context)
    monkeypatch.setattr(regnskapslinje_suggest, "load_rulebook_document", lambda: None)

    captured: dict[str, object] = {}
    real_build = svc.build_admin_rl_rows

    def _spy(**kwargs):
        captured.update(kwargs)
        return real_build(**kwargs)

    monkeypatch.setattr(svc, "build_admin_rl_rows", _spy)

    page = SimpleNamespace(
        dataset=hb_df,
        _df_filtered=hb_df,
        _rl_sb_df=sb_df,
        _get_effective_sb_df=lambda: sb_df,
        _include_ao_enabled=lambda: False,
    )

    rows = svc.build_page_admin_rl_rows(page)

    # Verifiser at vi faktisk gikk gjennom den kanoniske builderen
    assert captured.get("context") is fake_context
    assert captured.get("enrich") is True

    by_konto = {row.konto: row for row in rows}
    # Baseline + override + effektiv skal komme riktig ut gjennom delegeringen
    assert by_konto["1500"].interval_regnr == 10
    assert by_konto["1500"].override_regnr is None
    assert by_konto["1500"].effective_regnr == 10
    assert by_konto["1500"].mapping_status == "interval"

    assert by_konto["3000"].interval_regnr == 50
    assert by_konto["3000"].override_regnr == 165
    assert by_konto["3000"].effective_regnr == 165
    assert by_konto["3000"].mapping_status == "override"


# ---------------------------------------------------------------------------
# Backwards compat
# ---------------------------------------------------------------------------


def test_unmapped_account_issue_alias_is_rl_mapping_issue() -> None:
    import analyse_mapping_service as ams

    assert ams.UnmappedAccountIssue is svc.RLMappingIssue
    issue = ams.UnmappedAccountIssue("1000", "Bank", "HB", 100.0, 10, "Eiendeler", "interval")
    assert isinstance(issue, svc.RLMappingIssue)
    assert issue.is_problem is False
    assert issue.has_value is True
