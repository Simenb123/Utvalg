import pandas as pd

from views_selection_studio import (
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
    df_all = pd.DataFrame({"Bilag": [1, 2, 3, 4], "Konto": [6000, 6001, 6002, 6003], "Beløp": [1, 1, 1, 1]})
    df_base = df_all.iloc[:2].copy()

    txt_subset = build_source_text(df_base, df_all)
    txt_full = build_source_text(df_all, df_all)

    assert "delmengde" in txt_subset.lower()
    assert "hele datasettet" in txt_full.lower()


def test_build_population_summary_text_contains_core_fields():
    base_m = PopulationMetrics(rows=10, bilag=5, konto=3, sum_net=100.0, sum_abs=150.0)
    work_m = PopulationMetrics(rows=8, bilag=4, konto=3, sum_net=80.0, sum_abs=120.0)

    txt_abs = build_population_summary_text(base_m, work_m, abs_basis=True)
    assert "Grunnlag:" in txt_abs
    assert "bilag" in txt_abs.lower()
    assert "Sum (abs):" in txt_abs
    assert "Netto:" in txt_abs

    txt_net = build_population_summary_text(base_m, work_m, abs_basis=False)
    assert "Sum (netto):" in txt_net
    assert "Abs:" in txt_net


def test_build_sample_summary_text_uses_bilag_counts():
    sample_df = pd.DataFrame(
        {
            "Bilag": [10, 10, 20],
            "Beløp": [100, -25, 50],
            "Sum bilag (grunnlag)": [125, 125, 50],
            "Sum bilag (kontointervallet)": [75, 75, 50],
        }
    )
    txt = build_sample_summary_text(sample_df)
    assert "Utvalg:" in txt
    assert "2 bilag" in txt
    assert "3 rader" in txt
    assert "Sum (filtrert grunnlag)" in txt
    assert "Sum (valgte kontoer)" in txt
