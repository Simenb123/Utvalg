from __future__ import annotations

import pandas as pd

from page_analyse import AnalysePage


def test_get_all_tx_columns_uses_active_dataset_when_filtered_missing() -> None:
    page = AnalysePage.__new__(AnalysePage)
    page._df_filtered = None
    page.dataset = pd.DataFrame(
        {
            "Konto": ["1000"],
            "Bilag": ["1"],
            "Egendefinert": ["X"],
        }
    )
    page._tx_cols_order = ["Konto", "Bilag"]

    cols = AnalysePage._get_all_tx_columns_for_chooser(page)

    assert "Egendefinert" in cols


def test_get_all_tx_columns_dedupes_alias_columns_to_canonical_names() -> None:
    page = AnalysePage.__new__(AnalysePage)
    page._df_filtered = None
    page.dataset = pd.DataFrame(
        {
            "Konto": ["1000"],
            "konto": ["1000"],
            "CustomerName": ["ACME"],
            "mva-kode": ["3"],
        }
    )
    page._tx_cols_order = ["Konto", "konto", "customername"]

    cols = AnalysePage._get_all_tx_columns_for_chooser(page)

    assert "Konto" in cols
    assert "Kundenavn" in cols
    assert "MVA-kode" in cols
    assert "konto" not in cols
    assert "CustomerName" not in cols
    assert "mva-kode" not in cols
