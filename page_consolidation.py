"""page_consolidation.py — Konsolidering MVP arbeidsflate.

Layout (Analyse-lignende):
  Toolbar:  [Importer selskap] [Kjoer konsolidering] [Eksporter]
  Status:   "N selskaper | M elimineringer | Siste run: ..."
  Venstre:  [Selskaper] [Eliminering]  (tabs)
  Hoeyre:   [Detalj]    [Resultat]     (tabs)
  Statuslinje: Konsolidering | Klient / Aar | TB-only
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import session
from consolidation.models import (
    CompanyTB,
    ConsolidationProject,
    EliminationJournal,
    EliminationLine,
    EliminationSuggestion,
    MappingConfig,
)
from consolidation import storage, tb_import
from consolidation.control_rows import append_control_rows
from consolidation.suggestions import (
    create_journal_from_suggestion,
    generate_suggestions,
    ignore_suggestion,
    unignore_suggestion,
)
from consolidation_mapping_tab import MappingTab
from treeview_column_manager import TreeviewColumnManager
from ui_managed_treeview import ColumnSpec, ManagedTreeview

try:
    from ui_treeview_sort import enable_treeview_sorting
except Exception:  # pragma: no cover
    enable_treeview_sorting = None  # type: ignore


def _reset_sort_state(tree) -> None:
    """Nullstill sorteringstilstand slik at data vises i naturlig rekkefoelje."""
    if hasattr(tree, "_sort_state"):
        tree._sort_state.last_col = None
        tree._sort_state.descending = False

logger = logging.getLogger(__name__)

_SOURCE_LABELS = {
    "excel": "TB-fil",
    "csv": "TB-fil",
    "saft": "SAF-T TB",
    "session": "Session TB",
    "session-sb": "SAF-T SB",
}


def _source_display(source_type: str, has_ib: bool) -> str:
    """Human-readable source label with IB-quality indicator."""
    label = _SOURCE_LABELS.get(source_type, source_type or "ukjent")
    if not has_ib:
        label += " (kun netto)"
    return label


def _fmt_no(value: float, decimals: int = 0) -> str:
    """Formater beloep med norsk tusenskille (mellomrom) og komma som desimal.

    Eksempel: _fmt_no(423660.5, 2) -> '423 660,50'
    """
    if abs(value) < 0.005 and decimals == 0:
        return "0"
    sign = "-" if value < 0 else ""
    # Bruk Pythons innebygde formatering, bytt ut skilletegn
    if decimals > 0:
        formatted = f"{abs(value):,.{decimals}f}"
    else:
        formatted = f"{round(abs(value)):,}"
    # Bytt fra US-format (1,234.56) til norsk (1 234,56)
    formatted = formatted.replace(",", " ").replace(".", ",")
    return sign + formatted


_MAPPING_REVIEW_KEYWORDS = (
    "dispon",
    "disposition",
    "dividend",
    "udbytte",
    "utbytte",
    "egenkap",
    "equity",
    "årets resultat",
    "arets resultat",
)


def _normalize_mapping_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return text.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")


def _detect_mapping_review_accounts(
    mapped_df: pd.DataFrame,
    regnr_to_name: dict[int, str],
) -> tuple[set[str], list[str]]:
    """Finn kontoer som ser ut som EK/disponering, men er mappet inn i resultatdelen."""
    review_accounts: set[str] = set()
    review_details: list[str] = []
    if mapped_df is None or mapped_df.empty:
        return review_accounts, review_details

    for _, row in mapped_df.iterrows():
        regnr_raw = row.get("regnr")
        try:
            regnr = int(regnr_raw) if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            regnr = None
        if regnr is None or regnr >= 295:
            continue

        konto = str(row.get("konto", "") or "").strip()
        kontonavn = str(row.get("kontonavn", "") or "").strip()
        if not konto:
            continue

        ib = pd.to_numeric(pd.Series([row.get("ib", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        ub = pd.to_numeric(pd.Series([row.get("ub", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        netto = pd.to_numeric(pd.Series([row.get("netto", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        if abs(float(ib)) <= 0.005 and abs(float(ub)) <= 0.005 and abs(float(netto)) <= 0.005:
            continue

        name_norm = _normalize_mapping_text(kontonavn)
        if not any(keyword in name_norm for keyword in _MAPPING_REVIEW_KEYWORDS):
            continue

        review_accounts.add(konto)
        rl_name = str(row.get("regnskapslinje", "") or regnr_to_name.get(regnr, "") or "")
        review_details.append(f"{konto} {kontonavn} -> {regnr} {rl_name}".strip())

    return review_accounts, review_details


class ConsolidationPage(ttk.Frame):  # type: ignore[misc]
    """Hovedside for konsolidering MVP."""

    def __init__(self, master=None):
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            self._status_var = None
            return

        self._project: Optional[ConsolidationProject] = None
        self._company_tbs: dict[str, pd.DataFrame] = {}
        self._mapped_tbs: dict[str, pd.DataFrame] = {}
        self._mapping_review_accounts: dict[str, set[str]] = {}
        self._mapping_review_details: dict[str, list[str]] = {}
        self._result_df: Optional[pd.DataFrame] = None
        self._last_run_result = None  # RunResult fra siste kjøring (account_details m.m.)
        self._readiness_report = None
        self._current_detail_cid: Optional[str] = None
        self._suggestions: list[EliminationSuggestion] = []

        # Cached mapping config (loaded once per project)
        self._intervals: Optional[pd.DataFrame] = None
        self._regnskapslinjer: Optional[pd.DataFrame] = None
        self._regnr_to_name: dict[int, str] = {}

        self._status_var = tk.StringVar(value="Velg klient og aar for aa starte.")
        self._readiness_status_var = tk.StringVar(value="")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # --- Toolbar ---
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))

        ttk.Button(toolbar, text="Importer selskap", command=self._on_import_company).pack(
            side="left", padx=(0, 4),
        )
        self._btn_use_session_tb = ttk.Button(
            toolbar, text="Bruk aktiv klient som mor",
            command=self._on_use_session_tb,
        )
        self._btn_use_session_tb.pack(side="left", padx=(0, 4))
        self._btn_use_session_tb.pack_forget()  # skjult til data er tilgjengelig

        self._btn_run = ttk.Button(toolbar, text="Kjoer konsolidering", command=self._on_run)
        self._btn_run.pack(side="left", padx=(0, 4))
        self._btn_export = ttk.Button(toolbar, text="Eksporter", command=self._on_export)
        self._btn_export.pack(side="left", padx=(0, 4))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)

        # ÅO checkbox (gjelder kun morselskap)
        self._include_ao_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="Inkl. AO (mor)",
            variable=self._include_ao_var,
            command=self._on_ao_toggled,
        ).pack(side="left", padx=(0, 8))

        ttk.Label(toolbar, textvariable=self._status_var).pack(side="left")

        readiness_strip = ttk.Frame(self)
        readiness_strip.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))
        ttk.Label(readiness_strip, textvariable=self._readiness_status_var, anchor="w").pack(fill="x")

        # --- Main paned area ---
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)

        # Left: tabs Selskaper / Eliminering
        left_nb = ttk.Notebook(pw)
        self._left_nb = left_nb

        # Tab: Selskaper
        frm_companies = ttk.Frame(left_nb)
        self._left_tab_companies = frm_companies
        left_nb.add(frm_companies, text="Selskaper")
        self._tree_companies = self._make_company_tree(frm_companies)

        # Tab: Kontroller
        frm_controls = ttk.Frame(left_nb)
        self._left_tab_controls = frm_controls
        left_nb.add(frm_controls, text="Kontroller")
        self._build_controls_tab(frm_controls)

        # Tab: Eliminering
        frm_elim = ttk.Frame(left_nb)
        self._left_tab_elim = frm_elim
        left_nb.add(frm_elim, text="Eliminering")
        self._build_elimination_tab(frm_elim)

        # Tab: Grunnlag
        frm_grunnlag = ttk.Frame(left_nb)
        self._left_tab_grunnlag = frm_grunnlag
        left_nb.add(frm_grunnlag, text="Grunnlag")
        self._build_grunnlag_tab(frm_grunnlag)

        pw.add(left_nb, weight=3)

        # Right: tabs Detalj / Resultat
        right_nb = ttk.Notebook(pw)
        self._right_nb = right_nb

        # Tab: Detalj
        frm_detail = ttk.Frame(right_nb)
        self._right_tab_detail = frm_detail
        right_nb.add(frm_detail, text="Detalj")

        # Detalj toolbar med filter
        detail_toolbar = ttk.Frame(frm_detail)
        detail_toolbar.pack(side="top", fill="x", padx=4, pady=(4, 0))
        self._detail_hide_zero_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            detail_toolbar, text="Kun linjer med verdi",
            variable=self._detail_hide_zero_var,
            command=self._on_detail_filter_changed,
        ).pack(side="left")
        self._detail_count_var = tk.StringVar(value="")
        ttk.Label(detail_toolbar, textvariable=self._detail_count_var).pack(side="right")

        self._tree_detail = self._make_detail_tree(frm_detail)

        # Tab: Mapping
        self._mapping_tab = MappingTab(
            right_nb,
            on_overrides_changed=self._on_mapping_overrides_changed,
        )
        self._right_tab_mapping = self._mapping_tab
        right_nb.add(self._mapping_tab, text="Mapping")

        # Tab: Resultat
        frm_result = ttk.Frame(right_nb)
        self._right_tab_result = frm_result
        right_nb.add(frm_result, text="Resultat")
        self._build_result_tab(frm_result)

        pw.add(right_nb, weight=5)

        # --- Statuslinje ---
        status_bar = ttk.Frame(self)
        status_bar.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._lbl_statusbar = ttk.Label(
            status_bar, text="Konsolidering | TB-only", anchor="w",
        )
        self._lbl_statusbar.pack(fill="x")

    def _select_left_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        nb = getattr(self, "_left_nb", None)
        if nb is None:
            return
        tab_ref = getattr(self, tab_ref_attr, None)
        try:
            nb.select(tab_ref if tab_ref is not None else fallback_index)
        except Exception:
            pass

    def _select_right_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        nb = getattr(self, "_right_nb", None)
        if nb is None:
            return
        tab_ref = getattr(self, tab_ref_attr, None)
        try:
            nb.select(tab_ref if tab_ref is not None else fallback_index)
        except Exception:
            pass

    def _select_elim_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        nb = getattr(self, "_elim_nb", None)
        if nb is None:
            return
        tab_ref = getattr(self, tab_ref_attr, None)
        try:
            nb.select(tab_ref if tab_ref is not None else fallback_index)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Treeview builders
    # ------------------------------------------------------------------

    def _make_company_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        cols = ("name", "source", "rows", "mapping")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="browse")
        tree.heading("name", text="Selskap")
        tree.heading("source", text="Kilde")
        tree.heading("rows", text="Rader")
        tree.heading("mapping", text="Mapping")
        tree.column("name", width=160)
        tree.column("source", width=80)
        tree.column("rows", width=60, anchor="e")
        tree.column("mapping", width=80)
        tree.tag_configure("done", background="#E2F1EB")
        tree.tag_configure("review", background="#FCEBD9")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tree.bind("<<TreeviewSelect>>", self._on_company_select)
        tree.bind("<Delete>", self._on_delete_company)
        tree.bind("<Return>", self._on_company_select)

        # Hoeyreklikk-meny
        self._company_menu = tk.Menu(tree, tearoff=0)
        self._company_menu.add_command(label="Vis detalj", command=self._on_company_select)
        self._company_menu.add_command(label="Sett som morselskap", command=self._on_set_parent)
        self._company_menu.add_command(label="Importer paa nytt", command=self._on_reimport_company)
        self._company_menu.add_command(label="Vis umappede", command=self._on_show_unmapped)
        self._company_menu.add_separator()
        self._company_menu.add_command(label="Slett selskap", command=self._on_delete_company)
        self._companies_tree_mgr = ManagedTreeview(
            tree,
            view_id="companies",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("name", "Selskap", width=160, pinned=True, stretch=True),
                ColumnSpec("source", "Kilde", width=80),
                ColumnSpec("rows", "Rader", width=60, anchor="e"),
                ColumnSpec("mapping", "Mapping", width=80),
            ],
            on_body_right_click=self._on_company_right_click,
        )
        self._companies_col_mgr = self._companies_tree_mgr.column_manager
        return tree

    def _build_controls_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        toolbar.columnconfigure(0, weight=1)
        self._readiness_summary_var = tk.StringVar(value="Ingen kontroller kjørt ennå.")
        ttk.Label(toolbar, textvariable=self._readiness_summary_var).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Åpne valgt", command=self._open_selected_readiness_issue).grid(row=0, column=1, sticky="e", padx=(8, 0))

        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        cols = ("severity", "category", "company", "message", "action")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")
        tree.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        sb.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=sb.set)
        tree.tag_configure("blocking", background="#FCE4E4")
        tree.tag_configure("warning", background="#FFF4D6")
        tree.tag_configure("info", background="#E9F2FF")
        self._tree_controls = tree
        self._readiness_issue_map: dict[str, object] = {}

        self._controls_tree_mgr = ManagedTreeview(
            tree,
            view_id="consolidation.controls",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("severity", "Nivå", width=90, pinned=True),
                ColumnSpec("category", "Kategori", width=100, pinned=True),
                ColumnSpec("company", "Selskap", width=150, stretch=True),
                ColumnSpec("message", "Melding", width=360, stretch=True),
                ColumnSpec("action", "Handling", width=120),
            ],
        )
        tree.bind("<Double-1>", lambda _e=None: self._open_selected_readiness_issue())

    def _make_detail_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        cols = ("konto", "kontonavn", "regnr", "rl_navn", "ib", "netto", "ub")
        tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="extended")
        _detail_headings = {
            "konto": "Konto", "kontonavn": "Kontonavn", "regnr": "Regnr",
            "rl_navn": "Regnskapslinje", "ib": "IB", "netto": "Bevegelse", "ub": "UB",
        }
        for c in cols:
            tree.heading(c, text=_detail_headings.get(c, c.capitalize()))
            w = {
                "kontonavn": 140, "rl_navn": 150, "konto": 80, "regnr": 55,
            }.get(c, 80)
            anchor = "w" if c in ("kontonavn", "rl_navn") else "e"
            tree.column(c, width=w, anchor=anchor)
        tree.tag_configure("review", background="#FCEBD9")

        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Ctrl+C kopiering
        tree.bind("<Control-c>", lambda e: self._copy_tree_to_clipboard(tree))

        # Dobbeltklikk for aa endre mapping
        tree.bind("<Double-1>", self._on_detail_double_click)

        # Hoeyreklikk-meny paa detalj
        self._detail_menu = tk.Menu(tree, tearoff=0)
        self._detail_menu.add_command(
            label="Endre regnskapslinje...", command=self._on_change_mapping,
        )
        self._detail_tree_mgr = ManagedTreeview(
            tree,
            view_id="detail",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("konto", "Konto", width=80, pinned=True),
                ColumnSpec("kontonavn", "Kontonavn", width=140, stretch=True),
                ColumnSpec("regnr", "Regnr", width=55, anchor="e"),
                ColumnSpec("rl_navn", "Regnskapslinje", width=150, stretch=True),
                ColumnSpec("ib", "IB", width=80, anchor="e"),
                ColumnSpec("netto", "Bevegelse", width=80, anchor="e"),
                ColumnSpec("ub", "UB", width=80, anchor="e"),
            ],
            on_body_right_click=self._on_detail_right_click,
        )
        self._detail_col_mgr = self._detail_tree_mgr.column_manager
        return tree

    def _build_result_tab(self, parent: ttk.Frame) -> None:
        """Build the Resultat tab with mode selector and hide-zero filter."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # --- Toolbar ---
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))

        ttk.Label(toolbar, text="Visning:").pack(side="left", padx=(0, 4))
        self._result_mode_var = tk.StringVar(value="company")
        mode_combo = ttk.Combobox(
            toolbar, textvariable=self._result_mode_var,
            values=["Valgt selskap", "Konsolidert", "Per selskap"],
            state="readonly", width=16,
        )
        mode_combo.set("Valgt selskap")
        mode_combo.pack(side="left", padx=(0, 12))
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_result_mode_changed())

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        self._col_before_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="F\u00f8r omr.",
            variable=self._col_before_var,
            command=self._on_result_mode_changed,
        ).pack(side="left", padx=(0, 4))

        self._col_kurs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="Kurs",
            variable=self._col_kurs_var,
            command=self._on_result_mode_changed,
        ).pack(side="left", padx=(0, 4))

        self._col_fx_effect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            toolbar, text="Valutaeffekt",
            variable=self._col_fx_effect_var,
            command=self._on_result_mode_changed,
        ).pack(side="left", padx=(0, 8))

        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        self._hide_zero_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar, text="Kun m/verdi",
            variable=self._hide_zero_var,
            command=self._on_result_mode_changed,
        ).pack(side="left")

        # Preview-indikator
        self._preview_label_var = tk.StringVar(value="")
        self._preview_label = ttk.Label(
            toolbar, textvariable=self._preview_label_var,
            foreground="#0066CC",
        )
        self._preview_label.pack(side="right")

        # --- Treeview ---
        tree_frm = ttk.Frame(parent)
        tree_frm.grid(row=1, column=0, sticky="nsew")

        tree = ttk.Treeview(tree_frm, columns=(), show="headings", selectmode="browse")
        tree.tag_configure("sumline", background="#EDF1F5")
        tree.tag_configure("sumline_major", background="#E0E4EA")
        tree.tag_configure("neg", foreground="red")

        sb = ttk.Scrollbar(tree_frm, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tree.bind("<Control-c>", lambda e: self._copy_tree_to_clipboard(tree))
        tree.bind("<<TreeviewSelect>>", self._on_result_line_select)
        tree.bind("<Button-3>", self._on_result_right_click)
        self._tree_result = tree
        # One column manager per result mode so visibility/order don't bleed
        _pinned_result = ("regnr", "regnskapslinje")
        self._result_col_mgrs: dict[str, TreeviewColumnManager] = {
            key: TreeviewColumnManager(
                tree, view_id=f"result.{key}",
                all_cols=(), pinned_cols=_pinned_result,
            )
            for key in ("company", "consolidated", "per_company")
        }

        # Cached result DataFrames
        self._company_result_df: Optional[pd.DataFrame] = None
        self._consolidated_result_df: Optional[pd.DataFrame] = None
        self._preview_result_df: Optional[pd.DataFrame] = None

    # ------------------------------------------------------------------
    # Grunnlag tab (drilldown fra valgt regnskapslinje)
    # ------------------------------------------------------------------

    def _build_grunnlag_tab(self, parent: ttk.Frame) -> None:
        """Bygg Grunnlag-fanen med konto-drilldown fra Resultat."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Statuslinje
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
        self._grunnlag_label_var = tk.StringVar(value="Velg regnskapslinje i Resultat")
        ttk.Label(toolbar, textvariable=self._grunnlag_label_var).pack(side="left")

        # Treeview
        tree_frm = ttk.Frame(parent)
        tree_frm.grid(row=1, column=0, sticky="nsew")

        grunnlag_cols = (
            "selskap", "konto", "kontonavn", "regnr", "regnskapslinje",
            "ib", "bevegelse", "ub_original", "valuta", "kurs",
            "ub_konvertert", "valutaeffekt",
        )
        tree = ttk.Treeview(
            tree_frm, columns=grunnlag_cols, show="headings",
            selectmode="browse",
        )
        _grunnlag_headings = {
            "selskap": "Selskap", "konto": "Konto", "kontonavn": "Kontonavn",
            "regnr": "Regnr", "regnskapslinje": "Regnskapslinje",
            "ib": "IB", "bevegelse": "Bevegelse",
            "ub_original": "Bel\u00f8p f\u00f8r", "valuta": "Valuta",
            "kurs": "Kurs", "ub_konvertert": "Bel\u00f8p etter",
            "valutaeffekt": "Valutaeffekt",
        }
        _grunnlag_widths = {
            "selskap": 120, "konto": 70, "kontonavn": 140,
            "regnr": 50, "regnskapslinje": 120,
            "ib": 80, "bevegelse": 80, "ub_original": 90,
            "valuta": 50, "kurs": 55, "ub_konvertert": 90,
            "valutaeffekt": 85,
        }
        for c in grunnlag_cols:
            tree.heading(c, text=_grunnlag_headings.get(c, c))
            w = _grunnlag_widths.get(c, 80)
            anchor = "w" if c in ("selskap", "kontonavn", "regnskapslinje", "valuta") else "e"
            tree.column(c, width=w, anchor=anchor)

        tree.tag_configure("neg", foreground="red")

        sb = ttk.Scrollbar(tree_frm, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        tree.bind("<Control-c>", lambda e: self._copy_tree_to_clipboard(tree))
        self._tree_grunnlag = tree
        self._grunnlag_tree_mgr = ManagedTreeview(
            tree,
            view_id="grunnlag",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("selskap", "Selskap", width=120, pinned=True, stretch=True),
                ColumnSpec("konto", "Konto", width=70, pinned=True),
                ColumnSpec("kontonavn", "Kontonavn", width=140, stretch=True),
                ColumnSpec("regnr", "Regnr", width=50, anchor="e"),
                ColumnSpec("regnskapslinje", "Regnskapslinje", width=120, stretch=True),
                ColumnSpec("ib", "IB", width=80, anchor="e"),
                ColumnSpec("bevegelse", "Bevegelse", width=80, anchor="e"),
                ColumnSpec("ub_original", "Beløp før", width=90, anchor="e"),
                ColumnSpec("valuta", "Valuta", width=50),
                ColumnSpec("kurs", "Kurs", width=55, anchor="e"),
                ColumnSpec("ub_konvertert", "Beløp etter", width=90, anchor="e"),
                ColumnSpec("valutaeffekt", "Valutaeffekt", width=85, anchor="e"),
            ],
        )
        self._grunnlag_col_mgr = self._grunnlag_tree_mgr.column_manager

    def _on_result_line_select(self, event=None) -> None:
        """Callback for regnskapslinje-valg i Resultat-treet: oppdater Grunnlag."""
        sel = self._tree_result.selection()
        if not sel:
            return
        item = sel[0]
        vals = self._tree_result.item(item, "values")
        tags = self._tree_result.item(item, "tags")
        if not vals:
            return
        try:
            regnr = int(vals[0])
        except (ValueError, TypeError):
            return
        is_sumpost = "sumline" in tags or "sumline_major" in tags
        self._populate_grunnlag(regnr, is_sumpost=is_sumpost)
        # Auto-bytt til Grunnlag-fanen
        self._select_left_tab(2, "_left_tab_grunnlag")

    def _populate_grunnlag(self, regnr: int, *, is_sumpost: bool = False) -> None:
        """Fyll Grunnlag-treet med kontoer fra account_details for valgt regnr.

        I 'Valgt selskap'-modus filtreres paa valgt selskap.
        I 'Konsolidert'/'Per selskap' vises alle selskaper.
        For sumposter utvides til underliggende leaf-linjer.
        """
        tree = self._tree_grunnlag
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())

        # Finn rl-navn
        rl_name = self._regnr_to_name.get(regnr, "")

        # Utvid sumpost til underliggende leaf-regnr
        leaf_regnrs: list[int] = [regnr]
        if is_sumpost and self._regnskapslinjer is not None:
            try:
                from regnskap_mapping import expand_regnskapslinje_selection
                expanded = expand_regnskapslinje_selection(
                    regnskapslinjer=self._regnskapslinjer,
                    selected_regnr=[regnr],
                )
                if expanded:
                    leaf_regnrs = expanded
            except Exception:
                logger.debug("Could not expand sumpost %s", regnr, exc_info=True)

        # Hent account_details fra siste run
        run_result = self._last_run_result
        if run_result is None or run_result.account_details is None:
            self._grunnlag_label_var.set(f"Regnr {regnr}: {rl_name}")
            tree.insert("", "end", values=(
                "", "", "Kjoer konsolidering for aa se grunnlag",
                "", "", "", "", "", "", "", "", "",
            ))
            return

        details: pd.DataFrame = run_result.account_details
        # Filtrer paa leaf-regnr (en eller flere)
        leaf_set = set(float(r) for r in leaf_regnrs)
        mask = details["regnr"].notna() & details["regnr"].astype(float).isin(leaf_set)
        filtered = details.loc[mask].copy()

        # Kontekstfiltrering: i Valgt selskap-modus, vis kun valgt selskap
        mode = self._result_mode_var.get()
        company_filter = ""
        if mode == "Valgt selskap":
            cid = getattr(self, "_current_detail_cid", None)
            proj = getattr(self, "_project", None)
            if cid and proj:
                company = proj.find_company(cid)
                if company:
                    company_filter = company.name
                    filtered = filtered[filtered["selskap"] == company_filter]

        # Oppdater label
        scope_parts: list[str] = []
        if is_sumpost and len(leaf_regnrs) > 1:
            scope_parts.append(f"{len(leaf_regnrs)} underliggende linjer")
        scope_parts.append(company_filter if company_filter else "alle selskaper")
        self._grunnlag_label_var.set(f"Regnr {regnr}: {rl_name} ({', '.join(scope_parts)})")

        if filtered.empty:
            tree.insert("", "end", values=(
                "", "", f"Ingen kontoer paa regnr {regnr}",
                "", "", "", "", "", "", "", "", "",
            ))
            return

        # Stabil sortering: selskap → konto
        filtered = filtered.sort_values(
            ["selskap", "konto"], na_position="last",
        ).reset_index(drop=True)

        for _, row in filtered.iterrows():
            selskap = str(row.get("selskap", ""))
            konto = str(row.get("konto", ""))
            kontonavn = str(row.get("kontonavn", ""))
            r = int(row["regnr"])
            rl = str(row.get("regnskapslinje", ""))
            ib = float(row.get("ib", 0.0)) if pd.notna(row.get("ib")) else 0.0
            netto = float(row.get("netto", 0.0)) if pd.notna(row.get("netto")) else 0.0
            ub_orig = float(row.get("ub_original", 0.0)) if pd.notna(row.get("ub_original")) else 0.0
            valuta = str(row.get("valuta", ""))
            kurs = float(row.get("kurs", 1.0)) if pd.notna(row.get("kurs")) else 1.0
            ub_conv = float(row.get("ub", 0.0)) if pd.notna(row.get("ub")) else 0.0
            valutaeffekt = ub_conv - ub_orig

            tags = ()
            if ub_conv < -0.005:
                tags = ("neg",)

            tree.insert("", "end", values=(
                selskap, konto, kontonavn, r, rl,
                _fmt_no(ib, 2), _fmt_no(netto, 2), _fmt_no(ub_orig, 2),
                valuta, _fmt_no(kurs, 4) if abs(kurs - 1.0) > 0.0001 else "1",
                _fmt_no(ub_conv, 2),
                _fmt_no(valutaeffekt, 2) if abs(valutaeffekt) > 0.005 else "",
            ), tags=tags)

    # ------------------------------------------------------------------
    # Elimination tab
    # ------------------------------------------------------------------

    def _build_elimination_tab(self, parent: ttk.Frame) -> None:
        """Bygg Eliminering-fanen med intern notebook: Enkel, Journaler, Forslag, Valuta."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        self._elim_nb = ttk.Notebook(parent)
        self._elim_nb.grid(row=0, column=0, sticky="nsew")

        # --- Tab: Enkel eliminering (primaer) ---
        frm_enkel = ttk.Frame(self._elim_nb)
        self._elim_tab_simple = frm_enkel
        self._elim_nb.add(frm_enkel, text="Eliminering")
        self._build_enkel_elim_tab(frm_enkel)

        # --- Tab: Journaler ---
        frm_journaler = ttk.Frame(self._elim_nb)
        self._elim_tab_journals = frm_journaler
        self._elim_nb.add(frm_journaler, text="Journaler")
        self._build_journaler_tab(frm_journaler)

        # --- Tab: Forslag (sekundaer) ---
        frm_forslag = ttk.Frame(self._elim_nb)
        self._elim_tab_suggestions = frm_forslag
        self._elim_nb.add(frm_forslag, text="Forslag")
        self._build_forslag_tab(frm_forslag)

        # --- Tab: Valuta ---
        frm_valuta = ttk.Frame(self._elim_nb)
        self._elim_tab_fx = frm_valuta
        self._elim_nb.add(frm_valuta, text="Valuta")
        self._build_valuta_tab(frm_valuta)

    def _build_enkel_elim_tab(self, parent: ttk.Frame) -> None:
        """Eliminering: flerlinje-journalbygger paa regnskapslinjenivaa."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(4, weight=2)

        # === Input-seksjon ===
        form = ttk.LabelFrame(parent, text="Bilag — legg til linjer", padding=8)
        form.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        form.columnconfigure(1, weight=1)
        self._draft_source_journal_id: str | None = None
        self._draft_voucher_no: int = 1
        self._elim_mode_var = tk.StringVar(value="Nytt bilag")
        self._elim_voucher_var = tk.StringVar(value="Bilag nr: 1")
        self._elim_save_btn_var = tk.StringVar(value="Opprett bilag")

        header = ttk.Frame(form)
        header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, textvariable=self._elim_mode_var).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self._elim_voucher_var).grid(row=0, column=1, sticky="w", padx=(12, 0))

        header_btns = ttk.Frame(header)
        header_btns.grid(row=0, column=2, sticky="e")
        ttk.Button(header_btns, text="Nytt bilag", command=self._begin_new_elim_draft).pack(side="left")
        self._btn_create_elim = ttk.Button(
            header_btns,
            textvariable=self._elim_save_btn_var,
            command=self._on_create_simple_elim,
            state="disabled",
        )
        self._btn_create_elim.pack(side="left", padx=(4, 0))
        ttk.Button(header_btns, text="Nullstill utkast", command=self._on_draft_clear).pack(
            side="left", padx=(4, 0),
        )

        # Journalnavn brukes ikke lenger som manuell input, men beholdes av kompatibilitetshensyn.
        self._elim_desc_var = tk.StringVar()

        # Regnskapslinje (søkbar combobox)
        ttk.Label(form, text="Regnskapslinje:").grid(row=1, column=0, sticky="w", pady=2)
        self._elim_line_var = tk.StringVar()
        cb_rl = ttk.Combobox(form, textvariable=self._elim_line_var, width=60)
        cb_rl.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
        cb_rl.bind("<<ComboboxSelected>>", lambda _e: self._on_elim_line_selected())
        cb_rl.bind("<KeyRelease>", self._on_elim_combo_filter)
        self._elim_cb_rl = cb_rl

        rl_btn_frm = ttk.Frame(form)
        rl_btn_frm.grid(row=1, column=2, padx=(4, 0))
        self._elim_line_sum_var = tk.StringVar(value="")
        ttk.Label(rl_btn_frm, textvariable=self._elim_line_sum_var, foreground="#666666").pack(
            side="left", padx=(0, 6),
        )
        ttk.Button(
            rl_btn_frm, text="Fra Resultat", command=self._on_use_result_rl,
        ).pack(side="left")

        # Beloep (positiv=debet, negativ=kredit)
        ttk.Label(form, text="Beloep:").grid(row=2, column=0, sticky="w", pady=2)
        amt_frm = ttk.Frame(form)
        amt_frm.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=2)
        self._elim_amount_var = tk.StringVar()
        self._elim_amount_entry = ttk.Entry(amt_frm, textvariable=self._elim_amount_var, width=18)
        self._elim_amount_entry.pack(side="left")
        self._elim_amount_entry.bind("<Return>", lambda _e: self._on_draft_add_line())
        ttk.Label(amt_frm, text="(positiv = debet, negativ = kredit)", foreground="#888888").pack(
            side="left", padx=(8, 0),
        )

        # Linjebeskrivelse
        ttk.Label(form, text="Linjebeskrivelse:").grid(row=3, column=0, sticky="w", pady=2)
        self._elim_line_desc_var = tk.StringVar()
        desc_entry = ttk.Entry(form, textvariable=self._elim_line_desc_var, width=40)
        desc_entry.grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=2)
        desc_entry.bind("<Return>", lambda _e: self._on_draft_add_line())

        # Knapper
        btn_frm = ttk.Frame(form)
        btn_frm.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btn_frm, text="Legg til linje", command=self._on_draft_add_line).pack(
            side="left",
        )
        ttk.Button(btn_frm, text="Rediger valgt", command=self._on_draft_edit_line).pack(
            side="left", padx=(4, 0),
        )
        ttk.Button(btn_frm, text="Fjern valgt linje", command=self._on_draft_remove_line).pack(
            side="left", padx=(4, 0),
        )
        # --- Utkast-tre (debet/kredit-kolonner) ---
        draft_frm = ttk.Frame(parent)
        draft_frm.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 2))
        draft_frm.columnconfigure(0, weight=1)
        draft_frm.rowconfigure(0, weight=1)

        draft_cols = ("regnr", "regnskapslinje", "debet", "kredit", "desc")
        tree_d = ttk.Treeview(draft_frm, columns=draft_cols, show="headings", height=5)
        tree_d.heading("regnr", text="Regnr")
        tree_d.heading("regnskapslinje", text="Regnskapslinje")
        tree_d.heading("debet", text="Debet")
        tree_d.heading("kredit", text="Kredit")
        tree_d.heading("desc", text="Beskrivelse")
        tree_d.column("regnr", width=60, anchor="e")
        tree_d.column("regnskapslinje", width=200)
        tree_d.column("debet", width=100, anchor="e")
        tree_d.column("kredit", width=100, anchor="e")
        tree_d.column("desc", width=180)
        tree_d.bind("<Delete>", lambda _e: self._on_draft_remove_line())
        tree_d.bind("<Double-1>", lambda _e: self._on_draft_edit_line())
        tree_d.grid(row=0, column=0, sticky="nsew")
        sb_d = ttk.Scrollbar(draft_frm, orient="vertical", command=tree_d.yview)
        tree_d.configure(yscrollcommand=sb_d.set)
        sb_d.grid(row=0, column=1, sticky="ns")
        self._tree_draft_lines = tree_d
        self._draft_tree_mgr = ManagedTreeview(
            tree_d,
            view_id="draft_lines",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
                ColumnSpec("regnskapslinje", "Regnskapslinje", width=200, stretch=True),
                ColumnSpec("debet", "Debet", width=100, anchor="e"),
                ColumnSpec("kredit", "Kredit", width=100, anchor="e"),
                ColumnSpec("desc", "Beskrivelse", width=180, stretch=True),
            ],
        )
        self._draft_col_mgr = self._draft_tree_mgr.column_manager
        self._draft_lines: list[dict] = []  # {regnr, name, amount, desc}
        self._draft_edit_idx: int | None = None  # index being edited

        # --- Kontrollsummer ---
        ctrl_frm = ttk.Frame(parent)
        ctrl_frm.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 2))

        self._elim_ctrl_var = tk.StringVar(value="")
        ttk.Label(ctrl_frm, textvariable=self._elim_ctrl_var, foreground="#444444").pack(
            side="left",
        )

        self._elim_create_hint_var = tk.StringVar(value="Legg til minst 2 linjer")
        ttk.Label(ctrl_frm, textvariable=self._elim_create_hint_var, foreground="#888888").pack(
            side="right",
        )

        # === Aktive elimineringer ===
        ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=4, pady=4)

        elim_frm = ttk.Frame(parent)
        elim_frm.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        elim_frm.columnconfigure(0, weight=1)
        elim_frm.rowconfigure(1, weight=1)
        elim_frm.rowconfigure(3, weight=1)

        bar = ttk.Frame(elim_frm)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Lagrede bilag").pack(side="left")
        ttk.Button(bar, text="Slett valgt", command=self._on_delete_simple_elim).pack(
            side="right",
        )
        ttk.Button(bar, text="Kopier til utkast", command=self._on_copy_journal_to_draft).pack(
            side="right", padx=(0, 4),
        )
        ttk.Button(bar, text="Last i utkast", command=self._on_load_journal_to_draft).pack(
            side="right", padx=(0, 4),
        )

        cols_e = ("voucher", "lines", "debet", "kredit", "diff", "status")
        tree_e = ttk.Treeview(elim_frm, columns=cols_e, show="headings", height=4)
        tree_e.heading("voucher", text="Bilag")
        tree_e.heading("lines", text="Linjer")
        tree_e.heading("debet", text="Debet")
        tree_e.heading("kredit", text="Kredit")
        tree_e.heading("diff", text="Diff")
        tree_e.heading("status", text="Status")
        tree_e.column("voucher", width=110)
        tree_e.column("lines", width=60, anchor="e")
        tree_e.column("debet", width=95, anchor="e")
        tree_e.column("kredit", width=95, anchor="e")
        tree_e.column("diff", width=95, anchor="e")
        tree_e.column("status", width=80, anchor="center")
        tree_e.tag_configure("balanced", background="#E2F1EB")
        tree_e.tag_configure("unbalanced", background="#FCEBD9")
        tree_e.grid(row=1, column=0, sticky="nsew")
        tree_e.bind("<Delete>", lambda _e: self._on_delete_simple_elim())
        tree_e.bind("<<TreeviewSelect>>", self._on_simple_elim_selected)
        self._tree_simple_elims = tree_e
        self._simple_elims_tree_mgr = ManagedTreeview(
            tree_e,
            view_id="simple_elims",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("voucher", "Bilag", width=110, pinned=True),
                ColumnSpec("lines", "Linjer", width=60, anchor="e"),
                ColumnSpec("debet", "Debet", width=95, anchor="e"),
                ColumnSpec("kredit", "Kredit", width=95, anchor="e"),
                ColumnSpec("diff", "Diff", width=95, anchor="e"),
                ColumnSpec("status", "Status", width=80, anchor="center"),
            ],
        )
        self._simple_elims_col_mgr = self._simple_elims_tree_mgr.column_manager

        sb = ttk.Scrollbar(elim_frm, orient="vertical", command=tree_e.yview)
        tree_e.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns")

        # --- Detalj: linjer for valgt journal ---
        detail_cols = ("regnr", "regnskapslinje", "debet", "kredit", "desc")
        tree_det = ttk.Treeview(elim_frm, columns=detail_cols, show="headings", height=4)
        tree_det.heading("regnr", text="Regnr")
        tree_det.heading("regnskapslinje", text="Regnskapslinje")
        tree_det.heading("debet", text="Debet")
        tree_det.heading("kredit", text="Kredit")
        tree_det.heading("desc", text="Beskrivelse")
        tree_det.column("regnr", width=60, anchor="e")
        tree_det.column("regnskapslinje", width=180)
        tree_det.column("debet", width=90, anchor="e")
        tree_det.column("kredit", width=90, anchor="e")
        tree_det.column("desc", width=140)
        tree_det.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
        sb_det = ttk.Scrollbar(elim_frm, orient="vertical", command=tree_det.yview)
        tree_det.configure(yscrollcommand=sb_det.set)
        sb_det.grid(row=3, column=1, sticky="ns", pady=(2, 0))
        self._tree_elim_detail = tree_det
        self._elim_detail_tree_mgr = ManagedTreeview(
            tree_det,
            view_id="elim_detail",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
                ColumnSpec("regnskapslinje", "Regnskapslinje", width=180, stretch=True),
                ColumnSpec("debet", "Debet", width=90, anchor="e"),
                ColumnSpec("kredit", "Kredit", width=90, anchor="e"),
                ColumnSpec("desc", "Beskrivelse", width=140, stretch=True),
            ],
        )
        self._elim_detail_col_mgr = self._elim_detail_tree_mgr.column_manager

    def _build_forslag_tab(self, parent: ttk.Frame) -> None:
        """Forslag-arbeidsflate: slank kandidatliste + grunnlagspanel."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(3, weight=1)

        # --- Toolbar ---
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(top, text="Generer forslag", command=self._on_generate_suggestions).pack(side="left")
        ttk.Button(top, text="Opprett journal", command=self._on_create_journal_from_suggestion).pack(
            side="left", padx=(4, 0),
        )
        ttk.Button(top, text="Ignorer", command=self._on_ignore_suggestion).pack(
            side="left", padx=(4, 0),
        )

        # --- Filterrad ---
        filter_frm = ttk.Frame(parent)
        filter_frm.grid(row=0, column=0, sticky="e", padx=4, pady=4)
        # Plasser filterraden i toppen paa hoeyresiden
        filter_frm.lift()

        # Vis alle selskapspar (P1)
        self._show_all_pairs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="Vis alle selskapspar",
            variable=self._show_all_pairs_var,
            command=self._refresh_suggestion_tree,
        ).pack(side="left", padx=(12, 0))

        # Typefilter: default = Mellomvaerende + Renter (P3)
        self._sug_type_interco_var = tk.BooleanVar(value=True)
        self._sug_type_renter_var = tk.BooleanVar(value=True)
        self._sug_type_bidrag_var = tk.BooleanVar(value=False)
        self._sug_type_invest_var = tk.BooleanVar(value=False)

        type_frm = ttk.Frame(parent)
        type_frm.grid(row=0, column=0, sticky="ew", padx=4, pady=(28, 0))
        ttk.Checkbutton(
            type_frm, text="Mellomvaerende",
            variable=self._sug_type_interco_var,
            command=self._refresh_suggestion_tree,
        ).pack(side="left")
        ttk.Checkbutton(
            type_frm, text="Renter",
            variable=self._sug_type_renter_var,
            command=self._refresh_suggestion_tree,
        ).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            type_frm, text="Bidrag/Utbytte",
            variable=self._sug_type_bidrag_var,
            command=self._refresh_suggestion_tree,
        ).pack(side="left", padx=(6, 0))
        ttk.Checkbutton(
            type_frm, text="Investering/EK",
            variable=self._sug_type_invest_var,
            command=self._refresh_suggestion_tree,
        ).pack(side="left", padx=(6, 0))

        self._suggestion_count_var = tk.StringVar(value="")
        ttk.Label(type_frm, textvariable=self._suggestion_count_var).pack(side="right")

        # --- Kandidat-treeview (P4: slank visning) ---
        # Kolonnene: Type | Motpart | Linje mor | Linje motpart | Mor | Motpart | Diff | Status
        cols_s = ("kind", "counterparty", "line_a", "line_b",
                  "amount_a", "amount_b", "diff", "status")
        tree_s = ttk.Treeview(parent, columns=cols_s, show="headings", height=8)
        tree_s.heading("kind", text="Type")
        tree_s.heading("counterparty", text="Motpart")
        tree_s.heading("line_a", text="Linje mor")
        tree_s.heading("line_b", text="Linje motpart")
        tree_s.heading("amount_a", text="Mor")
        tree_s.heading("amount_b", text="Motpart")
        tree_s.heading("diff", text="Diff")
        tree_s.heading("status", text="Status")
        tree_s.column("kind", width=90)
        tree_s.column("counterparty", width=110)
        tree_s.column("line_a", width=120)
        tree_s.column("line_b", width=120)
        tree_s.column("amount_a", width=90, anchor="e")
        tree_s.column("amount_b", width=90, anchor="e")
        tree_s.column("diff", width=80, anchor="e")
        tree_s.column("status", width=70)
        tree_s.tag_configure("ny", background="#FFFFFF")
        tree_s.tag_configure("ignorert", background="#F0F0F0", foreground="#888888")
        tree_s.tag_configure("journalfoert", background="#E2F1EB")
        tree_s.tag_configure("diff_warning", foreground="#CC6600")
        tree_s.grid(row=2, column=0, sticky="nsew", padx=4)
        tree_s.bind("<<TreeviewSelect>>", self._on_suggestion_select)
        self._tree_suggestions = tree_s
        self._suggestions_tree_mgr = ManagedTreeview(
            tree_s,
            view_id="suggestions",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("kind", "Type", width=90, pinned=True),
                ColumnSpec("counterparty", "Motpart", width=110, stretch=True),
                ColumnSpec("line_a", "Linje mor", width=120, stretch=True),
                ColumnSpec("line_b", "Linje motpart", width=120, stretch=True),
                ColumnSpec("amount_a", "Mor", width=90, anchor="e"),
                ColumnSpec("amount_b", "Motpart", width=90, anchor="e"),
                ColumnSpec("diff", "Diff", width=80, anchor="e"),
                ColumnSpec("status", "Status", width=70),
            ],
        )
        self._suggestions_col_mgr = self._suggestions_tree_mgr.column_manager

        # --- Separator ---
        ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=4, pady=4)

        # --- Grunnlagspanel ---
        detail_frm = ttk.Frame(parent)
        detail_frm.grid(row=4, column=0, sticky="nsew", padx=4)
        detail_frm.columnconfigure(0, weight=1)
        detail_frm.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=2)
        parent.rowconfigure(4, weight=1)

        self._suggestion_detail_var = tk.StringVar(value="Ingen forslag generert.")
        ttk.Label(detail_frm, textvariable=self._suggestion_detail_var, anchor="w").grid(
            row=0, column=0, sticky="ew",
        )

        cols_d = ("regnr", "company", "amount", "desc")
        tree_d = ttk.Treeview(detail_frm, columns=cols_d, show="headings", height=4)
        tree_d.heading("regnr", text="Regnr")
        tree_d.heading("company", text="Selskap")
        tree_d.heading("amount", text="Beloep")
        tree_d.heading("desc", text="Beskrivelse")
        tree_d.column("regnr", width=60, anchor="e")
        tree_d.column("company", width=120)
        tree_d.column("amount", width=100, anchor="e")
        tree_d.column("desc", width=200)
        tree_d.grid(row=1, column=0, sticky="nsew")
        self._tree_suggestion_detail = tree_d
        self._sug_detail_tree_mgr = ManagedTreeview(
            tree_d,
            view_id="suggestion_det",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
                ColumnSpec("company", "Selskap", width=120, stretch=True),
                ColumnSpec("amount", "Beløp", width=100, anchor="e"),
                ColumnSpec("desc", "Beskrivelse", width=200, stretch=True),
            ],
        )
        self._sug_detail_col_mgr = self._sug_detail_tree_mgr.column_manager

    def _build_journaler_tab(self, parent: ttk.Frame) -> None:
        """Journaler-fane: manuell + forslagsgenererte journaler."""
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=4)
        ttk.Button(top, text="Nytt bilag", command=self._on_new_journal).pack(side="left")
        ttk.Button(top, text="Slett bilag", command=self._on_delete_journal).pack(side="left", padx=(4, 0))

        cols_j = ("voucher", "kind", "lines", "balance")
        self._tree_journals = ttk.Treeview(parent, columns=cols_j, show="headings", height=6)
        self._tree_journals.heading("voucher", text="Bilag")
        self._tree_journals.heading("kind", text="Type")
        self._tree_journals.heading("lines", text="Linjer")
        self._tree_journals.heading("balance", text="Balanse")
        self._tree_journals.column("voucher", width=130)
        self._tree_journals.column("kind", width=70)
        self._tree_journals.column("lines", width=50, anchor="e")
        self._tree_journals.column("balance", width=90)
        self._tree_journals.tag_configure("warning", background="#FCEBD9")
        self._tree_journals.tag_configure("done", background="#E2F1EB")
        self._tree_journals.tag_configure("template", background="#FFF8E1")
        self._tree_journals.pack(fill="x", padx=4)
        self._tree_journals.bind("<<TreeviewSelect>>", self._on_journal_select)
        self._tree_journals.bind("<Delete>", lambda e: self._on_delete_journal())
        self._journals_tree_mgr = ManagedTreeview(
            self._tree_journals,
            view_id="journals",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("voucher", "Bilag", width=130, pinned=True, stretch=True),
                ColumnSpec("kind", "Type", width=70),
                ColumnSpec("lines", "Linjer", width=50, anchor="e"),
                ColumnSpec("balance", "Balanse", width=90),
            ],
        )
        self._journals_col_mgr = self._journals_tree_mgr.column_manager

        sep = ttk.Separator(parent, orient="horizontal")
        sep.pack(fill="x", padx=4, pady=4)

        line_bar = ttk.Frame(parent)
        line_bar.pack(fill="x", padx=4)
        ttk.Button(line_bar, text="Legg til linje", command=self._on_add_elim_line).pack(side="left")
        ttk.Button(line_bar, text="Slett linje", command=self._on_delete_elim_line).pack(side="left", padx=(4, 0))

        self._elim_balance_var = tk.StringVar(value="")
        ttk.Label(line_bar, textvariable=self._elim_balance_var).pack(side="right")

        cols_l = ("regnr", "company", "amount", "desc")
        self._tree_elim_lines = ttk.Treeview(parent, columns=cols_l, show="headings")
        self._tree_elim_lines.heading("regnr", text="Regnr")
        self._tree_elim_lines.heading("company", text="Selskap")
        self._tree_elim_lines.heading("amount", text="Beloep")
        self._tree_elim_lines.heading("desc", text="Beskrivelse")
        self._tree_elim_lines.column("regnr", width=60, anchor="e")
        self._tree_elim_lines.column("company", width=120)
        self._tree_elim_lines.column("amount", width=100, anchor="e")
        self._tree_elim_lines.column("desc", width=160)
        self._tree_elim_lines.pack(fill="both", expand=True, padx=4, pady=(4, 0))
        self._tree_elim_lines.bind("<Delete>", lambda e: self._on_delete_elim_line())
        self._elim_lines_tree_mgr = ManagedTreeview(
            self._tree_elim_lines,
            view_id="elim_lines",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
                ColumnSpec("company", "Selskap", width=120, stretch=True),
                ColumnSpec("amount", "Beløp", width=100, anchor="e"),
                ColumnSpec("desc", "Beskrivelse", width=160, stretch=True),
            ],
        )
        self._elim_lines_col_mgr = self._elim_lines_tree_mgr.column_manager

    def _build_valuta_tab(self, parent: ttk.Frame) -> None:
        """Valuta-fane: kurser per selskap og prosjektdefaults."""
        parent.columnconfigure(1, weight=1)

        # Prosjekt-defaults
        lbl_frm = ttk.LabelFrame(parent, text="Prosjektinnstillinger", padding=8)
        lbl_frm.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        lbl_frm.columnconfigure(1, weight=1)

        ttk.Label(lbl_frm, text="Rapporteringsvaluta:").grid(row=0, column=0, sticky="w", pady=2)
        self._fx_reporting_var = tk.StringVar(value="NOK")
        ttk.Entry(lbl_frm, textvariable=self._fx_reporting_var, width=6).grid(
            row=0, column=1, sticky="w", padx=(4, 0),
        )

        ttk.Label(lbl_frm, text="Match-toleranse (NOK):").grid(row=1, column=0, sticky="w", pady=2)
        self._fx_tolerance_var = tk.StringVar(value="1000")
        ttk.Entry(lbl_frm, textvariable=self._fx_tolerance_var, width=10).grid(
            row=1, column=1, sticky="w", padx=(4, 0),
        )

        ttk.Button(lbl_frm, text="Lagre", command=self._on_save_fx_settings).grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(8, 0),
        )

        # Selskapsvaluta-tabell
        frm_rates = ttk.LabelFrame(parent, text="Valutakurser per selskap", padding=8)
        frm_rates.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=4, pady=4)
        frm_rates.columnconfigure(0, weight=1)
        frm_rates.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        cols_fx = ("company", "currency", "closing_rate", "average_rate")
        tree_fx = ttk.Treeview(frm_rates, columns=cols_fx, show="headings", height=6)
        tree_fx.heading("company", text="Selskap")
        tree_fx.heading("currency", text="Valuta")
        tree_fx.heading("closing_rate", text="Sluttkurs")
        tree_fx.heading("average_rate", text="Snittkurs")
        tree_fx.column("company", width=140)
        tree_fx.column("currency", width=60)
        tree_fx.column("closing_rate", width=80, anchor="e")
        tree_fx.column("average_rate", width=80, anchor="e")
        tree_fx.grid(row=0, column=0, sticky="nsew")
        self._tree_fx_rates = tree_fx
        fx_cols = ("company", "currency", "closing_rate", "average_rate")
        self._fx_tree_mgr = ManagedTreeview(
            tree_fx,
            view_id="fx_rates",
            pref_prefix="ui",
            column_specs=[
                ColumnSpec("company", "Selskap", width=140, pinned=True, stretch=True),
                ColumnSpec("currency", "Valuta", width=60),
                ColumnSpec("closing_rate", "Sluttkurs", width=80, anchor="e"),
                ColumnSpec("average_rate", "Snittkurs", width=80, anchor="e"),
            ],
        )
        self._fx_col_mgr = self._fx_tree_mgr.column_manager

        btn_frm = ttk.Frame(frm_rates)
        btn_frm.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(btn_frm, text="Rediger valuta...", command=self._on_edit_fx_rate).pack(side="left")

    # ------------------------------------------------------------------
    # Session / project loading
    # ------------------------------------------------------------------

    def refresh_from_session(self, sess: object) -> None:
        if not self._tk_ok or self._status_var is None:
            return

        client = str(getattr(sess, "client", "") or "").strip()
        year = str(getattr(sess, "year", "") or "").strip()

        # Alltid rydd run-cache ved sesjonsskifte
        self._invalidate_run_cache()
        self._current_detail_cid = None
        self._show_empty_result("Kjør konsolidering for å vise resultat")

        if not client or not year:
            self._status_var.set("Velg klient og aar for aa starte.")
            self._project = None
            self._update_session_tb_button(sess)
            self._refresh_readiness()
            return

        self._lbl_statusbar.configure(text=f"Konsolidering | {client} / {year} | TB-only")

        proj = storage.load_project(client, year)
        if proj is not None:
            self._project = proj
            self._load_company_tbs()
            self._compute_mapping_status()
            self._refresh_company_tree()
            self._refresh_simple_elim_tree()
            self._refresh_journal_tree()
            self._begin_new_elim_draft()
            self._refresh_fx_tree()
            self._update_status()
        else:
            self._project = None
            self._company_tbs.clear()
            self._mapped_tbs.clear()
            self._suggestions.clear()
            self._tree_companies.delete(*self._tree_companies.get_children())
            self._tree_journals.delete(*self._tree_journals.get_children())
            self._tree_elim_lines.delete(*self._tree_elim_lines.get_children())
            self._tree_suggestions.delete(*self._tree_suggestions.get_children())
            self._tree_fx_rates.delete(*self._tree_fx_rates.get_children())
            if hasattr(self, "_tree_simple_elims"):
                self._tree_simple_elims.delete(*self._tree_simple_elims.get_children())
            if hasattr(self, "_tree_elim_detail"):
                self._tree_elim_detail.delete(*self._tree_elim_detail.get_children())
            if hasattr(self, "_tree_draft_lines"):
                self._begin_new_elim_draft()
            self._status_var.set(
                f"{client} / {year} — ingen konsolideringsprosjekt. "
                "Importer et selskap for aa starte."
            )

        if self._project is None:
            self._refresh_readiness()
        self._update_session_tb_button(sess)

    def _ensure_project(self) -> ConsolidationProject:
        if self._project is not None:
            return self._project

        client = str(getattr(session, "client", "") or "").strip()
        year = str(getattr(session, "year", "") or "").strip()
        if not client or not year:
            raise RuntimeError("Klient/aar er ikke valgt.")

        self._project = ConsolidationProject(client=client, year=year)
        storage.save_project(self._project)
        return self._project

    def _update_session_tb_button(self, sess: object) -> None:
        """Show/hide 'Bruk aktiv klient som mor' based on data availability."""
        has_data = self._resolve_active_client_tb() is not None

        # Skjul hvis aktiv klient allerede er morselskap i prosjektet
        already_parent = False
        if has_data and self._project is not None:
            parent_id = self._project.parent_company_id
            if parent_id:
                for c in self._project.companies:
                    if c.company_id == parent_id and c.source_type in ("session", "session-sb"):
                        already_parent = True
                        break

        if has_data and not already_parent:
            self._btn_use_session_tb.pack(side="left", padx=(0, 4), before=self._btn_run)
        else:
            self._btn_use_session_tb.pack_forget()

    def _resolve_active_client_tb(self) -> Optional[tuple[pd.DataFrame, str, str]]:
        """Finn TB-data for aktiv klient.

        Returnerer (tb_df, klientnavn, source_type) eller None.
        Prioritet: 1) session.tb_df, 2) SB-versjon i client_store.
        """
        client = str(getattr(session, "client", "") or "").strip()
        year = str(getattr(session, "year", "") or "").strip()
        if not client:
            return None

        # 1. Session TB (bruker har valgt SB-versjon)
        tb = getattr(session, "tb_df", None)
        if tb is not None and isinstance(tb, pd.DataFrame) and not tb.empty:
            return tb, client, "session"

        # 2. Hent SB-versjon fra client_store (auto-opprettet fra SAF-T)
        if year:
            try:
                import client_store
                versions = client_store.list_versions(client, year=year, dtype="sb")
                if versions:
                    from trial_balance_reader import read_trial_balance
                    v = versions[0]  # nyeste SB-versjon
                    sb_df = read_trial_balance(v.path)
                    return sb_df, client, "session-sb"
            except Exception:
                logger.debug("Could not load SB from client_store", exc_info=True)

        return None

    def _on_use_session_tb(self) -> None:
        """Importer/oppdater aktiv klient som morselskap (upsert)."""
        resolved = self._resolve_active_client_tb()
        if resolved is None:
            messagebox.showinfo(
                "Morselskap",
                "Ingen aktiv saldobalanse funnet.\n\n"
                "Last inn SAF-T eller velg SB-versjon for aktiv klient foerst.",
            )
            return

        tb, client_name, source_type = resolved

        proj = self._ensure_project()

        # --- Upsert: finn eksisterende morselskap eller session-selskap ---
        existing = None
        # 1) Eksisterende parent
        if proj.parent_company_id:
            for c in proj.companies:
                if c.company_id == proj.parent_company_id:
                    existing = c
                    break
        # 2) Selskap med session/session-sb source_type
        if existing is None:
            for c in proj.companies:
                if c.source_type in ("session", "session-sb"):
                    existing = c
                    break

        if existing is not None:
            default_name = existing.name
        else:
            default_name = client_name

        name = simpledialog.askstring(
            "Selskapsnavn (morselskap)",
            "Skriv inn selskapsnavn for morselskapet:",
            initialvalue=default_name,
        )
        if not name:
            return

        # Normaliser til kanonisk TB-format
        from consolidation.tb_import import _normalize_columns, validate_tb
        tb = _normalize_columns(tb.copy())
        warnings = validate_tb(tb)

        has_ib = bool((tb["ib"].abs() > 0.005).any()) if "ib" in tb.columns else False

        if existing is not None:
            # Oppdater eksisterende selskap in-place
            existing.name = name
            existing.source_type = source_type
            existing.source_file = "aktiv klient" if source_type == "session" else "SAF-T SB"
            existing.row_count = len(tb)
            existing.has_ib = has_ib
            cid = existing.company_id
        else:
            # Nytt selskap
            company = CompanyTB(
                name=name,
                source_type=source_type,
                source_file="aktiv klient" if source_type == "session" else "SAF-T SB",
                row_count=len(tb),
                has_ib=has_ib,
            )
            proj.companies.append(company)
            cid = company.company_id

        proj.parent_company_id = cid
        self._company_tbs[cid] = tb
        storage.save_company_tb(proj.client, proj.year, cid, tb)
        storage.save_project(proj)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._update_status()
        self._select_and_show_company(cid)

        # Hide the button now
        self._btn_use_session_tb.pack_forget()

        if warnings:
            messagebox.showwarning("Import-advarsler", "\n".join(warnings))

    def _load_company_tbs(self) -> None:
        self._company_tbs.clear()
        if self._project is None:
            return
        from consolidation.tb_import import _normalize_columns
        for c in self._project.companies:
            tb = storage.load_company_tb(
                self._project.client, self._project.year, c.company_id,
            )
            if tb is not None:
                # Re-normaliserer lagrede TBer slik at UB deriveres fra
                # netto for eldre snapshots der UB=0 (fiks for kun-netto-data).
                tb = _normalize_columns(tb)
                self._company_tbs[c.company_id] = tb

    # ------------------------------------------------------------------
    # Mapping status
    # ------------------------------------------------------------------

    def _load_analyse_parent_overrides(self) -> dict[str, int]:
        """Hent persisted Analyse-overstyringer for morselskapet."""
        if self._project is None:
            return {}
        try:
            import regnskap_client_overrides
            return regnskap_client_overrides.load_account_overrides(
                self._project.client, year=self._project.year,
            )
        except Exception:
            return {}

    def _get_parent_override_deviation_details(self) -> list[str]:
        """Beskriv lokale parent-overstyringer som avviker fra Analyse."""
        if self._project is None:
            return []
        parent_id = self._project.parent_company_id or ""
        if not parent_id:
            return []
        analyse = self._load_analyse_parent_overrides()
        local_parent = self._project.mapping_config.company_overrides.get(parent_id, {}) or {}
        details: list[str] = []
        for konto, local_regnr in sorted(local_parent.items(), key=lambda item: str(item[0])):
            analyse_regnr = analyse.get(str(konto))
            if analyse_regnr == local_regnr:
                continue
            analyse_label = str(analyse_regnr) if analyse_regnr is not None else "Analyse: ingen"
            details.append(f"{konto}: {analyse_label} / Konsolidering {local_regnr}")
        return details

    def _get_effective_company_overrides(self, company_id: str) -> dict[str, int]:
        """Hent effektive overstyringer for et selskap.

        Mor bruker Analyse som kilde til sannhet.
        Doetre bruker lokale konsoliderings-overstyringer.
        Eventuelle lokale parent-overstyringer flagges separat som avvik.
        """
        if self._project is None:
            return {}

        if company_id == self._project.parent_company_id:
            return dict(self._load_analyse_parent_overrides())

        return dict(self._project.mapping_config.company_overrides.get(company_id, {}))
    def _get_effective_company_tb(self, company_id: str) -> pd.DataFrame | None:
        """Hent TB for selskap, med AO-justeringer for parent naar aktiv."""
        tb = self._company_tbs.get(company_id)
        if tb is None or self._project is None:
            return tb

        if not self._include_ao_var.get():
            return tb
        if company_id != self._project.parent_company_id:
            return tb

        try:
            import regnskap_client_overrides
            import tilleggsposteringer

            ao_entries = regnskap_client_overrides.load_supplementary_entries(
                self._project.client, self._project.year,
            )
            if not ao_entries:
                return tb
            adjusted = tilleggsposteringer.apply_to_sb(tb.copy(), ao_entries)
            logger.info("Applied %d AO entries to parent %s", len(ao_entries), company_id)
            return adjusted
        except Exception:
            logger.exception("Failed to apply AO entries for %s", company_id)
            return tb

    def _get_effective_tbs(self) -> dict[str, pd.DataFrame]:
        """Hent alle TBer med AO-justeringer der relevant."""
        result = {}
        for cid, tb in self._company_tbs.items():
            eff = self._get_effective_company_tb(cid)
            if eff is not None:
                result[cid] = eff
        return result

    def _compute_mapping_status(self) -> None:
        """Beregn mapping-status per selskap (proesentandel mappede kontoer)."""
        if not hasattr(self, "_mapping_review_accounts") or self._mapping_review_accounts is None:
            self._mapping_review_accounts = {}
        if not hasattr(self, "_mapping_review_details") or self._mapping_review_details is None:
            self._mapping_review_details = {}
        if not hasattr(self, "_mapping_unmapped") or self._mapping_unmapped is None:
            self._mapping_unmapped = {}
        if not hasattr(self, "_mapping_pct") or self._mapping_pct is None:
            self._mapping_pct = {}
        if not hasattr(self, "_mapped_tbs") or self._mapped_tbs is None:
            self._mapped_tbs = {}
        self._mapped_tbs.clear()
        self._mapping_pct: dict[str, int] = {}
        self._mapping_unmapped: dict[str, list[str]] = {}
        self._mapping_review_accounts.clear()
        self._mapping_review_details.clear()
        self._parent_mapping_deviation_details = []

        if self._project is None:
            return

        try:
            from consolidation.mapping import map_company_tb, load_shared_config
            intervals, regnskapslinjer = load_shared_config()
            self._intervals = intervals
            self._regnskapslinjer = regnskapslinjer
            self._regnr_to_name = {
                int(row["regnr"]): str(row.get("regnskapslinje", ""))
                for _, row in regnskapslinjer.iterrows()
            }
        except Exception:
            # Config mangler — alle selskaper faar "—"
            for c in self._project.companies:
                self._mapping_pct[c.company_id] = -1
            return

        self._parent_mapping_deviation_details = self._get_parent_override_deviation_details()

        for c in self._project.companies:
            tb = self._get_effective_company_tb(c.company_id)
            if tb is None or tb.empty:
                self._mapping_pct[c.company_id] = -1
                continue
            overrides = self._get_effective_company_overrides(c.company_id)
            try:
                mapped_df, unmapped = map_company_tb(
                    tb, overrides, intervals=intervals, regnskapslinjer=regnskapslinjer,
                )
                self._mapped_tbs[c.company_id] = mapped_df
                self._mapping_unmapped[c.company_id] = unmapped
                review_accounts, review_details = _detect_mapping_review_accounts(
                    mapped_df, self._regnr_to_name,
                )
                self._mapping_review_accounts[c.company_id] = review_accounts
                self._mapping_review_details[c.company_id] = review_details
                if "konto" in mapped_df.columns:
                    konto_series = mapped_df["konto"].astype(str).str.strip()
                    total = int(konto_series.replace("", pd.NA).dropna().nunique())
                    ok_kontos = set(
                        konto_series.loc[mapped_df["regnr"].notna()].replace("", pd.NA).dropna().tolist(),
                    )
                    if review_accounts:
                        ok_kontos -= set(review_accounts)
                    mapped_count = len(ok_kontos)
                else:
                    total = len(mapped_df)
                    ok_mask = mapped_df["regnr"].notna()
                    mapped_count = int(ok_mask.sum()) if total > 0 else 0
                self._mapping_pct[c.company_id] = int(mapped_count * 100 / total) if total > 0 else 0
            except Exception:
                self._mapping_pct[c.company_id] = -1

        # Oppdater enkel eliminering-UI
        if self._tk_ok and hasattr(self, "_elim_cb_rl"):
            self._populate_elim_combos()
            self._refresh_simple_elim_tree()
        try:
            self._refresh_readiness()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        if self._project is None:
            try:
                self._refresh_readiness()
            except Exception:
                pass
            return
        nc = len(self._project.companies)
        ne = len(self._project.eliminations)
        last_run = ""
        if self._project.runs:
            from datetime import datetime
            r = self._project.runs[-1]
            last_run = f" | Siste run: {datetime.fromtimestamp(r.run_at).strftime('%H:%M')}"
        self._status_var.set(f"{nc} selskaper | {ne} elimineringer{last_run}")
        try:
            self._refresh_readiness()
        except Exception:
            pass

    def _split_unmapped_counts(self, company_id: str) -> tuple[int, int]:
        """Del umappede kontoer i kontoer med verdi og rene 0-linjer."""
        missing = {
            str(k).strip()
            for k in self._mapping_unmapped.get(company_id, []) or []
            if str(k).strip()
        }
        if not missing:
            return 0, 0

        tb = self._get_effective_company_tb(company_id)
        if tb is None or tb.empty or "konto" not in tb.columns:
            return len(missing), 0

        value_cols = [col for col in ("ib", "netto", "ub") if col in tb.columns]
        if not value_cols:
            return len(missing), 0

        has_value: dict[str, bool] = {konto: False for konto in missing}
        for _, row in tb.iterrows():
            konto = str(row.get("konto", "") or "").strip()
            if konto not in has_value:
                continue
            valued = False
            for col in value_cols:
                try:
                    if abs(float(row.get(col, 0) or 0)) > 0.005:
                        valued = True
                        break
                except (ValueError, TypeError):
                    continue
            if valued:
                has_value[konto] = True

        valued_count = sum(1 for flagged in has_value.values() if flagged)
        zero_count = len(has_value) - valued_count
        return valued_count, zero_count

    def _refresh_readiness(self) -> None:
        try:
            import consolidation_readiness

            report = consolidation_readiness.build_readiness_report(self)
            self._readiness_report = report
            self._readiness_status_var.set(consolidation_readiness.summarize_report(report))
            summary_var = getattr(self, "_readiness_summary_var", None)
            if summary_var is not None:
                if report.issues:
                    summary_var.set(f"{report.blockers} blokkere | {report.warnings} advarsler | {report.infos} info")
                else:
                    summary_var.set("Ingen kontroller avdekket avvik.")
            self._refresh_controls_tree()
        except Exception:
            self._readiness_report = None
            try:
                self._readiness_status_var.set("")
            except Exception:
                pass

    def _refresh_controls_tree(self) -> None:
        tree = getattr(self, "_tree_controls", None)
        if tree is None:
            return
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())
        report = getattr(self, "_readiness_report", None)
        issue_map: dict[str, object] = {}
        if report is None:
            self._readiness_issue_map = issue_map
            return
        for idx, issue in enumerate(getattr(report, "issues", []) or []):
            iid = f"issue:{idx}"
            issue_map[iid] = issue
            values = (
                getattr(issue, "severity", ""),
                getattr(issue, "category", ""),
                getattr(issue, "company_name", "") or getattr(issue, "company_id", "") or "Globalt",
                getattr(issue, "message", ""),
                getattr(issue, "action", ""),
            )
            tags = (str(getattr(issue, "severity", "") or ""),)
            tree.insert("", "end", iid=iid, values=values, tags=tags)
        self._readiness_issue_map = issue_map

    def _open_selected_readiness_issue(self) -> None:
        tree = getattr(self, "_tree_controls", None)
        if tree is None:
            return
        try:
            selection = list(tree.selection())
        except Exception:
            selection = []
        if not selection:
            try:
                focused = tree.focus()
            except Exception:
                focused = ""
            if focused:
                selection = [focused]
        if not selection:
            return
        issue = getattr(self, "_readiness_issue_map", {}).get(selection[0])
        if issue is None:
            return
        action = str(getattr(issue, "action", "") or "")
        company_id = str(getattr(issue, "company_id", "") or "")
        if action == "open_mapping":
            if company_id:
                self._select_and_show_company(company_id)
            self._show_company_detail(self._current_detail_cid or company_id)
            try:
                self._mapping_tab.show_unmapped()
            except Exception:
                pass
            self._select_right_tab(1, "_right_tab_mapping")
            return
        if action == "open_valuta":
            self._select_left_tab(1, "_left_tab_elim")
            try:
                self._select_elim_tab(3, "_elim_tab_fx")
            except Exception:
                pass
            if company_id:
                try:
                    self._tree_fx_rates.selection_set((company_id,))
                    self._tree_fx_rates.focus(company_id)
                    self._tree_fx_rates.see(company_id)
                except Exception:
                    pass
            return
        if action == "open_elimination":
            self._select_left_tab(1, "_left_tab_elim")
            try:
                self._select_elim_tab(1, "_elim_tab_journals")
            except Exception:
                pass
            target = str(getattr(issue, "action_target", "") or "")
            if target and getattr(self, "_tree_journals", None) is not None:
                try:
                    self._tree_journals.selection_set((target,))
                    self._tree_journals.focus(target)
                    self._tree_journals.see(target)
                    self._show_journal_lines()
                except Exception:
                    pass
            return
        if action == "open_grunnlag":
            if company_id:
                self._select_and_show_company(company_id)
            self._select_left_tab(2, "_left_tab_grunnlag")
            return
        if action == "rerun":
            try:
                self._select_right_tab(2, "_right_tab_result")
                self._rerun_consolidation()
            except Exception:
                pass
            return

    def _refresh_company_tree(self) -> None:
        tree = self._tree_companies
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())
        if self._project is None:
            return
        parent_id = self._project.parent_company_id or ""
        # Parent først, resten alfabetisk
        companies_sorted = sorted(
            self._project.companies,
            key=lambda c: (0 if c.company_id == parent_id else 1, c.name),
        )
        for c in companies_sorted:
            pct = self._mapping_pct.get(c.company_id, -1)
            unmapped_count, zero_unmapped_count = self._split_unmapped_counts(c.company_id)
            review_count = len(self._mapping_review_accounts.get(c.company_id, set()))
            if pct < 0:
                mapping_text = "\u2014"
                tag = ()
            elif pct >= 100 and unmapped_count == 0 and zero_unmapped_count == 0 and review_count == 0:
                mapping_text = "100%"
                tag = ("done",)
            elif unmapped_count > 0 or review_count > 0:
                parts: list[str] = []
                if unmapped_count > 0:
                    parts.append(f"{unmapped_count} umappet")
                if zero_unmapped_count > 0:
                    parts.append(f"{zero_unmapped_count} umappet 0-linje")
                if review_count > 0:
                    parts.append(f"{review_count} avvik")
                mapping_text = f"{pct}% ({', '.join(parts)})"
                tag = ("review",)
            elif zero_unmapped_count > 0:
                mapping_text = f"{pct}% ({zero_unmapped_count} umappet 0-linje)"
                tag = ()
            else:
                mapping_text = f"{pct}%"
                tag = ("review",) if pct < 90 else ()

            display_name = c.name
            if c.company_id == parent_id:
                display_name = f"\u2605 {c.name}"  # star marker for parent

            # Vis kildetype med IB-status
            source_label = _source_display(c.source_type, c.has_ib)

            tree.insert("", "end", iid=c.company_id, values=(
                display_name, source_label, c.row_count, mapping_text,
            ), tags=tag)

    def _refresh_journal_tree(self) -> None:
        tree = self._tree_journals
        _reset_sort_state(tree)
        _reset_sort_state(self._tree_elim_lines)
        tree.delete(*tree.get_children())
        self._tree_elim_lines.delete(*self._tree_elim_lines.get_children())
        self._elim_balance_var.set("")
        if self._project is None:
            return
        _KIND_LABELS = {
            "manual": "Manuell",
            "from_suggestion": "Forslag",
            "template": "Template",
        }
        for j in self._project.eliminations:
            if j.is_balanced:
                bal_text = "OK"
                tag = ("done",)
            else:
                bal_text = f"Ubalanse ({_fmt_no(j.net)})"
                tag = ("warning",)
            if j.kind == "template":
                tag = ("template",)
            kind_label = _KIND_LABELS.get(j.kind, j.kind)
            tree.insert("", "end", iid=j.journal_id, values=(
                j.display_label, kind_label, len(j.lines), bal_text,
            ), tags=tag)

    def _refresh_elim_lines(self, journal: EliminationJournal) -> None:
        tree = self._tree_elim_lines
        tree.delete(*tree.get_children())
        name_map = {}
        if self._project:
            name_map = {c.company_id: c.name for c in self._project.companies}
        for i, line in enumerate(journal.lines):
            tree.insert("", "end", iid=str(i), values=(
                line.regnr,
                name_map.get(line.company_id, line.company_id[:12]),
                _fmt_no(line.amount, 2),
                line.description,
            ))
        # Vis balanseindikator
        if journal.is_balanced:
            self._elim_balance_var.set("Balansert")
        else:
            self._elim_balance_var.set(f"Netto: {_fmt_no(journal.net, 2)}")

    def _show_company_detail(self, company_id: str) -> None:
        """Vis selskapets TB i Detalj-fanen (med mapping-status)."""
        self._current_detail_cid = company_id

        # Bruk mapped TB hvis tilgjengelig, ellers effective raa TB
        effective_raw = self._get_effective_company_tb(company_id)
        tb = self._mapped_tbs.get(company_id)
        if tb is None or (isinstance(tb, pd.DataFrame) and tb.empty):
            tb = effective_raw
        if tb is None:
            self._tree_detail.delete(*self._tree_detail.get_children())
            return

        # Populate mapping tab
        if self._regnskapslinjer is not None:
            overrides = self._get_effective_company_overrides(company_id)
            read_only_reason = ""
            if self._project is not None and company_id == self._project.parent_company_id:
                read_only_reason = "Mor styres fra Analyse. Endre parent-mapping i Analyse-fanen."
            self._mapping_tab.set_data(
                company_id,
                effective_raw if effective_raw is not None else tb,
                self._mapped_tbs.get(company_id),
                overrides,
                self._regnskapslinjer,
                self._regnr_to_name,
                review_accounts=self._mapping_review_accounts.get(company_id, set()),
                read_only_reason=read_only_reason,
            )

        self._populate_detail_tree(tb, company_id)

        # Also build per-company result (shown if mode == "Valgt selskap")
        self._build_company_result(company_id)
        if self._result_mode_var.get() == "Valgt selskap":
            self._refresh_result_view()

    def _populate_detail_tree(self, tb: pd.DataFrame, company_id: str) -> None:
        """Fyll detalj-treeview med TB-rader, respekter nullstøy-filter."""
        tree = self._tree_detail
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())
        unmapped = set(self._mapping_unmapped.get(company_id, []))
        review_accounts = set(self._mapping_review_accounts.get(company_id, set()))
        hide_zero = self._detail_hide_zero_var.get()
        grouped: dict[str, dict[str, object]] = {}
        for _, row in tb.iterrows():
            konto = str(row.get("konto", "") or "").strip()
            if not konto:
                continue
            kontonavn = str(row.get("kontonavn", "") or "").strip()
            regnr_raw = row.get("regnr", "")
            try:
                regnr_int = (
                    int(regnr_raw)
                    if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan")
                    else None
                )
            except (ValueError, TypeError):
                regnr_int = None

            item = grouped.setdefault(
                konto,
                {
                    "konto": konto,
                    "kontonavn": kontonavn,
                    "regnr": regnr_int,
                    "ib": 0.0,
                    "netto": 0.0,
                    "ub": 0.0,
                },
            )
            if kontonavn and not str(item.get("kontonavn", "") or "").strip():
                item["kontonavn"] = kontonavn
            if item.get("regnr") is None and regnr_int is not None:
                item["regnr"] = regnr_int
            for col in ("ib", "netto", "ub"):
                try:
                    item[col] = float(item.get(col, 0.0) or 0.0) + float(row.get(col, 0.0) or 0.0)
                except (ValueError, TypeError):
                    pass

        total = len(grouped)
        shown = 0

        for konto, row in grouped.items():
            try:
                ib = float(row.get("ib", 0) or 0)
                ub = float(row.get("ub", 0) or 0)
                netto = float(row.get("netto", 0) or 0)
            except (ValueError, TypeError):
                ib = ub = netto = 0.0

            if hide_zero and abs(ib) < 0.005 and abs(ub) < 0.005 and abs(netto) < 0.005:
                continue

            shown += 1
            regnr_int = row.get("regnr")
            regnr_display = regnr_int if regnr_int is not None else ""
            rl_navn = self._regnr_to_name.get(int(regnr_int), "") if regnr_int is not None else ""
            tag = ("review",) if konto in unmapped or konto in review_accounts else ()
            tree.insert("", "end", iid=konto, values=(
                konto,
                row.get("kontonavn", ""),
                regnr_display,
                rl_navn,
                _fmt_no(ib, 2),
                _fmt_no(netto, 2),
                _fmt_no(ub, 2),
            ), tags=tag)

        if hide_zero and total > shown:
            self._detail_count_var.set(f"{shown}/{total} kontoer (0-linjer skjult)")
        else:
            self._detail_count_var.set(f"{total} kontoer")

    def _on_detail_filter_changed(self) -> None:
        """Re-populer detalj-tree ved filterendring."""
        cid = getattr(self, "_current_detail_cid", None)
        if not cid:
            return
        tb = self._mapped_tbs.get(cid)
        if tb is None or (isinstance(tb, pd.DataFrame) and tb.empty):
            tb = self._company_tbs.get(cid)
        if tb is not None:
            self._populate_detail_tree(tb, cid)

    def _build_company_result(self, company_id: str) -> None:
        """Bygg regnskapsoppstilling for valgt selskap med alle valutakolonner.

        Kolonner: UB (etter omregning), Før, Kurs, Valutaeffekt.
        Visibility styres av checkboxes i toolbar.
        """
        mapped_tb = self._mapped_tbs.get(company_id)
        if mapped_tb is None or self._regnskapslinjer is None:
            self._company_result_df = None
            return

        try:
            from regnskap_mapping import compute_sumlinjer

            rl = self._regnskapslinjer
            skeleton = rl[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
            skeleton["regnr"] = skeleton["regnr"].astype(int)
            result = skeleton.copy()
            leaf_mask = ~result["sumpost"]

            # --- Aggreger før-omregning (fra mapped_tb, som er originalvaluta) ---
            valid = mapped_tb.dropna(subset=["regnr"]).copy()
            if valid.empty:
                self._company_result_df = None
                return
            valid["regnr"] = valid["regnr"].astype(int)
            agg_before = valid.groupby("regnr")["ub"].sum().to_dict()

            # --- Aggreger etter-omregning + kurs fra account_details ---
            agg_after: dict[int, float] = {}
            agg_kurs: dict[int, float] = {}
            run = getattr(self, "_last_run_result", None)
            proj = getattr(self, "_project", None)
            if run and run.account_details is not None and proj:
                company = proj.find_company(company_id)
                cname = company.name if company else ""
                co = run.account_details[run.account_details["selskap"] == cname].copy()
                co_valid = co.dropna(subset=["regnr"]).copy()
                if not co_valid.empty:
                    co_valid["regnr"] = co_valid["regnr"].astype(int)
                    agg_after = co_valid.groupby("regnr")["ub"].sum().to_dict()
                    # Kurs per regnr: vektet snitt er overkill, bruk gjennomsnittlig kurs
                    # (alle kontoer på samme regnr har samme kursregel)
                    agg_kurs = co_valid.groupby("regnr")["kurs"].first().to_dict()

            # Hvis vi ikke har account_details, etter = før (NOK)
            if not agg_after:
                agg_after = dict(agg_before)
                agg_kurs = {r: 1.0 for r in agg_before}

            # --- Bygg kolonner ---
            result["UB"] = result["regnr"].map(lambda r: agg_after.get(int(r), 0.0))
            result.loc[result["sumpost"], "UB"] = 0.0

            result["F\u00f8r"] = result["regnr"].map(lambda r: agg_before.get(int(r), 0.0))
            result.loc[result["sumpost"], "F\u00f8r"] = 0.0

            result["Kurs"] = result["regnr"].map(lambda r: agg_kurs.get(int(r), 1.0))

            result["Valutaeffekt"] = 0.0
            result.loc[leaf_mask, "Valutaeffekt"] = (
                result.loc[leaf_mask, "UB"] - result.loc[leaf_mask, "F\u00f8r"]
            )

            # Sumlinjer for UB, Før, Valutaeffekt
            for col in ["UB", "F\u00f8r", "Valutaeffekt"]:
                base = {
                    int(r): float(v)
                    for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col])
                }
                all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
                sm = result["sumpost"]
                result.loc[sm, col] = result.loc[sm, "regnr"].map(
                    lambda r, av=all_v: float(av.get(int(r), 0.0))
                )
            # Kurs: sumlinjer skal ikke vise en aggregert kurs
            result.loc[result["sumpost"], "Kurs"] = float("nan")

            self._company_result_df = result.sort_values("regnr").reset_index(drop=True)

        except Exception:
            logger.exception("Failed to build company result for %s", company_id)
            self._company_result_df = None

    def _build_regnskap_from_agg(
        self, agg: dict[int, float], col_name: str,
    ) -> pd.DataFrame | None:
        """Bygg regnskapsoppstilling-DataFrame fra regnr->verdi aggregat."""
        from regnskap_mapping import compute_sumlinjer

        rl = self._regnskapslinjer
        if rl is None:
            return None
        skeleton = rl[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
        skeleton["regnr"] = skeleton["regnr"].astype(int)
        result = skeleton.copy()

        leaf_mask = ~result["sumpost"]
        result[col_name] = result["regnr"].map(lambda r: agg.get(int(r), 0.0))
        result.loc[result["sumpost"], col_name] = 0.0

        base_values = {
            int(r): float(v)
            for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col_name])
        }
        all_values = compute_sumlinjer(base_values=base_values, regnskapslinjer=rl)
        sum_mask = result["sumpost"]
        result.loc[sum_mask, col_name] = result.loc[sum_mask, "regnr"].map(
            lambda r, av=all_values: float(av.get(int(r), 0.0))
        )

        return result.sort_values("regnr").reset_index(drop=True)

    def _on_ao_toggled(self) -> None:
        """Refresh all views when AO checkbox is toggled."""
        self._invalidate_run_cache()
        self._compute_mapping_status()
        self._refresh_company_tree()
        # Refresh current detail/mapping/result if a company is selected
        cid = getattr(self, "_current_detail_cid", None)
        if cid:
            self._show_company_detail(cid)

    _RESULT_MODE_KEYS = {
        "Valgt selskap": "company",
        "Konsolidert": "consolidated",
        "Per selskap": "per_company",
    }

    @property
    def _result_col_mgr(self) -> TreeviewColumnManager:
        """Return the column manager for the active result mode."""
        mgrs = getattr(self, "_result_col_mgrs", None)
        if mgrs is None:
            raise AttributeError("_result_col_mgr")
        mode_var = getattr(self, "_result_mode_var", None)
        mode = mode_var.get() if mode_var else "Valgt selskap"
        key = self._RESULT_MODE_KEYS.get(mode, "company")
        return mgrs[key]

    def _on_result_mode_changed(self) -> None:
        """Refresh result view when mode or column checkboxes change."""
        self._refresh_result_view()

    def _fx_cols_active(self) -> tuple[bool, bool, bool]:
        """Returner (vis_foer, vis_kurs, vis_effekt) fra toolbar-checkboxes."""
        before = getattr(self, "_col_before_var", None)
        kurs = getattr(self, "_col_kurs_var", None)
        effect = getattr(self, "_col_fx_effect_var", None)
        return (
            before.get() if before else False,
            kurs.get() if kurs else False,
            effect.get() if effect else False,
        )

    def _refresh_result_view(self) -> None:
        """Populate result tree based on current mode, column checkboxes, and hide-zero."""
        mode = self._result_mode_var.get()
        show_before, show_kurs, show_effect = self._fx_cols_active()

        if mode == "Konsolidert":
            if self._preview_result_df is not None:
                self._preview_label_var.set("Preview aktiv")
                self._populate_result_tree(
                    self._preview_result_df,
                    ["Mor", "Doetre", "eliminering", "preview_elim", "konsolidert"],
                )
            elif self._consolidated_result_df is not None:
                self._preview_label_var.set("")
                cols = ["Mor", "Doetre", "eliminering", "konsolidert"]
                self._populate_result_tree(self._consolidated_result_df, cols)
            else:
                self._show_empty_result("Ingen konsolidering kjørt ennå")
        elif mode == "Per selskap":
            if self._consolidated_result_df is not None:
                self._preview_label_var.set("")
                cols = self._get_per_company_columns()
                self._populate_result_tree(self._consolidated_result_df, cols)
            else:
                self._show_empty_result("Kjør konsolidering for å se per selskap")
        elif self._company_result_df is not None:
            # Valgt selskap — vis UB + valgfrie valutakolonner
            cid = getattr(self, "_current_detail_cid", None)
            proj = getattr(self, "_project", None)
            company = proj.find_company(cid) if proj and cid else None
            reporting = (proj.reporting_currency or "NOK").upper() if proj else "NOK"
            ccur = (company.currency_code or "").upper() if company else ""
            has_fx = ccur and ccur != reporting
            self._preview_label_var.set(ccur if has_fx else "")

            cols = ["UB"]
            if show_before:
                cols.append("Før")
            if show_kurs:
                cols.append("Kurs")
            if show_effect:
                cols.append("Valutaeffekt")
            self._populate_result_tree(self._company_result_df, cols)
        else:
            self._show_empty_result("Velg et selskap eller kjør konsolidering")

    def _ensure_consolidated_fx_cols(
        self, show_before: bool, show_effect: bool,
    ) -> pd.DataFrame:
        """Legg til Mor_foer/Mor_effekt/Doetre_foer/Doetre_effekt paa consolidated df."""
        df = self._consolidated_result_df
        if not show_before and not show_effect:
            return df
        run = getattr(self, "_last_run_result", None)
        proj = getattr(self, "_project", None)
        if run is None or run.account_details is None or proj is None:
            return df
        if self._regnskapslinjer is None:
            return df

        try:
            from regnskap_mapping import compute_sumlinjer

            ad = run.account_details.copy()
            ad_valid = ad.dropna(subset=["regnr"]).copy()
            ad_valid["regnr"] = ad_valid["regnr"].astype(int)

            parent_id = proj.parent_company_id or ""
            parent_name = ""
            child_names = []
            for c in proj.companies:
                if c.company_id == parent_id:
                    parent_name = c.name
                else:
                    child_names.append(c.name)

            rl = self._regnskapslinjer
            leaf_mask = ~df["sumpost"]

            result = df.copy()

            # Helper: aggregate ub_original per regnr for a set of company names
            def _agg_before(names: list[str]) -> dict[int, float]:
                mask = ad_valid["selskap"].isin(names)
                return ad_valid.loc[mask].groupby("regnr")["ub_original"].sum().to_dict()

            def _fill_col(col_name: str, agg: dict[int, float]) -> None:
                result[col_name] = result["regnr"].map(lambda r: agg.get(int(r), 0.0))
                result.loc[result["sumpost"], col_name] = 0.0
                base = {
                    int(r): float(v)
                    for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col_name])
                }
                all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
                sm = result["sumpost"]
                result.loc[sm, col_name] = result.loc[sm, "regnr"].map(
                    lambda r, av=all_v: float(av.get(int(r), 0.0))
                )

            if show_before:
                _fill_col("Mor_foer", _agg_before([parent_name]) if parent_name else {})
                _fill_col("Doetre_foer", _agg_before(child_names) if child_names else {})

            if show_effect:
                if show_before:
                    # Effekt = etter - foer (etter er allerede in Mor/Doetre)
                    result["Mor_effekt"] = result["Mor"] - result.get("Mor_foer", 0.0)
                    result["Doetre_effekt"] = result["Doetre"] - result.get("Doetre_foer", 0.0)
                else:
                    # Need to compute foer first (temporarily)
                    mor_foer = _agg_before([parent_name]) if parent_name else {}
                    doetre_foer = _agg_before(child_names) if child_names else {}
                    result["Mor_effekt"] = result["regnr"].map(
                        lambda r: mor_foer.get(int(r), 0.0)
                    )
                    result.loc[leaf_mask, "Mor_effekt"] = (
                        result.loc[leaf_mask, "Mor"] - result.loc[leaf_mask, "Mor_effekt"]
                    )
                    result["Doetre_effekt"] = result["regnr"].map(
                        lambda r: doetre_foer.get(int(r), 0.0)
                    )
                    result.loc[leaf_mask, "Doetre_effekt"] = (
                        result.loc[leaf_mask, "Doetre"] - result.loc[leaf_mask, "Doetre_effekt"]
                    )
                    # Compute sumlinjer for effect cols
                    for ecol in ["Mor_effekt", "Doetre_effekt"]:
                        base = {
                            int(r): float(v)
                            for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, ecol])
                        }
                        all_v = compute_sumlinjer(base_values=base, regnskapslinjer=rl)
                        sm = result["sumpost"]
                        result.loc[sm, ecol] = result.loc[sm, "regnr"].map(
                            lambda r, av=all_v: float(av.get(int(r), 0.0))
                        )

            return result

        except Exception:
            logger.debug("Could not build FX columns for consolidated", exc_info=True)
            return df

    def _get_per_company_columns(self, df: pd.DataFrame | None = None) -> list[str]:
        """Bygg kolonner for Per selskap-visning: Mor, hver datter, eliminering, konsolidert."""
        if df is None:
            df = self._consolidated_result_df
        if self._project is None or df is None:
            return ["Mor", "Doetre", "eliminering", "konsolidert"]
        parent_id = self._project.parent_company_id or ""
        company_names = {}
        for c in sorted(self._project.companies, key=lambda x: x.company_id):
            company_names[c.company_id] = c.name
        parent_col = company_names.get(parent_id, "")
        cols: list[str] = []
        if parent_col and parent_col in df.columns:
            cols.append(parent_col)
        for cid, cname in company_names.items():
            if cid != parent_id and cname in df.columns:
                cols.append(cname)
        cols.extend(["eliminering", "konsolidert"])
        return cols

    def _show_empty_result(self, message: str = "") -> None:
        """Vis tom resultat-tree med tilbakestilte kolonner og melding."""
        tree = self._tree_result
        tree.delete(*tree.get_children())
        self._preview_label_var.set("")
        # Tilbakestill til standardkolonner
        default_cols = ("regnr", "regnskapslinje", "info")
        self._reset_result_tree_display_state()
        tree["columns"] = default_cols
        tree.heading("regnr", text="Regnr")
        tree.heading("regnskapslinje", text="Regnskapslinje")
        tree.heading("info", text="")
        tree.column("regnr", width=60, anchor="center")
        tree.column("regnskapslinje", width=200)
        tree.column("info", width=300)
        if message:
            tree.insert("", "end", values=("", "", message))

    # Kolonner som viser kurs (desimalformat, blank paa sumlinjer)
    _KURS_COLS = {"Kurs"}

    def _reset_result_tree_display_state(self) -> None:
        """Nullstill displaycolumns foer dynamiske kolonneskift."""
        tree = getattr(self, "_tree_result", None)
        if tree is None:
            return
        try:
            tree["displaycolumns"] = "#all"
        except Exception:
            pass

    def _populate_result_tree(
        self, result_df: pd.DataFrame, data_cols: list[str] | None = None,
    ) -> None:
        _reset_sort_state(self._tree_result)
        """Populate the result treeview from a regnskapsoppstilling DataFrame."""
        if data_cols is not None:
            augmented = append_control_rows(
                result_df,
                amount_cols=[c for c in data_cols if c not in self._KURS_COLS],
            )
        else:
            augmented = append_control_rows(result_df)
        if augmented is not None:
            result_df = augmented
        tree = self._tree_result
        tree.delete(*tree.get_children())

        meta_cols = {"regnr", "regnskapslinje", "sumpost", "formel"}
        if data_cols is None:
            data_cols = [c for c in result_df.columns if c not in meta_cols]
        # Filtrér bort kolonner som ikke finnes i DataFrame
        data_cols = [c for c in data_cols if c in result_df.columns]
        all_cols = ["regnr", "regnskapslinje"] + data_cols

        _col_labels = {
            "Mor": "Mor", "Doetre": "D\u00f8tre",
            "eliminering": "Eliminering", "konsolidert": "Konsolidert",
            "preview_elim": "Preview elim.",
            "F\u00f8r": "F\u00f8r omr.", "Kurs": "Kurs",
            "Valutaeffekt": "Val.effekt",
            "Mor_foer": "Mor f\u00f8r", "Mor_effekt": "Mor effekt",
            "Doetre_foer": "D\u00f8tre f\u00f8r", "Doetre_effekt": "D\u00f8tre effekt",
        }
        _col_widths = {
            "Kurs": 60, "Valutaeffekt": 85, "F\u00f8r": 90,
            "Mor_foer": 85, "Mor_effekt": 85, "Doetre_foer": 85, "Doetre_effekt": 85,
        }

        self._reset_result_tree_display_state()
        tree["columns"] = all_cols
        tree.heading("regnr", text="Nr")
        tree.heading("regnskapslinje", text="Regnskapslinje")
        tree.column("regnr", width=50, anchor="e")
        tree.column("regnskapslinje", width=160, anchor="w")
        for dc in data_cols:
            tree.heading(dc, text=_col_labels.get(dc, dc))
            tree.column(dc, width=_col_widths.get(dc, 100), anchor="e")

        hide_zero = self._hide_zero_var.get()
        # Kolonner som brukes for hide-zero (ignorer kurs-kolonner)
        amount_cols = [dc for dc in data_cols if dc not in self._KURS_COLS]

        for _, row in result_df.iterrows():
            is_sum = bool(row.get("sumpost", False))

            # Hide zero lines (non-sum lines where all amount cols are ~0)
            if hide_zero and not is_sum:
                if all(abs(float(row.get(dc, 0.0)) if pd.notna(row.get(dc, 0.0)) else 0.0) < 0.005
                       for dc in amount_cols):
                    continue

            vals: list = [int(row["regnr"]), row["regnskapslinje"]]
            any_neg = False
            for dc in data_cols:
                v = row.get(dc, 0.0)
                if dc in self._KURS_COLS:
                    # Kurs: vis som desimal, blank paa sumlinjer
                    if is_sum or pd.isna(v):
                        vals.append("")
                    else:
                        fv = float(v)
                        vals.append(_fmt_no(fv, 4) if abs(fv - 1.0) > 0.0001 else "1")
                else:
                    fv = float(v) if pd.notna(v) else 0.0
                    vals.append(_fmt_no(fv, 2))
                    if fv < -0.005:
                        any_neg = True

            tags = []
            if is_sum:
                tags.append("sumline")
            if any_neg and not is_sum:
                tags.append("neg")
            tree.insert("", "end", values=vals, tags=tuple(tags))

        # Enable sorting on dynamic columns
        if enable_treeview_sorting is not None:
            enable_treeview_sorting(tree, columns=all_cols)

        # Update column manager for dynamic columns
        if hasattr(self, "_result_col_mgr"):
            self._result_col_mgr.update_columns(all_cols)

    def _compute_preview(self, draft_lines: list[EliminationLine]) -> None:
        """Beregn preview av konsolidert resultat med ekstra elimineringslinjer."""
        if self._consolidated_result_df is None or not draft_lines:
            self._clear_preview()
            return

        # Bygg preview_elim-kolonne fra draft_lines
        from consolidation.elimination import aggregate_eliminations_by_regnr
        preview_journal = EliminationJournal(name="Preview", lines=draft_lines)
        preview_by_regnr = aggregate_eliminations_by_regnr([preview_journal])

        df = self._consolidated_result_df.copy()
        df["preview_elim"] = df["regnr"].map(
            lambda r: preview_by_regnr.get(int(r), 0.0)
        )
        # Nullstill sumposter — de beregnes fra leaf
        df.loc[df["sumpost"], "preview_elim"] = 0.0

        # Oppdater konsolidert med preview
        leaf = ~df["sumpost"]
        df.loc[leaf, "konsolidert"] = (
            df.loc[leaf, "sum_foer_elim"]
            + df.loc[leaf, "eliminering"]
            + df.loc[leaf, "preview_elim"]
        )

        # Reberegn sumlinjer for preview_elim og konsolidert
        try:
            from regnskap_mapping import compute_sumlinjer
            from consolidation.mapping import load_shared_config
            _, regnskapslinjer = load_shared_config()

            for col in ("preview_elim", "konsolidert"):
                base_values = {
                    int(r): float(v)
                    for r, v in zip(df.loc[leaf, "regnr"], df.loc[leaf, col])
                }
                all_values = compute_sumlinjer(
                    base_values=base_values,
                    regnskapslinjer=regnskapslinjer,
                )
                sum_mask = df["sumpost"]
                df.loc[sum_mask, col] = df.loc[sum_mask, "regnr"].map(
                    lambda r, av=all_values: float(av.get(int(r), 0.0))
                )
        except Exception:
            logger.debug("Could not recompute sumlinjer for preview", exc_info=True)

        self._preview_result_df = df
        self._result_mode_var.set("Konsolidert")
        self._refresh_result_view()

    def _clear_preview(self) -> None:
        """Fjern preview-effekt og gaa tilbake til normal visning."""
        self._preview_result_df = None
        self._preview_label_var.set("")
        self._refresh_result_view()

    def _show_result(self, result_df: pd.DataFrame) -> None:
        """Vis konsolideringsresultat i Resultat-fanen."""
        self._consolidated_result_df = result_df
        self._preview_result_df = None
        self._preview_label_var.set("")
        # Rebuild company result for currently selected company (uses fresh _last_run_result)
        cid = getattr(self, "_current_detail_cid", None)
        if cid:
            self._build_company_result(cid)
        self._result_mode_var.set("Konsolidert")
        self._refresh_result_view()
        self._select_right_tab(2, "_right_tab_result")

    def _ensure_consolidated_result(self) -> bool:
        """Sørg for at konsolidert resultat finnes, kjør om nødvendig.

        Returns True hvis resultat er tilgjengelig etterpå, False ellers.
        """
        if self._consolidated_result_df is not None:
            return True
        if self._project is None or not self._project.companies:
            return False
        # Sjekk at vi faktisk har TBer lastet
        if not self._company_tbs:
            return False
        self._on_run()
        return self._consolidated_result_df is not None

    def _invalidate_run_cache(self) -> None:
        """Nullstill all run-state slik at neste visning tvinger rerun."""
        self._result_df = None
        self._consolidated_result_df = None
        self._company_result_df = None
        self._preview_result_df = None
        self._last_run_result = None
        try:
            self._refresh_readiness()
        except Exception:
            pass

    def _rerun_consolidation(self) -> None:
        """Invalidate cache og kjør konsolidering på nytt hvis mulig.

        Etter kjøring oppdateres Resultat, Grunnlag og eliminerings-UI.
        """
        self._invalidate_run_cache()
        if (
            self._project is not None
            and self._project.companies
            and self._company_tbs
        ):
            self._on_run()

    # ------------------------------------------------------------------
    # Clipboard
    # ------------------------------------------------------------------

    def _copy_tree_to_clipboard(self, tree: ttk.Treeview) -> None:
        """Kopier alle synlige rader som TSV til clipboard."""
        lines = []
        cols = tree["columns"]
        lines.append("\t".join(str(tree.heading(c, "text")) for c in cols))
        for iid in tree.get_children():
            vals = tree.item(iid, "values")
            lines.append("\t".join(str(v) for v in vals))
        text = "\n".join(lines)
        try:
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Right-click
    # ------------------------------------------------------------------

    def _on_show_unmapped(self) -> None:
        """Vis umappede kontoer for valgt selskap i Mapping-fanen."""
        sel = self._tree_companies.selection()
        if not sel:
            return
        company_id = sel[0]
        self._show_company_detail(company_id)
        self._mapping_tab.show_unmapped()
        self._select_right_tab(1, "_right_tab_mapping")

    def _on_company_right_click(self, event) -> None:
        region = str(self._tree_companies.identify_region(event.x, event.y))
        if region == "heading":
            self._companies_col_mgr.show_header_menu(event)
            return
        iid = self._tree_companies.identify_row(event.y)
        if iid:
            self._tree_companies.selection_set(iid)
            self._company_menu.post(event.x_root, event.y_root)

    def _on_detail_right_click(self, event) -> None:
        region = str(self._tree_detail.identify_region(event.x, event.y))
        if region == "heading":
            self._detail_col_mgr.show_header_menu(event)
            return
        iid = self._tree_detail.identify_row(event.y)
        if iid:
            self._tree_detail.selection_set(iid)
            self._detail_menu.post(event.x_root, event.y_root)

    def _on_result_right_click(self, event) -> None:
        self._result_col_mgr.on_right_click(event)

    def _on_detail_double_click(self, event) -> None:
        iid = self._tree_detail.identify_row(event.y)
        if iid:
            self._tree_detail.selection_set(iid)
            self._on_change_mapping()

    def _on_change_mapping(self) -> None:
        """Endre regnskapslinje for valgte kontoer (bulk mapping override)."""
        sel_detail = self._tree_detail.selection()
        sel_company = self._tree_companies.selection()
        if not sel_detail or not sel_company or self._project is None:
            return

        company_id = sel_company[0]

        # Samle kontoer fra alle valgte rader
        selected_kontos_by_account: dict[str, tuple[str, str, str]] = {}
        for iid in sel_detail:
            vals = self._tree_detail.item(iid, "values")
            if vals:
                konto = str(vals[0]).strip()
                if konto and konto not in selected_kontos_by_account:
                    selected_kontos_by_account[konto] = (
                        konto,
                        str(vals[1]),
                        str(vals[2]) if vals[2] else "",
                    )

        selected_kontos = list(selected_kontos_by_account.values())

        if not selected_kontos:
            return

        # Hent tilgjengelige regnskapslinjer (bruk cache)
        regnskapslinjer = self._regnskapslinjer
        if regnskapslinjer is None:
            try:
                from consolidation.mapping import load_shared_config
                _, regnskapslinjer = load_shared_config()
            except Exception as exc:
                messagebox.showerror(
                    "Konfigurasjon",
                    f"Kunne ikke laste regnskapslinjer:\n{exc}",
                )
                return

        # Bygg valgliste: "regnr - Regnskapslinje"
        choices = []
        regnr_list = []
        for _, row in regnskapslinjer.iterrows():
            rn = int(row["regnr"])
            name = str(row.get("regnskapslinje", ""))
            is_sum = bool(row.get("sumpost", False))
            if not is_sum:
                choices.append(f"{rn} \u2013 {name}")
                regnr_list.append(rn)

        # Vis dialog
        dlg = tk.Toplevel(self)
        dlg.title("Tildel regnskapslinje")
        dlg.transient(self)
        dlg.grab_set()

        n = len(selected_kontos)
        if n == 1:
            konto, kontonavn, _ = selected_kontos[0]
            ttk.Label(
                dlg, text=f"Konto: {konto} \u2014 {kontonavn}", font=("", 10, "bold"),
            ).pack(padx=12, pady=(12, 4), anchor="w")
        else:
            ttk.Label(
                dlg, text=f"{n} kontoer valgt", font=("", 10, "bold"),
            ).pack(padx=12, pady=(12, 4), anchor="w")
            # Vis de foerste kontoene
            preview = ", ".join(k for k, _, _ in selected_kontos[:8])
            if n > 8:
                preview += f" ... (+{n - 8})"
            ttk.Label(dlg, text=preview, foreground="gray").pack(padx=12, anchor="w")

        ttk.Label(dlg, text="Velg regnskapslinje:").pack(
            padx=12, pady=(8, 2), anchor="w",
        )
        combo_var = tk.StringVar()
        combo = ttk.Combobox(dlg, textvariable=combo_var, values=choices, width=50)
        combo.pack(padx=12, fill="x")

        # Pre-select current regnr (only if single selection and has regnr)
        if n == 1 and selected_kontos[0][2]:
            for i, rn in enumerate(regnr_list):
                if str(rn) == selected_kontos[0][2]:
                    combo.current(i)
                    break

        result = {"regnr": None}

        def _on_ok():
            idx = combo.current()
            if idx < 0:
                messagebox.showwarning("Velg linje", "Velg en regnskapslinje.", parent=dlg)
                return
            result["regnr"] = regnr_list[idx]
            dlg.grab_release()
            dlg.destroy()

        def _on_cancel():
            dlg.grab_release()
            dlg.destroy()

        def _on_remove():
            result["regnr"] = "remove"
            dlg.grab_release()
            dlg.destroy()

        btn_frm = ttk.Frame(dlg)
        btn_frm.pack(fill="x", padx=12, pady=12)
        ttk.Button(btn_frm, text="Avbryt", command=_on_cancel).pack(side="right", padx=(4, 0))
        ttk.Button(btn_frm, text="OK", command=_on_ok).pack(side="right")
        # Show "Fjern" if any selection has an existing override
        has_any_regnr = any(r for _, _, r in selected_kontos)
        if has_any_regnr:
            ttk.Button(btn_frm, text="Fjern overstyring", command=_on_remove).pack(side="left")

        dlg.wait_window()

        if result["regnr"] is None:
            return

        if company_id == self._project.parent_company_id:
            messagebox.showinfo(
                "Mapping styres fra Analyse",
                "Morselskapet bruker Analyse som kilde til sannhet for mapping. "
                "Endre parent-mapping i Analyse-fanen, og kjør deretter konsolidering på nytt.",
                parent=dlg,
            )
            self._show_company_detail(company_id)
            return

        # Oppdater overrides for alle valgte kontoer
        overrides = self._project.mapping_config.company_overrides
        if company_id not in overrides:
            overrides[company_id] = {}

        for konto, _, _ in selected_kontos:
            if result["regnr"] == "remove":
                overrides[company_id].pop(konto, None)
            else:
                overrides[company_id][konto] = result["regnr"]

        # Rydd opp tomt dict
        if company_id in overrides and not overrides[company_id]:
            del overrides[company_id]

        self._project.touch()
        storage.save_project(self._project)
        self._invalidate_run_cache()
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._show_company_detail(company_id)

    def _on_mapping_overrides_changed(self, company_id: str, new_overrides: dict[str, int]) -> None:
        """Kalles nar MappingTab har endret overrides for et selskap."""
        if self._project is None:
            return
        if company_id == self._project.parent_company_id:
            try:
                from tkinter import messagebox
                messagebox.showinfo(
                    "Mapping styres fra Analyse",
                    "Morselskapet bruker Analyse som kilde til sannhet for mapping. "
                    "Endre parent-mapping i Analyse-fanen, og kj?r deretter konsolidering pa nytt.",
                )
            except Exception:
                pass
            self._show_company_detail(company_id)
            return
        overrides = self._project.mapping_config.company_overrides
        if new_overrides:
            overrides[company_id] = dict(new_overrides)
        else:
            overrides.pop(company_id, None)
        self._project.touch()
        storage.save_project(self._project)
        self._invalidate_run_cache()
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._show_company_detail(company_id)
    def _on_reimport_company(self) -> None:
        """Importer TB paa nytt for valgt selskap."""
        sel = self._tree_companies.selection()
        if not sel or self._project is None:
            return
        company = self._project.find_company(sel[0])
        if company is None:
            return

        path = filedialog.askopenfilename(
            title=f"Reimporter TB for {company.name}",
            filetypes=[
                ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        suffix = Path(path).suffix.lower()

        if suffix in (".xml", ".zip"):
            # SAF-T: direct import
            try:
                _, df, warnings = tb_import.import_company_tb(path, company.name)
            except Exception as exc:
                messagebox.showerror("Importfeil", str(exc))
                return
            if warnings:
                messagebox.showwarning("Import-advarsler", "\n".join(warnings))
        else:
            # Excel/CSV: preview dialog
            try:
                from tb_preview_dialog import open_tb_preview
                result = open_tb_preview(
                    self, path, initial_name=company.name,
                )
            except Exception as exc:
                messagebox.showerror("Feil", f"Forhåndsvisning feilet:\n{exc}")
                return
            if result is None:
                return
            df, _ = result
            from consolidation.tb_import import _normalize_columns
            df = _normalize_columns(df)

        company.source_file = Path(path).name
        company.row_count = len(df)
        company.has_ib = bool((df["ib"].abs() > 0.005).any()) if "ib" in df.columns else False
        self._company_tbs[company.company_id] = df
        storage.save_company_tb(
            self._project.client, self._project.year, company.company_id, df,
        )
        storage.save_project(self._project)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._show_company_detail(company.company_id)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_company_select(self, _event=None) -> None:
        sel = self._tree_companies.selection()
        if sel:
            self._show_company_detail(sel[0])
            # P1: Oppdater forslagsfilter naar selskapvalg endres
            if self._suggestions and not self._show_all_pairs_var.get():
                self._refresh_suggestion_tree()

    def _on_set_parent(self) -> None:
        """Sett valgt selskap som morselskap."""
        sel = self._tree_companies.selection()
        if not sel or self._project is None:
            return
        cid = sel[0]
        company = self._project.find_company(cid)
        if company is None:
            return

        if self._project.parent_company_id == cid:
            # Toggle off — fjern parent
            self._project.parent_company_id = ""
        else:
            self._project.parent_company_id = cid

        self._project.touch()
        storage.save_project(self._project)
        self._invalidate_run_cache()
        self._refresh_company_tree()

    def _on_delete_company(self, _event=None) -> None:
        sel = self._tree_companies.selection()
        if not sel or self._project is None:
            return
        cid = sel[0]
        company = self._project.find_company(cid)
        if company is None:
            return
        if not messagebox.askyesno("Slett selskap", f"Slett {company.name}?"):
            return
        self._project.companies = [c for c in self._project.companies if c.company_id != cid]
        self._company_tbs.pop(cid, None)
        self._mapped_tbs.pop(cid, None)
        self._mapping_pct.pop(cid, None)
        storage.delete_company_tb(self._project.client, self._project.year, cid)
        storage.save_project(self._project)
        self._refresh_company_tree()
        self._tree_detail.delete(*self._tree_detail.get_children())
        self._update_status()

    def _on_import_company(self) -> None:
        path = filedialog.askopenfilename(
            title="Importer saldobalanse",
            filetypes=[
                ("Excel/CSV/SAF-T", "*.xlsx *.xls *.csv *.xml *.zip"),
                ("Alle filer", "*.*"),
            ],
        )
        if not path:
            return

        # SAF-T files go through direct import (no preview needed)
        suffix = Path(path).suffix.lower()
        if suffix in (".xml", ".zip"):
            self._import_saft_direct(path)
            return

        # Excel/CSV: open preview dialog with column correction
        try:
            from tb_preview_dialog import open_tb_preview
            result = open_tb_preview(
                self, path, initial_name=Path(path).stem,
            )
        except Exception as exc:
            logger.exception("Preview dialog failed")
            messagebox.showerror("Feil", f"Kunne ikke åpne forhåndsvisning:\n{exc}")
            return

        if result is None:
            return  # User cancelled

        df, name = result
        self._finalize_import(df, name, Path(path))

    def _import_saft_direct(self, path: str) -> None:
        """Import SAF-T file directly (no preview — standard parser handles it)."""
        name = simpledialog.askstring(
            "Selskapsnavn",
            "Skriv inn selskapsnavn:",
            initialvalue=Path(path).stem,
        )
        if not name:
            return

        try:
            company, df, warnings = tb_import.import_company_tb(path, name)
        except Exception as exc:
            messagebox.showerror("Importfeil", str(exc))
            return

        proj = self._ensure_project()
        proj.companies.append(company)
        self._company_tbs[company.company_id] = df
        storage.save_company_tb(proj.client, proj.year, company.company_id, df)
        storage.save_project(proj)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._update_status()
        self._select_and_show_company(company.company_id)

        if warnings:
            messagebox.showwarning("Import-advarsler", "\n".join(warnings))

    def _finalize_import(
        self, df: pd.DataFrame, name: str, source_path: Path,
    ) -> None:
        """Shared finalization after preview dialog or direct import."""
        from consolidation.tb_import import _normalize_columns, validate_tb

        df = _normalize_columns(df)
        warnings = validate_tb(df)

        has_ib = bool((df["ib"].abs() > 0.005).any()) if "ib" in df.columns else False

        company = CompanyTB(
            name=name,
            source_file=source_path.name,
            source_type="excel" if source_path.suffix.lower() in (
                ".xlsx", ".xlsm", ".xls",
            ) else "csv",
            row_count=len(df),
            has_ib=has_ib,
        )

        proj = self._ensure_project()
        proj.companies.append(company)
        self._company_tbs[company.company_id] = df
        storage.save_company_tb(proj.client, proj.year, company.company_id, df)
        storage.save_project(proj)
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._update_status()
        self._select_and_show_company(company.company_id)

        if warnings:
            messagebox.showwarning("Import-advarsler", "\n".join(warnings))

    def _select_and_show_company(self, company_id: str) -> None:
        """Select a company in the tree and show its detail."""
        try:
            self._tree_companies.selection_set(company_id)
            self._tree_companies.see(company_id)
            self._show_company_detail(company_id)
            self._select_left_tab(0, "_left_tab_companies")
        except Exception:
            pass

    def _on_journal_select(self, _event=None) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal:
            self._refresh_elim_lines(journal)

    # ------------------------------------------------------------------
    # Enkel eliminering — handlers
    # ------------------------------------------------------------------

    def _populate_elim_combos(self) -> None:
        """Fyll comboboxen med regnskapslinjer (leaf-linjer)."""
        if self._regnskapslinjer is None:
            return
        rl = self._regnskapslinjer
        leaf = rl[~rl["sumpost"]]
        items = []
        for _, row in leaf.iterrows():
            rn = int(row["regnr"])
            name = str(row["regnskapslinje"])
            items.append(f"{rn} - {name}")
        self._elim_rl_items = items
        self._elim_cb_rl["values"] = items

    def _parse_regnr_from_combo(self, val: str) -> int | None:
        """Parse regnr fra combobox-verdi, f.eks. '105 - Renteinntekt...' -> 105."""
        if not val:
            return None
        try:
            return int(val.split(" - ")[0])
        except (ValueError, IndexError):
            return None

    def _get_sum_foer_elim(self, regnr: int) -> float | None:
        """Hent sum_foer_elim for en regnskapslinje fra siste konsolidering."""
        df = self._consolidated_result_df
        if df is None or "sum_foer_elim" not in df.columns:
            return None
        match = df[df["regnr"] == regnr]
        if match.empty:
            return None
        return float(match.iloc[0]["sum_foer_elim"])

    def _on_elim_line_selected(self) -> None:
        """Vis sum foer elim for valgt regnskapslinje, og autofyll beloep."""
        rn = self._parse_regnr_from_combo(self._elim_line_var.get())
        if rn is not None:
            amt = self._get_sum_foer_elim(rn)
            self._elim_line_sum_var.set(
                f"Sum: {_fmt_no(amt)}" if amt is not None else "(kjør konsolidering først)",
            )
            # Autofyll beløp med motsatt fortegn hvis feltet er tomt
            if amt is not None and not self._elim_amount_var.get().strip():
                neg = -amt
                self._elim_amount_var.set(str(round(neg, 2)))
                if hasattr(self, "_elim_amount_entry"):
                    self._elim_amount_entry.focus_set()
                    self._elim_amount_entry.select_range(0, "end")
        else:
            self._elim_line_sum_var.set("")

    def _on_elim_combo_filter(self, event=None) -> None:
        """Filtrer combobox-verdier ved tastatur i søkbar modus."""
        if not hasattr(self, "_elim_rl_items"):
            return
        typed = self._elim_line_var.get().strip().lower()
        if not typed:
            self._elim_cb_rl["values"] = self._elim_rl_items
            return
        filtered = [item for item in self._elim_rl_items if typed in item.lower()]
        self._elim_cb_rl["values"] = filtered

    def _on_use_result_rl(self) -> None:
        """Bruk markert regnskapslinje fra Resultat-treet i elimineringsskjemaet."""
        sel = self._tree_result.selection()
        if not sel:
            messagebox.showinfo("Regnskapslinje", "Velg en regnskapslinje i Resultat-fanen først.")
            return
        vals = self._tree_result.item(sel[0], "values")
        if not vals:
            return
        try:
            regnr = int(vals[0])
        except (ValueError, TypeError):
            return
        # Finn matching combobox-verdi
        target = None
        for item in getattr(self, "_elim_rl_items", []):
            if self._parse_regnr_from_combo(item) == regnr:
                target = item
                break
        if target:
            self._elim_line_var.set(target)
            self._on_elim_line_selected()

    def _ensure_elim_draft_voucher_no(self) -> int:
        raw_no = int(getattr(self, "_draft_voucher_no", 0) or 0)
        if raw_no > 0:
            return raw_no
        proj = getattr(self, "_project", None)
        next_no = proj.next_elimination_voucher_no() if proj is not None else 1
        self._draft_voucher_no = next_no
        return next_no

    def _update_elim_draft_header(self) -> None:
        voucher_no = self._ensure_elim_draft_voucher_no()
        source_journal_id = str(getattr(self, "_draft_source_journal_id", "") or "").strip()
        editing = bool(source_journal_id)

        if hasattr(self, "_elim_voucher_var"):
            self._elim_voucher_var.set(f"Bilag nr: {voucher_no}")
        if hasattr(self, "_elim_mode_var"):
            self._elim_mode_var.set(
                f"Redigerer bilag {voucher_no}" if editing else "Nytt bilag",
            )
        if hasattr(self, "_elim_save_btn_var"):
            self._elim_save_btn_var.set("Lagre endringer" if editing else "Opprett bilag")

    def _begin_new_elim_draft(self, reset_inputs: bool = True) -> None:
        proj = getattr(self, "_project", None)
        self._draft_source_journal_id = None
        self._draft_voucher_no = proj.next_elimination_voucher_no() if proj is not None else 1
        self._draft_lines.clear()
        self._draft_edit_idx = None
        if reset_inputs:
            if hasattr(self, "_elim_line_var"):
                self._elim_line_var.set("")
            if hasattr(self, "_elim_amount_var"):
                self._elim_amount_var.set("")
            if hasattr(self, "_elim_line_desc_var"):
                self._elim_line_desc_var.set("")
            if hasattr(self, "_elim_line_sum_var"):
                self._elim_line_sum_var.set("")
        self._refresh_draft_tree()
        try:
            self._tree_simple_elims.selection_remove(self._tree_simple_elims.selection())
        except Exception:
            pass
        if hasattr(self, "_elim_nb") and hasattr(self, "_elim_tab_simple"):
            try:
                self._elim_nb.select(self._elim_tab_simple)
            except Exception:
                pass

    def _load_journal_into_draft(self, journal: EliminationJournal, *, copy_mode: bool) -> None:
        proj = getattr(self, "_project", None)
        self._draft_lines.clear()
        self._draft_edit_idx = None
        for line in journal.lines:
            self._draft_lines.append({
                "regnr": line.regnr,
                "name": self._regnr_to_name.get(line.regnr, ""),
                "amount": line.amount,
                "desc": line.description,
            })
        self._draft_source_journal_id = None if copy_mode else journal.journal_id
        if copy_mode:
            self._draft_voucher_no = proj.next_elimination_voucher_no() if proj is not None else 1
        else:
            self._draft_voucher_no = int(journal.voucher_no or 0) or self._ensure_elim_draft_voucher_no()
        self._elim_amount_var.set("")
        self._elim_line_desc_var.set("")
        self._refresh_draft_tree()
        if hasattr(self, "_elim_nb") and hasattr(self, "_elim_tab_simple"):
            try:
                self._elim_nb.select(self._elim_tab_simple)
            except Exception:
                pass
        if hasattr(self, "_elim_amount_entry"):
            self._elim_amount_entry.focus_set()

    # --- Draft journal line management ---

    def _on_draft_add_line(self) -> None:
        """Legg til en linje i utkast-journalen (eller oppdater ved redigering)."""
        rn = self._parse_regnr_from_combo(self._elim_line_var.get())
        if rn is None:
            messagebox.showwarning("Eliminering", "Velg en regnskapslinje.")
            return

        raw = self._elim_amount_var.get().strip().replace(",", ".").replace(" ", "")
        try:
            amount = float(raw)
        except ValueError:
            messagebox.showwarning("Eliminering", "Ugyldig beloep.")
            return
        if abs(amount) < 0.005:
            messagebox.showwarning("Eliminering", "Beloepet maa vaere forskjellig fra null.")
            return

        name = self._regnr_to_name.get(rn, str(rn))
        line_desc = self._elim_line_desc_var.get().strip()
        entry = {"regnr": rn, "name": name, "amount": amount, "desc": line_desc}

        if self._draft_edit_idx is not None:
            # Update existing line
            self._draft_lines[self._draft_edit_idx] = entry
            self._draft_edit_idx = None
        else:
            self._draft_lines.append(entry)

        self._refresh_draft_tree()

        # Clear amount + desc, men behold valgt regnskapslinje
        self._elim_amount_var.set("")
        self._elim_line_desc_var.set("")
        # Sett fokus tilbake i beløpsfeltet
        if hasattr(self, "_elim_amount_entry"):
            self._elim_amount_entry.focus_set()

    def _on_draft_edit_line(self) -> None:
        """Last valgt utkastlinje inn i skjemaet for redigering."""
        sel = self._tree_draft_lines.selection()
        if not sel:
            return
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._draft_lines):
            return
        line = self._draft_lines[idx]
        self._draft_edit_idx = idx

        # Fyll input-feltene med linjens verdier
        combo_val = f"{line['regnr']} - {line['name']}"
        if combo_val in (self._elim_cb_rl["values"] or []):
            self._elim_line_var.set(combo_val)
        else:
            self._elim_line_var.set("")
        self._elim_amount_var.set(str(line["amount"]))
        self._elim_line_desc_var.set(line.get("desc", ""))
        self._on_elim_line_selected()

    def _on_draft_remove_line(self) -> None:
        """Fjern valgt linje fra utkast."""
        sel = self._tree_draft_lines.selection()
        if not sel:
            return
        idx = int(sel[0])
        if 0 <= idx < len(self._draft_lines):
            self._draft_lines.pop(idx)
        self._draft_edit_idx = None
        self._refresh_draft_tree()

    def _on_draft_clear(self) -> None:
        """Nullstill utkast."""
        self._draft_lines.clear()
        self._draft_edit_idx = None
        if hasattr(self, "_elim_amount_var"):
            self._elim_amount_var.set("")
        if hasattr(self, "_elim_line_desc_var"):
            self._elim_line_desc_var.set("")
        if hasattr(self, "_elim_line_sum_var"):
            self._elim_line_sum_var.set("")
        self._refresh_draft_tree()

    def _refresh_draft_tree(self) -> None:
        """Oppdater utkast-treet, kontrollsummer og opprett-knapp."""
        tree = self._tree_draft_lines
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())
        for i, line in enumerate(self._draft_lines):
            amt = line["amount"]
            debet = _fmt_no(amt, 2) if amt > 0 else ""
            kredit = _fmt_no(abs(amt), 2) if amt < 0 else ""
            tree.insert("", "end", iid=str(i), values=(
                line["regnr"], line["name"], debet, kredit, line.get("desc", ""),
            ))

        # Kontrollsummer
        sum_debet = sum(d["amount"] for d in self._draft_lines if d["amount"] > 0)
        sum_kredit = sum(abs(d["amount"]) for d in self._draft_lines if d["amount"] < 0)
        diff = sum_debet - sum_kredit
        n = len(self._draft_lines)

        if n > 0:
            status = "Balansert" if abs(diff) < 0.005 else "Ubalansert"
            self._elim_ctrl_var.set(
                f"Sum debet: {_fmt_no(sum_debet, 2)}  |  "
                f"Sum kredit: {_fmt_no(sum_kredit, 2)}  |  "
                f"Diff: {_fmt_no(diff, 2)}  |  {status}"
            )
        else:
            self._elim_ctrl_var.set("")

        # Opprett-knapp status
        can_create = n >= 2 and abs(diff) < 0.005
        self._btn_create_elim.configure(state="normal" if can_create else "disabled")
        if n < 2:
            self._elim_create_hint_var.set("Legg til minst 2 linjer")
        elif abs(diff) >= 0.005:
            self._elim_create_hint_var.set("Journalen maa balansere")
        else:
            self._elim_create_hint_var.set("")

        self._update_elim_draft_header()

    def _on_create_simple_elim(self) -> None:
        """Opprett eliminering fra utkastlinjene."""
        if len(self._draft_lines) < 2:
            return
        netto = sum(d["amount"] for d in self._draft_lines)
        if abs(netto) >= 0.005:
            return

        proj = self._ensure_project()
        voucher_no = int(getattr(self, "_draft_voucher_no", 0) or 0) or proj.next_elimination_voucher_no()
        lines = [
            EliminationLine(regnr=d["regnr"], amount=d["amount"], description=d.get("desc", ""))
            for d in self._draft_lines
        ]
        source_journal_id = str(getattr(self, "_draft_source_journal_id", "") or "").strip()
        journal = proj.find_journal(source_journal_id) if source_journal_id else None
        if journal is None:
            journal = EliminationJournal(
                voucher_no=voucher_no,
                name=f"Bilag {voucher_no}",
                kind="manual",
                lines=lines,
            )
            proj.eliminations.append(journal)
        else:
            journal.voucher_no = voucher_no
            journal.name = f"Bilag {voucher_no}"
            journal.kind = "manual"
            journal.lines = lines
        storage.save_project(proj)

        # Oppdater UI
        self._refresh_simple_elim_tree()
        self._refresh_journal_tree()
        try:
            self._tree_simple_elims.selection_set((journal.journal_id,))
            self._tree_simple_elims.focus(journal.journal_id)
            self._show_elim_detail(journal.journal_id)
        except Exception:
            pass
        try:
            self._tree_journals.selection_set((journal.journal_id,))
            self._tree_journals.focus(journal.journal_id)
            self._refresh_elim_lines(journal)
        except Exception:
            pass
        self._update_status()
        self._begin_new_elim_draft()

        # Re-kjør konsolidering (invalidate + run)
        self._clear_preview()
        self._rerun_consolidation()

    def _on_delete_simple_elim(self) -> None:
        """Slett valgt eliminering fra oversikten."""
        sel = self._tree_simple_elims.selection()
        if not sel or self._project is None:
            return
        jid = sel[0]
        journal = self._project.find_journal(jid)
        if journal is None:
            return
        if not messagebox.askyesno("Slett bilag", f"Slett '{journal.display_label}'?"):
            return
        self._project.eliminations.remove(journal)
        storage.save_project(self._project)
        self._refresh_simple_elim_tree()
        self._refresh_journal_tree()
        if getattr(self, "_draft_source_journal_id", None) == jid:
            self._begin_new_elim_draft()
        self._update_status()

        # Re-kjør konsolidering (invalidate + run)
        self._clear_preview()
        self._rerun_consolidation()

    def _refresh_simple_elim_tree(self) -> None:
        """Oppdater oversikten over aktive elimineringer."""
        tree = self._tree_simple_elims
        _reset_sort_state(tree)
        _reset_sort_state(self._tree_elim_detail)
        tree.delete(*tree.get_children())
        if hasattr(self, "_tree_elim_detail"):
            self._tree_elim_detail.delete(*self._tree_elim_detail.get_children())
        if self._project is None:
            return
        last_jid = None
        for j in self._project.eliminations:
            diff = j.total_debet - j.total_kredit
            status = "Balansert" if j.is_balanced else "Ubalansert"
            tags = ("balanced",) if j.is_balanced else ("unbalanced",)
            tree.insert(
                "", "end", iid=j.journal_id,
                values=(
                    j.display_label,
                    len(j.lines),
                    _fmt_no(j.total_debet, 2),
                    _fmt_no(j.total_kredit, 2),
                    _fmt_no(diff, 2),
                    status,
                ),
                tags=tags,
            )
            last_jid = j.journal_id
        # Auto-velg siste journal slik at linjene vises
        if last_jid:
            tree.selection_set(last_jid)
            self._show_elim_detail(last_jid)

    def _on_simple_elim_selected(self, _event=None) -> None:
        """Vis linjer for valgt journal i Aktive elimineringer."""
        sel = self._tree_simple_elims.selection()
        if not sel or self._project is None:
            if hasattr(self, "_tree_elim_detail"):
                self._tree_elim_detail.delete(*self._tree_elim_detail.get_children())
            return
        self._show_elim_detail(sel[0])

    def _show_elim_detail(self, journal_id: str) -> None:
        """Populer detalj-treet under Aktive elimineringer med journalens linjer."""
        tree = self._tree_elim_detail
        tree.delete(*tree.get_children())
        if self._project is None:
            return
        journal = self._project.find_journal(journal_id)
        if journal is None:
            return
        for line in journal.lines:
            debet = _fmt_no(line.amount, 2) if line.amount > 0.005 else ""
            kredit = _fmt_no(abs(line.amount), 2) if line.amount < -0.005 else ""
            rl_name = self._regnr_to_name.get(line.regnr, "")
            tree.insert("", "end", values=(
                line.regnr, rl_name, debet, kredit, line.description,
            ))

    def _on_load_journal_to_draft(self) -> None:
        """Last valgt journals linjer tilbake i utkastet for redigering."""
        sel = self._tree_simple_elims.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal is None:
            return
        self._load_journal_into_draft(journal, copy_mode=False)

    def _on_copy_journal_to_draft(self) -> None:
        """Kopier valgt bilag til nytt utkast med nytt bilagsnummer."""
        sel = self._tree_simple_elims.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal is None:
            return
        self._load_journal_into_draft(journal, copy_mode=True)

    def _on_new_journal(self) -> None:
        self._begin_new_elim_draft()

    def _on_delete_journal(self) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        jid = sel[0]
        journal = self._project.find_journal(jid)
        if journal is None:
            return
        if not messagebox.askyesno("Slett bilag", f"Slett '{journal.display_label}'?"):
            return
        self._project.eliminations = [
            j for j in self._project.eliminations if j.journal_id != jid
        ]
        storage.save_project(self._project)
        self._refresh_journal_tree()
        if getattr(self, "_draft_source_journal_id", None) == jid:
            self._begin_new_elim_draft()
        self._update_status()

    def _on_add_elim_line(self) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        journal = self._project.find_journal(sel[0])
        if journal is None:
            return

        company_names = {c.company_id: c.name for c in self._project.companies}
        if not company_names:
            messagebox.showwarning("Ingen selskaper", "Importer minst ett selskap foerst.")
            return

        # Samle-dialog: "regnr ; beloep ; selskap ; beskrivelse"
        company_hint = ", ".join(company_names.values())
        raw = simpledialog.askstring(
            "Ny elimineringslinje",
            f"Regnr ; Beloep ; Selskap ; Beskrivelse\n"
            f"Selskaper: {company_hint}\n"
            f"Eksempel: 3000 ; -500000 ; {list(company_names.values())[0]} ; Interco salg",
        )
        if not raw:
            return

        parts = [p.strip() for p in raw.split(";")]
        if len(parts) < 2:
            messagebox.showerror("Feil", "Skriv minst: regnr ; beloep")
            return

        try:
            regnr = int(parts[0])
        except ValueError:
            messagebox.showerror("Feil", "Regnr maa vaere et heltall.")
            return

        try:
            amount = float(parts[1].replace(",", ".").replace(" ", ""))
        except ValueError:
            messagebox.showerror("Feil", "Ugyldig beloep.")
            return

        # Match selskap
        company_id = list(company_names.keys())[0]
        if len(parts) >= 3 and parts[2]:
            needle = parts[2].lower()
            for cid, cname in company_names.items():
                if needle in cname.lower() or needle in cid.lower():
                    company_id = cid
                    break

        desc = parts[3] if len(parts) >= 4 else ""

        line = EliminationLine(
            regnr=regnr, company_id=company_id, amount=amount, description=desc,
        )
        journal.lines.append(line)
        storage.save_project(self._project)
        self._refresh_journal_tree()
        self._refresh_elim_lines(journal)

    def _on_delete_elim_line(self) -> None:
        sel_j = self._tree_journals.selection()
        sel_l = self._tree_elim_lines.selection()
        if not sel_j or not sel_l or self._project is None:
            return
        journal = self._project.find_journal(sel_j[0])
        if journal is None:
            return
        try:
            idx = int(sel_l[0])
            if 0 <= idx < len(journal.lines):
                journal.lines.pop(idx)
                storage.save_project(self._project)
                self._refresh_journal_tree()
                self._refresh_elim_lines(journal)
        except (ValueError, IndexError):
            pass

    # ------------------------------------------------------------------
    # Forslag (suggestions)
    # ------------------------------------------------------------------

    def _on_generate_suggestions(self) -> None:
        """Generer elimineringskandidater fra mapped TBer."""
        if self._project is None or not self._mapped_tbs:
            messagebox.showinfo("Forslag", "Importer og map selskaper foerst.")
            return
        try:
            self._suggestions = generate_suggestions(
                self._project, self._mapped_tbs, self._regnr_to_name,
            )
        except Exception as exc:
            logger.exception("Suggestion generation failed")
            messagebox.showerror("Feil", str(exc))
            return
        self._refresh_suggestion_tree()

    _KIND_DISPLAY = {
        "intercompany": "Mellomvaerende",
        "interest": "Renter",
        "group_contribution": "Konsernbidrag",
        "investment_equity": "Investering/EK",
        "fx_difference": "Valutadiff",
    }

    _STATUS_DISPLAY = {"ny": "Ny", "ignorert": "Ignorert", "journalfoert": "Journalfoert"}

    def _refresh_suggestion_tree(self) -> None:
        tree = self._tree_suggestions
        _reset_sort_state(tree)
        _reset_sort_state(self._tree_suggestion_detail)
        tree.delete(*tree.get_children())
        self._tree_suggestion_detail.delete(*self._tree_suggestion_detail.get_children())

        name_map = {}
        parent_id = ""
        if self._project:
            name_map = {c.company_id: c.name for c in self._project.companies}
            parent_id = self._project.parent_company_id or ""

        # P1: Selskapspar-filter
        show_all_pairs = self._show_all_pairs_var.get()
        selected_cid = ""
        try:
            sel = self._tree_companies.selection()
            if sel:
                selected_cid = sel[0]
        except Exception:
            pass

        # P3: Typefilter (checkbox-basert)
        allowed_kinds: set[str] = set()
        if self._sug_type_interco_var.get():
            allowed_kinds.add("intercompany")
        if self._sug_type_renter_var.get():
            allowed_kinds.add("interest")
        if self._sug_type_bidrag_var.get():
            allowed_kinds.add("group_contribution")
        if self._sug_type_invest_var.get():
            allowed_kinds.add("investment_equity")
        # Vis alltid valutadiff hvis det finnes
        allowed_kinds.add("fx_difference")

        tolerance = self._project.match_tolerance_nok if self._project else 1000

        shown = 0
        for i, s in enumerate(self._suggestions):
            # P3: Typefilter
            if s.kind not in allowed_kinds:
                continue

            # P1: Selskapspar-filter
            if not show_all_pairs and parent_id:
                # Vis bare forslag der parent er involvert
                if s.company_a_id != parent_id and s.company_b_id != parent_id:
                    continue
                # Hvis et ikke-parent selskap er valgt: filtrer til bare det paret
                if selected_cid and selected_cid != parent_id:
                    other = s.company_b_id if s.company_a_id == parent_id else s.company_a_id
                    if other != selected_cid:
                        continue

            shown += 1
            kind_text = self._KIND_DISPLAY.get(s.kind, s.kind)
            status_text = self._STATUS_DISPLAY.get(s.status, s.status)
            tags = (s.status,)
            if abs(s.diff_nok) > tolerance:
                tags = (s.status, "diff_warning")

            # P4: Slank visning — motpart er B-siden (parent er A)
            counterparty = name_map.get(s.company_b_id, s.company_b_id[:12])

            tree.insert("", "end", iid=str(i), values=(
                kind_text,
                counterparty,
                s.line_name_a,
                s.line_name_b,
                _fmt_no(s.amount_a, 2),
                _fmt_no(s.amount_b, 2),
                _fmt_no(s.diff_nok, 2),
                status_text,
            ), tags=tags)

        self._suggestion_count_var.set(f"{shown} forslag" if shown else "Ingen forslag for gjeldende filter")

        # P5: Auto-velg foerste forslag
        children = tree.get_children()
        if children:
            tree.selection_set(children[0])
            tree.see(children[0])
            self._on_suggestion_select()
        else:
            self._suggestion_detail_var.set("Ingen forslag for gjeldende filter.")
            self._clear_preview()

    def _on_suggestion_select(self, _event=None) -> None:
        sel = self._tree_suggestions.selection()
        if not sel:
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        if idx < 0 or idx >= len(self._suggestions):
            return
        s = self._suggestions[idx]
        self._show_suggestion_detail(s)

    def _show_suggestion_detail(self, s: EliminationSuggestion) -> None:
        """Vis grunnlag for valgt kandidat og preview-effekt i Resultat."""
        tree = self._tree_suggestion_detail
        tree.delete(*tree.get_children())

        name_map = {}
        if self._project:
            name_map = {c.company_id: c.name for c in self._project.companies}

        kind_text = self._KIND_DISPLAY.get(s.kind, s.kind)
        self._suggestion_detail_var.set(
            f"{kind_text}: {s.line_name_a} / {s.line_name_b}  —  "
            f"Diff: {_fmt_no(s.diff_nok, 2)} NOK"
        )

        for i, line in enumerate(s.journal_draft_lines):
            tree.insert("", "end", iid=str(i), values=(
                line.regnr,
                name_map.get(line.company_id, line.company_id[:12]),
                _fmt_no(line.amount, 2),
                line.description,
            ))

        # Preview-effekt i Resultat
        self._compute_preview(s.journal_draft_lines)

    def _on_create_journal_from_suggestion(self) -> None:
        sel = self._tree_suggestions.selection()
        if not sel or self._project is None:
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        if idx < 0 or idx >= len(self._suggestions):
            return

        s = self._suggestions[idx]
        if s.status == "journalfoert":
            messagebox.showinfo("Allerede opprettet", "Denne kandidaten har allerede en journal.")
            return

        journal = create_journal_from_suggestion(s, self._project)
        self._project.eliminations.append(journal)
        s.status = "journalfoert"
        storage.save_project(self._project)
        self._refresh_journal_tree()
        self._refresh_suggestion_tree()
        self._update_status()

    def _on_ignore_suggestion(self) -> None:
        sel = self._tree_suggestions.selection()
        if not sel or self._project is None:
            return
        try:
            idx = int(sel[0])
        except (ValueError, IndexError):
            return
        if idx < 0 or idx >= len(self._suggestions):
            return

        s = self._suggestions[idx]
        if s.status == "ignorert":
            # Toggle: fjern ignorer
            unignore_suggestion(s.suggestion_key, self._project)
            s.status = "ny"
        else:
            ignore_suggestion(s.suggestion_key, self._project)
            s.status = "ignorert"

        storage.save_project(self._project)
        self._refresh_suggestion_tree()

    # ------------------------------------------------------------------
    # Valuta
    # ------------------------------------------------------------------

    def _has_foreign_currency(self) -> bool:
        """Sjekk om minst ett selskap har annen valuta enn rapporteringsvaluta."""
        if self._project is None:
            return False
        rep = self._project.reporting_currency or "NOK"
        for c in self._project.companies:
            if c.currency_code and c.currency_code != rep:
                return True
            if abs(c.closing_rate - 1.0) > 0.0001 or abs(c.average_rate - 1.0) > 0.0001:
                return True
        return False

    def _update_valuta_tab_visibility(self) -> None:
        """P7: Vis/skjul Valuta-taben basert paa om valuta er relevant."""
        try:
            if self._has_foreign_currency():
                self._elim_nb.tab(self._elim_tab_fx, state="normal")
            else:
                # Skjul ikke helt — demp visuelt ved aa sette state=hidden
                # Brukeren kan fortsatt navigere dit via andre metoder
                self._elim_nb.tab(self._elim_tab_fx, state="hidden")
        except Exception:
            pass

    def _refresh_fx_tree(self) -> None:
        tree = self._tree_fx_rates
        _reset_sort_state(tree)
        tree.delete(*tree.get_children())
        if self._project is None:
            return
        self._fx_reporting_var.set(self._project.reporting_currency or "NOK")
        self._fx_tolerance_var.set(str(self._project.match_tolerance_nok))
        for c in self._project.companies:
            tree.insert("", "end", iid=c.company_id, values=(
                c.name,
                c.currency_code or self._project.reporting_currency,
                f"{c.closing_rate:.4f}",
                f"{c.average_rate:.4f}",
            ))
        self._update_valuta_tab_visibility()

    def _on_save_fx_settings(self) -> None:
        if self._project is None:
            return
        self._project.reporting_currency = self._fx_reporting_var.get().strip().upper() or "NOK"
        try:
            self._project.match_tolerance_nok = float(
                self._fx_tolerance_var.get().replace(",", ".").strip() or "1000"
            )
        except ValueError:
            pass
        storage.save_project(self._project)
        self._invalidate_run_cache()

    def _on_edit_fx_rate(self) -> None:
        sel = self._tree_fx_rates.selection()
        if not sel or self._project is None:
            return
        company = self._project.find_company(sel[0])
        if company is None:
            return

        raw = simpledialog.askstring(
            "Valutakurs",
            f"Selskap: {company.name}\n"
            f"Valutakode ; Sluttkurs ; Snittkurs\n"
            f"Eksempel: SEK ; 0.98 ; 0.97",
            initialvalue=f"{company.currency_code or 'NOK'} ; {company.closing_rate} ; {company.average_rate}",
        )
        if not raw:
            return

        parts = [p.strip() for p in raw.split(";")]
        if len(parts) >= 1:
            company.currency_code = parts[0].upper()
        if len(parts) >= 2:
            try:
                company.closing_rate = float(parts[1].replace(",", "."))
            except ValueError:
                pass
        if len(parts) >= 3:
            try:
                company.average_rate = float(parts[2].replace(",", "."))
            except ValueError:
                pass

        storage.save_project(self._project)
        self._invalidate_run_cache()
        self._refresh_fx_tree()

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def _on_run(self) -> None:
        if self._project is None:
            messagebox.showwarning("Konsolidering", "Ingen prosjekt. Importer minst ett selskap.")
            return
        if len(self._project.companies) < 1:
            messagebox.showwarning("Konsolidering", "Importer minst ett selskap foerst.")
            return

        # Analyse-endringer (overstyringer/AO) lagres utenfor konsolideringsmodulen.
        # Reberegn derfor mapped_tbs/unmapped før readiness og kjøring, slik at
        # "Valgt selskap" og kontrollpanelet ikke henger igjen på gammel state.
        self._compute_mapping_status()

        from consolidation.engine import run_consolidation
        from consolidation.mapping import ConfigNotLoadedError
        import consolidation_readiness

        try:
            preflight = consolidation_readiness.build_readiness_report(self)
        except Exception:
            preflight = None
        if preflight is not None:
            blockers = [
                issue for issue in getattr(preflight, "issues", []) or []
                if str(getattr(issue, "severity", "") or "") == "blocking"
                and str(getattr(issue, "category", "") or "") != "stale"
            ]
            if blockers:
                preview = "\n".join(
                    f"- {getattr(issue, 'message', '')}"
                    for issue in blockers[:5]
                )
                if len(blockers) > 5:
                    preview += f"\n... og {len(blockers) - 5} til"
                proceed = messagebox.askyesno(
                    "Konsolideringskontroller",
                    "Det finnes blokkere i grunnlaget som kan gi ufullstendig eller feil konsolidering:\n\n"
                    f"{preview}\n\n"
                    "Vil du kjøre likevel?",
                )
                if not proceed:
                    self._select_left_tab(1, "_left_tab_controls")
                    return

        # Forbered TBer og overstyringer
        tbs = self._prepare_tbs_for_run()
        eff_overrides = {
            c.company_id: self._get_effective_company_overrides(c.company_id)
            for c in self._project.companies
        }

        try:
            result_df, run_result = run_consolidation(
                self._project, tbs, effective_overrides=eff_overrides,
            )
        except ConfigNotLoadedError as exc:
            messagebox.showerror("Konfigurasjon mangler", str(exc))
            return
        except ValueError as exc:
            messagebox.showerror("Feil", str(exc))
            return
        except Exception as exc:
            logger.exception("Konsolidering feilet")
            messagebox.showerror("Feil", f"Konsolidering feilet:\n{exc}")
            return

        try:
            run_result.input_digest = consolidation_readiness.compute_input_digest(self)
        except Exception:
            run_result.input_digest = ""

        self._result_df = result_df
        self._last_run_result = run_result
        self._project.runs.append(run_result)
        storage.save_project(self._project)

        # Legg til varsler om umappede kontoer med beløp
        unmapped_warnings = self._build_unmapped_warnings(tbs)
        all_warnings = list(run_result.warnings) + unmapped_warnings

        if all_warnings:
            messagebox.showwarning("Advarsler", "\n".join(all_warnings))

        self._show_result(result_df)
        self._update_status()

    def _build_unmapped_warnings(
        self, tbs: dict[str, pd.DataFrame],
    ) -> list[str]:
        """Bygg varsler for umappede kontoer med beløp != 0."""
        warnings: list[str] = []
        if self._project is None:
            return warnings
        for c in self._project.companies:
            unmapped_kontos = self._mapping_unmapped.get(c.company_id, [])
            if not unmapped_kontos:
                continue
            tb = tbs.get(c.company_id)
            if tb is None or tb.empty:
                continue
            # Finn beløp for umappede kontoer
            col_konto = None
            col_ub = None
            for col in tb.columns:
                if col.lower() == "konto":
                    col_konto = col
                elif col.lower() == "ub":
                    col_ub = col
            if col_konto is None or col_ub is None:
                continue
            unmapped_set = set(str(k) for k in unmapped_kontos)
            parts: list[str] = []
            total_missing = 0.0
            for _, row in tb.iterrows():
                konto = str(row.get(col_konto, "")).strip()
                if konto in unmapped_set:
                    try:
                        ub = float(row.get(col_ub, 0.0) or 0.0)
                    except (ValueError, TypeError):
                        ub = 0.0
                    if abs(ub) > 0.005:
                        parts.append(f"{konto} ({_fmt_no(ub, 0)})")
                        total_missing += ub
            if parts:
                preview = ", ".join(parts[:5])
                suffix = f" +{len(parts) - 5} til" if len(parts) > 5 else ""
                warnings.append(
                    f"{c.name}: {len(parts)} umappede kontoer med beløp "
                    f"(sum {_fmt_no(total_missing, 0)}): {preview}{suffix}"
                )
        return warnings

    def _prepare_tbs_for_run(self) -> dict[str, pd.DataFrame]:
        """Forbered TBer for konsolidering, inkludert AO-justeringer."""
        return self._get_effective_tbs()

    def _on_export(self) -> None:
        if self._result_df is None or self._project is None:
            messagebox.showwarning("Eksport", "Kjoer konsolidering foerst.")
            return

        stale = False
        try:
            import consolidation_readiness

            report = consolidation_readiness.build_readiness_report(self)
            stale = report.is_stale
        except Exception:
            stale = self._consolidated_result_df is None

        # Stale-state guard: export skal ikke bruke et annet snapshot enn GUI
        if stale:
            ans = messagebox.askyesno(
                "Utdatert resultat",
                "Data har endret seg siden siste konsolidering.\n"
                "Vil du kjoere konsolidering paa nytt foer eksport?",
            )
            if ans:
                self._rerun_consolidation()
                try:
                    import consolidation_readiness

                    stale = consolidation_readiness.build_readiness_report(self).is_stale
                except Exception:
                    stale = self._result_df is None
                if self._result_df is None or stale:
                    return
            else:
                return

        from consolidation.export import save_consolidation_workbook

        path = filedialog.asksaveasfilename(
            title="Eksporter konsolidering",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"konsolidering_{self._project.client}_{self._project.year}.xlsx",
        )
        if not path:
            return

        run_result = getattr(self, "_last_run_result", None)
        if run_result is None and self._project.runs:
            run_result = self._project.runs[-1]
        if run_result is None:
            return

        try:
            out = save_consolidation_workbook(
                path,
                result_df=self._result_df,
                companies=self._project.companies,
                eliminations=self._project.eliminations,
                mapped_tbs=self._mapped_tbs,
                run_result=run_result,
                client=self._project.client,
                year=self._project.year,
                parent_company_id=self._project.parent_company_id or "",
                regnr_to_name=self._regnr_to_name,
                hide_zero=self._hide_zero_var.get(),
            )
            messagebox.showinfo("Eksport", f"Lagret til:\n{out}")
        except Exception as exc:
            logger.exception("Export failed")
            messagebox.showerror("Eksportfeil", str(exc))
