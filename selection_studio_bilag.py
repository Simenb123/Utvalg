# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Dict, List, Tuple, Union
import math

import pandas as pd

__all__ = ["build_bilag_dataframe", "stratify_bilag_sums"]


def _is_nan(x: Any) -> bool:
    try:
        return math.isnan(float(x))
    except Exception:
        return False


def _format_number_no(value: Any, *, decimals: int = 1) -> str:
    """
    Norsk tallformat:
      - alltid 1 desimal (default)
      - desimalkomma
    """
    if value is None:
        return ""
    try:
        f = float(value)
    except Exception:
        return ""
    if _is_nan(f):
        return ""
    return f"{f:.{decimals}f}".replace(".", ",")


def _format_interval_no(lo: Any, hi: Any) -> str:
    # En-dash (U+2013) er viktig – testene sjekker for "–"
    return f"{_format_number_no(lo)} – {_format_number_no(hi)}"


def build_bilag_dataframe(
    df: pd.DataFrame,
    *,
    bilag_col: str = "Bilag",
    amount_col: str = "Beløp",
    date_col: str = "Dato",
    text_col: str = "Tekst",
) -> pd.DataFrame:
    """
    Bygg et bilag-nivå DataFrame fra transaksjonslinjer.

    Aksepterer enten:
      - transaksjonslinjer med (Bilag + Beløp/Belop)
      - allerede aggregert med (Bilag + SumBeløp)

    Returnerer DataFrame med kolonner:
      - Bilag
      - Dato (alltid med, fylles med "" hvis ikke finnes)
      - Tekst (alltid med, fylles med "" hvis ikke finnes)
      - SumBeløp
    """
    cols_out = [bilag_col, date_col, text_col, "SumBeløp"]

    if df is None or df.empty:
        return pd.DataFrame(columns=cols_out)

    if bilag_col not in df.columns:
        raise KeyError(bilag_col)

    work = df.copy()

    # Robusthet: "Belop" uten norsk tegn
    amt_col = amount_col
    if amt_col not in work.columns and amt_col == "Beløp" and "Belop" in work.columns:
        amt_col = "Belop"

    # Velg hvilken kolonne som skal summeres til SumBeløp
    if amt_col in work.columns:
        work["SumBeløp"] = pd.to_numeric(work[amt_col], errors="coerce").fillna(0.0)
    elif "SumBeløp" in work.columns:
        work["SumBeløp"] = pd.to_numeric(work["SumBeløp"], errors="coerce").fillna(0.0)
    else:
        # matcher forventningen i testene (KeyError på default amount_col)
        raise KeyError(amount_col)

    # Sørg for at Dato/Tekst alltid finnes i output
    if date_col not in work.columns:
        work[date_col] = ""
    if text_col not in work.columns:
        work[text_col] = ""

    out = (
        work.groupby(bilag_col, as_index=False)
        .agg(
            {
                "SumBeløp": "sum",
                date_col: "first",
                text_col: "first",
            }
        )
        .loc[:, cols_out]
    )

    return out


