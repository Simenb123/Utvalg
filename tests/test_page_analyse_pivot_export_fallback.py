# -*- coding: utf-8 -*-
from __future__ import annotations

import pandas as pd

import analyse_viewdata as av
from page_analyse import AnalysePage


def test_prepare_pivot_export_sheets_builds_from_filtered_when_no_cache() -> None:
    """Happy path: når _pivot_df_last mangler, bygg pivot fra _df_filtered."""

    p = AnalysePage.__new__(AnalysePage)
    p._df_filtered = pd.DataFrame(
        {
            "Konto": ["3000", "3000"],
            "Kontonavn": ["Salg", "Salg"],
            "Bilag": ["1", "2"],
            "Beløp": [100.0, -50.0],
        }
    )

    # Sikre at cache ikke er satt
    if hasattr(p, "_pivot_df_last"):
        delattr(p, "_pivot_df_last")

    sheets = AnalysePage._prepare_pivot_export_sheets(p)

    assert list(sheets.keys()) == [av.SHEET_PIVOT]
    out = sheets[av.SHEET_PIVOT]

    assert not out.empty
    assert out.loc[0, "Konto"] == "3000"
    assert "Sum beløp" in out.columns
    assert "Antall bilag" in out.columns


def test_prepare_pivot_export_sheets_returns_empty_when_no_data() -> None:
    """Typisk feil-/tomtilfelle: tomt datagrunnlag gir tom pivot."""

    p = AnalysePage.__new__(AnalysePage)
    p._df_filtered = pd.DataFrame()

    if hasattr(p, "_pivot_df_last"):
        delattr(p, "_pivot_df_last")

    sheets = AnalysePage._prepare_pivot_export_sheets(p)

    assert list(sheets.keys()) == [av.SHEET_PIVOT]
    out = sheets[av.SHEET_PIVOT]
    assert out.empty
