from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
from unittest.mock import patch

import src.pages.consolidation.backend.readiness as readiness
from consolidation.models import AssociateCase, CompanyTB, ConsolidationProject, EliminationJournal, EliminationLine


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


def _make_line_basis_page(*, line_df: pd.DataFrame, last_digest: str = "digest"):
    project = ConsolidationProject(
        client="Test",
        year="2025",
        parent_company_id="dat",
        reporting_currency="NOK",
        companies=[CompanyTB(company_id="dat", name="Datter", row_count=len(line_df), basis_type="regnskapslinje")],
        eliminations=[],
    )
    regnskapslinjer = pd.DataFrame(
        {
            "regnr": [10, 11, 20],
            "regnskapslinje": ["Eiendeler", "Inntekter", "SUM"],
            "sumpost": [False, False, True],
            "delsumnr": [None, None, None],
            "sumnr": [None, None, None],
            "sumnr2": [None, None, None],
            "sluttsumnr": [None, None, None],
            "formel": [None, None, "=10+11"],
        }
    )
    page = SimpleNamespace()
    page._project = project
    page._include_ao_var = _DummyVar(False)
    page._intervals = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})
    page._regnskapslinjer = regnskapslinjer
    page._mapped_tbs = {"dat": line_df.copy()}
    page._company_line_bases = {"dat": line_df.copy()}
    page._mapping_unmapped = {"dat": []}
    page._mapping_review_details = {}
    page._parent_mapping_deviation_details = []
    page._last_run_result = SimpleNamespace(input_digest=last_digest) if last_digest is not None else None
    page._result_df = None
    page._get_effective_tbs = lambda: {"dat": line_df.copy()}
    page._get_effective_company_overrides = lambda _cid: {}
    return page


def _make_associate_page(*, case: AssociateCase):
    project = ConsolidationProject(
        client="Test",
        year="2025",
        parent_company_id="mor",
        reporting_currency="NOK",
        companies=[CompanyTB(company_id="mor", name="Mor", row_count=1)],
        associate_cases=[case],
        eliminations=[],
    )
    page = SimpleNamespace()
    page._project = project
    page._include_ao_var = _DummyVar(False)
    page._intervals = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})
    page._regnskapslinjer = pd.DataFrame(
        {
            "regnr": [100, 575, 695, 705],
            "regnskapslinje": [
                "Inntekt på investering i tilknyttet selskap",
                "Investeringer i tilknyttet selskap",
                "Annen egenkapital",
                "Udisponert resultat",
            ],
            "sumpost": [False, False, False, False],
            "delsumnr": [None, None, None, None],
            "sumnr": [None, None, None, None],
            "sumnr2": [None, None, None, None],
            "sluttsumnr": [None, None, None, None],
            "formel": [None, None, None, None],
        }
    )
    page._mapped_tbs = {}
    page._company_line_bases = {}
    page._mapping_unmapped = {}
    page._mapping_review_details = {}
    page._parent_mapping_deviation_details = []
    page._last_run_result = SimpleNamespace(input_digest="digest")
    page._result_df = None
    page._get_effective_tbs = lambda: {}
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


def test_line_basis_readiness_skips_tb_mapping_and_balance_checks() -> None:
    line_df = pd.DataFrame(
        {
            "regnr": [10, 11],
            "regnskapslinje": ["Eiendeler", "Inntekter"],
            "ub": [100.0, -50.0],
        }
    )
    page = _make_line_basis_page(line_df=line_df, last_digest="digest")

    issues = readiness.build_readiness_report(page).issues

    assert not any(issue.category == "mapping" and issue.severity == "blocking" for issue in issues)
    assert not any(issue.category == "balance" and issue.severity == "blocking" for issue in issues)


def test_line_basis_readiness_flags_invalid_sumline_import() -> None:
    line_df = pd.DataFrame(
        {
            "regnr": [20],
            "regnskapslinje": ["SUM"],
            "ub": [100.0],
        }
    )
    page = _make_line_basis_page(line_df=line_df, last_digest="digest")

    issues = readiness.build_readiness_report(page).issues

    assert any(issue.category == "grunnlag" and issue.severity == "blocking" for issue in issues)


def test_associate_readiness_flags_missing_investor_and_generation() -> None:
    case = AssociateCase(
        case_id="assoc1",
        name="Tilknyttet AS",
        investor_company_id="",
        ownership_pct=35.0,
        opening_carrying_amount=100.0,
    )
    page = _make_associate_page(case=case)

    issues = readiness.build_readiness_report(page).issues

    assert any(issue.category == "equity_method" and "mangler investor" in issue.message for issue in issues)


def test_associate_readiness_flags_stale_journal() -> None:
    case = AssociateCase(
        case_id="assoc1",
        name="Tilknyttet AS",
        investor_company_id="mor",
        ownership_pct=35.0,
        opening_carrying_amount=100.0,
        share_of_result=25.0,
        journal_id="ek1",
        status="stale",
    )
    page = _make_associate_page(case=case)
    page._project.eliminations.append(
        EliminationJournal(
            journal_id="ek1",
            name="EK-metode",
            kind="equity_method",
            status="stale",
            source_associate_case_id="assoc1",
            lines=[
                EliminationLine(regnr=575, company_id="mor", amount=25.0),
                EliminationLine(regnr=100, company_id="mor", amount=-25.0),
            ],
        )
    )

    issues = readiness.build_readiness_report(page).issues

    assert any(issue.category == "equity_method" and "utdatert" in issue.message for issue in issues)


def test_associate_readiness_flags_duplicate_full_consolidation() -> None:
    case = AssociateCase(
        case_id="assoc1",
        name="Live Seafood Center AS",
        investor_company_id="mor",
        ownership_pct=50.0,
        opening_carrying_amount=100.0,
    )
    page = _make_associate_page(case=case)
    page._project.companies.append(CompanyTB(company_id="dat1", name="Live Seafood Center AS", row_count=10))

    issues = readiness.build_readiness_report(page).issues

    assert any(issue.category == "equity_method" and "Velg enten fullkonsolidering eller EK-metoden" in issue.message for issue in issues)
