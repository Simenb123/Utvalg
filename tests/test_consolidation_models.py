"""Tests for consolidation.models — dataclass round-trip and invariants."""

from __future__ import annotations

from consolidation.models import (
    AssociateAdjustmentRow,
    AssociateCase,
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
    RunResult,
    project_from_dict,
    project_to_dict,
)


def _sample_project() -> ConsolidationProject:
    """Lag et eksempelprosjekt med 2 selskaper og 1 eliminering."""
    c1 = CompanyTB(
        company_id="c1",
        name="Morselskap AS",
        source_file="mor.xlsx",
        source_type="excel",
        row_count=100,
        has_ib=True,
    )
    c2 = CompanyTB(
        company_id="c2",
        name="Datter AS",
        source_file="datter.xml",
        source_type="saft",
        row_count=50,
        has_ib=False,
    )

    elim = EliminationJournal(
        journal_id="e1",
        name="Internhandel",
        lines=[
            EliminationLine(regnr=3000, company_id="c1", amount=-500000.0, description="Salg"),
            EliminationLine(regnr=4000, company_id="c2", amount=500000.0, description="Kjop"),
        ],
    )

    return ConsolidationProject(
        project_id="p1",
        client="Test AS",
        year="2025",
        companies=[c1, c2],
        associate_cases=[
            AssociateCase(
                case_id="assoc1",
                name="Tilknyttet AS",
                investor_company_id="c1",
                ownership_pct=40.0,
                journal_id="ek1",
                line_mapping={"investment_regnr": 575, "result_regnr": 100, "other_equity_regnr": 695, "retained_earnings_regnr": 705},
                manual_adjustment_rows=[
                    AssociateAdjustmentRow(
                        row_id="adj1",
                        label="Emisjon",
                        amount=25000.0,
                        offset_regnr=695,
                        description="Kapitalendring",
                    )
                ],
            )
        ],
        mapping_config=MappingConfig(company_overrides={"c1": {"1920": 1900}}),
        eliminations=[elim],
        runs=[],
    )


class TestProjectRoundTrip:
    def test_serialize_deserialize(self):
        proj = _sample_project()
        d = project_to_dict(proj)
        assert d["schema_version"] == 4
        assert len(d["associate_cases"]) == 1
        assert d["client"] == "Test AS"
        assert len(d["companies"]) == 2
        assert len(d["eliminations"]) == 1
        assert len(d["eliminations"][0]["lines"]) == 2

        proj2 = project_from_dict(d)
        assert proj2.project_id == "p1"
        assert proj2.client == "Test AS"
        assert proj2.year == "2025"
        assert len(proj2.companies) == 2
        assert len(proj2.associate_cases) == 1
        assert proj2.companies[0].name == "Morselskap AS"
        assert proj2.companies[1].source_type == "saft"
        assert proj2.associate_cases[0].manual_adjustment_rows[0].label == "Emisjon"
        assert len(proj2.eliminations) == 1
        assert proj2.eliminations[0].name == "Internhandel"
        assert len(proj2.eliminations[0].lines) == 2

    def test_mapping_config_preserved(self):
        proj = _sample_project()
        d = project_to_dict(proj)
        proj2 = project_from_dict(d)
        assert proj2.mapping_config.company_overrides == {"c1": {"1920": 1900}}

    def test_runs_preserved(self):
        proj = _sample_project()
        proj.runs.append(RunResult(
            run_id="r1",
            company_ids=["c1", "c2"],
            elimination_ids=["e1"],
            warnings=["Testadvarsel"],
            result_hash="abc123",
        ))
        d = project_to_dict(proj)
        proj2 = project_from_dict(d)
        assert len(proj2.runs) == 1
        assert proj2.runs[0].run_id == "r1"
        assert proj2.runs[0].warnings == ["Testadvarsel"]
        assert proj2.runs[0].result_hash == "abc123"


class TestEliminationJournal:
    def test_display_label_prefers_voucher_no(self):
        j = EliminationJournal(voucher_no=7, name="Internhandel")
        assert j.display_label == "Bilag 7"

    def test_balanced_journal(self):
        j = EliminationJournal(
            name="Test",
            lines=[
                EliminationLine(regnr=3000, company_id="c1", amount=-100.0),
                EliminationLine(regnr=4000, company_id="c2", amount=100.0),
            ],
        )
        assert j.is_balanced
        assert abs(j.net) < 0.005

    def test_unbalanced_journal(self):
        j = EliminationJournal(
            name="Test",
            lines=[
                EliminationLine(regnr=3000, company_id="c1", amount=-100.0),
                EliminationLine(regnr=4000, company_id="c2", amount=50.0),
            ],
        )
        assert not j.is_balanced
        assert abs(j.net - (-50.0)) < 0.005

    def test_empty_journal_is_balanced(self):
        j = EliminationJournal(name="Tom")
        assert j.is_balanced
        assert j.net == 0.0


