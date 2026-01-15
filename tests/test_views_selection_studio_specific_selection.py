import pandas as pd


from views_selection_studio_ui import (
    compute_specific_selection_recommendation,
    split_specific_selection_by_tolerable_error,
)


def test_split_specific_selection_by_tolerable_error_use_abs():
    df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3, 4],
            "SumBeløp": [100_000, 200_000, -250_000, 199_999],
        }
    )

    specific, remaining = split_specific_selection_by_tolerable_error(
        df, tolerable_error=200_000, amount_col="SumBeløp", use_abs=True
    )

    assert set(specific["Bilag"]) == {2, 3}
    assert set(remaining["Bilag"]) == {1, 4}


def test_split_specific_selection_by_tolerable_error_signed():
    df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3],
            "SumBeløp": [250_000, -250_000, 199_999],
        }
    )

    specific, remaining = split_specific_selection_by_tolerable_error(
        df, tolerable_error=200_000, amount_col="SumBeløp", use_abs=False
    )

    assert set(specific["Bilag"]) == {1}
    assert set(remaining["Bilag"]) == {2, 3}


def test_compute_specific_selection_recommendation_keys_and_values():
    df = pd.DataFrame(
        {
            "Bilag": [10, 11, 12],
            "SumBeløp": [500_000, 50_000, -600_000],
        }
    )

    rec = compute_specific_selection_recommendation(df, tolerable_error=200_000)

    assert rec["tolerable_error"] == 200_000
    assert rec["n_specific"] == 2
    assert rec["n_remaining"] == 1
    assert rec["specific_book_value"] == 1_100_000
    assert rec["remaining_book_value"] == 50_000
