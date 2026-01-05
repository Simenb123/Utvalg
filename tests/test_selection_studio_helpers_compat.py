# tests/test_selection_studio_helpers_compat.py
import pandas as pd

from selection_studio_helpers import (
    PopulationMetrics,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    format_interval_no,
)


def test_format_interval_no_converts_to_norwegian_format():
    assert format_interval_no("(0.259, 255.998]") == "(0,26 – 256,00]"


def test_population_metrics_accepts_rows_kw():
    m = PopulationMetrics(rows=10, bilag=5, konto=3, sum_net=100.0, sum_abs=150.0)
    assert m.rows == 10
    assert m.bilag == 5
    assert m.konto == 3
    assert m.sum_net == 100.0
    assert m.sum_abs == 150.0


def test_population_metrics_accepts_legacy_kw():
    m = PopulationMetrics(n_rows=10, n_bilag=5, n_accounts=3, sum_net=100.0, sum_abs=150.0)
    assert m.rows == 10
    assert m.bilag == 5
    assert m.konto == 3


def test_compute_population_metrics_basic():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Konto": [6000, 6000, 6500],
            "Beløp": [100.0, -50.0, 30.0],
        }
    )
    m = compute_population_metrics(df)
    assert m.rows == 3
    assert m.bilag == 2
    assert m.konto == 2
    assert m.sum_net == 80.0
    assert m.sum_abs == 180.0


def test_build_source_text_distinguishes_subset_vs_full():
    df_all = pd.DataFrame(
        {
            "Bilag": [1, 2, 3, 4],
            "Konto": [6000, 6001, 6002, 6003],
            "Beløp": [1, 1, 1, 1],
        }
    )
    df_base = df_all.iloc[:2].copy()

    txt_subset = build_source_text(df_base, df_all)
    txt_full = build_source_text(df_all, df_all)

    assert "delmengde" in txt_subset.lower()
    assert "hele datasettet" in txt_full.lower()


def test_build_sample_summary_text_uses_unique_bilag_counts():
    sample_df = pd.DataFrame(
        {
            "Bilag": [10, 10, 20],
            "Beløp": [100.0, -25.0, 50.0],
            "Sum bilag (grunnlag)": [125.0, 125.0, 50.0],
            "Sum bilag (kontointervallet)": [75.0, 75.0, 50.0],
        }
    )
    txt = build_sample_summary_text(sample_df)
    assert "2 bilag" in txt
