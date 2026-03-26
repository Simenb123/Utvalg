from __future__ import annotations

import pandas as pd

from motpost.view_konto_filters import available_mva_codes, filter_bilag_details_by_mva


def _details_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Bilag": "1", "MVA-kode": "3", "MVA-prosent": "25", "MVA-beløp": 250.0},
            {"Bilag": "2", "MVA-kode": "", "MVA-prosent": "", "MVA-beløp": 0.0},
            {"Bilag": "3", "MVA-kode": "1", "MVA-prosent": "15", "MVA-beløp": 150.0},
            {"Bilag": "4", "MVA-kode": "3, 1", "MVA-prosent": "25, 15", "MVA-beløp": 400.0},
        ]
    )


def test_available_mva_codes_returns_actual_codes_from_details() -> None:
    assert available_mva_codes(_details_df()) == ["Alle", "1", "3"]


def test_filter_bilag_details_by_mva_can_filter_by_code() -> None:
    out = filter_bilag_details_by_mva(_details_df(), mva_code="3")
    assert list(out["Bilag"]) == ["1", "4"]


def test_filter_bilag_details_by_mva_can_show_only_rows_without_code() -> None:
    out = filter_bilag_details_by_mva(_details_df(), mode="Uten MVA-kode", expected_rate="25")
    assert list(out["Bilag"]) == ["2"]


def test_filter_bilag_details_by_mva_can_show_expected_rate_only() -> None:
    out = filter_bilag_details_by_mva(_details_df(), mode="Treffer forventet", expected_rate="25")
    assert list(out["Bilag"]) == ["1"]


def test_filter_bilag_details_by_mva_can_show_deviation_from_expected_rate() -> None:
    out = filter_bilag_details_by_mva(_details_df(), mode="Avvik fra forventet", expected_rate="25")
    assert list(out["Bilag"]) == ["2", "3", "4"]
    assert out["_mva_avvik"].tolist() == [True, True, True]
