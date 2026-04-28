"""selection_studio_adapters.py

Små, testbare hjelpefunksjoner som brukes av SelectionStudio/Utvalg-UI.

Målet er at logikken her skal være fri for tkinter, slik at den er enkel å
unit-teste.
"""

from __future__ import annotations

from typing import Any, Union

import numpy as np
import pandas as pd


# ---------------------------
# Bilag-adapter (bilag-nivå)
# ---------------------------

_EN_DASH = "–"


def _fmt_no_1(x: float) -> str:
    """Norwegian-ish number formatting: one decimal, decimal comma."""
    try:
        xf = float(x)
    except Exception:
        return ""
    return f"{xf:.1f}".replace(".", ",")


def _format_interval(lo: float, hi: float) -> str:
    """Format as 'lo – hi' with decimal comma and en-dash."""
    return f"{_fmt_no_1(lo)} {_EN_DASH} {_fmt_no_1(hi)}"


def build_bilag_dataframe(
    df: pd.DataFrame,
    *,
    bilag_col: str = "Bilag",
    amount_col: str = "Beløp",
    date_col: str = "Dato",
    text_col: str = "Tekst",
) -> pd.DataFrame:
    """Bygg bilag-nivå DataFrame.

    - Aksepterer transaksjonsnivå (Bilag + Beløp/Belop) og summerer til SumBeløp
    - Aksepterer også allerede aggregert input med SumBeløp
    - Sørger for at kolonnene [Bilag, Dato, Tekst, SumBeløp] alltid finnes (i den rekkefølgen)
    """
    sum_col = "SumBeløp"

    def _empty() -> pd.DataFrame:
        cols: list[str] = [bilag_col]
        if date_col:
            cols.append(date_col)
        if text_col:
            cols.append(text_col)
        cols.append(sum_col)
        return pd.DataFrame(columns=cols)

    if df is None or df.empty:
        return _empty()

    if bilag_col not in df.columns:
        raise KeyError(bilag_col)

    # Finn riktig beløpskolonne
    amt_col = amount_col
    if amt_col not in df.columns and amt_col == "Beløp" and "Belop" in df.columns:
        amt_col = "Belop"

    # Case: allerede aggregert
    if amt_col not in df.columns and sum_col in df.columns:
        out = df.copy()

        # Sørg for dato/tekst kolonner
        if date_col and date_col not in out.columns:
            out[date_col] = ""
        if text_col and text_col not in out.columns:
            out[text_col] = ""

        cols: list[str] = [bilag_col]
        if date_col:
            cols.append(date_col)
        if text_col:
            cols.append(text_col)
        cols.append(sum_col)

        out = out[cols].drop_duplicates(subset=[bilag_col]).reset_index(drop=True)
        out[sum_col] = pd.to_numeric(out[sum_col], errors="coerce").fillna(0.0).astype(float)
        return out

    # Case: må aggregere fra transaksjoner
    if amt_col not in df.columns:
        raise KeyError(amount_col)

    work = df.copy()
    work[amt_col] = pd.to_numeric(work[amt_col], errors="coerce").fillna(0.0)

    # Vi vil alltid ha Dato/Tekst i output (om parametrene er satt)
    if date_col and date_col not in work.columns:
        work[date_col] = ""
    if text_col and text_col not in work.columns:
        work[text_col] = ""

    agg: dict[str, Any] = {amt_col: "sum"}
    if date_col:
        agg[date_col] = "first"
    if text_col:
        agg[text_col] = "first"

    out = work.groupby(bilag_col, as_index=False).agg(agg).rename(columns={amt_col: sum_col})

    cols2: list[str] = [bilag_col]
    if date_col:
        cols2.append(date_col)
    if text_col:
        cols2.append(text_col)
    cols2.append(sum_col)

    out = out[cols2]
    out[sum_col] = out[sum_col].astype(float)
    return out


def compute_specific_selection_recommendation_df(
    df_bilag: pd.DataFrame,
    *,
    selection_size: int,
    random_state: int = 0,
    bilag_col: str = "Bilag",
) -> pd.DataFrame:
    """Returner et spesifikt utvalg (bilag-rader) på en stabil måte.

    Dette er en enkel adapter som brukes i noen tester og i UI flow.
    """
    if df_bilag is None or df_bilag.empty or selection_size <= 0:
        return pd.DataFrame(columns=list(df_bilag.columns) if isinstance(df_bilag, pd.DataFrame) else [])

    rng = np.random.RandomState(random_state)
    selection_size = min(selection_size, len(df_bilag))

    # Stabilt utvalg: shuffle indeks, velg N første
    idx = np.array(df_bilag.index)
    rng.shuffle(idx)
    picked = idx[:selection_size]

    out = df_bilag.loc[picked].copy()
    if bilag_col in out.columns:
        out = out.sort_values(by=[bilag_col]).reset_index(drop=True)
    else:
        out = out.reset_index(drop=True)
    return out


# ---------------------------
# Stratifisering (bilag-sum)
# ---------------------------


