"""Verification tests for consolidation product quality.

These tests simulate the full end-to-end flow:
V1: Mor column has real values after run
V2: Switching between Valgt selskap / Konsolidert
V3: Hide-zero filter preserves sumlines and elim lines
V4: Project persistence (save/load round-trip)
V5: Mapping change reflects in result after re-run
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
    project_to_dict,
    project_from_dict,
)
from consolidation.engine import run_consolidation


# ---------------------------------------------------------------------------
# Shared test data — realistic 5-company scenario like Ortomedic
# ---------------------------------------------------------------------------

def _intervals() -> pd.DataFrame:
    return pd.DataFrame({
        "fra": [1000, 1500, 3000, 4000, 6000, 7000],
        "til": [1499, 1999, 3999, 5999, 6999, 7999],
        "regnr": [10, 11, 30, 40, 60, 70],
    })


def _regnskapslinjer() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11, 20, 30, 40, 50, 60, 70, 80, 99],
        "regnskapslinje": [
            "Bankinnskudd", "Kundefordringer", "Sum omloepsmidler",
            "Salgsinntekt", "Varekostnad", "Driftsresultat",
            "Renteinntekt", "Rentekostnad", "Finansresultat",
            "Resultat foer skatt",
        ],
        "sumpost": [False, False, True, False, False, True, False, False, True, True],
        "formel": [None, None, "=10+11", None, None, "=30+40", None, None, "=60+70", "=20+50+80"],
        "sumnivaa": [None] * 10,
        "delsumnr": [None] * 10,
        "sumnr": [None] * 10,
        "sumnr2": [None] * 10,
        "sluttsumnr": [None] * 10,
    })


def _ortomedic_tb() -> pd.DataFrame:
    """Morselskap — Ortomedic AS."""
    return pd.DataFrame({
        "konto": ["1000", "1500", "3000", "4000", "6000", "7000"],
        "kontonavn": ["Bank", "Kundefordringer", "Salg", "Varekost", "Renteinntekt", "Rentekostnad"],
        "ib": [0.0] * 6,
        "ub": [500_000.0, 200_000.0, -3_000_000.0, 1_500_000.0, -50_000.0, 80_000.0],
        "netto": [500_000.0, 200_000.0, -3_000_000.0, 1_500_000.0, -50_000.0, 80_000.0],
    })


def _datter_a_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "3000", "4000"],
        "kontonavn": ["Bank", "Salg", "Varekost"],
        "ib": [0.0, 0.0, 0.0],
        "ub": [100_000.0, -800_000.0, 400_000.0],
        "netto": [100_000.0, -800_000.0, 400_000.0],
    })


def _datter_b_tb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1000", "1500", "3000", "4000"],
        "kontonavn": ["Bank", "Kundefordringer", "Salg", "Varekost"],
        "ib": [0.0] * 4,
        "ub": [50_000.0, 30_000.0, -500_000.0, 250_000.0],
        "netto": [50_000.0, 30_000.0, -500_000.0, 250_000.0],
    })


def _project_3_companies(with_elim=False) -> ConsolidationProject:
    elims = []
    if with_elim:
        elims.append(EliminationJournal(
            journal_id="e1", name="Interco",
            lines=[
                EliminationLine(regnr=30, company_id="mor", amount=200_000.0, description="Interco salg"),
                EliminationLine(regnr=40, company_id="dat_a", amount=-200_000.0, description="Interco kjop"),
            ],
        ))
    return ConsolidationProject(
        project_id="p_orto",
        client="Ortomedic",
        year="2025",
        parent_company_id="mor",
        companies=[
            CompanyTB(company_id="mor", name="Ortomedic AS", row_count=6),
            CompanyTB(company_id="dat_a", name="Micromedic Aps", row_count=3),
            CompanyTB(company_id="dat_b", name="OrtoPharma AS", row_count=4),
        ],
        mapping_config=MappingConfig(),
        eliminations=elims,
    )


@pytest.fixture
def _mock_config(monkeypatch):
    import regnskap_config
    monkeypatch.setattr(regnskap_config, "load_kontoplan_mapping", lambda **kw: _intervals())
    monkeypatch.setattr(regnskap_config, "load_regnskapslinjer", lambda **kw: _regnskapslinjer())


# ---------------------------------------------------------------------------
# V1: Mor-kolonnen har reelle tall
# ---------------------------------------------------------------------------

class TestV1MorHasValues:
    def test_mor_column_has_ortomedic_values(self, _mock_config):
        proj = _project_3_companies()
        tbs = {
            "mor": _ortomedic_tb(),
            "dat_a": _datter_a_tb(),
            "dat_b": _datter_b_tb(),
        }
        result, run = run_consolidation(proj, tbs)

        assert "Mor" in result.columns
        assert "Doetre" in result.columns

        leaf = result[~result["sumpost"]]

        # Bankinnskudd (regnr 10): Mor=500k, Doetre=100k+50k=150k
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        assert r10["Mor"] == 500_000.0
        assert r10["Doetre"] == 150_000.0

        # Salgsinntekt (regnr 30): Mor=-3M, Doetre=-800k+(-500k)=-1.3M
        r30 = leaf[leaf["regnr"] == 30].iloc[0]
        assert r30["Mor"] == -3_000_000.0
        assert r30["Doetre"] == -1_300_000.0

        # Konsolidert = sum_foer_elim + eliminering
        assert r30["konsolidert"] == pytest.approx(-4_300_000.0)

    def test_mor_with_elimination(self, _mock_config):
        proj = _project_3_companies(with_elim=True)
        tbs = {
            "mor": _ortomedic_tb(),
            "dat_a": _datter_a_tb(),
            "dat_b": _datter_b_tb(),
        }
        result, _ = run_consolidation(proj, tbs)
        leaf = result[~result["sumpost"]]

        # Eliminering paa regnr 30: +200k
        r30 = leaf[leaf["regnr"] == 30].iloc[0]
        assert r30["eliminering"] == 200_000.0

        # Eliminering paa regnr 40: -200k
        r40 = leaf[leaf["regnr"] == 40].iloc[0]
        assert r40["eliminering"] == -200_000.0

        # Konsolidert regnr 30: sum_foer_elim + 200k
        assert r30["konsolidert"] == pytest.approx(r30["sum_foer_elim"] + 200_000.0)

    def test_sumlines_computed_for_mor_doetre(self, _mock_config):
        proj = _project_3_companies()
        tbs = {
            "mor": _ortomedic_tb(),
            "dat_a": _datter_a_tb(),
            "dat_b": _datter_b_tb(),
        }
        result, _ = run_consolidation(proj, tbs)

        # Sum omloepsmidler (regnr 20, formel: =10+11)
        r20 = result[result["regnr"] == 20].iloc[0]
        assert r20["sumpost"] == True  # noqa
        # Mor: bank 500k + kundeford 200k = 700k
        assert r20["Mor"] == pytest.approx(700_000.0)
        # Doetre: (100k+50k) + (0+30k) = 180k
        assert r20["Doetre"] == pytest.approx(180_000.0)

        # Driftsresultat (regnr 50, formel: =30+40)
        r50 = result[result["regnr"] == 50].iloc[0]
        # Mor: -3M + 1.5M = -1.5M
        assert r50["Mor"] == pytest.approx(-1_500_000.0)

        # Resultat foer skatt (regnr 99, formel: =20+50+80)
        r99 = result[result["regnr"] == 99].iloc[0]
        assert r99["sumpost"] == True  # noqa
        # Should be non-zero
        assert abs(r99["konsolidert"]) > 0.01


# ---------------------------------------------------------------------------
# V2: Switching between modes does not lose data
# ---------------------------------------------------------------------------

class TestV2ModeSwitching:
    def test_both_dataframes_cached(self, _mock_config):
        """After company select + run, both result DFs should be available."""
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        # Mock all UI elements
        page._tree_result = MagicMock()
        page._tree_result.get_children.return_value = []
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = False
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()
        page._right_nb = MagicMock()

        # Build a company result
        page._mapped_tbs = {"mor": MagicMock()}
        page._regnskapslinjer = _regnskapslinjer()

        # Simulate: after run, consolidated DF is stored
        proj = _project_3_companies()
        tbs = {"mor": _ortomedic_tb(), "dat_a": _datter_a_tb(), "dat_b": _datter_b_tb()}
        result_df, _ = run_consolidation(proj, tbs)

        page._consolidated_result_df = result_df

        # Simulate: company result also stored
        company_df = pd.DataFrame({
            "regnr": [10], "regnskapslinje": ["Bank"],
            "sumpost": [False], "formel": [None], "UB": [500_000.0],
        })
        page._company_result_df = company_df

        # Switch to Konsolidert
        page._result_mode_var.get.return_value = "Konsolidert"
        page._refresh_result_view()

        # Tree should have been populated with consolidated data
        assert page._tree_result.delete.called
        # The columns should include Mor
        cols_call = page._tree_result.__setitem__.call_args
        assert cols_call is not None
        set_cols = cols_call[0][1]
        assert "Mor" in set_cols

        # Switch back to Valgt selskap
        page._tree_result.reset_mock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._refresh_result_view()

        cols_call2 = page._tree_result.__setitem__.call_args
        set_cols2 = cols_call2[0][1]
        assert "UB" in set_cols2

    def test_empty_consolidated_shows_nothing(self):
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tree_result = MagicMock()
        page._tree_result.get_children.return_value = []
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Konsolidert"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = True
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()

        page._refresh_result_view()

        # Should just clear the tree, not crash
        page._tree_result.delete.assert_called()


# ---------------------------------------------------------------------------
# V3: Hide-zero preserves sumlines and elim lines
# ---------------------------------------------------------------------------

class TestV3HideZeroFilter:
    def test_sumlines_always_shown(self, _mock_config):
        """Sum lines should appear even if their value is 0."""
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tree_result = MagicMock()
        page._tree_result.get_children.return_value = []
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = True  # hide zero ON
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()

        # Create result with a zero leaf and a zero sumline
        result_df = pd.DataFrame({
            "regnr": [10, 11, 20],
            "regnskapslinje": ["Bank", "Ford", "Sum"],
            "sumpost": [False, False, True],
            "formel": [None, None, "=10+11"],
            "UB": [0.0, 0.0, 0.0],
        })
        page._company_result_df = result_df
        page._refresh_result_view()

        # Zero leaf lines should NOT be inserted (hide zero ON)
        # Sum lines SHOULD be inserted
        insert_calls = page._tree_result.insert.call_args_list
        inserted_regnrs = []
        for call in insert_calls:
            vals = call[1].get("values", call[0][2] if len(call[0]) > 2 else None)
            if vals:
                inserted_regnrs.append(vals[0])

        # Sumline 20 should be present, leaf 10 and 11 should not
        assert 20 in inserted_regnrs
        assert 10 not in inserted_regnrs
        assert 11 not in inserted_regnrs

    def test_elim_line_with_nonzero_shown(self, _mock_config):
        """Lines with elimination value should be shown even if other cols are low."""
        proj = _project_3_companies(with_elim=True)
        tbs = {"mor": _ortomedic_tb(), "dat_a": _datter_a_tb(), "dat_b": _datter_b_tb()}
        result, _ = run_consolidation(proj, tbs)

        # Check that regnr 30 (has eliminering) has non-zero values
        leaf = result[~result["sumpost"]]
        r30 = leaf[leaf["regnr"] == 30].iloc[0]

        # This line has sales values AND elimination — should NOT be filtered
        data_cols = ["Mor", "Doetre", "eliminering", "konsolidert"]
        any_nonzero = any(abs(float(r30[c])) > 0.005 for c in data_cols)
        assert any_nonzero, "Elim line should have non-zero values"

    def test_hide_zero_off_shows_everything(self, _mock_config):
        from page_consolidation import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tree_result = MagicMock()
        page._tree_result.get_children.return_value = []
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = False  # hide zero OFF
        page._company_result_df = None
        page._consolidated_result_df = None
        page._preview_result_df = None
        page._preview_label_var = MagicMock()

        result_df = pd.DataFrame({
            "regnr": [10, 11, 20],
            "regnskapslinje": ["Bank", "Ford", "Sum"],
            "sumpost": [False, False, True],
            "formel": [None, None, "=10+11"],
            "UB": [0.0, 100.0, 100.0],
        })
        page._company_result_df = result_df
        page._refresh_result_view()

        # All 3 rows should be inserted (including zero leaf)
        assert page._tree_result.insert.call_count == 3


# ---------------------------------------------------------------------------
# V4: Project persistence round-trip
# ---------------------------------------------------------------------------

class TestV4Persistence:
    def test_full_project_roundtrip(self, tmp_path):
        """Save and load a project with parent_company_id, companies, and overrides."""
        from consolidation import storage

        proj = _project_3_companies(with_elim=True)
        proj.mapping_config.company_overrides = {"mor": {"9999": 30}}

        # Save
        d = project_to_dict(proj)
        restored = project_from_dict(d)

        assert restored.parent_company_id == "mor"
        assert len(restored.companies) == 3
        assert restored.companies[0].name == "Ortomedic AS"
        assert restored.mapping_config.company_overrides == {"mor": {"9999": 30}}
        assert len(restored.eliminations) == 1
        assert restored.eliminations[0].name == "Interco"

    def test_parent_survives_storage_roundtrip(self, tmp_path, monkeypatch):
        """Save to disk and reload — parent_company_id must survive."""
        from consolidation import storage

        # Point storage at tmp_path
        monkeypatch.setattr(
            storage, "project_dir",
            lambda client, year: tmp_path,
        )

        proj = _project_3_companies()
        storage.save_project(proj)

        loaded = storage.load_project("Ortomedic", "2025")
        assert loaded is not None
        assert loaded.parent_company_id == "mor"
        assert len(loaded.companies) == 3


# ---------------------------------------------------------------------------
# V5: Mapping change reflects in result after re-run
# ---------------------------------------------------------------------------

class TestV5MappingChangeUpdatesResult:
    def test_override_changes_result(self, _mock_config):
        """Adding a mapping override must change the consolidation result."""
        proj = _project_3_companies()
        tbs = {"mor": _ortomedic_tb(), "dat_a": _datter_a_tb(), "dat_b": _datter_b_tb()}

        # Run without overrides
        result1, _ = run_consolidation(proj, tbs)
        leaf1 = result1[~result1["sumpost"]]

        # Ortomedic konto 7000 (Rentekostnad) maps to regnr 70 via interval
        r70_before = leaf1[leaf1["regnr"] == 70].iloc[0]
        assert r70_before["Mor"] == 80_000.0

        # Now override: move konto 7000 to regnr 40 (Varekostnad)
        proj.mapping_config.company_overrides = {"mor": {"7000": 40}}

        result2, _ = run_consolidation(proj, tbs)
        leaf2 = result2[~result2["sumpost"]]

        # regnr 70 should now be 0 for Mor (7000 moved away)
        r70_after = leaf2[leaf2["regnr"] == 70].iloc[0]
        assert r70_after["Mor"] == 0.0

        # regnr 40 should now include the 80k from konto 7000
        r40_after = leaf2[leaf2["regnr"] == 40].iloc[0]
        # Was 1_500_000, now 1_500_000 + 80_000 = 1_580_000
        assert r40_after["Mor"] == pytest.approx(1_580_000.0)

    def test_override_reflected_in_doetre(self, _mock_config):
        """Override on datter should change Doetre column."""
        proj = _project_3_companies()
        tbs = {"mor": _ortomedic_tb(), "dat_a": _datter_a_tb(), "dat_b": _datter_b_tb()}

        # Move dat_a konto 3000 (Salg, -800k, regnr 30) to regnr 40
        proj.mapping_config.company_overrides = {"dat_a": {"3000": 40}}

        result, _ = run_consolidation(proj, tbs)
        leaf = result[~result["sumpost"]]

        # regnr 30 Doetre should now only have dat_b: -500k
        r30 = leaf[leaf["regnr"] == 30].iloc[0]
        assert r30["Doetre"] == pytest.approx(-500_000.0)

        # regnr 40 Doetre should have dat_a: 400k + (-800k) + dat_b: 250k = -150k
        r40 = leaf[leaf["regnr"] == 40].iloc[0]
        assert r40["Doetre"] == pytest.approx(-150_000.0)
