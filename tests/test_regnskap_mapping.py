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


def test_apply_account_overrides_overrides_regnr() -> None:
    from regnskap_mapping import apply_account_overrides

    mapped = pd.DataFrame(
        {
            "konto": ["1000", "9999"],
            "regnr": pd.Series([10, pd.NA], dtype="Int64"),
        }
    )

    out = apply_account_overrides(mapped, {"9999": 42}, konto_col="konto")

    assert out.loc[out["konto"] == "1000", "regnr"].iloc[0] == 10
    assert int(out.loc[out["konto"] == "9999", "regnr"].iloc[0]) == 42


def test_expand_regnskapslinje_selection_expands_sumlinjer() -> None:
    from regnskap_mapping import expand_regnskapslinje_selection

    regn = pd.DataFrame(
        {
            "nr": [10, 11, 20, 99],
            "regnskapslinje": ["Eiendeler", "Inntekter", "Resultat", "SUM"],
            "sumpost": ["nei", "nei", "ja", "ja"],
            "Formel": ["", "", "=10+11", "=20"],
        }
    )

    assert expand_regnskapslinje_selection(regnskapslinjer=regn, selected_regnr=[20]) == [10, 11]
    assert expand_regnskapslinje_selection(regnskapslinjer=regn, selected_regnr=[99]) == [10, 11]


def test_aggregate_and_expand_sumlinjer_support_hierarchy_columns_without_formula() -> None:
    from regnskap_mapping import apply_interval_mapping, aggregate_by_regnskapslinje, expand_regnskapslinje_selection

    intervals = pd.DataFrame(
        {
            "fra": [1000, 1500],
            "til": [1499, 1599],
            "regnr": [10, 15],
        }
    )
    tb = pd.DataFrame(
        {
            "konto": ["1000", "1500"],
            "ub": [100.0, 50.0],
        }
    )
    mapped = apply_interval_mapping(tb, intervals)

    regn = pd.DataFrame(
        {
            "nr": [10, 15, 19, 80],
            "regnskapslinje": ["Salgsinntekt", "Annen driftsinntekt", "Sum driftsinntekter", "Driftsresultat"],
            "sumpost": ["nei", "nei", "ja", "ja"],
            "sumnivå": [1, 1, 2, 3],
            "delsumnr": [19, 19, None, None],
            "sumnr": [80, 80, None, None],
            "Formel": ["", "", "", "=19"],
        }
    )

    with_sum = aggregate_by_regnskapslinje(mapped.mapped, regn, amount_col="ub", include_sum_lines=True)

    assert float(with_sum.loc[with_sum["regnr"] == 19, "belop"].iloc[0]) == 150.0
    assert float(with_sum.loc[with_sum["regnr"] == 80, "belop"].iloc[0]) == 150.0
    assert expand_regnskapslinje_selection(regnskapslinjer=regn, selected_regnr=[19]) == [10, 15]
    assert expand_regnskapslinje_selection(regnskapslinjer=regn, selected_regnr=[80]) == [10, 15]
