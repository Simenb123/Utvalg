"""toolbar.py — Verktøylinje for EditorApp.

Alle knapper er koblet til callbacks som EditorApp setter. Toolbar-klassen
eier bare widgetene og layouten; forretningslogikken ligger i app.py.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class Toolbar(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, padding=(6, 4))

        # Callbacks (settes av EditorApp)
        self.on_new: Optional[Callable[[], None]] = None
        self.on_open: Optional[Callable[[], None]] = None
        self.on_save: Optional[Callable[[], None]] = None
        self.on_save_as: Optional[Callable[[], None]] = None
        self.on_import_mermaid: Optional[Callable[[], None]] = None
        self.on_export_mermaid: Optional[Callable[[], None]] = None
        self.on_add_node: Optional[Callable[[], None]] = None
        self.on_add_edge: Optional[Callable[[], None]] = None
        self.on_delete: Optional[Callable[[], None]] = None
        self.on_zoom_in: Optional[Callable[[], None]] = None
        self.on_zoom_out: Optional[Callable[[], None]] = None
        self.on_zoom_reset: Optional[Callable[[], None]] = None
        self.on_fit: Optional[Callable[[], None]] = None

        self._build()

    def _build(self) -> None:
        specs: list[tuple[str, str]] = [
            ("Ny", "_invoke_new"),
            ("Åpne…", "_invoke_open"),
            ("Lagre", "_invoke_save"),
            ("Lagre som…", "_invoke_save_as"),
            ("|", ""),
            ("Importer Mermaid…", "_invoke_import_mermaid"),
            ("Eksporter Mermaid…", "_invoke_export_mermaid"),
            ("|", ""),
            ("+ Node", "_invoke_add_node"),
            ("+ Kant", "_invoke_add_edge"),
            ("Slett", "_invoke_delete"),
            ("|", ""),
            ("Zoom −", "_invoke_zoom_out"),
            ("100 %", "_invoke_zoom_reset"),
            ("Zoom +", "_invoke_zoom_in"),
            ("Tilpass", "_invoke_fit"),
        ]
        col = 0
        for label, method in specs:
            if label == "|":
                sep = ttk.Separator(self, orient="vertical")
                sep.grid(row=0, column=col, sticky="ns", padx=6)
            else:
                btn = ttk.Button(self, text=label, command=getattr(self, method))
                btn.grid(row=0, column=col, padx=2)
            col += 1

    # Indirection for å tillate at callbacks settes etter init
    def _invoke_new(self) -> None:
        if self.on_new:
            self.on_new()

    def _invoke_open(self) -> None:
        if self.on_open:
            self.on_open()

    def _invoke_save(self) -> None:
        if self.on_save:
            self.on_save()

    def _invoke_save_as(self) -> None:
        if self.on_save_as:
            self.on_save_as()

    def _invoke_import_mermaid(self) -> None:
        if self.on_import_mermaid:
            self.on_import_mermaid()

    def _invoke_export_mermaid(self) -> None:
        if self.on_export_mermaid:
            self.on_export_mermaid()

    def _invoke_add_node(self) -> None:
        if self.on_add_node:
            self.on_add_node()

    def _invoke_add_edge(self) -> None:
        if self.on_add_edge:
            self.on_add_edge()

    def _invoke_delete(self) -> None:
        if self.on_delete:
            self.on_delete()

    def _invoke_zoom_in(self) -> None:
        if self.on_zoom_in:
            self.on_zoom_in()

    def _invoke_zoom_out(self) -> None:
        if self.on_zoom_out:
            self.on_zoom_out()

    def _invoke_zoom_reset(self) -> None:
        if self.on_zoom_reset:
            self.on_zoom_reset()

    def _invoke_fit(self) -> None:
        if self.on_fit:
            self.on_fit()
