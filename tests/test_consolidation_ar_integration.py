from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd


def _sample_tb() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "konto": ["1000", "3000"],
            "kontonavn": ["Bank", "Salg"],
            "ib": [10.0, 0.0],
            "ub": [100.0, -90.0],
            "netto": [90.0, -90.0],
        }
    )


def _make_page(project):
    from src.pages.consolidation.frontend.page import ConsolidationPage

    page = ConsolidationPage.__new__(ConsolidationPage)
    page._tk_ok = False
    page._project = project
    page._company_tbs = {}
    page._company_line_bases = {}
    page._mapped_tbs = {}
    page._mapping_pct = {}
    page._mapping_unmapped = {}
    page._compute_mapping_status = MagicMock()
    page._refresh_company_tree = MagicMock()
    page._update_status = MagicMock()
    page._select_and_show_company = MagicMock()
    page._invalidate_run_cache = MagicMock()
    page._refresh_associate_case_tree = MagicMock()
    page._refresh_simple_elim_tree = MagicMock()
    page._refresh_journal_tree = MagicMock()
    return page


def test_import_company_from_client_name_returns_company(monkeypatch, tmp_path) -> None:
    import client_store
    from src.pages.consolidation.backend.models import ConsolidationProject

    monkeypatch.setattr(
        client_store,
        "years_dir",
        lambda client, year: tmp_path / client / "years" / year,
    )
    monkeypatch.setattr(
        client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: SimpleNamespace(
            path=str(tmp_path / "air_cargo_sb.xlsx"),
            filename="air_cargo_sb.xlsx",
            client_display=display_name,
            year=year,
            dtype=dtype,
        ),
    )
    monkeypatch.setattr("trial_balance_reader.read_trial_balance", lambda _path: _sample_tb())
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    page = _make_page(ConsolidationProject(client="Air Management AS", year="2024"))

    company = page.import_company_from_client_name(
        "Air Cargo Logistics AS",
        target_company_name="Air Cargo Logistics AS",
    )

    assert company is not None
    assert company.name == "Air Cargo Logistics AS"
    assert company.source_type == "client_store_sb"
    assert page._project.companies[0].company_id == company.company_id
    pd.testing.assert_frame_equal(page._company_tbs[company.company_id], _sample_tb())


def test_create_or_update_associate_case_from_ar_relation_upserts_case(monkeypatch) -> None:
    from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject

    monkeypatch.setattr("src.pages.consolidation.frontend.page.storage.save_project", MagicMock())

    project = ConsolidationProject(
        client="Air Management AS",
        year="2024",
        parent_company_id="mor",
        companies=[CompanyTB(company_id="mor", name="Air Management AS")],
    )
    page = _make_page(project)

    case = page.create_or_update_associate_case_from_ar_relation(
        company_name="Live Seafood Center AS",
        company_orgnr="918038035",
        ownership_pct=50.0,
        matched_client="Live Seafood Center AS",
        relation_type="vurder",
        source_ref="AR 2024",
        note="Opprettet fra aksjonærregister",
    )

    assert case is not None
    assert len(project.associate_cases) == 1
    assert case.name == "Live Seafood Center AS"
    assert case.investor_company_id == "mor"
    assert case.ownership_pct == 50.0
    assert case.source_mode == "ar"
    assert case.status == "draft"
    assert "AR orgnr: 918038035" in case.notes
    assert "AR relasjon: vurder" in case.notes
    assert "AR klientmatch: Live Seafood Center AS" in case.notes

    updated = page.create_or_update_associate_case_from_ar_relation(
        company_name="Live Seafood Center AS",
        company_orgnr="918038035",
        ownership_pct=40.0,
        matched_client="Live Seafood Center AS",
        relation_type="tilknyttet",
        source_ref="AR 2024",
        note="Oppdatert",
    )

    assert updated is not None
    assert updated.case_id == case.case_id
    assert len(project.associate_cases) == 1
    assert updated.ownership_pct == 40.0
    assert "AR relasjon: tilknyttet" in updated.notes


def test_batch_import_daughters_multiple(monkeypatch, tmp_path) -> None:
    """Batch-import 3 companies with active SB — all should succeed."""
    import client_store
    from src.pages.consolidation.backend.models import ConsolidationProject

    monkeypatch.setattr(
        client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: SimpleNamespace(
            path=str(tmp_path / f"{display_name}.xlsx"),
            filename=f"{display_name}.xlsx",
        ),
    )
    monkeypatch.setattr("trial_balance_reader.read_trial_balance", lambda _path: _sample_tb())
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    page = _make_page(ConsolidationProject(client="Mor AS", year="2024"))

    rows = [
        {"company_name": "Datter A", "matched_client": "Datter A", "has_active_sb": True},
        {"company_name": "Datter B", "matched_client": "Datter B", "has_active_sb": True},
        {"company_name": "Datter C", "matched_client": "Datter C", "has_active_sb": True},
    ]
    results = page.import_companies_from_ar_batch(rows)

    assert len(results) == 3
    assert all(r is not None for r in results)
    assert len(page._project.companies) == 3
    names = {c.name for c in page._project.companies}
    assert names == {"Datter A", "Datter B", "Datter C"}


