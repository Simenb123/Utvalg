# -*- coding: utf-8 -*-
"""
ui_loading.py – Enkel, global "loading overlay" for Tkinter.
Bruk:
    from ui_loading import LoadingOverlay
    self.loading = LoadingOverlay(self)
    with self.loading.busy("Bygger datasett..."):
        tung_job()
Egenskaper:
- Modal toppvindu med progressbar (indeterminate) og tekst.
- Setter musepeker til "watch".
- Sikker mot nested bruk (teller antall enter/exit).
"""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from contextlib import contextmanager

class LoadingOverlay:
    def __init__(self, master: tk.Misc) -> None:
        self.master = master
        self._win: tk.Toplevel | None = None
        self._count = 0
        self._label_text = tk.StringVar(value="Arbeider...")

    def _create(self) -> None:
        if self._win is not None:
            return
        parent = self.master.winfo_toplevel() if hasattr(self.master, "winfo_toplevel") else self.master
        win = tk.Toplevel(parent)
        win.withdraw()
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        frm = ttk.Frame(win, padding=20)
        frm.pack(fill="both", expand=True)
        lbl = ttk.Label(frm, textvariable=self._label_text, anchor="center")
        pb = ttk.Progressbar(frm, mode="indeterminate", length=280)
        lbl.pack(fill="x", pady=(4,8))
        pb.pack(fill="x")
        self._pb = pb
        self._win = win

    def show(self, text: str = "Arbeider...") -> None:
        self._create()
        self._count += 1
        self._label_text.set(text)
        win = self._win
        if not win:
            return
        parent = self.master.winfo_toplevel()
        parent.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        if pw == 1 and ph == 1:
            parent.update_idletasks()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        ww, wh = 360, 90
        x = px + (pw - ww)//2
        y = py + (ph - wh)//2
        win.geometry(f"{ww}x{wh}+{x}+{y}")
        win.deiconify()
        try:
            parent.config(cursor="watch")
        except Exception:
            pass
        try:
            self._pb.start(12)
        except Exception:
            pass
        win.update_idletasks()

    def hide(self) -> None:
        if self._count > 0:
            self._count -= 1
        if self._count > 0:
            return
        win = self._win
        if not win:
            return
        try:
            self._pb.stop()
        except Exception:
            pass
        try:
            self.master.winfo_toplevel().config(cursor="")
        except Exception:
            pass
        win.withdraw()

    @contextmanager
    def busy(self, text: str = "Arbeider..."):
        self.show(text)
        try:
            yield
        finally:
            self.hide()
