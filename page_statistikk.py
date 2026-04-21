"""page_statistikk.py — Statistikk-fane for Utvalg."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
    from tkinter.filedialog import asksaveasfilename
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


# Data-beregning (utskilt til page_statistikk_compute)
from page_statistikk_compute import (  # noqa: E402
    _AMT_FMT,
    _compute_bilag,
    _compute_extra_stats,
    _compute_kontoer,
    _compute_maned_pivot,
    _compute_motpost,
    _compute_mva,
    _filter_df,
    _fmt_amount,
    _fmt_pct,
    _get_konto_ranges,
    _get_konto_set_for_regnr,
    _safe_float,
    _safe_int,
    _sb_kontoer_in_ranges,
)


def _open_file(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Treeview-sortering
# ---------------------------------------------------------------------------

_SORT_STATE: dict[tuple[int, str], bool] = {}  # (id(tree), col) → ascending


def _sort_col(tree: object, col: str) -> None:
    """Sorter treeview etter kolonne ved klikk på header. Sum-rader holdes nederst."""
    key = (id(tree), col)
    ascending = not _SORT_STATE.get(key, False)
    _SORT_STATE[key] = ascending

    items = list(tree.get_children(""))  # type: ignore[union-attr]
    pinned = [i for i in items if "sum" in (tree.item(i, "tags") or ())]  # type: ignore[union-attr]
    sortable = [i for i in items if i not in set(pinned)]

    def _key(iid: str) -> tuple:
        raw = str(tree.set(iid, col))  # type: ignore[union-attr]
        cleaned = raw.replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace("%", "").replace("\u2013", "0")
        try:
            return (0, float(cleaned))
        except ValueError:
            return (1, raw.lower())

    sortable.sort(key=_key, reverse=not ascending)

    # Oppdater heading-tekst med pil
    for c in tree["columns"]:  # type: ignore[index]
        txt = str(tree.heading(c, "text")).rstrip(" ▲▼")  # type: ignore[union-attr]
        tree.heading(c, text=txt)  # type: ignore[union-attr]
    arrow = " \u25b2" if ascending else " \u25bc"
    cur_txt = str(tree.heading(col, "text")).rstrip(" ▲▼")  # type: ignore[union-attr]
    tree.heading(col, text=cur_txt + arrow)  # type: ignore[union-attr]

    for idx, iid in enumerate(sortable + pinned):
        tree.move(iid, "", idx)  # type: ignore[union-attr]


def _attach_sort(tree: object) -> None:
    """Kobler klikk-sortering til alle kolonner i ett treeview."""
    for col in tree["columns"]:  # type: ignore[index]
        tree.heading(col, command=lambda c=col, t=tree: _sort_col(t, c))  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Widget-hjelper
# ---------------------------------------------------------------------------

def _make_tree(
    parent: object,
    cols: tuple,
    widths: dict,
    *,
    text_cols: tuple = (),
    stretch_col: str | None = None,
    with_hscroll: bool = False,
) -> "ttk.Treeview":
    frame = ttk.Frame(parent)  # type: ignore[misc]
    frame.grid(row=0, column=0, sticky="nsew")
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(frame, columns=cols, show="headings")  # type: ignore[misc]
    for col in cols:
        tree.column(col, width=widths.get(col, 100),
                    anchor="w" if col in text_cols else "e",
                    stretch=(col == stretch_col))
        tree.heading(col, text=col)

    vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)  # type: ignore[misc]
    tree.configure(yscrollcommand=vsb.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")

    if with_hscroll:
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)  # type: ignore[misc]
        tree.configure(xscrollcommand=hsb.set)
        hsb.grid(row=1, column=0, sticky="ew")

    _attach_sort(tree)
    return tree


# ---------------------------------------------------------------------------
# StatistikkPage
# ---------------------------------------------------------------------------

class StatistikkPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, parent: object) -> None:
        super().__init__(parent)  # type: ignore[call-arg]
        self._analyse_page: Optional[object] = None
        self._current_regnr: Optional[int] = None
        self._current_rl_name: str = ""
        self._rl_options: list[tuple[int, str]] = []
        self._maned_frame: Optional[object] = None
        self._df_rl_last: Optional[pd.DataFrame] = None
        self._df_all_last: Optional[pd.DataFrame] = None
        self._mva_result_last: Optional[dict] = None
        self._motpost_data_last: Optional[pd.DataFrame] = None
        self._motpost_rl_last: Optional[pd.DataFrame] = None
        self._kombo_data_last: Optional[pd.DataFrame] = None
        self._kombo_bilag_map_last: dict[str, str] = {}
        self._kombo_rl_kontoer_last: set[str] = set()
        self._build_ui()

    # ------------------------------------------------------------------
    # Offentlig API

    def set_analyse_page(self, page: object) -> None:
        self._analyse_page = page

    def show_regnr(self, regnr: int) -> None:
        for r, name in self._rl_options:
            if r == regnr:
                self._var_rl.set(f"{r} \u2013 {name}")
                self._current_regnr = regnr
                self._current_rl_name = name
                self._refresh()
                return
        self._current_regnr = regnr
        self._current_rl_name = str(regnr)
        self._refresh()

    def refresh_from_session(self, session: object = None, **_kw: object) -> None:
        self._reload_rl_options()
        if self._current_regnr is not None:
            self._refresh()

    # ------------------------------------------------------------------
    # UI

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # Topplinje
        top = ttk.Frame(self, padding=(8, 6, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Regnskapslinje:").grid(row=0, column=0, sticky="w")
        self._var_rl = tk.StringVar()
        self._combo = ttk.Combobox(top, textvariable=self._var_rl, state="readonly", width=55)
        self._combo.grid(row=0, column=1, sticky="ew", padx=(8, 4))
        self._combo.bind("<<ComboboxSelected>>", self._on_combo_select)
        ttk.Button(top, text="Vis", command=self._refresh, width=8).grid(row=0, column=2, padx=(0, 8))
        ttk.Button(top, text="Eksporter arbeidsdokument \u2192 Excel", command=self._export).grid(row=0, column=3)

        # Nøkkeltall + ekstra stats
        kpi_outer = ttk.LabelFrame(self, text="Nøkkeltall", padding=(8, 4, 8, 6))
        kpi_outer.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        kpi_outer.columnconfigure(0, weight=1)

        kpi_frame = ttk.Frame(kpi_outer)
        kpi_frame.grid(row=0, column=0, sticky="ew")
        self._kpi_vars: dict[str, tk.StringVar] = {}
        for i, (key, label) in enumerate([
            ("ub", "UB"), ("ub_fjor", "UB i fjor"), ("endring_kr", "Endring (kr)"),
            ("endring_pct", "Endring %"), ("antall", "Antall bilag"),
        ]):
            f = ttk.Frame(kpi_frame)
            f.grid(row=0, column=i, padx=(0 if i == 0 else 20, 0), sticky="w")
            ttk.Label(f, text=label, font=("", 8), foreground="#666666").pack(anchor="w")
            var = tk.StringVar(value="\u2013")
            self._kpi_vars[key] = var
            ttk.Label(f, textvariable=var, font=("", 12, "bold")).pack(anchor="w")

        # Separator
        ttk.Separator(kpi_outer, orient="horizontal").grid(row=1, column=0, sticky="ew", pady=(6, 4))

        # Ekstra analytiske nøkkeltall (rad 2)
        ext_frame = ttk.Frame(kpi_outer)
        ext_frame.grid(row=2, column=0, sticky="ew")
        self._ext_vars: dict[str, tk.StringVar] = {}
        for i, (key, label) in enumerate([
            ("top10", "Topp 10 bilag"),
            ("n_bilag", "Unike bilag"),
            ("n_kunder", "Unike kunder"),
            ("mnd_max", "Største måned"),
            ("anomali", "Anomale måneder"),
            ("runde", "Runde beløp"),
        ]):
            f = ttk.Frame(ext_frame)
            f.grid(row=0, column=i, padx=(0 if i == 0 else 16, 0), sticky="w")
            ttk.Label(f, text=label, font=("", 8), foreground="#888888").pack(anchor="w")
            var = tk.StringVar(value="\u2013")
            self._ext_vars[key] = var
            ttk.Label(f, textvariable=var, font=("", 10)).pack(anchor="w")

        # Notebook
        self._nb = ttk.Notebook(self)
        self._nb.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))

        self._tab_kontoer = ttk.Frame(self._nb)
        self._tab_maned = ttk.Frame(self._nb)
        self._tab_bilag = ttk.Frame(self._nb)
        self._tab_mva = ttk.Frame(self._nb)
        self._tab_motpost = ttk.Frame(self._nb)
        self._tab_kombo = ttk.Frame(self._nb)

        self._nb.add(self._tab_kontoer, text="Kontoer")
        self._nb.add(self._tab_maned, text="Månedspivot")
        self._nb.add(self._tab_bilag, text="Bilag-analyse")
        self._nb.add(self._tab_mva, text="MVA-analyse")
        self._nb.add(self._tab_motpost, text="Motpostfordeling")
        self._nb.add(self._tab_kombo, text="Kombinasjoner")

        for tab in (self._tab_kontoer, self._tab_maned, self._tab_bilag, self._tab_mva, self._tab_motpost, self._tab_kombo):
            tab.columnconfigure(0, weight=1)
            tab.rowconfigure(0, weight=1)

        # --- Kontoer ---
        self._tree_kontoer = _make_tree(
            self._tab_kontoer,
            ("Konto", "Kontonavn", "IB", "Bevegelse", "UB", "Antall"),
            {"Konto": 80, "Kontonavn": 260, "IB": 140, "Bevegelse": 140, "UB": 140, "Antall": 80},
            text_cols=("Konto", "Kontonavn"), stretch_col="Kontonavn",
        )
        self._tree_kontoer.bind("<Double-Button-1>", self._on_kontoer_doubleclick)
        ttk.Label(
            self._tab_kontoer, text="Dobbeltklikk en rad for å se transaksjoner",
            foreground="#888888", font=("", 8),
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(2, 2))

        # --- Månedspivot (dynamisk) ---
        self._maned_frame = self._tab_maned

        # --- Bilag-analyse ---
        self._tree_bilag = _make_tree(
            self._tab_bilag,
            ("Bilag", "Dato", "Tekst", "Sum beløp", "Antall poster", "Kontoer"),
            {"Bilag": 80, "Dato": 90, "Tekst": 280, "Sum beløp": 140, "Antall poster": 90, "Kontoer": 200},
            text_cols=("Bilag", "Dato", "Tekst", "Kontoer"), stretch_col="Tekst",
        )
        self._tree_bilag.bind("<Double-Button-1>", self._on_bilag_doubleclick)
        ttk.Label(
            self._tab_bilag, text="Dobbeltklikk et bilag for å se enkeltposteringene",
            foreground="#888888", font=("", 8),
        ).grid(row=1, column=0, sticky="w", padx=6, pady=(2, 2))

        # --- MVA-analyse ---
        self._tab_mva.rowconfigure(1, weight=0)
        self._tab_mva.rowconfigure(2, weight=0)
        self._tree_mva = _make_tree(
            self._tab_mva,
            ("MVA-kode", "Antall", "Grunnlag", "MVA-beløp", "Sats %", "Effektiv %", "Status"),
            {"MVA-kode": 100, "Antall": 70, "Grunnlag": 150, "MVA-beløp": 150,
             "Sats %": 70, "Effektiv %": 80, "Status": 240},
            text_cols=("MVA-kode", "Status"), stretch_col="Status",
        )
        self._tree_mva.tag_configure("ok", foreground="#2E7D32")
        self._tree_mva.tag_configure("avvik", foreground="#C62828")
        self._tree_mva.tag_configure("ingen", foreground="#888888")
        self._tree_mva.bind("<Double-Button-1>", self._on_mva_doubleclick)

        # Avstemmingspanel
        avsf = ttk.LabelFrame(self._tab_mva, text="Avstemming mot totale salgsinntekter", padding=(8, 4))
        avsf.grid(row=1, column=0, sticky="ew", padx=6, pady=(4, 2))
        avsf.columnconfigure(1, weight=1)
        avsf.columnconfigure(3, weight=1)
        self._mva_avs_vars: dict[str, tk.StringVar] = {}
        _avs_fields = [
            ("bev", "Total bevegelse (RL):", 0, 0),
            ("med", "  Herav med MVA-kode:", 1, 0),
            ("uten", "  Herav uten kode:", 2, 0),
            ("faktisk", "Total faktisk MVA:", 0, 2),
            ("forventet", "Forventet MVA:", 1, 2),
            ("avvik", "Avvik:", 2, 2),
        ]
        for key, label, row_i, col_i in _avs_fields:
            ttk.Label(avsf, text=label, foreground="#555555").grid(
                row=row_i, column=col_i, sticky="w", padx=(0 if col_i == 0 else 20, 4)
            )
            var = tk.StringVar(value="\u2013")
            self._mva_avs_vars[key] = var
            fg = "#2E7D32" if key == "avvik" else "#222222"
            ttk.Label(avsf, textvariable=var, foreground=fg, font=("TkFixedFont", 10)).grid(
                row=row_i, column=col_i + 1, sticky="e"
            )

        ttk.Label(
            self._tab_mva, text="Dobbeltklikk en kode for å se transaksjoner",
            foreground="#888888", font=("", 8),
        ).grid(row=2, column=0, sticky="w", padx=6, pady=(0, 2))

        # --- Motpostfordeling ---
        self._tab_motpost.rowconfigure(0, weight=0)
        self._tab_motpost.rowconfigure(1, weight=1)
        self._tab_motpost.rowconfigure(2, weight=0)

        motpost_top = ttk.Frame(self._tab_motpost)
        motpost_top.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        ttk.Label(motpost_top, text="Gruppér på:", foreground="#555555").grid(row=0, column=0, sticky="w")
        self._var_motpost_mode = tk.StringVar(value="konto")
        ttk.Radiobutton(
            motpost_top, text="Konto", value="konto",
            variable=self._var_motpost_mode, command=self._on_motpost_mode_change,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Radiobutton(
            motpost_top, text="Regnskapslinje", value="rl",
            variable=self._var_motpost_mode, command=self._on_motpost_mode_change,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

        motpost_mid = ttk.Frame(self._tab_motpost)
        motpost_mid.grid(row=1, column=0, sticky="nsew")
        motpost_mid.columnconfigure(0, weight=1)
        motpost_mid.rowconfigure(0, weight=1)
        self._tree_motpost = _make_tree(
            motpost_mid,
            ("Konto", "Kontonavn", "Beløp", "Andel %", "Antall bilag"),
            {"Konto": 80, "Kontonavn": 260, "Beløp": 140, "Andel %": 80, "Antall bilag": 90},
            text_cols=("Konto", "Kontonavn"), stretch_col="Kontonavn",
        )
        self._tree_motpost.bind("<Double-Button-1>", self._on_motpost_doubleclick)
        motpost_bot = ttk.Frame(self._tab_motpost)
        motpost_bot.grid(row=2, column=0, sticky="ew", padx=6, pady=(2, 2))
        motpost_bot.columnconfigure(0, weight=1)
        self._motpost_hint_var = tk.StringVar(
            value="Dobbeltklikk en konto for å se tilhørende bilag"
        )
        ttk.Label(
            motpost_bot, textvariable=self._motpost_hint_var,
            foreground="#888888", font=("", 8),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(
            motpost_bot, text="\U0001f4ca  Vis flowchart", command=self._show_motpost_flowchart,
        ).grid(row=0, column=1, sticky="e")

        # --- Kombinasjoner ---
        self._tab_kombo.rowconfigure(0, weight=0)
        self._tab_kombo.rowconfigure(1, weight=1)
        self._tab_kombo.rowconfigure(2, weight=0)

        kombo_top = ttk.Frame(self._tab_kombo)
        kombo_top.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        ttk.Label(kombo_top, text="Vis kombinasjon som:", foreground="#555555").grid(row=0, column=0, sticky="w")
        self._var_kombo_mode = tk.StringVar(value="konto")
        ttk.Radiobutton(
            kombo_top, text="Kontoer", value="konto",
            variable=self._var_kombo_mode, command=self._on_kombo_mode_change,
        ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Radiobutton(
            kombo_top, text="Regnskapslinjer", value="rl",
            variable=self._var_kombo_mode, command=self._on_kombo_mode_change,
        ).grid(row=0, column=2, sticky="w", padx=(8, 0))

        kombo_mid = ttk.Frame(self._tab_kombo)
        kombo_mid.grid(row=1, column=0, sticky="nsew")
        kombo_mid.columnconfigure(0, weight=1)
        kombo_mid.rowconfigure(0, weight=1)
        self._tree_kombo = _make_tree(
            kombo_mid,
            ("Nr", "Kombinasjon", "Antall bilag", "Sum valgte kontoer", "Andel %"),
            {"Nr": 50, "Kombinasjon": 360, "Antall bilag": 90, "Sum valgte kontoer": 150, "Andel %": 80},
            text_cols=("Nr", "Kombinasjon"), stretch_col="Kombinasjon",
        )
        self._tree_kombo.bind("<Double-Button-1>", self._on_kombo_doubleclick)
        ttk.Label(
            self._tab_kombo,
            text="Dobbeltklikk en rad for å se bilagene i kombinasjonen",
            foreground="#888888", font=("", 8),
        ).grid(row=2, column=0, sticky="w", padx=6, pady=(2, 2))

        # Statuslinje
        self._status_var = tk.StringVar(value="Velg en regnskapslinje og trykk Vis")
        ttk.Label(self, textvariable=self._status_var, foreground="#555555").grid(
            row=3, column=0, sticky="w", padx=8, pady=(0, 4)
        )

    # ------------------------------------------------------------------
    # Dropdown

    def _reload_rl_options(self) -> None:
        page = self._analyse_page
        if page is None:
            return
        regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
        if regnskapslinjer is None or (hasattr(regnskapslinjer, "empty") and regnskapslinjer.empty):
            self._rl_options = []
            try:
                self._combo["values"] = []
            except Exception:
                pass
            return
        try:
            from regnskap_mapping import normalize_regnskapslinjer
            regn = normalize_regnskapslinjer(regnskapslinjer)
            self._rl_options = [
                (int(r["regnr"]), str(r.get("regnskapslinje", "") or ""))
                for _, r in regn.iterrows()
            ]
            self._combo["values"] = [f"{r} \u2013 {n}" for r, n in self._rl_options]
        except Exception as exc:
            log.warning("_reload_rl_options: %s", exc)

    def _on_combo_select(self, event: object = None) -> None:
        val = self._var_rl.get()
        if not val:
            return
        try:
            parts = val.split("\u2013", 1)
            self._current_regnr = int(parts[0].strip())
            self._current_rl_name = parts[1].strip() if len(parts) > 1 else str(self._current_regnr)
        except (ValueError, IndexError):
            pass

    # ------------------------------------------------------------------
    # Refresh

    def _refresh(self) -> None:
        self._on_combo_select()
        if self._current_regnr is None:
            self._status_var.set("Velg en regnskapslinje")
            return
        page = self._analyse_page
        if page is None:
            self._status_var.set("Ikke koblet til Analyse-siden")
            return
        df_all = getattr(page, "_df_filtered", None)
        if df_all is None or (hasattr(df_all, "empty") and df_all.empty):
            self._status_var.set("Ingen transaksjonsdata lastet")
            return

        ranges = _get_konto_ranges(page, self._current_regnr)
        df_rl = _filter_df(df_all, ranges)

        # Post-filtrer på faktisk regnr-mapping (respekterer klient-overrides).
        # Sikrer at summene i Kontoer-fanen matcher pivot-raden for regnr.
        sb_df_eff: pd.DataFrame | None = None
        try:
            sb_df_eff = page._get_effective_sb_df()  # type: ignore[union-attr]
        except Exception:
            sb_df_eff = getattr(page, "_rl_sb_df", None)
        konto_set = _get_konto_set_for_regnr(
            page, self._current_regnr, ranges,
            df_all=df_all,
            sb_df=sb_df_eff,
            sb_prev_df=getattr(page, "_rl_sb_prev_df", None),
        )
        if konto_set is not None and "Konto" in df_rl.columns:
            df_rl = df_rl[df_rl["Konto"].astype(str).isin(konto_set)].copy()

        # Lagre for drill-down
        self._df_rl_last = df_rl
        self._df_all_last = df_all

        self._update_kpi(page, self._current_regnr)
        kontoer_data, ib_label = _compute_kontoer(df_rl, page, ranges=ranges, konto_set=konto_set)
        self._populate_kontoer(kontoer_data, ib_label)
        self._rebuild_maned_pivot(df_rl)
        self._populate_bilag(_compute_bilag(df_rl))
        mva_result = _compute_mva(df_rl, df_all)
        self._mva_result_last = mva_result
        self._populate_mva(mva_result)
        motpost_data = _compute_motpost(df_all, df_rl)
        self._motpost_data_last = motpost_data
        self._motpost_rl_last = None  # reberegnes on-demand
        if getattr(self, "_var_motpost_mode", None) and self._var_motpost_mode.get() == "rl":
            self._motpost_rl_last = self._build_motpost_rl_df(motpost_data)
        self._populate_motpost(motpost_data)

        rl_kontoer = (
            set(df_rl["Konto"].dropna().astype(str).unique())
            if "Konto" in df_rl.columns
            else set()
        )
        self._kombo_rl_kontoer_last = rl_kontoer
        combos_df, bilag_map = self._compute_kombinasjoner(df_all, rl_kontoer)
        self._kombo_data_last = combos_df
        self._kombo_bilag_map_last = bilag_map
        self._populate_kombo()
        self._populate_extra_stats(_compute_extra_stats(df_rl))

        self._status_var.set(
            f"{self._current_regnr} \u2013 {self._current_rl_name}"
            f"  \u00b7  {len(df_rl):,} transaksjoner"
        )

    def _update_kpi(self, page: object, regnr: int) -> None:
        pivot_df = getattr(page, "_pivot_df_last", None)
        blank = "\u2013"
        if pivot_df is None or pivot_df.empty:
            for var in self._kpi_vars.values():
                var.set(blank)
            return
        row = next(
            (r for _, r in pivot_df.iterrows() if _safe_int(r.get("regnr", -1)) == regnr),
            None,
        )
        if row is None:
            for var in self._kpi_vars.values():
                var.set(blank)
            return
        self._kpi_vars["ub"].set(_fmt_amount(row.get("UB")))
        self._kpi_vars["ub_fjor"].set(_fmt_amount(row.get("UB_fjor")))
        self._kpi_vars["endring_kr"].set(_fmt_amount(row.get("Endring")))
        self._kpi_vars["endring_pct"].set(_fmt_pct(row.get("Endring_pct")))
        antall = row.get("Antall")
        self._kpi_vars["antall"].set(str(_safe_int(antall)) if antall is not None else blank)

    # ------------------------------------------------------------------
    # Populate

    def _populate_extra_stats(self, stats: dict) -> None:
        blank = "\u2013"
        top10 = stats.get("top10_pct")
        self._ext_vars["top10"].set(f"{top10:.0f} %" if top10 is not None else blank)
        n_b = stats.get("n_bilag")
        self._ext_vars["n_bilag"].set(f"{n_b:,}" if n_b is not None else blank)
        n_k = stats.get("n_kunder")
        self._ext_vars["n_kunder"].set(f"{n_k:,}" if n_k is not None else blank)
        maks = stats.get("mnd_max_name")
        maks_v = stats.get("mnd_max_val")
        self._ext_vars["mnd_max"].set(f"{maks}  {_fmt_amount(maks_v)}" if maks else blank)
        n_an = stats.get("n_anomali_mnd")
        self._ext_vars["anomali"].set(
            f"{n_an} mnd" + (" \u26a0" if n_an and n_an > 0 else "  \u2713")
            if n_an is not None else blank
        )
        runde = stats.get("runde_pct")
        self._ext_vars["runde"].set(f"{runde:.0f} %" if runde is not None else blank)

    def _populate_kontoer(self, grp: pd.DataFrame, ib_label: str = "IB") -> None:
        tree = self._tree_kontoer
        # Oppdater kolonneoverskrift dynamisk
        try:
            tree.heading("IB", text=ib_label)
        except Exception:
            pass
        tree.delete(*tree.get_children())
        if grp.empty:
            return

        sum_ib = sum_bev = sum_ub = sum_ant = 0.0
        has_sb = False

        for _, row in grp.iterrows():
            ib_v = row.get("IB")
            ub_v = row.get("UB")
            ib_ok = ib_v is not None and str(ib_v) not in ("", "nan")
            ub_ok = ub_v is not None and str(ub_v) not in ("", "nan")
            bev = _safe_float(row["Bevegelse"])
            ant = _safe_int(row["Antall"])
            if ib_ok:
                sum_ib += _safe_float(ib_v)
                has_sb = True
            if ub_ok:
                sum_ub += _safe_float(ub_v)
            sum_bev += bev
            sum_ant += ant
            tree.insert("", tk.END, values=(
                str(row["Konto"]),
                str(row.get("Kontonavn", "") or ""),
                _fmt_amount(ib_v) if ib_ok else "",
                _fmt_amount(bev),
                _fmt_amount(ub_v) if ub_ok else "",
                ant,
            ))

        # Totalsrad
        tree.insert("", tk.END, values=(
            "", "Sum",
            _fmt_amount(sum_ib) if has_sb else "",
            _fmt_amount(sum_bev),
            _fmt_amount(sum_ub) if has_sb else "",
            _safe_int(sum_ant),
        ), tags=("sum",))
        tree.tag_configure("sum", font=("", 10, "bold"))

    def _rebuild_maned_pivot(self, df_rl: pd.DataFrame) -> None:
        frame = self._maned_frame
        if frame is None:
            return
        for child in frame.winfo_children():
            try:
                child.destroy()
            except Exception:
                pass

        months, pivot = _compute_maned_pivot(df_rl)
        if pivot.empty:
            ttk.Label(frame, text="Ingen data").grid(row=0, column=0, padx=8, pady=8)
            return

        mnds = [m.replace("-", "\u2011") for m in months]
        all_cols = ("Konto", "Kontonavn") + tuple(mnds) + ("Sum",)

        inner = ttk.Frame(frame)
        inner.grid(row=0, column=0, sticky="nsew")
        inner.columnconfigure(0, weight=1)
        inner.rowconfigure(0, weight=1)

        tree = ttk.Treeview(inner, columns=all_cols, show="headings")  # type: ignore[misc]
        tree.column("Konto", width=70, anchor="w", stretch=False)
        tree.heading("Konto", text="Konto")
        tree.column("Kontonavn", width=220, anchor="w", stretch=True)
        tree.heading("Kontonavn", text="Kontonavn")
        for col, m in zip(mnds, months):
            try:
                from calendar import month_abbr
                yr, mn = m.split("-")
                short = f"{month_abbr[int(mn)]} {yr[2:]}"
            except Exception:
                short = col
            tree.column(col, width=90, anchor="e", stretch=False)
            tree.heading(col, text=short)
        tree.column("Sum", width=110, anchor="e", stretch=False)
        tree.heading("Sum", text="Sum")

        vsb = ttk.Scrollbar(inner, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(inner, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        _attach_sort(tree)

        # Negative verdier i rødt
        tree.tag_configure("neg", foreground="#C62828")

        totals: dict[str, float] = {c: 0.0 for c in mnds}
        grand_total = 0.0
        for _, row in pivot.iterrows():
            vals: list = [str(row["Konto"]), str(row.get("Kontonavn", "") or "")]
            row_neg = False
            for col, m in zip(mnds, months):
                v = _safe_float(row.get(m, 0))
                totals[col] = totals.get(col, 0.0) + v
                vals.append(_fmt_amount(v) if v != 0.0 else "")
                if v < 0:
                    row_neg = True
            s = _safe_float(row.get("Sum", 0))
            grand_total += s
            vals.append(_fmt_amount(s))
            tree.insert("", tk.END, values=tuple(vals), tags=("neg",) if row_neg else ())

        # Sum-rad
        sv = ["", "Sum"] + [_fmt_amount(totals[c]) for c in mnds] + [_fmt_amount(grand_total)]
        tree.insert("", tk.END, values=tuple(sv), tags=("sum",))
        tree.tag_configure("sum", font=("", 10, "bold"))

    def _populate_bilag(self, grp: pd.DataFrame) -> None:
        tree = self._tree_bilag
        tree.delete(*tree.get_children())
        for _, row in grp.iterrows():
            bel = _safe_float(row["Sum beløp"])
            tree.insert("", tk.END, values=(
                str(row.get("Bilag", "") or ""),
                str(row.get("Dato", "") or ""),
                str(row.get("Tekst", "") or ""),
                _fmt_amount(bel),
                _safe_int(row["Antall poster"]),
                str(row.get("Kontoer", "") or ""),
            ), tags=("neg",) if bel < 0 else ())
        self._tree_bilag.tag_configure("neg", foreground="#C62828")

    def _populate_mva(self, result: dict) -> None:
        tree = self._tree_mva
        tree.delete(*tree.get_children())

        # Oppdater avstemmingspanel
        bev = result.get("total_bevegelse", 0.0)
        med = result.get("total_med_kode", 0.0)
        uten = result.get("total_uten_kode", 0.0)
        faktisk = result.get("total_mva", 0.0)
        forventet = result.get("total_forventet_mva", 0.0)
        avvik_kr = abs(faktisk) - forventet

        self._mva_avs_vars["bev"].set(_fmt_amount(bev))
        self._mva_avs_vars["med"].set(_fmt_amount(med))
        self._mva_avs_vars["uten"].set(_fmt_amount(uten))
        self._mva_avs_vars["faktisk"].set(_fmt_amount(faktisk))
        self._mva_avs_vars["forventet"].set(_fmt_amount(-forventet if faktisk < 0 else forventet))
        avvik_txt = _fmt_amount(avvik_kr)
        if abs(avvik_kr) < 1 and forventet > 0:
            avvik_txt += "  \u2713 OK"
        elif forventet > 0:
            avvik_txt += "  \u26a0"
        self._mva_avs_vars["avvik"].set(avvik_txt)

        grp = result.get("rows", pd.DataFrame())
        if grp is None or grp.empty:
            return

        for _, row in grp.iterrows():
            kode = str(row.get("MVA-kode", ""))
            status = str(row.get("Status", ""))
            ingen = kode.startswith("\u2013")
            tag = "ingen" if ingen else ("ok" if "\u2713" in status else ("avvik" if "\u26a0" in status else ""))
            tree.insert("", tk.END, values=(
                kode,
                _safe_int(row["Antall"]),
                _fmt_amount(row["Grunnlag"]),
                _fmt_amount(row["MVA-beløp"]) if not ingen else "",
                _fmt_pct(row.get("Sats %")) if not ingen else "",
                _fmt_pct(row.get("Effektiv %")) if not ingen else "",
                status,
            ), tags=(tag,) if tag else ())

    def _populate_motpost(self, grp: pd.DataFrame) -> None:
        mode = str(getattr(self, "_var_motpost_mode", None).get() if getattr(self, "_var_motpost_mode", None) else "konto")
        tree = self._tree_motpost
        tree.delete(*tree.get_children())

        if mode == "rl":
            tree.heading("Konto", text="Nr")
            tree.heading("Kontonavn", text="Regnskapslinje")
            tree.column("Konto", width=60, anchor="e")
            tree.column("Kontonavn", width=280, anchor="w")
            df = self._motpost_rl_last if isinstance(self._motpost_rl_last, pd.DataFrame) else pd.DataFrame()
            self._motpost_hint_var.set("Dobbeltklikk en regnskapslinje for å se tilhørende bilag")
            key_col, name_col = "Regnr", "Regnskapslinje"
        else:
            tree.heading("Konto", text="Konto")
            tree.heading("Kontonavn", text="Kontonavn")
            tree.column("Konto", width=80, anchor="w")
            tree.column("Kontonavn", width=260, anchor="w")
            df = grp if isinstance(grp, pd.DataFrame) else pd.DataFrame()
            self._motpost_hint_var.set("Dobbeltklikk en konto for å se tilhørende bilag")
            key_col, name_col = "Konto", "Kontonavn"

        if df is None or df.empty:
            self._tree_motpost.tag_configure("neg", foreground="#C62828")
            return

        for _, row in df.iterrows():
            bel = _safe_float(row.get("Beløp"))
            tree.insert("", tk.END, values=(
                str(row.get(key_col, "") or ""),
                str(row.get(name_col, "") or ""),
                _fmt_amount(bel),
                f"{float(row.get('Andel') or 0):.1f}",
                _safe_int(row.get("AntallBilag")),
            ), tags=("neg",) if bel < 0 else ())
        self._tree_motpost.tag_configure("neg", foreground="#C62828")

    def _on_motpost_mode_change(self) -> None:
        """Triggeres når brukeren bytter Konto/RL-modus."""
        mode = self._var_motpost_mode.get()
        if mode == "rl" and (self._motpost_rl_last is None or self._motpost_rl_last is False):
            self._motpost_rl_last = self._build_motpost_rl_df(self._motpost_data_last)
        self._populate_motpost(self._motpost_data_last if isinstance(self._motpost_data_last, pd.DataFrame) else pd.DataFrame())

    def _build_motpost_rl_df(self, grp: pd.DataFrame | None) -> pd.DataFrame:
        """Aggregér konto-motpost på regnskapslinje-nivå.

        Kontoer som ikke mapper til noen RL samles i en pseudo-rad
        ``Regnr=<NA>, Regnskapslinje='— umappet —'``.
        """
        empty = pd.DataFrame(columns=["Regnr", "Regnskapslinje", "Beløp", "Andel", "AntallBilag"])
        if not isinstance(grp, pd.DataFrame) or grp.empty:
            return empty

        page = self._analyse_page
        if page is None:
            return empty

        try:
            from regnskapslinje_mapping_service import context_from_page, resolve_accounts_to_rl
            ctx = context_from_page(page)
            kontoer = grp["Konto"].astype(str).tolist()
            mapping = resolve_accounts_to_rl(kontoer, context=ctx)
        except Exception as exc:
            log.warning("_build_motpost_rl_df: mapping feilet: %s", exc)
            return empty

        df = grp.copy()
        df["Konto"] = df["Konto"].astype(str)
        mapping = mapping.rename(columns={"konto": "Konto"})[["Konto", "regnr", "regnskapslinje"]]
        merged = df.merge(mapping, on="Konto", how="left")

        def _fmt_regnr(v: object) -> str:
            if v is None or (hasattr(v, "__class__") and pd.isna(v)):
                return ""
            try:
                return str(int(v))
            except Exception:
                return ""

        merged["Regnr"] = merged["regnr"].map(_fmt_regnr)
        merged["Regnskapslinje"] = merged["regnskapslinje"].fillna("").astype(str)
        merged.loc[merged["Regnr"] == "", "Regnskapslinje"] = "— umappet —"

        merged["_b"] = pd.to_numeric(merged["Beløp"], errors="coerce").fillna(0.0)
        merged["_n"] = pd.to_numeric(merged["AntallBilag"], errors="coerce").fillna(0).astype(int)

        agg = (
            merged.groupby(["Regnr", "Regnskapslinje"], sort=False, dropna=False)
            .agg(Beløp=("_b", "sum"), AntallBilag=("_n", "sum"))
            .reset_index()
        )
        agg["_abs"] = agg["Beløp"].abs()
        total = agg["_abs"].sum()
        agg["Andel"] = (agg["_abs"] / total * 100).round(1) if total > 0 else 0.0
        agg = agg.sort_values("_abs", ascending=False).drop(columns=["_abs"])
        return agg[["Regnr", "Regnskapslinje", "Beløp", "Andel", "AntallBilag"]].reset_index(drop=True)

    # ------------------------------------------------------------------
    # Drill-down: dobbeltklikk i Bilag-analyse

    # ------------------------------------------------------------------
    # Drill-down helpers

    def _open_tx_popup(self, title: str, df: pd.DataFrame) -> None:
        """Generisk transaksjonspopup — viser df som en sortérbar tabell."""
        if df is None or df.empty:
            messagebox.showinfo("Ingen data", "Ingen transaksjoner funnet.", parent=self)
            return
        top = tk.Toplevel(self)
        top.title(title)
        top.geometry("980x440")
        top.transient(self)

        frame = ttk.Frame(top, padding=8)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        pref_cols = ("Dato", "Bilag", "Konto", "Kontonavn", "Tekst", "Beløp", "MVA-kode", "MVA-beløp")
        avail = [c for c in pref_cols if c in df.columns]
        widths = {"Dato": 90, "Bilag": 80, "Konto": 70, "Kontonavn": 180,
                  "Tekst": 270, "Beløp": 120, "MVA-kode": 70, "MVA-beløp": 110}
        text_cols_p = ("Dato", "Bilag", "Konto", "Kontonavn", "Tekst", "MVA-kode")

        tree = ttk.Treeview(frame, columns=avail, show="headings")
        for col in avail:
            tree.heading(col, text=col)
            tree.column(col, width=widths.get(col, 100),
                        anchor="w" if col in text_cols_p else "e")
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        _attach_sort(tree)
        tree.tag_configure("neg", foreground="#C62828")

        sum_bel = 0.0
        for _, row in df.iterrows():
            dato_str = ""
            if "Dato" in row.index:
                try:
                    d = pd.to_datetime(row["Dato"], dayfirst=True, errors="coerce")
                    dato_str = d.strftime("%d.%m.%Y") if not pd.isna(d) else str(row["Dato"])
                except Exception:
                    dato_str = str(row.get("Dato", ""))
            bel = _safe_float(row.get("Beløp"))
            sum_bel += bel
            vals: list = []
            for col in avail:
                if col == "Dato":
                    vals.append(dato_str)
                elif col in ("Beløp", "MVA-beløp"):
                    vals.append(_fmt_amount(row.get(col)))
                else:
                    vals.append(str(row.get(col, "") or ""))
            tree.insert("", tk.END, values=tuple(vals), tags=("neg",) if bel < 0 else ())

        bot = ttk.Frame(frame)
        bot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        bot.columnconfigure(0, weight=1)
        ttk.Label(
            bot, text=f"{len(df):,} poster  |  Sum beløp: {_fmt_amount(sum_bel)}",
            font=("", 10, "bold"),
        ).grid(row=0, column=0, sticky="w")
        ttk.Button(bot, text="Lukk", command=top.destroy).grid(row=0, column=1, sticky="e")

    def _on_kontoer_doubleclick(self, event: object = None) -> None:
        tree = self._tree_kontoer
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals or not str(vals[0]).strip():
            return
        konto = str(vals[0]).strip()
        df_rl = self._df_rl_last
        if df_rl is None or df_rl.empty or "Konto" not in df_rl.columns:
            return
        df_detail = df_rl[df_rl["Konto"].astype(str) == konto]
        kontonavn = str(vals[1]) if len(vals) > 1 else konto
        self._open_tx_popup(f"Transaksjoner — konto {konto} {kontonavn}", df_detail)

    def _on_mva_doubleclick(self, event: object = None) -> None:
        tree = self._tree_mva
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals:
            return
        kode = str(vals[0]).strip()
        df_rl = self._df_rl_last
        if df_rl is None or df_rl.empty or "MVA-kode" not in df_rl.columns:
            return
        if kode.startswith("\u2013"):
            # "Ingen kode" — vis rader uten MVA-kode
            mask = df_rl["MVA-kode"].isna() | (df_rl["MVA-kode"].astype(str).str.strip() == "")
            df_detail = df_rl[mask]
            title = "Transaksjoner uten MVA-kode"
        else:
            df_detail = df_rl[df_rl["MVA-kode"].astype(str).str.strip() == kode]
            title = f"Transaksjoner — MVA-kode {kode}"
        self._open_tx_popup(title, df_detail)

    def _on_motpost_doubleclick(self, event: object = None) -> None:
        tree = self._tree_motpost
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals or not str(vals[0]).strip():
            return
        df_rl = self._df_rl_last
        df_all = self._df_all_last
        if df_rl is None or df_all is None or "Bilag" not in df_rl.columns:
            return
        rl_bilag = set(df_rl["Bilag"].dropna().astype(str).unique())

        mode = str(getattr(self, "_var_motpost_mode", None).get() if getattr(self, "_var_motpost_mode", None) else "konto")
        if mode == "rl":
            regnr_str = str(vals[0]).strip()
            rl_navn = str(vals[1]) if len(vals) > 1 else regnr_str
            kontoer_for_regnr = self._kontoer_for_regnr(regnr_str)
            if not kontoer_for_regnr:
                return
            mask = (
                df_all["Bilag"].astype(str).isin(rl_bilag)
                & df_all["Konto"].astype(str).isin(kontoer_for_regnr)
            )
            df_detail = df_all[mask]
            title = f"Motpostbilag — {regnr_str} {rl_navn}" if regnr_str else f"Motpostbilag — {rl_navn}"
            self._open_tx_popup(title, df_detail)
        else:
            konto = str(vals[0]).strip()
            kontonavn = str(vals[1]) if len(vals) > 1 else konto
            mask = df_all["Bilag"].astype(str).isin(rl_bilag) & (df_all["Konto"].astype(str) == konto)
            df_detail = df_all[mask]
            self._open_tx_popup(f"Motpostbilag — konto {konto} {kontonavn}", df_detail)

    def _kontoer_for_regnr(self, regnr_str: str) -> set[str]:
        """Returner kontoer i _motpost_data_last som mapper til angitt regnr.

        Tomt regnr_str = kontoer uten mapping ("— umappet —").
        """
        grp = self._motpost_data_last
        if not isinstance(grp, pd.DataFrame) or grp.empty:
            return set()
        page = self._analyse_page
        if page is None:
            return set()
        try:
            from regnskapslinje_mapping_service import context_from_page, resolve_accounts_to_rl
            ctx = context_from_page(page)
            mapping = resolve_accounts_to_rl(grp["Konto"].astype(str).tolist(), context=ctx)
        except Exception:
            return set()
        if regnr_str == "":
            sub = mapping[mapping["regnr"].isna()]
        else:
            try:
                target = int(regnr_str)
            except Exception:
                return set()
            sub = mapping[mapping["regnr"] == target]
        return set(sub["konto"].astype(str).tolist())

    # ------------------------------------------------------------------
    # Kombinasjoner

    def _compute_kombinasjoner(
        self, df_all: pd.DataFrame, rl_kontoer: set[str]
    ) -> tuple[pd.DataFrame, dict[str, str]]:
        """Bygg kombinasjoner + bilag→kombinasjon-mapping for drill-down."""
        empty_cols = [
            "Kombinasjon #", "Kombinasjon", "Kombinasjon (navn)",
            "Antall bilag", "Sum valgte kontoer", "% andel bilag", "Outlier",
        ]
        if df_all is None or df_all.empty or not rl_kontoer:
            return pd.DataFrame(columns=empty_cols), {}
        try:
            from motpost.konto_core import build_motpost_data
            from motpost.combinations import (
                build_bilag_to_motkonto_combo,
                build_motkonto_combinations,
            )
            mp = build_motpost_data(df_all, set(rl_kontoer), selected_direction="Alle")
            combos = build_motkonto_combinations(mp.df_scope, set(rl_kontoer))
            bilag_map = build_bilag_to_motkonto_combo(mp.df_scope, list(rl_kontoer))
        except Exception as exc:
            log.warning("_compute_kombinasjoner: %s", exc)
            return pd.DataFrame(columns=empty_cols), {}
        return combos, bilag_map

    def _kombo_rl_label(self, combo: str) -> str:
        """Oversett kombinasjon-streng fra konto-numre til RL-navn."""
        from motpost.combo_workflow import combo_display_name_for_mode

        page = self._analyse_page
        konto_rl_map: dict[str, str] = {}
        konto_navn_map: dict[str, str] = {}
        if page is not None:
            try:
                from regnskapslinje_mapping_service import context_from_page, resolve_accounts_to_rl
                ctx = context_from_page(page)
                kontoer = [
                    p.strip()
                    for p in str(combo or "").split(",")
                    if p.strip()
                ]
                if kontoer:
                    mapping = resolve_accounts_to_rl(kontoer, context=ctx)
                    for _, r in mapping.iterrows():
                        k = str(r.get("konto") or "").strip()
                        nm = str(r.get("regnskapslinje") or "").strip()
                        if k:
                            konto_rl_map[k] = nm or k
            except Exception:
                konto_rl_map = {}
        return combo_display_name_for_mode(
            combo,
            display_mode="regnskap",
            konto_navn_map=konto_navn_map,
            konto_regnskapslinje_map=konto_rl_map,
        )

    def _populate_kombo(self) -> None:
        tree = self._tree_kombo
        tree.delete(*tree.get_children())
        df = self._kombo_data_last
        if df is None or df.empty:
            return

        mode = self._var_kombo_mode.get() if getattr(self, "_var_kombo_mode", None) else "konto"
        use_rl = (mode == "rl")

        for _, row in df.iterrows():
            combo_raw = str(row.get("Kombinasjon", "") or "")
            if use_rl:
                label = self._kombo_rl_label(combo_raw)
            else:
                label = str(row.get("Kombinasjon (navn)") or combo_raw)
            bel = _safe_float(row.get("Sum valgte kontoer"))
            tree.insert("", tk.END, values=(
                _safe_int(row.get("Kombinasjon #")),
                label,
                _safe_int(row.get("Antall bilag")),
                _fmt_amount(bel),
                f"{float(row.get('% andel bilag') or 0):.1f}",
            ), tags=("neg",) if bel < 0 else ())
        tree.tag_configure("neg", foreground="#C62828")

    def _on_kombo_mode_change(self) -> None:
        self._populate_kombo()

    def _on_kombo_doubleclick(self, event: object = None) -> None:
        tree = self._tree_kombo
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals:
            return
        try:
            nr = int(vals[0])
        except Exception:
            return

        df = self._kombo_data_last
        bilag_map = self._kombo_bilag_map_last
        df_all = self._df_all_last
        if df is None or df.empty or not bilag_map or df_all is None or df_all.empty:
            return
        row = df[df["Kombinasjon #"].astype(int) == nr]
        if row.empty:
            return
        combo_raw = str(row.iloc[0].get("Kombinasjon", "") or "")
        bilag_set = {b for b, c in bilag_map.items() if c == combo_raw}
        if not bilag_set:
            return
        mask = df_all["Bilag"].astype(str).isin(bilag_set)
        df_detail = df_all[mask]
        label = str(vals[1]) if len(vals) > 1 else combo_raw
        self._open_tx_popup(f"Bilag — kombinasjon {nr}: {label}", df_detail)

    def _show_motpost_flowchart(self) -> None:
        """Genererer D3 Sankey-diagram som HTML og åpner i nettleser."""
        import json
        import tempfile
        import webbrowser

        grp = self._motpost_data_last
        df_rl = self._df_rl_last
        if grp is None or grp.empty:
            messagebox.showinfo("Ingen data", "Vis statistikk for en regnskapslinje først.", parent=self)
            return

        grp_top = grp.head(15).reset_index(drop=True)

        # --- Bygg nodedata og lenker ---
        src_name = f"{self._current_regnr} {self._current_rl_name}"
        if df_rl is not None and not df_rl.empty and "Konto" in df_rl.columns:
            kontoer = sorted(df_rl["Konto"].dropna().astype(str).unique())
            kontoer_str = ", ".join(kontoer[:5]) + ("…" if len(kontoer) > 5 else "")
            src_name += f"  ({kontoer_str})"

        nodes = [{"name": src_name, "group": "source"}]
        links = []
        for _, row in grp_top.iterrows():
            konto = str(row.get("Konto", ""))
            navn = str(row.get("Kontonavn", ""))
            beløp = abs(float(row.get("Beløp", 0)))
            andel = float(row.get("Andel", 0))
            node_name = f"{konto}  {navn}"
            nodes.append({
                "name": node_name,
                "group": "target",
                "beløp": beløp,
                "andel": andel,
            })
            links.append({
                "source": 0,
                "target": len(nodes) - 1,
                "value": max(beløp, 1.0),
                "andel": andel,
                "beløp_fmt": _fmt_amount(float(row.get("Beløp", 0))),
            })

        nodes_json = json.dumps(nodes, ensure_ascii=False)
        links_json = json.dumps(links, ensure_ascii=False)
        tittel = f"Motpostfordeling — {self._current_regnr} {self._current_rl_name}"

        html = f"""<!DOCTYPE html>
