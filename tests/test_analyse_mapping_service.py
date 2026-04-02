from __future__ import annotations

import pandas as pd

import analyse_mapping_service as svc


def _regnskapslinjer_df(*, sumline_regnr: int | None = None) -> pd.DataFrame:
    rows = [
        {"regnr": 10, "regnskapslinje": "Eiendeler", "sumpost": False},
        {"regnr": 165, "regnskapslinje": "Skattekostnad på resultat", "sumpost": False},
    ]
    if sumline_regnr is not None:
        rows.append({"regnr": sumline_regnr, "regnskapslinje": "Sumlinje", "sumpost": True})
    return pd.DataFrame(rows)


def test_build_mapping_issues_flags_ao_only_unmapped_account() -> None:
    hb_df = pd.DataFrame(
        {
            "Konto": ["1000"],
            "Kontonavn": ["Bank"],
            "Beløp": [100.0],
        }
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["1000", "9999"],
            "kontonavn": ["Bank", "AO-konto"],
            "ib": [0.0, 0.0],
            "ub": [100.0, 250.0],
        }
    )
    intervals = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})

    issues = svc.build_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        intervals=intervals,
        regnskapslinjer=_regnskapslinjer_df(),
        account_overrides={},
        include_ao=True,
    )

    by_konto = {issue.konto: issue for issue in issues}
    assert by_konto["9999"].kilde == "AO_ONLY"
    assert by_konto["9999"].mapping_status == "unmapped"
    assert by_konto["9999"].belop == 250.0


def test_build_mapping_issues_flags_sumline_mapping() -> None:
    hb_df = pd.DataFrame(
        {
            "Konto": ["8800"],
            "Kontonavn": ["Skatt"],
            "Beløp": [12_000.0],
        }
    )
    effective_sb_df = pd.DataFrame(
        {
            "konto": ["8800"],
            "kontonavn": ["Skatt"],
            "ib": [0.0],
            "ub": [12_000.0],
        }
    )
    intervals = pd.DataFrame({"fra": [8800], "til": [9999], "regnr": [350]})

    issues = svc.build_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        intervals=intervals,
        regnskapslinjer=_regnskapslinjer_df(sumline_regnr=350),
        account_overrides={},
        include_ao=False,
    )

    assert len(issues) == 1
    assert issues[0].konto == "8800"
    assert issues[0].mapping_status == "sumline"


def test_problem_mapping_issues_and_summary_only_include_nonzero_problems() -> None:
    issues = [
        svc.UnmappedAccountIssue("1000", "Bank", "HB", 100.0, 10, "Eiendeler", "interval"),
        svc.UnmappedAccountIssue("9999", "AO", "AO_ONLY", 250.0, None, "", "unmapped"),
        svc.UnmappedAccountIssue("3500", "Sum", "HB", 0.0, 350, "Sumlinje", "sumline"),
    ]

    problems = svc.problem_mapping_issues(issues)
    assert [issue.konto for issue in problems] == ["9999"]
    assert svc.get_problem_accounts(issues) == ["9999"]
    assert "9999" in svc.summarize_mapping_issues(issues)
