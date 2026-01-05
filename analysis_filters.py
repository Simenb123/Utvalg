from __future__ import annotations

"""
analysis_filters.py

Small, testable helpers for the Analyse-tab filtering.

Design goals
- Be tolerant to small UI/API naming differences (e.g. `query` vs `search`)
  so the GUI doesn't break due to a keyword mismatch.
- Keep the filtering semantics stable and covered by tests.

Filtering rules (current)
- `direction`:
    - "Alle": no sign filtering
    - "Debet" (or "Inngående"): keep Beløp > 0
    - "Kredit" (or "Utgående"): keep Beløp < 0
- Amount thresholds are applied on ABS(Beløp), except:
    - when BOTH min and max are set:
        * Positive values must satisfy: min <= Beløp <= max
        * Negative values are only constrained by max (ABS(Beløp) <= max)
- Account filtering:
    - `accounts`: exact account numbers (e.g. 1500, 2400)
    - account-series (kontoserier): first digit of account (0-9)
      can be supplied via `konto_series` / `kontoserier` / `series`,
      or mixed into `accounts` as single-digit values.
"""

from typing import Any, Iterable, Optional

import pandas as pd


def parse_amount(value: Any) -> Optional[float]:
    """
    Parse an amount from user input.

    Accepts:
      - None / "" / whitespace -> None
      - numbers -> float(number)
      - strings like "1 234,56", "1234.56", "-1 234,56" (NBSP) -> float
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    # Normalise common thousand separators and decimal comma.
    # Keep digits, minus, comma, dot. Remove spaces and NBSP etc.
    s = s.replace("\u00A0", " ").replace("\u202F", " ")
    s = s.replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _as_iterable(value: Any) -> list[Any]:
    if value is None:
        return []
    # strings should be treated as scalars, not iterables of chars
    if isinstance(value, (str, bytes, int)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def filter_dataset(
    df: pd.DataFrame,
    search: str | None = None,
    *,
    query: str | None = None,
    direction: str = "Alle",
    min_amount: float | None = None,
    max_amount: float | None = None,
    accounts: Iterable[str | int] | None = None,
    konto_series: Iterable[str | int] | None = None,
    kontoserier: Iterable[str | int] | None = None,
    series: Iterable[str | int] | None = None,
    **_: Any,
) -> pd.DataFrame:
    """
    Filter a dataset by text, direction, amount thresholds and account filters.

    The function is intentionally tolerant to keyword naming differences:
    - `query` is treated as an alias for `search` (used by some GUI code).
    - Account-series can be provided via `konto_series`, `kontoserier` or `series`.
    - Unknown extra keyword args are ignored so the GUI won't crash if it passes
      a field that an older/newer version doesn't use.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df

    # Alias handling
    if (search is None or str(search).strip() == "") and query:
        search = query

    # 1) Search filter
    s = str(search).strip() if search is not None else ""
    if s:
        s_lower = s.lower()
        cols = [c for c in ("Konto", "Kontonavn", "Tekst", "Kundenr", "Bilag") if c in out.columns]
        if cols:
            mask = pd.Series(False, index=out.index)
            for c in cols:
                mask |= out[c].astype(str).str.lower().str.contains(s_lower, na=False)
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 2) Direction (sign) filter (requires Beløp)
    if "Beløp" in out.columns:
        belop_series = pd.to_numeric(out["Beløp"], errors="coerce")
        dir_norm = str(direction or "Alle").strip().lower()
        if dir_norm in {"debet", "inngående", "inngaaende", "inn"}:
            out = out.loc[belop_series > 0]
        elif dir_norm in {"kredit", "utgående", "utgaaende", "ut"}:
            out = out.loc[belop_series < 0]

    if out.empty:
        return out.copy()

    # 3) Amount thresholds (requires Beløp)
    if "Beløp" in out.columns and (min_amount is not None or max_amount is not None):
        belop = pd.to_numeric(out["Beløp"], errors="coerce")
        abs_amount = belop.abs()

        if min_amount is not None and max_amount is not None:
            pos_mask = (belop >= float(min_amount)) & (belop <= float(max_amount))
            neg_mask = (belop < 0) & (abs_amount <= float(max_amount))
            out = out.loc[pos_mask | neg_mask]
        elif min_amount is not None:
            out = out.loc[abs_amount >= float(min_amount)]
        elif max_amount is not None:
            out = out.loc[abs_amount <= float(max_amount)]

    if out.empty:
        return out.copy()

    # 4) Account-series / accounts filters
    konto_col = "Konto"
    if konto_col in out.columns:
        konto_str = out[konto_col].astype(str).str.strip()

        # Collect account-series (first digit)
        series_vals: set[str] = set()
        for src in (konto_series, kontoserier, series):
            for v in _as_iterable(src):
                sv = str(v).strip()
                if sv:
                    series_vals.add(sv)

        # Also accept single-digit values inside `accounts` as series filters
        acct_vals: set[str] = set()
        for v in _as_iterable(accounts):
            sv = str(v).strip()
            if not sv:
                continue
            if sv.isdigit() and len(sv) == 1:
                series_vals.add(sv)
            else:
                acct_vals.add(sv)

        if series_vals:
            first_digit = konto_str.str[0].fillna("")
            out = out.loc[first_digit.isin(series_vals)]

        if acct_vals:
            out = out.loc[konto_str.isin(acct_vals)]

    return out.copy()