<html lang="no">
<head>
<meta charset="utf-8">
<title>{tittel}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f8f9fa; color: #1a1a2e; }}
  #header {{ padding: 18px 28px 10px; border-bottom: 1px solid #dee2e6; background: #fff; }}
  #header h1 {{ font-size: 16px; font-weight: 600; color: #1565C0; }}
  #header p {{ font-size: 12px; color: #6c757d; margin-top: 4px; }}
  #chart {{ padding: 20px 28px; }}
  svg {{ width: 100%; overflow: visible; }}
  .link {{ fill: none; stroke-opacity: 0.45; transition: stroke-opacity 0.2s; }}
  .link:hover {{ stroke-opacity: 0.75; cursor: pointer; }}
  .node rect {{ rx: 6; ry: 6; stroke-width: 1.5; }}
  .node text {{ font-size: 12px; }}
  .tooltip {{
    position: fixed; background: rgba(0,0,0,0.82); color: #fff;
    padding: 8px 12px; border-radius: 6px; font-size: 12px;
    pointer-events: none; display: none; white-space: nowrap;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
  }}
</style>
</head>
<body>
<div id="header">
  <h1>{tittel}</h1>
  <p>Hover over strømmene for detaljer. Bredden er proporsjonal med beløpet.</p>
</div>
<div id="chart"><svg id="sankey"></svg></div>
<div class="tooltip" id="tip"></div>

