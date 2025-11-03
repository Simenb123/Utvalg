"""
analyzers_round_share.py
------------------------
Andel runde beløp pr. gruppe (Konto/Part/Måned) med valgbar toleranse
og min. antall rader.
"""

from __future__ import annotations
from typing import Iterable
import numpy as np
import pandas as pd
from models import Columns


def _is_round_any_bases(abs_amounts: pd.Series, bases: Iterable[int], tol: float) -> pd.Series:
    """True hvis beløpet er rundt mot minst én base innenfor ±tol."""
    tol = float(tol)
    flags = None
    for b in bases:
        if b <= 0:
            continue
        nearest = (np.round(abs_amounts / b) * b).astype(float)
        delta = (abs_amounts - nearest).abs()
        m = delta <= tol
        flags = m if flags is None else (flags | m)
    return flags if flags is not None else pd.Series(False, index=abs_amounts.index)


def round_share_by_group(df: pd.DataFrame, c: Columns, *,
                         group_by: str = "Konto",
                         bases: Iterable[int] = (1000, 500, 100),
                         tol: float = 0.0,
                         threshold: float = 0.30,
                         min_rows: int = 20) -> pd.DataFrame:
    """
    Beregn andel runde beløp pr. gruppe. Returnerer grupper med andel >= threshold.
    """
    if c.belop not in df.columns:
        return pd.DataFrame(columns=["Gruppe", "Verdi", "Antall", "Runde", "Andel", "Sum |beløp|"])

    d = df.copy(); d["_ABS"] = d[c.belop].astype(float).abs()

    if group_by.lower() == "måned":
        if not c.dato or c.dato not in d.columns:
            return pd.DataFrame(columns=["Gruppe", "Verdi", "Antall", "Runde", "Andel", "Sum |beløp|"])
        d["_GRP"] = d[c.dato].dt.to_period("M").astype(str); label = "Måned"
    elif group_by.lower() == "part":
        if not c.part or c.part not in d.columns:
            return pd.DataFrame(columns=["Gruppe", "Verdi", "Antall", "Runde", "Andel", "Sum |beløp|"])
        d["_GRP"] = d[c.part].astype(str); label = "Part"
    else:
        d["_GRP"] = d[c.konto].astype(str); label = "Konto"

    is_round = _is_round_any_bases(d["_ABS"], bases, tol).fillna(False)
    d["_ROUND"] = is_round

    g = d.groupby("_GRP")
    tab = g["_ROUND"].agg(Runde="sum").to_frame()
    tab["Antall"] = g.size()
    tab["Andel"] = (tab["Runde"].astype(float) / tab["Antall"].astype(float)).fillna(0.0)
    tab["Sum |beløp|"] = g["_ABS"].sum()

    tab = tab[tab["Antall"] >= int(min_rows)].reset_index().rename(columns={"_GRP": "Verdi"})
    tab.insert(0, "Gruppe", label)
    flagged = tab[tab["Andel"] >= float(threshold)].copy()
    return flagged.sort_values(["Andel", "Antall", "Sum |beløp|"], ascending=[False, False, False])[["Gruppe", "Verdi", "Antall", "Runde", "Andel", "Sum |beløp|"]]
