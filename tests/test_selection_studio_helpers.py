import pandas as pd

from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    format_interval_no,
    suggest_sample_size,
)


def test_format_interval_no_parses_string():
    assert format_interval_no("(0.259, 255.998]") == "(0,26 – 256,00]"


def test_compute_population_metrics_basic():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Konto": [6000, 6000, 6500],
            "Beløp": [100, -50, 30],
        }
    )
    m = compute_population_metrics(df)
    assert m.rows == 3
    assert m.bilag == 2
    assert m.konto == 2
    assert m.sum_net == 80
    assert m.sum_abs == 180


def test_build_source_text_with_accounts():
    df = pd.DataFrame({"Konto": [6200, 7791, 7000]})
    txt = build_source_text(df)
    assert "Kilde:" in txt
    assert "Kontoer:" in txt
    assert "(6200-7791)" in txt


def test_population_summary_text_contains_core_fields():
    m = PopulationMetrics(rows=10, bilag=5, konto=3, sum_net=100.0, sum_abs=150.0)
    txt = build_population_summary_text(m, removed_rows=2, removed_bilag=1)
    assert "10" in txt and "rader" in txt
    assert "5" in txt and "bilag" in txt
    assert "3" in txt and "konto" in txt
    assert "Sum (abs)" in txt
    assert "Netto" in txt


def test_build_sample_summary_text_counts_unique_bilag():
    df = pd.DataFrame(
        {
            "Bilag": [10, 10, 20],
            "Sum bilag (grunnlag)": [125, 125, 50],
            "Sum bilag (kontointervallet)": [75, 75, 50],
        }
    )
    txt = build_sample_summary_text(df)
    assert "2 bilag" in txt
    assert "Sum bilag (grunnlag)" in txt
    assert "Sum bilag (kontointervallet)" in txt


def test_suggest_sample_size_never_exceeds_population():
    n = suggest_sample_size(10, risk_factor=5, assurance="95%")
    assert 1 <= n <= 10
