from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from io_utils import fmt_amount
from models import DECIMAL_COMMA


# ----------------------------- RANGE SLIDER -----------------------------

class RangeSlider(ttk.Frame):
    """To-håndtaks range-slider (ttk.Scale x 2) + manuell input."""
    def __init__(self, master, command=None):
        super().__init__(master)
        self.command = command
        self._min = 0.0
        self._max = 1.0
        self._v1 = tk.DoubleVar(value=0.0)
        self._v2 = tk.DoubleVar(value=1.0)

        top = ttk.Frame(self); top.pack(fill=tk.X)
        self.lbl_lo = ttk.Label(top, text="Min: –")
        self.lbl_hi = ttk.Label(top, text="Maks: –")
        self.lbl_lo.pack(side=tk.LEFT); self.lbl_hi.pack(side=tk.RIGHT)

        body = ttk.Frame(self); body.pack(fill=tk.X, pady=2)
        self.s1 = ttk.Scale(body, from_=0, to=1, variable=self._v1, command=self._on_slide1)
        self.s2 = ttk.Scale(body, from_=0, to=1, variable=self._v2, command=self._on_slide2)
        self.s1.pack(fill=tk.X, padx=2); self.s2.pack(fill=tk.X, padx=2, pady=(4, 0))

        entry = ttk.Frame(self); entry.pack(fill=tk.X, pady=2)
        ttk.Label(entry, text="Min:").pack(side=tk.LEFT)
        self.ent_min = ttk.Entry(entry, width=14); self.ent_min.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Label(entry, text="Maks:").pack(side=tk.LEFT)
        self.ent_max = ttk.Entry(entry, width=14); self.ent_max.pack(side=tk.LEFT, padx=(2, 8))
        ttk.Button(entry, text="Bruk", command=self._apply_entries).pack(side=tk.LEFT)
        ttk.Button(entry, text="Nullstill", command=self._reset).pack(side=tk.RIGHT)

        self._refresh_labels()

    # --- public API ---
    def set_bounds(self, lo: float, hi: float):
        self._min, self._max = float(lo), float(hi)
        if self._max < self._min: self._max = self._min
        for sc in (self.s1, self.s2):
            sc.configure(from_=self._min, to=self._max)
        self.set_values(self._min, self._max)

    def set_values(self, lo: float, hi: float):
        lo = max(self._min, min(float(lo), self._max))
        hi = max(self._min, min(float(hi), self._max))
        if lo > hi: lo, hi = hi, lo
        self._v1.set(lo); self._v2.set(hi)
        self._refresh_labels(); self._sync_entries(); self._emit()

    def get_values(self):
        v1, v2 = float(self._v1.get()), float(self._v2.get())
        return (min(v1, v2), max(v1, v2))

    # --- internals ---
    def _emit(self):
        if callable(self.command):
            lo, hi = self.get_values()
            self.command(lo, hi)

    def _on_slide1(self, _=None):
        if self._v1.get() > self._v2.get(): self._v2.set(self._v1.get())
        self._refresh_labels(); self._sync_entries(); self._emit()

    def _on_slide2(self, _=None):
        if self._v2.get() < self._v1.get(): self._v1.set(self._v2.get())
        self._refresh_labels(); self._sync_entries(); self._emit()

    def _refresh_labels(self):
        lo, hi = self.get_values()
        self.lbl_lo.configure(text=f"Min: {fmt_amount(lo)}")
        self.lbl_hi.configure(text=f"Maks: {fmt_amount(hi)}")

    def _sync_entries(self):
        lo, hi = self.get_values()
        self.ent_min.delete(0, tk.END)
        self.ent_min.insert(0, f"{lo:.2f}".replace(".", "," if DECIMAL_COMMA else "."))
        self.ent_max.delete(0, tk.END)
        self.ent_max.insert(0, f"{hi:.2f}".replace(".", "," if DECIMAL_COMMA else "."))

    def _apply_entries(self):
        def parse(s: str) -> float:
            s = (s or "").strip().replace(" ", "")
            s = s.replace(".", "") if DECIMAL_COMMA else s.replace(",", "")
            s = s.replace(",", ".")
            return float(s)
        try:
            lo = parse(self.ent_min.get()); hi = parse(self.ent_max.get())
        except Exception:
            return
        self.set_values(lo, hi)

    def _reset(self):
        self.set_values(self._min, self._max)


# ----------------------------- STATSGRID --------------------------------

class StatsGrid(ttk.Frame):
    """Rutenettvisning for deskriptiv statistikk."""
    FIELDS = [
        ("linjer", "Linjer"), ("bilag_unike", "Bilag (unik)"), ("konto_unike", "Konto (unik)"),
        ("sum", "Sum (netto)"), ("debet", "Debet"), ("kredit", "Kredit"),
        ("min", "Min"), ("p25", "P25"), ("median", "Median"), ("p75", "P75"),
        ("maks", "Maks"), ("snitt", "Snitt"), ("std", "Std.avvik"),
    ]
    def __init__(self, master):
        super().__init__(master, padding=(2, 2))
        self.labels = {}
        for i, (key, title) in enumerate(self.FIELDS):
            ttk.Label(self, text=title + ":").grid(row=i, column=0, sticky="w", padx=(0, 6))
            lbl = ttk.Label(self, text="")
            lbl.grid(row=i, column=1, sticky="e")
            self.labels[key] = lbl
        self.grid_columnconfigure(1, weight=1)

    def update_values(self, stats: dict):
        for key, _title in self.FIELDS:
            val = stats.get(key, "")
            self.labels[key].configure(text=str(val))
