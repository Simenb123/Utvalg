# views_dataset.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from dataset_pane import DatasetPane
from session import set_dataset

def open_dataset_window(parent: tk.Tk | tk.Toplevel):
    win = tk.Toplevel(parent)
    win.title("Datasett")
    win.geometry("860x520")

    dp = DatasetPane(win, "Datasett")
    dp.frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

    bar = ttk.Frame(win); bar.pack(fill=tk.X, padx=8, pady=(0,8))

    def _use():
        # Bruk siste «Bygg» dersom bruker allerede trykket det,
        # ellers bygg nå.
        df, cols = dp.get_last_build()
        if df is None or cols is None:
            df, cols = dp.build_dataset()

        if df is None or cols is None:
            messagebox.showinfo("Datasett", "Velg fil/header/kolonner og trykk «Bygg datasett».")
            return

        set_dataset(df, cols)
        messagebox.showinfo("Datasett", f"Datasettet er klart ({len(df):,} rader). Åpne Hovedvisning/Utvalgsstudio.")
        try:
            win.destroy()
        except Exception:
            pass

    ttk.Button(bar, text="Bruk datasett", command=_use).pack(side=tk.RIGHT)
