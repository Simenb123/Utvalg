from __future__ import annotations

import pandas as pd

from src.pages.consolidation.backend.associate_equity_method import (
    build_associate_case_calculation,
    compute_goodwill_amortization,
    delete_associate_case,
    mark_associate_case_stale,
    suggest_associate_fields_from_line_basis,
    sync_associate_case_journal,
)
from src.pages.consolidation.backend.models import AssociateAdjustmentRow, AssociateCase, CompanyTB, ConsolidationProject


def _project() -> ConsolidationProject:
    return ConsolidationProject(
        client="Test",
        year="2025",
        companies=[CompanyTB(company_id="mor", name="Mor AS")],
    )


def _case() -> AssociateCase:
    return AssociateCase(
        case_id="assoc1",
        name="Tilknyttet AS",
        investor_company_id="mor",
        ownership_pct=40.0,
        opening_carrying_amount=1000.0,
        share_of_result=120.0,
        share_of_other_equity=30.0,
        dividends=20.0,
        impairment=10.0,
        excess_value_amortization=5.0,
        manual_adjustment_rows=[
            AssociateAdjustmentRow(
                row_id="adj1",
                label="Emisjon",
                amount=15.0,
                offset_regnr=695,
                description="Kapitalendring",
            )
        ],
    )


def test_build_associate_case_calculation_computes_closing_amount() -> None:
    calc = build_associate_case_calculation(_case())

    assert calc["opening_carrying_amount"] == 1000.0
    assert calc["total_movement"] == 130.0
    assert calc["closing_carrying_amount"] == 1130.0
    assert len(calc["movements"]) == 6


def test_sync_associate_case_journal_creates_balanced_locked_journal() -> None:
    project = _project()
    case = _case()
    project.associate_cases.append(case)

    journal = sync_associate_case_journal(case, project)

    assert journal.kind == "equity_method"
    assert journal.locked is True
    assert journal.is_balanced
    assert journal.source_associate_case_id == case.case_id
    assert case.journal_id == journal.journal_id
    assert case.status == "generated"
    assert {line.regnr for line in journal.lines} >= {100, 575, 695, 705}


def test_mark_associate_case_stale_marks_case_and_journal() -> None:
    project = _project()
    case = _case()
    project.associate_cases.append(case)
    journal = sync_associate_case_journal(case, project)

    case.share_of_result = 220.0
    mark_associate_case_stale(case, project)

    assert case.status == "stale"
    assert journal.status == "stale"


def test_delete_associate_case_removes_linked_journal() -> None:
    project = _project()
    case = _case()
    project.associate_cases.append(case)
    journal = sync_associate_case_journal(case, project)

    delete_associate_case(case.case_id, project)

    assert not project.associate_cases
    assert project.find_journal(journal.journal_id) is None


def test_suggest_associate_fields_from_line_basis_scales_by_ownership() -> None:
    df = pd.DataFrame(
        {
            "regnr": [100, 200, 300],
            "regnskapslinje": ["Årsresultat", "Annen egenkapital", "Utbytte"],
            "source_regnskapslinje": ["Årsresultat", "Annen egenkapital", "Utbytte"],
            "source_text": ["Årsresultat 500", "Annen egenkapital 80", "Utbytte 30"],
            "ub": [500.0, 80.0, 30.0],
            "source_page": [1, 1, 2],
            "confidence": [0.9, 0.8, 0.7],
        }
    )

    suggestions = suggest_associate_fields_from_line_basis(df, ownership_pct=40.0)
    as_map = {item.field_name: item for item in suggestions}

    assert round(as_map["share_of_result"].share_amount, 2) == 200.0
    assert round(as_map["share_of_other_equity"].share_amount, 2) == 32.0
    assert round(as_map["dividends"].share_amount, 2) == 12.0


# ---- goodwill tests ---------------------------------------------------------


def test_compute_goodwill_basic() -> None:
    case = AssociateCase(
        acquisition_cost=500_000.0,
        share_of_net_assets_at_acquisition=350_000.0,
        goodwill_useful_life_years=5,
    )
    info = compute_goodwill_amortization(case)
    assert info["goodwill"] == 150_000.0
    assert info["annual_amortization"] == 30_000.0
    assert info["goodwill_useful_life_years"] == 5


def test_goodwill_zero_when_no_cost() -> None:
    case = AssociateCase(
        acquisition_cost=0.0,
        share_of_net_assets_at_acquisition=0.0,
    )
    info = compute_goodwill_amortization(case)
    assert info["goodwill"] == 0.0
    assert info["annual_amortization"] == 0.0


def test_goodwill_negative_is_badwill() -> None:
    case = AssociateCase(
        acquisition_cost=200_000.0,
        share_of_net_assets_at_acquisition=300_000.0,
        goodwill_useful_life_years=10,
    )
    info = compute_goodwill_amortization(case)
    assert info["goodwill"] == -100_000.0
    assert info["annual_amortization"] == -10_000.0


def test_goodwill_amortization_years() -> None:
    case = AssociateCase(
        acquisition_cost=600_000.0,
        share_of_net_assets_at_acquisition=400_000.0,
        goodwill_useful_life_years=10,
    )
    info = compute_goodwill_amortization(case)
    assert info["goodwill"] == 200_000.0
    assert info["annual_amortization"] == 20_000.0
    assert info["goodwill_useful_life_years"] == 10


def test_build_calculation_includes_goodwill_info() -> None:
    case = _case()
    case.acquisition_cost = 500_000.0
    case.share_of_net_assets_at_acquisition = 350_000.0
    case.goodwill_useful_life_years = 5
    calc = build_associate_case_calculation(case)
    assert "goodwill" in calc
    assert calc["goodwill"]["goodwill"] == 150_000.0
    assert calc["goodwill"]["annual_amortization"] == 30_000.0
