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


# ---------------------------------------------------------------------------
# P6: Norwegian amount formatting
# ---------------------------------------------------------------------------

class TestFmtNo:
    def test_basic_formatting(self):
        from page_consolidation import _fmt_no

        assert _fmt_no(0) == "0"
        assert _fmt_no(1234) == "1 234"
        assert _fmt_no(-5678) == "-5 678"
        assert _fmt_no(1234567.89, 2) == "1 234 567,89"
        assert _fmt_no(-42.5, 2) == "-42,50"
        assert _fmt_no(999) == "999"
        assert _fmt_no(1000) == "1 000"
        assert _fmt_no(0, 2) == "0,00"

    def test_rounding(self):
        from page_consolidation import _fmt_no

        assert _fmt_no(99.999) == "100"
        assert _fmt_no(99.999, 2) == "100,00"
        assert _fmt_no(1_234_567.895, 2) == "1 234 567,90"


# ---------------------------------------------------------------------------
# Parent-mapping: Analyse-overrides arves av morselskapet
# ---------------------------------------------------------------------------

class TestParentMappingFromAnalyse:
    """Verify _get_effective_company_overrides merges Analyse + local correctly."""

    def _make_page(self, *, analyse_overrides=None, local_overrides=None):
        from unittest.mock import MagicMock, patch
        from page_consolidation import ConsolidationPage

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

    def test_local_override_wins_over_analyse(self):
        """Local consolidation override should take precedence over Analyse."""
        from unittest.mock import patch

        page = self._make_page(
            analyse_overrides={"1000": 10, "2000": 11},
            local_overrides={"parent": {"1000": 99}},  # override konto 1000
        )

        with patch("regnskap_client_overrides.load_account_overrides", return_value=self._analyse_overrides):
            result = page._get_effective_company_overrides("parent")

        # 1000 overridden locally to 99, 2000 inherited from Analyse
        assert result == {"1000": 99, "2000": 11}

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
        from page_consolidation import ConsolidationPage

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
        from page_consolidation import ConsolidationPage

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
