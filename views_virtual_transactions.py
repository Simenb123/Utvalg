# -*- coding: utf-8 -*-
"""
VirtualTransactionsPanel – R12d
- Tåler NaN/None i beløp/dato
- Støtter pinned/ønsket rekkefølge/visible
- Rendrer kun 'limit' rader for rask GUI
- Dobbeltklikk callback via on_row_dblclick(pd.Series)
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Sequence, List, Any
import pandas as pd

def _is_nan(v: Any) -> bool:
    try:
        return pd.isna(v)
    except Exception:
        return v is None

def _fmt_number_no(n: Any) -> str:
    if _is_nan(n):
        return ""
    try:
        val = float(n)
    except Exception:
        return str(n)
    s = f"{abs(val):,.2f}".replace(",", " ").replace(".", ",")
    return f"-{s}" if val < 0 else s

def _fmt_date_no(v: Any) -> str:
    if _is_nan(v):
        return ""
    try:
        d = pd.to_datetime(v, dayfirst=True, errors="coerce")
        if pd.isna(d):
            return ""
        d = d.date()
        return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"
    except Exception:
        return str(v)

def _fmt_cell(v: Any, colname: str) -> str:
    cn = (colname or "").lower()
    if "dato" in cn or "date" in cn:
        return _fmt_date_no(v)
    try:
        if isinstance(v, (int, float)):
            return _fmt_number_no(v)
    except Exception:
        pass
    return "" if _is_nan(v) else str(v)

class VirtualTransactionsPanel(ttk.Frame):
    def __init__(self, master, columns: Optional[Sequence[str]] = None,
                 display_limit: int = 200, **kwargs) -> None:
        self._on_dbl = kwargs.pop("on_row_dblclick", None)
        super().__init__(master)
        self._tree = ttk.Treeview(self, show="headings")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._df: Optional[pd.DataFrame] = None
        self._display_df: Optional[pd.DataFrame] = None
        self._columns: List[str] = list(columns) if columns else []
        self._limit: int = int(display_limit) if display_limit else 200
        if self._on_dbl:
            self._tree.bind("<Double-1>", self._handle_dblclick)
        if self._columns:
            self._setup_columns(self._columns)

    def clear(self) -> None:
        self._df = None
        self._display_df = None
        self._tree.delete(*self._tree.get_children())

    def set_display_limit(self, n: int) -> None:
        self._limit = max(1, int(n))
        if self._df is not None:
            self._refresh_rows()

    def set_dataframe(self, df: pd.DataFrame,
                      pinned: Optional[Sequence[str]] = None,
                      columns: Optional[Sequence[str]] = None,
                      prefer_order: Optional[Sequence[str]] = None,
                      visible: Optional[Sequence[str]] = None,
                      limit: Optional[int] = None,
                      **_ignore) -> None:
        if df is None or len(df)==0:
            self.clear(); return
        self._df = df
        src = list(df.columns)
        pins = [c for c in (pinned or []) if c in src]
        order = list(columns or prefer_order or src)
        rest = [c for c in order if c in src and c not in pins]
        tail = [c for c in src if c not in pins and c not in rest]
        ordered = pins + rest + tail
        vis = [c for c in ordered if c in (visible or ordered)]
        if vis != self._columns:
            self._columns = vis
            self._setup_columns(self._columns)
        if limit is not None and int(limit) > 0:
            self._limit = int(limit)
        self._refresh_rows()

    def _setup_columns(self, cols: Sequence[str]) -> None:
        self._tree["columns"] = list(cols)
        for c in cols:
            self._tree.heading(c, text=c)
            w = 120
            if c.lower() in ("beløp","belop"):
                w = 110
            elif c.lower() in ("tekst","kontonavn"):
                w = 240
            self._tree.column(c, width=w, stretch=True)

    def _refresh_rows(self) -> None:
        if self._df is None:
            return
        df = self._df
        cols = self._columns if self._columns else list(df.columns)
        view = df.loc[:, [c for c in cols if c in df.columns]].head(self._limit).copy()
        self._tree.delete(*self._tree.get_children())
        rows = []
        for _, row in view.iterrows():
            vals = [_fmt_cell(row.get(c, ""), c) for c in cols]
            rows.append(vals)
        for i, vals in enumerate(rows):
            self._tree.insert("", "end", iid=str(i), values=vals)
        self._display_df = view

    def _handle_dblclick(self, _evt=None) -> None:
        if not isinstance(self._on_dbl, (type(lambda:None),)) and not callable(self._on_dbl):
            return
        sel = self._tree.selection()
        if not sel:
            focus = self._tree.focus()
            if not focus:
                return
            sel = (focus,)
        try:
            idx = int(sel[0])
        except Exception:
            return
        if self._display_df is None or idx < 0 or idx >= len(self._display_df):
            return
        row = self._display_df.iloc[idx]
        try:
            self._on_dbl(row)
        except Exception:
            pass