<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/d3-sankey@0.12/dist/d3-sankey.min.js"></script>
<script>
const rawNodes = {nodes_json};
const rawLinks = {links_json};

const W = Math.max(window.innerWidth - 56, 600);
const nodeCount = rawNodes.length;
const H = Math.max(nodeCount * 52 + 80, 360);

const svg = d3.select("#sankey")
  .attr("viewBox", `0 0 ${{W}} ${{H}}`)
  .attr("height", H);

const sankey = d3.sankey()
  .nodeId(d => d.index)
  .nodeWidth(200)
  .nodePadding(18)
  .extent([[16, 16], [W - 16, H - 16]]);

const graph = sankey({{
  nodes: rawNodes.map((d, i) => ({{ ...d, index: i }})),
  links: rawLinks.map(d => ({{ ...d }})),
}});

const color = d3.scaleOrdinal()
  .domain(["source"])
  .range(["#1565C0"])
  .unknown("#2196F3");

// Links
const link = svg.append("g").attr("fill", "none")
  .selectAll("path")
  .data(graph.links)
  .join("path")
    .attr("class", "link")
    .attr("d", d3.sankeyLinkHorizontal())
    .attr("stroke", d => color(graph.nodes[d.target.index].group))
    .attr("stroke-width", d => Math.max(1, d.width));

