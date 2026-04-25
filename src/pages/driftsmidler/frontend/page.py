"""DriftsmidlerPage — Tk-widget for driftsmiddel-fanen.

Tynt frontend-lag: bygger Tk-widgets, leser data fra Analyse-siden og
delegerer all forretningslogikk til ``..backend.compute``.

Backend kan testes hodeløst og vil senere kunne eksponeres via
REST-endepunkter for en evt. React-frontend.
"""
from __future__ import annotations

import logging
import tkinter as tk
from tkinter import ttk
from typing import Any

import pandas as pd

import analyse_treewidths
import formatting

from ..backend.compute import (
    build_dm_reconciliation,
    classify_dm_transactions,
    get_konto_ranges,
    safe_float,
)

log = logging.getLogger(__name__)


_TAG_HEADER = "header"
_FMT = formatting.fmt_amount


class DriftsmidlerPage(ttk.Frame):
    """Driftsmidler-fane med automatisk avstemming."""

    def __init__(self, parent: Any) -> None:
        super().__init__(parent)
        self._analyse_page: Any = None
        self._reconciliation: dict[str, Any] | None = None
        self._classified_df: pd.DataFrame | None = None
        self._build_ui()

    # --- Public API ---

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page

    def refresh_from_session(self, session: Any = None, **_kw: Any) -> None:
        try:
            self.after(50, self._refresh)
        except Exception:
            self._refresh()

    def get_note_data(self) -> dict[str, str]:
        """Returnér data for auto-fylling av DRIFTSMIDLER_SPEC."""
        r = self._reconciliation
        if not r:
            return {}
        return {
            "dm_akk_01": _FMT(r["kostpris_ib"], 0),
            "dm_tilgang": _FMT(r["tilgang"], 0),
            "dm_avgang": _FMT(r["avgang"], 0),
            "dm_akk_31": _FMT(r["kostpris_ub_sb"], 0),
            "dm_avskr_01": _FMT(r["avskr_ib"], 0),
            "dm_avskr_aar": _FMT(r["avskr_aar"], 0),
            "dm_avskr_31": _FMT(r["avskr_ub_sb"], 0),
        }

    # --- UI ---

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Toolbar
        top = ttk.Frame(self, padding=(8, 6, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        self._status_var = tk.StringVar(value="Laster...")
        ttk.Label(top, textvariable=self._status_var,
                  font=("TkDefaultFont", 9)).grid(row=0, column=0, sticky="w")
        ttk.Button(top, text="Oppdater", command=self._refresh).grid(
            row=0, column=1, padx=(8, 0))

        # Avstemming (LabelFrame)
        self._lf_recon = ttk.LabelFrame(self, text="Avstemming — varige driftsmidler",
                                        padding=(8, 4, 8, 6))
        self._lf_recon.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._lf_recon.columnconfigure(1, weight=1)

        self._recon_vars: dict[str, tk.StringVar] = {}
        rows = [
            ("header_kp", "KOSTPRIS", None),
            ("kostpris_ib", "Anskaffelseskost 01.01", ""),
            ("tilgang", "+ Tilgang", ""),
            ("avgang", "- Avgang", ""),
            ("kostpris_ub", "= Anskaffelseskost 31.12", ""),
            ("kostpris_ctrl", "  Kontroll (SB UB)", ""),
            ("sep1", None, None),
            ("header_av", "AKK. AVSKRIVNINGER", None),
            ("avskr_ib", "01.01", ""),
            ("avskr_aar", "+ Årets avskrivninger", ""),
            ("avskr_ub", "= 31.12", ""),
            ("avskr_ctrl", "  Kontroll (SB UB)", ""),
            ("sep2", None, None),
            ("bokfort", "BOKFØRT VERDI 31.12", ""),
            ("bokfort_ctrl", "  Kontroll (regnr 555)", ""),
        ]

        for i, (key, label, default) in enumerate(rows):
            if key.startswith("sep"):
                ttk.Separator(self._lf_recon, orient="horizontal").grid(
                    row=i, column=0, columnspan=3, sticky="ew", pady=3)
                continue
            if key.startswith("header"):
                ttk.Label(self._lf_recon, text=label,
                          font=("TkDefaultFont", 9, "bold")).grid(
                    row=i, column=0, columnspan=3, sticky="w", pady=(4, 1))
                continue
            ttk.Label(self._lf_recon, text=label).grid(
                row=i, column=0, sticky="w", padx=(12, 6))
            svar = tk.StringVar(value=default or "")
            self._recon_vars[key] = svar
            ttk.Label(self._lf_recon, textvariable=svar, anchor="e",
                      width=18).grid(row=i, column=1, sticky="e", padx=(0, 6))

        self._recon_info_var = tk.StringVar(value="")
        ttk.Label(self._lf_recon, textvariable=self._recon_info_var,
                  foreground="#555", font=("TkDefaultFont", 8)).grid(
            row=len(rows), column=0, columnspan=3, sticky="w", pady=(4, 0))

        # Tabs: Kontoer + Transaksjoner
        nb = ttk.Notebook(self)
        nb.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))

        # Tab: Kontoer
        tab_konto = ttk.Frame(nb)
        tab_konto.columnconfigure(0, weight=1)
        tab_konto.rowconfigure(0, weight=1)
        nb.add(tab_konto, text="Kontoer")

        konto_cols = ("Konto", "Kontonavn", "IB", "Bevegelse", "UB", "Type")
        self._tree_konto = ttk.Treeview(tab_konto, columns=konto_cols,
                                        show="headings", height=8)
        for c in konto_cols:
            anchor = analyse_treewidths.column_anchor(c)
            self._tree_konto.heading(c, text=c, anchor=anchor)
            self._tree_konto.column(
                c,
                width=analyse_treewidths.default_column_width(c),
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=anchor,
                stretch=c == "Kontonavn",
            )
        vsb_k = ttk.Scrollbar(tab_konto, orient="vertical",
                               command=self._tree_konto.yview)
        self._tree_konto.configure(yscrollcommand=vsb_k.set)
        self._tree_konto.grid(row=0, column=0, sticky="nsew")
        vsb_k.grid(row=0, column=1, sticky="ns")

        # Tab: Transaksjoner
        tab_tx = ttk.Frame(nb)
        tab_tx.columnconfigure(0, weight=1)
        tab_tx.rowconfigure(0, weight=1)
        nb.add(tab_tx, text="Transaksjoner")

        tx_cols = ("Bilag", "Dato", "Konto", "Kontonavn", "Tekst",
                   "Beløp", "Motpost", "Kategori")
        self._tree_tx = ttk.Treeview(tab_tx, columns=tx_cols,
                                     show="headings", height=12)
        for c in tx_cols:
            anchor = analyse_treewidths.column_anchor(c)
            self._tree_tx.heading(c, text=c, anchor=anchor)
            self._tree_tx.column(
                c,
                width=analyse_treewidths.default_column_width(c),
                minwidth=analyse_treewidths.column_minwidth(c),
                anchor=anchor,
                stretch=c == "Tekst",
            )
        self._tree_tx.tag_configure("tilgang", foreground="#1a7a2a")
        self._tree_tx.tag_configure("avgang", foreground="#C00000")
        self._tree_tx.tag_configure("avskrivning", foreground="#1a5fa8")
        self._tree_tx.tag_configure("ukjent", foreground="#C00000",
                                    background="#FFF8E1")
        self._tree_tx.tag_configure("omklassifisering", foreground="#666")

        vsb_t = ttk.Scrollbar(tab_tx, orient="vertical",
                               command=self._tree_tx.yview)
        self._tree_tx.configure(yscrollcommand=vsb_t.set)
        self._tree_tx.grid(row=0, column=0, sticky="nsew")
        vsb_t.grid(row=0, column=1, sticky="ns")

    # --- Data refresh ---

    def _refresh(self) -> None:
        page = self._analyse_page
        if page is None:
            self._status_var.set("Ikke koblet til Analyse-siden")
            return

        df_all = getattr(page, "_df_filtered", None)
        if df_all is None or (hasattr(df_all, "empty") and df_all.empty):
            self._status_var.set("Ingen transaksjonsdata lastet")
            return

        try:
            sb_df = page._get_effective_sb_df()
        except Exception:
            sb_df = getattr(page, "_rl_sb_df", None)

        # Hent intervals + regnskapslinjer fra Analyse-siden, send dem
        # som rene data inn til backend (som ikke kjenner til page-objektet).
        intervals = getattr(page, "_rl_intervals", None)
        regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
        dm_ranges = get_konto_ranges(intervals, regnskapslinjer, 555)
        avskr_ranges = get_konto_ranges(intervals, regnskapslinjer, 50)

        if not dm_ranges:
            self._status_var.set("Ingen kontorange for regnr 555 (varige driftsmidler)")
            return

        # Klassifiser transaksjoner
        classified = classify_dm_transactions(df_all, dm_ranges, avskr_ranges)
        self._classified_df = classified

        # Hent regnr 555 UB fra pivot. Bruk _pivot_df_rl (RL-spesifikk),
        # ikke _pivot_df_last — sistnevnte kan være konto-pivot uten regnr.
        regnr_555_ub = None
        pivot_df = getattr(page, "_pivot_df_rl", None)
        if pivot_df is not None and not pivot_df.empty and "regnr" in pivot_df.columns:
            row_555 = pivot_df[pivot_df["regnr"].astype(int) == 555]
            if not row_555.empty and "UB" in row_555.columns:
                regnr_555_ub = safe_float(row_555["UB"].iloc[0])

        # Bygg avstemming
        recon = build_dm_reconciliation(sb_df, classified, dm_ranges,
                                         regnr_555_ub=regnr_555_ub)
        self._reconciliation = recon

        # Oppdater GUI
        n_kontoer = len(recon["kontoer"]) if isinstance(recon["kontoer"], pd.DataFrame) else 0
        n_tx = len(classified) if classified is not None and not classified.empty else 0
        self._status_var.set(
            f"Regnr 555 — {n_kontoer} kontoer — {n_tx} transaksjoner")

        self._populate_reconciliation(recon)
        self._populate_accounts(recon.get("kontoer", pd.DataFrame()))
        self._populate_transactions(classified)

    def _populate_reconciliation(self, r: dict[str, Any]) -> None:
        f = lambda v: _FMT(v, 0) if v is not None else "–"

        def _check(avvik: float) -> str:
            return "✓" if abs(avvik) < 1.0 else f"⚠ avvik {_FMT(avvik, 0)}"

        self._recon_vars["kostpris_ib"].set(f(r["kostpris_ib"]))
        self._recon_vars["tilgang"].set(
            f"{f(r['tilgang'])}   ({r['tilgang_tx']} tx)")
        self._recon_vars["avgang"].set(
            f"{f(r['avgang'])}   ({r['avgang_tx']} tx)")
        self._recon_vars["kostpris_ub"].set(f(r["kostpris_ub_beregnet"]))
        self._recon_vars["kostpris_ctrl"].set(
            f"{f(r['kostpris_ub_sb'])}   {_check(r['kostpris_avvik'])}")

        self._recon_vars["avskr_ib"].set(f(r["avskr_ib"]))
        self._recon_vars["avskr_aar"].set(
            f"{f(r['avskr_aar'])}   ({r['avskr_tx']} tx)")
        self._recon_vars["avskr_ub"].set(f(r["avskr_ub_beregnet"]))
        self._recon_vars["avskr_ctrl"].set(
            f"{f(r['avskr_ub_sb'])}   {_check(r['avskr_avvik'])}")

        self._recon_vars["bokfort"].set(f(r["bokfort_verdi"]))
        regnr_ub = r.get("regnr_555_ub")
        if regnr_ub is not None:
            diff = abs(r["bokfort_verdi"] - regnr_ub)
            self._recon_vars["bokfort_ctrl"].set(
                f"{f(regnr_ub)}   {_check(diff)}")
        else:
            self._recon_vars["bokfort_ctrl"].set("–")

        # Info
        parts = []
        if r["ukjente_tx"] > 0:
            parts.append(f"⚠ {r['ukjente_tx']} transaksjoner ikke klassifisert")
        if abs(r["omklassifisering"]) > 0.01:
            parts.append(f"Omklassifisering: {_FMT(r['omklassifisering'], 0)}")
        self._recon_info_var.set("  |  ".join(parts) if parts else "")

    def _populate_accounts(self, df: pd.DataFrame) -> None:
        tree = self._tree_konto
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            return
        for _, row in df.iterrows():
            tree.insert("", "end", values=(
                str(row.get("konto", "")),
                str(row.get("kontonavn", "")),
                _FMT(safe_float(row.get("ib")), 0),
                _FMT(safe_float(row.get("bevegelse")), 0),
                _FMT(safe_float(row.get("ub")), 0),
                str(row.get("_type", "")),
            ))

    def _populate_transactions(self, df: pd.DataFrame) -> None:
        tree = self._tree_tx
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            return

        tag_map = {
            "Tilgang": "tilgang", "Avgang": "avgang",
            "Avskrivning": "avskrivning", "Ukjent": "ukjent",
            "Omklassifisering": "omklassifisering",
        }

        # Bruk .itertuples() for raskere iterasjon (5-10x vs iterrows)
        cols = {c: i for i, c in enumerate(df.columns)}
        for tup in df.itertuples(index=False):
            kat = str(tup[cols["dm_kategori"]]) if "dm_kategori" in cols else ""
            tag = tag_map.get(kat, "")
            motpost = str(tup[cols["_motpost_konto"]]) if "_motpost_konto" in cols else ""
            motpost_navn = str(tup[cols["_motpost_navn"]]) if "_motpost_navn" in cols else ""
            motpost_str = f"{motpost} {motpost_navn}".strip() if motpost else ""
            bilag = str(tup[cols["_bilag"]]) if "_bilag" in cols else str(tup[cols.get("Bilag", 0)])
            dato = str(tup[cols["Dato"]])[:10] if "Dato" in cols else ""

            tree.insert("", "end", values=(
                bilag, dato,
                str(tup[cols.get("Konto", 0)]),
                str(tup[cols.get("Kontonavn", 0)]) if "Kontonavn" in cols else "",
                str(tup[cols.get("Tekst", 0)]) if "Tekst" in cols else "",
                _FMT(tup[cols["_belop"]]) if "_belop" in cols else "",
                motpost_str,
                kat,
            ), tags=(tag,) if tag else ())
