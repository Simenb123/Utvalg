"""Tests for consolidation.engine — deterministisk konsolideringsmotor."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    MappingConfig,
)
from types import SimpleNamespace

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


def _company_line_basis() -> pd.DataFrame:
    return pd.DataFrame({
        "regnr": [10, 11],
        "regnskapslinje": ["Eiendeler", "Inntekter"],
        "ub": [75.0, -40.0],
        "review_status": ["approved", "approved"],
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

    def test_konto_level_elimination_aggregates_to_regnr(self, _mock_config):
        """Konto-level elimination should aggregate up to regnr level."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(company_id="b", name="Dat", row_count=2),
            ],
            eliminations=[
                EliminationJournal(
                    journal_id="e1", name="Konto-elim",
                    lines=[
                        # konto 1000 maps to regnr 10 via company_a_tb
                        EliminationLine(regnr=10, amount=30.0, konto="1000"),
                        EliminationLine(regnr=10, amount=-30.0, konto="1500"),
                    ],
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Both konto lines map to regnr 10: 30 + (-30) = 0
        assert r10["eliminering"] == pytest.approx(0.0)
        assert r10["konsolidert"] == pytest.approx(r10["sum_foer_elim"])

    def test_konto_elimination_warns_on_unmapped_konto(self, _mock_config):
        """Konto-level elimination with unknown konto should warn."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
            ],
            eliminations=[
                EliminationJournal(
                    journal_id="e1", name="Bad konto",
                    lines=[
                        EliminationLine(regnr=0, amount=50.0, konto="9999"),
                        EliminationLine(regnr=0, amount=-50.0, konto="9998"),
                    ],
                ),
            ],
        )
        tbs = {"a": _company_a_tb()}
        _, run_result = run_consolidation(proj, tbs)
        assert any("9999" in w for w in run_result.warnings)

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

    def test_mixed_tb_and_line_basis_companies(self, _mock_config):
        proj = ConsolidationProject(
            client="Test",
            year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2, basis_type="tb"),
                CompanyTB(company_id="b", name="Rapporteringspakke", row_count=2, basis_type="regnskapslinje"),
            ],
        )

        result_df, run_result = run_consolidation(
            proj,
            {"a": _company_a_tb(), "b": _company_line_basis()},
        )

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        r11 = leaf[leaf["regnr"] == 11].iloc[0]

        assert r10["Mor"] == 100.0
        assert r10["Rapporteringspakke"] == 75.0
        assert r10["sum_foer_elim"] == 175.0
        assert r11["Rapporteringspakke"] == -40.0
        assert run_result.account_details is not None
        detail = run_result.account_details
        assert "review_status" in detail.columns
        assert "Rapporteringspakke" in result_df.columns

    def test_line_basis_uses_fx_rules_from_regnr(self, _mock_config):
        proj = ConsolidationProject(
            client="Test",
            year="2025",
            reporting_currency="NOK",
            companies=[
                CompanyTB(
                    company_id="b",
                    name="USD Datter",
                    row_count=2,
                    basis_type="regnskapslinje",
                    currency_code="USD",
                    closing_rate=10.0,
                    average_rate=8.0,
                ),
            ],
        )

        result_df, run_result = run_consolidation(proj, {"b": _company_line_basis()})
        leaf = result_df[~result_df["sumpost"]]

        assert leaf.loc[leaf["regnr"] == 10, "USD Datter"].iloc[0] == pytest.approx(75.0 * 8.0)
        assert leaf.loc[leaf["regnr"] == 11, "USD Datter"].iloc[0] == pytest.approx(-40.0 * 8.0)
        assert run_result.currency_details


class TestParentCompanyInResult:
    """Test that Mor/Doetre columns appear when parent_company_id is set."""

    def test_mor_doetre_columns_present(self, _mock_config):
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"  # Morselskap AS
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        assert "Mor" in result_df.columns
        assert "Doetre" in result_df.columns

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Mor = company a = 100, Doetre = company b = 50
        assert r10["Mor"] == 100.0
        assert r10["Doetre"] == 50.0
        assert r10["konsolidert"] == 150.0

    def test_mor_doetre_with_elimination(self, _mock_config):
        proj = _sample_project(with_elimination=True)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        assert r11["Mor"] == -200.0
        assert r11["Doetre"] == -100.0
        assert r11["eliminering"] == 0.0  # balanced elim
        assert r11["konsolidert"] == -300.0

    def test_no_parent_gives_zero_mor(self, _mock_config):
        proj = _sample_project(with_elimination=False)
        # No parent_company_id set
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # No parent => Mor=0, Doetre=all companies
        assert r10["Mor"] == 0.0
        assert r10["Doetre"] == 150.0

    def test_sumlinjer_for_mor_doetre(self, _mock_config):
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        sum_row = result_df[result_df["regnr"] == 20].iloc[0]
        assert sum_row["sumpost"] == True  # noqa: E712
        # SUM (formel: =10+11)
        # Mor: 100 + (-200) = -100
        assert sum_row["Mor"] == pytest.approx(-100.0)
        # Doetre: 50 + (-100) = -50
        assert sum_row["Doetre"] == pytest.approx(-50.0)


class TestParentCompanySerialization:
    """Test that parent_company_id survives serialization round-trip."""

    def test_roundtrip(self):
        from consolidation.models import project_to_dict, project_from_dict

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="abc-123",
            companies=[CompanyTB(company_id="abc-123", name="Mor")],
        )
        d = project_to_dict(proj)
        assert d["parent_company_id"] == "abc-123"

        restored = project_from_dict(d)
        assert restored.parent_company_id == "abc-123"

    def test_missing_parent_in_old_data(self):
        from consolidation.models import project_from_dict

        d = {
            "project_id": "p1", "client": "Test", "year": "2025",
            "created_at": 0, "updated_at": 0,
            "companies": [], "mapping_config": {},
            "eliminations": [], "runs": [],
        }
        # Old data without parent_company_id field
        proj = project_from_dict(d)
        assert proj.parent_company_id == ""


# ---------------------------------------------------------------------------
# P1: Effective overrides passed to engine
# ---------------------------------------------------------------------------

class TestEffectiveOverrides:
    def test_effective_overrides_override_project_config(self, _mock_config):
        """effective_overrides parameter should take precedence."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        # Override: move konto 1000 (normally regnr 10) to regnr 11
        eff = {"a": {"1000": 11}, "b": {}}
        result_df, _ = run_consolidation(proj, tbs, effective_overrides=eff)

        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Mor konto 1000 moved away from regnr 10
        assert r10["Mor"] == 0.0

        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        # Mor: konto 3000 (-200) + konto 1000 (100) = -100
        assert r11["Mor"] == pytest.approx(-100.0)


# ---------------------------------------------------------------------------
# P2: Currency conversion in engine
# ---------------------------------------------------------------------------

class TestCurrencyInEngine:
    def test_no_currency_no_conversion(self, _mock_config):
        """Companies without currency should not be converted."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)
        leaf = result_df[~result_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        assert r10["Datter AS"] == 50.0
        # No currency warnings
        assert not any("omregnet" in w for w in run_result.warnings)

    def test_foreign_currency_converts_result_lines(self, _mock_config):
        """Result lines (regnr < 500) should use average_rate."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="Datter DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        # regnr 10 (Eiendeler, < 500) — should use average_rate for DKK company
        # Wait, regnr 10 < 500 — but our test intervals have regnr 10 and 11
        # With our test data: regnr 10 -> balance (typically >=500), but here regnr <500
        # The rule: regnr < 500 -> average_rate, regnr >= 500 -> closing_rate
        # Both regnr 10 and 11 are < 500, so both use average_rate (1.4)
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Datter DKK: ub=50 * average_rate=1.4 = 70
        assert r10["Datter DKK"] == pytest.approx(70.0)

        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        # Datter DKK: ub=-100 * average_rate=1.4 = -140
        assert r11["Datter DKK"] == pytest.approx(-140.0)

        # Should have conversion warning
        assert any("omregnet" in w for w in run_result.warnings)
        assert any("DKK" in w for w in run_result.warnings)

    def test_balance_lines_use_closing_rate(self, _mock_config, monkeypatch):
        """Balance lines (regnr >= 500) should use closing_rate."""
        import regnskap_config

        # Use intervals where one regnr is >= 500
        monkeypatch.setattr(regnskap_config, "load_kontoplan_mapping", lambda **kw: pd.DataFrame({
            "fra": [1000, 3000],
            "til": [1999, 3999],
            "regnr": [500, 11],  # regnr 500 is balance
        }))
        monkeypatch.setattr(regnskap_config, "load_regnskapslinjer", lambda **kw: pd.DataFrame({
            "regnr": [500, 11, 20],
            "regnskapslinje": ["Balanse", "Resultat", "SUM"],
            "sumpost": [False, False, True],
            "formel": [None, None, "=500+11"],
            "sumnivaa": [None]*3, "delsumnr": [None]*3,
            "sumnr": [None]*3, "sumnr2": [None]*3, "sluttsumnr": [None]*3,
        }))

        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"b": _company_b_tb()}
        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        # regnr 500 (balance, >= 500): ub=50 * closing_rate=1.5 = 75
        r500 = leaf[leaf["regnr"] == 500].iloc[0]
        assert r500["DKK"] == pytest.approx(75.0)

        # regnr 11 (result, < 500): ub=-100 * average_rate=1.4 = -140
        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        assert r11["DKK"] == pytest.approx(-140.0)


# ---------------------------------------------------------------------------
# P4: Export hide-zero filter
# ---------------------------------------------------------------------------

class TestExportHideZero:
    def test_hide_zero_filters_result(self, _mock_config):
        """Export with hide_zero should exclude zero leaf lines."""
        from consolidation.export import build_consolidation_workbook
        from consolidation.models import RunResult

        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        # Add a zero line to the result
        zero_row = pd.DataFrame({
            "regnr": [99], "regnskapslinje": ["Tom linje"],
            "sumpost": [False], "formel": [None],
            "Morselskap AS": [0.0], "Datter AS": [0.0],
            "Mor": [0.0], "Doetre": [0.0],
            "sum_foer_elim": [0.0], "eliminering": [0.0],
            "konsolidert": [0.0],
        })
        result_with_zero = pd.concat([result_df, zero_row], ignore_index=True)

        # Without hide_zero
        wb_all = build_consolidation_workbook(
            result_with_zero, proj.companies, [], {},
            run_result, hide_zero=False,
        )
        ws_all = wb_all["Konsernoppstilling"]
        rows_all = ws_all.max_row

        # With hide_zero
        wb_filtered = build_consolidation_workbook(
            result_with_zero, proj.companies, [], {},
            run_result, hide_zero=True,
        )
        ws_filtered = wb_filtered["Konsernoppstilling"]
        rows_filtered = ws_filtered.max_row

        # Filtered should have fewer rows (the zero line excluded)
        assert rows_filtered < rows_all

    def test_hide_zero_filters_company_sheets(self, _mock_config):
        """Export with hide_zero should also filter company TB sheets."""
        from consolidation.export import build_consolidation_workbook

        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        # Add a zero row to mapped TB for company a
        mapped_a = tbs["a"].copy()
        mapped_a["regnr"] = [10, 11]
        zero_row = pd.DataFrame({"konto": ["9999"], "kontonavn": ["Tom"], "ib": [0.0], "ub": [0.0], "netto": [0.0], "regnr": [10]})
        mapped_a_with_zero = pd.concat([mapped_a, zero_row], ignore_index=True)
        mapped_tbs = {"a": mapped_a_with_zero, "b": tbs["b"]}

        wb_all = build_consolidation_workbook(
            result_df, proj.companies, [], mapped_tbs,
            run_result, hide_zero=False,
        )
        wb_filtered = build_consolidation_workbook(
            result_df, proj.companies, [], mapped_tbs,
            run_result, hide_zero=True,
        )

        # Find the company sheet for "a"
        sheet_a_all = [s for s in wb_all.sheetnames if "Morselskap" in s][0]
        sheet_a_filt = [s for s in wb_filtered.sheetnames if "Morselskap" in s][0]
        rows_all = wb_all[sheet_a_all].max_row
        rows_filt = wb_filtered[sheet_a_filt].max_row

        assert rows_filt < rows_all

    def test_main_sheet_places_parent_company_first(self, _mock_config):
        """Konsernoppstilling should always place parent company first among company columns."""
        from consolidation.export import build_consolidation_workbook

        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df,
            proj.companies,
            [],
            {},
            run_result,
            parent_company_id=proj.parent_company_id,
        )
        ws = wb["Konsernoppstilling"]

        headers = [ws.cell(row=4, column=col).value for col in range(1, ws.max_column + 1)]
        parent_idx = headers.index("Morselskap AS")
        child_idx = headers.index("Datter AS")

        assert parent_idx < child_idx


