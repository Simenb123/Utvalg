"""Tests for consolidation.models — dataclass round-trip and invariants."""

from __future__ import annotations

from consolidation.models import (
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
        mapping_config=MappingConfig(company_overrides={"c1": {"1920": 1900}}),
        eliminations=[elim],
        runs=[],
    )


class TestProjectRoundTrip:
    def test_serialize_deserialize(self):
        proj = _sample_project()
        d = project_to_dict(proj)
        assert d["schema_version"] == 2
        assert d["client"] == "Test AS"
        assert len(d["companies"]) == 2
        assert len(d["eliminations"]) == 1
        assert len(d["eliminations"][0]["lines"]) == 2

        proj2 = project_from_dict(d)
        assert proj2.project_id == "p1"
        assert proj2.client == "Test AS"
        assert proj2.year == "2025"
        assert len(proj2.companies) == 2
        assert proj2.companies[0].name == "Morselskap AS"
        assert proj2.companies[1].source_type == "saft"
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

    def test_touch_updates_timestamp(self):
        proj = _sample_project()
        old_ts = proj.updated_at
        import time
        time.sleep(0.01)
        proj.touch()
        assert proj.updated_at > old_ts