def test_batch_import_skips_missing_sb(monkeypatch, tmp_path) -> None:
    """Batch-import with a mix of importable and non-importable rows."""
    import client_store
    from src.pages.consolidation.backend.models import ConsolidationProject

    monkeypatch.setattr(
        client_store,
        "get_active_version",
        lambda display_name, *, year, dtype: SimpleNamespace(
            path=str(tmp_path / f"{display_name}.xlsx"),
            filename=f"{display_name}.xlsx",
        ),
    )
    monkeypatch.setattr("trial_balance_reader.read_trial_balance", lambda _path: _sample_tb())
    monkeypatch.setattr("src.pages.consolidation.frontend.page.messagebox", MagicMock())

    page = _make_page(ConsolidationProject(client="Mor AS", year="2024"))

    rows = [
        {"company_name": "OK AS", "matched_client": "OK AS", "has_active_sb": True},
        {"company_name": "No Match", "matched_client": "", "has_active_sb": False},
        {"company_name": "No SB", "matched_client": "No SB", "has_active_sb": False},
    ]
    results = page.import_companies_from_ar_batch(rows)

    assert len(results) == 3
    assert results[0] is not None
    assert results[1] is None
    assert results[2] is None
    assert len(page._project.companies) == 1


def test_batch_import_associates_multiple(monkeypatch) -> None:
    """Batch-create 2 associate cases from AR rows."""
    from src.pages.consolidation.backend.models import CompanyTB, ConsolidationProject

    monkeypatch.setattr("src.pages.consolidation.frontend.page.storage.save_project", MagicMock())

    project = ConsolidationProject(
        client="Mor AS",
        year="2024",
        parent_company_id="mor",
        companies=[CompanyTB(company_id="mor", name="Mor AS")],
    )
    page = _make_page(project)

    rows = [
        {
            "company_name": "Tilknyttet A",
            "company_orgnr": "111111111",
            "ownership_pct": 30.0,
            "matched_client": "Tilknyttet A",
            "relation_type": "tilknyttet",
            "note": "",
        },
        {
            "company_name": "Tilknyttet B",
            "company_orgnr": "222222222",
            "ownership_pct": 45.0,
            "matched_client": "",
            "relation_type": "vurder",
            "note": "Sjekk",
        },
    ]
    results = page.create_associate_cases_from_ar_batch(rows, year="2024")

    assert len(results) == 2
    assert all(r is not None for r in results)
    assert len(project.associate_cases) == 2
    names = {c.name for c in project.associate_cases}
    assert names == {"Tilknyttet A", "Tilknyttet B"}
    assert project.associate_cases[0].ownership_pct == 30.0
    assert project.associate_cases[1].ownership_pct == 45.0


def test_associate_next_step_text_warns_about_duplicate_company() -> None:
    from src.pages.consolidation.backend.models import AssociateCase, CompanyTB, ConsolidationProject
    from src.pages.consolidation.frontend.page import ConsolidationPage

    project = ConsolidationProject(
        client="Air Management AS",
        year="2024",
        parent_company_id="mor",
        companies=[
            CompanyTB(company_id="mor", name="Air Management AS"),
            CompanyTB(company_id="dat1", name="Live Seafood Center AS"),
        ],
    )
    page = ConsolidationPage.__new__(ConsolidationPage)
    page._project = project

    text = page._build_associate_next_step_text(
        AssociateCase(
            name="Live Seafood Center AS",
            investor_company_id="mor",
            ownership_pct=50.0,
        )
    )

    assert "Velg enten fullkonsolidering eller EK-metoden" in text


def test_default_line_mapping_applied_to_new_case() -> None:
    """Project-level default line mapping should merge into new AssociateCase."""
    from src.pages.consolidation.backend.models import AssociateCase, ConsolidationProject

    project = ConsolidationProject(
        client="Mor AS",
        year="2024",
        default_associate_line_mapping={
            "investment_regnr": 999,
            "result_regnr": 888,
        },
    )

    # Simulate what on_new_associate_case does with project defaults
    proj_defaults = project.default_associate_line_mapping or {}
    case = AssociateCase(name="Test AS")
    if proj_defaults:
        merged = dict(case.line_mapping)
        merged.update(proj_defaults)
        case.line_mapping = merged

    assert case.line_mapping["investment_regnr"] == 999
    assert case.line_mapping["result_regnr"] == 888
    assert case.line_mapping["other_equity_regnr"] == 695
    assert case.line_mapping["retained_earnings_regnr"] == 705
