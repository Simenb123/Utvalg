import pandas as pd

from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    fmt_amount_no,
    fmt_int_no,
    format_amount_no,
    format_interval_no,
    parse_amount,
    suggest_sample_size,
)


def test_format_interval_no_converts_to_norwegian_format():
    assert format_interval_no("(0.259, 255.998]") == "(0,26 – 256,00]"


def test_parse_and_format_amount_no():
    assert parse_amount("1 234,50") == 1234.5
    assert parse_amount("1.234,50") == 1234.5
    assert parse_amount("1,234.50") == 1234.5
    assert parse_amount("(1 234,50)") == -1234.5
    assert parse_amount(10) == 10.0
    assert parse_amount(10.25) == 10.25
    assert parse_amount("") is None

    assert format_amount_no(1234.5) == "1 234,50"
    assert fmt_amount_no(1234.5) == "1 234,50"


def test_format_int_no():
    assert fmt_int_no(1234567) == "1 234 567"


def test_compute_population_metrics_basic():
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Konto": [6000, 6001, 6000],
            "Beløp": [100.0, -50.0, 25.0],
        }
    )

    m = compute_population_metrics(df)
    assert isinstance(m, PopulationMetrics)
    assert m.rows == 3
    assert m.bilag == 2
    assert m.konto == 2
    assert m.sum_net == 75.0
    assert m.sum_abs == 175.0


def test_build_source_text_distinguishes_subset_vs_full():
    df_all = pd.DataFrame({"Bilag": [1, 1, 2], "Konto": [6000, 6001, 6000], "Beløp": [1, 2, 3]})
    df_subset = df_all[df_all["Konto"] == 6000]

    assert "delmengde" in build_source_text(df_subset, df_all).lower()
    assert "hele datasettet" in build_source_text(df_all, df_all).lower()


def test_build_population_summary_contains_core_fields():
    txt = build_population_summary_text(PopulationMetrics(rows=10, bilag=5, konto=3, sum_net=100.0, sum_abs=150.0))
    assert "Grunnlag" in txt
    assert "rader" in txt
    assert "bilag" in txt
    assert "konto" in txt


def test_build_sample_summary_text_uses_bilag_counts_and_does_not_crash():
    sample = pd.DataFrame(
        {
            "Bilag": [10, 10, 20],
            "Konto": [6000, 6001, 6000],
            "Beløp": [100.0, -50.0, 25.0],
        }
    )

    txt = build_sample_summary_text(sample)
    assert "2" in txt  # 2 bilag
    assert "bilag" in txt.lower()


def test_suggest_sample_size_basic():
    # 1 000 000 / 100 000 = 10, faktor 1.6 => 16
    assert suggest_sample_size(1_000_000, 100_000, risk_level="middels", confidence_level="middels") == 16
