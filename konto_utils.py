"""Utilities for handling Norwegian account codes ("Konto").

In practice, account codes often come from Excel and can show up as:
- int (1002)
- float (1002.0)
- string ("1002" or "1002.0")

If different parts of the UI normalise differently, selections/filters break
(e.g. Analyse -> Utvalg).

This module provides a single, shared normalisation.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def konto_to_str(x: Any) -> str:
    """Normalise a Konto/Bilag-like value to a plain string.

    Rules:
    - None/NaN/NaT -> ""
    - 1002.0 -> "1002"
    - "1002.0" -> "1002"
    - " 1002 " -> "1002"

    This is intentionally forgiving and should be safe to use for filtering
    and UI display.
    """

    if x is None:
        return ""

    # pandas missing values (also covers pd.NaT)
    try:
        if pd.isna(x):
            return ""
    except Exception:
        # pd.isna may raise for some exotic objects; fall back below
        pass

    # Fast-path for numeric types
    if isinstance(x, float):
        if np.isnan(x):
            return ""
        if x.is_integer():
            return str(int(x))
        s = str(x)
        return s.rstrip("0").rstrip(".")

    if isinstance(x, (int, np.integer)):
        return str(int(x))

    s = str(x).strip()
    if not s:
        return ""

    # Common Excel artefact when numbers are read as floats
    if s.endswith(".0"):
        head = s[:-2]
        # Allow leading minus for completeness
        if head.replace("-", "").isdigit():
            return head

    return s


def first_digit(x: Any) -> str:
    """Return the first digit of a normalised Konto string (or empty string)."""

    s = konto_to_str(x)
    return s[0] if s else ""
