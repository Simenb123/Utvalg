import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple


def beregn_strata(df: pd.DataFrame, k: int, mode: str, abs_belop: bool):
    """
    Del bilagene i k grupper (quantile eller equal) basert på sum per bilag.

    Parametre
    ---------
    df : DataFrame
        Transaksjonsdata med minst kolonnen "Bilag" og "Beløp".
    k : int
        Ønsket antall grupper (minimum 2 – høyere tall justeres ned hvis
        datagrunnlaget ikke gir nok unike verdier).
    mode : {"quantile", "equal"}
        "quantile" – like store grupper etter antall bilag (så langt det går).
        "equal" – like brede intervaller i NOK.
    abs_belop : bool
        Hvis True brukes absoluttbeløp ved summering per bilag.

    Returnerer
    ----------
    summary : DataFrame
        Én rad per gruppe med antall bilag, sum, min, median og maks.
    bilag_df : DataFrame
        Én rad per bilag med sum og gruppekode (__grp__).
    interval_map : dict[int, str]
        Oppslag fra gruppe-id til tekstlig intervall ("(x, y]") for visning.
    """
    bel = pd.to_numeric(df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)

    # Summér per bilag: bruk absoluttbeløp hvis angitt
    if abs_belop:
        s_bilag = df.groupby("Bilag")[bel.name].apply(lambda x: x.abs().sum())
    else:
        s_bilag = df.groupby("Bilag")[bel.name].sum()

    # Dropp bilag uten gyldig nøkkel
    s_bilag = s_bilag[~s_bilag.index.isna()]

    # Minst 2 grupper
    k = max(2, int(k))

    if len(s_bilag) == 0:
        # Tomt grunnlag – returner tomme strukturer
        empty_summary = pd.DataFrame(
            columns=["Gruppe", "Antall_bilag", "SumBeløp", "Min_Beløp", "Median_Beløp", "Max_Beløp", "Intervall"]
        )
        empty_bilag_df = pd.DataFrame(columns=["Bilag", "SumBeløp", "__interval__", "__grp__"])
        return empty_summary, empty_bilag_df, {}

    # Quantile = like store grupper etter sum, equal = like store intervaller
    if mode == "equal":
        cats = pd.cut(s_bilag, bins=k, duplicates="drop")
    else:
        # Default til quantile hvis noe annet er oppgitt
        cats = pd.qcut(s_bilag, q=k, duplicates="drop")

    # Sorter intervaller og lag gruppekoder 1..n
    intervals = cats.cat.categories
    sorted_intervals = sorted(
        intervals,
        key=lambda iv: iv.left if hasattr(iv, "left") else float(str(iv).split(",")[0].strip("(["))
    )
    mapping = {iv: idx + 1 for idx, iv in enumerate(sorted_intervals)}

    bilag_df = pd.DataFrame({
        "Bilag": s_bilag.index.astype(object),
        "SumBeløp": s_bilag.values,
        "__interval__": cats
    })
    bilag_df["__grp__"] = bilag_df["__interval__"].map(mapping)

    # Bygg oppsummering per gruppe
    tmp = bilag_df.copy()
    summary = (
        tmp.groupby("__grp__", observed=True)["SumBeløp"]
        .agg(
            Antall_bilag="count",
            SumBeløp="sum",
            Min_Beløp="min",
            Median_Beløp="median",
            Max_Beløp="max",
        )
        .reset_index()
        .rename(columns={"__grp__": "Gruppe"})
    )

    interval_map = {mapping[iv]: str(iv) for iv in mapping}
    summary["Intervall"] = summary["Gruppe"].map(interval_map)
    summary = summary.sort_values("Gruppe").reset_index(drop=True)
    return summary, bilag_df, interval_map


