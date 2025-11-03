from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

import pandas as pd

from models import Columns


@dataclass
class _State:
    direction: str = "Alle"      # "Alle" | "Debet" | "Kredit"
    basis: str = "signed"        # "signed" | "abs"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None


class DataControllerCore:
    """
    Tynt service‑lag mellom UI og DataFrame:
    - holder 'clean' df (med riktige typer)
    - bygger pivot per konto
    - leverer filtrert df til drilldown
    """
    def __init__(self) -> None:
        self.df_clean: Optional[pd.DataFrame] = None
        self.df_acc: Optional[pd.DataFrame] = None
        self.cols = Columns()
        self._st = _State()

    # init
    def init_prepared(self, df: pd.DataFrame, cols: Columns) -> None:
        self.df_clean = df.copy()
        self.cols = cols
        self._recompute()

    # config
    def set_direction(self, direction: str) -> None:
        self._st.direction = direction or "Alle"
        self._recompute()

    def set_amount_basis(self, basis: str) -> None:
        self._st.basis = basis if basis in {"signed", "abs"} else "signed"
        self._recompute()

    def set_amount_range(self, mi: Optional[float], ma: Optional[float]) -> None:
        self._st.min_amount, self._st.max_amount = mi, ma
        self._recompute()

    # data
    def filtered_df(self) -> Optional[pd.DataFrame]:
        if self.df_clean is None:
            return None
        c = self.cols
        df = self.df_clean

        # retning
        if self._st.direction.lower().startswith("debet"):
            df = df[df[c.belop] > 0]
        elif self._st.direction.lower().startswith("kredit"):
            df = df[df[c.belop] < 0]

        # basis for terskler
        series = df[c.belop].abs() if self._st.basis == "abs" else df[c.belop]
        if self._st.min_amount is not None:
            df = df[series >= float(self._st.min_amount)]
        if self._st.max_amount is not None:
            df = df[series <= float(self._st.max_amount)]
        return df

    # intern
    def _recompute(self) -> None:
        if self.df_clean is None:
            self.df_acc = None
            return
        df = self.filtered_df()
        if df is None or df.empty:
            self.df_acc = pd.DataFrame(columns=[self.cols.konto, self.cols.kontonavn, "Antall", "Sum"])
            return
        c = self.cols
        self.df_acc = (
            df.groupby([c.konto, c.kontonavn])[c.belop]
              .agg(Antall="count", Sum="sum")
              .reset_index()
              .sort_values([c.konto, c.kontonavn])
        )
