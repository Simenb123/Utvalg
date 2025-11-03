"""
ab_matchers.py
--------------
Krysshint mellom datasett A og B: likt beløp, motsatt fortegn (kreditnota),
two-sum (B+B=A) og 1-til-1-unik paring (greedy).

Ingen I/O. Kun pandas-logikk. Importeres av ab_analyzers.py (façade).
"""

from __future__ import annotations
from typing import Dict, List
import numpy as np
import pandas as pd

from models import Columns


def _prep(df: pd.DataFrame, c: Columns) -> pd.DataFrame:
    """Standardiser kolonner til idx, Part, Bilag, Belop, Dato (+ evt. Konto/Tekst)."""
    out = pd.DataFrame(index=df.index)
    out["idx"] = df.index
    out["Part"] = df[c.part] if (c.part and c.part in df.columns) else ""
    out["Bilag"] = df[c.bilag] if (c.bilag in df.columns) else ""
    out["Belop"] = df[c.belop].astype(float)
    out["Dato"] = df[c.dato] if (c.dato and c.dato in df.columns) else pd.NaT
    try:
        out["Dato"] = pd.to_datetime(out["Dato"], errors="coerce")
    except Exception:
        out["Dato"] = pd.NaT
    if c.konto and c.konto in df.columns:
        out["Konto"] = df[c.konto]
    if c.tekst and c.tekst in df.columns:
        out["Tekst"] = df[c.tekst]
    return out


def _greedy_unique_pairs(df: pd.DataFrame,
                         a_col: str,
                         b_col: str,
                         amount_col: str | None = None,
                         days_col: str | None = None) -> pd.DataFrame:
    """
    Greedy 1-til-1-paring: minst score først.
    score = |beløpsavvik|*100 + |dager| (NaN i dager straffes høyt).
    """
    if df is None or df.empty:
        return df
    work = df.copy()
    amt = work[amount_col].abs().astype(float).fillna(0.0) if amount_col in work.columns else 0.0
    days = work[days_col].abs().fillna(1e9) if days_col in work.columns else 0.0
    work["_score"] = (amt * 100.0) + days

    order_a = work.groupby(a_col).size().sort_values().index.tolist()
    used_b = set()
    chosen_idx = []

    for a in order_a:
        sub = work[work[a_col] == a].sort_values(by=["_score", b_col])
        for ridx, row in sub.iterrows():
            b = row[b_col]
            if b in used_b:
                continue
            used_b.add(b)
            chosen_idx.append(ridx)
            break

    return work.loc[chosen_idx].drop(columns=["_score"])


def match_same_amount(
    dfA: pd.DataFrame, cA: Columns,
    dfB: pd.DataFrame, cB: Columns,
    days_tol: int = 3, amount_tol: float = 0.0,
    require_same_party: bool = False,
    unique: bool = False
) -> pd.DataFrame:
    """
    A ↔ B likt beløp (± amount_tol). Valgfritt: ± days_tol, samme Part, og 1-til-1.
    """
    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["cents"] = np.rint(A["Belop"] * 100).astype("Int64")
    B["cents"] = np.rint(B["Belop"] * 100).astype("Int64")
    tol = int(round(float(amount_tol) * 100))

    idx_map: Dict[int, List[int]] = {}
    for i, v in B["cents"].dropna().items():
        idx_map.setdefault(int(v), []).append(i)

    rows = []
    for ia, ca in A["cents"].dropna().items():
        ca = int(ca)
        candidates: List[int] = []
        if tol == 0:
            candidates = idx_map.get(ca, [])
        else:
            for d in range(-tol, tol + 1):
                candidates += idx_map.get(ca + d, [])
        if not candidates:
            continue

        arow = A.loc[ia]
        for ib in candidates:
            brow = B.loc[ib]
            if require_same_party and (str(arow["Part"]) != str(brow["Part"])):
                continue
            if days_tol is not None and pd.notna(arow["Dato"]) and pd.notna(brow["Dato"]):
                ddd = abs((brow["Dato"] - arow["Dato"]).days)
                if ddd > int(days_tol):
                    continue
                days = ddd
            else:
                days = np.nan
            bel_diff = float(brow["Belop"] - arow["Belop"])
            rows.append({
                "A_idx": ia, "A_Part": arow["Part"], "A_Bilag": arow["Bilag"], "A_Dato": arow["Dato"], "A_Belop": arow["Belop"],
                "B_idx": ib, "B_Part": brow["Part"], "B_Bilag": brow["Bilag"], "B_Dato": brow["Dato"], "B_Belop": brow["Belop"],
                "Dager_diff": days, "Beløpsavvik": bel_diff
            })
    out = pd.DataFrame(rows)
    if unique and not out.empty:
        out = _greedy_unique_pairs(out, "A_idx", "B_idx", "Beløpsavvik", "Dager_diff")
    return out