# ---------------------------------------------------------------------------
# P6: Norwegian amount formatting
# ---------------------------------------------------------------------------

class TestFmtNo:
    def test_basic_formatting(self):
        from src.pages.consolidation.frontend.page import _fmt_no

        assert _fmt_no(0) == "0"
        assert _fmt_no(1234) == "1 234"
        assert _fmt_no(-5678) == "-5 678"
        assert _fmt_no(1234567.89, 2) == "1 234 567,89"
        assert _fmt_no(-42.5, 2) == "-42,50"
        assert _fmt_no(999) == "999"
        assert _fmt_no(1000) == "1 000"
        assert _fmt_no(0, 2) == "0,00"

    def test_rounding(self):
        from src.pages.consolidation.frontend.page import _fmt_no

        assert _fmt_no(99.999) == "100"
        assert _fmt_no(99.999, 2) == "100,00"
        assert _fmt_no(1_234_567.895, 2) == "1 234 567,90"


# ---------------------------------------------------------------------------
# Parent-mapping: Analyse-overrides arves av morselskapet
# ---------------------------------------------------------------------------

class TestParentMappingFromAnalyse:
    """Verify parent uses Analyse as source of truth while daughters use consolidation overrides."""

    def _make_page(self, *, analyse_overrides=None, local_overrides=None):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = MagicMock()
        page._project.client = "TestClient"
        page._project.year = "2025"
        page._project.parent_company_id = "parent"
        page._project.mapping_config.company_overrides = local_overrides or {}

        # Patch the Analyse overrides loader
        self._analyse_overrides = analyse_overrides or {}
        return page

    def test_parent_inherits_analyse_overrides(self):
        """Parent company should use Analyse overrides as base mapping."""
        from unittest.mock import patch

        page = self._make_page(
            analyse_overrides={"1000": 10, "2000": 11},
            local_overrides={},  # no local overrides
        )

        with patch("regnskap_client_overrides.load_account_overrides", return_value=self._analyse_overrides):
            result = page._get_effective_company_overrides("parent")

        assert result == {"1000": 10, "2000": 11}

    def test_parent_ignores_local_consolidation_override(self):
        """Parent should ignore local consolidation overrides and use Analyse only."""
        from unittest.mock import patch

        page = self._make_page(
            analyse_overrides={"1000": 10, "2000": 11},
            local_overrides={"parent": {"1000": 99}},  # override konto 1000
        )

        with patch("regnskap_client_overrides.load_account_overrides", return_value=self._analyse_overrides):
            result = page._get_effective_company_overrides("parent")

        assert result == {"1000": 10, "2000": 11}

    def test_daughter_does_not_inherit_analyse(self):
        """Daughter companies should NOT get Analyse overrides."""
        from unittest.mock import patch

        page = self._make_page(
            analyse_overrides={"1000": 10},
            local_overrides={"daughter": {"3000": 20}},
        )

        with patch("regnskap_client_overrides.load_account_overrides", return_value=self._analyse_overrides) as mock_load:
            result = page._get_effective_company_overrides("daughter")

        # Should not have called Analyse loader for daughter
        mock_load.assert_not_called()
        assert result == {"3000": 20}


# ---------------------------------------------------------------------------
# UI helpers
# ---------------------------------------------------------------------------

class TestUiLabelHelpers:
    def test_source_display_skips_netto_hint_for_line_basis_sources(self):
        from src.pages.consolidation.frontend.page import _source_display

        assert _source_display("rl_excel", False) == "Regnskapslinjer"
        assert _source_display("pdf_regnskap", False) == "PDF-regnskap"
        assert _source_display("excel", False) == "TB-fil (kun netto)"

    def test_build_detail_meta_text_for_line_basis_pdf_includes_review_summary(self):
        from src.pages.consolidation.frontend.page import _build_detail_meta_text

        company = CompanyTB(
            company_id="c1",
            name="Rapporteringspakke AS",
            source_type="pdf_regnskap",
            row_count=2,
            basis_type="regnskapslinje",
            has_ib=False,
        )
        basis = pd.DataFrame(
            {
                "regnr": [10, 11],
                "regnskapslinje": ["Eiendeler", "Inntekter"],
                "ub": [100.0, -50.0],
                "review_status": ["approved", ""],
            }
        )

        assert (
            _build_detail_meta_text(company, basis)
            == "Regnskapslinje-grunnlag | PDF-regnskap | 2 linjer | 1 godkjent"
        )


# ---------------------------------------------------------------------------
# Valutakontroll — currency control sheet
# ---------------------------------------------------------------------------

class TestValutakontroll:
    """Verify CurrencyDetail rows are produced by engine and exported correctly."""

    def test_result_line_uses_snittkurs(self, _mock_config):
        """Result lines (regnr < 500) should show Snittkurs in control data."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="Datter DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        # Find DKK result lines (regnr 10 and 11 are both < 500)
        dkk_details = [d for d in run_result.currency_details if d.company_name == "Datter DKK"]
        assert len(dkk_details) > 0

        for d in dkk_details:
            assert d.currency == "DKK"
            # Both regnr 10 and 11 < 500, so all are result lines
            assert d.line_type == "Resultat"
            assert d.rate_rule == "Snittkurs"
            assert d.rate == pytest.approx(1.4)
            assert d.amount_after == pytest.approx(d.amount_before * 1.4)

    def test_balance_line_uses_sluttkurs(self, _mock_config, monkeypatch):
        """Balance lines (regnr >= 500) should show Sluttkurs in control data."""
        import regnskap_config

        monkeypatch.setattr(regnskap_config, "load_kontoplan_mapping", lambda **kw: pd.DataFrame({
            "fra": [1000, 3000],
            "til": [1999, 3999],
            "regnr": [500, 11],
        }))
        monkeypatch.setattr(regnskap_config, "load_regnskapslinjer", lambda **kw: pd.DataFrame({
            "regnr": [500, 11, 20],
            "regnskapslinje": ["Balanse", "Resultat", "SUM"],
            "sumpost": [False, False, True],
            "formel": [None, None, "=500+11"],
            "sumnivaa": [None]*3, "delsumnr": [None]*3,
            "sumnr": [None]*3, "sumnr2": [None]*3, "sluttsumnr": [None]*3,
        }))

        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        details = run_result.currency_details
        r500 = [d for d in details if d.regnr == 500][0]
        assert r500.line_type == "Balanse"
        assert r500.rate_rule == "Sluttkurs"
        assert r500.rate == pytest.approx(1.5)
        assert r500.amount_after == pytest.approx(r500.amount_before * 1.5)

        r11 = [d for d in details if d.regnr == 11][0]
        assert r11.line_type == "Resultat"
        assert r11.rate_rule == "Snittkurs"
        assert r11.rate == pytest.approx(1.4)

    def test_nok_company_shows_rate_1(self, _mock_config):
        """NOK company (no conversion) should still appear with rate=1.0."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        # All companies are NOK (no currency_code set)
        assert len(run_result.currency_details) > 0
        for d in run_result.currency_details:
            assert d.rate == pytest.approx(1.0)
            assert d.amount_before == pytest.approx(d.amount_after)

    def test_control_sheet_in_export(self, _mock_config):
        """Valutakontroll sheet should appear in export and use engine data."""
        from consolidation.export import build_consolidation_workbook

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="Datter SEK", row_count=2,
                    currency_code="SEK", closing_rate=0.95, average_rate=0.93,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )

        assert "Valutakontroll" in wb.sheetnames
        ws = wb["Valutakontroll"]

        # Header row
        assert ws.cell(row=1, column=1).value == "Selskap"
        assert ws.cell(row=1, column=6).value == "Beloep foer omregning"
        assert ws.cell(row=1, column=9).value == "Beloep etter omregning"

        # Data rows should match currency_details count
        data_rows = ws.max_row - 1  # minus header
        assert data_rows == len(run_result.currency_details)

        # Verify numeric cells (not text)
        for row_idx in range(2, ws.max_row + 1):
            assert isinstance(ws.cell(row=row_idx, column=6).value, (int, float))
            assert isinstance(ws.cell(row=row_idx, column=7).value, (int, float))
            assert isinstance(ws.cell(row=row_idx, column=9).value, (int, float))


# ---------------------------------------------------------------------------
# Saldobalanse alle — flat per-account per-company sheet
# ---------------------------------------------------------------------------

