from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List
import re
import numpy as np
import pandas as pd
from models import Columns

@dataclass
class ScopeCfg:
    name: str = "Populasjon"
    accounts_expr: str = ""
    direction: str = "Alle"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    apply_to: str = "Alle"
    use_abs: bool = True
    date_from: Optional[pd.Timestamp] = None
    date_to: Optional[pd.Timestamp] = None

@dataclass
class BucketCfg:
    n: int = 0
    method: str = "quantile"
    basis: str = "abs"

def _parse_accounts_expr(expr: str) -> List[str]:
    expr = (expr or "").strip()
    if not expr: return []
    parts = [e.strip() for e in expr.split(",") if e.strip()]
    return parts

def _acct_mask(series: pd.Series, tokens: List[str]) -> pd.Series:
    s = series.astype(str)
    mask = pd.Series(False, index=series.index)
    for t in tokens:
        if "-" in t and not "*" in t:
            lo, hi = t.split("-", 1)
            try:
                import re as _re
                lo_i = int(_re.sub(r"\D", "", lo))
                hi_i = int(_re.sub(r"\D", "", hi))
                mask |= series.astype("Int64").astype(int).between(lo_i, hi_i, inclusive="both")
            except Exception:
                continue
        elif "*" in t:
            pat = "^" + re.escape(t).replace("\\*", ".*") + "$"
            mask |= s.str.match(pat)
        else:
            try: v = int(re.sub(r"\D", "", t)); mask |= (series.astype("Int64").astype(int) == v)
            except Exception: mask |= (s == t)
    return mask

def apply_scope(df: pd.DataFrame, cols: Columns, cfg: ScopeCfg) -> pd.DataFrame:
    c = cols; d = df.copy()
    if getattr(c, "dato", None) and c.dato in d.columns:
        if cfg.date_from is not None:
            d = d[d[c.dato] >= cfg.date_from]
        if cfg.date_to is not None:
            d = d[d[c.dato] <= cfg.date_to]
    tokens = _parse_accounts_expr(cfg.accounts_expr)
    if tokens: d = d[_acct_mask(d[c.konto], tokens)]
    if cfg.direction.lower().startswith("debet"): d = d[d[c.belop] > 0]
    elif cfg.direction.lower().startswith("kredit"): d = d[d[c.belop] < 0]
    if cfg.min_amount is not None or cfg.max_amount is not None:
        s = d[c.belop].abs() if (cfg.use_abs and cfg.apply_to == "Alle") else d[c.belop]
        if cfg.apply_to.lower().startswith("debet"): s = d[c.belop][d[c.belop] > 0]
        elif cfg.apply_to.lower().startswith("kredit"): s = d[c.belop][d[c.belop] < 0]
        if cfg.min_amount is not None: d = d[s >= cfg.min_amount]
        if cfg.max_amount is not None: d = d[s <= cfg.max_amount]
    return d

def pivot_accounts(df: pd.DataFrame, cols: Columns) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    c = cols
    return (df.groupby([c.konto, c.kontonavn])[c.belop].agg(Linjer="count", Sum="sum").reset_index().sort_values([c.konto, c.kontonavn]))

def stratify(df: pd.DataFrame, cols: Columns, bcfg: BucketCfg) -> pd.DataFrame:
    if df is None or df.empty or bcfg.n <= 0: return pd.DataFrame(columns=["Bucket","Unike bilag","Sum"])
    c = cols; s = df[c.belop].abs() if bcfg.basis == "abs" else df[c.belop]
    if bcfg.method == "equal":
        mn, mx = float(s.min()), float(s.max())
        if mn == mx: edges = [mn, mx]
        else: edges = list(np.linspace(mn, mx, bcfg.n + 1))
    else:
        qs = np.linspace(0, 1, bcfg.n + 1); edges = s.quantile(qs).tolist()
        for i in range(1, len(edges)):
            if edges[i] <= edges[i-1]: edges[i] = edges[i-1] + 0.01
    labels = [f"{edges[i]:,.2f} – {edges[i+1]:,.2f}" for i in range(bcfg.n)]
    cats = pd.cut(s, bins=edges, include_lowest=True, labels=labels)
    tab = df.assign(Bucket=cats).groupby("Bucket")[c.bilag].nunique().reset_index(name="Unike bilag")
    sums = df.assign(Bucket=cats).groupby("Bucket")[c.belop].sum().reset_index(name="Sum")
    out = tab.merge(sums, on="Bucket", how="left")
    return out
