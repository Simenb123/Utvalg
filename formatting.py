"""
Formateringshjelpere (norsk).

Modulen brukes på tvers av GUI, eksport og analyser, og har tilhørende tester.

Mål/kontrakt:
  - None/NaN -> "" (tom streng)
  - Pandas Series/DataFrame (og andre "tabell-lignende" objekter) -> str(x)
    (for å unngå "truth value of a Series is ambiguous" osv.)
  - Norske tall: mellomrom som tusenskiller og komma som desimalskiller.
"""

from __future__ import annotations

from typing import Any, Optional

import math
import re

import pandas as pd


def _is_tabular(x: Any) -> bool:
    """Returner True for tabell-lignende pandas-objekter som ikke skal formateres."""
    # Viktig: IKKE evaluer truthiness på Series/DataFrame.
    return isinstance(x, (pd.Series, pd.DataFrame, pd.Index))


def _try_parse_float(x: Any) -> Optional[float]:
    """Best-effort parsing til float for norske tallstrenger."""
    if x is None:
        return None

    # Ikke la bool gå via int/float
    if isinstance(x, bool):
        return None

    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try:
            return float(x)
        except Exception:
            return None

    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return None

        # Fjern NBSP og vanlige mellomrom (tusenskiller)
        s = s.replace("\u00A0", " ").replace(" ", "")

        # Fjern prosenttegn hvis det finnes
        s = s.replace("%", "")

        # Håndter både 1.234,56 og 1234,56 og 1234.56
        if "," in s and "." in s:
            # Anta . som tusenskiller og , som desimal
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")

        try:
            return float(s)
        except Exception:
            return None

    return None


def _format_with_spaces(num: float, decimals: int) -> str:
    """Formatter float med tusenskiller (mellomrom) og desimal komma."""
    if decimals < 0:
        decimals = 0
    s = f"{num:,.{decimals}f}"
    # US -> NO
    s = s.replace(",", " ").replace(".", ",")
    return s


def format_number_no(x: Any, decimals: int = 2) -> str:
    """Norsk tallformat.

    - None/NaN -> ""
    - Ugyldig streng -> returner original streng
    - Series/DataFrame -> str(x)
    """
    if x is None:
        return ""

    if _is_tabular(x):
        return str(x)

    # Viktig: whitespace-strenger behandles som tom verdi (forventet av tester/UI)
    if isinstance(x, str) and x.strip() == "":
        return ""

    v = _try_parse_float(x)
    if v is None:
        return str(x)

    # NaN/NaT
    if pd.isna(v) or (isinstance(v, float) and not math.isfinite(v)):
        return ""

    return _format_with_spaces(float(v), int(decimals))


def format_int_no(x: Any) -> str:
    """Norsk heltallsformat med tusenskiller.

    - None/NaN -> ""
    - Ugyldig streng -> returner original streng
    - Series/DataFrame -> str(x)
    """
    if x is None:
        return ""

    if _is_tabular(x):
        return str(x)

    # Først: prøv int direkte
    try:
        if isinstance(x, str):
            s = x.strip()
            if s == "":
                return ""
            # typisk "12.0" eller "12,0"
            s_norm = s.replace("\u00A0", " ").replace(" ", "")
            s_norm = s_norm.replace(",", ".")
            if re.fullmatch(r"[+-]?\d+", s_norm):
                iv = int(s_norm)
                return f"{iv:,}".replace(",", " ")
    except Exception:
        pass

    v = _try_parse_float(x)
    if v is None:
        return str(x)

    if pd.isna(v) or (isinstance(v, float) and not math.isfinite(v)):
        return ""

    iv = int(v)
    return f"{iv:,}".replace(",", " ")


def format_date_no(x: Any) -> str:
    """Datoformat dd.mm.yyyy (Norsk).

    Merk: Tester låser dagens oppførsel: ISO-lignende streng kan tolkes med dayfirst=True.
    - None/NaN -> ""
    - Ugyldig -> ""
    - Exception i to_datetime -> str(x)
    """
    if x is None:
        return ""

    if _is_tabular(x):
        return str(x)

    try:
        dt = pd.to_datetime(x, errors="coerce", dayfirst=True)
    except Exception:
        return str(x)

    if pd.isna(dt):
        return ""

    try:
        return dt.strftime("%d.%m.%Y")
    except Exception:
        # For sikkerhets skyld
        return ""


# --- Alias brukt rundt i GUI/eksport -----------------------------------------

def fmt_amount(x: Any, decimals: int = 2) -> str:
    return format_number_no(x, decimals=decimals)


def fmt_int(x: Any) -> str:
    return format_int_no(x)


def fmt_date(x: Any) -> str:
    """Mer robust datoformattering enn format_date_no.

    - Hvis input ser ut som ISO (YYYY-MM-DD), tolk som ISO (dayfirst=False)
    - Ellers: dayfirst=True (typisk norsk)
    """
    if x is None:
        return ""
    if _is_tabular(x):
        return str(x)

    if isinstance(x, str):
        s = x.strip()
        if s == "":
            return ""
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) or re.fullmatch(r"\d{4}/\d{2}/\d{2}", s):
            try:
                dt = pd.to_datetime(s, errors="coerce", dayfirst=False)
            except Exception:
                return str(x)
        else:
            try:
                dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
            except Exception:
                return str(x)
    else:
        try:
            dt = pd.to_datetime(x, errors="coerce")
        except Exception:
            return str(x)

    if pd.isna(dt):
        return ""

    try:
        return dt.strftime("%d.%m.%Y")
    except Exception:
        return ""


# Bakoverkompatibilitet: noen moduler har importert format_date
format_date = fmt_date


def is_number_like_col(name: Any) -> bool:
    """Heuristikk: kolonnenavn som typisk inneholder tall."""
    if name is None:
        return False
    if not isinstance(name, str):
        name = str(name)

    s = name.strip().lower()
    if not s:
        return False

    keywords = (
        "beløp",
        "belop",
        "amount",
        "sum",
        "saldo",
        "mva",
        "vat",
        "debet",
        "debit",
        "kredit",
        "credit",
        "netto",
        "brutto",
        "%",
    )
    return any(k in s for k in keywords)


def is_percent_col(name: Any) -> bool:
    """Heuristikk: kolonnenavn som typisk er prosent."""
    if name is None:
        return False
    if not isinstance(name, str):
        name = str(name)

    s = name.strip().lower()
    if not s:
        return False

    return ("%" in s) or ("prosent" in s) or ("pct" in s) or ("percentage" in s)


__all__ = [
    "format_number_no",
    "format_int_no",
    "format_date_no",
    "fmt_amount",
    "fmt_int",
    "fmt_date",
    "format_date",
    "is_number_like_col",
    "is_percent_col",
]
