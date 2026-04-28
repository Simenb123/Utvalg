"""Tester for HB versjonsdiff Excel-eksport."""

from __future__ import annotations

import pandas as pd
import pytest

import src.audit_actions.diff.hb_engine as hb_version_diff
import src.audit_actions.diff.hb_excel as hb_version_diff_excel


def _make_version_a() -> pd.DataFrame:
    return pd.DataFrame({
        "Bilag": ["B001", "B001", "B002", "B003", "B003"],
        "Konto": ["1920", "3000", "1920", "4000", "1920"],
        "Beløp": [100.0, -100.0, 500.0, 200.0, -200.0],
        "Tekst": ["Salg", "Salg", "Innbetaling", "Kjøp", "Kjøp"],
    })


def _make_version_b() -> pd.DataFrame:
    return pd.DataFrame({
        "Bilag": ["B001", "B001", "B003", "B003", "B004", "B004"],
        "Konto": ["1920", "3000", "4000", "1920", "6000", "1920"],
        "Beløp": [100.0, -100.0, 300.0, -300.0, 150.0, -150.0],
        "Tekst": ["Salg", "Salg", "Kjøp revidert", "Kjøp revidert", "Lønn", "Lønn"],
    })


def _get_diff():
    return hb_version_diff.diff_hb_versions(_make_version_a(), _make_version_b())


def test_workpaper_has_four_sheets() -> None:
    wb = hb_version_diff_excel.build_hb_diff_workpaper(_get_diff())
    assert set(wb.sheetnames) == {"Oppsummering", "Nye bilag", "Fjernede bilag", "Endrede bilag"}


def test_workpaper_with_client_and_year() -> None:
    wb = hb_version_diff_excel.build_hb_diff_workpaper(
        _get_diff(), client="TestKlient", year=2025,
    )
    ws = wb["Oppsummering"]
    assert "TestKlient" in ws["A1"].value
    assert "2025" in ws["A1"].value


def test_added_sheet_has_data() -> None:
    wb = hb_version_diff_excel.build_hb_diff_workpaper(_get_diff())
    ws = wb["Nye bilag"]
    # Header row is 4, data starts at 5
    assert ws.cell(row=5, column=1).value == "B004"


def test_removed_sheet_has_data() -> None:
    wb = hb_version_diff_excel.build_hb_diff_workpaper(_get_diff())
    ws = wb["Fjernede bilag"]
    assert ws.cell(row=5, column=1).value == "B002"


def test_changed_sheet_has_data() -> None:
    wb = hb_version_diff_excel.build_hb_diff_workpaper(_get_diff())
    ws = wb["Endrede bilag"]
    assert ws.cell(row=5, column=1).value == "B003"


def test_empty_diff_no_crash() -> None:
    df = _make_version_a()
    result = hb_version_diff.diff_hb_versions(df, df.copy())
    wb = hb_version_diff_excel.build_hb_diff_workpaper(result)
    assert "Oppsummering" in wb.sheetnames
    ws = wb["Endrede bilag"]
    assert "Ingen" in (ws.cell(row=5, column=1).value or "")
