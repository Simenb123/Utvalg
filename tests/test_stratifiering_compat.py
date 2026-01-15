import random

import pandas as pd

from stratifiering import sample_stratified, stratify_quantiles


def test_stratify_quantiles_returns_labels_aligned_to_index():
    df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3, 4, 5],
            "SumBeløp": [10, 20, 30, 40, 50],
        },
        index=["a", "b", "c", "d", "e"],
    )

    labels = stratify_quantiles(df, amount_column="SumBeløp", k=3, use_abs=True)

    assert isinstance(labels, pd.Series)
    assert labels.index.tolist() == df.index.tolist()
    assert labels.min() >= 1
    assert labels.max() <= 3


def test_sample_stratified_draws_exact_n_and_is_subset_of_population():
    df = pd.DataFrame(
        {
            "Bilag": list(range(1, 11)),
            "SumBeløp": [5, 7, 9, 10, 11, 20, 30, 40, 41, 42],
        }
    )
    strata = stratify_quantiles(df, amount_column="SumBeløp", k=2)

    rng = random.Random(123)
    sample = sample_stratified(df, strata, 4, rng=rng)

    assert len(sample) == 4
    assert set(sample.index).issubset(set(df.index))
    assert set(sample["Bilag"]).issubset(set(df["Bilag"]))


def test_sample_stratified_handles_small_n_less_than_groups():
    df = pd.DataFrame({"SumBeløp": [1, 2, 3, 4, 5, 6]})
    strata = stratify_quantiles(df, amount_column="SumBeløp", k=3)

    sample = sample_stratified(df, strata, 2, rng=random.Random(7))
    assert len(sample) == 2
