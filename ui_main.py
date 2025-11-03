# ui_main.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from theme import apply_sisu_theme
from dataset_pane import DatasetPane
from page_analyse import AnalysePage
from page_utvalg import UtvalgPage
from session import set_dataset, get_dataset, has_dataset


class MainUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Utvalgsgenerator")
        self.root.geometry("1220x780")
        apply_sisu_theme(self.root)

        self._build_menu()

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Faner
        self.tab_dataset = ttk.Frame(self.nb); self.nb.add(self.tab_dataset, text="Datasett")
        self.tab_analyse = ttk.Frame(self.nb); self.nb.add(self.tab_analyse, text="Analyse")
        self.tab_utvalg  = ttk.Frame(self.nb); self.nb.add(self.tab_utvalg,  text="Utvalg")

        # Innhold
        self.dp = DatasetPane(self.tab_dataset, on_built=self._apply_dataset)
        self.dp.frm.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.analyse = AnalysePage(self.tab_analyse, on_to_utvalg=self._open_utvalg)
        self.analyse.pack(fill=tk.BOTH, expand=True)

        self.utvalg = UtvalgPage(self.tab_utvalg)
        self.utvalg.pack(fill=tk.BOTH, expand=True)

    def _apply_dataset(self, df, cols):
        set_dataset(df, cols)
        self.nb.select(self.tab_analyse)
        # Sørg for at Analyse fylles
        self.analyse.refresh_from_session()

    def _open_utvalg(self, accounts, direction, vmin, vmax):
        df, cols = get_dataset()
        if df is None or cols is None:
            return
        # For utvalg bruker vi som default absolutt-beløp i filter
        self.utvalg.prepare(df, cols, accounts, direction=direction, min_amount=vmin, max_amount=vmax, use_abs=True)
        self.nb.select(self.tab_utvalg)

    def _build_menu(self):
        m = tk.Menu(self.root); self.root.config(menu=m)

        m_file = tk.Menu(m, tearoff=False); m.add_cascade(label="Fil", menu=m_file)
        m_file.add_command(label="Avslutt", command=self.root.destroy)

        m_nav = tk.Menu(m, tearoff=False); m.add_cascade(label="Naviger", menu=m_nav)
        m_nav.add_command(label="Datasett", command=lambda: self.nb.select(self.tab_dataset))
        m_nav.add_command(label="Analyse", command=lambda: self.nb.select(self.tab_analyse))
        m_nav.add_command(label="Utvalg",  command=lambda: self.nb.select(self.tab_utvalg))

    def mainLoop(self):
        self.root.mainloop()


if __name__ == "__main__":
    MainUI().mainLoop()
