# views_drilldown.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

import pandas as pd

from models import Columns
from formatting import fmt_amount, fmt_date
from ui_utils import enable_treeview_sort

def open_drilldown(parent: tk.Tk | tk.Toplevel, df: pd.DataFrame, cols: Columns,
                   konto: int, kontonavn: str = ""):
    win = tk.Toplevel(parent)
    win.title(f"Drilldown – {konto} {kontonavn}")
    win.geometry("1100x680")

    info = ttk.Frame(win); info.pack(fill=tk.X, padx=8, pady=6)
    ttk.Label(info, text=f"Konto: {konto}  {kontonavn}").pack(side=tk.LEFT)

    frame = ttk.Frame(win); frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0,8))

    cols_show = ("dato","bilag","tekst","belop")
    tree = ttk.Treeview(frame, columns=cols_show, show="headings")
    tree.heading("dato", text="Dato");   tree.column("dato", width=100, anchor="w")
    tree.heading("bilag", text="Bilag"); tree.column("bilag", width=140, anchor="w")
    tree.heading("tekst", text="Tekst"); tree.column("tekst", width=700, anchor="w")
    tree.heading("belop", text="Beløp"); tree.column("belop", width=120, anchor="e")
    tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    ttk.Scrollbar(frame, orient="vertical", command=tree.yview).pack(side=tk.RIGHT, fill=tk.Y)

    c = cols
    dff = df[df[c.konto].astype("Int64").astype(int) == int(konto)].copy()

    col_dato = getattr(cols, "dato", None) if hasattr(cols, "dato") else None
    col_txt  = getattr(cols, "tekst", None) if hasattr(cols, "tekst") else None

    for _, r in dff.iterrows():
        dato = fmt_date(r[col_dato]) if col_dato and col_dato in dff.columns else ""
        bilag = str(r[c.bilag])
        tekst = str(r[col_txt]) if col_txt and col_txt in dff.columns else ""
        belop = fmt_amount(float(r[c.belop]) if pd.notna(r[c.belop]) else 0.0)
        tree.insert("", tk.END, values=(dato, bilag, tekst, belop))

    enable_treeview_sort(tree, {"dato":"date","bilag":"text","tekst":"text","belop":"amount"})
