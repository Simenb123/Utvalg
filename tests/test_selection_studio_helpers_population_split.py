import pandas as pd

from selection_studio_helpers import (
    build_bilag_split_summary_text,
    compute_bilag_split_summary,
    compute_population_metrics,
)


def test_compute_population_metrics_accepts_abs_basis_kwarg():
    df = pd.DataFrame({"Bilag": [1, 1, 2], "Beløp": [100.0, -20.0, 50.0]})
    metrics = compute_population_metrics(df, abs_basis=True)  # should not raise

    assert metrics.row_count == 3
    assert metrics.bilag_count == 2
    assert metrics.sum_net == 130.0
    assert metrics.sum_abs == 170.0


def test_compute_population_metrics_uses_sum_belop_when_belop_missing():
    df = pd.DataFrame({"Bilag": [1, 2], "SumBeløp": [100.0, -20.0]})
    metrics = compute_population_metrics(df)

    assert metrics.row_count == 2
    assert metrics.bilag_count == 2
    assert metrics.sum_net == 80.0
    assert metrics.sum_abs == 120.0


def test_compute_bilag_split_summary_counts_and_values_use_remaining_population():
    bilag_df = pd.DataFrame(
        {"Bilag": [1, 2, 3], "SumBeløp": [2_000_000.0, 500_000.0, 400_000.0]}
    )

    split = compute_bilag_split_summary(
        bilag_df, tolerable_error=1_000_000, use_abs=True
    )

    assert split["population"].n_bilag == 3
    assert split["specific"].n_bilag == 1
    assert split["remaining"].n_bilag == 2

    assert split["population"].book_value == 2_900_000.0
    assert split["specific"].book_value == 2_000_000.0
    assert split["remaining"].book_value == 900_000.0


def test_build_bilag_split_summary_text_contains_sections_and_values():
    bilag_df = pd.DataFrame(
        {"Bilag": [1, 2, 3], "SumBeløp": [2_000_000.0, 500_000.0, 400_000.0]}
    )
    split = compute_bilag_split_summary(
        bilag_df, tolerable_error=1_000_000, use_abs=True
    )

    text = build_bilag_split_summary_text(split, decimals=0)

    assert "Populasjon:" in text
    assert "Spesifikk:" in text
    assert "Restpopulasjon:" in text
    assert "2 000 000" in text
    assert "900 000" in text
