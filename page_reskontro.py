"""page_reskontro.py — Reskontro fane.

Viser kunde- og leverandørtransaksjoner fra SAF-T / HB-data,
med integrert BRREG-sjekk (Enhetsregisteret + Regnskapsregisteret).

Layout:
  - Toolbar: toggle Kunder / Leverandører, søkefelt, BRREG-knapp, eksport
  - Venstre panel: liste med IB/Bevegelse/UB + MVA-reg, Status, Bransje
  - Høyre panel (øverst): transaksjoner for valgt post
  - Høyre panel (nederst): BRREG-detaljer for valgt post
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import formatting
from reskontro_brreg_helpers import (  # noqa: E402
    _brreg_status_text,
    _brreg_has_risk,
    _fmt_nok,
    _fmt_pct,
    _compute_nokkeltall,
)
from reskontro_open_items import (  # noqa: E402
    _is_invoice_tekst,
    _is_payment_tekst,
    _is_non_invoice_tekst,
    _RE_FAKTURA_NR,
    _extract_faktura_nr,
    _compute_open_items,
    _compute_open_items_with_confidence,
    _compute_aging_buckets,
    _match_open_against_period,
)
import reskontro_brreg_panel  # noqa: E402
import reskontro_popups  # noqa: E402

try:
    from ui_treeview_sort import enable_treeview_sorting as _enable_sort
except Exception:
    _enable_sort = None  # type: ignore


# ---------------------------------------------------------------------------
# Treeview-hjelpere: sortering + copy-paste
# ---------------------------------------------------------------------------

def _make_popup(master: Any, *, title: str, geometry: str = "960x400") -> Any:
    """Lag et standard Toplevel-vindu: transient, Escape-lukking, sentrert."""
    win = tk.Toplevel(master)
    win.title(title)
    win.geometry(geometry)
    win.resizable(True, True)
    try:
        win.transient(master.winfo_toplevel())
    except Exception:
        pass
    win.bind("<Escape>", lambda _e: win.destroy())
    win.bind("<Control-w>", lambda _e: win.destroy())
    return win


def _setup_tree(tree: Any, *, extended: bool = False) -> None:
    """Wire klikk-for-sortering, Ctrl+C (TSV-kopi) og Ctrl+A (velg alle).

    Kalles etter at tree er ferdig konfigurert med kolonner og headings.
    ``extended=True`` endrer selectmode til 'extended' (flervalg).
    """
    if tree is None:
        return
    if extended:
        try:
            tree.configure(selectmode="extended")
        except Exception:
            pass
    if _enable_sort is not None:
        try:
            _enable_sort(tree)
        except Exception:
            pass

    def _copy_selection(event: Any = None) -> None:
        sel = tree.selection()
        if not sel:
            return
        all_cols: list[str] = list(tree["columns"])
        try:
            disp = list(tree["displaycolumns"])
            if disp and disp[0] != "#all":
                all_cols = disp
        except Exception:
            pass
        col_idx = {c: i for i, c in enumerate(tree["columns"])}
        lines: list[str] = ["\t".join(
            str(tree.heading(c).get("text", c)) for c in all_cols)]
        for iid in sel:
            vals = tree.item(iid, "values")
            row = [str(vals[col_idx[c]]) if col_idx.get(c, -1) < len(vals) else ""
                   for c in all_cols]
            lines.append("\t".join(row))
        try:
            tree.clipboard_clear()
            tree.clipboard_append("\n".join(lines))
        except Exception:
            pass

    def _select_all(event: Any = None) -> None:
        try:
            tree.selection_set(tree.get_children(""))
        except Exception:
            pass

    tree.bind("<Control-c>", _copy_selection)
    tree.bind("<Control-C>", _copy_selection)
    tree.bind("<Control-a>", _select_all)
    tree.bind("<Control-A>", _select_all)


# ---------------------------------------------------------------------------
# Kolonner — master
# ---------------------------------------------------------------------------

_COL_NR      = "Nr"
_COL_NAVN    = "Navn"
_COL_ORGNR   = "Org.nr"
_COL_KONTO   = "Konto"
_COL_ANT     = "Trans."
_COL_IB      = "IB"
_COL_BEV     = "Bevegelse"
_COL_UB      = "UB"
_COL_MVA     = "MVA-reg"
_COL_STATUS  = "Status"
_COL_BRANSJE = "Bransje"

_MASTER_COLS = (
    _COL_NR, _COL_NAVN, _COL_ORGNR, _COL_KONTO, _COL_ANT,
    _COL_IB, _COL_BEV, _COL_UB,
    _COL_MVA, _COL_STATUS, _COL_BRANSJE,
)

_DETAIL_COLS = (
    "Dato", "Bilag", "Konto", "Kontonavn",
    "Tekst", "Beløp", "MVA-kode", "MVA-beløp", "Referanse", "Valuta",
)
_TAG_MVA_LINE = "mva_line"  # transaksjonsrad som har MVA-kode
_TAG_MOTPOST  = "motpost"   # motpost-linje (innrykket under hovedtransaksjon)

# Visningsnavn i høyrepanelene (må matche verdier i comboboxene)
_UPPER_VIEW_ALLE   = "Alle transaksjoner"
_UPPER_VIEW_APNE   = "\u00c5pne poster"
_LOWER_VIEW_BRREG  = "BRREG-info"
_LOWER_VIEW_NESTE  = "Transaksjoner neste periode"
_LOWER_VIEW_BETALT = "Betalinger"

_OPEN_ITEMS_COLS = (
    "Status", "Dato", "Bilag", "FakturaNr", "Tekst",
    "Fakturabeløp", "Betalt (i år)", "Gjenstår",
)
_SUBSEQ_COLS = (
    "Dato", "Bilag", "Konto", "Kontonavn", "Tekst",
    "Beløp", "MVA-kode", "MVA-beløp", "Referanse",
)
_PAYMENTS_COLS = (
    "Status", "FakturaBilag", "FakturaNr",
    "Betaling dato", "Betaling bilag", "Betaling tekst",
    "Betalt beløp", "Resterende",
)

# ---------------------------------------------------------------------------
# Tags
# ---------------------------------------------------------------------------

_TAG_NEG          = "neg"
_TAG_HEADER       = "header"
_TAG_ZERO         = "zero"
_TAG_BRREG_WARN   = "brreg_warn"     # konkurs / avvikling / slettet
_TAG_MVA_WARN     = "mva_warn"       # ikke MVA-registrert, men med saldo
_TAG_MVA_FRADRAG  = "mva_fradrag"    # leverandør har MVA-fradrag men er ikke MVA-reg.


# ---------------------------------------------------------------------------
# Hjelpefunksjoner
# ---------------------------------------------------------------------------

def _has_reskontro_data(df: Any) -> bool:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    cols = set(df.columns)
    return "Kundenr" in cols or "Leverandørnr" in cols


def _build_master(
    df: pd.DataFrame, *, mode: str, year: int | None = None
) -> pd.DataFrame:
    """Bygg sammendragstabell per kunde/leverandør.

    IB / UB hentes primært fra SAF-T master-data (KundeIB/KundeUB eller
    LeverandørIB/LeverandørUB) — disse er autoritative og leses direkte fra
    <BalanceAccount> i SAF-T XML.  Bevegelse = sum av transaksjoner i year.

    Fallback (f.eks. HB-import uten SAF-T balanse-data):
      IB = sum transaksjoner med år < year
      Bevegelse = sum transaksjoner med år == year
      UB = IB + Bevegelse
    """
    nr_col    = "Kundenr"      if mode == "kunder" else "Leverandørnr"
    navn_col  = "Kundenavn"    if mode == "kunder" else "Leverandørnavn"
    orgnr_col = "Kundeorgnr"   if mode == "kunder" else "Leverandørorgnr"
    ib_col    = "KundeIB"      if mode == "kunder" else "LeverandørIB"
    ub_col    = "KundeUB"      if mode == "kunder" else "LeverandørUB"
    konto_col = "KundeKonto"   if mode == "kunder" else "LeverandørKonto"
    mva_col   = "KundeMvaReg"  if mode == "kunder" else "LeverandørMvaReg"

    empty = pd.DataFrame(
        columns=["nr", "navn", "orgnr", "antall", "ib", "bev", "ub",
                 "konto", "saft_mva_reg", "has_mva_tx"])
    if nr_col not in df.columns:
        return empty

    sub = df[
        df[nr_col].notna() & (df[nr_col].astype(str).str.strip() != "")
    ].copy()
    if sub.empty:
        return empty

    sub["__nr__"]    = sub[nr_col].astype(str).str.strip()
    sub["__navn__"]  = (sub[navn_col].astype(str).str.strip()
                        if navn_col in sub.columns else "")
    sub["__orgnr__"] = (sub[orgnr_col].astype(str).str.strip()
                        if orgnr_col in sub.columns else "")
    sub["__belop__"] = (pd.to_numeric(sub["Beløp"], errors="coerce").fillna(0.0)
                        if "Beløp" in sub.columns
                        else pd.Series(0.0, index=sub.index))
    sub["__konto__"] = (sub[konto_col].astype(str).str.strip()
                        if konto_col in sub.columns else "")
    sub["__mvareg__"] = (sub[mva_col].fillna(False).astype(bool)
                         if mva_col in sub.columns
                         else pd.Series(False, index=sub.index))

    grp = sub.groupby("__nr__")

    # Pre-compute: om noen transaksjoner har MVA-beløp (inngående fradrag)
    if "MVA-beløp" in sub.columns:
        sub["__mva_belop__"] = pd.to_numeric(sub["MVA-beløp"], errors="coerce").fillna(0.0)
        _mva_tx_flag = (
            sub.groupby("__nr__")["__mva_belop__"]
            .apply(lambda x: (x.abs() > 0.01).any())
            .rename("has_mva_tx")
        )
    else:
        _mva_tx_flag = None

    # SAF-T autoritative balanser — tilgjengelig hvis kolonnen finnes og
    # minst én rad har en ikke-NaN-verdi (0 er gyldig IB-verdi).
    has_saft_bal = (ib_col in sub.columns and sub[ib_col].notna().any())
    if has_saft_bal:
        sub["__ib__"] = pd.to_numeric(sub[ib_col], errors="coerce")
        sub["__ub__"] = pd.to_numeric(sub[ub_col], errors="coerce")
        grp_ib = grp["__ib__"].first().rename("ib")
        grp_ub = grp["__ub__"].first().rename("ub")

        base = pd.DataFrame({
            "nr":     grp["__nr__"].first(),
            "navn":   grp["__navn__"].first(),
            "orgnr":  grp["__orgnr__"].first(),
            "antall": grp["__nr__"].count(),
            "konto":  grp["__konto__"].first(),
            "saft_mva_reg": grp["__mvareg__"].first(),
        }).reset_index(drop=True)
        base = base.join(grp_ib, on="nr").join(grp_ub, on="nr")
        base["ib"]  = base["ib"].fillna(0.0)
        base["ub"]  = base["ub"].fillna(0.0)
        # Bevegelse = UB − IB (netto endring i perioden, samme som Audit Helper)
        base["bev"] = base["ub"] - base["ib"]
    else:
        # Fallback: beregn IB/UB fra transaksjoner
        if year is not None and "Dato" in sub.columns:
            dato = pd.to_datetime(sub["Dato"], errors="coerce")
            sub["__year__"] = dato.dt.year
            ib_mask  = sub["__year__"] < year
            bev_mask = sub["__year__"] == year
            grp_ib  = sub[ib_mask].groupby("__nr__")["__belop__"].sum().rename("ib")
            grp_bev = sub[bev_mask].groupby("__nr__")["__belop__"].sum().rename("bev")
            base = pd.DataFrame({
                "nr":     grp["__nr__"].first(),
                "navn":   grp["__navn__"].first(),
                "orgnr":  grp["__orgnr__"].first(),
                "antall": grp["__nr__"].count(),
                "konto":  grp["__konto__"].first(),
                "saft_mva_reg": grp["__mvareg__"].first(),
            }).reset_index(drop=True)
            base = base.join(grp_ib, on="nr").join(grp_bev, on="nr")
            base["ib"]  = base["ib"].fillna(0.0)
            base["bev"] = base["bev"].fillna(0.0)
            base["ub"]  = base["ib"] + base["bev"]
        else:
            tot = grp["__belop__"].sum()
            base = pd.DataFrame({
                "nr":     grp["__nr__"].first(),
                "navn":   grp["__navn__"].first(),
                "orgnr":  grp["__orgnr__"].first(),
                "antall": grp["__nr__"].count(),
                "konto":  grp["__konto__"].first(),
                "saft_mva_reg": grp["__mvareg__"].first(),
                "ib":     0.0,
                "bev":    tot,
                "ub":     tot,
            }).reset_index(drop=True)

    base["orgnr"]       = base["orgnr"].fillna("").replace("nan", "")
    base["konto"]       = base["konto"].fillna("").replace("nan", "")
    base["saft_mva_reg"] = base["saft_mva_reg"].fillna(False)
    if _mva_tx_flag is not None:
        base = base.join(_mva_tx_flag, on="nr")
        base["has_mva_tx"] = base["has_mva_tx"].fillna(False)
    else:
        base["has_mva_tx"] = False
    base = base.sort_values(
        "nr", key=lambda s: pd.to_numeric(s, errors="coerce").fillna(999_999))
    return base


def _build_detail(df: pd.DataFrame, *, nr: str, mode: str) -> pd.DataFrame:
    """Hent transaksjoner for én kunde/leverandør, sortert på dato."""
    nr_col = "Kundenr" if mode == "kunder" else "Leverandørnr"
    if nr_col not in df.columns:
        return pd.DataFrame()
    mask = df[nr_col].astype(str).str.strip() == nr
    sub = df[mask].copy()
    if not sub.empty and "Dato" in sub.columns:
        sub = sub.sort_values("Dato")
    return sub


# ---------------------------------------------------------------------------
# Hoved-side
# ---------------------------------------------------------------------------

class ReskontroPage(ttk.Frame):  # type: ignore[misc]

    def __init__(self, master: Any = None) -> None:
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            return

        self._df: pd.DataFrame | None = None
        self._master_df: pd.DataFrame | None = None
        self._mode: str = "kunder"
        self._selected_nr: str = ""
        self._filter_var: Any = None

        # BRREG: {orgnr: {"enhet": dict|None, "regnskap": dict|None}}
        self._brreg_data: dict[str, dict] = {}
        # intern_nr → orgnr
        self._orgnr_map: dict[str, str] = {}
        # Etterfølgende periode SAF-T (lastet inn av bruker for matching)
        self._subsequent_df: pd.DataFrame | None = None
        self._subsequent_label: str = ""

        if tk is None:
            return

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_ui()

    # ------------------------------------------------------------------
    # API
    # ------------------------------------------------------------------

    def refresh_from_session(self, session: Any = None) -> None:
        import session as _session
        df = getattr(_session, "dataset", None)
        self._df = df if _has_reskontro_data(df) else None
        self._refresh_all()
        # Auto-start BRREG-sjekk i bakgrunn etter kort forsinkelse
        if self._df is not None and self._orgnr_map:
            self.after(500, self._auto_brreg_all)

    # ------------------------------------------------------------------
    # UI-bygging
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        tb = ttk.Frame(self, padding=(6, 4))
        tb.grid(row=0, column=0, sticky="ew")

        ttk.Label(tb, text="Reskontro",
                  font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))

        self._mode_var = tk.StringVar(value="kunder")
        ttk.Radiobutton(tb, text="Kunder", variable=self._mode_var,
                        value="kunder",
                        command=self._on_mode_change).pack(side="left")
        ttk.Radiobutton(tb, text="Leverandører", variable=self._mode_var,
                        value="leverandorer",
                        command=self._on_mode_change).pack(side="left",
                                                           padx=(6, 12))

        ttk.Label(tb, text="Søk:").pack(side="left")
        self._filter_var = tk.StringVar()
        search = ttk.Entry(tb, textvariable=self._filter_var, width=22)
        search.pack(side="left", padx=(4, 8))
        self._filter_var.trace_add("write", lambda *_: self._apply_filter())

        ttk.Button(tb, text="Oppdater",
                   command=self.refresh_from_session,
                   width=10).pack(side="left")

        self._brreg_btn = ttk.Button(
            tb, text="BRREG-sjekk\u2026",
            command=self._start_brreg_sjekk, width=14)
        self._brreg_btn.pack(side="left", padx=(6, 0))

        ttk.Button(tb, text="Eksporter til Excel\u2026",
                   command=self._export_excel).pack(side="left", padx=(6, 0))

        ttk.Button(tb, text="Reskontrorapport (PDF)\u2026",
                   command=self._export_pdf_report).pack(side="left", padx=(6, 0))

        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y",
                                                   padx=(8, 8), pady=2)

        self._hide_zero_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(tb, text="Skjul nullposter",
                        variable=self._hide_zero_var,
                        command=self._apply_filter).pack(side="left")

        self._decimals_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tb, text="Desimaler",
                        variable=self._decimals_var,
                        command=self._on_decimals_toggle).pack(side="left",
                                                                padx=(6, 0))

        ttk.Button(
            tb, text="Saldoliste\u2026", command=self._show_saldoliste_popup,
        ).pack(side="left", padx=(6, 0))

        pane = ttk.PanedWindow(self, orient="horizontal")
        pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 0))

        # Statuslinje nederst
        self.rowconfigure(2, weight=0)
        status_bar = ttk.Frame(self, relief="sunken", padding=(4, 1))
        status_bar.grid(row=2, column=0, sticky="ew")
        self._status_lbl = ttk.Label(status_bar, text="", foreground="#555",
                                     font=("TkDefaultFont", 8))
        self._status_lbl.pack(side="left")

        # ---- Venstre: master-liste ----
        left = ttk.Frame(pane)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        pane.add(left, weight=1)

        self._master_tree = self._make_master_tree(left)
        self._master_tree.grid(row=0, column=0, sticky="nsew")
        vsb1 = ttk.Scrollbar(left, orient="vertical",
                              command=self._master_tree.yview)
        vsb1.grid(row=0, column=1, sticky="ns")
        hsb1 = ttk.Scrollbar(left, orient="horizontal",
                              command=self._master_tree.xview)
        hsb1.grid(row=1, column=0, sticky="ew")
        self._master_tree.configure(yscrollcommand=vsb1.set,
                                    xscrollcommand=hsb1.set)
        self._master_tree.bind("<<TreeviewSelect>>", self._on_master_select)

        # Sum-rad: IB / Bevegelse / UB totalt + avstemming
        sum_f = ttk.Frame(left, padding=(2, 2))
        sum_f.grid(row=2, column=0, columnspan=2, sticky="ew")
        sum_f.columnconfigure(1, weight=1)
        ttk.Label(sum_f, text="Sum:", font=("TkDefaultFont", 8, "bold"),
                  foreground="#333").grid(row=0, column=0, sticky="w", padx=(2, 6))
        self._sum_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                                   foreground="#333")
        self._sum_lbl.grid(row=0, column=1, sticky="w")
        self._recon_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                                     foreground="#777")
        self._recon_lbl.grid(row=0, column=2, sticky="e", padx=(12, 2))

        # ---- Høyre: vertikal PanedWindow (resizable) ----
        right = ttk.Frame(pane)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)
        pane.add(right, weight=2)

        right_pane = ttk.PanedWindow(right, orient="vertical")
        right_pane.grid(row=0, column=0, sticky="nsew")

        # === Øvre høyrepanel: valgt visning for valgt kunde/leverandør ===
        upper_container = ttk.Frame(right_pane)
        upper_container.columnconfigure(0, weight=1)
        upper_container.rowconfigure(1, weight=1)

        upper_hdr = ttk.Frame(upper_container)
        upper_hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        upper_hdr.columnconfigure(0, weight=1)
        self._detail_lbl = ttk.Label(
            upper_hdr, text="Velg en post for å se transaksjoner",
            font=("TkDefaultFont", 9, "bold"))
        self._detail_lbl.grid(row=0, column=0, sticky="w")
        ttk.Label(upper_hdr, text="Visning:").grid(
            row=0, column=1, sticky="e", padx=(6, 2))
        self._upper_view_var = tk.StringVar(value=_UPPER_VIEW_ALLE)
        self._upper_view_cb = ttk.Combobox(
            upper_hdr, textvariable=self._upper_view_var,
            values=(_UPPER_VIEW_ALLE, _UPPER_VIEW_APNE),
            state="readonly", width=18)
        self._upper_view_cb.grid(row=0, column=2, sticky="e")
        self._upper_view_cb.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._on_upper_view_change())

        # Innholdsflaten i øvre panel — bytter mellom detail_tree og open_items_tree
        self._upper_content = ttk.Frame(upper_container)
        self._upper_content.grid(row=1, column=0, sticky="nsew", padx=(4, 0))
        self._upper_content.columnconfigure(0, weight=1)
        self._upper_content.rowconfigure(0, weight=1)

        self._detail_tree_frame = ttk.Frame(self._upper_content)
        self._detail_tree_frame.columnconfigure(0, weight=1)
        self._detail_tree_frame.rowconfigure(0, weight=1)
        self._detail_tree = self._make_detail_tree(self._detail_tree_frame)
        self._detail_tree.grid(row=0, column=0, sticky="nsew")
        vsb2 = ttk.Scrollbar(self._detail_tree_frame, orient="vertical",
                              command=self._detail_tree.yview)
        vsb2.grid(row=0, column=1, sticky="ns")
        hsb2 = ttk.Scrollbar(self._detail_tree_frame, orient="horizontal",
                              command=self._detail_tree.xview)
        hsb2.grid(row=1, column=0, sticky="ew")
        self._detail_tree.configure(yscrollcommand=vsb2.set,
                                    xscrollcommand=hsb2.set)

        self._open_items_frame = ttk.Frame(self._upper_content)
        self._open_items_frame.columnconfigure(0, weight=1)
        self._open_items_frame.rowconfigure(0, weight=1)
        self._open_items_tree = self._make_open_items_tree(
            self._open_items_frame)
        self._open_items_tree.grid(row=0, column=0, sticky="nsew")
        vsb_oi = ttk.Scrollbar(self._open_items_frame, orient="vertical",
                                command=self._open_items_tree.yview)
        vsb_oi.grid(row=0, column=1, sticky="ns")
        hsb_oi = ttk.Scrollbar(self._open_items_frame, orient="horizontal",
                                command=self._open_items_tree.xview)
        hsb_oi.grid(row=1, column=0, sticky="ew")
        self._open_items_tree.configure(yscrollcommand=vsb_oi.set,
                                        xscrollcommand=hsb_oi.set)

        # Start med Alle transaksjoner synlig
        self._detail_tree_frame.grid(row=0, column=0, sticky="nsew")

        right_pane.add(upper_container, weight=2)

        # === Nedre høyrepanel: BRREG / neste periode / betalinger ===
        lower_container = ttk.Frame(right_pane)
        lower_container.columnconfigure(0, weight=1)
        lower_container.rowconfigure(1, weight=1)

        lower_hdr = ttk.Frame(lower_container)
        lower_hdr.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        lower_hdr.columnconfigure(2, weight=1)
        ttk.Label(lower_hdr, text="Info:").grid(
            row=0, column=0, sticky="w", padx=(0, 4))
        self._lower_view_var = tk.StringVar(value=_LOWER_VIEW_BRREG)
        self._lower_view_cb = ttk.Combobox(
            lower_hdr, textvariable=self._lower_view_var,
            values=(_LOWER_VIEW_BRREG, _LOWER_VIEW_NESTE, _LOWER_VIEW_BETALT),
            state="readonly", width=28)
        self._lower_view_cb.grid(row=0, column=1, sticky="w")
        self._lower_view_cb.bind(
            "<<ComboboxSelected>>",
            lambda _e: self._on_lower_view_change())
        self._load_subseq_btn = ttk.Button(
            lower_hdr, text="Last inn etterfølgende periode\u2026",
            command=self._open_subsequent_period)
        # pakkes inn/ut dynamisk i _refresh_lower_panel

        self._lower_content = ttk.Frame(lower_container)
        self._lower_content.grid(row=1, column=0, sticky="nsew", padx=(4, 0))
        self._lower_content.columnconfigure(0, weight=1)
        self._lower_content.rowconfigure(0, weight=1)

        # BRREG
        self._brreg_frame = ttk.Frame(self._lower_content)
        self._brreg_frame.columnconfigure(0, weight=1)
        self._brreg_frame.rowconfigure(0, weight=1)
        self._brreg_info_labels: dict[str, tk.StringVar] = {}
        self._build_brreg_panel()

        # Neste periode
        self._subseq_frame = ttk.Frame(self._lower_content)
        self._subseq_frame.columnconfigure(0, weight=1)
        self._subseq_frame.rowconfigure(1, weight=1)
        self._subseq_empty_lbl = ttk.Label(
            self._subseq_frame, text="", foreground="#666",
            font=("TkDefaultFont", 9))
        self._subseq_empty_lbl.grid(row=0, column=0, columnspan=2,
                                     sticky="w", padx=4, pady=(2, 2))
        self._subseq_tree = self._make_subseq_tree(self._subseq_frame)
        self._subseq_tree.grid(row=1, column=0, sticky="nsew")
        vsb_ss = ttk.Scrollbar(self._subseq_frame, orient="vertical",
                                command=self._subseq_tree.yview)
        vsb_ss.grid(row=1, column=1, sticky="ns")
        hsb_ss = ttk.Scrollbar(self._subseq_frame, orient="horizontal",
                                command=self._subseq_tree.xview)
        hsb_ss.grid(row=2, column=0, sticky="ew")
        self._subseq_tree.configure(yscrollcommand=vsb_ss.set,
                                     xscrollcommand=hsb_ss.set)

        # Betalinger
        self._payments_frame = ttk.Frame(self._lower_content)
        self._payments_frame.columnconfigure(0, weight=1)
        self._payments_frame.rowconfigure(1, weight=1)
        self._payments_empty_lbl = ttk.Label(
            self._payments_frame, text="", foreground="#666",
            font=("TkDefaultFont", 9))
        self._payments_empty_lbl.grid(row=0, column=0, columnspan=2,
                                       sticky="w", padx=4, pady=(2, 2))
        self._payments_tree = self._make_payments_tree(self._payments_frame)
        self._payments_tree.grid(row=1, column=0, sticky="nsew")
        vsb_pm = ttk.Scrollbar(self._payments_frame, orient="vertical",
                                command=self._payments_tree.yview)
        vsb_pm.grid(row=1, column=1, sticky="ns")
        hsb_pm = ttk.Scrollbar(self._payments_frame, orient="horizontal",
                                command=self._payments_tree.xview)
        hsb_pm.grid(row=2, column=0, sticky="ew")
        self._payments_tree.configure(yscrollcommand=vsb_pm.set,
                                       xscrollcommand=hsb_pm.set)

        # Start med BRREG synlig
        self._brreg_frame.grid(row=0, column=0, sticky="nsew")

        right_pane.add(lower_container, weight=1)

    def _make_master_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_MASTER_COLS, show="headings",
                             selectmode="browse")
        tree.heading(_COL_NR,      text="Nr",        anchor="w")
        tree.heading(_COL_NAVN,    text="Navn",       anchor="w")
        tree.heading(_COL_ORGNR,   text="Org.nr",     anchor="w")
        tree.heading(_COL_KONTO,   text="Konto",      anchor="w")
        tree.heading(_COL_ANT,     text="Trans.",     anchor="e")
        tree.heading(_COL_IB,      text="IB",         anchor="e")
        tree.heading(_COL_BEV,     text="Bevegelse",  anchor="e")
        tree.heading(_COL_UB,      text="UB",         anchor="e")
        tree.heading(_COL_MVA,     text="MVA-reg",    anchor="center")
        tree.heading(_COL_STATUS,  text="Status",     anchor="w")
        tree.heading(_COL_BRANSJE, text="Bransje",    anchor="w")

        tree.column(_COL_NR,      width=70,  anchor="w",      stretch=False)
        tree.column(_COL_NAVN,    width=180, anchor="w",      stretch=True)
        tree.column(_COL_ORGNR,   width=90,  anchor="w",      stretch=False)
        tree.column(_COL_KONTO,   width=55,  anchor="w",      stretch=False)
        tree.column(_COL_ANT,     width=55,  anchor="e",      stretch=False)
        tree.column(_COL_IB,      width=110, anchor="e",      stretch=False)
        tree.column(_COL_BEV,     width=110, anchor="e",      stretch=False)
        tree.column(_COL_UB,      width=110, anchor="e",      stretch=False)
        tree.column(_COL_MVA,     width=75,  anchor="center", stretch=False)
        tree.column(_COL_STATUS,  width=110, anchor="w",      stretch=False)
        tree.column(_COL_BRANSJE, width=200, anchor="w",      stretch=True)

        tree.tag_configure(_TAG_NEG,        foreground="red")
        tree.tag_configure(_TAG_ZERO,       foreground="#888888")
        tree.tag_configure(_TAG_BRREG_WARN,  foreground="#8B0000",
                           background="#FFF3CD")
        tree.tag_configure(_TAG_MVA_WARN,    background="#FFF8E1")
        tree.tag_configure(_TAG_MVA_FRADRAG, foreground="#8B4500",
                           background="#FDEBD0")
        _setup_tree(tree)
        return tree

    def _make_detail_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_DETAIL_COLS, show="headings",
                             selectmode="extended")
        widths = {
            "Dato": 90, "Bilag": 80, "Konto": 70, "Kontonavn": 170,
            "Tekst": 240, "Beløp": 110, "MVA-kode": 70, "MVA-beløp": 100,
            "Referanse": 80, "Valuta": 55,
        }
        right_cols = {"Beløp", "MVA-beløp"}
        for col in _DETAIL_COLS:
            tree.heading(col, text=col,
                         anchor="e" if col in right_cols else "w")
            tree.column(col, width=widths.get(col, 90),
                        anchor="e" if col in right_cols else "w",
                        stretch=col in ("Tekst", "Kontonavn"))
        tree.tag_configure(_TAG_NEG,      foreground="red")
        tree.tag_configure(_TAG_HEADER,   background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_MVA_LINE, background="#F0FFF0")
        tree.bind("<Double-1>", self._on_detail_double_click)
        tree.bind("<Return>",   self._on_detail_double_click)
        tree.bind("<<TreeviewSelect>>", self._on_detail_select)
        tree.bind("<Button-3>", self._on_detail_right_click)
        _setup_tree(tree, extended=True)
        return tree

    def _make_open_items_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_OPEN_ITEMS_COLS, show="headings",
                             selectmode="extended")
        widths = {
            "Status": 110, "Dato": 90, "Bilag": 80, "FakturaNr": 100,
            "Tekst": 280, "Fakturabeløp": 120, "Betalt (i år)": 120,
            "Gjenstår": 120,
        }
        right_cols = {"Fakturabeløp", "Betalt (i år)", "Gjenstår"}
        for col in _OPEN_ITEMS_COLS:
            tree.heading(col, text=col,
                         anchor="e" if col in right_cols else "w")
            tree.column(col, width=widths.get(col, 90),
                        anchor="e" if col in right_cols else "w",
                        stretch=col == "Tekst")
        tree.tag_configure(_TAG_NEG,     foreground="red")
        tree.tag_configure(_TAG_HEADER,  background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.bind("<Double-1>", self._on_detail_double_click)
        _setup_tree(tree, extended=True)
        return tree

    def _make_subseq_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_SUBSEQ_COLS, show="headings",
                             selectmode="extended")
        widths = {
            "Dato": 90, "Bilag": 80, "Konto": 70, "Kontonavn": 170,
            "Tekst": 240, "Beløp": 110, "MVA-kode": 70, "MVA-beløp": 100,
            "Referanse": 90,
        }
        right_cols = {"Beløp", "MVA-beløp"}
        for col in _SUBSEQ_COLS:
            tree.heading(col, text=col,
                         anchor="e" if col in right_cols else "w")
            tree.column(col, width=widths.get(col, 90),
                        anchor="e" if col in right_cols else "w",
                        stretch=col in ("Tekst", "Kontonavn"))
        tree.tag_configure(_TAG_NEG,     foreground="red")
        tree.tag_configure(_TAG_HEADER,  background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        tree.tag_configure(_TAG_MVA_LINE, background="#F0FFF0")
        _setup_tree(tree, extended=True)
        return tree

    def _make_payments_tree(self, parent: Any) -> Any:
        tree = ttk.Treeview(parent, columns=_PAYMENTS_COLS, show="headings",
                             selectmode="extended")
        widths = {
            "Status": 110, "FakturaBilag": 100, "FakturaNr": 100,
            "Betaling dato": 100, "Betaling bilag": 110,
            "Betaling tekst": 260, "Betalt beløp": 110, "Resterende": 110,
        }
        right_cols = {"Betalt beløp", "Resterende"}
        for col in _PAYMENTS_COLS:
            tree.heading(col, text=col,
                         anchor="e" if col in right_cols else "w")
            tree.column(col, width=widths.get(col, 90),
                        anchor="e" if col in right_cols else "w",
                        stretch=col == "Betaling tekst")
        tree.tag_configure(_TAG_NEG,     foreground="red")
        tree.tag_configure(_TAG_HEADER,  background="#E8EFF7",
                           font=("TkDefaultFont", 9, "bold"))
        _setup_tree(tree, extended=True)
        return tree

    def _detail_decimals(self) -> int:
        """Returnerer antall desimaler for detaljvisning basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _master_decimals(self) -> int:
        """Returnerer antall desimaler for master-listen basert på toggle."""
        try:
            return 2 if self._decimals_var.get() else 0
        except Exception:
            return 2

    def _on_detail_double_click(self, event: Any) -> None:
        """Dobbeltklikk på transaksjon → vis alle linjer for samme bilag.

        Leser fra treet dobbeltklikket skjedde i (``event.widget``), og
        slår opp Bilag-kolonnen dynamisk — kolonneindeksen er ulik i
        flat transaksjonsliste og i åpne-poster-visningen.
        """
        tree = getattr(event, "widget", None) or self._detail_tree
        item = tree.identify_row(event.y)
        if not item:
            return
        try:
            cols = list(tree["columns"])
        except Exception:
            cols = list(_DETAIL_COLS)
        try:
            bilag_idx = cols.index("Bilag")
        except ValueError:
            return
        vals = tree.item(item, "values")
        if not vals or bilag_idx >= len(vals):
            return
        bilag = str(vals[bilag_idx]).strip()
        if not bilag:
            return
        self._open_bilag_popup(bilag)

    def _open_bilag_popup(self, bilag: str) -> None:
        reskontro_popups.open_bilag_popup(self, bilag)

    def _build_brreg_panel(self) -> None:
        reskontro_brreg_panel.build_brreg_panel(self, parent=self._brreg_frame)

    def _brreg_write(self, *parts: tuple[str, str]) -> None:
        reskontro_brreg_panel.brreg_write(self, *parts)

    def _clear_brreg_panel(self) -> None:
        reskontro_brreg_panel.clear_brreg_panel(self)

    def _update_brreg_panel(self, orgnr: str) -> None:
        reskontro_brreg_panel.update_brreg_panel(self, orgnr)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _on_decimals_toggle(self) -> None:
        """Re-render master og detail med ny desimal-innstilling."""
        self._apply_filter()
        if self._selected_nr:
            self._refresh_upper_panel()
            self._refresh_lower_panel()

    def _on_mode_change(self) -> None:
        self._mode = self._mode_var.get()
        self._selected_nr = ""
        self._detail_tree.delete(*self._detail_tree.get_children())
        self._open_items_tree.delete(*self._open_items_tree.get_children())
        self._subseq_tree.delete(*self._subseq_tree.get_children())
        self._payments_tree.delete(*self._payments_tree.get_children())
        self._detail_lbl.configure(text="Velg en post for å se transaksjoner")
        self._clear_brreg_panel()
        self._refresh_all()

    def _refresh_all(self) -> None:
        self._detail_tree.delete(*self._detail_tree.get_children())
        self._open_items_tree.delete(*self._open_items_tree.get_children())
        self._subseq_tree.delete(*self._subseq_tree.get_children())
        self._payments_tree.delete(*self._payments_tree.get_children())
        self._detail_lbl.configure(text="Velg en post for å se transaksjoner")
        self._clear_brreg_panel()
        try:
            self._refresh_lower_panel()
        except Exception:
            pass

        if not _has_reskontro_data(self._df):
            self._master_tree.delete(*self._master_tree.get_children())
            self._status_lbl.configure(
                text="Ingen kunde-/leverandørdata. "
                     "Last inn en SAF-T-fil (zip/xml).")
            return

        import session as _session
        year_str = getattr(_session, "year", None)
        year = int(year_str) if year_str else None
        self._master_df = _build_master(self._df, mode=self._mode, year=year)

        # Bygg orgnr-kart
        if "orgnr" in self._master_df.columns:
            self._orgnr_map = {
                str(r["nr"]): str(r["orgnr"])
                for _, r in self._master_df.iterrows()
                if str(r.get("orgnr", "")).strip()
            }
        else:
            self._orgnr_map = {}

        self._apply_filter()

    def _apply_filter(self) -> None:
        if self._master_df is None:
            return
        q = (self._filter_var.get().strip().lower()
             if self._filter_var else "")
        hide_zero = bool(getattr(self, "_hide_zero_var", None)
                         and self._hide_zero_var.get())
        dec = self._master_decimals()

        tree = self._master_tree
        # Bevar scroll-posisjon og valgt rad ved filter-refresh
        _prev_sel  = tree.selection()
        _prev_yview = tree.yview()[0] if tree.get_children() else 0.0
        tree.delete(*tree.get_children())

        shown = 0
        n_mva_warn_shown  = 0
        n_mva_fradrag     = 0
        sum_ib = sum_bev = sum_ub = 0.0

        for _, row in self._master_df.iterrows():
            nr   = str(row["nr"])
            navn = str(row["navn"])
            ant  = int(row["antall"])
            ib   = float(row["ib"])
            bev  = float(row["bev"])
            ub   = float(row["ub"])

            # orgnr må hentes FØR søke-filteret (brukes i søket)
            orgnr = self._orgnr_map.get(nr, "")

            if q and q not in nr.lower() and q not in navn.lower() \
                    and q not in orgnr.lower():
                continue

            # Skjul poster der alt er 0
            if hide_zero and abs(ib) < 0.01 and abs(bev) < 0.01 and abs(ub) < 0.01:
                continue

            # --- MVA: SAF-T er primærkilde, BRREG er override ---
            saft_mva  = bool(row.get("saft_mva_reg", False))
            has_mva_tx = bool(row.get("has_mva_tx", False))
            brec      = self._brreg_data.get(orgnr, {}) if orgnr else {}
            enhet     = brec.get("enhet") or {} if brec else {}

            if enhet:
                mva_reg     = enhet.get("registrertIMvaregisteret", False)
                mva_txt     = "\u2713 BRREG" if mva_reg else "\u2717 BRREG"
                status_txt  = _brreg_status_text(enhet)
                nk  = enhet.get("naeringskode", "")
                nn  = enhet.get("naeringsnavn", "")
                bransje_txt = (f"{nk} {nn}".strip() if nk else nn)[:40]
            elif saft_mva:
                mva_txt     = "\u2713 SAF-T"
                status_txt  = ""
                bransje_txt = ""
                mva_reg     = True
            else:
                mva_txt     = ""
                status_txt  = ""
                bransje_txt = ""
                mva_reg     = None

            tags: list[str] = []
            if enhet and _brreg_has_risk(enhet):
                tags.append(_TAG_BRREG_WARN)
            elif (mva_reg is False and self._mode == "leverandorer"
                  and has_mva_tx):
                # Leverandør ikke MVA-reg., men det er ført MVA-fradrag
                tags.append(_TAG_MVA_FRADRAG)
                n_mva_fradrag += 1
            elif mva_reg is False and abs(ub) > 0.01:
                tags.append(_TAG_MVA_WARN)
                n_mva_warn_shown += 1

            if not tags:
                if abs(ub) < 0.01:
                    tags.append(_TAG_ZERO)
                elif ub < 0:
                    tags.append(_TAG_NEG)

            orgnr_disp = orgnr if orgnr else ""
            konto_disp = str(row.get("konto", "")) if "konto" in self._master_df.columns else ""
            tree.insert("", "end", iid=nr,
                        values=(
                            nr, navn, orgnr_disp, konto_disp, ant,
                            formatting.fmt_amount(ib,  dec),
                            formatting.fmt_amount(bev, dec),
                            formatting.fmt_amount(ub,  dec),
                            mva_txt, status_txt, bransje_txt,
                        ),
                        tags=tuple(tags))
            shown += 1
            sum_ib  += ib
            sum_bev += bev
            sum_ub  += ub

        # --- Sum-rad ---
        sum_txt = (
            f"IB {formatting.fmt_amount(sum_ib, dec)}"
            f"   Bev. {formatting.fmt_amount(sum_bev, dec)}"
            f"   UB {formatting.fmt_amount(sum_ub, dec)}"
        )
        if hasattr(self, "_sum_lbl"):
            self._sum_lbl.configure(text=sum_txt)

        # --- Avstemming: bevegelse i reskontro vs. konto-bevegelse i full df ---
        if hasattr(self, "_recon_lbl"):
            recon_txt = ""
            try:
                konto = ""
                if self._master_df is not None and "konto" in self._master_df.columns:
                    kontoes = (self._master_df["konto"]
                               .replace("", None).dropna().unique())
                    if len(kontoes) == 1:
                        konto = str(kontoes[0])
                if konto and self._df is not None and "Konto" in self._df.columns:
                    konto_bev = pd.to_numeric(
                        self._df.loc[
                            self._df["Konto"].astype(str).str.strip() == konto,
                            "Beløp"
                        ], errors="coerce"
                    ).sum()
                    avvik = sum_bev - konto_bev
                    recon_txt = (
                        f"Konto {konto}: "
                        f"Bev. RS={formatting.fmt_amount(sum_bev, dec)}, "
                        f"Konto={formatting.fmt_amount(konto_bev, dec)}, "
                        f"Avvik={formatting.fmt_amount(avvik, dec)}"
                        + ("  \u2713" if abs(avvik) < 0.01 else "  \u26a0")
                    )
            except Exception:
                pass
            self._recon_lbl.configure(text=recon_txt)

        # --- Statuslinje ---
        mode_label = "kunder" if self._mode == "kunder" else "leverandører"
        q_suffix   = f"  (filter: '{self._filter_var.get().strip()}')" if q else ""
        n_brreg    = len(self._brreg_data)
        parts      = [f"{shown} {mode_label}"]
        if n_brreg:
            parts.append(f"{n_brreg} BRREG-sjekket")
        if n_mva_fradrag:
            parts.append(f"\u26a0 {n_mva_fradrag} MVA-fradrag uten reg.")
        if n_mva_warn_shown:
            parts.append(f"\u2717 {n_mva_warn_shown} ikke MVA-reg.")
        self._status_lbl.configure(
            text=("  \u2022  ".join(parts)) + q_suffix)

        # Gjenopprett scroll-posisjon og valgt rad etter filter-refresh
        if _prev_yview > 0:
            self.after(0, lambda y=_prev_yview: tree.yview_moveto(y))
        if _prev_sel:
            still_there = [s for s in _prev_sel if tree.exists(s)]
            if still_there:
                tree.selection_set(still_there)
                tree.see(still_there[0])


    def _on_master_select(self, _event: Any = None) -> None:
        sel = self._master_tree.selection()
        if not sel:
            return
        self._selected_nr = sel[0]
        self._refresh_upper_panel()
        orgnr = self._orgnr_map.get(self._selected_nr, "")
        # BRREG: hent automatisk hvis ikke cachet
        if (self._lower_view_var.get() == _LOWER_VIEW_BRREG
                and orgnr and orgnr not in self._brreg_data):
            self._auto_fetch_brreg_single(orgnr)
        else:
            self._refresh_lower_panel()

    def _auto_fetch_brreg_single(self, orgnr: str) -> None:
        """Hent BRREG-data for ett enkelt orgnr i bakgrunn og oppdater panelet."""
        if not orgnr or len(orgnr) != 9 or not orgnr.isdigit():
            self._update_brreg_panel(orgnr)
            return
        self._brreg_write(("Henter BRREG-data\u2026", "dim"))

        def _run() -> None:
            try:
                import brreg_client as _brreg
                enhet = _brreg.fetch_enhet(orgnr)
                regnskap = _brreg.fetch_regnskap(orgnr)
                result = {"enhet": enhet, "regnskap": regnskap}
                self.after(0, lambda: self._on_single_brreg_done(orgnr, result))
            except Exception as exc:
                log.warning("Auto BRREG-henting feilet for %s: %s", orgnr, exc)
                self.after(0, lambda: self._update_brreg_panel(orgnr))

        threading.Thread(target=_run, daemon=True).start()

    def _on_single_brreg_done(self, orgnr: str, result: dict) -> None:
        """Kalles når enkelt BRREG-henting er ferdig."""
        self._brreg_data[orgnr] = result
        if self._lower_view_var.get() == _LOWER_VIEW_BRREG:
            self._update_brreg_panel(orgnr)
        # Oppdater master-treet for å vise MVA/status/bransje
        self._apply_filter()

    def _on_detail_select(self, _event: Any = None) -> None:
        """Oppdater statuslinje med antall markerte rader og sum beløp."""
        sel = self._detail_tree.selection()
        n = len(sel)
        if n <= 1:
            return  # Statuslinja settes av andre metoder ved enkeltvalg
        # Beregn sum av Beløp-kolonnen for markerte rader
        belop_idx = list(_DETAIL_COLS).index("Beløp") if "Beløp" in _DETAIL_COLS else -1
        total = 0.0
        if belop_idx >= 0:
            for iid in sel:
                vals = self._detail_tree.item(iid, "values")
                if vals and belop_idx < len(vals):
                    try:
                        raw = str(vals[belop_idx]).replace("\u00a0", "").replace("\u202f", "").replace(" ", "").replace(",", ".")
                        total += float(raw)
                    except (ValueError, TypeError):
                        pass
        dec = self._detail_decimals()
        self._status_lbl.configure(
            text=f"Markert: {n} rader  |  Beløp: {formatting.fmt_amount(total, dec)}")

    def _on_detail_right_click(self, event: Any) -> None:
        """Høyreklikk-kontekstmeny på detaljrader."""
        tree = self._detail_tree
        iid = tree.identify_row(event.y)
        if iid and iid not in tree.selection():
            tree.selection_set(iid)
            tree.focus(iid)
        sel = tree.selection()
        if not sel:
            return

        vals = tree.item(sel[0], "values")
        bilag = str(vals[1]).strip() if len(vals) > 1 else ""

        menu = tk.Menu(tree, tearoff=0)
        if bilag:
            menu.add_command(
                label=f"Åpne bilag {bilag}  (alle HB-linjer)",
                command=lambda b=bilag: self._open_bilag_popup(b))
            menu.add_separator()
        menu.add_command(
            label=f"Kopier {'rad' if len(sel) == 1 else str(len(sel)) + ' rader'}  (Ctrl+C)",
            command=lambda: tree.event_generate("<Control-c>"))
        menu.add_command(
            label="Velg alle  (Ctrl+A)",
            command=lambda: tree.selection_set(tree.get_children("")))
        menu.add_separator()
        menu.add_command(
            label="Åpne poster for valgt kunde/leverandør",
            command=self._show_open_items_popup)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _populate_detail(self, nr: str) -> None:
        """Flat transaksjonsliste (Ã©n rad per transaksjon) for valgt nr."""
        tree = self._detail_tree
        tree.delete(*tree.get_children())

        if self._df is None:
            return

        sub = _build_detail(self._df, nr=nr, mode=self._mode)
        if sub.empty:
            self._update_detail_header(nr, n_tx=0, total=0.0)
            return

        def _v_any(col: str, row: Any, default: Any = "") -> Any:
            try:
                val = row[col]
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    return default
                return val
            except (KeyError, IndexError):
                return default

        total = 0.0
        debet = 0.0
        kredit = 0.0
        dec = self._detail_decimals()
        for _, row in sub.iterrows():
            dato      = str(_v_any("Dato",      row, ""))[:10]
            bilag     = str(_v_any("Bilag",     row, ""))
            konto     = str(_v_any("Konto",     row, ""))
            knavn     = str(_v_any("Kontonavn", row, ""))
            tekst     = str(_v_any("Tekst",     row, ""))
            ref       = str(_v_any("Referanse", row, ""))
            valuta    = str(_v_any("Valuta",    row, ""))
            mva_kode  = str(_v_any("MVA-kode",  row, ""))
            if mva_kode in ("nan", "None"):
                mva_kode = ""
            try:
                belop = float(_v_any("Beløp", row, 0.0))
            except (ValueError, TypeError):
                belop = 0.0
            try:
                mva_belop_raw = _v_any("MVA-beløp", row, None)
                mva_belop = float(mva_belop_raw) if mva_belop_raw not in (None, "", "nan") else None
            except (ValueError, TypeError):
                mva_belop = None

            total += belop
            if belop >= 0:
                debet += belop
            else:
                kredit += belop

            has_mva = bool(mva_kode or (mva_belop is not None and abs(mva_belop) > 0.001))
            tags: list[str] = []
            if belop < 0:
                tags.append(_TAG_NEG)
            if has_mva:
                tags.append(_TAG_MVA_LINE)

            tree.insert("", "end", values=(
                dato, bilag, konto, knavn, tekst,
                formatting.fmt_amount(belop, dec),
                mva_kode,
                formatting.fmt_amount(mva_belop, dec) if mva_belop is not None else "",
                ref, valuta,
            ), tags=tuple(tags))

        tree.insert("", "end", values=(
            "", "", "", "",
            (f"\u03a3 {len(sub)} trans.  "
             f"D: {formatting.fmt_amount(debet, dec)}  "
             f"K: {formatting.fmt_amount(kredit, dec)}"),
            formatting.fmt_amount(total, dec),
            "", "", "", "",
        ), tags=(_TAG_HEADER,))

        self._update_detail_header(nr, n_tx=len(sub), total=total)
        self._status_lbl.configure(
            text=(f"Markert: 1 rad  |  Beløp: {formatting.fmt_amount(total, dec)}"
                  f"  \u2022  D: {formatting.fmt_amount(debet, dec)}"
                  f"  K: {formatting.fmt_amount(kredit, dec)}"))

    def _update_detail_header(self, nr: str, *, n_tx: int, total: float) -> None:
        navn = self._navn_for_nr(nr)
        mode_str = "Kunde" if self._mode == "kunder" else "Leverandør"
        lbl = f"{mode_str} {nr}"
        if navn:
            lbl += f"  \u2014  {navn}"
        ub_display = total
        if self._master_df is not None:
            row_m = self._master_df[self._master_df["nr"].astype(str) == nr]
            if not row_m.empty:
                ub_display = float(row_m["ub"].iloc[0])
        lbl += f"  ({n_tx} transaksjoner, UB {formatting.fmt_amount(ub_display)})"
        self._detail_lbl.configure(text=lbl)

    # ------------------------------------------------------------------
    # Visningsbytte: øvre og nedre høyrepanel
    # ------------------------------------------------------------------

    def _on_upper_view_change(self) -> None:
        view = self._upper_view_var.get()
        if view == _UPPER_VIEW_APNE:
            self._detail_tree_frame.grid_remove()
            self._open_items_frame.grid(row=0, column=0, sticky="nsew")
        else:
            self._open_items_frame.grid_remove()
            self._detail_tree_frame.grid(row=0, column=0, sticky="nsew")
        self._refresh_upper_panel()

    def _on_lower_view_change(self) -> None:
        self._refresh_lower_panel()

    def _refresh_upper_panel(self) -> None:
        """Render innhold i øvre høyrepanel basert på valgt visning."""
        view = self._upper_view_var.get()
        nr = self._selected_nr
        if view == _UPPER_VIEW_APNE:
            self._populate_open_items_inline(nr)
        else:
            if nr:
                self._populate_detail(nr)
            else:
                self._detail_tree.delete(*self._detail_tree.get_children())
                self._detail_lbl.configure(
                    text="Velg en post for å se transaksjoner")

    def _refresh_lower_panel(self) -> None:
        """Render innhold i nedre høyrepanel basert på valgt visning."""
        view = self._lower_view_var.get()

        # Skjul alle, vis valgt
        for fr in (self._brreg_frame, self._subseq_frame, self._payments_frame):
            try:
                fr.grid_remove()
            except Exception:
                pass

        # Kontekstuell "Last inn etterfølgende periode…"-knapp
        need_subseq = view in (_LOWER_VIEW_NESTE, _LOWER_VIEW_BETALT)
        has_subseq = self._subsequent_df is not None and not self._subsequent_df.empty
        try:
            if need_subseq and not has_subseq:
                self._load_subseq_btn.grid(
                    row=0, column=3, sticky="e", padx=(6, 0))
            else:
                self._load_subseq_btn.grid_remove()
        except Exception:
            pass

        if view == _LOWER_VIEW_BRREG:
            self._brreg_frame.grid(row=0, column=0, sticky="nsew")
            orgnr = self._orgnr_map.get(self._selected_nr, "") if self._selected_nr else ""
            self._update_brreg_panel(orgnr)
        elif view == _LOWER_VIEW_NESTE:
            self._subseq_frame.grid(row=0, column=0, sticky="nsew")
            self._populate_subseq_tree(self._selected_nr)
        elif view == _LOWER_VIEW_BETALT:
            self._payments_frame.grid(row=0, column=0, sticky="nsew")
            self._populate_payments_tree(self._selected_nr)

    def _populate_open_items_inline(self, nr: str) -> None:
        """Render åpne poster for valgt nr direkte i øvre tree."""
        tree = self._open_items_tree
        tree.delete(*tree.get_children())

        if not nr:
            self._detail_lbl.configure(
                text="Velg en post for å se åpne poster")
            return
        if self._df is None or self._master_df is None:
            return

        ub = 0.0
        ib = 0.0
        row_m = self._master_df[self._master_df["nr"].astype(str) == nr]
        if not row_m.empty:
            ub = float(row_m["ub"].iloc[0])
            ib = float(row_m["ib"].iloc[0])

        result_df, conf = _compute_open_items_with_confidence(
            self._df, nr=nr, mode=self._mode, ub=ub, ib=ib)

        dec = self._detail_decimals()
        n_open = 0
        sum_open = 0.0
        for _, r in result_df.iterrows():
            status = str(r.get("Status", ""))
            dato   = str(r.get("Dato", ""))[:10]
            bilag  = str(r.get("Bilag", ""))
            fnr    = str(r.get("FakturaNr", "") or "")
            tekst  = str(r.get("Tekst", ""))
            try:
                fakt   = float(r.get("Fakturabeløp", 0) or 0)
                betalt = float(r.get("Betalt (i år)", 0) or 0)
                gjen   = float(r.get("Gjenstår", 0) or 0)
            except (ValueError, TypeError):
                fakt = betalt = gjen = 0.0

            tags: list[str] = []
            if gjen < 0:
                tags.append(_TAG_NEG)

            tree.insert("", "end", values=(
                status, dato, bilag, fnr, tekst,
                formatting.fmt_amount(fakt, dec),
                formatting.fmt_amount(betalt, dec),
                formatting.fmt_amount(gjen, dec),
            ), tags=tuple(tags))

            if "\u00c5pen" in status or "Delvis" in status:
                n_open += 1
                sum_open += gjen

        tree.insert("", "end", values=(
            "", "", "", "", f"\u03a3 {n_open} åpne",
            "", "", formatting.fmt_amount(sum_open, dec),
        ), tags=(_TAG_HEADER,))

        navn = self._navn_for_nr(nr)
        mode_str = "Kunde" if self._mode == "kunder" else "Leverandør"
        lbl = f"{mode_str} {nr}"
        if navn:
            lbl += f"  \u2014  {navn}"
        lbl += (f"  ({len(result_df)} linjer, {n_open} åpne, "
                f"UB {formatting.fmt_amount(ub)})")
        if conf:
            lbl += f"  — tillit: {conf.get('level', '')}"
        self._detail_lbl.configure(text=lbl)

    def _populate_subseq_tree(self, nr: str) -> None:
        """Render transaksjoner for valgt nr i etterfølgende periode."""
        tree = self._subseq_tree
        tree.delete(*tree.get_children())

        if self._subsequent_df is None or self._subsequent_df.empty:
            self._subseq_empty_lbl.configure(
                text="Ingen etterfølgende periode er lastet.")
            return
        if not nr:
            self._subseq_empty_lbl.configure(
                text="Velg en post til venstre for å se transaksjoner i "
                     f"etterfølgende periode ({self._subsequent_label}).")
            return

        sub = _build_detail(self._subsequent_df, nr=nr, mode=self._mode)
        if sub.empty:
            self._subseq_empty_lbl.configure(
                text=(f"Ingen transaksjoner for {nr} i etterfølgende "
                      f"periode ({self._subsequent_label})."))
            return
        self._subseq_empty_lbl.configure(
            text=f"Etterfølgende periode: {self._subsequent_label}  "
                 f"({len(sub)} transaksjoner)")

        def _v(col: str, row: Any, default: Any = "") -> Any:
            try:
                val = row[col]
                if val is None or (isinstance(val, float) and str(val) == "nan"):
                    return default
                return val
            except (KeyError, IndexError):
                return default

        dec = self._detail_decimals()
        total = 0.0
        for _, row in sub.iterrows():
            dato  = str(_v("Dato",      row, ""))[:10]
            bilag = str(_v("Bilag",     row, ""))
            konto = str(_v("Konto",     row, ""))
            knavn = str(_v("Kontonavn", row, ""))
            tekst = str(_v("Tekst",     row, ""))
            ref   = str(_v("Referanse", row, ""))
            mva_kode = str(_v("MVA-kode", row, ""))
            if mva_kode in ("nan", "None"):
                mva_kode = ""
            try:
                belop = float(_v("Beløp", row, 0.0))
            except (ValueError, TypeError):
                belop = 0.0
            try:
                mva_raw = _v("MVA-beløp", row, None)
                mva_belop = float(mva_raw) if mva_raw not in (None, "", "nan") else None
            except (ValueError, TypeError):
                mva_belop = None
            total += belop

            tags: list[str] = []
            if belop < 0:
                tags.append(_TAG_NEG)
            if mva_kode or (mva_belop is not None and abs(mva_belop) > 0.001):
                tags.append(_TAG_MVA_LINE)

            tree.insert("", "end", values=(
                dato, bilag, konto, knavn, tekst,
                formatting.fmt_amount(belop, dec),
                mva_kode,
                formatting.fmt_amount(mva_belop, dec) if mva_belop is not None else "",
                ref,
            ), tags=tuple(tags))

        tree.insert("", "end", values=(
            "", "", "", "", f"\u03a3 {len(sub)} trans.",
            formatting.fmt_amount(total, dec), "", "", "",
        ), tags=(_TAG_HEADER,))

    def _populate_payments_tree(self, nr: str) -> None:
        """Render matchede betalinger for åpne poster."""
        tree = self._payments_tree
        tree.delete(*tree.get_children())

        if self._subsequent_df is None or self._subsequent_df.empty:
            self._payments_empty_lbl.configure(
                text="Ingen etterfølgende periode er lastet — "
                     "matching krever at neste SAF-T er lastet inn.")
            return
        if not nr:
            self._payments_empty_lbl.configure(
                text="Velg en post til venstre for å se matchede betalinger.")
            return
        if self._df is None or self._master_df is None:
            return

        ub = 0.0
        ib = 0.0
        row_m = self._master_df[self._master_df["nr"].astype(str) == nr]
        if not row_m.empty:
            ub = float(row_m["ub"].iloc[0])
            ib = float(row_m["ib"].iloc[0])

        open_df, _ = _compute_open_items_with_confidence(
            self._df, nr=nr, mode=self._mode, ub=ub, ib=ib)
        if open_df.empty:
            self._payments_empty_lbl.configure(
                text=f"Ingen åpne poster for {nr} — ingenting å matche.")
            return

        matched = _match_open_against_period(
            open_df, self._subsequent_df, nr=nr, mode=self._mode)
        if matched.empty:
            self._payments_empty_lbl.configure(
                text=f"Ingen matchende betalinger i {self._subsequent_label} "
                     f"for åpne poster på {nr}.")
            return

        self._payments_empty_lbl.configure(
            text=f"Matchet mot: {self._subsequent_label}  "
                 f"({len(matched)} linjer)")

        dec = self._detail_decimals()
        sum_betalt = 0.0
        sum_rest = 0.0
        for _, r in matched.iterrows():
            status = str(r.get("Status", ""))
            f_bilag = str(r.get("Bilag", ""))
            f_nr    = str(r.get("FakturaNr", "") or "")
            p_dato  = str(r.get("Betalt dato", "") or "")
            p_bilag = str(r.get("Betalt bilag", "") or "")
            p_tekst = str(r.get("Tekst", ""))
            try:
                p_belop = float(r.get("Betalt beløp") or 0.0)
                rest   = float(r.get("Resterende") or 0.0)
            except (ValueError, TypeError):
                p_belop = 0.0
                rest = 0.0

            tags: list[str] = []
            if rest < 0:
                tags.append(_TAG_NEG)

            tree.insert("", "end", values=(
                status, f_bilag, f_nr, p_dato, p_bilag, p_tekst,
                formatting.fmt_amount(p_belop, dec),
                formatting.fmt_amount(rest, dec),
            ), tags=tuple(tags))
            sum_betalt += p_belop
            sum_rest += rest

        tree.insert("", "end", values=(
            "", "", "", "", "", f"\u03a3 {len(matched)} linjer",
            formatting.fmt_amount(sum_betalt, dec),
            formatting.fmt_amount(sum_rest, dec),
        ), tags=(_TAG_HEADER,))

    # ------------------------------------------------------------------
    # Åpne poster (legacy popups — brukes fortsatt for Saldoliste)
    # ------------------------------------------------------------------

    def _navn_for_nr(self, nr: str) -> str:
        """Returner kundenavn/leverandørnavn for et internt nr-nummer."""
        try:
            navn_col = "Kundenavn" if self._mode == "kunder" else "Leverandørnavn"
            nr_col   = "Kundenr"   if self._mode == "kunder" else "Leverandørnr"
            if self._df is not None and nr_col in self._df.columns:
                mask = self._df[nr_col].astype(str).str.strip() == nr
                rows = self._df[mask]
                if not rows.empty and navn_col in rows.columns:
                    return str(rows[navn_col].iloc[0])
        except Exception:
            pass
        return ""

    def _show_open_items_popup(self) -> None:
        reskontro_popups.show_open_items_popup(self)

    def _show_saldoliste_popup(self) -> None:
        reskontro_popups.show_saldoliste_popup(self)

    def _open_subsequent_period(self) -> None:
        """Last inn SAF-T for etterfølgende periode."""
        try:
            from tkinter import filedialog
        except Exception:
            return

        path = filedialog.askopenfilename(
            parent=self,
            title="Velg SAF-T for etterfølgende periode (zip/xml)",
            filetypes=[
                ("SAF-T filer", "*.zip *.xml"),
                ("Alle filer",  "*.*"),
            ],
        )
        if not path:
            return

        try:
            self._load_subseq_btn.configure(state="disabled", text="Laster\u2026")
        except Exception:
            pass

        def _load() -> None:
            try:
                import saft_reader as _sr
                df2 = _sr.read_saft_ledger(path)
                import os
                label = os.path.basename(path)
                self.after(0, lambda: self._on_subseq_loaded(df2, label))
            except Exception as exc:
                log.exception("Etterfølgende SAF-T lasting feilet: %s", exc)
                def _fail(e: Exception = exc) -> None:
                    try:
                        self._load_subseq_btn.configure(
                            state="normal",
                            text="Last inn etterfølgende periode\u2026")
                    except Exception:
                        pass
                    self._status_lbl.configure(text=f"Feil ved lasting: {e}")
                self.after(0, _fail)

        import threading as _thr
        _thr.Thread(target=_load, daemon=True).start()

    def _on_subseq_loaded(self, df2: pd.DataFrame, label: str) -> None:
        self._subsequent_df    = df2
        self._subsequent_label = label
        try:
            self._load_subseq_btn.configure(
                state="normal",
                text="Last inn etterfølgende periode\u2026")
        except Exception:
            pass
        self._status_lbl.configure(
            text=f"Etterfølgende periode lastet: {label}")
        # Refresh nedre panel — viser matching/transaksjoner om valgt visning
        # trenger det. Ingen automatisk popup lenger.
        self._refresh_lower_panel()

    def _show_subsequent_match_popup(self) -> None:
        reskontro_popups.show_subsequent_match_popup(self)

    # ------------------------------------------------------------------
    # BRREG-sjekk
    # ------------------------------------------------------------------

    def _auto_brreg_all(self) -> None:
        """Auto-start BRREG-sjekk for alle orgnr som ikke allerede er hentet."""
        if self._master_df is None or self._master_df.empty:
            return
        # Sjekk om det finnes uhentede orgnr
        missing = [
            orgnr for orgnr in self._orgnr_map.values()
            if orgnr and len(orgnr) == 9 and orgnr.isdigit()
            and orgnr not in self._brreg_data
        ]
        if missing:
            self._start_brreg_sjekk()

    def _start_brreg_sjekk(self) -> None:
        """Start bakgrunnstråd som henter BRREG-data for alle synlige poster."""
        if self._master_df is None or self._master_df.empty:
            return

        orgnrs = [
            orgnr for orgnr in self._orgnr_map.values()
            if orgnr and len(orgnr) == 9 and orgnr.isdigit()
        ]
        if not orgnrs:
            self._status_lbl.configure(
                text="Ingen gyldige orgnumre i data. "
                     "Krever SAF-T-fil med RegistrationNumber.")
            return

        self._brreg_btn.configure(state="disabled", text="Henter\u2026")
        total = len(set(orgnrs))
        self._status_lbl.configure(
            text=f"BRREG: henter 0\u202f/\u202f{total}\u2026")

        def _progress(done: int, tot: int) -> None:
            self.after(0, lambda d=done, t=tot: self._status_lbl.configure(
                text=f"BRREG: henter {d}\u202f/\u202f{t}\u2026"))

        def _run() -> None:
            try:
                import brreg_client as _brreg
                results = _brreg.fetch_many(
                    list(set(orgnrs)),
                    progress_cb=_progress,
                    include_regnskap=True,
                )
                self.after(0, lambda r=results: self._on_brreg_done(r))
            except Exception as exc:
                log.exception("BRREG-sjekk feilet: %s", exc)
                self.after(0, lambda: (
                    self._brreg_btn.configure(
                        state="normal", text="BRREG-sjekk\u2026"),
                    self._status_lbl.configure(
                        text=f"BRREG feilet: {exc}"),
                ))

        threading.Thread(target=_run, daemon=True).start()

    def _on_brreg_done(self, results: dict) -> None:
        """Kalles fra main-tråden når BRREG-henting er ferdig."""
        self._brreg_data.update(results)
        self._apply_filter()
        self._brreg_btn.configure(state="normal", text="BRREG-sjekk\u2026")

        n_ok    = sum(1 for v in results.values() if v.get("enhet"))
        n_total = len(results)
        n_warn  = sum(
            1 for v in results.values()
            if _brreg_has_risk(v.get("enhet") or {}))
        n_no_mva = sum(
            1 for v in results.values()
            if v.get("enhet")
            and not (v["enhet"] or {}).get("registrertIMvaregisteret"))

        parts = [f"BRREG: {n_ok}/{n_total} hentet"]
        if n_warn:
            parts.append(f"\u26a0 {n_warn} med risiko")
        if n_no_mva:
            parts.append(f"\u2717 {n_no_mva} ikke MVA-reg.")
        self._status_lbl.configure(text="  \u2022  ".join(parts))

        # Oppdater BRREG-panelet for valgt rad hvis den visningen er aktiv
        if (self._selected_nr
                and self._lower_view_var.get() == _LOWER_VIEW_BRREG):
            orgnr = self._orgnr_map.get(self._selected_nr, "")
            if orgnr:
                self._update_brreg_panel(orgnr)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def _export_excel(self) -> None:
        try:
            import session as _session
            import analyse_export_excel as _xls
            client     = getattr(_session, "client", None) or ""
            year       = str(getattr(_session, "year", "") or "")
            mode_label = "kunder" if self._mode == "kunder" else "leverandorer"
            path = _xls.open_save_dialog(
                title="Eksporter Reskontro",
                default_filename=(
                    f"reskontro_{mode_label}_{client}_{year}.xlsx"
                ).strip("_"),
                master=self,
            )
            if not path:
                return
            master_sheet = _xls.treeview_to_sheet(
                self._master_tree,
                title="Oversikt",
                heading=(
                    f"Reskontro \u2014 "
                    f"{'Kunder' if self._mode == 'kunder' else 'Leverand\u00f8rer'}"
                ),
                bold_tags=(_TAG_HEADER,),
                bg_tags={
                    _TAG_NEG:        "FFEBEE",
                    _TAG_BRREG_WARN: "FFF3CD",
                    _TAG_MVA_WARN:   "FFF8E1",
                },
            )
            # Eksporter treet som faktisk er synlig i øvre høyrepanel —
            # brukeren forventer at det de ser er det de får.
            upper_view = ""
            try:
                upper_view = self._upper_view_var.get()
            except Exception:
                upper_view = _UPPER_VIEW_ALLE
            if upper_view == _UPPER_VIEW_APNE:
                upper_tree  = self._open_items_tree
                upper_title = "Åpne poster"
                upper_head  = f"Åpne poster: {self._selected_nr}"
            else:
                upper_tree  = self._detail_tree
                upper_title = "Transaksjoner"
                upper_head  = f"Transaksjoner: {self._selected_nr}"
            detail_sheet = _xls.treeview_to_sheet(
                upper_tree,
                title=upper_title,
                heading=upper_head,
                bold_tags=(_TAG_HEADER,),
                bg_tags={_TAG_NEG: "FFEBEE"},
            )
            _xls.export_and_open(
                path, [master_sheet, detail_sheet],
                title="Reskontro", client=client, year=year)
        except Exception as exc:
            log.exception("Reskontro Excel-eksport feilet: %s", exc)

    def _export_pdf_report(self) -> None:
        from tkinter import filedialog, messagebox
        if not _has_reskontro_data(self._df):
            messagebox.showinfo(
                "Reskontrorapport",
                "Ingen reskontrodata er lastet. Last inn en SAF-T-fil først.",
                parent=self,
            )
            return
        try:
            import session as _session
            from reskontro_report_engine import compute_reskontro_report
            from reskontro_report_html import save_report_pdf

            client = getattr(_session, "client", None) or ""
            year = str(getattr(_session, "year", "") or "")

            sb_df = None
            try:
                from page_analyse_rl import load_sb_for_session
                sb_df = load_sb_for_session()
            except Exception:
                sb_df = None

            reference_date = ""
            if year:
                reference_date = f"{year}-12-31"

            report = compute_reskontro_report(
                self._df,
                mode=self._mode,
                client=client,
                year=year,
                reference_date=reference_date,
                sb_df=sb_df,
                top_n=10,
            )

            mode_label = "kunder" if self._mode == "kunder" else "leverandorer"
            default_name = f"reskontrorapport_{mode_label}_{client}_{year}.pdf".strip("_")
            path = filedialog.asksaveasfilename(
                parent=self,
                title="Lagre reskontrorapport som PDF",
                defaultextension=".pdf",
                initialfile=default_name,
                filetypes=[("PDF", "*.pdf")],
            )
            if not path:
                return

            saved = save_report_pdf(path, report, top_n=10)
            try:
                import os
                os.startfile(saved)
            except Exception:
                pass
        except ImportError as exc:
            messagebox.showerror(
                "Reskontrorapport",
                f"Playwright mangler: {exc}",
                parent=self,
            )
        except Exception as exc:
            log.exception("Reskontrorapport PDF-eksport feilet: %s", exc)
            messagebox.showerror(
                "Reskontrorapport",
                f"Kunne ikke generere PDF:\n{exc}",
                parent=self,
            )
