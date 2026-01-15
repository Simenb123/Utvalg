import pandas as pd

from selection_studio_helpers import (
    build_bilag_split_summary_text,
    compute_bilag_split_summary,
)


def test_compute_bilag_split_summary_splits_specific_and_remaining_abs():
    bilag_df = pd.DataFrame(
        {
            "SumBeløp": [100.0, 50.0, -200.0],
        }
    )

    split = compute_bilag_split_summary(bilag_df, tolerable_error=80.0, use_abs=True)

    assert split["population"].n_bilag == 3
    assert split["specific"].n_bilag == 2
    assert split["remaining"].n_bilag == 1

    # abs book values
    assert split["population"].book_value == 350.0
    assert split["specific"].book_value == 300.0
    assert split["remaining"].book_value == 50.0

    txt = build_bilag_split_summary_text(split)
    assert "Populasjon" in txt
    assert "Spesifikk" in txt
    assert "Restpopulasjon" in txt


def test_compute_bilag_split_summary_splits_specific_and_remaining_net():
    bilag_df = pd.DataFrame(
        {
            "SumBeløp": [100.0, 50.0, -200.0],
        }
    )

    split = compute_bilag_split_summary(bilag_df, tolerable_error=80.0, use_abs=False)

    # In net mode, only amounts >= 80 are considered specific (negative values are not).
    assert split["specific"].n_bilag == 1
    assert split["remaining"].n_bilag == 2
