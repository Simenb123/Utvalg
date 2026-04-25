from __future__ import annotations

import pandas as pd

import src.pages.materiality.backend.engine as mod


def test_build_benchmark_amounts_from_rl_df_uses_key_regnskapslinjer() -> None:
    rl_df = pd.DataFrame(
        [
            {"regnr": 19, "UB": -8500000},
            {"regnr": 20, "UB": 2500000},
            {"regnr": 160, "UB": -1000000},
            {"regnr": 665, "UB": 10500000},
            {"regnr": 715, "UB": -4100000},
        ]
    )

    amounts = mod.build_benchmark_amounts_from_rl_df(rl_df)

    assert amounts["revenue"] == 8500000
    assert amounts["gross_profit"] == 6000000
    assert amounts["profit_before_tax"] == 1000000
    assert amounts["total_assets"] == 10500000
    assert amounts["equity"] == 4100000


def test_calculate_materiality_rounds_to_whole_kroner() -> None:
    calc = mod.calculate_materiality(
        "profit_before_tax",
        1000000,
        om_pct=7.5,
        pm_pct=75,
        trivial_pct=10,
    )

    assert calc.om == 75000
    assert calc.pm == 56250
    assert calc.trivial == 5625


def test_calculate_materiality_accepts_explicit_total_materiality_and_exposes_reference_range() -> None:
    calc = mod.calculate_materiality(
        "gross_profit",
        6000000,
        om_pct=2.25,
        pm_pct=75,
        trivial_pct=10,
        selected_om=175000,
    )

    assert calc.reference_pct_low == 1.5
    assert calc.reference_pct_high == 3.0
    assert calc.reference_amount_low == 90000
    assert calc.reference_amount_high == 180000
    assert calc.om == 175000
    assert calc.pm == 131250
    assert calc.trivial == 13125