// Nodes
const node = svg.append("g")
  .selectAll("g")
  .data(graph.nodes)
  .join("g")
    .attr("class", "node");

node.append("rect")
  .attr("x", d => d.x0)
  .attr("y", d => d.y0)
  .attr("width", d => d.x1 - d.x0)
  .attr("height", d => Math.max(1, d.y1 - d.y0))
  .attr("fill", d => d.group === "source" ? "#E3F2FD" : "#EEF2FF")
  .attr("stroke", d => d.group === "source" ? "#1565C0" : "#3F51B5");

node.append("text")
  .attr("x", d => d.x0 + (d.x1 - d.x0) / 2)
  .attr("y", d => (d.y0 + d.y1) / 2 - (d.group === "source" ? 6 : 7))
  .attr("text-anchor", "middle")
  .attr("dominant-baseline", "middle")
  .attr("font-weight", "600")
  .attr("fill", d => d.group === "source" ? "#0D47A1" : "#1a1a2e")
  .attr("font-size", d => d.group === "source" ? "12px" : "12px")
  .each(function(d) {{
    const el = d3.select(this);
    const parts = d.name.split("  ");
    if (parts.length > 1 && d.group === "target") {{
      el.append("tspan")
        .attr("x", d.x0 + (d.x1 - d.x0) / 2)
        .attr("dy", "0")
        .attr("font-weight", "700")
        .attr("fill", "#1565C0")
        .text(parts[0]);
      el.append("tspan")
        .attr("x", d.x0 + (d.x1 - d.x0) / 2)
        .attr("dy", "1.3em")
        .attr("font-weight", "400")
        .attr("fill", "#333")
        .text(parts.slice(1).join("  ").trim());
    }} else {{
      el.text(d.name);
    }}
  }});

