from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from unittest.mock import patch

import consolidation_readiness as readiness
from consolidation.models import CompanyTB, ConsolidationProject, EliminationJournal, EliminationLine


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def _make_page(*, tb_df: pd.DataFrame, unmapped: list[str] | None = None, last_digest: str = ""):
    project = ConsolidationProject(
        client="Test",
        year="2025",
        parent_company_id="mor",
        reporting_currency="NOK",
        companies=[CompanyTB(company_id="mor", name="Mor", row_count=len(tb_df))],
        eliminations=[],
    )
    regnskapslinjer = pd.DataFrame(
        {
            "regnr": [165, 665],
            "regnskapslinje": ["Skattekostnad på resultat", "Sum eiendeler"],
            "sumpost": [False, True],
            "delsumnr": [None, None],
            "sumnr": [None, None],
            "sumnr2": [None, None],
            "sluttsumnr": [None, None],
            "formel": [None, None],
        }
    )
    page = SimpleNamespace()
    page._project = project
    page._include_ao_var = _DummyVar(False)
    page._intervals = pd.DataFrame({"fra": [8000], "til": [8999], "regnr": [165]})
    page._regnskapslinjer = regnskapslinjer
    page._mapped_tbs = {"mor": tb_df.copy()}
    page._mapping_unmapped = {"mor": list(unmapped or [])}
    page._mapping_review_details = {}
    page._parent_mapping_deviation_details = []
    page._last_run_result = SimpleNamespace(input_digest=last_digest) if last_digest is not None else None
    page._result_df = None
    page._get_effective_tbs = lambda: {"mor": tb_df.copy()}
    page._get_effective_company_overrides = lambda _cid: {}
    return page


def test_build_readiness_report_flags_unmapped_and_stale() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["1000", "9999"],
            "kontonavn": ["Bank", "AO"],
            "ib": [0.0, 0.0],
            "ub": [100.0, 250.0],
            "netto": [100.0, 250.0],
            "regnr": [165, None],
        }
    )
    page = _make_page(tb_df=tb_df, unmapped=["9999"], last_digest="")

    report = readiness.build_readiness_report(page)

    categories = {(issue.category, issue.severity) for issue in report.issues}
    assert ("mapping", "blocking") in categories
    assert ("stale", "blocking") in categories
    assert report.blockers >= 2


def test_compute_input_digest_changes_when_elimination_changes() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ib": [0.0],
            "ub": [0.0],
            "netto": [0.0],
            "regnr": [165],
        }
    )
    page = _make_page(tb_df=tb_df, last_digest="")
    digest_before = readiness.compute_input_digest(page)

    page._project.eliminations.append(
        EliminationJournal(
            journal_id="j1",
            name="Test",
            lines=[EliminationLine(regnr=165, company_id="mor", amount=10.0)],
        )
    )
    digest_after = readiness.compute_input_digest(page)

    assert digest_before
    assert digest_before != digest_after


def test_build_balance_issues_flags_nonzero_trial_balance() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["1000", "2000"],
            "kontonavn": ["Bank", "Gjeld"],
            "ib": [0.0, 0.0],
            "ub": [100.0, -50.0],
            "netto": [100.0, -50.0],
            "regnr": [165, 165],
        }
    )
    page = _make_page(tb_df=tb_df, last_digest="digest")

    issues = readiness.build_readiness_report(page).issues
    assert any(issue.category == "balance" and issue.severity == "blocking" for issue in issues)


def test_build_readiness_report_warns_when_ao_exists_but_checkbox_off() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ib": [0.0],
            "ub": [0.0],
            "netto": [0.0],
            "regnr": [165],
        }
    )
    page = _make_page(tb_df=tb_df, last_digest="digest")
    page._include_ao_var = _DummyVar(False)

    with patch.object(readiness.session, "client", "Test"), patch.object(readiness.session, "year", "2025"):
        with patch(
            "regnskap_client_overrides.load_supplementary_entries",
            return_value=[{"bilag": "Å01", "konto": "8740", "debet": 12000000.0, "kredit": 0.0, "belop": 12000000.0}],
        ):
            issues = readiness.build_readiness_report(page).issues

    assert any(
        issue.category == "ao"
        and issue.severity == "warning"
        and "Inkl. AO (mor) er av" in issue.message
        for issue in issues
    )


def test_build_readiness_report_flags_suspicious_mappings() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["3800"],
            "kontonavn": ["Disponering annen egenkapital"],
            "ib": [0.0],
            "ub": [-285718.06],
            "netto": [-285718.06],
            "regnr": [15],
            "regnskapslinje": ["Annen driftsinntekt"],
        }
    )
    page = _make_page(tb_df=tb_df, last_digest="digest")
    page._mapping_review_details = {
        "mor": ["3800 Disponering annen egenkapital -> 15 Annen driftsinntekt"]
    }

    issues = readiness.build_readiness_report(page).issues

    assert any(
        issue.category == "mapping"
        and issue.severity == "blocking"
        and "mistenkelig mapping" in issue.message
        for issue in issues
    )


def test_build_readiness_report_warns_when_parent_has_local_mapping_deviation() -> None:
    tb_df = pd.DataFrame(
        {
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "ib": [0.0],
            "ub": [0.0],
            "netto": [0.0],
            "regnr": [165],
        }
    )
    page = _make_page(tb_df=tb_df, last_digest="digest")
    page._parent_mapping_deviation_details = ["3800: 320 / Konsolidering 15"]

    issues = readiness.build_readiness_report(page).issues

    assert any(
        issue.category == "mapping"
        and issue.severity == "warning"
        and "avviker fra Analyse" in issue.message
        for issue in issues
    )
