from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import pandas as pd
from models import Columns
from formatting import fmt_amount, fmt_date
from excel_export import export_temp_excel

class VoucherDrill(tk.Toplevel):
    def __init__(self, parent, df: pd.DataFrame, cols: Columns, bilag_id: str):
        super().__init__(parent)
        self.title(f"Bilag {bilag_id} – drilldown")
        self.geometry("900x600"); self.transient(parent); self.grab_set()
        self.df = df.copy(); self.c = cols; self.bilag_id = str(bilag_id)

        top = ttk.Frame(self, padding=8); top.pack(fill=tk.X)
        ttk.Label(top, text=f"Bilag {self.bilag_id}").pack(side=tk.LEFT)
        ttk.Button(top, text="Åpne i Excel (temp)", command=self._excel).pack(side=tk.RIGHT)

        frame = ttk.Frame(self); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        cols = ("dato","konto","navn","tekst","belop")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for cid, txt, w, anc in (("dato","Dato",100,"w"),("konto","Konto",80,"e"),("navn","Kontonavn",280,"w"),("tekst","Tekst",320,"w"),("belop","Beløp",120,"e")):
            self.tree.heading(cid, text=txt); self.tree.column(cid, width=w, anchor=anc)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview).pack(side=tk.RIGHT, fill=tk.Y)
        self._fill()

    def _fill(self):
        c = self.c; d = self.df[self.df[c.bilag].astype(str) == self.bilag_id].copy()
        col_dato = getattr(c, "dato", None); col_txt = getattr(c, "tekst", None)
        if col_dato and col_dato not in d.columns: col_dato = None
        if col_txt and col_txt not in d.columns: col_txt = None
        for _, r in d.iterrows():
            self.tree.insert("", tk.END, values=(fmt_date(r[col_dato]) if col_dato else "", str(r[c.konto]), str(r[c.kontonavn] or ""), str(r[col_txt] or "") if col_txt else "", fmt_amount(float(r[c.belop]))))

    def _excel(self):
        c = self.c; d = self.df[self.df[c.bilag].astype(str) == self.bilag_id].copy()
        export_temp_excel({f"Bilag_{self.bilag_id}": d}, prefix=f"Bilag_{self.bilag_id}_")
