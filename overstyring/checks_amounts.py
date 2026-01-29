from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from .core import CheckResult, build_voucher_summary, filter_accounts, resolve_core_columns, _amount_from_cols


def large_vouchers(
    df: pd.DataFrame,
    cols: Any | None = None,
    threshold: float = 1_500_000.0,
    top_n: int = 200,
    include_only_accounts: Sequence[str] | None = None,
    exclude_accounts: Sequence[str] | None = None,
    check_id: str = "large_vouchers",
    title: str = "Store bilag",
) -> CheckResult:
    """
    Finn bilag der abs(netto) >= threshold.

    include_only_accounts/exclude_accounts filtrerer linjenivå før aggregasjon.
    Drilldown kan fortsatt åpne hele bilaget via df_all i UI.
    """
    colmap, missing = resolve_core_columns(df, cols=cols, strict=False)
    bilag_col = colmap.get("bilag", "")
    konto_col = colmap.get("konto", "")

    if not bilag_col or bilag_col not in df.columns:
        return CheckResult(check_id, title, pd.DataFrame(), pd.DataFrame(), meta={"missing": missing})

    df_base = filter_accounts(df, konto_col, include_only_accounts, exclude_accounts)

    summ = build_voucher_summary(df_base, cols=cols)
    if summ.empty:
        return CheckResult(check_id, title, summ, df_base.iloc[0:0].copy(), meta={"missing": missing})

    summ = summ[summ["NettoAbs"] >= float(threshold)].copy()
    summ = summ.sort_values("NettoAbs", ascending=False, kind="mergesort")

    if top_n and len(summ) > int(top_n):
        summ = summ.head(int(top_n)).copy()

    bilags = summ["Bilag"].astype("string").tolist()
    lines = df_base[df_base[bilag_col].astype("string").isin(bilags)].copy()

    return CheckResult(
        check_id=check_id,
        title=title,
        summary_df=summ.reset_index(drop=True),
        lines_df=lines.reset_index(drop=True),
        meta={
            "threshold": threshold,
            "top_n": top_n,
            "include_only_accounts": list(include_only_accounts or []),
            "exclude_accounts": list(exclude_accounts or []),
            "colmap": colmap,
            "missing": missing,
        },
    )


def _round_analysis_for_amounts(
    amounts_abs: pd.Series,
    round_base: float,
    tol: float = 0.0,
) -> tuple[pd.Series, pd.Series]:
    """
    For hver verdi, finn "beste" (minste avstand) base blant:
      base, base/10, base/100 (så lenge >= 1)

    Returnerer:
        (best_base, best_dist)
    """
    x = pd.to_numeric(amounts_abs, errors="coerce").fillna(0.0).astype("float64")

    bases: list[float] = [float(round_base)]
    for f in (0.1, 0.01):
        b = float(round_base) * f
        if b >= 1:
            bases.append(b)

    best_base = pd.Series(np.nan, index=x.index, dtype="float64")
    best_dist = pd.Series(np.inf, index=x.index, dtype="float64")

    for b in bases:
        q = np.rint(x / b)
        dist = (x - q * b).abs()
        is_round = dist <= float(tol)

        # Oppdater kun der verdien faktisk er "round"
        upd = is_round & (dist < best_dist)
        if upd.any():
            best_base.loc[upd] = b
            best_dist.loc[upd] = dist.loc[upd]

    # Hvis ingenting traff: best_base blir NaN, best_dist inf
    return best_base, best_dist


