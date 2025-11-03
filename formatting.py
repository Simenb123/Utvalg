from __future__ import annotations
import datetime as dt
from typing import Any, Optional

import numpy as np
import pandas as pd

# Failsafe: bruk norsk formatering selv om konstanten evt. ikke kan importeres
try:
    from models import DECIMAL_COMMA
except Exception:
    DECIMAL_COMMA = True  # norsk standard (mellomrom som tusenskille, komma som desimal)


# --------------------------- BELØP --------------------------------------

def _normalize_amount_string(s: str) -> str:
    """Gjør vanlige norske/engelsk varianter til et 'float-vennlig' uttrykk."""
    t = (s or "").strip()
    if not t:
        return ""
    t = (
        t.replace("\xa0", "")  # non-breaking space
         .replace(" ", "")
         .replace("kr", "")
         .replace("(", "-").replace(")", "")  # (1 000,00) -> -1000,00
    )
    # Hvis både komma og punktum finnes, antar vi norsk (punktum tusen, komma desimal)
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        # ren norsk
        t = t.replace(",", ".")
    return t


def parse_amount(x: Any) -> Optional[float]:
    """Robust parser for beløp (norsk/US). Returnerer None ved tom/ugyldig."""
    if isinstance(x, (int, float)):
        if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
            return None
        return float(x)
    t = _normalize_amount_string(str(x))
    if not t:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def fmt_amount(x: Any) -> str:
    """Norsk beløp med tusenskiller og 2 desimaler."""
    val = parse_amount(x)
    if val is None:
        return ""
    if DECIMAL_COMMA:
        us = f"{val:,.2f}"               # 12,345.67
        return us.replace(",", " ").replace(".", ",")  # 12 345,67
    return f"{val:,.2f}"


def fmt_int(x: Any) -> str:
    try:
        v = int(x)
    except Exception:
        return ""
    txt = f"{v:,}"
    return txt.replace(",", " ") if DECIMAL_COMMA else txt


# --------------------------- DATO ---------------------------------------

def parse_date(x: Any) -> Optional[pd.Timestamp]:
    """
    Forsøker å tolke x som dato.
    Returnerer pandas.Timestamp (UTC-naiv) ved suksess, ellers None.
    Godtar bl.a.: dd.mm.yyyy, dd/mm/yyyy, yyyy-mm-dd, yyyy.mm.dd, mm/dd/yyyy, ISO.
    """
    if x is None:
        return None

    # Allerede datetime?
    if isinstance(x, pd.Timestamp):
        d = x
    elif isinstance(x, (dt.datetime, dt.date)):
        d = pd.to_datetime(x)
    else:
        s = str(x).strip()
        if not s:
            return None
        # Først et generisk forsøk m/ dayfirst=True (uten deprecated infer-flag)
        d = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if pd.isna(d):
            # Prøv noen vanlige eksplisitte formater
            for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%Y.%m.%d", "%m/%d/%Y"):
                try:
                    d = pd.to_datetime(s, format=fmt, errors="raise")
                    break
                except Exception:
                    d = pd.NaT
            if pd.isna(d):
                return None

    # Normaliser/strip tidssone, og la tidspunkt være 00:00:00
    try:
        if d.tz is not None:
            d = d.tz_localize(None)
    except Exception:
        pass
    return pd.Timestamp(year=d.year, month=d.month, day=d.day)


def fmt_date(x: Any) -> str:
    """dd.mm.yyyy – tom streng ved manglende verdi."""
    d = parse_date(x)
    return "" if d is None else d.strftime("%d.%m.%Y")


__all__ = ["fmt_amount", "fmt_int", "fmt_date", "parse_amount", "parse_date"]