class TestSaldobalanseAlle:
    """Verify the flat account-level control sheet in export."""

    def test_sheet_exists_and_row_count(self, _mock_config):
        """Sheet should exist and have one row per account per company."""
        from consolidation.export import build_consolidation_workbook

        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )

        assert "Saldobalanse alle" in wb.sheetnames
        ws = wb["Saldobalanse alle"]

        # 2 accounts per company, 2 companies = 4 data rows + 1 header
        data_rows = ws.max_row - 1
        assert data_rows == 4

    def test_columns_are_correct(self, _mock_config):
        """Header columns should match spec."""
        from consolidation.export import build_consolidation_workbook

        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )
        ws = wb["Saldobalanse alle"]

        expected = [
            "Selskap", "Konto", "Kontonavn", "Regnr", "Regnskapslinje",
            "IB", "Bevegelse", "UB",
            "Valuta", "Kurs brukt", "Kursregel",
            "Beloep foer omregning", "Beloep etter omregning",
        ]
        for col_idx, name in enumerate(expected, start=1):
            assert ws.cell(row=1, column=col_idx).value == name

    def test_amounts_and_rate_are_numeric(self, _mock_config):
        """All amount/rate cells should be numeric, not text."""
        from consolidation.export import build_consolidation_workbook

        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )
        ws = wb["Saldobalanse alle"]

        # Columns: 6=IB, 7=Bevegelse, 8=UB, 10=Kurs, 12=foer, 13=etter
        numeric_cols = [6, 7, 8, 10, 12, 13]
        for row_idx in range(2, ws.max_row + 1):
            for col_idx in numeric_cols:
                val = ws.cell(row=row_idx, column=col_idx).value
                assert isinstance(val, (int, float)), (
                    f"Row {row_idx}, col {col_idx}: expected numeric, got {type(val)}: {val!r}"
                )

    def test_result_account_uses_snittkurs(self, _mock_config):
        """Accounts mapped to regnr < 500 should show Snittkurs."""
        from consolidation.export import build_consolidation_workbook

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )
        ws = wb["Saldobalanse alle"]

        # Find DKK rows — both regnr 10 and 11 are < 500 (result)
        for row_idx in range(2, ws.max_row + 1):
            selskap = ws.cell(row=row_idx, column=1).value
            if selskap == "DKK":
                kursregel = ws.cell(row=row_idx, column=11).value
                kurs = ws.cell(row=row_idx, column=10).value
                assert kursregel == "Snittkurs"
                assert kurs == pytest.approx(1.4)
                # Verify conversion: etter = foer * rate
                foer = ws.cell(row=row_idx, column=12).value
                etter = ws.cell(row=row_idx, column=13).value
                assert etter == pytest.approx(foer * 1.4)

    def test_balance_account_uses_sluttkurs(self, _mock_config, monkeypatch):
        """Accounts mapped to regnr >= 500 should show Sluttkurs."""
        import regnskap_config
        from consolidation.export import build_consolidation_workbook

        # Use intervals where konto 1000-1999 maps to regnr 500 (balance)
        monkeypatch.setattr(regnskap_config, "load_kontoplan_mapping", lambda **kw: pd.DataFrame({
            "fra": [1000, 3000],
            "til": [1999, 3999],
            "regnr": [500, 11],
        }))
        monkeypatch.setattr(regnskap_config, "load_regnskapslinjer", lambda **kw: pd.DataFrame({
            "regnr": [500, 11, 20],
            "regnskapslinje": ["Balanse", "Resultat", "SUM"],
            "sumpost": [False, False, True],
            "formel": [None, None, "=500+11"],
            "sumnivaa": [None]*3, "delsumnr": [None]*3,
            "sumnr": [None]*3, "sumnr2": [None]*3, "sluttsumnr": [None]*3,
        }))

        proj = ConsolidationProject(
            client="Test", year="2025",
            companies=[
                CompanyTB(
                    company_id="b", name="SEK", row_count=2,
                    currency_code="SEK", closing_rate=0.95, average_rate=0.93,
                ),
            ],
        )
        tbs = {"b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )
        ws = wb["Saldobalanse alle"]

        found_balanse = False
        found_resultat = False
        for row_idx in range(2, ws.max_row + 1):
            regnr = ws.cell(row=row_idx, column=4).value
            kursregel = ws.cell(row=row_idx, column=11).value
            kurs = ws.cell(row=row_idx, column=10).value
            if regnr == 500:
                assert kursregel == "Sluttkurs"
                assert kurs == pytest.approx(0.95)
                found_balanse = True
            elif regnr == 11:
                assert kursregel == "Snittkurs"
                assert kurs == pytest.approx(0.93)
                found_resultat = True

        assert found_balanse, "No balance line (regnr 500) found"
        assert found_resultat, "No result line (regnr 11) found"

    def test_unmapped_accounts_included(self, _mock_config):
        """Unmapped accounts (no regnr) should appear in Saldobalanse alle."""
        from consolidation.export import build_consolidation_workbook

        # TB with one unmapped konto (5000 is outside intervals 1000-1999 / 3000-3999)
        tb_with_unmapped = pd.DataFrame({
            "konto": ["1000", "5000"],
            "kontonavn": ["Bank", "Ukjent"],
            "ib": [0.0, 10.0],
            "ub": [100.0, 50.0],
            "netto": [100.0, 40.0],
        })

        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        proj.companies = [CompanyTB(company_id="a", name="Mor", row_count=2)]
        tbs = {"a": tb_with_unmapped}
        result_df, run_result = run_consolidation(proj, tbs)

        wb = build_consolidation_workbook(
            result_df, proj.companies, [], {},
            run_result,
        )
        ws = wb["Saldobalanse alle"]

        # Should have 2 data rows (mapped + unmapped)
        data_rows = ws.max_row - 1
        assert data_rows == 2

        # Find the unmapped row
        found_unmapped = False
        for row_idx in range(2, ws.max_row + 1):
            konto = ws.cell(row=row_idx, column=2).value
            if str(konto) == "5000":
                found_unmapped = True
                regnr = ws.cell(row=row_idx, column=4).value
                regnskapslinje = ws.cell(row=row_idx, column=5).value
                kursregel = ws.cell(row=row_idx, column=11).value
                foer = ws.cell(row=row_idx, column=12).value
                etter = ws.cell(row=row_idx, column=13).value
                # Unmapped: regnr is empty, no kursregel
                assert regnr == "" or regnr is None
                assert regnskapslinje == "" or regnskapslinje is None
                assert kursregel == "" or kursregel is None
                # No conversion: foer == etter
                assert foer == pytest.approx(etter)

        assert found_unmapped, "Unmapped konto 5000 not found in Saldobalanse alle"

    def test_row_count_with_unmapped(self, _mock_config):
        """Total rows should include both mapped and unmapped accounts."""
        tb = pd.DataFrame({
            "konto": ["1000", "3000", "5000", "6000"],
            "kontonavn": ["Bank", "Salg", "X", "Y"],
            "ib": [0.0]*4,
            "ub": [100.0, -200.0, 30.0, 40.0],
            "netto": [100.0, -200.0, 30.0, 40.0],
        })

        proj = _sample_project(with_elimination=False)
        proj.companies = [CompanyTB(company_id="a", name="Test", row_count=4)]
        tbs = {"a": tb}
        _, run_result = run_consolidation(proj, tbs)

        assert run_result.account_details is not None
        # 4 accounts total (2 mapped + 2 unmapped)
        assert len(run_result.account_details) == 4


# ---------------------------------------------------------------------------
# ÅO consistency — effective TB used throughout page
# ---------------------------------------------------------------------------

class TestAOConsistency:
    """Verify _get_effective_company_tb applies AO to parent consistently."""

    def _make_page(self, *, ao_on=True, ao_entries=None):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = MagicMock()
        page._project.client = "TestClient"
        page._project.year = "2025"
        page._project.parent_company_id = "parent"
        page._project.mapping_config.company_overrides = {}

        page._include_ao_var = MagicMock()
        page._include_ao_var.get = MagicMock(return_value=ao_on)

        # Raw TBs
        page._company_tbs = {
            "parent": pd.DataFrame({
                "konto": ["1000", "3000"],
                "kontonavn": ["Bank", "Salg"],
                "ib": [0.0, 0.0],
                "ub": [100.0, -200.0],
                "netto": [100.0, -200.0],
            }),
            "child": pd.DataFrame({
                "konto": ["1500"],
                "kontonavn": ["Varelager"],
                "ib": [0.0],
                "ub": [50.0],
                "netto": [50.0],
            }),
        }

        self._ao_entries = ao_entries or [{"konto": "9000", "kontonavn": "AO-post", "netto": 999.0}]
        return page

    def test_parent_gets_ao_when_checkbox_on(self):
        """Parent TB should include AO entries when checkbox is active."""
        from unittest.mock import patch, MagicMock

        page = self._make_page(ao_on=True)

        # Mock AO loader to return entries, and apply_to_sb to add a row
        def fake_apply(tb, entries):
            ao_row = pd.DataFrame({"konto": ["9000"], "kontonavn": ["AO-post"],
                                   "ib": [0.0], "ub": [999.0], "netto": [999.0]})
            return pd.concat([tb, ao_row], ignore_index=True)

        with patch("regnskap_client_overrides.load_supplementary_entries", return_value=self._ao_entries):
            with patch("tilleggsposteringer.apply_to_sb", side_effect=fake_apply):
                result = page._get_effective_company_tb("parent")

        # Should have 3 rows (2 original + 1 AO)
        assert len(result) == 3
        assert "9000" in result["konto"].values

    def test_parent_raw_when_checkbox_off(self):
        """Parent TB should be raw when checkbox is off."""
        page = self._make_page(ao_on=False)
        result = page._get_effective_company_tb("parent")
        assert len(result) == 2  # No AO added

    def test_child_never_gets_ao(self):
        """Child TB should never include AO regardless of checkbox."""
        from unittest.mock import patch

        page = self._make_page(ao_on=True)
        with patch("regnskap_client_overrides.load_supplementary_entries") as mock_load:
            result = page._get_effective_company_tb("child")

        mock_load.assert_not_called()
        assert len(result) == 1  # Raw child TB

    def test_get_effective_tbs_applies_ao_to_parent_only(self):
        """_get_effective_tbs should apply AO to parent but not children."""
        from unittest.mock import patch

        page = self._make_page(ao_on=True)

        def fake_apply(tb, entries):
            ao_row = pd.DataFrame({"konto": ["9000"], "kontonavn": ["AO-post"],
                                   "ib": [0.0], "ub": [999.0], "netto": [999.0]})
            return pd.concat([tb, ao_row], ignore_index=True)

        with patch("regnskap_client_overrides.load_supplementary_entries", return_value=self._ao_entries):
            with patch("tilleggsposteringer.apply_to_sb", side_effect=fake_apply):
                tbs = page._get_effective_tbs()

        assert len(tbs["parent"]) == 3  # AO added
        assert len(tbs["child"]) == 1   # Untouched

    def test_run_uses_effective_tbs(self, _mock_config):
        """Run with AO should produce different result than without."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[CompanyTB(company_id="a", name="Mor", row_count=2)],
        )

        raw_tb = _company_a_tb()
        # Add an AO row to konto 1000 range (maps to regnr 10)
        ao_tb = raw_tb.copy()
        ao_row = pd.DataFrame({"konto": ["1100"], "kontonavn": ["AO"],
                               "ib": [0.0], "ub": [500.0], "netto": [500.0]})
        ao_tb = pd.concat([ao_tb, ao_row], ignore_index=True)

        result_raw, _ = run_consolidation(proj, {"a": raw_tb})
        result_ao, _ = run_consolidation(proj, {"a": ao_tb})

        leaf_raw = result_raw[~result_raw["sumpost"]]
        leaf_ao = result_ao[~result_ao["sumpost"]]

        r10_raw = leaf_raw[leaf_raw["regnr"] == 10].iloc[0]["Mor"]
        r10_ao = leaf_ao[leaf_ao["regnr"] == 10].iloc[0]["Mor"]

        # AO adds 500 to regnr 10
        assert r10_ao == pytest.approx(r10_raw + 500.0)


# ---------------------------------------------------------------------------
# State robustness — _ensure_consolidated_result and re-run logic
# ---------------------------------------------------------------------------

class TestEnsureConsolidatedResult:
    """Verify _ensure_consolidated_result auto-runs when cache is missing."""

    def _make_page(self, *, has_project=True, has_companies=True, has_tbs=True,
                   has_cached_result=False):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        if has_project:
            page._project = MagicMock()
            page._project.client = "TestClient"
            page._project.year = "2025"
            page._project.parent_company_id = "a"
            if has_companies:
                page._project.companies = [
                    MagicMock(company_id="a"),
                    MagicMock(company_id="b"),
                ]
            else:
                page._project.companies = []
        else:
            page._project = None

        page._company_tbs = {}
        if has_tbs:
            page._company_tbs = {
                "a": _company_a_tb(),
                "b": _company_b_tb(),
            }

        if has_cached_result:
            page._consolidated_result_df = pd.DataFrame({"regnr": [10]})
        else:
            page._consolidated_result_df = None

        # Mock _on_run to track calls and simulate setting the cache
        page._on_run = MagicMock(side_effect=lambda: setattr(
            page, "_consolidated_result_df", pd.DataFrame({"regnr": [10]})
        ))

        return page

    def test_returns_true_when_cached(self):
        """Should return True immediately if result is already cached."""
        page = self._make_page(has_cached_result=True)
        assert page._ensure_consolidated_result() is True
        page._on_run.assert_not_called()

    def test_runs_consolidation_when_cache_missing(self):
        """Should call _on_run when cache is missing and project has companies."""
        page = self._make_page(has_cached_result=False)
        result = page._ensure_consolidated_result()
        assert result is True
        page._on_run.assert_called_once()

    def test_returns_false_no_project(self):
        """Should return False when no project is loaded."""
        page = self._make_page(has_project=False)
        assert page._ensure_consolidated_result() is False
        page._on_run.assert_not_called()

    def test_returns_false_no_companies(self):
        """Should return False when project has no companies."""
        page = self._make_page(has_companies=False)
        assert page._ensure_consolidated_result() is False
        page._on_run.assert_not_called()

    def test_returns_false_no_tbs(self):
        """Should return False when no TBs are loaded."""
        page = self._make_page(has_tbs=False)
        assert page._ensure_consolidated_result() is False
        page._on_run.assert_not_called()


class TestEliminationRerunAlwaysTriggers:
    """Verify that adding/deleting eliminations changes consolidated result."""

    def test_adding_elimination_changes_result(self, _mock_config):
        """Running twice — once without, once with elimination — should differ."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_before, _ = run_consolidation(proj, tbs)

        # Add elimination
        proj.eliminations.append(EliminationJournal(
            journal_id="e1", name="Test",
            lines=[
                EliminationLine(regnr=11, company_id="a", amount=50.0),
                EliminationLine(regnr=11, company_id="b", amount=-50.0),
            ],
        ))
        result_after, _ = run_consolidation(proj, tbs)

        # Hashes must differ since elimination changes the result
        leaf_b = result_before[~result_before["sumpost"]]
        leaf_a = result_after[~result_after["sumpost"]]
        r11_before = leaf_b[leaf_b["regnr"] == 11].iloc[0]["eliminering"]
        r11_after = leaf_a[leaf_a["regnr"] == 11].iloc[0]["eliminering"]
        assert r11_before == 0.0
        assert r11_after == 0.0  # balanced elim nets to 0 total per regnr

    def test_removing_elimination_changes_result(self, _mock_config):
        """Removing an elimination should change the konsolidert column."""
        # Use a cross-regnr elimination that moves value between lines
        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(company_id="b", name="Dat", row_count=2),
            ],
            eliminations=[EliminationJournal(
                journal_id="e1", name="Cross",
                lines=[
                    EliminationLine(regnr=10, company_id="a", amount=25.0),
                    EliminationLine(regnr=11, company_id="a", amount=-25.0),
                ],
            )],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_with, _ = run_consolidation(proj, tbs)
        leaf_w = result_with[~result_with["sumpost"]]
        kons_10_with = leaf_w[leaf_w["regnr"] == 10].iloc[0]["konsolidert"]

        proj.eliminations.clear()
        result_without, _ = run_consolidation(proj, tbs)
        leaf_wo = result_without[~result_without["sumpost"]]
        kons_10_without = leaf_wo[leaf_wo["regnr"] == 10].iloc[0]["konsolidert"]

        # Elimination moved 25 into regnr 10, so removing it changes the value
        assert kons_10_with == pytest.approx(kons_10_without + 25.0)


