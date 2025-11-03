from __future__ import annotations
import numpy as np
import pandas as pd

from models import Columns, FilterState
from io_utils import fmt_amount


# -------------------------- FILTER & PIVOT ------------------------------

def apply_filters(df: pd.DataFrame, c: Columns, f: FilterState) -> pd.DataFrame:
    """Filtrer etter retning og beløpsintervall."""
    if df is None or df.empty:
        return df
    out = df
    if f.direction.lower().startswith("debet"):
        out = out[out[c.belop] > 0]
    elif f.direction.lower().startswith("kredit"):
        out = out[out[c.belop] < 0]
    if f.min_amount is not None:
        out = out[out[c.belop] >= f.min_amount]
    if f.max_amount is not None:
        out = out[out[c.belop] <= f.max_amount]
    return out


def pivot_accounts(df_view: pd.DataFrame, c: Columns) -> pd.DataFrame:
    if df_view is None or df_view.empty:
        return pd.DataFrame(columns=[c.konto, c.kontonavn, "Antall", "Sum"])
    grp = (
        df_view.groupby([c.konto, c.kontonavn])[c.belop]
        .agg(Antall="count", Sum="sum")
        .reset_index()
        .sort_values([c.konto, c.kontonavn])
    )
    return grp


# ------------------------ DESKRIPTIV STATISTIKK ------------------------

def describe_amounts(df_view: pd.DataFrame, c: Columns) -> dict:
    if df_view is None or df_view.empty:
        return {
            "linjer": 0, "bilag_unike": 0, "konto_unike": 0,
            "sum": fmt_amount(0), "debet": fmt_amount(0), "kredit": fmt_amount(0),
            "min": "", "p25": "", "median": "", "p75": "", "maks": "",
            "snitt": "", "std": ""
        }
    s = df_view[c.belop].dropna().astype(float)
    deb = s[s > 0].sum()
    kre = s[s < 0].sum()
    d = {
        "linjer": int(len(df_view)),
        "bilag_unike": int(df_view[c.bilag].astype(str).nunique()),
        "konto_unike": int(df_view[c.konto].nunique()),
        "sum": fmt_amount(s.sum()),
        "debet": fmt_amount(deb),
        "kredit": fmt_amount(abs(kre)),  # vis som positiv størrelse
        "min": fmt_amount(s.min()) if not s.empty else "",
        "p25": fmt_amount(float(s.quantile(0.25))) if not s.empty else "",
        "median": fmt_amount(float(s.median())) if not s.empty else "",
        "p75": fmt_amount(float(s.quantile(0.75))) if not s.empty else "",
        "maks": fmt_amount(s.max()) if not s.empty else "",
        "snitt": fmt_amount(float(s.mean())) if not s.empty else "",
        "std": fmt_amount(float(s.std(ddof=1))) if len(s) > 1 else "",
    }
    return d


# --------------------------- UNDERPOPULASJON ---------------------------

def make_bucket_edges(values: pd.Series, n_buckets: int, method: str) -> np.ndarray:
    if n_buckets <= 0:
        return np.array([])
    if method == "equal":
        lo, hi = float(values.min()), float(values.max())
        if lo == hi:
            edges = np.array([lo, hi])
        else:
            edges = np.linspace(lo, hi, n_buckets + 1)
    else:  # "quantile"
        qs = np.linspace(0, 1, n_buckets + 1)
        edges = values.quantile(qs).to_numpy()
    # Sørg for strengt stigende grenser
    for i in range(1, len(edges)):
        if edges[i] <= edges[i - 1]:
            edges[i] = edges[i - 1] + 1e-8
    return edges


def bucket_summary(df_view: pd.DataFrame, c: Columns, n_buckets: int, method: str, basis: str) -> pd.DataFrame:
    """
    Lag bøtter og oppsummer:
    - 'basis' := "abs" -> bruk |beløp| som sorteringsgrunnlag
               := "signed" -> bruk beløp
    - 'method' := "quantile" eller "equal"
    """
    if n_buckets <= 0 or df_view is None or df_view.empty:
        return pd.DataFrame(columns=["Fra", "Til", "Linjer", "Unike bilag", "Sum (netto)", "Sum |beløp|", "Andel linjer", "Andel sum| |"])
    s = df_view[c.belop].astype(float)
    ground = s.abs() if basis == "abs" else s
    edges = make_bucket_edges(ground, n_buckets, method)
    labels = [f"{fmt_amount(edges[i])} – {fmt_amount(edges[i+1])}" for i in range(n_buckets)]
    cats = pd.cut(ground, bins=edges, include_lowest=True, labels=labels)
    pop = df_view.assign(_bucket=cats)
    tab = (
        pop.groupby("_bucket", dropna=False)
        .agg(
            Linjer=(c.belop, "count"),
            **{"Unike bilag": (c.bilag, lambda x: x.astype(str).nunique())},
            **{"Sum (netto)": (c.belop, "sum")},
            **{"Sum |beløp|": (c.belop, lambda x: x.abs().sum())},
        )
        .reset_index()
        .rename(columns={"_bucket": "Intervall"})
    )
    tot_linjer = int(len(df_view))
    tot_abs = float(s.abs().sum())
    tab["Andel linjer"] = (tab["Linjer"] / max(1, tot_linjer)).astype(float)
    tab["Andel sum| |"] = (tab["Sum |beløp|"] / max(1e-12, tot_abs)).astype(float)
    # Splitt "Intervall" til "Fra"/"Til" for penere eksport/visning
    tab["Fra"] = tab["Intervall"].str.split(" – ").str[0]
    tab["Til"] = tab["Intervall"].str.split(" – ").str[1]
    cols = ["Fra", "Til", "Linjer", "Unike bilag", "Sum (netto)", "Sum |beløp|", "Andel linjer", "Andel sum| |"]
    return tab[cols]
