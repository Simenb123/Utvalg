
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import pandas as pd

class BilagDrillDialog(tk.Toplevel):
    """Dobbeltklikk på transaksjon => vis alle linjer på samme bilag (inkl. motposter)."""
    def __init__(self, master, df: pd.DataFrame, bilag_col: str = "Bilag"):
        super().__init__(master)
        self.title("Bilagsdrill")
        self.geometry("1000x600")
        self.df = df
        self.bilag_col = bilag_col

        top = ttk.Frame(self)
        top.pack(fill="x", padx=6, pady=4)
        ttk.Label(top, text="Bilag:").pack(side="left")
        self.var_bilag = tk.StringVar(value="")
        self.ent = ttk.Entry(top, textvariable=self.var_bilag, width=30)
        self.ent.pack(side="left")
        ttk.Button(top, text="Vis", command=self._refresh).pack(side="left", padx=6)

        self.tree = ttk.Treeview(self, show="headings")
        self.tree.pack(fill="both", expand=True)
        sbx = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        sbx.pack(fill="x")
        self.tree.configure(xscrollcommand=sbx.set)

    def preset_and_show(self, bilag_value: str):
        self.var_bilag.set(str(bilag_value))
        self._refresh()

    def _refresh(self):
        b = self.var_bilag.get().strip()
        if not b:
            return
        view = self.df[self.df[self.bilag_col].astype(str) == b]
        # Build columns on first refresh
        cols = list(view.columns)
        self.tree["columns"] = tuple(cols)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120, stretch=True)
        self.tree.delete(*self.tree.get_children())
        for _, row in view.iterrows():
            self.tree.insert("", "end", values=[row.get(c, "") for c in cols])
