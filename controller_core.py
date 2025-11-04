from __future__ import annotations
import pandas as pd
from typing import Optional
from models import Columns

class DataControllerCore:
    def __init__(self):
        self.df_clean: Optional[pd.DataFrame] = None
        self.cols: Optional[Columns] = None
        self._direction: str = "Alle"
        self._basis: str = "signed"
        self._min: Optional[float] = None
        self._max: Optional[float] = None
        self._date_from = None
        self._date_to = None
        self.df_acc: Optional[pd.DataFrame] = None

    def init_prepared(self, df: pd.DataFrame, cols: Columns) -> None:
        self.df_clean = df.copy()
        self.cols = cols
        self._direction = "Alle"
        self._basis = "signed"
        self._min = None; self._max = None
        self._date_from = None; self._date_to = None
        self.rebuild_pivot()

    def set_direction(self, direction: str) -> None:
        self._direction = direction or "Alle"

    def set_amount_basis(self, basis: str) -> None:
        self._basis = basis if basis in {"signed", "abs"} else "signed"

    def set_amount_range(self, min_v: Optional[float], max_v: Optional[float]) -> None:
        self._min, self._max = min_v, max_v

    def set_date_range(self, date_from, date_to) -> None:
        self._date_from, self._date_to = date_from, date_to

    def filtered_df(self) -> Optional[pd.DataFrame]:
        if self.df_clean is None or self.cols is None:
            return None
        c = self.cols
        df = self.df_clean.copy()

        if getattr(c, "dato", None) and c.dato in df.columns:
            if self._date_from is not None:
                df = df[df[c.dato] >= self._date_from]
            if self._date_to is not None:
                df = df[df[c.dato] <= self._date_to]

        if self._direction.lower().startswith("debet"):
            df = df[df[c.belop] > 0]
        elif self._direction.lower().startswith("kredit"):
            df = df[df[c.belop] < 0]

        if self._min is not None or self._max is not None:
            s = df[c.belop].abs() if (self._basis == "abs" and self._direction == "Alle") else df[c.belop]
            if self._min is not None:
                df = df[s >= self._min]
            if self._max is not None:
                df = df[s <= self._max]

        return df

    def rebuild_pivot(self) -> None:
        df = self.filtered_df()
        if df is None or df.empty or self.cols is None:
            self.df_acc = None; return
        c = self.cols
        self.df_acc = (
            df.groupby([c.konto, c.kontonavn])[c.belop]
            .agg(Antall="count", Sum="sum")
            .reset_index()
            .sort_values([c.konto, c.kontonavn])
        )
