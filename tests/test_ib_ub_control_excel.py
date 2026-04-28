"""Tester for IB/UB-kontroll Excel-arbeidspapir."""

from __future__ import annotations

import pandas as pd

import src.audit_actions.diff.ib_ub_engine as ib_ub_control
import src.audit_actions.diff.ib_ub_excel as ib_ub_control_excel


def _make_sb() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["1920", "3000", "4000"],
        "kontonavn": ["Bankinnskudd", "Salgsinntekter", "Varekostnad"],
        "ib": [100_000.0, 0.0, 0.0],
        "ub": [150_000.0, -500_000.0, 200_000.0],
    })


def _make_hb() -> pd.DataFrame:
    return pd.DataFrame({
        "Konto": ["1920", "1920", "3000", "4000"],
        "Beløp": [60_000.0, -10_000.0, -500_000.0, 200_000.0],
    })


def test_workpaper_has_expected_sheets() -> None:
    sb = _make_sb()
    hb = _make_hb()
    result = ib_ub_control.reconcile(sb, hb)

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        result.account_level,
        summary=result.summary,
        client="Test AS",
        year="2025",
    )

    assert "Oppsummering" in wb.sheetnames
    assert "Avstemming pr konto" in wb.sheetnames
    assert "Avvik" in wb.sheetnames


def test_workpaper_oppsummering_has_title() -> None:
    sb = _make_sb()
    hb = _make_hb()
    result = ib_ub_control.reconcile(sb, hb)

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        result.account_level,
        summary=result.summary,
        client="Test AS",
        year="2025",
    )
    ws = wb["Oppsummering"]
    assert "Test AS" in str(ws["A1"].value)


def test_workpaper_data_rows_match_account_count() -> None:
    sb = _make_sb()
    hb = _make_hb()
    result = ib_ub_control.reconcile(sb, hb)

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        result.account_level,
        summary=result.summary,
    )
    ws = wb["Avstemming pr konto"]
    # Header er rad 4, data starter rad 5
    data_rows = [r for r in ws.iter_rows(min_row=5) if r[0].value is not None]
    assert len(data_rows) == 3


def test_workpaper_avvik_sheet_empty_when_balanced() -> None:
    sb = _make_sb()
    hb = _make_hb()
    result = ib_ub_control.reconcile(sb, hb)

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        result.account_level,
        summary=result.summary,
    )
    ws = wb["Avvik"]
    # Skal vise "Ingen avvik funnet" når alt stemmer
    assert "Ingen avvik" in str(ws["A5"].value)


def test_workpaper_avvik_sheet_populated_with_discrepancies() -> None:
    sb = pd.DataFrame({
        "konto": ["1920", "3000"],
        "kontonavn": ["Bank", "Salg"],
        "ib": [0.0, 0.0],
        "ub": [200.0, -500.0],
    })
    hb = pd.DataFrame({
        "Konto": ["1920", "3000"],
        "Beløp": [100.0, -400.0],  # Begge har avvik
    })
    result = ib_ub_control.reconcile(sb, hb)

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        result.account_level,
        summary=result.summary,
    )
    ws = wb["Avvik"]
    data_rows = [r for r in ws.iter_rows(min_row=5) if r[0].value is not None]
    assert len(data_rows) == 2


def test_workpaper_includes_rl_sheet_when_provided() -> None:
    rl_recon = pd.DataFrame({
        "regnr": [10, 20],
        "regnskapslinje": ["Salgsinntekt", "Varekostnad"],
        "sb_ib": [0.0, 0.0],
        "sb_ub": [-500.0, 200.0],
        "sb_netto": [-500.0, 200.0],
        "hb_sum": [-500.0, 200.0],
        "differanse": [0.0, 0.0],
        "har_avvik": [False, False],
    })
    account_recon = pd.DataFrame({
        "konto": ["3000"],
        "kontonavn": ["Salg"],
        "sb_ib": [0.0],
        "sb_ub": [-500.0],
        "sb_netto": [-500.0],
        "hb_sum": [-500.0],
        "differanse": [0.0],
        "har_avvik": [False],
    })

    wb = ib_ub_control_excel.build_ib_ub_workpaper(
        account_recon,
        rl_recon=rl_recon,
        summary={"total_sb_ib": 0, "total_sb_ub": -300, "total_sb_netto": -300,
                 "total_hb_sum": -300, "total_differanse": 0, "antall_kontoer": 1, "antall_avvik": 0},
    )
    assert "Avstemming pr RL" in wb.sheetnames
