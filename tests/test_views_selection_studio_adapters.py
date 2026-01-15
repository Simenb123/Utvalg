import pandas as pd

from views_selection_studio_ui import (
    build_bilag_dataframe,
    compute_specific_selection_recommendation,
    stratify_bilag_sums,
)


def test_build_bilag_dataframe_groups_and_sums_amounts() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [1, 1, 2],
            "Beløp": [100.0, -25.0, 10.0],
            "Dato": ["2024-01-01", "2024-01-01", "2024-01-02"],
            "Tekst": ["a", "a", "b"],
        }
    )

    out = build_bilag_dataframe(df)

    assert list(out.columns) == ["Bilag", "Dato", "Tekst", "SumBeløp"]
    assert out.loc[out["Bilag"] == 1, "SumBeløp"].iloc[0] == 75.0
    assert out.loc[out["Bilag"] == 2, "SumBeløp"].iloc[0] == 10.0


def test_compute_specific_selection_recommendation_series_confidence_factor() -> None:
    # A og C tas alltid med (>= tolerable error), og additional_n beregnes på resten.
    values = pd.Series([200.0, 50.0, 180.0], index=["A", "B", "C"])

    rec = compute_specific_selection_recommendation(
        bilag_values=values,
        tolerable_error=100.0,
        confidence_factor=1.6,
    )

    assert rec.specific_bilag == ["A", "C"]
    assert rec.specific_count == 2
    assert rec.remaining_count == 1
    assert rec.additional_n == 1
    assert rec.total_n == 3


def test_compute_specific_selection_recommendation_dataframe_returns_splits() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [10, 11, 12],
            "SumBeløp": [500_000, 50_000, -600_000],
        }
    )

    rec = compute_specific_selection_recommendation(df, tolerable_error=200_000)

    assert rec.specific_bilag == [10, 12]
    assert rec.specific_count == 2
    assert rec.remaining_count == 1
    assert rec["specific_book_value"] == 1_100_000
    assert rec["remaining_book_value"] == 50_000
    assert len(rec["specific_df"]) == 2
    assert len(rec["remaining_df"]) == 1


def test_stratify_bilag_sums_series_quantile_two_groups() -> None:
    s = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], index=list("ABCDEFGHIJ"))

    groups, interval_map, stats_df = stratify_bilag_sums(s, method="quantile", k=2)

    assert len(groups) == 2
    assert isinstance(interval_map, dict)
    assert {"Gruppe", "Antall", "Sum", "Min", "Max"}.issubset(stats_df.columns)


def test_stratify_bilag_sums_dataframe_adds_group_and_interval() -> None:
    df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3, 4],
            "SumBeløp": [100.0, -200.0, 300.0, -400.0],
        }
    )

    summary, bilag_out, interval_map = stratify_bilag_sums(df, method="quantile", k=2, use_abs=True)

    assert "Gruppe" in bilag_out.columns
    assert "Intervall" in bilag_out.columns
    assert {"Gruppe", "Antall", "Sum", "Min", "Max"}.issubset(summary.columns)
    assert isinstance(interval_map, dict)
