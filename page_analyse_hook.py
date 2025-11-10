# Patch: only minor hook to set max_rows via preferences (if available), and no functional changes beyond pinned reset that you already have.
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import Optional, Dict, Any, Sequence, List
import pandas as pd
import importlib

try:
    import preferences as prefs
except Exception:
    prefs = None

try:
    from views_virtual_transactions import VirtualTransactionsPanel
except Exception:
    class VirtualTransactionsPanel(ttk.Frame):
        def __init__(self, master, columns, **kwargs):
            super().__init__(master, **kwargs)
            self._tv = ttk.Treeview(self, columns=columns, show="headings")
            for c in columns: self._tv.heading(c, text=c); self._tv.column(c, width=120, anchor="w")
            self._tv.pack(fill="both", expand=True)
        def set_dataframe(self, df: pd.DataFrame, pinned=None): pass
        def bind_row_double_click(self, cb): pass
        def update_columns(self, columns, pinned=None): pass
        @property
        def visible_limit(self): return 0

# Hook function to create panel with prefs-based max_rows
def make_trans_panel(parent, columns):
    limit = 100_000
    if prefs:
        try:
            limit = int(prefs.get("table.max_rows", 100_000))
        except Exception:
            pass
    return VirtualTransactionsPanel(parent, columns=columns, max_rows=limit, window_size=1500)