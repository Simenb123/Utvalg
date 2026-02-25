import numpy as np
import pandas as pd


import analyse_viewdata


def test_normalize_konto_series_handles_common_cases_object() -> None:
    s = pd.Series(["1002.0", " 1003 ", None, "", "1004.10", "-1005.0", np.nan])
    out = analyse_viewdata.normalize_konto_series(s).tolist()
    assert out == ["1002", "1003", "", "", "1004.10", "-1005", ""]


def test_normalize_konto_series_handles_numeric_dtype() -> None:
    s = pd.Series([1002.0, 1003.0, np.nan, 1004.25])
    out = analyse_viewdata.normalize_konto_series(s).tolist()
    assert out == ["1002", "1003", "", "1004.25"]


def test_compute_selected_transactions_caches_normalized_konto_column() -> None:
    df = pd.DataFrame(
        {
            "Konto": [1000.0, "1000.0", "1001", " 1002 ", None],
            "Beløp": [1, 2, 3, 4, 5],
        }
    )

    df_all, df_show = analyse_viewdata.compute_selected_transactions(df, ["1000"], max_rows=1)
    assert "_KONTO_NORM" in df.columns
    assert len(df_all) == 2
    assert len(df_show) == 1

    # Second call should still work (and reuse cached column best-effort)
    df_all2, df_show2 = analyse_viewdata.compute_selected_transactions(df, ["1002"], max_rows=10)
    assert len(df_all2) == 1
    assert len(df_show2) == 1
