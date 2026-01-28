# -*- coding: utf-8 -*-
from __future__ import annotations

import warnings

import pandas as pd

from page_analyse import AnalysePage
import analyse_viewdata as av


class _DummyVar:
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value


def test_prepare_transactions_export_sheets_no_futurewarning_and_cleans_kunder() -> None:
    # Mixed customer columns + mixed date formats (norsk + ISO)
    df = pd.DataFrame(
        {
            "Bilag": ["1", "2"],
            "Beløp": [100.0, -50.0],
            "Tekst": ["A", "B"],
            "Kundenavn": [" ACME ", "nan"],
            "Kunde": ["", "Contoso"],
            "Konto": ["3000", "1920"],
            "Kontonavn": ["Salg", "Bank"],
            "Dato": ["01.01.2026", "2026-01-02"],
        }
    )

    p = AnalysePage.__new__(AnalysePage)
    p._df_filtered = df
    p._var_max_rows = _DummyVar(200)
    p._get_selected_accounts = lambda: ["3000", "1920"]

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sheets = AnalysePage._prepare_transactions_export_sheets(p)

    assert sheets, "Skal få eksport-ark"
    assert not any(isinstance(x.message, FutureWarning) for x in w), "Skal ikke gi FutureWarning"

    # Kan være 1 eller 2 ark avhengig av max_rows; plukk ett
    out_df = next(iter(sheets.values()))
    assert "Kunder" in out_df.columns
    assert out_df.loc[0, "Kunder"] == "ACME"
    assert out_df.loc[1, "Kunder"] == "Contoso"

    # Dato skal være norsk format
    assert out_df.loc[0, "Dato"] == "01.01.2026"
    assert out_df.loc[1, "Dato"] == "02.01.2026"


def test_prepare_pivot_export_sheets_uses_last_pivot_if_present() -> None:
    p = AnalysePage.__new__(AnalysePage)
    p._df_filtered = pd.DataFrame({"Konto": ["3000"], "Beløp": [1.0]})
    p._pivot_df_last = pd.DataFrame({"Konto": ["3000"], "Kontonavn": ["Salg"], "Sum beløp": [1.0], "Antall bilag": [1]})

    sheets = AnalysePage._prepare_pivot_export_sheets(p)

    assert list(sheets.keys()) == [av.SHEET_PIVOT]
    assert sheets[av.SHEET_PIVOT].loc[0, "Konto"] == "3000"
