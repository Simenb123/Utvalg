
from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np

def kontoserie_value(konto: Optional[object]) -> Optional[int]:
    """Robust første-siffer-mapping for kontoserier 1..9.
    Returnerer None om ikke mulig å tolke.
    """
    if konto is None:
        return None
    try:
        # Tolerer str, float, int
        s = str(konto).strip()
        if s == "" or s.lower() == "nan":
            return None
        # Fjern desimaler/komma
        if "." in s:
            s = s.split(".")[0]
        if "," in s:
            s = s.split(",")[0]
        # Fjern ledende tegn +/−
        while s and (s[0] in "+- "):
            s = s[1:]
        if not s:
            return None
        return int(s[0])
    except Exception:
        return None

def apply_kontoserie_filter(df: pd.DataFrame, series_selected: set[int], konto_col: str = "Konto") -> pd.DataFrame:
    if not series_selected:
        return df
    ser = df[konto_col].map(kontoserie_value)
    mask = ser.isin(series_selected)
    return df.loc[mask]

def ensure_abs_belop(df: pd.DataFrame, belop_col: str = "Beløp") -> pd.Series:
    if belop_col not in df.columns:
        return pd.Series([], dtype="float64")
    s = pd.to_numeric(df[belop_col], errors="coerce").fillna(0.0)
    return s.abs()
