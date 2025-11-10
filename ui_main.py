from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox

from dataset_pane import DatasetPane
from page_analyse import AnalysePage
from page_utvalg import UtvalgPage
from page_logg import LoggPage
import theme

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Utvalg/Analyse – Norge")
        self.geometry("1280x860")
        try:
            theme.apply_theme(self)
        except Exception:
            pass

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Faner
        self.page_data = ttk.Frame(self.nb); self.nb.add(self.page_data, text="Datasett")
        self.page_analyse = AnalysePage(self.nb); self.nb.add(self.page_analyse, text="Analyse")
        self.page_utvalg = UtvalgPage(self.nb); self.nb.add(self.page_utvalg, text="Utvalg")
        self.page_logg = LoggPage(self.nb); self.nb.add(self.page_logg, text="Logg")

        # Datasett-panelet
        self.ds_pane = DatasetPane(self.page_data, on_dataset_ready=self._on_dataset_ready)
        self.ds_pane.pack(fill=tk.BOTH, expand=True)

        # Meny
        self._build_menu()

    def _build_menu(self):
        menubar = tk.Menu(self)
        mfile = tk.Menu(menubar, tearoff=False)
        mfile.add_command(label="Avslutt", command=self.destroy)
        menubar.add_cascade(label="Fil", menu=mfile)
        self.config(menu=menubar)

    def _on_dataset_ready(self, _e=None):
        try:
            self.page_analyse.refresh_from_session()
            self.nb.select(self.page_analyse)
        except Exception as ex:
            messagebox.showwarning("Analyse", f"Klarte ikke å oppdatere analyse: {ex}")

# Bakoverkompatibilitet: enkelte miljøer importerer MainUI
MainUI = MainApp

if __name__ == "__main__":
    MainApp().mainloop()