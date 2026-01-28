"""Felles hjelpefunksjoner for motpost-analyse.

Denne modulen samler små, robuste hjelpefunksjoner som brukes på tvers av
motpost-relatert logikk (data, kombinasjoner og Excel-export).

Mål:
- Unngå duplisert kode i flere motpost-moduler.
- Ha konsistente normaliseringsregler for konto/bilag og tall.

NB: Funksjonsnavnene bruker underscore-prefiks for å signalisere "internt"
bruk i prosjektet, men de er bevisst lagt i egen modul for å kunne gjenbrukes.
"""

from __future__ import annotations

from typing import Any
import math
import re

from konto_utils import konto_to_str


_WS_RE = re.compile(r"\s+")


def _clean_name(value: Any) -> str:
    """Rens og normaliser et kontonavn/tekst.

    - None -> ""
    - erstatter NBSP og linjeskift med mellomrom
    - kollapser flere mellomrom
    """

    if value is None:
        return ""
    s = str(value)
    s = s.replace("\xa0", " ").replace("\n", " ").replace("\r", " ")
    s = s.strip()
    s = _WS_RE.sub(" ", s)
    return s


def _konto_str(value: Any) -> str:
    """Normaliser konto til streng."""

    return konto_to_str(value)


def _bilag_str(value: Any) -> str:
    """Normaliser bilag til streng."""

    if value is None:
        return ""

    # Excel/Pandas gir ofte bilag som float (f.eks. 2501.0). Vi vil ha "2501".
    try:
        # bool er en underklasse av int i Python – men gir ikke mening her.
        if isinstance(value, bool):
            return str(int(value))
        if isinstance(value, (int,)):
            return str(value)
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return str(value)
    except Exception:
        pass

    s=str(value).strip()
    # "2501,0" -> "2501" (best effort)
    if s.endswith(",0") and s.replace(",",".").replace(".","",1).isdigit():
        s=s[:-2]
    return s


def _safe_float(x: Any) -> float:
    """Gjør et tallfelt robust til float.

    Håndterer:
    - None -> 0.0
    - tom streng -> 0.0
    - "1 234,50" / "1234,50" -> 1234.5
    - NaN/inf -> 0.0
    """

    if x is None:
        return 0.0

    try:
        if isinstance(x, str):
            s = x.strip().replace("\xa0", " ")
            s = s.replace(" ", "")
            if s == "":
                return 0.0
            # Norsk/Europeisk desimal -> punktum
            if "," in s and "." not in s:
                s = s.replace(",", ".")
            val = float(s)
        else:
            val = float(x)

        if math.isnan(val) or math.isinf(val):
            return 0.0
        return val
    except Exception:
        return 0.0
