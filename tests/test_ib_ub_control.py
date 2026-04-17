"""Tester for IB/UB-kontroll beregningsmodul."""

from __future__ import annotations

import pandas as pd
import pytest

import ib_ub_control


def _make_sb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1920", "3000", "4000", "6000"],
        "kontonavn": ["Bankinnskudd", "Salgsinntekter", "Varekostnad", "Lønn"],
        "ib": [100_000.0, 0.0, 0.0, 0.0],
        "ub": [150_000.0, -500_000.0, 200_000.0, 150_000.0],
    })


def _make_hb() -> pd.DataFrame:
    return pd.DataFrame({
        "Konto": ["1920", "1920", "3000", "3000", "4000", "6000"],
        "Beløp": [60_000.0, -10_000.0, -300_000.0, -200_000.0, 200_000.0, 150_000.0],
    })


class TestBuildAccountReconciliation:
    def test_basic_reconciliation(self) -> None:
        sb = _make_sb()
        hb = _make_hb()
        result = ib_ub_control.build_account_reconciliation(sb, hb)

        assert list(result.columns) == [
            "konto", "kontonavn", "sb_ib", "sb_ub", "sb_netto", "hb_sum", "differanse", "har_avvik",
        ]
        assert len(result) == 4

        bank = result.loc[result["konto"] == "1920"].iloc[0]
        assert bank["sb_ib"] == 100_000.0
        assert bank["sb_ub"] == 150_000.0
        assert bank["sb_netto"] == pytest.approx(50_000.0)
        assert bank["hb_sum"] == pytest.approx(50_000.0)
        assert bank["differanse"] == pytest.approx(0.0)
        assert bank["har_avvik"] is False or bank["har_avvik"] == False  # noqa: E712

    def test_detects_discrepancy(self) -> None:
        sb = pd.DataFrame({
            "konto": ["1920"],
            "kontonavn": ["Bank"],
            "ib": [100.0],
            "ub": [200.0],
        })
        hb = pd.DataFrame({
            "Konto": ["1920"],
            "Beløp": [50.0],  # SB netto=100, HB sum=50 → avvik 50
        })
        result = ib_ub_control.build_account_reconciliation(sb, hb)
        assert result.iloc[0]["har_avvik"] == True  # noqa: E712
        assert result.iloc[0]["differanse"] == pytest.approx(50.0)

    def test_account_only_in_sb(self) -> None:
        sb = pd.DataFrame({
            "konto": ["1920", "9999"],
            "kontonavn": ["Bank", "Ukjent"],
            "ib": [50.0, 100.0],
            "ub": [50.0, 100.0],
        })
        hb = pd.DataFrame({"Konto": ["1920"], "Beløp": [0.0]})
        result = ib_ub_control.build_account_reconciliation(sb, hb)
        assert len(result) == 2
        ukjent = result.loc[result["konto"] == "9999"].iloc[0]
        assert ukjent["hb_sum"] == 0.0

    def test_account_only_in_hb(self) -> None:
        sb = pd.DataFrame({"konto": ["1920"], "kontonavn": ["Bank"], "ib": [10.0], "ub": [10.0]})
        hb = pd.DataFrame({"Konto": ["1920", "8888"], "Beløp": [0.0, 500.0]})
        result = ib_ub_control.build_account_reconciliation(sb, hb)
        assert len(result) == 2
        only_hb = result.loc[result["konto"] == "8888"].iloc[0]
        assert only_hb["hb_sum"] == 500.0
        assert only_hb["sb_netto"] == 0.0
        assert only_hb["har_avvik"] == True  # noqa: E712


class TestBuildSummary:
    def test_summary_totals(self) -> None:
        sb = _make_sb()
        hb = _make_hb()
        recon = ib_ub_control.build_account_reconciliation(sb, hb)
        summary = ib_ub_control.build_summary(recon)

        assert summary["total_sb_ib"] == pytest.approx(100_000.0)
        assert summary["total_sb_ub"] == pytest.approx(0.0)  # 150k - 500k + 200k + 150k = 0
        assert summary["antall_kontoer"] == 4


class TestReconcile:
    def test_full_reconciliation(self) -> None:
        sb = _make_sb()
        hb = _make_hb()
        result = ib_ub_control.reconcile(sb, hb)

        assert isinstance(result, ib_ub_control.ReconciliationResult)
        assert len(result.account_level) == 4
        assert isinstance(result.summary, dict)
        assert result.rl_level is None  # ingen intervals/regnskapslinjer gitt

    def test_no_discrepancies_when_balanced(self) -> None:
        sb = _make_sb()
        hb = _make_hb()
        result = ib_ub_control.reconcile(sb, hb)
        assert len(result.discrepancies) == 0
