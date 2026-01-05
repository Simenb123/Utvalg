import pandas as pd
import pytest

from stratifiering import beregn_strata, stratify_bilag, trekk_sample, summer_per_bilag


def _make_df_for_strata():
    # Fire bilag, én linje per bilag
    data = [
        {"Bilag": "1", "Beløp": 100.0},
        {"Bilag": "2", "Beløp": 200.0},
        {"Bilag": "3", "Beløp": 300.0},
        {"Bilag": "4", "Beløp": 400.0},
    ]
    return pd.DataFrame(data)


def test_beregn_strata_quantile_two_groups():
    df = _make_df_for_strata()
    summary, bilag_df, interval_map = beregn_strata(df, k=2, mode="quantile", abs_belop=False)

    # Vi forventer 2 grupper og totalt 4 bilag
    assert summary["Gruppe"].nunique() == 2
    assert summary["Antall_bilag"].sum() == 4

    # Alle bilag fra input skal være med i bilag_df
    assert set(bilag_df["Bilag"]) == {"1", "2", "3", "4"}
    # interval_map skal ha én entry per faktisk gruppe
    assert set(interval_map.keys()) == set(summary["Gruppe"])


def test_stratify_bilag_er_alias_for_beregn_strata():
    """Nyere kode kan importere `stratify_bilag`.

    For å unngå store refaktoreringer (risiko) beholder vi `beregn_strata` og
    eksponerer et alias. Her verifiserer vi at resultatene er identiske.
    """

    df = _make_df_for_strata()
    summary1, bilag1, interval_map1 = beregn_strata(df, k=2, mode="quantile", abs_belop=False)
    summary2, bilag2, interval_map2 = stratify_bilag(df, k=2, method="quantile", abs_belop=False)

    # Samme grupper og bilag
    assert summary1["Gruppe"].tolist() == summary2["Gruppe"].tolist()
    assert set(bilag1["Bilag"].tolist()) == set(bilag2["Bilag"].tolist())
    assert interval_map1 == interval_map2


def test_beregn_strata_abs_belop_vs_netto():
    # Ett bilag med +100 og -100 skal gi 0 i netto, men 200 i absolutt
    df = pd.DataFrame(
        [
            {"Bilag": "A", "Beløp": 100.0},
            {"Bilag": "A", "Beløp": -100.0},
            {"Bilag": "B", "Beløp": 50.0},
        ]
    )

    summary_netto, bilag_netto, _ = beregn_strata(df, k=2, mode="equal", abs_belop=False)
    summary_abs, bilag_abs, _ = beregn_strata(df, k=2, mode="equal", abs_belop=True)

    # I netto-variant skal bilag A ha sum 0
    sum_A_netto = float(bilag_netto.loc[bilag_netto["Bilag"] == "A", "SumBeløp"].iloc[0])
    # I absolutt-variant skal bilag A ha sum 200
    sum_A_abs = float(bilag_abs.loc[bilag_abs["Bilag"] == "A", "SumBeløp"].iloc[0])

    assert sum_A_netto == pytest.approx(0.0)
    assert sum_A_abs == pytest.approx(200.0)

    # Sørg også for at begge summer faktisk er representert i summary
    assert summary_netto["SumBeløp"].sum() == pytest.approx(50.0)
    assert summary_abs["SumBeløp"].sum() == pytest.approx(250.0)


def _make_bilag_for_trekk():
    # Lag et bilagsgrunnlag med 2 grupper
    bilag_df = pd.DataFrame(
        {
            "Bilag": ["1", "2", "3", "4", "5"],
            "__grp__": [1, 1, 1, 2, 2],
        }
    )
    # Summer per gruppe er ikke viktig for selve trekkingen, men summary krever kolonnenavn
    summary = pd.DataFrame(
        {
            "Gruppe": [1, 2],
            "SumBeløp": [300.0, 200.0],
        }
    )
    return bilag_df, summary


def test_trekk_sample_custom_counts_respekterer_grenser():
    bilag_df, summary = _make_bilag_for_trekk()

    # Be om flere bilag enn det finnes i gruppe 2
    custom_counts = {1: 2, 2: 10}
    selected = trekk_sample(
        bilag_df=bilag_df,
        summary=summary,
        custom_counts=custom_counts,
        n_per_group=0,
        total_n=0,
        auto_fordel=False,
    )

    # Vi forventer maks tilgjengelige per gruppe: 2 i gruppe 2, 2 i gruppe 1
    assert len(selected) == 4
    assert set(selected).issubset(set(bilag_df["Bilag"]))


def test_trekk_sample_total_n_respekterer_total_og_grupper():
    bilag_df, summary = _make_bilag_for_trekk()

    total_n = 3
    selected = trekk_sample(
        bilag_df=bilag_df,
        summary=summary,
        custom_counts=None,
        n_per_group=0,
        total_n=total_n,
        auto_fordel=False,
    )

    # Antall trukket skal være lik total_n (så lenge total_n <= totalt tilgjengelig)
    assert len(selected) == total_n
    # Alle valgte bilag må finnes i grunnlaget
    assert set(selected).issubset(set(bilag_df["Bilag"]))


def test_trekk_sample_total_n_klippes_til_maks_tilgjengelig():
    bilag_df, summary = _make_bilag_for_trekk()
    max_available = len(bilag_df)

    # Be om flere bilag enn det som totalt finnes
    total_n = max_available + 10
    selected = trekk_sample(
        bilag_df=bilag_df,
        summary=summary,
        custom_counts=None,
        n_per_group=0,
        total_n=total_n,
        auto_fordel=True,
    )

    # Skal aldri trekke flere enn totalt tilgjengelig
    assert len(selected) == max_available
    # Og alle bilag i grunnlaget skal være med i utvalget
    assert set(selected) == set(bilag_df["Bilag"])


def test_summer_per_bilag_med_df_all():
    # Bilag 1 har to linjer i intervallet og én ekstra linje i df_all
    df_base = pd.DataFrame(
        [
            {"Bilag": "1", "Beløp": 100.0},
            {"Bilag": "1", "Beløp": -40.0},
            {"Bilag": "2", "Beløp": 200.0},
        ]
    )
    df_all = pd.DataFrame(
        [
            {"Bilag": "1", "Beløp": 100.0},
            {"Bilag": "1", "Beløp": -40.0},
            {"Bilag": "1", "Beløp": 10.0},
            {"Bilag": "2", "Beløp": 200.0},
        ]
    )

    bilag_list = ["1", "2"]
    result = summer_per_bilag(df_base=df_base, df_all=df_all, bilag_list=bilag_list)

    # Sum bilag (kontointervallet) er netto i df_base
    sums_int = dict(zip(result["Bilag"], result["Sum bilag (kontointervallet)"]))
    assert sums_int["1"] == pytest.approx(60.0)  # 100 - 40
    assert sums_int["2"] == pytest.approx(200.0)

    # Sum rader (kontointervallet) er absoluttverdier i df_base
    sums_rows = dict(zip(result["Bilag"], result["Sum rader (kontointervallet)"]))
    assert sums_rows["1"] == pytest.approx(140.0)  # 100 + 40
    assert sums_rows["2"] == pytest.approx(200.0)

    # Sum bilag (alle kontoer) inkluderer ekstralinjen i df_all
    sums_all = dict(zip(result["Bilag"], result["Sum bilag (alle kontoer)"]))
    assert sums_all["1"] == pytest.approx(70.0)  # 100 - 40 + 10
    assert sums_all["2"] == pytest.approx(200.0)