def match_opposite_sign(
    dfA: pd.DataFrame, cA: Columns,
    dfB: pd.DataFrame, cB: Columns,
    days_tol: int = 3, amount_tol: float = 0.0,
    require_same_party: bool = False,
    unique: bool = False
) -> pd.DataFrame:
    """A ↔ −B likt beløp (kreditnota-hint). Samme parametre som over."""
    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["cents"] = np.rint(A["Belop"] * 100).astype("Int64")
    B["cents"] = np.rint(B["Belop"] * 100).astype("Int64")
    tol = int(round(float(amount_tol) * 100))

    idx_map: Dict[int, List[int]] = {}
    for i, v in B["cents"].dropna().items():
        idx_map.setdefault(int(v), []).append(i)

    rows = []
    for ia, ca in A["cents"].dropna().items():
        target = -int(ca)
        candidates: List[int] = []
        if tol == 0:
            candidates = idx_map.get(target, [])
        else:
            for d in range(-tol, tol + 1):
                candidates += idx_map.get(target + d, [])
        if not candidates:
            continue
        arow = A.loc[ia]
        for ib in candidates:
            brow = B.loc[ib]
            if require_same_party and (str(arow["Part"]) != str(brow["Part"])):
                continue
            if days_tol is not None and pd.notna(arow["Dato"]) and pd.notna(brow["Dato"]):
                ddd = abs((brow["Dato"] - arow["Dato"]).days)
                if ddd > int(days_tol):
                    continue
                days = ddd
            else:
                days = np.nan
            bel_diff = float(brow["Belop"] + arow["Belop"])
            rows.append({
                "A_idx": ia, "A_Part": arow["Part"], "A_Bilag": arow["Bilag"], "A_Dato": arow["Dato"], "A_Belop": arow["Belop"],
                "B_idx": ib, "B_Part": brow["Part"], "B_Bilag": brow["Bilag"], "B_Dato": brow["Dato"], "B_Belop": brow["Belop"],
                "Dager_diff": days, "Beløpsavvik": bel_diff
            })
    out = pd.DataFrame(rows)
    if unique and not out.empty:
        out = _greedy_unique_pairs(out, "A_idx", "B_idx", "Beløpsavvik", "Dager_diff")
    return out


def match_two_sum(
    dfA: pd.DataFrame, cA: Columns,
    dfB: pd.DataFrame, cB: Columns,
    days_tol: int = 3,
    require_same_party: bool = False,
    unique_a: bool = False
) -> pd.DataFrame:
    """
    Finn par (B1,B2) slik at B1+B2 = A (eksakt øre).
    Hvis unique_a=True: maks ett (B1,B2)-par per A (lavest datokost).
    """
    A = _prep(dfA, cA); B = _prep(dfB, cB)
    A["cents"] = np.rint(A["Belop"] * 100).astype("Int64")
    B["cents"] = np.rint(B["Belop"] * 100).astype("Int64")

    rows = []
    groups = {k: v.index.tolist()} if require_same_party else {"__ALL__": B.index.tolist()}
    if require_same_party:
        groups = {k: v.index.tolist() for k, v in B.groupby(B["Part"].astype(str))}

    for ia, arow in A.dropna(subset=["cents"]).iterrows():
        target = int(arow["cents"])
        key = str(arow["Part"]) if require_same_party else "__ALL__"
        idxs = groups.get(key, [])
        if not idxs:
            continue

        if days_tol is not None and pd.notna(arow["Dato"]):
            cand = [ib for ib in idxs
                    if pd.notna(B.at[ib, "Dato"]) and abs((B.at[ib, "Dato"] - arow["Dato"]).days) <= int(days_tol)]
        else:
            cand = idxs

        seen: Dict[int, List[int]] = {}
        for ib in cand:
            vb = int(B.at[ib, "cents"])
            comp = target - vb
            if comp in seen:
                for ib2 in seen[comp]:
                    if ib2 == ib:
                        continue
                    b1, b2 = (ib2, ib) if ib2 < ib else (ib, ib2)
                    brow1 = B.loc[b1]; brow2 = B.loc[b2]
                    d1 = abs((brow1["Dato"] - arow["Dato"]).days) if pd.notna(brow1["Dato"]) and pd.notna(arow["Dato"]) else np.nan
                    d2 = abs((brow2["Dato"] - arow["Dato"]).days) if pd.notna(brow2["Dato"]) and pd.notna(arow["Dato"]) else np.nan
                    dcost = np.nanmax([d1, d2]) if not (np.isnan(d1) and np.isnan(d2)) else np.nan
                    rows.append({
                        "A_idx": ia, "A_Part": arow["Part"], "A_Bilag": arow["Bilag"], "A_Dato": arow["Dato"], "A_Belop": arow["Belop"],
                        "B1_idx": b1, "B1_Part": brow1["Part"], "B1_Bilag": brow1["Bilag"], "B1_Dato": brow1["Dato"], "B1_Belop": brow1["Belop"],
                        "B2_idx": b2, "B2_Part": brow2["Part"], "B2_Bilag": brow2["Bilag"], "B2_Dato": brow2["Dato"], "B2_Belop": brow2["Belop"],
                        "Dato_kost": dcost
                    })
            seen.setdefault(vb, []).append(ib)

    out = pd.DataFrame(rows)
    if unique_a and not out.empty:
        out = (out.sort_values(["A_idx", "Dato_kost", "B1_idx", "B2_idx"])
                  .groupby("A_idx", as_index=False).head(1))
    return out
