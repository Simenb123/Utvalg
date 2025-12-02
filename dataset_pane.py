# -*- coding: utf-8 -*-
"""
dataset_pane.py – R12f+hotfix+extensions
----------------------------------------
Denne modulen bygger brukergrensesnittet for å velge og mappe kolonner fra
et datasett før det lastes inn i resten av applikasjonen. Koden er
basert på den offisielle R12f+hotfix‑utgaven av Utvalg, men vi har
gjort noen forbedringer:

* **Utvidet combobox‑høyde:** Alle nedtrekksmenyer for kolonnekarting
  (`ttk.Combobox`) settes nå opp med `height=15`. Dette gjør det lettere
  å bla i lister med mange kolonnenavn, siden flere elementer vises
  samtidig før brukeren må skrolle.
* Ingen annen funksjonalitet er endret; modulen laster fortsatt inn
  overskrifter, gjetter mapping basert på historikk og alias (via
  `ml_map_utils.suggest_mapping`) og bygger datasett raskt med
  `dataset_build_fast.build_from_file`.

Modulen støtter en `on_dataset_ready`‑callback for å varsle andre
komponenter når datasettet er bygd, og håndterer fravær av `session`
og `bus` på en trygg måte.
"""

from __future__ import annotations
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import List, Dict, Optional, Callable

import pandas as pd

# session og bus er valgfrie; vi håndterer fravær trygt
try:
    import session  # type: ignore
except Exception:
    class session:  # type: ignore
        dataset = None

try:
    import bus  # type: ignore
except Exception:
    class bus:  # type: ignore
        @staticmethod
        def emit(_name, _payload=None) -> None:
            return None

# loading overlay (fallback no-op om modulen ikke finnes)
try:
    from ui_loading import LoadingOverlay
except Exception:
    class LoadingOverlay:
        def __init__(self, *_a, **_k) -> None:
            pass
        def busy(self, *_a, **_k):
            class _C:
                def __enter__(self_s) -> None: return None
                def __exit__(self_s, *e) -> bool: return False
            return _C()

# ML + rask bygging
from ml_map_utils import load_ml_map, suggest_mapping, update_ml_map
from dataset_build_fast import build_from_file

CANON = [
    "Konto", "Kontonavn", "Bilag", "Beløp", "Dato", "Tekst",
    "Kundenr", "Kundenavn", "Leverandørnr", "Leverandørnavn",
    "MVA-kode", "MVA-beløp", "MVA-prosent", "Valuta", "Valutabeløp"
]

