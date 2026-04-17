"""Tests for scoping_engine."""

from __future__ import annotations

import pandas as pd
import pytest

from scoping_engine import ScopingLine, ScopingResult, build_scoping, classify_line


class TestClassifyLine:
    def test_vesentlig(self):
        assert classify_line(500_000, 375_000, 25_000) == "vesentlig"

    def test_moderat(self):
        assert classify_line(100_000, 375_000, 25_000) == "moderat"

    def test_ikke_vesentlig(self):
        assert classify_line(10_000, 375_000, 25_000) == "ikke_vesentlig"

    def test_exact_pm_is_vesentlig(self):
        assert classify_line(375_000, 375_000, 25_000) == "vesentlig"

    def test_exact_sum_is_moderat(self):
        assert classify_line(25_000, 375_000, 25_000) == "moderat"

    def test_negative_amount(self):
        assert classify_line(-500_000, 375_000, 25_000) == "vesentlig"

    def test_zero_pm_returns_empty(self):
        assert classify_line(100_000, 0, 0) == ""


class TestBuildScoping:
    @pytest.fixture()
    def rl_pivot(self):
        return pd.DataFrame({
            "regnr": [10, 20, 70],
            "regnskapslinje": ["Salgsinntekt", "Varekostnad", "Annen driftskostnad"],
            "IB": [10_000_000, 7_000_000, 15_000],
            "UB": [12_000_000, 8_000_000, 18_000],
            "UB_fjor": [10_000_000, 7_000_000, 15_000],
            "Endring_fjor": [2_000_000, 1_000_000, 3_000],
            "Endring_pct": [20.0, 14.3, 20.0],
            "Antall": [100, 50, 10],
        })

    @pytest.fixture()
    def materiality(self):
        return {
            "active_materiality": {
                "overall_materiality": 500_000,
                "performance_materiality": 375_000,
                "clearly_trivial": 25_000,
            }
        }

    def test_basic_classification(self, rl_pivot, materiality):
        result = build_scoping(rl_pivot, materiality)
        assert len(result.lines) == 3
        assert result.om == 500_000
        assert result.pm == 375_000

        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["10"].classification == "vesentlig"
        assert by_regnr["20"].classification == "vesentlig"
        assert by_regnr["70"].classification == "ikke_vesentlig"

    def test_change_amount_and_pct_from_ub_fjor(self, rl_pivot, materiality):
        result = build_scoping(rl_pivot, materiality)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["10"].change_amount == 2_000_000
        assert by_regnr["10"].change_pct == 20.0  # (12M - 10M) / 10M * 100

    def test_pct_of_pm(self, rl_pivot, materiality):
        result = build_scoping(rl_pivot, materiality)
        by_regnr = {l.regnr: l for l in result.lines}
        # 12M / 375k * 100 = 3200%
        assert by_regnr["10"].pct_of_pm == 3200.0
        # Klassifisering skal fortsatt beregnes fra dagens UB, ikke fjorårets UB
        assert by_regnr["70"].classification == "ikke_vesentlig"

    def test_missing_ub_fjor_does_not_fallback_to_ib(self, rl_pivot, materiality):
        rl_pivot = rl_pivot.copy()
        rl_pivot.loc[rl_pivot["regnr"] == 70, "UB_fjor"] = None
        result = build_scoping(rl_pivot, materiality)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["70"].amount_prior is None
        assert by_regnr["70"].change_amount is None
        assert by_regnr["70"].change_pct is None

    def test_real_zero_ub_is_preserved(self, rl_pivot, materiality):
        rl_pivot = rl_pivot.copy()
        rl_pivot.loc[rl_pivot["regnr"] == 70, "UB"] = 0.0
        rl_pivot.loc[rl_pivot["regnr"] == 70, "UB_fjor"] = 10_000.0
        result = build_scoping(rl_pivot, materiality)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["70"].amount == 0.0
        assert by_regnr["70"].classification == "ikke_vesentlig"
        assert by_regnr["70"].change_amount == -10_000.0

    def test_overrides(self, rl_pivot, materiality):
        overrides = {"70": {"scoping": "ut", "rationale": "Under SUM"}}
        result = build_scoping(rl_pivot, materiality, overrides=overrides)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["70"].scoping == "ut"
        assert by_regnr["70"].rationale == "Under SUM"

    def test_aggregation_ok(self, rl_pivot, materiality):
        overrides = {"70": {"scoping": "ut"}}
        result = build_scoping(rl_pivot, materiality, overrides=overrides)
        assert result.scoped_out_total == 18_000
        assert result.aggregation_ok is True

    def test_aggregation_fail(self, rl_pivot, materiality):
        # Scope out varekostnad (8M) which exceeds OM (500k)
        overrides = {"20": {"scoping": "ut"}}
        result = build_scoping(rl_pivot, materiality, overrides=overrides)
        assert result.scoped_out_total == 8_000_000
        assert result.aggregation_ok is False

    def test_no_materiality(self, rl_pivot):
        result = build_scoping(rl_pivot, None)
        assert result.om == 0
        assert result.pm == 0
        # All lines should have empty classification
        for line in result.lines:
            assert line.classification == ""

    def test_action_counts(self, rl_pivot, materiality):
        counts = {"10": 7, "20": 2}
        result = build_scoping(rl_pivot, materiality, action_counts=counts)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["10"].action_count == 7
        assert by_regnr["20"].action_count == 2
        assert by_regnr["70"].action_count == 0

    def test_ib_ub_avvik(self, rl_pivot, materiality):
        result = build_scoping(rl_pivot, materiality, ib_ub_avvik={"10"})
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["10"].has_ib_ub_avvik is True
        assert by_regnr["20"].has_ib_ub_avvik is False

    def test_manual_classification_override(self, rl_pivot, materiality):
        overrides = {"70": {"classification": "manuell"}}
        result = build_scoping(rl_pivot, materiality, overrides=overrides)
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["70"].classification == "manuell"
        assert by_regnr["70"].auto_classification == "ikke_vesentlig"

    def test_empty_pivot(self, materiality):
        result = build_scoping(pd.DataFrame(), materiality)
        assert len(result.lines) == 0
        assert result.om == 500_000

    def test_summary_lines_excluded(self, rl_pivot, materiality):
        """Sumposter (is_summary=True) skal ikke klassifiseres eller scopes."""
        result = build_scoping(
            rl_pivot, materiality, summary_regnr={"19", "79"},
        )
        by_regnr = {l.regnr: l for l in result.lines}
        # regnr 19 og 79 finnes ikke i fixture, men la oss teste med en som finnes
        # Legg til sumpost-regnr som finnes i fixture
        rl_with_sum = rl_pivot.copy()
        rl_with_sum = pd.concat([rl_with_sum, pd.DataFrame({
            "regnr": [19],
            "regnskapslinje": ["Sum driftsinntekter"],
            "IB": [10_000_000],
            "UB": [12_000_000],
            "Endring": [2_000_000],
            "Antall": [0],
        })], ignore_index=True)

        result = build_scoping(
            rl_with_sum, materiality, summary_regnr={"19"},
        )
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["19"].is_summary is True
        assert by_regnr["19"].classification == ""
        assert by_regnr["19"].scoping == ""
        assert by_regnr["19"].pct_of_pm == 0.0
        # Vanlige linjer er ikke påvirket
        assert by_regnr["10"].is_summary is False
        assert by_regnr["10"].classification == "vesentlig"

    def test_summary_excluded_from_aggregation(self, rl_pivot, materiality):
        """Scopet-ut sumposter skal ikke telle med i aggregering."""
        rl_with_sum = pd.concat([rl_pivot, pd.DataFrame({
            "regnr": [19],
            "regnskapslinje": ["Sum driftsinntekter"],
            "IB": [10_000_000],
            "UB": [12_000_000],
            "Endring": [2_000_000],
            "Antall": [0],
        })], ignore_index=True)

        # Selv om sumposten har override "ut", skal den ikke telle
        overrides = {"19": {"scoping": "ut"}, "70": {"scoping": "ut"}}
        result = build_scoping(
            rl_with_sum, materiality,
            overrides=overrides,
            summary_regnr={"19"},
        )
        # Sumposten har scoping="" fordi is_summary blokkerer det
        by_regnr = {l.regnr: l for l in result.lines}
        assert by_regnr["19"].scoping == ""
        # Bare regnr 70 (18k) teller
        assert result.scoped_out_total == 18_000
