"""Tests for scoping_engine."""

from __future__ import annotations

import pandas as pd
import pytest

from src.pages.scoping.backend.engine import (
    ScopingLine,
    ScopingResult,
    build_scoping,
    classify_line,
    compute_auto_scope_out,
    scoped_out_totals_by_group,
)


def _mk_line(regnr: str, amount: float, line_type: str = "PL", is_summary: bool = False) -> ScopingLine:
    return ScopingLine(
        regnr=regnr,
        regnskapslinje=f"Linje {regnr}",
        line_type=line_type,
        amount=amount,
        is_summary=is_summary,
    )


class TestComputeAutoScopeOut:
    def test_stops_when_adding_exceeds_pm(self):
        # PM=175_000. Kandidater <175k, sortert stigende:
        #   5k → cum 5k
        #   10k → cum 15k
        #   50k → cum 65k
        #   80k → cum 145k   ← inkludert
        #   150k → cum 295k  ← bryter PM, stopp. 150k er IKKE scoped ut.
        lines = [
            _mk_line("10", 150_000),
            _mk_line("20", 80_000),
            _mk_line("30", 50_000),
            _mk_line("40", 10_000),
            _mk_line("50", 5_000),
            _mk_line("60", 200_000),  # ≥ PM, kandidat uten effekt
        ]
        result = compute_auto_scope_out(lines, pm=175_000)
        assert result == {
            "50": "ut",
            "40": "ut",
            "30": "ut",
            "20": "ut",
        }
        assert "10" not in result  # 150k brøt grensen
        assert "60" not in result  # over PM, aldri kandidat

    def test_absolute_values_used(self):
        """Negative og positive beløp behandles like."""
        lines = [
            _mk_line("10", -50_000),
            _mk_line("20", 30_000),
            _mk_line("30", -20_000),
        ]
        result = compute_auto_scope_out(lines, pm=175_000)
        # Sorteres: 20k, 30k, 50k → cumulative 20k, 50k, 100k, alle under PM
        assert result == {"30": "ut", "20": "ut", "10": "ut"}

    def test_pl_and_bs_treated_separately(self):
        """PM brukes per gruppe — PL og BS har separate cumulative."""
        # PM=100k. PL-linjer: 30k + 40k = 70k (begge ut). 80k > 70k+80k=150k, brutt
        # BS-linjer: 60k alene (under PM). Neste ville bryte ved 60+50=110k
        lines = [
            _mk_line("10", 30_000, "PL"),
            _mk_line("20", 40_000, "PL"),
            _mk_line("30", 80_000, "PL"),  # ville bryte
            _mk_line("100", 50_000, "BS"),
            _mk_line("110", 60_000, "BS"),  # cum 110k > PM=100k → break. 60k forblir IN.
        ]
        result = compute_auto_scope_out(lines, pm=100_000)
        assert result == {
            "10": "ut",  # PL
            "20": "ut",  # PL (30+40=70 ≤ 100)
            "100": "ut",  # BS (50 ≤ 100)
        }

    def test_summary_lines_excluded(self):
        """Sumposter (is_summary=True) er ikke kandidater for auto-scope."""
        lines = [
            _mk_line("10", 5_000),
            _mk_line("19", 50_000, is_summary=True),  # Sum driftsinntekter
            _mk_line("20", 10_000),
        ]
        result = compute_auto_scope_out(lines, pm=175_000)
        assert "19" not in result
        assert result == {"10": "ut", "20": "ut"}

    def test_amount_at_pm_not_candidate(self):
        """Linjer med |amount| = PM er over grensen og skal ikke scoped ut."""
        lines = [_mk_line("10", 175_000)]
        result = compute_auto_scope_out(lines, pm=175_000)
        assert result == {}

    def test_zero_pm_returns_empty(self):
        lines = [_mk_line("10", 100)]
        assert compute_auto_scope_out(lines, pm=0) == {}
        assert compute_auto_scope_out(lines, pm=-1) == {}

    def test_empty_lines(self):
        assert compute_auto_scope_out([], pm=100_000) == {}

    def test_greedy_smallest_first_not_optimal(self):
        """Algoritmen er greedy smallest-first — ikke optimal fylling.

        Hvis man kunne velge smartere kunne man kanskje fylt PM bedre,
        men brukerens regel er 'start på minste, jobb oppover'. Denne
        testen dokumenterer den bevisste begrensningen.
        """
        # PM=100k. Linjer: 10k, 90k, 50k (sortert: 10, 50, 90)
        # Greedy: 10 (cum 10) → 50 (cum 60) → 90 (cum 150) → stopp.
        # Scoper ut: 10k + 50k = 60k. Igjen 40k kapasitet, men algoritmen
        # tar ikke "neste etter" siden 90k bryter.
        lines = [
            _mk_line("10", 10_000),
            _mk_line("20", 90_000),
            _mk_line("30", 50_000),
        ]
        result = compute_auto_scope_out(lines, pm=100_000)
        assert result == {"10": "ut", "30": "ut"}
        assert "20" not in result  # 90k brøt grensen


class TestScopedOutTotalsByGroup:
    def test_sums_per_group(self):
        lines = [
            ScopingLine(regnr="10", regnskapslinje="a", line_type="PL", amount=-5_000, scoping="ut"),
            ScopingLine(regnr="20", regnskapslinje="b", line_type="PL", amount=10_000, scoping="ut"),
            ScopingLine(regnr="30", regnskapslinje="c", line_type="PL", amount=99_000, scoping=""),  # i scope
            ScopingLine(regnr="100", regnskapslinje="d", line_type="BS", amount=7_000, scoping="ut"),
            ScopingLine(regnr="19", regnskapslinje="sum", line_type="PL", amount=1_000_000, scoping="ut", is_summary=True),  # ekskluderes
        ]
        totals = scoped_out_totals_by_group(lines)
        assert totals["PL"] == 15_000  # 5 + 10, sumposten ekskluderes
        assert totals["BS"] == 7_000

    def test_empty_lines(self):
        assert scoped_out_totals_by_group([]) == {"PL": 0.0, "BS": 0.0}


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
