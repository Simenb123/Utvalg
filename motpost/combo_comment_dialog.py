from __future__ import annotations

"""Lett kommentardialog for kombinasjoner (Tkinter).

Krav fra arbeidsflyt:
- Dobbeltklikk på en kombinasjon åpner et lite popup-vindu.
- Fokus settes direkte i feltet (bruker kan skrive umiddelbart).
- Enter lagrer og lukker.
- Esc avbryter (lagrer ikke).

Dialogen er bevisst enkel (single-line) for effektivitet.
"""

from typing import Optional

import tkinter as tk
from tkinter import ttk


class ComboCommentDialog(tk.Toplevel):
    """Modal dialog for å redigere kommentar til én kombinasjon."""

    def __init__(self, parent: tk.Misc, *, combo: str, initial_comment: str = ""):
        super().__init__(parent)

        self._result: Optional[str] = None
        self._combo = str(combo)
        self._var = tk.StringVar(value=str(initial_comment or ""))

        self.title("Kommentar")
        self.transient(parent)
        try:
            self.resizable(False, False)
        except Exception:
            pass

        root = ttk.Frame(self, padding=10)
        root.pack(fill=tk.BOTH, expand=True)

        ttk.Label(root, text=f"Kombinasjon: {self._combo}").pack(anchor=tk.W)

        entry = ttk.Entry(root, textvariable=self._var, width=80)
        entry.pack(fill=tk.X, pady=(6, 10))

        # Fokus direkte for rask inntasting
        try:
            entry.focus_set()
            entry.selection_range(0, tk.END)
        except Exception:
            pass

        btns = ttk.Frame(root)
        btns.pack(fill=tk.X)

        ttk.Button(btns, text="Avbryt (Esc)", command=self._on_cancel).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Lagre (Enter)", command=self._on_save).pack(side=tk.RIGHT, padx=(0, 6))

        # Tastatur: Enter lagrer, Esc avbryter
        entry.bind("<Return>", lambda _e: self._on_save_break())
        entry.bind("<Escape>", lambda _e: self._on_cancel_break())
        self.bind("<Return>", lambda _e: self._on_save_break())
        self.bind("<Escape>", lambda _e: self._on_cancel_break())

        # Best effort: sentrer over parent
        try:
            self.update_idletasks()
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w = self.winfo_width()
            h = self.winfo_height()
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            self.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _on_save_break(self) -> str:
        self._on_save()
        return "break"

    def _on_cancel_break(self) -> str:
        self._on_cancel()
        return "break"

    def _on_save(self) -> None:
        self._result = self._var.get()
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _on_cancel(self) -> None:
        self._result = None
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def show(self) -> Optional[str]:
        """Vis dialogen modalt og returner kommentar (evt. tom) eller None ved avbryt."""
        try:
            self.grab_set()
        except Exception:
            pass
        self.wait_window(self)
        return self._result


def edit_combo_comment(parent: tk.Misc, *, combo: str, initial_comment: str = "") -> Optional[str]:
    """Åpner dialog og returnerer ny kommentar.

    Returnerer:
    - None dersom bruker avbryter
    - ellers streng (kan være tom -> betyr "fjern kommentar")
    """
    dlg = ComboCommentDialog(parent, combo=combo, initial_comment=initial_comment)
    return dlg.show()