class DatasetPane(ttk.Frame):
    def __init__(self, master, **kwargs) -> None:
        # Ta ut våre egne kwargs FØR super().__init__ for å unngå TclError
        self._on_ready: Optional[Callable[[pd.DataFrame], None]] = kwargs.pop("on_dataset_ready", None)
        # Valgfri error-callback hvis noen har brukt det i UI (støttes stille)
        self._on_error: Optional[Callable[[Exception], None]] = kwargs.pop("on_error", None)
        # Viktig: ikke send ukjente kwargs videre til ttk.Frame
        super().__init__(master, **kwargs)
        self.loading = LoadingOverlay(self)
        self.path_var = tk.StringVar(value="")
        self.headers: List[str] = []
        self.combos: Dict[str, ttk.Combobox] = {}
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        # Filrad
        rowf = ttk.Frame(self)
        rowf.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        ttk.Label(rowf, text="Fil:").pack(side="left")
        ttk.Entry(rowf, textvariable=self.path_var, width=70).pack(side="left", padx=(4, 8))
        ttk.Button(rowf, text="Bla…", command=self._choose_file).pack(side="left")
        ttk.Button(rowf, text="Last inn header", command=self._load_headers).pack(side="left", padx=(6, 0))
        # Mapping
        frm = ttk.LabelFrame(self, text="Kolonnemapping")
        frm.grid(row=1, column=0, sticky="ew", padx=8, pady=8)
        frm.columnconfigure(1, weight=1)
        r = 0
        for canon in CANON:
            ttk.Label(frm, text=f"{canon}:").grid(row=r, column=0, sticky="w", padx=6, pady=2)
            # her er forbedringen: height=15 gjør listen dypere
            cb = ttk.Combobox(frm, values=[], state="readonly", width=50, height=15)
            cb.grid(row=r, column=1, sticky="ew", padx=6, pady=2)
            self.combos[canon] = cb
            r += 1
        # Knapper
        rowb = ttk.Frame(self)
        rowb.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 8))
        ttk.Button(rowb, text="Gjett mapping", command=self._guess).pack(side="left")
        ttk.Button(rowb, text="Bygg datasett", command=self._build_dataset).pack(side="left", padx=(8, 0))
        # Status
        self.status = ttk.Label(self, text="Klar.")
        self.status.grid(row=3, column=0, sticky="w", padx=8, pady=(0, 8))

    # ---------- Actions ----------
    def _choose_file(self) -> None:
        p = filedialog.askopenfilename(
            title="Velg fil",
            filetypes=[("Regnskapsdata", "*.xlsx;*.xls;*.csv;*.txt"), ("Alle", "*.*")],
        )
        if not p:
            return
        self.path_var.set(p)
        self._load_headers()

    def _read_headers_only(self, path: str) -> List[str]:
        ext = os.path.splitext(path)[1].lower()
        if ext in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"):
            try:
                df0 = pd.read_excel(path, nrows=0, engine="openpyxl")
                return list(df0.columns)
            except Exception:
                pass
        try:
            df0 = pd.read_csv(path, nrows=0, sep=None, engine="python")
            return list(df0.columns)
        except Exception:
            try:
                df0 = pd.read_csv(path, nrows=0, sep=";", encoding="utf-8")
                return list(df0.columns)
            except Exception:
                return []

    def _load_headers(self) -> None:
        p = self.path_var.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning("Fil", "Velg gyldig fil først.")
            return
        with self.loading.busy("Leser overskrifter…"):
            cols = self._read_headers_only(p)
            self.headers = cols
            # Tilbakestill combobox-verdier og populér med nye kolonner
            for cb in self.combos.values():
                cb["values"] = cols
                cb.set("")
            # ML-foreslå mapping basert på historikk og alias
            ml = load_ml_map()
            mapping = suggest_mapping(cols, ml) or {}
            for canon, src in mapping.items():
                if canon in self.combos and src in cols:
                    self.combos[canon].set(src)
            # Beregn antall felter som ble truffet via ML/alias
            num_hits = len([c for c in CANON if mapping.get(c)])
        # Oppdater status med både antall kolonner og antall felter som ble gjettet
        try:
            self.status.configure(
                text=f"Lest {len(self.headers)} kolonner. Fant {num_hits}/{len(CANON)} felt (ML/alias)."
            )
        except Exception:
            self.status.configure(text=f"Lest {len(self.headers)} kolonner.")

    def _guess(self) -> None:
        if not self.headers:
            self._load_headers()
            if not self.headers:
                return
        ml = load_ml_map()
        mapping = suggest_mapping(self.headers, ml) or {}
        for canon, src in mapping.items():
            cb = self.combos.get(canon)
            if cb and src in self.headers:
                cb.set(src)
        # Oppdater status med antall trufne felt
        num_hits = len([c for c in CANON if mapping.get(c)])
        try:
            self.status.configure(text=f"Gjettet {num_hits}/{len(CANON)} felt (ML/alias).")
        except Exception:
            pass

    def _build_dataset(self) -> None:
        p = self.path_var.get().strip()
        if not p or not os.path.exists(p):
            messagebox.showwarning("Fil", "Velg gyldig fil først.")
            return
        # samle mapping
        mapping = {
            canon: self.combos[canon].get().strip()
            for canon in CANON
            if canon in self.combos and self.combos[canon].get().strip()
        }
        missing = [c for c in ["Konto", "Kontonavn", "Bilag", "Beløp"] if c not in mapping]
        if missing:
            messagebox.showwarning("Kolonner", f"Mangler påkrevde felter: {', '.join(missing)}")
            return
        df: Optional[pd.DataFrame] = None
        try:
            # Vis en dedikert Toplevel med fremdriftsindikator for å gjøre
            # brukeropplevelsen tydelig. Selv om GUI kan fryse under
            # innlesingen, vil dette vinduet gjøre det klart at noe skjer.
            progress: Optional[tk.Toplevel] = tk.Toplevel(self)
            try:
                progress.title("Laster datasett")
                # Gjør vinduet modal og transient til toppvinduet
                root = self.winfo_toplevel()
                progress.transient(root)
                progress.grab_set()
                progress.resizable(False, False)
                # Senter vinduet på foreldrevinduet
                root.update_idletasks()
                w, h = 420, 140
                rx, ry = root.winfo_rootx(), root.winfo_rooty()
                rw, rh = root.winfo_width(), root.winfo_height()
                x = rx + (rw - w) // 2
                y = ry + (rh - h) // 2
                progress.geometry(f"{w}x{h}+{x}+{y}")
                # Tekst og progressbar
                ttk.Label(progress, text="Laster datasett, vennligst vent…", padding=12).pack(anchor="center")
                pb = ttk.Progressbar(progress, mode="indeterminate")
                pb.pack(fill="x", padx=16, pady=(0, 16))
                pb.start(10)
                progress.update_idletasks()
            except Exception:
                progress = None
            with self.loading.busy("Bygger datasett…"):
                # Tving frem oppdatering av GUI slik at overlay og toppvindu vises
                try:
                    self.update_idletasks()
                except Exception:
                    pass
                # Rask bygging
                df = build_from_file(p, mapping=mapping)
                # Lagre ML
                try:
                    ml = load_ml_map()
                    update_ml_map(self.headers, mapping, ml)
                except Exception:
                    pass
                # Lagre i session + bus
                session.dataset = df
                try:
                    bus.emit("DATASET_BUILT", df)
                except Exception:
                    pass
        except Exception as e:
            # Lukk progresjonsvindu ved feil
            try:
                if progress is not None:
                    progress.destroy()
            except Exception:
                pass
            if callable(self._on_error):
                try:
                    self._on_error(e)
                except Exception:
                    pass
            messagebox.showerror("Datasett", f"Feil ved bygging: {e}")
            return
        # Lukk progresjonsvindu etter vellykket bygging
        try:
            if progress is not None:
                progress.destroy()
        except Exception:
            pass
        n = len(df) if isinstance(df, pd.DataFrame) else 0
        k = len(df.columns) if isinstance(df, pd.DataFrame) else 0
        self.status.configure(text=f"Datasett bygd: rader={n:,} kolonner={k}".replace(",", " "))
        try:
            messagebox.showinfo("Datasett", f"Klar. Rader={n:,} | Kolonner={k}".replace(",", " "))
        except Exception:
            pass
        # Varsle UI at datasett er klart
        if callable(self._on_ready) and isinstance(df, pd.DataFrame):
            try:
                self._on_ready(df)
            except Exception:
                pass