// Andel-label under kontonavn for target-noder
node.filter(d => d.group === "target")
  .append("text")
  .attr("x", d => d.x0 + (d.x1 - d.x0) / 2)
  .attr("y", d => (d.y0 + d.y1) / 2 + 18)
  .attr("text-anchor", "middle")
  .attr("font-size", "11px")
  .attr("fill", "#555")
  .text(d => {{
    const lnk = graph.links.find(l => l.target.index === d.index);
    if (!lnk) return "";
    return `${{lnk.andel.toFixed(1)}}%  ${{lnk.beløp_fmt}}`;
  }});

// Tooltip
const tip = document.getElementById("tip");
link.on("mousemove", function(event, d) {{
  tip.style.display = "block";
  tip.style.left = (event.clientX + 14) + "px";
  tip.style.top = (event.clientY - 10) + "px";
  tip.innerHTML = `<b>${{d.target.name}}</b><br>Andel: ${{d.andel.toFixed(1)}}%<br>Beløp: ${{d.beløp_fmt}}`;
}}).on("mouseleave", () => tip.style.display = "none");
</script>
</body>
</html>"""

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".html", delete=False, encoding="utf-8",
            prefix="utvalg_motpost_",
        )
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name.replace(os.sep, '/')}")

    def _on_bilag_doubleclick(self, event: object = None) -> None:
        tree = self._tree_bilag
        sel = tree.selection()
        if not sel:
            return
        vals = tree.item(sel[0], "values")
        if not vals:
            return
        bilag_nr = str(vals[0]).strip()
        df_rl = self._df_rl_last
        if df_rl is None or df_rl.empty or "Bilag" not in df_rl.columns:
            return
        df_detail = df_rl[df_rl["Bilag"].astype(str) == bilag_nr]
        if df_detail.empty:
            return
        self._open_tx_popup(f"Bilag {bilag_nr}", df_detail)

    # ------------------------------------------------------------------
    # Eksport

    def _export(self) -> None:
        if self._current_regnr is None:
            messagebox.showwarning("Ingen valgt linje", "Velg en regnskapslinje og trykk Vis.", parent=self)
            return
        page = self._analyse_page
        if page is None:
            return
        df_all = getattr(page, "_df_filtered", None)
        if df_all is None or (hasattr(df_all, "empty") and df_all.empty):
            messagebox.showwarning("Ingen data", "Ingen transaksjonsdata lastet.", parent=self)
            return

        try:
            import session as _s
            client = getattr(_s, "client", None) or ""
            year = getattr(_s, "year", None) or ""
        except Exception:
            client, year = "", ""

        name_safe = self._current_rl_name.replace("/", "-").replace("\\", "-").replace(":", "")[:40]
        default_name = f"Statistikk_{self._current_regnr}_{name_safe}_{datetime.now().strftime('%Y%m%d')}.xlsx"
        init_dir = str(Path.home())
        try:
            import client_store
            if client and year:
                init_dir = str(client_store.exports_dir(client, year=year))
        except Exception:
            pass

        path = asksaveasfilename(
            parent=self, title="Lagre arbeidsdokument", defaultextension=".xlsx",
            filetypes=[("Excel-arbeidsbok", "*.xlsx")],
            initialfile=default_name, initialdir=init_dir,
        )
        if not path:
            return
        try:
            ranges = _get_konto_ranges(page, self._current_regnr)
            df_rl = _filter_df(df_all, ranges)
            try:
                sb_eff = page._get_effective_sb_df()  # type: ignore[union-attr]
            except Exception:
                sb_eff = getattr(page, "_rl_sb_df", None)
            konto_set = _get_konto_set_for_regnr(
                page, self._current_regnr, ranges,
                df_all=df_all,
                sb_df=sb_eff,
                sb_prev_df=getattr(page, "_rl_sb_prev_df", None),
            )
            if konto_set is not None and "Konto" in df_rl.columns:
                df_rl = df_rl[df_rl["Konto"].astype(str).isin(konto_set)].copy()
            _write_workbook(
                path, regnr=self._current_regnr, rl_name=self._current_rl_name,
                df_rl=df_rl, df_all=df_all, page=page, client=client, year=year,
                konto_set=konto_set,
            )
            self._status_var.set(f"Eksportert: {Path(path).name}")
            _open_file(path)
        except Exception as exc:
            messagebox.showerror("Eksport feilet", str(exc), parent=self)
            log.exception("StatistikkPage: eksport feilet")



# ---------------------------------------------------------------------------
# Excel (re-eksport fra page_statistikk_excel)
# ---------------------------------------------------------------------------

from page_statistikk_excel import (  # noqa: E402
    _compute_kombinasjoner_export,
    _compute_motpost_rl,
    write_workbook as _write_workbook,
)
