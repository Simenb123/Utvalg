# ui_shell.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from page_dataset import DatasetPage
from page_analyse import AnalysePage
from session import has_dataset


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Utvalgsgenerator")
        self.geometry("1280x900")
        self.minsize(1100, 740)

        # Meny – enkel, kan bygges ut
        menubar = tk.Menu(self)
        self.config(menu=menubar)
        m_fil = tk.Menu(menubar, tearoff=False)
        m_fil.add_command(label="Avslutt", command=self.destroy)
        menubar.add_cascade(label="Fil", menu=m_fil)

        # Notebook med faner (ett globalt UI)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill=tk.BOTH, expand=True)

        # Faner
        self.tab_dataset = DatasetPage(self.nb, on_ready=self._goto_analyse)
        self.nb.add(self.tab_dataset, text="Datasett")

        self.tab_analyse = AnalysePage(self.nb)
        self.nb.add(self.tab_analyse, text="Analyse")

        # Statuslinje
        self.status = ttk.Label(self, relief=tk.SUNKEN, anchor="w")
        self.status.pack(fill=tk.X, side=tk.BOTTOM)
        self.set_status("Velkommen! Start med Datasett → åpne og bruk datasett.")

        # Hvis noen allerede har lastet inn i session (dev-bruk), vis Analyse
        if has_dataset():
            self._goto_analyse()

    def set_status(self, txt: str):
        self.status.config(text=txt)

    def _goto_analyse(self):
        # Oppdater Analyse-fanen fra session og vis den
        self.tab_analyse.refresh_from_session()
        self.nb.select(self.tab_analyse)


if __name__ == "__main__":
    App().mainloop()
