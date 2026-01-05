# tests/test_selection_studio_helpers_regression.py
import pandas as pd

from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    format_interval_no,
)


def test_format_interval_no_converts_to_norwegian_format():
    assert format_interval_no("(0.259, 255.998]") == "(0,26 – 256,00]"


def test_compute_population_metrics_basic():
    df = pd.DataFrame(
        {"Bilag": [10, 10, 20], "Konto": [6000, 6001, 6000], "Beløp": [1.0, -2.0, 3.0]}
    )
    m = compute_population_metrics(df)
    assert m.rows == 3
    assert m.bilag == 2
    assert m.konto == 2
    assert m.sum_net == 2.0
    assert m.sum_abs == 6.0


def test_build_source_text_distinguishes_subset_vs_full():
    df_all = pd.DataFrame({"Bilag": [1, 2], "Konto": [6000, 6001], "Beløp": [1, 2]})
    df_sub = df_all[df_all["Konto"] == 6000]

    full_txt = build_source_text(df_all, df_all).lower()
    sub_txt = build_source_text(df_sub, df_all).lower()

    assert "hele datasettet" in full_txt
    assert "delmengde av datasett" in sub_txt


def test_build_population_summary_text_contains_core_fields():
    m = PopulationMetrics(rows=10, bilag=5, konto=3, sum_net=100.0, sum_abs=150.0)
    txt = build_population_summary_text(m, removed_rows=2, removed_bilag=1)
    assert "10 rader" in txt
    assert "5 bilag" in txt
    assert "3 kontoer" in txt


def test_build_sample_summary_text_uses_bilag_counts():
    df = pd.DataFrame({"Bilag": [10, 10, 20], "Beløp": [1, 2, 3]})
    txt = build_sample_summary_text(df)
    assert "2 bilag" in txt