class TestProjectHelpers:
    def test_find_company(self):
        proj = _sample_project()
        assert proj.find_company("c1") is not None
        assert proj.find_company("c1").name == "Morselskap AS"
        assert proj.find_company("nonexistent") is None

    def test_find_journal(self):
        proj = _sample_project()
        assert proj.find_journal("e1") is not None
        assert proj.find_journal("e1").name == "Internhandel"
        assert proj.find_journal("nonexistent") is None

    def test_find_associate_case(self):
        proj = _sample_project()
        assert proj.find_associate_case("assoc1") is not None
        assert proj.find_associate_case("assoc1").name == "Tilknyttet AS"
        assert proj.find_associate_case("missing") is None

    def test_touch_updates_timestamp(self):
        proj = _sample_project()
        old_ts = proj.updated_at
        import time
        time.sleep(0.01)
        proj.touch()
        assert proj.updated_at > old_ts

    def test_ensure_elimination_voucher_numbers_backfills(self):
        proj = _sample_project()
        proj.eliminations.append(
            EliminationJournal(journal_id="e2", name="", voucher_no=0),
        )

        changed = proj.ensure_elimination_voucher_numbers()

        assert changed is True
        assert [j.voucher_no for j in proj.eliminations] == [1, 2]
        assert proj.eliminations[1].name == "Bilag 2"

    def test_next_elimination_voucher_no_after_backfill(self):
        proj = _sample_project()
        proj.ensure_elimination_voucher_numbers()

        assert proj.next_elimination_voucher_no() == 2


class TestNewFieldsRoundTrip:
    """Verify serialization of fields added in Fase 2-4."""

    def test_goodwill_fields_roundtrip(self):
        proj = ConsolidationProject(
            client="T", year="2025",
            associate_cases=[
                AssociateCase(
                    name="GW AS",
                    acquisition_cost=500_000.0,
                    share_of_net_assets_at_acquisition=350_000.0,
                    goodwill_useful_life_years=10,
                    goodwill_method="linear",
                )
            ],
        )
        d = project_to_dict(proj)
        restored = project_from_dict(d)
        c = restored.associate_cases[0]
        assert c.acquisition_cost == 500_000.0
        assert c.share_of_net_assets_at_acquisition == 350_000.0
        assert c.goodwill_useful_life_years == 10
        assert c.goodwill_method == "linear"

    def test_konto_field_roundtrip(self):
        proj = ConsolidationProject(
            client="T", year="2025",
            eliminations=[
                EliminationJournal(
                    lines=[
                        EliminationLine(regnr=10, amount=100.0, konto="1500"),
                        EliminationLine(regnr=20, amount=-100.0),
                    ]
                )
            ],
        )
        d = project_to_dict(proj)
        restored = project_from_dict(d)
        lines = restored.eliminations[0].lines
        assert lines[0].konto == "1500"
        assert lines[1].konto == ""

    def test_default_associate_line_mapping_roundtrip(self):
        proj = ConsolidationProject(
            client="T", year="2025",
            default_associate_line_mapping={
                "investment_regnr": 999,
                "result_regnr": 888,
            },
        )
        d = project_to_dict(proj)
        restored = project_from_dict(d)
        assert restored.default_associate_line_mapping == {
            "investment_regnr": 999,
            "result_regnr": 888,
        }

    def test_old_project_without_new_fields_loads_with_defaults(self):
        """Simulates loading a project saved before new fields existed."""
        d = {
            "schema_version": 4,
            "project_id": "old",
            "client": "Old AS",
            "year": "2024",
            "companies": [],
            "associate_cases": [
                {
                    "case_id": "a1",
                    "name": "Old Case",
                    "investor_company_id": "",
                    "ownership_pct": 30.0,
                    "status": "draft",
                    # No goodwill fields, no konto
                }
            ],
            "eliminations": [
                {
                    "journal_id": "j1",
                    "lines": [
                        {"regnr": 10, "amount": 50.0}
                        # No konto field
                    ],
                }
            ],
        }
        proj = project_from_dict(d)
        case = proj.associate_cases[0]
        assert case.acquisition_cost == 0.0
        assert case.goodwill_useful_life_years == 5
        line = proj.eliminations[0].lines[0]
        assert line.konto == ""
        assert proj.default_associate_line_mapping == {}
