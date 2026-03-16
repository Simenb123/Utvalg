from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_apply_interval_mapping_and_aggregate_leaf_and_sum() -> None:
    from regnskap_mapping import apply_interval_mapping, aggregate_by_regnskapslinje

    intervals = pd.DataFrame(
        {
            "fra": [1000, 3000],
            "til": [1999, 3999],
            "regnr": [10, 11],
        }
    )

    tb = pd.DataFrame(
        {
            "konto": ["1000", "1500", "3000"],
            "ub": [100.0, 50.0, -200.0],
        }
    )

    mapped = apply_interval_mapping(tb, intervals)
    assert mapped.mapped["regnr"].tolist() == [10, 10, 11]
    assert mapped.unmapped_konto == []

    regn = pd.DataFrame(
        {
            "nr": [10, 11, 20],
            "regnskapslinje": ["Eiendeler", "Inntekter", "SUM"],
            "sumpost": ["nei", "nei", "ja"],
            "Formel": ["", "", "=10+11"],
        }
    )

    leaf = aggregate_by_regnskapslinje(mapped.mapped, regn, amount_col="ub", include_sum_lines=False)
    assert leaf["regnr"].tolist() == [10, 11]
    assert leaf.loc[leaf["regnr"] == 10, "belop"].iloc[0] == 150.0
    assert leaf.loc[leaf["regnr"] == 11, "belop"].iloc[0] == -200.0

    with_sum = aggregate_by_regnskapslinje(mapped.mapped, regn, amount_col="ub", include_sum_lines=True)
    assert set(with_sum["regnr"].tolist()) == {10, 11, 20}
    assert with_sum.loc[with_sum["regnr"] == 20, "belop"].iloc[0] == -50.0


def test_apply_interval_mapping_marks_unmapped() -> None:
    from regnskap_mapping import apply_interval_mapping

    intervals = pd.DataFrame({"fra": [1000], "til": [1999], "regnr": [10]})
    tb = pd.DataFrame({"konto": ["9999"], "ub": [1.0]})
    res = apply_interval_mapping(tb, intervals)
    assert res.unmapped_konto == ["9999"]
