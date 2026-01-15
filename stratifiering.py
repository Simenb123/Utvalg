import math
import random
from typing import Any, Optional

import pandas as pd


def beregn_strata(df: pd.DataFrame, k: int = 5, mode: str = "quantile", abs_belop: bool = False):
    """
    Lager strata på bilagsnivå.
    - Først aggregeres df til bilag_df med sum per bilag (netto eller absolutt).
    - Deretter deles bilag_df inn i k grupper etter sum.
      mode: "quantile" => like mange bilag i hver gruppe, "equal" => like beløpsintervaller.
    Returnerer:
      summary: DataFrame med gruppe-statistikk,
      bilag_df: DataFrame med Bilag, SumBeløp, __grp__,
      interval_map: dict gruppe -> interval string (kan brukes til visning)
    """
    if df is None or df.empty:
        summary = pd.DataFrame(
            columns=["Gruppe", "Antall_bilag", "SumBeløp", "Min_Beløp", "Median_Beløp", "Max_Beløp", "Intervall"]
        )
        bilag_df = pd.DataFrame(columns=["Bilag", "SumBeløp", "__grp__"])
        return summary, bilag_df, {}

    belop = df["Beløp"].abs() if abs_belop else df["Beløp"]
    bilag_df = df.groupby("Bilag", as_index=False).apply(lambda g: belop.loc[g.index].sum(), include_groups=False)
    bilag_df = bilag_df.rename(columns={None: "SumBeløp"})
    # groupby.apply gir ofte en DataFrame med index, vi vil ha vanlige kolonner
    if "Bilag" not in bilag_df.columns:
        bilag_df = bilag_df.reset_index()

    # Sikre riktige datatyper
    bilag_df["SumBeløp"] = pd.to_numeric(bilag_df["SumBeløp"], errors="coerce").fillna(0.0)

    if k < 1:
        k = 1
    k = min(k, len(bilag_df)) if len(bilag_df) > 0 else 1

    if mode == "quantile":
        # pd.qcut kan feile hvis mange like verdier; duplicates="drop" reduserer antall grupper
        try:
            bilag_df["__grp__"] = pd.qcut(bilag_df["SumBeløp"], q=k, labels=False, duplicates="drop") + 1
        except ValueError:
            # fallback: alt i én gruppe
            bilag_df["__grp__"] = 1
    else:
        # equal beløpsintervaller
        minv = bilag_df["SumBeløp"].min()
        maxv = bilag_df["SumBeløp"].max()
        if minv == maxv:
            bilag_df["__grp__"] = 1
        else:
            bins = pd.interval_range(start=minv, end=maxv, periods=k)
            # cut bruker bins (interval objects)
            bilag_df["__bin__"] = pd.cut(bilag_df["SumBeløp"], bins=bins, include_lowest=True)
            # map intervaller til 1..k
            mapping = {iv: i + 1 for i, iv in enumerate(sorted(bins))}
            bilag_df["__grp__"] = bilag_df["__bin__"].map(mapping).fillna(1).astype(int)
            bilag_df = bilag_df.drop(columns=["__bin__"])

    # summary pr gruppe
    grp = bilag_df.groupby("__grp__")["SumBeløp"]
    summary = grp.agg(
        Antall_bilag="count",
        SumBeløp="sum",
        Min_Beløp="min",
        Median_Beløp="median",
        Max_Beløp="max",
    ).reset_index().rename(columns={"__grp__": "Gruppe"})

    # Intervall per gruppe (for visning)
    # Vi lager en map: Gruppe -> "[min, max]" basert på faktiske min/max i gruppen
    interval_map = {}
    for _, r in summary.iterrows():
        g = int(r["Gruppe"])
        interval_map[g] = f"[{r['Min_Beløp']:.2f}, {r['Max_Beløp']:.2f}]"
    summary["Intervall"] = summary["Gruppe"].map(interval_map)
    summary = summary.sort_values("Gruppe").reset_index(drop=True)
    return summary, bilag_df, interval_map


def stratify_bilag(
    df: pd.DataFrame,
    k: int = 5,
    method: str = "quantile",
    abs_belop: bool = False,
):
    """Bakoverkompatibel alias for :func:`beregn_strata`.

    Repoet har både norsk og engelsk navngivning i omløp. Enkelte moduler/tester
    forventer `stratify_bilag`, mens den opprinnelige implementasjonen heter
    `beregn_strata`.

    Dette wrapper-kallet gjør at vi kan stabilisere API-et og få grønn pytest,
    uten store refaktor-endringer akkurat nå.
    """
    return beregn_strata(df=df, k=k, mode=method, abs_belop=abs_belop)


