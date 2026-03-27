"""Tests for consolidation.engine — deterministisk konsolideringsmotor."""

from __future__ import annotations

import pandas as pd
import pytest

from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
)
from consolidation.engine import run_consolidation
from consolidation.mapping import ConfigNotLoadedError


# ---------------------------------------------------------------------------
# Syntetisk testdata
# ---------------------------------------------------------------------------

def _intervals_df() -> pd.DataFrame:
    return pd.DataFrame({
        "fra": [1000, 3000],
        "til": [1999, 3999],
        "regnr": [10, 11],
    })


def _regnskapslinjer_df() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11, 20],
        "regnskapslinje": ["Eiendeler", "Inntekter", "SUM"],
        "sumpost": [False, False, True],
        "formel": [None, None, "=10+11"],
        "sumnivaa": [None, None, None],
        "delsumnr": [None, None, None],
        "sumnr": [None, None, None],
        "sumnr2": [None, None, None],
        "sluttsumnr": [None, None, None],
    })


def _company_a_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "3000"],
        "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0],
        "ub": [100.0, -200.0],
        "netto": [100.0, -200.0],
    })


def _company_b_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1500", "3500"],
        "kontonavn": ["Varelager", "Tjenestesal"],
        "ib": [0.0, 0.0],
        "ub": [50.0, -100.0],
        "netto": [50.0, -100.0],
    })


def _sample_project(with_elimination: bool = True) -> ConsolidationProject:
    eliminations = []
    if with_elimination:
        eliminations.append(
            EliminationJournal(
                journal_id="e1",
                name="Internhandel",
                lines=[
                    EliminationLine(regnr=11, company_id="a", amount=50.0, description="Elim interco"),
                    EliminationLine(regnr=11, company_id="b", amount=-50.0, description="Elim interco mot"),
                ],
            )
        )
    return ConsolidationProject(
        project_id="p1",
        client="TestKonsern",
        year="2025",
        companies=[
            CompanyTB(company_id="a", name="Morselskap AS", row_count=2),
            CompanyTB(company_id="b", name="Datter AS", row_count=2),
        ],
        mapping_config=MappingConfig(),
        eliminations=eliminations,
    )


@pytest.fixture
def _mock_config(monkeypatch):
    """Monkeypatch regnskap_config for aa unngaa filsystem-avhengighet."""
    import regnskap_config

    monkeypatch.setattr(
        regnskap_config, "load_kontoplan_mapping",
        lambda **kw: _intervals_df(),
    )
    monkeypatch.setattr(
        regnskap_config, "load_regnskapslinjer",
        lambda **kw: _regnskapslinjer_df(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRunConsolidation:
    def test_two_companies_one_elimination(self, _mock_config):
        proj = _sample_project(with_elimination=True)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, run_result = run_consolidation(proj, tbs)

        # Sjekk selskapskolonner (leaf-verdier)
        leaf = result_df[~result_df["sumpost"]]

        regnr_10 = leaf[leaf["regnr"] == 10].iloc[0]
        assert regnr_10["Morselskap AS"] == 100.0
        assert regnr_10["Datter AS"] == 50.0
        assert regnr_10["sum_foer_elim"] == 150.0
        assert regnr_10["eliminering"] == 0.0
        assert regnr_10["konsolidert"] == 150.0

        regnr_11 = leaf[leaf["regnr"] == 11].iloc[0]
        assert regnr_11["Morselskap AS"] == -200.0
        assert regnr_11["Datter AS"] == -100.0
        assert regnr_11["sum_foer_elim"] == -300.0
        # Eliminering: +50 + (-50) = 0 total for regnr 11
        assert regnr_11["eliminering"] == 0.0
        assert regnr_11["konsolidert"] == -300.0

        # Sjekk sumlinje (formel: =10+11)
        sum_row = result_df[result_df["regnr"] == 20].iloc[0]
        assert sum_row["sumpost"] == True  # noqa: E712 — numpy bool
        assert sum_row["konsolidert"] == pytest.approx(150.0 + (-300.0))

        # RunResult
        assert len(run_result.company_ids) == 2
        assert run_result.result_hash != ""
        assert len(run_result.warnings) == 0

    def test_elimination_single_regnr(self, _mock_config):
        """Eliminering som treffer bare ett regnr."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(company_id="b", name="Dat", row_count=2),
            ],
            eliminations=[
                EliminationJournal(
                    journal_id="e1", name="Enkel",
                    lines=[
                        EliminationLine(regnr=10, company_id="a", amount=25.0),
                        EliminationLine(regnr=10, company_id="b", amount=-25.0),
                    ],
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # 25 + (-25) = 0 netto eliminering paa regnr 10
        assert r10["eliminering"] == 0.0

    def test_hash_determinism(self, _mock_config):
        proj = _sample_project()
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        _, run1 = run_consolidation(proj, tbs)
        _, run2 = run_consolidation(proj, tbs)

        assert run1.result_hash == run2.result_hash

    def test_missing_tb_warns_but_continues(self, _mock_config):
        proj = _sample_project()
        # Bare TB for selskap "a"
        tbs = {"a": _company_a_tb()}

        result_df, run_result = run_consolidation(proj, tbs)

        assert len(run_result.company_ids) == 1
        assert "a" in run_result.company_ids
        assert any("Datter AS" in w for w in run_result.warnings)
        assert "Morselskap AS" in result_df.columns
        assert "Datter AS" not in result_df.columns

    def test_no_companies_raises(self, _mock_config):
        proj = ConsolidationProject(client="Tom", year="2025")

        with pytest.raises(ValueError, match="ingen selskaper"):
            run_consolidation(proj, {})

    def test_no_valid_tbs_raises(self, _mock_config):
        proj = _sample_project()
        # Tomme TBer
        tbs = {"a": pd.DataFrame(), "b": pd.DataFrame()}

        with pytest.raises(ValueError, match="Ingen gyldige"):
            run_consolidation(proj, tbs)

    def test_config_not_loaded_raises(self, monkeypatch):
        import regnskap_config

        monkeypatch.setattr(
            regnskap_config, "load_kontoplan_mapping",
            lambda **kw: (_ for _ in ()).throw(FileNotFoundError("test")),
        )

        proj = _sample_project()
        tbs = {"a": _company_a_tb()}

        with pytest.raises(ConfigNotLoadedError):
            run_consolidation(proj, tbs)

    def test_unmapped_accounts_in_warnings(self, _mock_config):
        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[CompanyTB(company_id="a", name="Mor", row_count=3)],
        )
        # Konto 9999 faller utenfor intervallene
        tb = pd.DataFrame({
            "konto": ["1000", "9999"],
            "kontonavn": ["Bank", "Ukjent"],
            "ib": [0.0, 0.0],
            "ub": [100.0, 50.0],
            "netto": [100.0, 50.0],
        })
        _, run_result = run_consolidation(proj, {"a": tb})

        assert any("umappede" in w for w in run_result.warnings)
        assert any("9999" in w for w in run_result.warnings)

    def test_unbalanced_elimination_warns(self, _mock_config):
        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[CompanyTB(company_id="a", name="Mor", row_count=2)],
            eliminations=[
                EliminationJournal(
                    journal_id="e1", name="Ubalansert",
                    lines=[
                        EliminationLine(regnr=10, company_id="a", amount=100.0),
                    ],
                ),
            ],
        )
        _, run_result = run_consolidation(proj, {"a": _company_a_tb()})
        assert any("ikke balansert" in w for w in run_result.warnings)