def _stratify_series(
    s: pd.Series,
    *,
    method: str,
    k: int,
    use_abs: bool,
) -> tuple[list[tuple[int, pd.Series]], dict[str, str], pd.DataFrame, pd.Series]:
    """Kjernestratifisering for en Series.

    Returnerer:
      - groups: [(gruppe_id:int, maske:Series[bool])]
      - interval_map: {\"1\": \"lo – hi\", ...}
      - stats_df: DataFrame med Gruppe/Antall/Sum/Min/Max
      - grp_codes: Series med gruppe_id pr indeks (int, starter på 1)
    """
    if s is None or len(s) == 0:
        empty_stats = pd.DataFrame(columns=["Gruppe", "Antall", "Sum", "Min", "Max"])
        return [], {}, empty_stats, pd.Series(dtype=int)

    # Normaliser k
    k = int(k) if k is not None else 1
    if k < 1:
        k = 1

    work = s.copy()
    if use_abs:
        work = work.abs()

    # Fallback: alt i én gruppe om ikke nok variasjon
    if k < 2 or work.nunique(dropna=True) < 2:
        grp_codes = pd.Series(1, index=work.index, dtype=int)
        mask = pd.Series(True, index=work.index)
        g_min = float(work.min()) if len(work) else 0.0
        g_max = float(work.max()) if len(work) else 0.0
        interval_map = {"1": _format_interval(g_min, g_max)}
        stats_df = pd.DataFrame(
            [
                {
                    "Gruppe": 1,
                    "Antall": int(mask.sum()),
                    "Sum": float(work.sum()),
                    "Min": g_min,
                    "Max": g_max,
                }
            ]
        )
        return [(1, mask)], interval_map, stats_df, grp_codes

    # Lag bins
    try:
        if method == "quantile":
            bins = pd.qcut(work, q=k, duplicates="drop")
        elif method == "equal_width":
            bins = pd.cut(work, bins=k, include_lowest=True)
        else:
            raise ValueError(f"Unknown method: {method}")
    except Exception:
        # Robust fallback
        grp_codes = pd.Series(1, index=work.index, dtype=int)
        mask = pd.Series(True, index=work.index)
        g_min = float(work.min()) if len(work) else 0.0
        g_max = float(work.max()) if len(work) else 0.0
        interval_map = {"1": _format_interval(g_min, g_max)}
        stats_df = pd.DataFrame(
            [
                {
                    "Gruppe": 1,
                    "Antall": int(mask.sum()),
                    "Sum": float(work.sum()),
                    "Min": g_min,
                    "Max": g_max,
                }
            ]
        )
        return [(1, mask)], interval_map, stats_df, grp_codes

    # qcut/cut gir kategorier; map til int labels 1..n
    codes = bins.cat.codes  # -1 for NaN
    grp_codes = (codes + 1).astype(int)

    # Hvis alt havnet i én gruppe pga duplicates/drop: fallback
    unique_groups = sorted([g for g in grp_codes.unique().tolist() if g > 0])
    if len(unique_groups) < 2:
        grp_codes = pd.Series(1, index=work.index, dtype=int)
        mask = pd.Series(True, index=work.index)
        g_min = float(work.min())
        g_max = float(work.max())
        interval_map = {"1": _format_interval(g_min, g_max)}
        stats_df = pd.DataFrame(
            [
                {
                    "Gruppe": 1,
                    "Antall": int(mask.sum()),
                    "Sum": float(work.sum()),
                    "Min": g_min,
                    "Max": g_max,
                }
            ]
        )
        return [(1, mask)], interval_map, stats_df, grp_codes

    # Sørg for at labels er sammenhengende fra 1..n
    remap = {old: new for new, old in enumerate(unique_groups, start=1)}
    grp_codes = grp_codes.map(remap).astype(int)

    groups: list[tuple[int, pd.Series]] = []
    interval_map: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    for g in sorted(grp_codes.unique()):
        if g <= 0:
            continue
        mask = pd.Series(grp_codes == g, index=work.index)
        groups.append((int(g), mask))

        g_vals = work[mask]
        g_min = float(g_vals.min()) if len(g_vals) else 0.0
        g_max = float(g_vals.max()) if len(g_vals) else 0.0
        interval_map[str(int(g))] = _format_interval(g_min, g_max)

        rows.append(
            {
                "Gruppe": int(g),
                "Antall": int(mask.sum()),
                "Sum": float(g_vals.sum()),
                "Min": g_min,
                "Max": g_max,
            }
        )

    stats_df = pd.DataFrame(rows)
    return groups, interval_map, stats_df, grp_codes


def stratify_bilag_sums(
    values: Union[pd.Series, pd.DataFrame],
    *,
    method: str = "quantile",
    k: int = 3,
    use_abs: bool = False,
    bilag_col: str = "Bilag",
    val_col: str = "SumBeløp",
) -> Any:
    """Stratifiser bilagsummer.

    - Series path (brukes av UI): returnerer (groups, interval_map[str->str], stats_df)
    - DataFrame path (brukes av adapter-tester): returnerer (stats_df, df_out, interval_map[int->str])
    """
    if isinstance(values, pd.DataFrame):
        df = values.copy()

        # Hvis vi ikke har SumBeløp, prøv å bygge bilag_df først
        if val_col not in df.columns:
            df = build_bilag_dataframe(df, bilag_col=bilag_col)
            if val_col not in df.columns:
                raise KeyError(val_col)

        s = pd.Series(df[val_col].values, index=df.index)

        groups, interval_map_str, stats_df, grp_codes = _stratify_series(
            s, method=method, k=k, use_abs=use_abs
        )

        df["__grp__"] = grp_codes.values
        df["Gruppe"] = df["__grp__"].apply(lambda g: f"Gruppe {int(g)}" if int(g) > 0 else "")
        df["Intervall"] = df["__grp__"].astype(str).map(interval_map_str).fillna("")

        # For DataFrame-path: testene forventer int keys
        interval_map_int = {int(k): v for k, v in interval_map_str.items()}

        return stats_df, df, interval_map_int

    # Series-path: UI og tester forventer string keys i interval_map
    s = pd.Series(values)
    groups, interval_map_str, stats_df, _grp_codes = _stratify_series(
        s, method=method, k=k, use_abs=use_abs
    )
    return groups, interval_map_str, stats_df


__all__ = [
    "build_bilag_dataframe",
    "stratify_bilag_sums",
    "compute_specific_selection_recommendation_df",
]