def round_amount_vouchers(
    df: pd.DataFrame,
    cols: Any | None = None,
    round_base: float = 10_000.0,
    require_zero_cents: bool = True,
    min_netto_abs: float = 0.0,
    top_n: int = 200,
    check_id: str = "round_amounts",
    title: str = "Runde beløp",
) -> CheckResult:
    """
    Finn bilag som inneholder linjer med "runde beløp" (f.eks 10k, 100k, ...).

    Heuristikk:
      - vi sjekker round_base, round_base/10 og round_base/100
      - dist må være 0 (tol=0) for å regnes som rund
      - require_zero_cents => beløpet må være helt i valutaenheter (0 øre)
    """
    colmap, missing = resolve_core_columns(df, cols=cols, strict=False)
    bilag_col = colmap.get("bilag", "")
    if not bilag_col or bilag_col not in df.columns:
        return CheckResult(check_id, title, pd.DataFrame(), pd.DataFrame(), meta={"missing": missing})

    amt = _amount_from_cols(df, colmap)
    abs_amt = amt.abs()

    best_base, best_dist = _round_analysis_for_amounts(abs_amt, round_base=round_base, tol=0.0)
    is_round = best_base.notna()

    if require_zero_cents:
        cents = (abs_amt % 1).abs()
        is_round = is_round & (cents < 1e-9)

    flagged_lines = df[is_round].copy()
    if flagged_lines.empty:
        return CheckResult(check_id, title, pd.DataFrame(), df.iloc[0:0].copy(), meta={"missing": missing})

    # Bilag som har minst én rund linje
    bilags = flagged_lines[bilag_col].astype("string")
    bilags = bilags[bilags.notna()].unique().tolist()

    # Sammendrag basert på hele df (ikke bare runde linjer)
    summ_all = build_voucher_summary(df, cols=cols)
    summ = summ_all[summ_all["Bilag"].astype("string").isin(bilags)].copy()

    # Antall runde linjer per bilag + "rundhetsnivå" (største base)
    # Vi må mappe best_base til de runde linjene
    flagged_lines["__RoundBase__"] = best_base[is_round].astype("float64").values
    g = flagged_lines.groupby(flagged_lines[bilag_col].astype("string"), dropna=True)

    summ = summ.set_index("Bilag")
    summ["AntallRundeLinjer"] = g.size()
    summ["MaksRundhetsnivå"] = g["__RoundBase__"].max()
    summ = summ.reset_index()

    # Begrens (mest "runde"/store først)
    summ = summ.sort_values(["AntallRundeLinjer", "MaksRundhetsnivå", "NettoAbs"], ascending=[False, False, False], kind="mergesort")

    # Valgfritt: filter bort små bilag på netto (abs)
    try:
        thr = float(min_netto_abs)
    except Exception:
        thr = 0.0
    if thr and "NettoAbs" in summ.columns:
        summ = summ[summ["NettoAbs"] >= thr].copy()

    if top_n and len(summ) > int(top_n):
        summ = summ.head(int(top_n)).copy()

    # For UI/eksport: vis en mer kompakt tabell (fokus på netto)
    preferred_cols = [
        "Bilag",
        "DatoMin",
        "DatoMax",
        "Netto",
        "NettoAbs",
        "AntallLinjer",
        "KontoNunique",
        "AntallRundeLinjer",
        "MaksRundhetsnivå",
    ]
    cols_present = [c for c in preferred_cols if c in summ.columns]
    if cols_present:
        summ = summ[cols_present].copy()

    keep_bilags = summ["Bilag"].astype("string").tolist()
    lines = df[df[bilag_col].astype("string").isin(keep_bilags)].copy()

    # Marker runde linjer i lines
    lines["__IsRound__"] = False
    round_idx = flagged_lines.index.intersection(lines.index)
    if len(round_idx) > 0:
        lines.loc[round_idx, "__IsRound__"] = True
        lines.loc[round_idx, "__RoundBase__"] = flagged_lines.loc[round_idx, "__RoundBase__"].values

    return CheckResult(
        check_id=check_id,
        title=title,
        summary_df=summ.reset_index(drop=True),
        lines_df=lines.reset_index(drop=True),
        meta={
            "round_base": round_base,
            "require_zero_cents": require_zero_cents,
            "min_netto_abs": min_netto_abs,
            "top_n": top_n,
            "colmap": colmap,
            "missing": missing,
        },
    )
