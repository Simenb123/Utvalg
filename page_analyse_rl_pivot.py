"""page_analyse_rl_pivot.py

Pivot-bygging og aggregering for RL-pivot (regnskapslinje-nivå).

Utskilt fra page_analyse_rl.py. Re-eksportert via page_analyse_rl som
fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import pandas as pd

from page_analyse_rl_data import _resolve_regnr_for_accounts

log = logging.getLogger("app")


def build_rl_pivot(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    sb_df: Optional[pd.DataFrame] = None,
    sb_prev_df: Optional[pd.DataFrame] = None,
    account_overrides: Optional[dict[str, int]] = None,
    prior_year_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Bygg regnskapslinje-pivot.

    Args:
        df_hb:          Filtrert HB-DataFrame med kolonnene "Konto" og "Beløp".
        intervals:      Intervall-mapping (fra, til, regnr).
        regnskapslinjer: Regnskapslinjer-definisjoner.
        sb_df:          Normalisert SB-DataFrame (konto, ib, ub, netto).
                        Hvis None brukes HB-sum som UB (fallback).

    Returnerer DataFrame med kolonnene:
        regnr (int), regnskapslinje (str), IB (float), Endring (float),
        UB (float), Antall (int), og eventuelt UB_fjor/Endring_fjor/Endring_pct.

    Visningsregel:
        Med SB:   vis RL der |UB| > 1e-9 ELLER Antall > 0
        Uten SB:  vis kun RL der Antall > 0
    """
    from regnskap_mapping import (
        compute_sumlinjer,
        normalize_regnskapslinjer,
    )

    if df_hb is None or df_hb.empty:
        return _empty_pivot()
    if "Konto" not in df_hb.columns:
        return _empty_pivot()

    # --- Antall fra HB ---
    df_work = df_hb[["Konto"]].copy()
    df_work["Konto"] = df_work["Konto"].astype(str)
    df_work["_cnt"] = 1
    konto_cnt = df_work.groupby("Konto", as_index=False)["_cnt"].sum()
    konto_cnt.rename(columns={"Konto": "konto"}, inplace=True)

    # Map konto → regnr for HB via servicen
    try:
        regnr_lookup = _resolve_regnr_for_accounts(
            konto_cnt["konto"].astype(str).tolist(),
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
        cnt_mapped = konto_cnt.merge(regnr_lookup, on="konto", how="left")
    except Exception as exc:
        log.warning("RL-pivot: konto-mapping feilet: %s", exc)
        return _empty_pivot()

    antall_per_regnr = (
        cnt_mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)["_cnt"]
        .sum()
        .rename(columns={"_cnt": "Antall"})
    )
    antall_per_regnr["regnr"] = antall_per_regnr["regnr"].astype(int)

    # --- Antall unike bilag per regnr (telles via konto → regnr-mapping) ---
    # Et bilag som treffer flere konti innenfor samme regnr telles én gang.
    bilag_col = next(
        (c for c in ("Bilag", "bilag", "Bilagsnr", "bilagsnr") if c in df_hb.columns),
        None,
    )
    antall_bilag_per_regnr: Optional[pd.DataFrame] = None
    if bilag_col is not None:
        try:
            konto_regnr_map = cnt_mapped[["konto", "regnr"]].dropna(subset=["regnr"]).copy()
            konto_regnr_map["regnr"] = konto_regnr_map["regnr"].astype(int)
            hb_bilag = df_hb[["Konto", bilag_col]].copy()
            hb_bilag["konto"] = hb_bilag["Konto"].astype(str)
            hb_with_regnr = hb_bilag.merge(konto_regnr_map, on="konto", how="inner")
            antall_bilag_per_regnr = (
                hb_with_regnr.groupby("regnr", as_index=False)[bilag_col]
                .nunique()
                .rename(columns={bilag_col: "Antall_bilag"})
            )
            antall_bilag_per_regnr["regnr"] = antall_bilag_per_regnr["regnr"].astype(int)
        except Exception as exc:
            log.warning("RL-pivot: kunne ikke telle unike bilag per regnr: %s", exc)
            antall_bilag_per_regnr = None

    # --- IB og UB ---
    if sb_df is not None and not sb_df.empty and "konto" in sb_df.columns:
        ib_ub = _aggregate_sb_to_regnr(
            sb_df,
            intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    else:
        # Fallback: bruk HB Beløp som UB
        ib_ub = _aggregate_hb_to_regnr(
            df_hb,
            intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )

    # --- Merge med regnskapslinjer ---
    try:
        regn = normalize_regnskapslinjer(regnskapslinjer)
        leaf = regn.loc[~regn["sumpost"]][["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    except Exception as exc:
        log.warning("RL-pivot: normalize_regnskapslinjer feilet: %s", exc)
        return _empty_pivot()

    merged = leaf.merge(ib_ub, how="left", on="regnr")
    merged = merged.merge(antall_per_regnr, how="left", on="regnr")
    if antall_bilag_per_regnr is not None:
        merged = merged.merge(antall_bilag_per_regnr, how="left", on="regnr")
    else:
        merged["Antall_bilag"] = 0

    merged["IB"] = merged["IB"].fillna(0.0)
    merged["UB"] = merged["UB"].fillna(0.0)
    merged["Endring"] = merged["UB"] - merged["IB"]
    merged["Antall"] = merged["Antall"].fillna(0).astype(int)
    merged["Antall_bilag"] = merged["Antall_bilag"].fillna(0).astype(int)

    all_lines = regn[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    if bool(all_lines["sumpost"].any()):
        base_ib = {int(r): float(v) for r, v in zip(merged["regnr"], merged["IB"])}
        base_ub = {int(r): float(v) for r, v in zip(merged["regnr"], merged["UB"])}
        base_endring = {int(r): float(v) for r, v in zip(merged["regnr"], merged["Endring"])}
        base_antall = {int(r): float(v) for r, v in zip(merged["regnr"], merged["Antall"])}
        base_antall_bilag = {int(r): float(v) for r, v in zip(merged["regnr"], merged["Antall_bilag"])}

        try:
            ib_values = compute_sumlinjer(base_values=base_ib, regnskapslinjer=regn)
            ub_values = compute_sumlinjer(base_values=base_ub, regnskapslinjer=regn)
            endring_values = compute_sumlinjer(base_values=base_endring, regnskapslinjer=regn)
            antall_values = compute_sumlinjer(base_values=base_antall, regnskapslinjer=regn)
            antall_bilag_values = compute_sumlinjer(base_values=base_antall_bilag, regnskapslinjer=regn)
        except Exception as exc:
            log.warning("RL-pivot: kunne ikke beregne sumposter: %s", exc)
            ib_values = base_ib
            ub_values = base_ub
            endring_values = base_endring
            antall_values = base_antall
            antall_bilag_values = base_antall_bilag

        all_lines["IB"] = all_lines["regnr"].map(lambda r: float(ib_values.get(int(r), 0.0)))
        all_lines["UB"] = all_lines["regnr"].map(lambda r: float(ub_values.get(int(r), 0.0)))
        all_lines["Endring"] = all_lines["regnr"].map(lambda r: float(endring_values.get(int(r), 0.0)))
        all_lines["Antall"] = (
            all_lines["regnr"]
            .map(lambda r: int(round(float(antall_values.get(int(r), 0.0)))))
            .astype(int)
        )
        all_lines["Antall_bilag"] = (
            all_lines["regnr"]
            .map(lambda r: int(round(float(antall_bilag_values.get(int(r), 0.0)))))
            .astype(int)
        )
    else:
        all_lines = all_lines.merge(
            merged[["regnr", "IB", "Endring", "UB", "Antall", "Antall_bilag"]],
            how="left",
            on="regnr",
        )
        all_lines["IB"] = all_lines["IB"].fillna(0.0)
        all_lines["UB"] = all_lines["UB"].fillna(0.0)
        all_lines["Endring"] = all_lines["Endring"].fillna(0.0)
        all_lines["Antall"] = all_lines["Antall"].fillna(0).astype(int)
        all_lines["Antall_bilag"] = all_lines["Antall_bilag"].fillna(0).astype(int)

    # --- Filtrer tomme linjer ---
    if sb_df is not None and not sb_df.empty:
        mask = (all_lines["UB"].abs() > 1e-9) | (all_lines["Antall"] > 0)
    else:
        mask = all_lines["Antall"] > 0

    merged = all_lines.loc[mask].sort_values("regnr").reset_index(drop=True)

    result = merged[["regnr", "regnskapslinje", "IB", "Endring", "UB", "Antall", "Antall_bilag"]]

    if sb_prev_df is not None and not sb_prev_df.empty:
        try:
            import previous_year_comparison

            result = previous_year_comparison.add_previous_year_columns(
                result,
                sb_prev_df,
                intervals,
                regnskapslinjer,
                account_overrides=account_overrides,
                prior_year_overrides=prior_year_overrides,
            )
        except Exception as exc:
            log.warning("build_rl_pivot: fjorårskolonner feilet: %s", exc)

    return result


def _aggregate_sb_to_regnr(
    sb_df: pd.DataFrame,
    intervals: pd.DataFrame,
    *,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Aggreger SB (IB/UB) per regnr via den kanoniske RL-servicen."""
    work = sb_df[["konto", "ib", "ub"]].copy()
    work["konto"] = work["konto"].astype(str).str.strip()
    work["ib"] = pd.to_numeric(work["ib"], errors="coerce").fillna(0.0)
    work["ub"] = pd.to_numeric(work["ub"], errors="coerce").fillna(0.0)

    try:
        regnr_lookup = _resolve_regnr_for_accounts(
            work["konto"].tolist(),
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        log.warning("_aggregate_sb_to_regnr: mapping feilet: %s", exc)
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    mapped = work.merge(regnr_lookup, on="konto", how="left")
    agg = (
        mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)
        .agg(IB=("ib", "sum"), UB=("ub", "sum"))
    )
    agg["regnr"] = agg["regnr"].astype(int)
    return agg


def _aggregate_hb_to_regnr(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    *,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Fallback: bruk sum av HB Beløp som UB (ingen IB tilgjengelig)."""
    if "Beløp" not in df_hb.columns:
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    work = df_hb[["Konto", "Beløp"]].copy()
    work["Konto"] = work["Konto"].astype(str)
    work["_bel"] = pd.to_numeric(work["Beløp"], errors="coerce").fillna(0.0)
    konto_agg = work.groupby("Konto", as_index=False)["_bel"].sum()
    konto_agg.rename(columns={"Konto": "konto"}, inplace=True)
    konto_agg["konto"] = konto_agg["konto"].astype(str).str.strip()

    try:
        regnr_lookup = _resolve_regnr_for_accounts(
            konto_agg["konto"].tolist(),
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        log.warning("_aggregate_hb_to_regnr: mapping feilet: %s", exc)
        return pd.DataFrame(columns=["regnr", "IB", "UB"])

    mapped = konto_agg.merge(regnr_lookup, on="konto", how="left")
    agg = (
        mapped.dropna(subset=["regnr"])
        .groupby("regnr", as_index=False)["_bel"]
        .sum()
        .rename(columns={"_bel": "UB"})
    )
    agg["IB"] = 0.0
    agg["regnr"] = agg["regnr"].astype(int)
    return agg[["regnr", "IB", "UB"]]


def _empty_pivot() -> pd.DataFrame:
    return pd.DataFrame(columns=["regnr", "regnskapslinje", "IB", "Endring", "UB", "Antall", "Antall_bilag"])


def _add_adjustment_columns(
    pivot_df: pd.DataFrame,
    *,
    base_pivot_df: Optional[pd.DataFrame] = None,
    adjusted_pivot_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Legg til sammenligningskolonner for tilleggsposteringer/ÅO."""
    out = pivot_df.copy()
    if out.empty:
        out["AO_belop"] = pd.Series(dtype=float)
        out["UB_for_ao"] = pd.Series(dtype=float)
        out["UB_etter_ao"] = pd.Series(dtype=float)
        return out

    current_ub = pd.to_numeric(out.get("UB"), errors="coerce").fillna(0.0)
    current_map = {
        int(regnr): float(ub)
        for regnr, ub in zip(out["regnr"], current_ub)
    }

    before_map: dict[int, float] = {}
    if isinstance(base_pivot_df, pd.DataFrame) and not base_pivot_df.empty:
        for _, row in base_pivot_df.iterrows():
            try:
                before_map[int(row["regnr"])] = float(row.get("UB", 0.0) or 0.0)
            except Exception:
                continue

    after_map: dict[int, float] = {}
    if isinstance(adjusted_pivot_df, pd.DataFrame) and not adjusted_pivot_df.empty:
        for _, row in adjusted_pivot_df.iterrows():
            try:
                after_map[int(row["regnr"])] = float(row.get("UB", 0.0) or 0.0)
            except Exception:
                continue

    out["UB_for_ao"] = out["regnr"].map(lambda value: before_map.get(int(value), current_map.get(int(value), 0.0)))
    out["UB_etter_ao"] = out["regnr"].map(lambda value: after_map.get(int(value), current_map.get(int(value), 0.0)))
    out["UB_for_ao"] = pd.to_numeric(out["UB_for_ao"], errors="coerce").fillna(current_ub)
    out["UB_etter_ao"] = pd.to_numeric(out["UB_etter_ao"], errors="coerce").fillna(current_ub)
    out["AO_belop"] = out["UB_etter_ao"] - out["UB_for_ao"]
    return out


def get_unmapped_rl_accounts(
    df_hb: Optional[pd.DataFrame],
    intervals: Optional[pd.DataFrame],
    *,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> List[str]:
    """Returner kontoer i HB-scope som ikke treffer RL-intervall-mapping."""
    if df_hb is None or df_hb.empty or "Konto" not in df_hb.columns:
        return []

    kontos = df_hb["Konto"].dropna().astype(str).unique().tolist()
    if not kontos:
        return []

    try:
        regnr_lookup = _resolve_regnr_for_accounts(
            kontos,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
    except Exception as exc:
        log.warning("get_unmapped_rl_accounts: mapping feilet: %s", exc)
        return []
    return regnr_lookup.loc[regnr_lookup["regnr"].isna(), "konto"].astype(str).unique().tolist()


def _format_mapping_warning(unmapped_accounts: List[str]) -> str:
    if not unmapped_accounts:
        return ""

    count = len(unmapped_accounts)
    sample = ", ".join(unmapped_accounts[:5])
    if count > 5:
        sample += ", ..."

    noun = "konto" if count == 1 else "kontoer"
    return f"Mappingavvik: {count} {noun} uten regnskapslinje-mapping ({sample})"
