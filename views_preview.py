from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import pandas as pd

from header_detection import detect_header_row
from preview_format import format_preview_value, infer_column_kinds


def show_preview(parent, df_raw: pd.DataFrame, on_choose_header):
    """
    Viser de første ~150 rå-radene uten header.
    Dobbeltklikk på rad => kaller on_choose_header(idx_1based).
    """
    top = tk.Toplevel(parent)
    top.title("Forhåndsvisning – dobbeltklikk rad for å sette header")
    top.geometry("920x520")
    ttk.Label(top, text="Dobbeltklikk på raden som er header. Den settes i 'Header-rad' i hovedvinduet.").pack(fill=tk.X, padx=8, pady=6)

    frame = ttk.Frame(top); frame.pack(fill=tk.BOTH, expand=True)
    dfp = df_raw.head(150)
    cols = [f"kol{i+1}" for i in range(dfp.shape[1])]
    tree = ttk.Treeview(frame, columns=cols, show="headings")
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=120, stretch=True)
    # Best-effort: gjett header-rad for å velge bedre visningsformat.
    rows_for_guess = [list(r) for r in dfp.itertuples(index=False, name=None)]
    hdr_idx0 = None
    try:
        hdr_idx0 = detect_header_row(rows_for_guess)
    except Exception:
        hdr_idx0 = None

    kinds = infer_column_kinds(rows_for_guess, header_row_idx0=hdr_idx0)
    if len(kinds) < len(cols):
        kinds = kinds + ["generic"] * (len(cols) - len(kinds))

    for i in range(len(dfp)):
        row = dfp.iloc[i].tolist()
        values = [format_preview_value(v, kind=kinds[j] if j < len(kinds) else "") for j, v in enumerate(row)]
        tree.insert("", tk.END, iid=str(i), values=values)

    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    tree.grid(row=0, column=0, sticky="nsew"); vsb.grid(row=0, column=1, sticky="ns"); hsb.grid(row=1, column=0, sticky="ew")
    frame.grid_columnconfigure(0, weight=1); frame.grid_rowconfigure(0, weight=1)

    def on_double(_ev=None):
        sel = tree.selection()
        if not sel: return
        idx = int(sel[0]) + 1  # 1-based til hovedvindu
        on_choose_header(idx)
        top.destroy()

    tree.bind("<Double-1>", on_double)
