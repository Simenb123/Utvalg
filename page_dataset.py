# page_dataset.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from dataset_pane import DatasetPane
from session import set_dataset


class DatasetPage(ttk.Frame):
    def __init__(self, parent: ttk.Notebook, on_ready=None):
        super().__init__(parent)
        self.on_ready = on_ready

        # Panelet gjenbrukes (samme logikk som før)
        self.dp = DatasetPane(self, "Datasett")
        self.dp.frm.pack(fill=tk.BOTH, expand=True)

        # Handling-bar nederst
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=8, pady=(0,8))
        ttk.Button(bar, text="Bruk datasett", command=self._use).pack(side=tk.RIGHT)

        # Hint
        self.hint = ttk.Label(self, text="Tips: Åpne fil → sett header → kontroller gjetting → «Bygg datasett» → «Bruk datasett».",
                              foreground="#555555")
        self.hint.pack(fill=tk.X, padx=8, pady=(0,8))

    def _use(self):
        # Bruk siste bygg hvis det finnes, ellers bygg nå
        df, cols = self.dp.get_last_build()
        if df is None or cols is None:
            df, cols = self.dp.build_dataset()
        if df is None or cols is None:
            messagebox.showinfo("Datasett", "Fullfør bygging av datasett først.")
            return
        set_dataset(df, cols)
        # Ikke popup – gi inline bekreftelse og flytt appen videre
        self.hint.config(text=f"Datasett klart ({len(df):,} rader). Går til Analyse …")
        if callable(self.on_ready):
            self.after(50, self.on_ready)
