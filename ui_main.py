from __future__ import annotations
import tkinter as tk
from tkinter import ttk, messagebox
from theme import setup_theme
from dataset_pane import DatasetPage
from page_analyse import AnalysePage
from views_selection_studio import SelectionStudio
from session import has_dataset

class MainUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Utvalgsgenerator")
        self.geometry("1280x780")
        setup_theme(self)

        # Meny
        menubar = tk.Menu(self)
        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="Avslutt", command=self.destroy)
        menubar.add_cascade(label="Fil", menu=m_file)
        self.config(menu=menubar)

        # Faner
        self.nb = ttk.Notebook(self); self.nb.pack(fill=tk.BOTH, expand=True)

        self.page_dataset = DatasetPage(self.nb, on_ready=self._go_analyse)
        self.nb.add(self.page_dataset, text="Datasett")

        self.page_analyse = AnalysePage(self.nb, open_selection_cb=self._go_selection)
        self.nb.add(self.page_analyse, text="Analyse")

        self.page_selection = SelectionStudio(self.nb)
        self.nb.add(self.page_selection, text="Utvalg")

        # Start på Datasett
        self.nb.select(self.page_dataset)

    # Callbacks
    def _go_analyse(self):
        self.page_analyse.refresh_from_session()
        self.nb.select(self.page_analyse)

    def _go_selection(self, accounts):
        if not has_dataset():
            messagebox.showinfo("Utvalg", "Bygg datasett først.")
            return
        self.page_selection.set_accounts(accounts)
        self.nb.select(self.page_selection)