def trekk_sample(
    bilag_df: pd.DataFrame,
    summary: pd.DataFrame,
    custom_counts: dict[int, int] | None = None,
    n_per_group: int = 5,
    total_n: int = 0,
    auto_fordel: bool = False,
    seed: int = 42,
):
    """
    Trekker bilag fra bilag_df etter grupper.
    - Hvis custom_counts er satt, brukes det som eksakt antall per gruppe (klippes til tilgjengelige bilag).
    - Ellers:
        - Hvis total_n > 0:
            - auto_fordel=True => fordel total_n proporsjonalt etter SumBeløp
            - auto_fordel=False => trekk total_n jevnt over grupper
        - Hvis total_n == 0: trekk n_per_group per gruppe
    Returnerer liste med Bilag (strings) som er valgt.
    """
    if bilag_df is None or bilag_df.empty:
        return []

    rng = random.Random(seed)
    bilag_df = bilag_df.copy()
    bilag_df["__grp__"] = bilag_df["__grp__"].astype(int)

    # tilgjengelig per gruppe
    available = bilag_df.groupby("__grp__")["Bilag"].apply(list).to_dict()
    groups = sorted(available.keys())

    # bygg counts per gruppe
    counts = {g: 0 for g in groups}

    if custom_counts:
        for g in groups:
            counts[g] = int(custom_counts.get(g, 0))
    else:
        if total_n and total_n > 0:
            if auto_fordel:
                # fordel proporsjonalt etter SumBeløp
                # fall back til antall hvis SumBeløp mangler
                if "SumBeløp" in summary.columns:
                    grp_sum = summary.set_index("Gruppe")["SumBeløp"].to_dict()
                    total_sum = sum(float(grp_sum.get(g, 0.0)) for g in groups)
                    if total_sum <= 0:
                        # jevn fordeling hvis sum=0
                        per = max(1, total_n // max(1, len(groups)))
                        for g in groups:
                            counts[g] = per
                    else:
                        # initial tildeling
                        for g in groups:
                            frac = float(grp_sum.get(g, 0.0)) / total_sum
                            counts[g] = int(round(frac * total_n))
                else:
                    # fallback: jevnt
                    per = max(1, total_n // max(1, len(groups)))
                    for g in groups:
                        counts[g] = per

                # juster opp/ned så totalsum matcher total_n
                current = sum(counts.values())
                # hvis rounding ga avvik, juster fra største grupper
                if current != total_n and len(groups) > 0:
                    # ranger grupper etter sum (høyest først)
                    if "SumBeløp" in summary.columns:
                        grp_sum = summary.set_index("Gruppe")["SumBeløp"].to_dict()
                        order = sorted(groups, key=lambda g: float(grp_sum.get(g, 0.0)), reverse=True)
                    else:
                        order = list(groups)

                    while current < total_n:
                        for g in order:
                            counts[g] += 1
                            current += 1
                            if current >= total_n:
                                break
                    while current > total_n:
                        for g in order:
                            if counts[g] > 0:
                                counts[g] -= 1
                                current -= 1
                                if current <= total_n:
                                    break
            else:
                # jevn fordeling på grupper
                per = max(1, total_n // max(1, len(groups)))
                for g in groups:
                    counts[g] = per
                # fordel resten
                rest = total_n - sum(counts.values())
                i = 0
                while rest > 0 and len(groups) > 0:
                    counts[groups[i % len(groups)]] += 1
                    rest -= 1
                    i += 1
        else:
            # fast per gruppe
            for g in groups:
                counts[g] = int(n_per_group)

    # klipp counts til tilgjengelige
    for g in groups:
        counts[g] = min(counts[g], len(available[g]))

    # hvis total_n var større enn totalt tilgjengelig, returner alle
    total_available = sum(len(v) for v in available.values())
    if total_n and total_n > total_available:
        return [b for sub in available.values() for b in sub]

    # trekk tilfeldig per gruppe
    selected = []
    for g in groups:
        candidates = list(available[g])
        rng.shuffle(candidates)
        selected.extend(candidates[: counts[g]])

    # Hvis total_n er satt og vi likevel har fått litt for mange (pga klipping/fordeling), klipp globalt
    if total_n and len(selected) > total_n:
        rng.shuffle(selected)
        selected = selected[:total_n]

    return selected


def summer_per_bilag(df_base: pd.DataFrame, df_all: pd.DataFrame | None, bilag_list: list):
    """
    Lager oppsummeringstabell per bilag:
    - Sum bilag (kontointervallet): netto sum innenfor df_base (fra kontointervallet)
    - Sum rader (kontointervallet): sum av absoluttverdier innenfor df_base
    - Sum bilag (alle kontoer): netto sum innenfor df_all (hele dataset), hvis df_all gitt
    """
    if df_base is None or df_base.empty:
        return pd.DataFrame(
            columns=[
                "Bilag",
                "Sum bilag (kontointervallet)",
                "Sum rader (kontointervallet)",
                "Sum bilag (alle kontoer)",
            ]
        )

    base = df_base[df_base["Bilag"].isin(bilag_list)].copy()
    out = base.groupby("Bilag")["Beløp"].agg(
        **{
            "Sum bilag (kontointervallet)": "sum",
            "Sum rader (kontointervallet)": lambda s: s.abs().sum(),
        }
    ).reset_index()

    if df_all is not None and not df_all.empty:
        all_df = df_all[df_all["Bilag"].isin(bilag_list)].copy()
        all_sum = (
            all_df.groupby("Bilag")["Beløp"].sum().reset_index().rename(columns={"Beløp": "Sum bilag (alle kontoer)"})
        )
        out = out.merge(all_sum, on="Bilag", how="left")
    else:
        out["Sum bilag (alle kontoer)"] = out["Sum bilag (kontointervallet)"]

    # fyll NaN
    out["Sum bilag (alle kontoer)"] = out["Sum bilag (alle kontoer)"].fillna(out["Sum bilag (kontointervallet)"])
    return out


def stratify_quantiles(
    df: pd.DataFrame,
    *,
    amount_column: str = "SumBeløp",
    k: int = 5,
    use_abs: bool = True,
    amount_col: Optional[str] = None,
) -> pd.Series:
    """Lager kvantil-strata (1..k) for df. Returnerer Serie alignet til df.index."""

    if amount_col is not None:
        amount_column = amount_col

    if df is None or df.empty:
        return pd.Series(dtype=int)

    if amount_column not in df.columns:
        raise KeyError(f"Kolonne '{amount_column}' finnes ikke i DataFrame.")

    k = int(k) if k is not None else 1
    if k < 1:
        k = 1
    k = min(k, len(df)) if len(df) > 0 else 1

    values = pd.to_numeric(df[amount_column], errors="coerce").fillna(0.0)
    if use_abs:
        values = values.abs()

    # qcut kan feile ved mange duplikater. Rank(method="first") gjør serien strengt økende.
    ranked = values.rank(method="first")
    try:
        labels = pd.qcut(ranked, q=k, labels=False, duplicates="drop")
        if labels.isna().any():
            labels = labels.fillna(0)
        labels = labels.astype(int) + 1
    except Exception:
        labels = pd.Series(1, index=df.index)

    labels.index = df.index
    return labels.astype(int)


def sample_stratified(
    df: pd.DataFrame,
    strata: pd.Series,
    n_total: int,
    *,
    rng: Optional[random.Random] = None,
) -> pd.DataFrame:
    """Trekk et stratifisert, tilfeldig utvalg fra df (kompatibilitet)."""

    if df is None or df.empty or n_total is None:
        return pd.DataFrame(columns=(df.columns if isinstance(df, pd.DataFrame) else None))

    n_total = int(n_total)
    if n_total <= 0:
        return df.head(0).copy()

    n_total = min(n_total, len(df))

    if rng is None:
        rng = random.Random(42)

    # Align strata to df
    strata = strata.reindex(df.index)
    if strata.isna().any():
        strata = strata.fillna(0)

    # Build index lists per stratum
    groups = []
    for label in sorted(strata.unique()):
        idxs = list(df.index[strata == label])
        if not idxs:
            continue
        rng.shuffle(idxs)
        groups.append((label, idxs))

    if not groups:
        # Fallback: simple random sample
        idxs = list(df.index)
        rng.shuffle(idxs)
        return df.loc[idxs[:n_total]].copy()

    # Initial allocation: 1 per group if possible
    alloc = {label: 0 for label, _idxs in groups}
    if n_total >= len(groups):
        for label, idxs in groups:
            alloc[label] = 1 if len(idxs) > 0 else 0

    remaining_to_allocate = n_total - sum(alloc.values())
    if remaining_to_allocate > 0:
        capacities = {label: max(len(idxs) - alloc[label], 0) for label, idxs in groups}
        total_cap = sum(capacities.values())
        if total_cap > 0:
            fractions = {label: remaining_to_allocate * (cap / total_cap) for label, cap in capacities.items()}
            adds = {label: int(math.floor(f)) for label, f in fractions.items()}
            for label in adds:
                adds[label] = min(adds[label], capacities[label])

            remainder = remaining_to_allocate - sum(adds.values())
            order = sorted(
                capacities.keys(),
                key=lambda l: (fractions[l] - adds[l], capacities[l]),
                reverse=True,
            )
            for label in order:
                if remainder <= 0:
                    break
                if adds[label] < capacities[label]:
                    adds[label] += 1
                    remainder -= 1

            for label in adds:
                alloc[label] += adds[label]

    selected_idx: list[Any] = []
    for label, idxs in groups:
        take = min(alloc.get(label, 0), len(idxs))
        if take > 0:
            selected_idx.extend(idxs[:take])

    # Fill hvis vi mangler rader (pga kapasitet/avrunding)
    if len(selected_idx) < n_total:
        remaining_idx = [i for i in df.index if i not in set(selected_idx)]
        rng.shuffle(remaining_idx)
        selected_idx.extend(remaining_idx[: n_total - len(selected_idx)])

    if len(selected_idx) > n_total:
        selected_idx = selected_idx[:n_total]

    return df.loc[selected_idx].copy()
