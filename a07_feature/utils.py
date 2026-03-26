from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

import pandas as pd


D0 = Decimal("0")
Q2 = Decimal("0.01")
_RE_CLEAN = re.compile(r"[^\d,.\-+() ]+")


def dec_round(x: Decimal, q: Decimal = Q2) -> Decimal:
    return x.quantize(q, rounding=ROUND_HALF_UP)


def nb_to_decimal(x: Any) -> Decimal:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return D0
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        return Decimal(int(x))
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        return Decimal(str(x))

    s = str(x).strip()
    if not s:
        return D0

    s = _RE_CLEAN.sub("", s).strip()
    if not s:
        return D0

    neg = False
    if s.endswith("-"):
        neg = True
        s = s[:-1].strip()
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()

    s = s.replace(" ", "")

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")

    try:
        d = Decimal(s)
    except (InvalidOperation, ValueError):
        return D0

    return -d if neg else d


def to_decimal(x: Any) -> Decimal:
    return nb_to_decimal(x)
