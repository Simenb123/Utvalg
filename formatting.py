from __future__ import annotations
import math
import pandas as pd
from typing import Any, Optional

_THINSPACE = "\u202F"  # reserved if we want, but we use normal space per spec

def format_number_no(x: Any, decimals: int = 2) -> str:
    """Norsk visning: tusenskiller ' ' (mellomrom), komma som desimal."""
    if x is None:
        return ""
    try:
        if isinstance(x, (pd.Series, pd.DataFrame)):
            raise TypeError("format_number_no expects scalar")
        if isinstance(x, str) and x.strip() == "":
            return ""
        v = float(x)
        if math.isnan(v):
            return ""
    except Exception:
        return str(x)
    s = f"{v:,.{decimals}f}"  # 1,234,567.89
    # bytt om: komma -> mellomrom (tusen), punktum -> komma (desimal)
    s = s.replace(",", " ").replace(".", ",")
    return s

def format_int_no(x: Any) -> str:
    if x is None:
        return ""
    try:
        v = int(x)
    except Exception:
        # fall back to float->int when it's like 12.0
        try:
            v = int(float(x))
        except Exception:
            return str(x)
    s = f"{v:,}".replace(",", " ")
    return s

def format_date_no(x: Any) -> str:
    if x is None:
        return ""
    try:
        if isinstance(x, str):
            ts = pd.to_datetime(x, errors="coerce", dayfirst=True)
        else:
            ts = pd.to_datetime(x, errors="coerce")
        if pd.isna(ts):
            return ""
        return ts.strftime("%d.%m.%Y")
    except Exception:
        return str(x)

def is_number_like_col(col_name: str) -> bool:
    lname = (col_name or "").lower()
    return any(k in lname for k in ["beløp","belop","sum","mva","valuta","amount"])

def is_percent_col(col_name: str) -> bool:
    lname = (col_name or "").lower()
    return "prosent" in lname or lname.endswith("%")