from __future__ import annotations
from typing import Optional
import pandas as pd
from models import Columns

class DataControllerCore:
    """
    Holder en 'prepared' DataFrame og bygger filtre/pivot.
    """
    def __init__(self) -> None:
        self.df_clean: Optional[pd.DataFrame] = None
        self.cols: Optional[Columns] = None
        self._dir = "Alle"
        self._basis = "signed"  # 'signed' | 'abs'
        self._min: Optional[float] = None
        self._max: Optional[float] = None
        self.df_acc: Optional[pd.DataFrame] = None  # pivot pr konto

    def init_prepared(self, df: pd.DataFrame, cols: Columns) -> None:
        self.df_clean = df
        self.cols = cols
        self.recompute()

    def set_direction(self, v: str) -> None:
        self._dir = (v or "Alle")
        self.recompute()

    def set_amount_basis(self, basis: str) -> None:
        self._basis = basis if basis in ("signed", "abs") else "signed"
        self.recompute()

    def set_amount_range(self, vmin: Optional[float], vmax: Optional[float]) -> None:
        self._min, self._max = vmin, vmax
        self.recompute()

    def filtered_df(self) -> pd.DataFrame:
        if self.df_clean is None or self.cols is None:
            return pd.DataFrame()
        c = self.cols
        df = self.df_clean
        # retning
        if (self._dir or "").lower().startswith("debet"):
            df = df[df[c.belop] > 0]
        elif (self._dir or "").lower().startswith("kredit"):
            df = df[df[c.belop] < 0]
        # beløp
        if self._min is not None:
            df = df[df[c.belop] >= float(self._min)]
        if self._max is not None:
            df = df[df[c.belop] <= float(self._max)]
        return df

    def recompute(self) -> None:
        if self.df_clean is None or self.cols is None:
            self.df_acc = None
            return
        df = self.filtered_df()
        c = self.cols
        if df.empty:
            self.df_acc = df
            return
        grp = (
            df.groupby([c.konto, c.kontonavn])[c.belop]
            .agg(Antall="count", Sum="sum")
            .reset_index()
            .sort_values([c.konto, c.kontonavn])
        )
        self.df_acc = grp
