"""page_dataset.py

Dataset-fanen: innlesing og bygging av hovedbokdatasett.

Denne siden er en tynn wrapper rundt DatasetPane, som håndterer
selve GUI-et for filvalg, kolonnemapping og bygging av dataset.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from dataset_pane import DatasetPane


class DatasetPage(ttk.Frame):
    """
    Dataset-fane som embedder DatasetPane i notebooken.

    Bruk:
        page = DatasetPage(notebook)
        notebook.add(page, text="Dataset")
    """

    def __init__(self, parent: tk.Misc, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        # DatasetPane forventer kun parent som argument.
        # Den tidligere koden brukte DatasetPane(self, "Dataset"),
        # men __init__ tar bare (self, parent), så vi fjerner tittelen her.
        self.dp = DatasetPane(self)
        self.dp.pack(fill="both", expand=True)
