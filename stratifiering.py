import numpy as np
import pandas as pd

def beregn_strata(df: pd.DataFrame, k: int, mode: str, abs_belop: bool):
    """
    Del bilagene i k grupper (quantile eller equal) basert på sum per bilag.
    """
    bel = pd.to_numeric(df.get("Beløp", pd.Series(dtype="float64")), errors="coerce").fillna(0.0)
    # Summér per bilag: bruk absoluttbeløp hvis angitt
    if abs_belop:
        s_bilag = df.groupby("Bilag")[bel.name].apply(lambda x: x.abs().sum())
    else:
        s_bilag = df.groupby("Bilag")[bel.name].sum()
    s_bilag = s_bilag[~s_bilag.index.isna()]
    k = max(2, int(k))
    # Quantile = like store grupper etter sum, equal = like store intervaller
    cats = (
        pd.cut(s_bilag, bins=k, duplicates="drop")
        if mode == "equal"
        else pd.qcut(s_bilag, q=k, duplicates="drop")
    )
    intervals = cats.cat.categories
    sorted_intervals = sorted(
        intervals,
        key=lambda iv: iv.left if hasattr(iv, "left")
        else float(str(iv).split(",")[0].strip("(["))
    )
    mapping = {iv: idx + 1 for idx, iv in enumerate(sorted_intervals)}
    bilag_df = pd.DataFrame({
        "Bilag": s_bilag.index.astype(object),
        "SumBeløp": s_bilag.values,
        "__interval__": cats
    })
    bilag_df["__grp__"] = bilag_df["__interval__"].map(mapping)
    tmp = bilag_df.copy()
    summary = tmp.groupby("__grp__", observed=True)["SumBeløp"].agg(
        Antall_bilag="count",
        SumBeløp="sum",
        Min_Beløp="min",
        Median_Beløp="median",
        Max_Beløp="max"
    ).reset_index().rename(columns={"__grp__": "Gruppe"})
    interval_map = {mapping[iv]: str(iv) for iv in mapping}
    summary["Intervall"] = summary["Gruppe"].map(interval_map)
    summary = summary.sort_values("Gruppe").reset_index(drop=True)
    return summary, bilag_df, interval_map

def trekk_sample(
    bilag_df: pd.DataFrame,
    summary: pd.DataFrame,
    custom_counts: dict[int, int] | None,
    n_per_group: int,
    total_n: int,
    auto_fordel: bool
) -> list:
    """
    Trekk bilag fra hver gruppe basert på enten custom_counts, total_n eller n_per_group.
    """
    tmp = bilag_df.copy()
    bilags_per_group = tmp.groupby("__grp__").size().to_dict()
    group_counts = {}
    k_actual = len(summary)
    # 1. Bruk spesifiserte antall hvis angitt
    if custom_counts:
        for grp, cnt in custom_counts.items():
            group_counts[grp] = max(0, min(cnt, bilags_per_group.get(grp, 0)))
    # 2. Total_n: fordel jevnt eller etter sumandel
    elif total_n > 0:
        if auto_fordel and total_n > 0:
            total_sum = abs(summary["SumBeløp"]).sum()
            provisional = {}
            if total_sum == 0:
                # Jevn fordeling når total_sum=0
                for _, row in summary.iterrows():
                    g = int(row["Gruppe"])
                    provisional[g] = min(
                        int(total_n / k_actual + 0.5),
                        bilags_per_group.get(g, 0)
                    )
            else:
                # Proportional fordeling
                for _, row in summary.iterrows():
                    g = int(row["Gruppe"])
                    share = abs(row["SumBeløp"]) / total_sum
                    n_grp = int(round(total_n * share))
                    provisional[g] = min(n_grp, bilags_per_group.get(g, 0))
            # Juster rest eller underskudd
            diff = total_n - sum(provisional.values())
            if diff != 0:
                fracs = {
                    int(row["Gruppe"]): abs(row["SumBeløp"]) / total_sum if total_sum else 0
                    for _, row in summary.iterrows()
                }
                order = sorted(fracs, key=fracs.get, reverse=(diff > 0))
                idx = 0
                while diff != 0 and idx < len(order):
                    g = order[idx]
                    max_count = bilags_per_group.get(g, 0)
                    if diff > 0 and provisional[g] < max_count:
                        provisional[g] += 1; diff -= 1
                    elif diff < 0 and provisional[g] > 0:
                        provisional[g] -= 1; diff += 1
                    idx = (idx + 1) % len(order)
            group_counts = provisional
        else:
            # Jevnt antall per gruppe
            n_per = int(total_n / k_actual + 0.5) if k_actual > 0 else 0
            for _, row in summary.iterrows():
                g = int(row["Gruppe"])
                group_counts[g] = min(n_per, bilags_per_group.get(g, 0))
            remainder = total_n - sum(group_counts.values())
            if remainder > 0:
                idx = 0
                groups = [int(row["Gruppe"]) for _, row in summary.iterrows()]
                while remainder > 0 and idx < len(groups):
                    g = groups[idx]
                    max_count = bilags_per_group.get(g, 0)
                    if group_counts[g] < max_count:
                        group_counts[g] += 1; remainder -= 1
                    idx = (idx + 1) % len(groups)
    # 3. Fast antall per gruppe
    else:
        n_per = max(0, int(n_per_group))
        for _, row in summary.iterrows():
            g = int(row["Gruppe"])
            group_counts[g] = min(n_per, bilags_per_group.get(g, 0))
    # Trekk bilag fra hver gruppe
    rng = np.random.default_rng()
    selected = []
    for grp, n in group_counts.items():
        if n <= 0:
            continue
        bilags = tmp.loc[tmp["__grp__"] == grp, "Bilag"].tolist()
        if n >= len(bilags):
            selected.extend(bilags)
        else:
            selected.extend(rng.choice(bilags, size=n, replace=False).tolist())
    return selected

def summer_per_bilag(
    df_base: pd.DataFrame,
    df_all: pd.DataFrame | None,
    bilag_list: list
) -> pd.DataFrame:
    """
    Returner en DataFrame med summer per bilag:
    - Sum bilag (kontointervallet): netto sum av bilag i df_base.
    - Sum rader (kontointervallet): absolutt sum av alle rader i df_base.
    - Sum bilag (alle kontoer): netto sum av bilag i df_all (hvis df_all gis).
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