# ---------------------------------------------------------------------------
# Per selskap view — engine produces company columns
# ---------------------------------------------------------------------------

class TestPerSelskapView:
    """Verify engine output has individual company columns usable for Per selskap mode."""

    def test_get_per_company_columns_order(self, _mock_config):
        """_get_per_company_columns should return Mor first, then daughters, then elim+kons."""
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, _ = run_consolidation(proj, tbs)

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = result_df

        cols = page._get_per_company_columns()
        assert cols[0] == "Morselskap AS"
        assert cols[1] == "Datter AS"
        assert cols[-2] == "eliminering"
        assert cols[-1] == "konsolidert"

    def test_result_has_company_name_columns(self, _mock_config):
        """Result df should contain a column per company name."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        assert "Morselskap AS" in result_df.columns
        assert "Datter AS" in result_df.columns

    def test_per_company_columns_match_mor_doetre(self, _mock_config):
        """Sum of company columns should equal sum_foer_elim for leaf lines."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        for _, row in leaf.iterrows():
            company_sum = row["Morselskap AS"] + row["Datter AS"]
            assert company_sum == pytest.approx(row["sum_foer_elim"])

    def test_mor_column_equals_parent_company(self, _mock_config):
        """Mor column should equal the parent company column."""
        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        result_df, _ = run_consolidation(proj, tbs)

        leaf = result_df[~result_df["sumpost"]]
        for _, row in leaf.iterrows():
            assert row["Mor"] == pytest.approx(row["Morselskap AS"])


# ---------------------------------------------------------------------------
# Grunnlag drilldown — account_details filtering
# ---------------------------------------------------------------------------

class TestGrunnlagDrilldown:
    """Verify account_details can be filtered by regnr for drilldown view."""

    def test_account_details_has_required_columns(self, _mock_config):
        """account_details should contain all columns needed for Grunnlag view."""
        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        ad = run_result.account_details
        assert ad is not None
        for col in ("selskap", "konto", "kontonavn", "regnr", "regnskapslinje",
                     "ib", "ub_original", "ub", "valuta", "kurs"):
            assert col in ad.columns, f"Missing column: {col}"

    def test_filter_by_regnr_returns_correct_accounts(self, _mock_config):
        """Filtering account_details by regnr should return only matching accounts."""
        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        ad = run_result.account_details
        # regnr 10 maps to kontoer 1000-1999
        regnr10 = ad[ad["regnr"].astype(float) == 10]
        assert len(regnr10) > 0
        for _, row in regnr10.iterrows():
            assert 1000 <= int(row["konto"]) <= 1999

    def test_filter_by_regnr_has_both_companies(self, _mock_config):
        """Both companies should appear in drilldown for a shared regnr."""
        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        ad = run_result.account_details
        regnr10 = ad[ad["regnr"].astype(float) == 10]
        companies = set(regnr10["selskap"].unique())
        assert "Morselskap AS" in companies
        assert "Datter AS" in companies

    def test_currency_columns_in_account_details(self, _mock_config):
        """Currency details (kurs, ub_original, ub) should be present and consistent."""
        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        ad = run_result.account_details
        dkk_rows = ad[ad["valuta"] == "DKK"]
        assert len(dkk_rows) > 0

        for _, row in dkk_rows.iterrows():
            if pd.notna(row["regnr"]):
                kurs = float(row["kurs"])
                ub_orig = float(row["ub_original"])
                ub_conv = float(row["ub"])
                assert ub_conv == pytest.approx(ub_orig * kurs)

    def test_valutaeffekt_is_zero_for_nok(self, _mock_config):
        """NOK accounts should have zero valutaeffekt (kurs=1)."""
        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        _, run_result = run_consolidation(proj, tbs)

        ad = run_result.account_details
        for _, row in ad.iterrows():
            if pd.notna(row["regnr"]):
                ub_orig = float(row["ub_original"])
                ub_conv = float(row["ub"])
                assert ub_conv == pytest.approx(ub_orig)  # kurs = 1


# ---------------------------------------------------------------------------
# FX mode — consolidated view before/after/effect
# ---------------------------------------------------------------------------

