# controller_selection.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple

import numpy as np
import pandas as pd

from models import Columns
from scope import parse_accounts


@dataclass
class SelectionState:
    accounts_spec: str = ""     # "6100-7999, 7210, 73*"
    direction: str = "Alle"     # Alle | Debet | Kredit (på signert)
    basis: str = "abs"          # "abs" | "signed" (grunnlag for beløpsfilter + bøtter)
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    method: str = "quantile"    # "quantile" | "equal"
    bins: int = 5
    seed: Optional[int] = None


class SelectionController:
    """Logikk for Utvalgsstudio (populasjon + stratifisering + trekk)."""
    def __init__(self, df: pd.DataFrame, cols: Columns):
        self.df = df.copy()
        self.cols = cols
        self.state = SelectionState()

    # ----------------- filtering -----------------
    def _accounts_set(self) -> List[int]:
        if not self.state.accounts_spec:
            return []
        existing = self.df[self.cols.konto].dropna().astype("Int64").astype(int).unique().tolist()
        return sorted(parse_accounts(self.state.accounts_spec, existing))

    def filtered_df(self) -> pd.DataFrame:
        df = self.df
        c = self.cols

        # Accounts
        acc = self._accounts_set()
        if acc:
            df = df[df[c.konto].astype("Int64").astype(int).isin(acc)]
        else:
            df = df.iloc[0:0].copy()  # tom hvis ingen spesifikasjon

        # Direction (signert)
        if self.state.direction == "Debet":
            df = df[df[c.belop] > 0]
        elif self.state.direction == "Kredit":
            df = df[df[c.belop] < 0]

        # Amount range (på valgt basis)
        s = df[c.belop].abs() if self.state.basis == "abs" else df[c.belop]
        if self.state.min_amount is not None:
            df = df[s >= float(self.state.min_amount)]
        if self.state.max_amount is not None:
            df = df[s <= float(self.state.max_amount)]

        return df

    # ----------------- buckets -----------------
    def _edges(self, s: pd.Series) -> List[float]:
        b = max(1, int(self.state.bins))
        if self.state.method == "equal":
            lo, hi = float(s.min()), float(s.max())
            edges = np.linspace(lo, hi, b + 1)
        else:
            qs = np.linspace(0, 1, b + 1)
            edges = s.quantile(qs).to_numpy()
        # sørg for strengt økende
        for i in range(1, len(edges)):
            if edges[i] <= edges[i-1]:
                edges[i] = edges[i-1] + 1e-9
        return edges.tolist()

    def build_buckets(self) -> Tuple[pd.DataFrame, List[pd.Interval]]:
        df = self.filtered_df()
        if df.empty:
            return pd.DataFrame(columns=["Fra", "Til", "Linjer", "Unike bilag", "Sum (netto)", "Sum (|beløp|)"]), []

        s_basis = df[self.cols.belop].abs() if self.state.basis == "abs" else df[self.cols.belop]
        edges = self._edges(s_basis)
        cats = pd.cut(s_basis, bins=edges, include_lowest=True)

        out = (
            df.assign(_bucket=cats)
              .groupby("_bucket", observed=False)
              .agg(**{
                  "Linjer": (self.cols.bilag, "count"),
                  "Unike bilag": (self.cols.bilag, lambda x: x.astype(str).nunique()),
                  "Sum (netto)": (self.cols.belop, "sum"),
                  "Sum (|beløp|)": (self.cols.belop, lambda x: x.abs().sum()),
              })
              .reset_index()
        )
        # Split interval to fra/til som kolonner for klarhet
        fra = out["_bucket"].apply(lambda iv: iv.left if isinstance(iv, pd.Interval) else np.nan).astype(float)
        til = out["_bucket"].apply(lambda iv: iv.right if isinstance(iv, pd.Interval) else np.nan).astype(float)
        out = out.drop(columns=["_bucket"])
        out.insert(0, "Fra", fra)
        out.insert(1, "Til", til)
        return out, cats.cat.categories.tolist() if len(cats) else []

    # ----------------- sample -----------------
    def draw_sample(self, n_total: int, per_bucket: str = "equal") -> pd.Series:
        """
        Trekker 'n_total' unike bilag fra populasjonen.
        per_bucket = 'equal' (likt antall per bøtte) eller 'prop' (proporsjonalt med unike bilag).
        Returnerer Series med bilagsnumre (str).
        """
        df = self.filtered_df()
        if df.empty:
            return pd.Series([], dtype=str)
        c = self.cols
        s_basis = df[c.belop].abs() if self.state.basis == "abs" else df[c.belop]
        edges = self._edges(s_basis)
        cats = pd.cut(s_basis, bins=edges, include_lowest=True)
        df = df.assign(_bucket=cats)
        grp = df.groupby("_bucket", observed=False)

        uniq_counts = grp[c.bilag].nunique()
        buckets = uniq_counts.index.tolist()
        if not buckets:
            return pd.Series([], dtype=str)

        if per_bucket == "prop":
            # proporsjonal fordeling (min 1 hvis mulig)
            weights = uniq_counts / max(1, int(uniq_counts.sum()))
            alloc = (weights * n_total).round().astype(int)
            # sikre minst én i bøtter med unike > 0 hvis sum < n_total
            deficit = n_total - int(alloc.sum())
            i = 0
            while deficit > 0:
                if uniq_counts.iloc[i] > 0:
                    alloc.iloc[i] += 1
                    deficit -= 1
                i = (i + 1) % len(alloc)
        else:
            # lik fordeling
            per = max(1, n_total // max(1, len(buckets)))
            alloc = pd.Series([per] * len(buckets), index=buckets, dtype=int)
            # fordel rest
            rest = n_total - int(alloc.sum())
            i = 0
            while rest > 0:
                alloc.iloc[i] += 1
                rest -= 1
                i = (i + 1) % len(alloc)

        rng = np.random.RandomState(self.state.seed) if self.state.seed is not None else None
        picks: List[str] = []
        for b, need in alloc.items():
            sub = df[df["_bucket"] == b]
            uniq = sub[c.bilag].dropna().astype(str).drop_duplicates()
            if uniq.empty:
                continue
            k = int(min(need, len(uniq)))
            if k <= 0:
                continue
            samp = uniq.sample(n=k, random_state=rng)
            picks.extend(samp.tolist())

        return pd.Series(sorted(set(picks)), dtype=str)