def trekk_sample(
    bilag_df: pd.DataFrame,
    summary: pd.DataFrame,
    custom_counts: Optional[Dict[int, int]],
    n_per_group: int,
    total_n: int,
    auto_fordel: bool,
) -> List:
    """
    Trekk bilag fra hver gruppe basert på enten custom_counts, total_n eller n_per_group.

    Prioritet:
    1. Hvis custom_counts er gitt, brukes disse (klippes til maks tilgjengelig per gruppe).
    2. Ellers, hvis total_n > 0:
       - fordeles enten proporsjonalt (auto_fordel=True) eller jevnt (auto_fordel=False)
         mellom gruppene, men aldri flere enn det finnes totalt.
    3. Ellers brukes n_per_group som fast antall per gruppe.

    Funksjonen garanterer:
    - det trekkes aldri flere bilag enn det finnes totalt,
    - ingen bilag trekkes mer enn én gang,
    - ingen risiko for uendelige løkker ved "over-bestilling".
    """
    tmp = bilag_df.copy()
    if tmp.empty or summary.empty:
        return []

    # Antall tilgjengelige bilag per gruppe (kapasitet)
    bilags_per_group: Dict[int, int] = tmp.groupby("__grp__").size().to_dict()
    group_counts: Dict[int, int] = {}
    k_actual = len(summary)

    if k_actual == 0:
        return []

    # 1. Egendefinerte antall per gruppe
    if custom_counts:
        for grp, cnt in custom_counts.items():
            max_count = bilags_per_group.get(grp, 0)
            group_counts[grp] = max(0, min(int(cnt), max_count))

    # 2. Total_n: fordel jevnt eller etter sumandel
    elif total_n > 0:
        # Klipp total_n til maks tilgjengelig for å unngå uendelige løkker
        max_available = int(sum(bilags_per_group.values()))
        total_n = max(0, min(int(total_n), max_available))

        if total_n == 0:
            group_counts = {int(row["Gruppe"]): 0 for _, row in summary.iterrows()}
        else:
            # Hjelpestruktur for kapasitet
            capacities: Dict[int, int] = {
                int(row["Gruppe"]): bilags_per_group.get(int(row["Gruppe"]), 0)
                for _, row in summary.iterrows()
            }

            def _adjust_counts_to_total(
                provisional: Dict[int, int],
                target_total: int,
                order: List[int],
                caps: Dict[int, int],
            ) -> Dict[int, int]:
                """
                Juster foreløpige group_counts slik at summen blir target_total.

                Øker eller reduserer med 1 per steg i oppgitt rekkefølge, uten å
                overskride kapasitet eller gå under 0.
                """
                current = sum(provisional.values())
                diff = int(target_total - current)

                if diff == 0:
                    return provisional

                # Vi endrer bare i riktig retning, diff beveger seg monotont mot 0
                while diff != 0:
                    changed = False
                    for g in order:
                        if diff > 0:
                            if provisional.get(g, 0) < caps.get(g, 0):
                                provisional[g] = provisional.get(g, 0) + 1
                                diff -= 1
                                changed = True
                        elif diff < 0:
                            if provisional.get(g, 0) > 0:
                                provisional[g] = provisional.get(g, 0) - 1
                                diff += 1
                                changed = True

                        if diff == 0:
                            break

                    if not changed:
                        # Kan ikke justere mer (burde ikke skje når target_total <= sum(capacities))
                        break
                return provisional

            total_sum = float(abs(summary["SumBeløp"]).sum())

            if auto_fordel and total_sum > 0.0:
                # Proposjonal fordeling etter sumandel
                provisional: Dict[int, int] = {}
                fracs: Dict[int, float] = {}

                for _, row in summary.iterrows():
                    g = int(row["Gruppe"])
                    share = float(abs(row["SumBeløp"])) / total_sum
                    fracs[g] = share
                    n_grp = int(round(total_n * share))
                    provisional[g] = min(n_grp, capacities.get(g, 0))

                order_inc = sorted(fracs, key=fracs.get)          # for reduksjon
                order_dec = sorted(fracs, key=fracs.get, reverse=True)  # for økning

                # Juster opp/ned til vi treffer total_n
                current_total = sum(provisional.values())
                if current_total < total_n:
                    group_counts = _adjust_counts_to_total(provisional, total_n, order_dec, capacities)
                elif current_total > total_n:
                    group_counts = _adjust_counts_to_total(provisional, total_n, order_inc, capacities)
                else:
                    group_counts = provisional

            else:
                # Jevn fordeling når auto_fordel=False eller total_sum == 0
                groups: List[int] = [int(row["Gruppe"]) for _, row in summary.iterrows()]

                base = int(total_n // k_actual)
                provisional: Dict[int, int] = {}

                for g in groups:
                    provisional[g] = min(base, capacities.get(g, 0))

                # Rest (pga. avrunding) fordeles i grupperekkefølge
                group_counts = _adjust_counts_to_total(provisional, total_n, groups, capacities)

    # 3. Fast antall per gruppe
    else:
        n_per = max(0, int(n_per_group))
        for _, row in summary.iterrows():
            g = int(row["Gruppe"])
            max_count = bilags_per_group.get(g, 0)
            group_counts[g] = min(n_per, max_count)

    # Trekk bilag fra hver gruppe
    rng = np.random.default_rng()
    selected: List = []

    for grp, n in group_counts.items():
        if n <= 0:
            continue
        bilags = tmp.loc[tmp["__grp__"] == grp, "Bilag"].tolist()

        if n >= len(bilags):
            # Ta alle bilag i gruppen
            selected.extend(bilags)
        else:
            # Tilfeldig utvalg uten erstatning
            chosen = rng.choice(bilags, size=int(n), replace=False).tolist()
            selected.extend(chosen)

    return selected


def summer_per_bilag(
    df_base: pd.DataFrame,
    df_all: Optional[pd.DataFrame],
    bilag_list: List,
) -> pd.DataFrame:
    """
    Returner en DataFrame med summer per bilag.

    Kolonner
    --------
    Bilag
    Sum bilag (kontointervallet)
        Netto sum av bilag i df_base.
    Sum rader (kontointervallet)
        Absolutt sum av alle rader i df_base (alle linjer for bilaget).
    Sum bilag (alle kontoer)
        Netto sum av bilag i df_all (hvis df_all gis), ellers 0.0.
    """
    out = pd.DataFrame({"Bilag": bilag_list})

    bel_base = pd.to_numeric(df_base.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
    sum_bilag_int = df_base.groupby("Bilag")[bel_base.name].sum()
    sum_rows_int = df_base.groupby("Bilag")[bel_base.name].apply(lambda x: x.abs().sum())

    out["Sum bilag (kontointervallet)"] = out["Bilag"].map(sum_bilag_int).fillna(0.0)
    out["Sum rader (kontointervallet)"] = out["Bilag"].map(sum_rows_int).fillna(0.0)

    if df_all is not None:
        bel_all = pd.to_numeric(df_all.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
        sum_bilag_all = df_all.groupby("Bilag")[bel_all.name].sum()
        out["Sum bilag (alle kontoer)"] = out["Bilag"].map(sum_bilag_all).fillna(0.0)
    else:
        out["Sum bilag (alle kontoer)"] = 0.0

    return out
