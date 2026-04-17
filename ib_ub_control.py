"""IB/UB-kontroll: avstemming mellom saldobalanse (SB) og hovedbok (HB).

Ren beregningsmodul — ingen GUI-avhengigheter.

Brukes til å:
- Sammenligne SB IB/UB med HB-posteringer
- Avdekke differanser per konto og per regnskapslinje
- Generere data for arbeidspapir i Excel
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd


@dataclass
class ReconciliationResult:
    """Resultat fra SB/HB-avstemming."""

    account_level: pd.DataFrame
    rl_level: Optional[pd.DataFrame]
    summary: Dict[str, object]
    discrepancies: pd.DataFrame


@dataclass
class ContinuityResult:
    """Resultat fra IB/UB-kontinuitetskontroll (IB i år == UB fjor)."""

    account_level: pd.DataFrame
    summary: Dict[str, object]
    discrepancies: pd.DataFrame


def build_account_reconciliation(
    sb_df: pd.DataFrame,
    hb_df: pd.DataFrame,
    *,
    konto_col: str = "Konto",
    belop_col: str = "Beløp",
    tolerance: float = 0.01,
    skip_zero: bool = True,
) -> pd.DataFrame:
    """Bygg avstemming per konto mellom SB og HB.

    Returnerer DataFrame med kolonner:
        konto, kontonavn, sb_ib, sb_ub, sb_netto, hb_sum, differanse, har_avvik
    """
    # SB-side: konto, kontonavn, ib, ub, netto
    sb = sb_df[["konto", "kontonavn", "ib", "ub"]].copy()
    sb["konto"] = sb["konto"].astype(str).str.strip()
    sb["ib"] = pd.to_numeric(sb["ib"], errors="coerce").fillna(0.0)
    sb["ub"] = pd.to_numeric(sb["ub"], errors="coerce").fillna(0.0)
    sb["sb_netto"] = sb["ub"] - sb["ib"]
    sb = sb.rename(columns={"ib": "sb_ib", "ub": "sb_ub"})

    # HB-side: sum per konto
    hb = hb_df[[konto_col, belop_col]].copy()
    hb[konto_col] = hb[konto_col].astype(str).str.strip()
    hb[belop_col] = pd.to_numeric(hb[belop_col], errors="coerce").fillna(0.0)
    hb_sum = hb.groupby(konto_col, sort=False)[belop_col].sum().reset_index()
    hb_sum.columns = ["konto", "hb_sum"]

    # Koble SB og HB — full outer join
    merged = sb.merge(hb_sum, on="konto", how="outer")
    merged["kontonavn"] = merged["kontonavn"].fillna("")
    merged["sb_ib"] = merged["sb_ib"].fillna(0.0)
    merged["sb_ub"] = merged["sb_ub"].fillna(0.0)
    merged["sb_netto"] = merged["sb_netto"].fillna(0.0)
    merged["hb_sum"] = merged["hb_sum"].fillna(0.0)
    merged["differanse"] = merged["sb_netto"] - merged["hb_sum"]
    merged["har_avvik"] = merged["differanse"].abs() > tolerance

    # Filtrer vekk kontoer der alt er null (ingen bevegelse verken i SB eller HB)
    if skip_zero:
        has_data = (
            (merged["sb_ib"].abs() > tolerance)
            | (merged["sb_ub"].abs() > tolerance)
            | (merged["sb_netto"].abs() > tolerance)
            | (merged["hb_sum"].abs() > tolerance)
        )
        merged = merged.loc[has_data].copy()

    # Sorter etter konto (numerisk der mulig)
    merged["_sort"] = pd.to_numeric(merged["konto"], errors="coerce").fillna(999999)
    merged = merged.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return merged[["konto", "kontonavn", "sb_ib", "sb_ub", "sb_netto", "hb_sum", "differanse", "har_avvik"]]


def build_rl_reconciliation(
    account_recon: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    account_overrides: Optional[Dict[str, int]] = None,
) -> pd.DataFrame:
    """Aggreger avstemming fra kontonivå til regnskapslinje-nivå.

    Returnerer DataFrame med kolonner:
        regnr, regnskapslinje, sb_ib, sb_ub, sb_netto, hb_sum, differanse, har_avvik
    """
    from regnskap_mapping import (
        apply_account_overrides,
        apply_interval_mapping,
        normalize_regnskapslinjer,
    )

    df = account_recon.copy()
    df["konto_int"] = pd.to_numeric(df["konto"], errors="coerce")

    # Map konto → regnr
    mapped = apply_interval_mapping(df, intervals, konto_col="konto_int")

    if account_overrides:
        mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")

    regn = normalize_regnskapslinjer(regnskapslinjer)
    regnr_to_name = dict(zip(regn["regnr"].astype(int), regn["regnskapslinje"]))

    if "regnr" not in mapped.columns:
        return pd.DataFrame(columns=["regnr", "regnskapslinje", "sb_ib", "sb_ub", "sb_netto", "hb_sum", "differanse", "har_avvik"])

    mapped["regnr"] = pd.to_numeric(mapped["regnr"], errors="coerce")
    mapped = mapped.dropna(subset=["regnr"])
    mapped["regnr"] = mapped["regnr"].astype(int)

    agg = mapped.groupby("regnr", sort=True).agg(
        sb_ib=("sb_ib", "sum"),
        sb_ub=("sb_ub", "sum"),
        sb_netto=("sb_netto", "sum"),
        hb_sum=("hb_sum", "sum"),
        differanse=("differanse", "sum"),
    ).reset_index()

    agg["regnskapslinje"] = agg["regnr"].map(regnr_to_name).fillna("")
    agg["har_avvik"] = agg["differanse"].abs() > 0.01

    return agg[["regnr", "regnskapslinje", "sb_ib", "sb_ub", "sb_netto", "hb_sum", "differanse", "har_avvik"]]


def build_summary(account_recon: pd.DataFrame) -> Dict[str, object]:
    """Oppsummering av totaler og avvik."""
    df = account_recon
    return {
        "total_sb_ib": float(df["sb_ib"].sum()),
        "total_sb_ub": float(df["sb_ub"].sum()),
        "total_sb_netto": float(df["sb_netto"].sum()),
        "total_hb_sum": float(df["hb_sum"].sum()),
        "total_differanse": float(df["differanse"].sum()),
        "antall_kontoer": len(df),
        "antall_avvik": int(df["har_avvik"].sum()),
        "kun_i_sb": int((df["hb_sum"].abs() < 0.01).sum() & (df["sb_netto"].abs() > 0.01).sum()),
        "kun_i_hb": int((df["sb_netto"].abs() < 0.01).sum() & (df["hb_sum"].abs() > 0.01).sum()),
    }


def reconcile(
    sb_df: pd.DataFrame,
    hb_df: pd.DataFrame,
    *,
    intervals: Optional[pd.DataFrame] = None,
    regnskapslinjer: Optional[pd.DataFrame] = None,
    account_overrides: Optional[Dict[str, int]] = None,
    konto_col: str = "Konto",
    belop_col: str = "Beløp",
    tolerance: float = 0.01,
) -> ReconciliationResult:
    """Komplett avstemming: konto-nivå, evt. RL-nivå, oppsummering og avvik."""
    account_level = build_account_reconciliation(
        sb_df, hb_df,
        konto_col=konto_col,
        belop_col=belop_col,
        tolerance=tolerance,
    )

    rl_level = None
    if intervals is not None and regnskapslinjer is not None:
        try:
            rl_level = build_rl_reconciliation(
                account_level, intervals, regnskapslinjer,
                account_overrides=account_overrides,
            )
        except Exception:
            pass

    summary = build_summary(account_level)
    discrepancies = account_level.loc[account_level["har_avvik"]].reset_index(drop=True)

    return ReconciliationResult(
        account_level=account_level,
        rl_level=rl_level,
        summary=summary,
        discrepancies=discrepancies,
    )


# ---------------------------------------------------------------------------
# IB/UB-kontinuitetskontroll:  IB(i år) == UB(fjor)
# ---------------------------------------------------------------------------

def build_continuity_check(
    sb_current: pd.DataFrame,
    sb_previous: pd.DataFrame,
    *,
    tolerance: float = 0.01,
) -> pd.DataFrame:
    """Sjekk at IB i inneværende år stemmer med UB fra forrige år, per konto.

    Begge DataFrames forventes med kolonner: konto, kontonavn, ib, ub.

    Returnerer DataFrame med kolonner:
        konto, kontonavn, ib_current, ub_previous, differanse, har_avvik
    """
    cur = sb_current[["konto", "kontonavn", "ib"]].copy()
    cur["konto"] = cur["konto"].astype(str).str.strip()
    cur["ib"] = pd.to_numeric(cur["ib"], errors="coerce").fillna(0.0)
    cur = cur.rename(columns={"ib": "ib_current"})

    prev = sb_previous[["konto", "ub"]].copy()
    prev["konto"] = prev["konto"].astype(str).str.strip()
    prev["ub"] = pd.to_numeric(prev["ub"], errors="coerce").fillna(0.0)
    prev = prev.rename(columns={"ub": "ub_previous"})

    merged = cur.merge(prev, on="konto", how="outer")
    merged["kontonavn"] = merged["kontonavn"].fillna("")
    merged["ib_current"] = merged["ib_current"].fillna(0.0)
    merged["ub_previous"] = merged["ub_previous"].fillna(0.0)
    merged["differanse"] = merged["ib_current"] - merged["ub_previous"]
    merged["har_avvik"] = merged["differanse"].abs() > tolerance

    # Filtrer vekk kontoer der begge er null
    has_data = (merged["ib_current"].abs() > tolerance) | (merged["ub_previous"].abs() > tolerance)
    merged = merged.loc[has_data].copy()

    merged["_sort"] = pd.to_numeric(merged["konto"], errors="coerce").fillna(999999)
    merged = merged.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    return merged[["konto", "kontonavn", "ib_current", "ub_previous", "differanse", "har_avvik"]]


def build_continuity_summary(df: pd.DataFrame) -> Dict[str, object]:
    """Oppsummering av IB/UB-kontinuitetskontroll."""
    return {
        "total_ib_current": float(df["ib_current"].sum()),
        "total_ub_previous": float(df["ub_previous"].sum()),
        "total_differanse": float(df["differanse"].sum()),
        "antall_kontoer": len(df),
        "antall_avvik": int(df["har_avvik"].sum()),
        "kun_i_current": int(((df["ub_previous"].abs() < 0.01) & (df["ib_current"].abs() > 0.01)).sum()),
        "kun_i_previous": int(((df["ib_current"].abs() < 0.01) & (df["ub_previous"].abs() > 0.01)).sum()),
    }


def check_continuity(
    sb_current: pd.DataFrame,
    sb_previous: pd.DataFrame,
    *,
    tolerance: float = 0.01,
) -> ContinuityResult:
    """Komplett IB/UB-kontinuitetskontroll."""
    account_level = build_continuity_check(sb_current, sb_previous, tolerance=tolerance)
    summary = build_continuity_summary(account_level)
    discrepancies = account_level.loc[account_level["har_avvik"]].reset_index(drop=True)
    return ContinuityResult(
        account_level=account_level,
        summary=summary,
        discrepancies=discrepancies,
    )
