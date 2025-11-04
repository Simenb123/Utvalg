from __future__ import annotations
from typing import Any, Optional
import pandas as pd
import numpy as np

DECIMAL_COMMA = True

def fmt_amount(x: Any) -> str:
    try: xv = float(x)
    except (TypeError, ValueError): return ""
    txt = f"{xv:,.2f}"
    if DECIMAL_COMMA:
        txt = txt.replace(",", " ").replace(".", ",")
    return txt

def fmt_int(n: Any) -> str:
    try: iv = int(n)
    except (TypeError, ValueError): return "0"
    txt = f"{iv:,}"
    if DECIMAL_COMMA: txt = txt.replace(",", " ")
    return txt

def parse_amount(s: Any) -> Optional[float]:
    if s is None: return None
    t = str(s).strip()
    if t == "": return None
    t = t.replace(" ", "").replace("kr", "").replace("\u00A0","").replace(".", "").replace(",", ".")
    try: return float(t)
    except Exception: return None

def fmt_date(v: Any) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)): return ""
    try: d = pd.to_datetime(v, errors="coerce", dayfirst=True)
    except Exception: return ""
    if pd.isna(d): return ""
    return d.strftime("%d.%m.%Y")

def parse_date(s: str):
    s = (s or "").strip()
    if not s: return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return pd.to_datetime(s, format=fmt, errors="raise")
        except Exception:
            continue
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return None if pd.isna(d) else d