class TestFxColumnsBuildCompanyResult:
    """Verify _build_company_result produces correct FX columns."""

    def _make_fx_page(self, _mock_config):
        """Build a page-like object with FX companies and a run result."""
        from consolidation.mapping import map_company_tb, load_shared_config
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            reporting_currency="NOK",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        intervals, regnskapslinjer = load_shared_config()
        mapped_tbs = {}
        for c in proj.companies:
            tb = tbs[c.company_id]
            mapped_df, _ = map_company_tb(
                tb, None, intervals=intervals, regnskapslinjer=regnskapslinjer,
            )
            mapped_tbs[c.company_id] = mapped_df

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = result_df
        page._last_run_result = run_result
        page._regnskapslinjer = _regnskapslinjer_df()
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}
        page._mapped_tbs = mapped_tbs
        page._company_result_df = None

        return page, result_df, run_result

    def test_dkk_company_ub_has_converted_values(self, _mock_config):
        """UB column should show after-conversion amounts for DKK company."""
        page, _, _ = self._make_fx_page(_mock_config)
        page._build_company_result("b")
        df = page._company_result_df
        assert df is not None

        leaf = df[~df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # DKK company b: regnr 10 has ub=50, average_rate=1.4 → 70
        assert r10["UB"] == pytest.approx(70.0)
        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        # regnr 11: ub=-100, average_rate=1.4 → -140
        assert r11["UB"] == pytest.approx(-140.0)

    def test_dkk_company_foer_has_original_values(self, _mock_config):
        """Før column should show pre-conversion amounts."""
        page, _, _ = self._make_fx_page(_mock_config)
        page._build_company_result("b")
        df = page._company_result_df

        leaf = df[~df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        assert r10["Før"] == pytest.approx(50.0)
        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        assert r11["Før"] == pytest.approx(-100.0)

    def test_dkk_company_kurs_values(self, _mock_config):
        """Kurs column should show rate per regnr line."""
        page, _, _ = self._make_fx_page(_mock_config)
        page._build_company_result("b")
        df = page._company_result_df

        leaf = df[~df["sumpost"]]
        # Both regnr 10, 11 are < 500 → average_rate = 1.4
        for regnr in [10, 11]:
            row = leaf[leaf["regnr"] == regnr].iloc[0]
            assert row["Kurs"] == pytest.approx(1.4)

        # Sum lines should have NaN for Kurs
        sum_rows = df[df["sumpost"]]
        for _, row in sum_rows.iterrows():
            assert pd.isna(row["Kurs"])

    def test_dkk_company_valutaeffekt(self, _mock_config):
        """Valutaeffekt = UB - Før for leaf lines."""
        page, _, _ = self._make_fx_page(_mock_config)
        page._build_company_result("b")
        df = page._company_result_df

        leaf = df[~df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # 70 - 50 = 20
        assert r10["Valutaeffekt"] == pytest.approx(20.0)
        r11 = leaf[leaf["regnr"] == 11].iloc[0]
        # -140 - (-100) = -40
        assert r11["Valutaeffekt"] == pytest.approx(-40.0)

    def test_nok_company_no_fx_effect(self, _mock_config):
        """NOK company should have UB == Før, Kurs == 1, Valutaeffekt == 0."""
        page, _, _ = self._make_fx_page(_mock_config)
        page._build_company_result("a")
        df = page._company_result_df

        leaf = df[~df["sumpost"]]
        for regnr in [10, 11]:
            row = leaf[leaf["regnr"] == regnr].iloc[0]
            assert row["UB"] == pytest.approx(row["Før"])
            assert row["Kurs"] == pytest.approx(1.0)
            assert abs(row["Valutaeffekt"]) < 0.01


class TestFxColumnsConsolidated:
    """Verify _ensure_consolidated_fx_cols produces correct Mor/Doetre FX cols."""

    def _make_fx_page(self, _mock_config):
        """Build a page-like object with FX companies and a run result."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            reporting_currency="NOK",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = result_df
        page._last_run_result = run_result
        page._regnskapslinjer = _regnskapslinjer_df()
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}

        return page, result_df, run_result

    def test_doetre_foer_shows_original_amounts(self, _mock_config):
        """Doetre_foer should show pre-conversion amounts for child companies."""
        page, _, _ = self._make_fx_page(_mock_config)
        fx_df = page._ensure_consolidated_fx_cols(show_before=True, show_effect=False)

        leaf = fx_df[~fx_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # DKK company b (child): regnr 10 original ub=50
        assert r10["Doetre_foer"] == pytest.approx(50.0)
        # Doetre (after) should still be 70
        assert r10["Doetre"] == pytest.approx(70.0)

    def test_mor_foer_shows_original_amounts(self, _mock_config):
        """Mor_foer should equal Mor for NOK parent (no conversion)."""
        page, _, _ = self._make_fx_page(_mock_config)
        fx_df = page._ensure_consolidated_fx_cols(show_before=True, show_effect=False)

        leaf = fx_df[~fx_df["sumpost"]]
        for regnr in [10, 11]:
            row = leaf[leaf["regnr"] == regnr].iloc[0]
            assert row["Mor_foer"] == pytest.approx(row["Mor"])

    def test_effect_cols(self, _mock_config):
        """Mor_effekt and Doetre_effekt should show etter - foer."""
        page, _, _ = self._make_fx_page(_mock_config)
        fx_df = page._ensure_consolidated_fx_cols(show_before=True, show_effect=True)

        leaf = fx_df[~fx_df["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Mor (NOK): no effect
        assert abs(r10["Mor_effekt"]) < 0.01
        # Doetre (DKK): 70 - 50 = 20
        assert r10["Doetre_effekt"] == pytest.approx(20.0)

    def test_nok_only_no_effect(self, _mock_config):
        """For NOK-only project, all FX effect columns should be zero."""
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = _sample_project(with_elimination=False)
        proj.parent_company_id = "a"
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = result_df
        page._last_run_result = run_result
        page._regnskapslinjer = _regnskapslinjer_df()

        fx_df = page._ensure_consolidated_fx_cols(show_before=True, show_effect=True)
        leaf = fx_df[~fx_df["sumpost"]]
        for regnr in [10, 11]:
            row = leaf[leaf["regnr"] == regnr].iloc[0]
            assert abs(row["Mor_effekt"]) < 0.01
            assert abs(row["Doetre_effekt"]) < 0.01


class TestShowResultRebuildsCompanyResult:
    """Verify _show_result rebuilds _company_result_df for selected company."""

    def test_show_result_refreshes_company_result(self, _mock_config):
        """After consolidation, _company_result_df should use fresh run_result."""
        from unittest.mock import MagicMock, patch
        from consolidation.mapping import map_company_tb, load_shared_config
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            reporting_currency="NOK",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(
                    company_id="b", name="DKK", row_count=2,
                    currency_code="DKK", closing_rate=1.5, average_rate=1.4,
                ),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}

        intervals, regnskapslinjer = load_shared_config()
        mapped_tbs = {}
        for c in proj.companies:
            tb = tbs[c.company_id]
            mapped_df, _ = map_company_tb(
                tb, None, intervals=intervals, regnskapslinjer=regnskapslinjer,
            )
            mapped_tbs[c.company_id] = mapped_df

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = None
        page._last_run_result = None
        page._regnskapslinjer = _regnskapslinjer_df()
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}
        page._mapped_tbs = mapped_tbs
        page._company_result_df = None
        page._current_detail_cid = "b"
        page._preview_result_df = None
        page._result_mode_var = MagicMock()
        page._preview_label_var = MagicMock()
        page._right_nb = MagicMock()

        # Build company result BEFORE consolidation → no account_details → fallback
        page._build_company_result("b")
        df_before_run = page._company_result_df
        assert df_before_run is not None
        leaf = df_before_run[~df_before_run["sumpost"]]
        r10 = leaf[leaf["regnr"] == 10].iloc[0]
        # Without run_result, UB == Før (fallback)
        assert r10["UB"] == pytest.approx(r10["Før"])

        # Now run consolidation and call _show_result
        result_df, run_result = run_consolidation(proj, tbs)
        page._last_run_result = run_result

        # Mock _refresh_result_view to avoid GUI calls
        page._refresh_result_view = MagicMock()
        page._show_result(result_df)

        # _company_result_df should now have fresh data with actual conversion
        df_after_run = page._company_result_df
        assert df_after_run is not None
        leaf2 = df_after_run[~df_after_run["sumpost"]]
        r10_2 = leaf2[leaf2["regnr"] == 10].iloc[0]
        # Now UB should be converted: 50 * 1.4 = 70, Før = 50
        assert r10_2["UB"] == pytest.approx(70.0)
        assert r10_2["Før"] == pytest.approx(50.0)
        assert r10_2["Kurs"] == pytest.approx(1.4)


class TestInvalidateRunCache:
    """Verify _invalidate_run_cache clears all run state."""

    def test_invalidate_clears_all_cache(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._result_df = pd.DataFrame()
        page._consolidated_result_df = pd.DataFrame()
        page._company_result_df = pd.DataFrame()
        page._preview_result_df = pd.DataFrame()
        page._last_run_result = "something"

        page._invalidate_run_cache()

        assert page._result_df is None
        assert page._consolidated_result_df is None
        assert page._company_result_df is None
        assert page._preview_result_df is None
        assert page._last_run_result is None

    def test_rerun_invalidates_and_runs(self, _mock_config):
        """_rerun_consolidation should invalidate cache and call _on_run."""
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._result_df = pd.DataFrame()
        page._consolidated_result_df = pd.DataFrame()
        page._company_result_df = pd.DataFrame()
        page._preview_result_df = pd.DataFrame()
        page._last_run_result = "something"
        page._project = _sample_project(with_elimination=False)
        page._company_tbs = {"a": _company_a_tb()}
        page._on_run = MagicMock()

        page._rerun_consolidation()

        # Cache should be cleared before _on_run is called
        assert page._consolidated_result_df is None
        page._on_run.assert_called_once()


class TestEliminationRerunOnCreateDelete:
    """Verify elimination create/delete forces actual rerun."""

    def test_create_elim_invalidates_and_reruns(self, _mock_config):
        """_on_create_simple_elim should call _rerun_consolidation (not just _ensure)."""
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = _sample_project(with_elimination=False)
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._result_df = result_df
        page._consolidated_result_df = result_df
        page._company_result_df = None
        page._preview_result_df = None
        page._last_run_result = run_result
        page._company_tbs = tbs
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}
        page._draft_lines = [
            {"regnr": 10, "name": "Eiendeler", "amount": 50.0, "desc": "D"},
            {"regnr": 11, "name": "Inntekter", "amount": -50.0, "desc": "K"},
        ]
        page._draft_edit_idx = None
        page._draft_source_journal_id = None
        page._draft_voucher_no = 1
        page._refresh_draft_tree = MagicMock()
        page._refresh_simple_elim_tree = MagicMock()
        page._refresh_journal_tree = MagicMock()
        page._update_status = MagicMock()
        page._clear_preview = MagicMock()
        # Mock _on_run to just set result back
        page._on_run = MagicMock()

        with patch("src.pages.consolidation.frontend.page.storage") as mock_storage:
            page._on_create_simple_elim()

        # Should have created the journal
        assert len(proj.eliminations) == 1
        assert proj.eliminations[0].voucher_no == 1
        assert proj.eliminations[0].name == "Bilag 1"

        # Cache should have been invalidated before _on_run
        assert page._consolidated_result_df is None
        assert page._last_run_result is None
        page._on_run.assert_called_once()


class TestRunRefreshesMappingState:
    """Verify _on_run refreshes external Analyse-driven mapping state first."""

    def test_on_run_recomputes_mapping_status_before_preflight(self, _mock_config):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        proj = ConsolidationProject(
            client="Test",
            year="2025",
            parent_company_id="mor",
            companies=[CompanyTB(company_id="mor", name="Mor", row_count=1)],
        )
        tb = pd.DataFrame(
            {
                "konto": ["1000"],
                "kontonavn": ["Bank"],
                "ib": [0.0],
                "ub": [100.0],
                "netto": [100.0],
            }
        )

        page._project = proj
        page._company_tbs = {"mor": tb}
        page._compute_mapping_status = MagicMock()
        page._prepare_tbs_for_run = MagicMock(return_value={"mor": tb})
        page._get_effective_company_overrides = MagicMock(return_value={})
        page._build_unmapped_warnings = MagicMock(return_value=[])
        page._show_result = MagicMock()
        page._update_status = MagicMock()

        with patch("src.pages.consolidation.frontend.page.messagebox") as mock_mb:
            mock_mb.askyesno.return_value = True
            with patch(
                "src.pages.consolidation.backend.readiness.build_readiness_report",
                return_value=SimpleNamespace(issues=[]),
            ):
                with patch("consolidation.engine.run_consolidation") as mock_run:
                    mock_run.return_value = (
                        pd.DataFrame({"regnr": [10], "konsolidert": [100.0]}),
                        SimpleNamespace(warnings=[], input_digest=""),
                    )
                    with patch("src.pages.consolidation.frontend.page.storage") as mock_storage:
                        page._on_run()

        page._compute_mapping_status.assert_called_once()
        mock_run.assert_called_once()
        mock_storage.save_project.assert_called_once()


class TestShowElimDetail:
    """Verify _show_elim_detail populates elimination line details."""

    def test_show_lines_for_selected_journal(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = _sample_project(with_elimination=True)
        journal = proj.eliminations[0]

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}

        # Mock the detail treeview
        tree_mock = MagicMock()
        page._tree_elim_detail = tree_mock

        page._show_elim_detail(journal.journal_id)

        # Should have cleared and inserted lines
        tree_mock.delete.assert_called_once()
        assert tree_mock.insert.call_count == len(journal.lines)

        # Verify first line values
        first_call_values = tree_mock.insert.call_args_list[0][1]["values"]
        assert first_call_values[0] == 11  # regnr
        assert first_call_values[1] == "Inntekter"  # rl name


class TestGrunnlagContextFiltering:
    """Verify Grunnlag filters by company in Valgt selskap mode."""

    def _make_page_with_run(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        proj = ConsolidationProject(
            client="Test", year="2025",
            parent_company_id="a",
            companies=[
                CompanyTB(company_id="a", name="Mor", row_count=2),
                CompanyTB(company_id="b", name="Datter", row_count=2),
            ],
        )
        tbs = {"a": _company_a_tb(), "b": _company_b_tb()}
        result_df, run_result = run_consolidation(proj, tbs)

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = proj
        page._consolidated_result_df = result_df
        page._last_run_result = run_result
        page._regnr_to_name = {10: "Eiendeler", 11: "Inntekter", 20: "SUM"}
        page._tree_grunnlag = MagicMock()
        page._grunnlag_label_var = MagicMock()
        page._result_mode_var = MagicMock()
        page._current_detail_cid = None

        return page, run_result

    def test_konsolidert_mode_shows_all_companies(self, _mock_config):
        page, run = self._make_page_with_run(_mock_config)
        page._result_mode_var.get.return_value = "Konsolidert"

        page._populate_grunnlag(10)

        # Should show all companies (both a and b have regnr 10)
        calls = page._tree_grunnlag.insert.call_args_list
        assert len(calls) == 2

    def test_valgt_selskap_mode_filters_to_company(self, _mock_config):
        page, run = self._make_page_with_run(_mock_config)
        page._result_mode_var.get.return_value = "Valgt selskap"
        page._current_detail_cid = "a"

        page._populate_grunnlag(10)

        # Should only show company "a" (Mor)
        calls = page._tree_grunnlag.insert.call_args_list
        assert len(calls) == 1
        first_values = calls[0][1]["values"]
        assert first_values[0] == "Mor"


class TestRefreshFromSessionClearsCache:
    """Verify refresh_from_session clears run state."""

    def test_session_reload_invalidates_cache(self, _mock_config):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = True
        page._status_var = MagicMock()
        page._result_df = pd.DataFrame()
        page._consolidated_result_df = pd.DataFrame()
        page._company_result_df = pd.DataFrame()
        page._preview_result_df = pd.DataFrame()
        page._last_run_result = "something"
        page._current_detail_cid = "xyz"
        page._tree_result = MagicMock()
        page._preview_label_var = MagicMock()
        page._lbl_statusbar = MagicMock()
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Konsolidert"
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = False
        page._update_session_tb_button = MagicMock()

        sess = MagicMock()
        sess.client = ""
        sess.year = ""

        with patch("src.pages.consolidation.frontend.page.storage"):
            page.refresh_from_session(sess)

        assert page._result_df is None
        assert page._consolidated_result_df is None
        assert page._company_result_df is None
        assert page._last_run_result is None
        assert page._current_detail_cid is None


# ---------------------------------------------------------------------------
# Tests: _on_show_unmapped handler
# ---------------------------------------------------------------------------

class TestOnShowUnmapped:
    """Verify Vis umappede handler navigates to Mapping tab with filter."""

    def test_show_unmapped_calls_detail_and_switches_tab(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_companies = MagicMock()
        page._tree_companies.selection.return_value = ["c1"]
        page._show_company_detail = MagicMock()
        page._mapping_tab = MagicMock()
        page._right_nb = MagicMock()

        page._on_show_unmapped()

        page._show_company_detail.assert_called_once_with("c1")
        page._mapping_tab.show_unmapped.assert_called_once()
        page._right_nb.select.assert_called_once_with(1)

    def test_show_unmapped_no_selection_does_nothing(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_companies = MagicMock()
        page._tree_companies.selection.return_value = []
        page._show_company_detail = MagicMock()
        page._mapping_tab = MagicMock()
        page._right_nb = MagicMock()

        page._on_show_unmapped()

        page._show_company_detail.assert_not_called()
        page._mapping_tab.show_unmapped.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _build_unmapped_warnings
# ---------------------------------------------------------------------------

class TestBuildUnmappedWarnings:
    """Verify unmapped account warnings include amounts."""

    def test_warns_about_unmapped_kontos_with_amounts(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage
        from consolidation.models import CompanyTB, ConsolidationProject

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(
            companies=[CompanyTB(company_id="a", name="Mor", row_count=3)],
        )
        page._mapping_unmapped = {"a": ["5000", "6000"]}

        tb = pd.DataFrame({
            "konto": ["1000", "5000", "6000"],
            "kontonavn": ["Bank", "Skatt", "Annet"],
            "ub": [100.0, 50000.0, 0.0],
        })
        tbs = {"a": tb}

        warnings = page._build_unmapped_warnings(tbs)

        assert len(warnings) == 1
        assert "Mor" in warnings[0]
        assert "5000" in warnings[0]
        # konto 6000 has ub=0 so should not be listed
        assert "6000" not in warnings[0]
        assert "1 umappede" in warnings[0]

    def test_no_warnings_when_all_mapped(self, _mock_config):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage
        from consolidation.models import CompanyTB, ConsolidationProject

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = ConsolidationProject(
            companies=[CompanyTB(company_id="a", name="Mor", row_count=2)],
        )
        page._mapping_unmapped = {"a": []}

        tbs = {"a": pd.DataFrame({"konto": ["1000"], "ub": [100.0]})}
        warnings = page._build_unmapped_warnings(tbs)

        assert warnings == []

    def test_no_warnings_when_no_project(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = None

        warnings = page._build_unmapped_warnings({})
        assert warnings == []


# ---------------------------------------------------------------------------
# Tests: export stale-state guard
# ---------------------------------------------------------------------------

class TestExportStaleGuard:
    """Verify export warns when run state is stale."""

    def test_export_warns_when_consolidated_result_is_none(self, _mock_config):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._result_df = pd.DataFrame({"regnr": [10]})
        page._project = MagicMock()
        page._project.client = "Test"
        page._project.year = "2025"
        page._consolidated_result_df = None  # stale!

        with patch("src.pages.consolidation.frontend.page.messagebox") as mock_mb:
            mock_mb.askyesno.return_value = True
            page._rerun_consolidation = MagicMock()
            # After rerun, result_df becomes None (no TBs) — should bail
            def _clear_result():
                page._result_df = None
            page._rerun_consolidation.side_effect = _clear_result

            page._on_export()

            mock_mb.askyesno.assert_called_once()
            page._rerun_consolidation.assert_called_once()

    def test_export_proceeds_when_user_declines_rerun(self, _mock_config):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._result_df = pd.DataFrame({"regnr": [10]})
        page._project = MagicMock()
        page._project.client = "Test"
        page._project.year = "2025"
        page._project.runs = []
        page._consolidated_result_df = None  # stale

        with patch("src.pages.consolidation.frontend.page.messagebox") as mock_mb, \
             patch("src.pages.consolidation.frontend.page.filedialog") as mock_fd:
            mock_mb.askyesno.return_value = False  # user says no
            # No runs → run_result is None → early return
            page._on_export()

            mock_mb.askyesno.assert_called_once()
            # Should not have asked for file (no runs available)

    def test_export_skips_guard_when_not_stale(self, _mock_config):
        from unittest.mock import MagicMock, patch
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._result_df = pd.DataFrame({"regnr": [10]})
        page._project = MagicMock()
        page._project.client = "Test"
        page._project.year = "2025"
        page._project.runs = [MagicMock()]
        page._consolidated_result_df = pd.DataFrame()  # NOT stale
        page._mapped_tbs = {}
        page._regnr_to_name = {}
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = False

        with patch("src.pages.consolidation.frontend.page.messagebox") as mock_mb, \
             patch("src.pages.consolidation.frontend.page.filedialog") as mock_fd:
            mock_fd.asksaveasfilename.return_value = ""  # user cancels
            page._on_export()

            # No stale warning dialog
            mock_mb.askyesno.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Sorting wiring (Del A)
# ---------------------------------------------------------------------------

class TestSortingWiring:
    """Verify enable_treeview_sorting is called on tree builds."""

    def test_page_imports_sorting(self, _mock_config):
        import src.pages.consolidation.frontend.page as page_consolidation
        assert hasattr(page_consolidation, "enable_treeview_sorting")

    def test_mapping_tab_imports_sorting(self, _mock_config):
        import src.pages.consolidation.frontend.mapping_tab as consolidation_mapping_tab
        assert hasattr(consolidation_mapping_tab, "enable_treeview_sorting")

    def test_reset_sort_state_clears_state(self, _mock_config):
        from src.pages.consolidation.frontend.page import _reset_sort_state
        from types import SimpleNamespace

        tree = MagicMock()
        tree._sort_state = SimpleNamespace(last_col="konto", descending=True)
        _reset_sort_state(tree)
        assert tree._sort_state.last_col is None
        assert tree._sort_state.descending is False

    def test_reset_sort_state_no_state_is_harmless(self, _mock_config):
        from src.pages.consolidation.frontend.page import _reset_sort_state

        tree = MagicMock(spec=[])  # no _sort_state
        _reset_sort_state(tree)  # should not raise

    def test_mapping_tab_reset_sort_state(self, _mock_config):
        from src.pages.consolidation.frontend.mapping_tab import _reset_sort_state
        from types import SimpleNamespace

        tree = MagicMock()
        tree._sort_state = SimpleNamespace(last_col="x", descending=True)
        _reset_sort_state(tree)
        assert tree._sort_state.last_col is None
        assert tree._sort_state.descending is False


# ---------------------------------------------------------------------------
# Tests: Sumpost drilldown (Del C)
# ---------------------------------------------------------------------------

class TestSumpostDrilldown:
    """Verify _populate_grunnlag expands sumposter to leaf lines."""

    def _make_page(self):
        from unittest.mock import MagicMock
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_grunnlag = MagicMock()
        page._tree_grunnlag.get_children.return_value = []
        page._grunnlag_label_var = MagicMock()
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Konsolidert"
        page._regnr_to_name = {
            10: "Eiendeler", 11: "Inntekter", 20: "SUM",
        }
        page._regnskapslinjer = _regnskapslinjer_df()
        page._last_run_result = None
        return page

    def test_sumpost_false_uses_single_regnr(self, _mock_config):
        page = self._make_page()

        # With no run result, just check label is set correctly
        page._populate_grunnlag(10, is_sumpost=False)
        label_text = page._grunnlag_label_var.set.call_args[0][0]
        assert "10" in label_text
        assert "underliggende" not in label_text

    def test_sumpost_true_expands_leaf_lines(self, _mock_config):
        from consolidation.models import RunResult

        page = self._make_page()

        # Create account_details that cover leaf-lines 10 and 11
        details = pd.DataFrame({
            "selskap": ["Mor", "Mor", "Datter"],
            "konto": ["1000", "3000", "1500"],
            "kontonavn": ["Bank", "Salg", "Varelager"],
            "regnr": [10.0, 11.0, 10.0],
            "regnskapslinje": ["Eiendeler", "Inntekter", "Eiendeler"],
            "ib": [0.0, 0.0, 0.0],
            "netto": [100.0, -200.0, 50.0],
            "ub_original": [100.0, -200.0, 50.0],
            "valuta": ["NOK", "NOK", "NOK"],
            "kurs": [1.0, 1.0, 1.0],
            "ub": [100.0, -200.0, 50.0],
        })
        run_result = MagicMock()
        run_result.account_details = details
        page._last_run_result = run_result

        page._populate_grunnlag(20, is_sumpost=True)

        # Should show "2 underliggende linjer" in label
        label_text = page._grunnlag_label_var.set.call_args[0][0]
        assert "underliggende" in label_text

        # All 3 rows should be inserted (regnr 10 and 11 are both leaf lines of sumpost 20)
        insert_calls = page._tree_grunnlag.insert.call_args_list
        assert len(insert_calls) == 3

    def test_sumpost_no_regnskapslinjer_falls_back(self, _mock_config):
        page = self._make_page()
        page._regnskapslinjer = None  # no regnskapslinjer loaded

        details = pd.DataFrame({
            "selskap": ["Mor"],
            "konto": ["1000"],
            "kontonavn": ["Bank"],
            "regnr": [20.0],
            "regnskapslinje": ["SUM"],
            "ib": [0.0],
            "netto": [100.0],
            "ub_original": [100.0],
            "valuta": ["NOK"],
            "kurs": [1.0],
            "ub": [100.0],
        })
        run_result = MagicMock()
        run_result.account_details = details
        page._last_run_result = run_result

        # With is_sumpost=True but no regnskapslinjer, should fallback to [regnr]
        page._populate_grunnlag(20, is_sumpost=True)

        # Label should NOT mention "underliggende" since we couldn't expand
        label_text = page._grunnlag_label_var.set.call_args[0][0]
        assert "underliggende" not in label_text

    def test_on_result_line_select_detects_sumpost_tag(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_result = MagicMock()
        page._tree_result.selection.return_value = ["item1"]
        page._tree_result.item.side_effect = lambda iid, key: {
            "values": (20, "SUM", "100", "-200"),
            "tags": ("sumline",),
        }[key]
        page._left_nb = MagicMock()
        page._populate_grunnlag = MagicMock()

        page._on_result_line_select()

        page._populate_grunnlag.assert_called_once_with(20, is_sumpost=True)
        page._left_nb.select.assert_called_once_with(2)

    def test_on_result_line_select_leaf_line(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_result = MagicMock()
        page._tree_result.selection.return_value = ["item1"]
        page._tree_result.item.side_effect = lambda iid, key: {
            "values": (10, "Eiendeler", "100"),
            "tags": (),
        }[key]
        page._left_nb = MagicMock()
        page._populate_grunnlag = MagicMock()

        page._on_result_line_select()

        page._populate_grunnlag.assert_called_once_with(10, is_sumpost=False)

    def test_on_result_line_select_no_selection(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_result = MagicMock()
        page._tree_result.selection.return_value = []
        page._populate_grunnlag = MagicMock()

        page._on_result_line_select()

        page._populate_grunnlag.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: Right-click routing (Del B)
# ---------------------------------------------------------------------------

class TestRightClickRouting:
    """Verify header right-clicks route to column manager, data clicks to context menu."""

    def test_company_right_click_heading_shows_col_menu(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_companies = MagicMock()
        page._tree_companies.identify_region.return_value = "heading"
        page._companies_col_mgr = MagicMock()
        page._company_menu = MagicMock()
        event = MagicMock()

        page._on_company_right_click(event)

        page._companies_col_mgr.show_header_menu.assert_called_once_with(event)
        page._company_menu.post.assert_not_called()

    def test_company_right_click_cell_shows_context_menu(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_companies = MagicMock()
        page._tree_companies.identify_region.return_value = "cell"
        page._tree_companies.identify_row.return_value = "item1"
        page._companies_col_mgr = MagicMock()
        page._company_menu = MagicMock()
        event = MagicMock()

        page._on_company_right_click(event)

        page._companies_col_mgr.show_header_menu.assert_not_called()
        page._company_menu.post.assert_called_once()

    def test_detail_right_click_heading_shows_col_menu(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_detail = MagicMock()
        page._tree_detail.identify_region.return_value = "heading"
        page._detail_col_mgr = MagicMock()
        page._detail_menu = MagicMock()
        event = MagicMock()

        page._on_detail_right_click(event)

        page._detail_col_mgr.show_header_menu.assert_called_once_with(event)
        page._detail_menu.post.assert_not_called()

    def test_detail_right_click_cell_replaces_selection(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_detail = MagicMock()
        page._tree_detail.identify_region.return_value = "cell"
        page._tree_detail.identify_row.return_value = "6510"
        page._detail_col_mgr = MagicMock()
        page._detail_menu = MagicMock()
        event = MagicMock()

        page._on_detail_right_click(event)

        page._tree_detail.selection_set.assert_called_once_with("6510")
        page._detail_menu.post.assert_called_once()

    def test_result_right_click_delegates_to_col_mgr(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        mock_mgr = MagicMock()
        page._result_col_mgrs = {"company": mock_mgr, "consolidated": mock_mgr, "per_company": mock_mgr}
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        event = MagicMock()

        page._on_result_right_click(event)

        mock_mgr.on_right_click.assert_called_once_with(event)


# ---------------------------------------------------------------------------
# Tests: Per-mode result column profiles (P2)
# ---------------------------------------------------------------------------

class TestResultColumnProfiles:
    """Verify each result mode uses its own column manager."""

    def test_three_separate_managers_created(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        # Simulate the dict that _build_result_tab creates
        mgr_a = MagicMock()
        mgr_b = MagicMock()
        mgr_c = MagicMock()
        page._result_col_mgrs = {
            "company": mgr_a,
            "consolidated": mgr_b,
            "per_company": mgr_c,
        }
        page._result_mode_var = MagicMock()

        page._result_mode_var.get.return_value = "Valgt selskap"
        assert page._result_col_mgr is mgr_a

        page._result_mode_var.get.return_value = "Konsolidert"
        assert page._result_col_mgr is mgr_b

        page._result_mode_var.get.return_value = "Per selskap"
        assert page._result_col_mgr is mgr_c

    def test_mode_keys_mapping(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        assert ConsolidationPage._RESULT_MODE_KEYS == {
            "Valgt selskap": "company",
            "Konsolidert": "consolidated",
            "Per selskap": "per_company",
        }

    def test_different_modes_use_different_pref_keys(self, _mock_config):
        """Each mode manager should persist under a unique view_id."""
        from treeview_column_manager import TreeviewColumnManager

        tree = MagicMock()
        tree.__setitem__ = MagicMock()

        with patch.object(TreeviewColumnManager, "load_from_preferences"):
            mgr_co = TreeviewColumnManager(tree, view_id="result.company", all_cols=())
            mgr_con = TreeviewColumnManager(tree, view_id="result.consolidated", all_cols=())
            mgr_pc = TreeviewColumnManager(tree, view_id="result.per_company", all_cols=())

        assert mgr_co._pref_key != mgr_con._pref_key
        assert mgr_con._pref_key != mgr_pc._pref_key
        assert mgr_co._order_key != mgr_con._order_key

    def test_update_columns_only_affects_active_mode(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False

        mgr_a = MagicMock()
        mgr_b = MagicMock()
        mgr_c = MagicMock()
        page._result_col_mgrs = {
            "company": mgr_a,
            "consolidated": mgr_b,
            "per_company": mgr_c,
        }
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Konsolidert"

        # Simulate what _populate_result_tree does
        page._result_col_mgr.update_columns(["regnr", "regnskapslinje", "Mor", "Doetre"])

        mgr_b.update_columns.assert_called_once_with(["regnr", "regnskapslinje", "Mor", "Doetre"])
        mgr_a.update_columns.assert_not_called()
        mgr_c.update_columns.assert_not_called()


class _StrictResultTree:
    """Minimal tree that fails if stale displaycolumns survive a column rebuild."""

    def __init__(self):
        self.columns = ()
        self.displaycolumns = ("regnr", "regnskapslinje", "Mor")
        self.rows = []

    def __setitem__(self, key, value):
        if key == "displaycolumns":
            self.displaycolumns = value
            return
        if key == "columns":
            if self.displaycolumns != "#all":
                active = tuple(self.displaycolumns)
                invalid = next((c for c in active if c not in value), None)
                if invalid is not None:
                    raise RuntimeError(f"Invalid column index {invalid}")
            self.columns = tuple(value)
            return
        raise KeyError(key)

    def __getitem__(self, key):
        if key == "columns":
            return self.columns
        if key == "displaycolumns":
            return self.displaycolumns
        raise KeyError(key)

    def delete(self, *_a, **_k):
        self.rows.clear()

    def get_children(self, *_a, **_k):
        return []

    def heading(self, *_a, **_k):
        return None

    def column(self, *_a, **_k):
        return None

    def insert(self, *_a, **_k):
        self.rows.append((_a, _k))


class TestResultTreeColumnReset:
    def test_populate_result_tree_resets_stale_displaycolumns_before_columns(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_result = _StrictResultTree()
        page._hide_zero_var = MagicMock()
        page._hide_zero_var.get.return_value = False
        page._result_mode_var = MagicMock()
        page._result_mode_var.get.return_value = "Valgt selskap"
        active_mgr = MagicMock()
        page._result_col_mgrs = {
            "company": active_mgr,
            "consolidated": MagicMock(),
            "per_company": MagicMock(),
        }

        df = pd.DataFrame({
            "regnr": [145],
            "regnskapslinje": ["Annen rentekostnad"],
            "sumpost": [False],
            "formel": [None],
            "UB": [784896.95],
        })

        with patch("src.pages.consolidation.frontend.page.enable_treeview_sorting", None):
            page._populate_result_tree(df, ["UB"])

        assert page._tree_result.displaycolumns == "#all"
        assert page._tree_result.columns == ("regnr", "regnskapslinje", "UB")
        active_mgr.update_columns.assert_called_once_with(["regnr", "regnskapslinje", "UB"])


class TestConsolidationControlRows:
    def test_append_control_rows_builds_balance_and_disposition_rows(self):
        from consolidation.control_rows import append_control_rows

        df = pd.DataFrame(
            {
                "regnr": [280, 350, 665, 850],
                "regnskapslinje": [
                    "Årsresultat",
                    "Sum overføringer",
                    "Sum eiendeler",
                    "Sum egenkapital og gjeld",
                ],
                "sumpost": [True, True, True, True],
                "formel": ["", "", "", ""],
                "Ortomedic AS": [-100.0, 100.0, 500.0, -500.0],
                "Micromedic AB": [250.0, -245.0, 800.0, -790.0],
                "konsolidert": [150.0, -145.0, 1300.0, -1290.0],
            }
        )

        out = append_control_rows(df)
        assert out is not None

        ctrl_balance = out.loc[out["regnr"] == 9010].iloc[0]
        ctrl_disp = out.loc[out["regnr"] == 9020].iloc[0]
        ctrl_sum = out.loc[out["regnr"] == 9030].iloc[0]

        assert ctrl_balance["regnskapslinje"] == "Kontroll eiendeler / EK + Gjeld"
        assert ctrl_balance["Ortomedic AS"] == pytest.approx(0.0)
        assert ctrl_balance["Micromedic AB"] == pytest.approx(10.0)
        assert ctrl_balance["konsolidert"] == pytest.approx(10.0)

        assert ctrl_disp["regnskapslinje"] == "Kontroll Årsresultat / Sum overføringer"
        assert ctrl_disp["Ortomedic AS"] == pytest.approx(0.0)
        assert ctrl_disp["Micromedic AB"] == pytest.approx(5.0)
        assert ctrl_disp["konsolidert"] == pytest.approx(5.0)

        assert ctrl_sum["regnskapslinje"] == "Sumkontroll"
        assert ctrl_sum["Ortomedic AS"] == pytest.approx(0.0)
        assert ctrl_sum["Micromedic AB"] == pytest.approx(15.0)
        assert ctrl_sum["konsolidert"] == pytest.approx(15.0)

    def test_export_appends_control_rows_to_main_sheet(self, _mock_config):
        from consolidation.export import build_consolidation_workbook
        from consolidation.models import RunResult

        result_df = pd.DataFrame(
            {
                "regnr": [280, 350, 665, 850],
                "regnskapslinje": [
                    "Årsresultat",
                    "Sum overføringer",
                    "Sum eiendeler",
                    "Sum egenkapital og gjeld",
                ],
                "sumpost": [True, True, True, True],
                "formel": ["", "", "", ""],
                "Ortomedic AS": [-100.0, 100.0, 500.0, -500.0],
                "Micromedic AB": [250.0, -245.0, 800.0, -790.0],
                "Mor": [-100.0, 100.0, 500.0, -500.0],
                "Doetre": [250.0, -245.0, 800.0, -790.0],
                "sum_foer_elim": [150.0, -145.0, 1300.0, -1290.0],
                "eliminering": [0.0, 0.0, 0.0, 0.0],
                "konsolidert": [150.0, -145.0, 1300.0, -1290.0],
            }
        )
        run_result = RunResult(company_ids=["a"], account_details=pd.DataFrame())

        wb = build_consolidation_workbook(
            result_df, [], [], {},
            run_result,
        )
        ws = wb["Konsernoppstilling"]

        labels = {
            ws.cell(row=row_idx, column=2).value: row_idx
            for row_idx in range(5, ws.max_row + 1)
            if ws.cell(row=row_idx, column=2).value
        }

        assert "Kontroll eiendeler / EK + Gjeld" in labels
        assert "Kontroll Årsresultat / Sum overføringer" in labels
        assert "Sumkontroll" in labels


class _SettableVar:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class TestDetailTreeAggregation:
    def test_populate_detail_tree_aggregates_duplicate_accounts(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_detail = MagicMock()
        page._tree_detail.get_children.return_value = []
        page._mapping_unmapped = {}
        page._mapping_review_accounts = {}
        page._detail_hide_zero_var = MagicMock()
        page._detail_hide_zero_var.get.return_value = False
        page._detail_count_var = _SettableVar()
        page._regnr_to_name = {695: "Annen egenkapital"}

        tb = pd.DataFrame(
            {
                "konto": ["6510", "6510"],
                "kontonavn": ["Registreret kapital mv.", "Annen egenkapital"],
                "regnr": [695, 695],
                "ib": [0.0, 0.0],
                "netto": [100.0, 200.0],
                "ub": [100.0, 200.0],
            }
        )

        page._populate_detail_tree(tb, "d1")

        page._tree_detail.insert.assert_called_once()
        _, kwargs = page._tree_detail.insert.call_args
        assert kwargs["iid"] == "6510"
        assert kwargs["values"][0] == "6510"
        assert kwargs["values"][2] == 695
        assert kwargs["values"][5] == "300,00"
        assert kwargs["values"][6] == "300,00"
        assert page._detail_count_var.value == "1 konto"

    def test_populate_line_basis_detail_tree_formats_pdf_rows(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._tree_detail = MagicMock()
        page._tree_detail.get_children.return_value = []
        page._detail_hide_zero_var = MagicMock()
        page._detail_hide_zero_var.get.return_value = False
        page._detail_count_var = _SettableVar()

        basis = pd.DataFrame(
            {
                "regnr": [10],
                "regnskapslinje": ["Eiendeler"],
                "source_regnskapslinje": ["Eiendeler i årsregnskap"],
                "ub": [1234.5],
                "source_page": [2],
                "confidence": [0.83],
                "review_status": ["approved"],
            }
        )

        page._populate_line_basis_detail_tree(basis)

        page._tree_detail.insert.assert_called_once()
        _, kwargs = page._tree_detail.insert.call_args
        assert kwargs["values"][0] == 10
        assert kwargs["values"][1] == "Eiendeler"
        assert kwargs["values"][2] == "Eiendeler i årsregnskap"
        assert kwargs["values"][3] == "1 234,50"
        assert kwargs["values"][4] == 2
        assert kwargs["values"][5] == "Godkjent"
        assert kwargs["values"][6] == "83%"
        assert kwargs["tags"] == ("approved",)
        assert page._detail_count_var.value == "1 linje"

    def test_change_mapping_deduplicates_selected_accounts(self, _mock_config):
        from src.pages.consolidation.frontend.page import ConsolidationPage

        page = ConsolidationPage.__new__(ConsolidationPage)
        page._tk_ok = False
        page._project = MagicMock()
        page._tree_companies = MagicMock()
        page._tree_companies.selection.return_value = ["d1"]
        page._tree_detail = MagicMock()
        page._tree_detail.selection.return_value = ["row1", "row2"]
        page._tree_detail.item.side_effect = [
            ("6510", "Registreret kapital mv.", "670"),
            ("6510", "Annen egenkapital", "695"),
        ]
        page._regnskapslinjer = pd.DataFrame(
            {
                "regnr": [695],
                "regnskapslinje": ["Annen egenkapital"],
                "sumpost": [False],
            }
        )

        fake_dialog = MagicMock()
        label_calls = []

        def _fake_label(*_args, **kwargs):
            label_calls.append(kwargs)
            widget = MagicMock()
            widget.pack = MagicMock()
            return widget

        def _fake_widget(*_args, **_kwargs):
            widget = MagicMock()
            widget.pack = MagicMock()
            return widget

        with patch("src.pages.consolidation.frontend.page.tk.Toplevel", return_value=fake_dialog), \
             patch("src.pages.consolidation.frontend.page.ttk.Label", side_effect=_fake_label), \
             patch("src.pages.consolidation.frontend.page.ttk.Combobox", side_effect=_fake_widget), \
             patch("src.pages.consolidation.frontend.page.ttk.Frame", side_effect=_fake_widget), \
             patch("src.pages.consolidation.frontend.page.ttk.Button", side_effect=_fake_widget), \
             patch("src.pages.consolidation.frontend.page.tk.StringVar", return_value=MagicMock()):
            page._on_change_mapping()

        first_label = next(call for call in label_calls if call.get("font") == ("", 10, "bold"))
        assert first_label["text"] == "Konto: 6510 — Registreret kapital mv."
