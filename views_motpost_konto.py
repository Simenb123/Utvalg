from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import pandas as pd
from models import Columns
from formatting import fmt_amount, fmt_int
from excel_export import export_temp_excel

class KontoMotpostDialog(tk.Toplevel):
    """Vis fordeling av motposter for en valgt konto (summert over bilag)."""
    def __init__(self, parent, df: pd.DataFrame, cols: Columns, konto: int):
        super().__init__(parent)
        self.title(f"Motpost-fordeling for konto {konto}")
        self.geometry("760x560"); self.transient(parent); self.grab_set()
        self.df = df.copy(); self.c = cols; self.konto = int(konto)

        top = ttk.Frame(self, padding=8); top.pack(fill=tk.X)
        ttk.Label(top, text=f"Konto {konto} – fordeling på motpost").pack(side=tk.LEFT)
        ttk.Button(top, text="Åpne i Excel (temp)", command=self._excel).pack(side=tk.RIGHT)

        frame = ttk.Frame(self); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        cols = ("motkonto","navn","linjer","sum")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for cid, txt, w, anc in (("motkonto","Motkonto",100,"w"),("navn","Kontonavn",300,"w"),("linjer","Linjer",80,"e"),("sum","Sum",120,"e")):
            self.tree.heading(cid, text=txt); self.tree.column(cid, width=w, anchor=anc)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self._fill()

    def _fill(self):
        c = self.c; d = self.df.copy()
        d = d[d[c.konto].astype("Int64").astype(int) == self.konto]
        joined = d[[c.bilag]].merge(self.df, on=c.bilag, how="left", suffixes=("_sel",""))
        mot = joined[joined[c.konto] != self.konto]
        pv = mot.groupby([c.konto, c.kontonavn])[c.belop].agg(Linjer="count", Sum="sum").reset_index()
        for _, r in pv.iterrows():
            self.tree.insert("", tk.END, values=(str(r[c.konto]), str(r[c.kontonavn] or ""), fmt_int(int(r["Linjer"])), fmt_amount(float(r["Sum"]))))
        self._pv = pv

    def _excel(self):
        export_temp_excel({f"Motpost_{self.konto}": self._pv.copy()}, prefix=f"Motpost_{self.konto}_")
