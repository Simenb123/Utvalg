"""
analyzers_outliers.py
---------------------
Outlier-detektering (uvanlige transaksjoner) med to robuste metoder:
- MAD-Z (robust z-score rundt median)
- IQR (klassisk boksplott-regel)
"""

from __future__ import annotations
from typing import List
import numpy as np
import pandas as pd
from models import Columns


def _mad_z(values: pd.Series) -> pd.Series:
    x = values.astype(float)
    med = np.nanmedian(x)
    dev = np.abs(x - med)
    mad = np.nanmedian(dev)
    if not np.isfinite(mad) or mad == 0:
        return pd.Series(np.nan, index=values.index)
    z = 0.67448975 * (x - med) / mad  # 0.6745 ~ invCDF(0.75)
    return np.abs(z)


def _iqr_bounds(values: pd.Series, k: float) -> tuple[float, float]:
    x = values.astype(float)
    q1 = np.nanpercentile(x, 25); q3 = np.nanpercentile(x, 75)
    iqr = q3 - q1
    if not np.isfinite(iqr) or iqr == 0:
        return -np.inf, np.inf
    return q1 - k * iqr, q3 + k * iqr


def outliers_by_group(df: pd.DataFrame, c: Columns, *,
                      method: str = "MAD", threshold: float = 3.5,
                      group_by: str = "Konto", min_group: int = 20,
                      basis: str = "abs") -> pd.DataFrame:
    """
    Finn uvanlige transaksjoner per valgt gruppe.
    method: "MAD" (robust z) eller "IQR" (k*IQR-regel)
    group_by: "Global", "Konto", "Part", "Konto+Part"
    basis: "abs" (|beløp|) eller "signed" (beløp)
    """
    if c.belop not in df.columns:
        return pd.DataFrame(columns=["Gruppe", "Konto", "Part", "Bilag", "Dato", "Beløp", "Score", "Metode"])

    d = df.copy()
    x = d[c.belop].astype(float)
    if basis.lower().startswith("abs"):
        x = x.abs()
    d["_VAL"] = x

    # Bygg grupper
    groups: List[tuple[str, ...]] = []
    if group_by.lower() == "global":
        groups = [()]
    elif group_by.lower() == "konto+part":
        if not c.part or c.part not in d.columns:
            return pd.DataFrame(columns=["Gruppe", "Konto", "Part", "Bilag", "Dato", "Beløp", "Score", "Metode"])
        groups = [(c.konto, c.part)]
    elif group_by.lower() == "part":
        if not c.part or c.part not in d.columns:
            return pd.DataFrame(columns=["Gruppe", "Part", "Bilag", "Dato", "Beløp", "Score", "Metode"])
        groups = [(c.part,)]
    else:
        groups = [(c.konto,)]

    out_rows = []
    for gcols in groups:
        subgroups = [("", d)] if len(gcols) == 0 else [(key, sub) for key, sub in d.groupby(list(gcols), dropna=False)]
        for key, sub in subgroups:
            if len(sub) < int(min_group):
                continue
            vals = sub["_VAL"]
            if method.upper() == "MAD":
                z = _mad_z(vals); mask = z >= float(threshold); score = z; method_name = "MAD-Z"
            else:
                lo, hi = _iqr_bounds(vals, float(threshold))
                mask = (vals < lo) | (vals > hi)
                score = np.where(vals < lo, lo - vals, vals - hi)
                score = pd.Series(score, index=sub.index); method_name = f"IQR(k={threshold})"
            if not mask.any():
                continue
            flagged = sub.loc[mask].copy()
            flagged["Score"] = score.loc[mask].astype(float)
            out = flagged[[c.konto, c.part, c.bilag, c.dato, c.belop]].copy()
            out.columns = ["Konto", "Part", "Bilag", "Dato", "Beløp"]
            label = "Global" if len(gcols) == 0 else ("Konto+Part" if gcols == (c.konto, c.part) else ("Part" if gcols == (c.part,) else "Konto"))
            out["Gruppe"] = label; out["Metode"] = method_name
            out_rows.append(out[["Gruppe", "Konto", "Part", "Bilag", "Dato", "Beløp", "Score", "Metode"]])

    if not out_rows:
        return pd.DataFrame(columns=["Gruppe", "Konto", "Part", "Bilag", "Dato", "Beløp", "Score", "Metode"])
    return pd.concat(out_rows, ignore_index=True).sort_values(["Score"], ascending=False)
