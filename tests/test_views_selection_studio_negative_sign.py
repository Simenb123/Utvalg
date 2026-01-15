import pandas as pd
import pytest

from views_selection_studio_ui import compute_specific_selection_recommendation


def test_compute_specific_selection_recommendation_handles_negative_net_population():
    # Kreditposter er ofte negative; i "nettobeløp"-modus (use_abs=False) må vi
    # fortsatt beregne utvalgsstørrelse basert på størrelsen (|beløp|).
    df = pd.DataFrame(
        {
            "Bilag": [1, 2, 3],
            "SumBeløp": [-1000.0, -2000.0, -3000.0],
        }
    )

    rec = compute_specific_selection_recommendation(
        df,
        tolerable_error=1000.0,
        confidence_factor=1.0,
        amount_col="SumBeløp",
        use_abs=False,
    )

    assert rec["ok"] is True
    assert rec["n_specific"] == 0
    assert rec["remaining_count"] == 3
    assert rec["remaining_value"] == pytest.approx(-6000.0)

    # abs(-6000)/1000 = 6 -> ceil(6) = 6, men vi kan ikke velge flere enn remaining_count
    assert rec["additional_n"] == 3
    assert rec["n_total_recommended"] == 3
