import pandas as pd

from views_selection_studio_ui import (
    compute_net_basis_recommendation,
    recommend_random_sample_size_net_basis,
)


def test_recommend_random_sample_size_net_basis_handles_negative_net_and_clamps():
    # Netto er negativ (typisk salgsinntekter), men beregningen bruker |netto|
    n = recommend_random_sample_size_net_basis(
        population_value_net=-1300.0,
        population_count=2,
        tolerable_error=1500.0,
        confidence_factor=1.6,
    )
    # (|netto|/tol)*cf = (1300/1500)*1.6 = 1.386.. => ceil = 2, clamp til 2 bilag
    assert n == 2


def test_recommend_random_sample_size_net_basis_returns_zero_when_no_basis():
    assert (
        recommend_random_sample_size_net_basis(
            population_value_net=0.0,
            population_count=10,
            tolerable_error=1000.0,
            confidence_factor=1.6,
        )
        == 0
    )
    assert (
        recommend_random_sample_size_net_basis(
            population_value_net=1000.0,
            population_count=10,
            tolerable_error=0.0,
            confidence_factor=1.6,
        )
        == 0
    )
    assert (
        recommend_random_sample_size_net_basis(
            population_value_net=1000.0,
            population_count=0,
            tolerable_error=1000.0,
            confidence_factor=1.6,
        )
        == 0
    )


def test_compute_net_basis_recommendation_specific_selection_uses_abs_and_remaining_uses_net():
    bilag_df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3],
            # Bilag 2 er kredit (negativt), og skal likevel tas i spesifikk pga |beløp| >= tol
            "SumBeløp": [1000.0, -2000.0, 300.0],
        }
    )

    rec = compute_net_basis_recommendation(
        bilag_df,
        tolerable_error=1500.0,
        confidence_factor=1.6,
        amount_col="SumBeløp",
    )

    assert rec["n_specific"] == 1  # bilag -2000
    assert rec["remaining_net"] == 1300.0  # 1000 + 300 (netto, signert)
    assert rec["n_random"] == 2  # ceil((1300/1500)*1.6) = 2, clamp til 2
    assert rec["n_total"] == 3  # 1 spesifikk + 2 tilfeldig
