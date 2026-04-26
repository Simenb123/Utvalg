from __future__ import annotations

"""
analysis_filters.py

Small, testable helpers for the Analyse-tab filtering.

Design goals
- Be tolerant to small UI/API naming differences (for example `query` vs `search`)
  so the GUI does not break due to a keyword mismatch.
- Keep the filtering semantics stable and covered by tests.

Filtering rules
- `direction`:
    - "Alle": no sign filtering
    - "Debet" (or "Inngaaende"): keep Belop > 0
    - "Kredit" (or "Utgaaende"): keep Belop < 0
- Amount thresholds are applied on ABS(Belop), except:
    - when BOTH min and max are set:
        * Positive values must satisfy: min <= Belop <= max
        * Negative values are only constrained by max (ABS(Belop) <= max)
- Account filtering:
    - `accounts`: exact account numbers (for example 1500, 2400)
    - account-series (kontoserier): first digit of account (0-9)
      can be supplied via `konto_series` / `kontoserier` / `series`,
      or mixed into `accounts` as single-digit values.
"""

import re
from typing import Any, Iterable, Optional

import pandas as pd


def parse_amount(value: Any) -> Optional[float]:
    """
    Parse an amount from user input.

    Accepts:
      - None / "" / whitespace -> None
      - numbers -> float(number)
      - strings like "1 234,56", "1234.56", "-1 234,56" -> float
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

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
    if isinstance(value, (str, bytes, int)):
        return [value]
    try:
        return list(value)
    except TypeError:
        return [value]


def _find_first_column(df: pd.DataFrame, names: Iterable[str]) -> str | None:
    for name in names:
        if name in df.columns:
            return name
    return None


def _nonempty_text_mask(series: pd.Series) -> pd.Series:
    text = series.astype(str).str.strip()
    return text.ne("") & ~text.str.lower().isin({"nan", "none", "<na>"})


def _parse_datetime_series(series: pd.Series) -> pd.Series:
    text = series.astype("string").fillna("").astype(str).str.strip()
    dt = pd.Series(pd.NaT, index=text.index, dtype="datetime64[ns]")

    iso_mask = text.str.match(r"^\d{4}-\d{1,2}-\d{1,2}(?:[ T].*)?$", na=False)
    if iso_mask.any():
        dt.loc[iso_mask] = pd.to_datetime(text.loc[iso_mask], errors="coerce")

    remaining = dt.isna() & text.ne("")
    if remaining.any():
        try:
            parsed = pd.to_datetime(text.loc[remaining], errors="coerce", dayfirst=True, format="mixed")
        except TypeError:
            parsed = pd.to_datetime(text.loc[remaining], errors="coerce", dayfirst=True)
            if parsed.isna().any():
                parsed2 = pd.to_datetime(text.loc[remaining], errors="coerce")
                parsed = parsed.fillna(parsed2)
        dt.loc[remaining] = parsed

    return dt


def _parse_single_date(value: Any) -> pd.Timestamp | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = _parse_datetime_series(pd.Series([text])).iloc[0]
    if pd.isna(parsed):
        return None
    return parsed.normalize()


def _parse_month_value(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        month = int(text)
    except Exception:
        return None
    if 1 <= month <= 12:
        return month
    return None


def _split_filter_tokens(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        raw: list[str] = []
        for item in value:
            raw.extend(_split_filter_tokens(item))
        return raw

    tokens = re.split(r"[,\s;|]+", str(value).strip())
    out: list[str] = []
    for token in tokens:
        t = _normalize_code_value(token)
        if t:
            out.append(t)
    return out


def _normalize_code_value(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered in {"nan", "none", "<na>"}:
        return ""
    parsed = parse_amount(text)
    if parsed is not None and abs(parsed - round(parsed)) < 1e-9:
        return str(int(round(parsed)))
    return text.upper()


def filter_dataset(
    df: pd.DataFrame,
    search: str | None = None,
    *,
    query: str | None = None,
    bilag: str | None = None,
    motpart: str | None = None,
    period_from: str | int | None = None,
    period_to: str | int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str = "Alle",
    min_amount: float | None = None,
    max_amount: float | None = None,
    accounts: Iterable[str | int] | None = None,
    konto_series: Iterable[str | int] | None = None,
    kontoserier: Iterable[str | int] | None = None,
    series: Iterable[str | int] | None = None,
    mva_code: str | Iterable[str] | None = None,
    mva_codes: Iterable[str] | None = None,
    mva_mode: str | None = None,
    search_cols: Iterable[str] | None = None,
    **_: Any,
) -> pd.DataFrame:
    """
    Filter a dataset by text, period, voucher, amount and account filters.

    Unknown extra keyword args are ignored so the GUI will not crash if it
    passes a field that an older/newer version does not use.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df

    if (search is None or str(search).strip() == "") and query:
        search = query

    # 1) General search
    # Hvis search_cols er gitt (typisk via Ctrl+klikk-merking i UI),
    # søk KUN i de valgte kolonnene. Ellers fall tilbake på et
    # utvidet default-sett som dekker både tekst- og tall-/kode-kolonner.
    search_text = str(search or "").strip().lower()
    if search_text:
        if search_cols:
            cols = [c for c in search_cols if c in out.columns]
        else:
            cols = [
                c
                for c in (
                    "Konto",
                    "Kontonavn",
                    "Tekst",
                    "Kundenr",
                    "Kundenavn",
                    "Leverandørnr",
                    "Leverandørnavn",
                    "Bilag",
                    "Beløp",
                    "Dato",
                    "MVA-kode",
                    "Regnr",
                    "Regnskapslinje",
                )
                if c in out.columns
            ]
        if cols:
            mask = pd.Series(False, index=out.index)
            for c in cols:
                mask |= out[c].astype(str).str.lower().str.contains(search_text, na=False)
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 2) Bilag filter
    bilag_text = str(bilag or "").strip().lower()
    if bilag_text:
        bilag_col = _find_first_column(out, ("Bilag", "bilag"))
        if bilag_col is not None:
            mask = out[bilag_col].astype(str).str.lower().str.contains(bilag_text, na=False)
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 3) Motpart filter
    motpart_text = str(motpart or "").strip().lower()
    if motpart_text:
        motpart_cols = [
            c
            for c in (
                "Kunder",
                "kunder",
                "Kundenr",
                "kundenr",
                "Kundenavn",
                "kundenavn",
                "Leverandørnr",
                "leverandørnr",
                "Leverandornr",
                "leverandornr",
                "Leverandørnavn",
                "leverandørnavn",
                "Leverandornavn",
                "leverandornavn",
                "Motpart",
                "motpart",
                "Kunde",
                "kunde",
                "Customer",
                "customer",
                "CustomerName",
                "customername",
                "Leverandør",
                "leverandør",
                "Leverandor",
                "leverandor",
            )
            if c in out.columns
        ]
        if motpart_cols:
            mask = pd.Series(False, index=out.index)
            for c in motpart_cols:
                mask |= out[c].astype(str).str.lower().str.contains(motpart_text, na=False)
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 4) Period filter
    month_from = _parse_month_value(period_from)
    month_to = _parse_month_value(period_to)
    if month_from is not None or month_to is not None:
        date_col = _find_first_column(out, ("Dato", "dato", "Bilagsdato", "bilagsdato"))
        if date_col is not None:
            dt = _parse_datetime_series(out[date_col])
            months = dt.dt.month
            mask = dt.notna()
            if month_from is not None:
                mask &= months >= month_from
            if month_to is not None:
                mask &= months <= month_to
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 5) Optional exact date range
    dt_from = _parse_single_date(date_from)
    dt_to = _parse_single_date(date_to)
    if dt_from is not None or dt_to is not None:
        date_col = _find_first_column(out, ("Dato", "dato", "Bilagsdato", "bilagsdato"))
        if date_col is not None:
            dt = _parse_datetime_series(out[date_col]).dt.normalize()
            mask = dt.notna()
            if dt_from is not None:
                mask &= dt >= dt_from
            if dt_to is not None:
                mask &= dt <= dt_to
            out = out.loc[mask]

    if out.empty:
        return out.copy()

    # 6) Direction (sign) filter
    if "Beløp" in out.columns:
        belop_series = pd.to_numeric(out["Beløp"], errors="coerce")
        dir_norm = str(direction or "Alle").strip().lower()
        if dir_norm in {"debet", "inngående", "inngaaende", "inn"}:
            out = out.loc[belop_series > 0]
        elif dir_norm in {"kredit", "utgående", "utgaaende", "ut"}:
            out = out.loc[belop_series < 0]

    if out.empty:
        return out.copy()

    # 7) Amount thresholds
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

    # 8) Account-series / accounts filters
    konto_col = "Konto"
    if konto_col in out.columns:
        konto_str = out[konto_col].astype(str).str.strip()

        series_vals: set[str] = set()
        for src in (konto_series, kontoserier, series):
            for v in _as_iterable(src):
                sv = str(v).strip()
                if sv:
                    series_vals.add(sv)

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

    if out.empty:
        return out.copy()

    # 9) MVA filters
    mva_code_col = _find_first_column(out, ("MVA-kode", "mva-kode", "Mva", "mva"))
    mva_amount_col = _find_first_column(out, ("MVA-beløp", "MVA-belop", "mva-beløp", "mva-belop"))

    mva_tokens = _split_filter_tokens(mva_codes if mva_codes is not None else mva_code)
    if mva_tokens:
        if mva_code_col is None:
            return out.iloc[0:0].copy()
        code_text = out[mva_code_col].map(_normalize_code_value)
        out = out.loc[code_text.isin(mva_tokens)]

    if out.empty:
        return out.copy()

    mode = str(mva_mode or "Alle").strip().lower()
    if mode and mode not in {"alle", ""}:
        has_code = (
            _nonempty_text_mask(out[mva_code_col])
            if mva_code_col is not None
            else pd.Series(False, index=out.index)
        )
        if mva_amount_col is not None:
            mva_amount = pd.to_numeric(out[mva_amount_col], errors="coerce")
            has_amount = mva_amount.notna() & (mva_amount.abs() > 1e-9)
        else:
            has_amount = pd.Series(False, index=out.index)

        if mode in {"med mva-kode", "kun med mva-kode"}:
            out = out.loc[has_code]
        elif mode in {"uten mva-kode", "kun uten mva-kode"}:
            out = out.loc[~has_code]
        elif mode in {"med mva-beløp", "med mva-belop", "kun med mva-beløp", "kun med mva-belop"}:
            out = out.loc[has_amount]
        elif mode in {"uten mva-beløp", "uten mva-belop", "kun uten mva-beløp", "kun uten mva-belop"}:
            out = out.loc[~has_amount]
        elif mode in {"mva-avvik", "avvik"}:
            out = out.loc[has_code ^ has_amount]

    return out.copy()