def _stratify_series(
    s: pd.Series,
    *,
    method: str = "quantile",
    k: int = 5,
    use_abs: bool = False,
) -> Tuple[List[Tuple[int, pd.Series]], Dict[str, str], pd.DataFrame]:
    """
    Series-path: returnerer (groups, interval_map, stats_df)

    groups: List[(gruppe_id:int, mask:pd.Series[bool])]
    interval_map: Dict[str(gruppe_id) -> "min – max" (norsk format)]
    stats_df: DataFrame med Gruppe(int), Antall, Sum, Min, Max
    """
    stats_cols = ["Gruppe", "Antall", "Sum", "Min", "Max"]

    if s is None or len(s) == 0:
        return [], {}, pd.DataFrame(columns=stats_cols)

    if not isinstance(s, pd.Series):
        s = pd.Series(s)

    vals = pd.to_numeric(s, errors="coerce")
    strat_vals = vals.abs() if use_abs else vals

    if strat_vals.dropna().empty:
        return [], {}, pd.DataFrame(columns=stats_cols)

    if not isinstance(k, int) or k < 1:
        k = 1

    # Antall bins kan ikke være større enn antall observasjoner
    n_bins = min(k, int(strat_vals.notna().sum()))
    if n_bins < 1:
        n_bins = 1

    try:
        if method == "quantile":
            bins = pd.qcut(strat_vals, q=n_bins, labels=False, duplicates="drop")
        elif method == "equal_width":
            bins = pd.cut(strat_vals, bins=n_bins, labels=False, include_lowest=True, duplicates="drop")
        else:
            raise ValueError(f"Ukjent stratifikasjonsmetode: {method!r}")
    except Exception:
        grp_ids = pd.Series(1, index=strat_vals.index, dtype=int)
    else:
        # bins er 0..(g-1) -> gruppe 1..g
        if bins is None or pd.Series(bins).dropna().empty:
            grp_ids = pd.Series(1, index=strat_vals.index, dtype=int)
        else:
            grp_ids = pd.Series(bins, index=strat_vals.index).astype(int) + 1

    # Remap til 1..G (sikrer contiguous labels)
    unique_labels = sorted(pd.unique(grp_ids))
    remap = {lab: i + 1 for i, lab in enumerate(unique_labels)}
    grp_ids = grp_ids.map(remap).astype(int)

    groups: List[Tuple[int, pd.Series]] = []
    interval_map: Dict[str, str] = {}
    rows: List[Dict[str, Any]] = []

    for lab in sorted(set(remap.values())):
        mask = grp_ids == lab
        groups.append((lab, mask))

        g_vals = vals[mask]              # original (signert)
        g_strat = strat_vals[mask]       # brukt til grense/min/max (abs hvis use_abs)

        antall = int(mask.sum())
        sum_ = float(g_vals.sum()) if antall else 0.0
        min_ = float(g_strat.min()) if antall else float("nan")
        max_ = float(g_strat.max()) if antall else float("nan")

        rows.append({"Gruppe": lab, "Antall": antall, "Sum": sum_, "Min": min_, "Max": max_})

        # Viktig for test: key er "1"/"2"/... og tekst inneholder "–"
        interval_map[str(lab)] = _format_interval_no(min_, max_)

    stats_df = pd.DataFrame(rows, columns=stats_cols)
    return groups, interval_map, stats_df


def stratify_bilag_sums(
    data: Union[pd.Series, pd.DataFrame],
    *,
    method: str = "quantile",
    k: int = 5,
    use_abs: bool = False,
    bilag_col: str = "Bilag",
    sum_col: str = "SumBeløp",
) -> Any:
    """
    Overload:
      - Series inn -> (groups, interval_map(str->str), stats_df)
      - DataFrame inn -> (summary_df, bilag_out_df, interval_map(int->str))

    Dette matcher testene:
      - interval_map keys i Series-path: {"1","2",...}
      - interval_map keys i DF-path: {1,2,...}
    """
    if isinstance(data, pd.DataFrame):
        df = data.copy()

        if bilag_col not in df.columns:
            raise KeyError(bilag_col)

        # Hvis vi får transaksjonslinjer uten SumBeløp, bygg bilag_df først
        if sum_col not in df.columns:
            # prøv Beløp/Belop
            if "Beløp" in df.columns or "Belop" in df.columns:
                df = build_bilag_dataframe(df, bilag_col=bilag_col)
            else:
                raise KeyError(sum_col)

        # Lag Series med bilag som index
        s = df.set_index(bilag_col)[sum_col]

        groups, interval_map_str, stats_df = _stratify_series(s, method=method, k=k, use_abs=use_abs)

        # Map bilag -> gruppe-id
        bilag_to_grp: Dict[Any, int] = {}
        for lab, mask in groups:
            for bilag in s.index[mask]:
                bilag_to_grp[bilag] = int(lab)

        bilag_out = df.copy()
        bilag_out["__grp__"] = bilag_out[bilag_col].map(bilag_to_grp).astype(int)

        # Visningskolonner (kan være nyttig i UI)
        bilag_out["Gruppe"] = bilag_out["__grp__"].astype(str)

        # DF-path: keys som int (test forventer dette)
        interval_map_int: Dict[int, str] = {int(k): v for k, v in interval_map_str.items()}
        bilag_out["Intervall"] = bilag_out["__grp__"].map(interval_map_int)

        summary = stats_df.copy()
        return summary, bilag_out, interval_map_int

    # Series-path
    return _stratify_series(pd.Series(data), method=method, k=k, use_abs=use_abs)
