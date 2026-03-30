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
from consolidation.suggestions import (
    create_journal_from_suggestion,
    generate_suggestions,
    ignore_suggestion,
    unignore_suggestion,
)
from consolidation_mapping_tab import MappingTab

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
        self._result_df: Optional[pd.DataFrame] = None
        self._current_detail_cid: Optional[str] = None
        self._suggestions: list[EliminationSuggestion] = []

        # Cached mapping config (loaded once per project)
        self._intervals: Optional[pd.DataFrame] = None
        self._regnskapslinjer: Optional[pd.DataFrame] = None
        self._regnr_to_name: dict[int, str] = {}

        self._status_var = tk.StringVar(value="Velg klient og aar for aa starte.")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI Build
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

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

        # --- Main paned area ---
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)

        # Left: tabs Selskaper / Eliminering
        left_nb = ttk.Notebook(pw)
        self._left_nb = left_nb

        # Tab: Selskaper
        frm_companies = ttk.Frame(left_nb)
        left_nb.add(frm_companies, text="Selskaper")
        self._tree_companies = self._make_company_tree(frm_companies)

        # Tab: Eliminering
        frm_elim = ttk.Frame(left_nb)
        left_nb.add(frm_elim, text="Eliminering")
        self._build_elimination_tab(frm_elim)

        pw.add(left_nb, weight=3)

        # Right: tabs Detalj / Resultat
        right_nb = ttk.Notebook(pw)
        self._right_nb = right_nb

        # Tab: Detalj
        frm_detail = ttk.Frame(right_nb)
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
        right_nb.add(self._mapping_tab, text="Mapping")

        # Tab: Resultat
        frm_result = ttk.Frame(right_nb)
        right_nb.add(frm_result, text="Resultat")
        self._build_result_tab(frm_result)

        pw.add(right_nb, weight=5)

        # --- Statuslinje ---
        status_bar = ttk.Frame(self)
        status_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._lbl_statusbar = ttk.Label(
            status_bar, text="Konsolidering | TB-only", anchor="w",
        )
        self._lbl_statusbar.pack(fill="x")

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
        self._company_menu.add_separator()
        self._company_menu.add_command(label="Slett selskap", command=self._on_delete_company)
        tree.bind("<Button-3>", self._on_company_right_click)
        return tree

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
        tree.bind("<Button-3>", self._on_detail_right_click)

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
            values=["Valgt selskap", "Konsolidert"],
            state="readonly", width=16,
        )
        mode_combo.set("Valgt selskap")
        mode_combo.pack(side="left", padx=(0, 12))
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_result_mode_changed())

        self._hide_zero_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            toolbar, text="Kun linjer med verdi",
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
        self._tree_result = tree

        # Cached result DataFrames
        self._company_result_df: Optional[pd.DataFrame] = None
        self._consolidated_result_df: Optional[pd.DataFrame] = None
        self._preview_result_df: Optional[pd.DataFrame] = None

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
        self._elim_nb.add(frm_enkel, text="Eliminering")
        self._build_enkel_elim_tab(frm_enkel)

        # --- Tab: Journaler ---
        frm_journaler = ttk.Frame(self._elim_nb)
        self._elim_nb.add(frm_journaler, text="Journaler")
        self._build_journaler_tab(frm_journaler)

        # --- Tab: Forslag (sekundaer) ---
        frm_forslag = ttk.Frame(self._elim_nb)
        self._elim_nb.add(frm_forslag, text="Forslag")
        self._build_forslag_tab(frm_forslag)

        # --- Tab: Valuta ---
        frm_valuta = ttk.Frame(self._elim_nb)
        self._elim_nb.add(frm_valuta, text="Valuta")
        self._build_valuta_tab(frm_valuta)

    def _build_enkel_elim_tab(self, parent: ttk.Frame) -> None:
        """Eliminering: flerlinje-journalbygger paa regnskapslinjenivaa."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(4, weight=2)

        # === Input-seksjon ===
        form = ttk.LabelFrame(parent, text="Ny eliminering — legg til linjer", padding=8)
        form.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        form.columnconfigure(1, weight=1)

        # Journalbeskrivelse
        ttk.Label(form, text="Journalnavn:").grid(row=0, column=0, sticky="w", pady=2)
        self._elim_desc_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._elim_desc_var, width=50).grid(
            row=0, column=1, columnspan=2, sticky="ew", padx=(4, 0), pady=2,
        )

        ttk.Separator(form, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", pady=6,
        )

        # Regnskapslinje
        ttk.Label(form, text="Regnskapslinje:").grid(row=2, column=0, sticky="w", pady=2)
        self._elim_line_var = tk.StringVar()
        cb_rl = ttk.Combobox(form, textvariable=self._elim_line_var, state="readonly", width=60)
        cb_rl.grid(row=2, column=1, sticky="ew", padx=(4, 0), pady=2)
        cb_rl.bind("<<ComboboxSelected>>", lambda _e: self._on_elim_line_selected())
        self._elim_cb_rl = cb_rl

        self._elim_line_sum_var = tk.StringVar(value="")
        ttk.Label(form, textvariable=self._elim_line_sum_var, foreground="#666666").grid(
            row=2, column=2, padx=(8, 0),
        )

        # Beloep (positiv=debet, negativ=kredit)
        ttk.Label(form, text="Beloep:").grid(row=3, column=0, sticky="w", pady=2)
        amt_frm = ttk.Frame(form)
        amt_frm.grid(row=3, column=1, sticky="w", padx=(4, 0), pady=2)
        self._elim_amount_var = tk.StringVar()
        ttk.Entry(amt_frm, textvariable=self._elim_amount_var, width=18).pack(side="left")
        ttk.Label(amt_frm, text="(positiv = debet, negativ = kredit)", foreground="#888888").pack(
            side="left", padx=(8, 0),
        )

        # Linjebeskrivelse
        ttk.Label(form, text="Linjebeskrivelse:").grid(row=4, column=0, sticky="w", pady=2)
        self._elim_line_desc_var = tk.StringVar()
        ttk.Entry(form, textvariable=self._elim_line_desc_var, width=40).grid(
            row=4, column=1, sticky="ew", padx=(4, 0), pady=2,
        )

        # Knapper
        btn_frm = ttk.Frame(form)
        btn_frm.grid(row=5, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Button(btn_frm, text="Legg til linje", command=self._on_draft_add_line).pack(
            side="left",
        )
        ttk.Button(btn_frm, text="Rediger valgt", command=self._on_draft_edit_line).pack(
            side="left", padx=(4, 0),
        )
        ttk.Button(btn_frm, text="Fjern valgt linje", command=self._on_draft_remove_line).pack(
            side="left", padx=(4, 0),
        )
        ttk.Button(btn_frm, text="Nullstill utkast", command=self._on_draft_clear).pack(
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
        self._draft_lines: list[dict] = []  # {regnr, name, amount, desc}
        self._draft_edit_idx: int | None = None  # index being edited

        # --- Kontrollsummer + opprett ---
        ctrl_frm = ttk.Frame(parent)
        ctrl_frm.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 2))

        self._elim_ctrl_var = tk.StringVar(value="")
        ttk.Label(ctrl_frm, textvariable=self._elim_ctrl_var, foreground="#444444").pack(
            side="left",
        )

        self._btn_create_elim = ttk.Button(
            ctrl_frm, text="Opprett eliminering", command=self._on_create_simple_elim,
            state="disabled",
        )
        self._btn_create_elim.pack(side="right")

        self._elim_create_hint_var = tk.StringVar(value="Legg til minst 2 linjer")
        ttk.Label(ctrl_frm, textvariable=self._elim_create_hint_var, foreground="#888888").pack(
            side="right", padx=(0, 12),
        )

        # === Aktive elimineringer ===
        ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=4, pady=4)

        elim_frm = ttk.Frame(parent)
        elim_frm.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
        elim_frm.columnconfigure(0, weight=1)
        elim_frm.rowconfigure(1, weight=1)

        bar = ttk.Frame(elim_frm)
        bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(bar, text="Aktive elimineringer").pack(side="left")
        ttk.Button(bar, text="Slett valgt", command=self._on_delete_simple_elim).pack(
            side="right",
        )

        cols_e = ("desc", "lines", "netto", "status")
        tree_e = ttk.Treeview(elim_frm, columns=cols_e, show="headings", height=6)
        tree_e.heading("desc", text="Beskrivelse")
        tree_e.heading("lines", text="Linjer")
        tree_e.heading("netto", text="Netto")
        tree_e.heading("status", text="Status")
        tree_e.column("desc", width=220)
        tree_e.column("lines", width=60, anchor="e")
        tree_e.column("netto", width=100, anchor="e")
        tree_e.column("status", width=80, anchor="center")
        tree_e.tag_configure("balanced", background="#E2F1EB")
        tree_e.tag_configure("unbalanced", background="#FCEBD9")
        tree_e.grid(row=1, column=0, sticky="nsew")
        tree_e.bind("<Delete>", lambda _e: self._on_delete_simple_elim())
        self._tree_simple_elims = tree_e

        sb = ttk.Scrollbar(elim_frm, orient="vertical", command=tree_e.yview)
        tree_e.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns")

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

    def _build_journaler_tab(self, parent: ttk.Frame) -> None:
        """Journaler-fane: manuell + forslagsgenererte journaler."""
        top = ttk.Frame(parent)
        top.pack(fill="x", padx=4, pady=4)
        ttk.Button(top, text="Ny journal", command=self._on_new_journal).pack(side="left")
        ttk.Button(top, text="Slett journal", command=self._on_delete_journal).pack(side="left", padx=(4, 0))

        cols_j = ("name", "kind", "lines", "balance")
        self._tree_journals = ttk.Treeview(parent, columns=cols_j, show="headings", height=6)
        self._tree_journals.heading("name", text="Journal")
        self._tree_journals.heading("kind", text="Type")
        self._tree_journals.heading("lines", text="Linjer")
        self._tree_journals.heading("balance", text="Balanse")
        self._tree_journals.column("name", width=130)
        self._tree_journals.column("kind", width=70)
        self._tree_journals.column("lines", width=50, anchor="e")
        self._tree_journals.column("balance", width=90)
        self._tree_journals.tag_configure("warning", background="#FCEBD9")
        self._tree_journals.tag_configure("done", background="#E2F1EB")
        self._tree_journals.tag_configure("template", background="#FFF8E1")
        self._tree_journals.pack(fill="x", padx=4)
        self._tree_journals.bind("<<TreeviewSelect>>", self._on_journal_select)
        self._tree_journals.bind("<Delete>", lambda e: self._on_delete_journal())

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

        if not client or not year:
            self._status_var.set("Velg klient og aar for aa starte.")
            self._project = None
            self._update_session_tb_button(sess)
            return

        self._lbl_statusbar.configure(text=f"Konsolidering | {client} / {year} | TB-only")

        proj = storage.load_project(client, year)
        if proj is not None:
            self._project = proj
            self._load_company_tbs()
            self._compute_mapping_status()
            self._refresh_company_tree()
            self._refresh_journal_tree()
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
            self._status_var.set(
                f"{client} / {year} — ingen konsolideringsprosjekt. "
                "Importer et selskap for aa starte."
            )

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

    def _get_effective_company_overrides(self, company_id: str) -> dict[str, int]:
        """Hent effektive overstyringer for et selskap.

        For morselskapet: start med Analyse-klientoverstyringer, legg paa
        lokale konsoliderings-overstyringer (som vinner).
        For doetre: kun lokale konsoliderings-overstyringer.
        """
        result: dict[str, int] = {}
        if self._project is None:
            return result

        # For morselskapet: bruk Analyse-overstyringer som base
        if company_id == self._project.parent_company_id:
            try:
                import regnskap_client_overrides
                analyse_overrides = regnskap_client_overrides.load_account_overrides(
                    self._project.client, year=self._project.year,
                )
                result.update(analyse_overrides)
            except Exception:
                pass

        # Lokale konsoliderings-overstyringer vinner
        local = self._project.mapping_config.company_overrides.get(company_id, {})
        result.update(local)
        return result

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
        self._mapped_tbs.clear()
        self._mapping_pct: dict[str, int] = {}
        self._mapping_unmapped: dict[str, list[str]] = {}

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
                total = len(mapped_df)
                mapped_count = mapped_df["regnr"].notna().sum()
                self._mapping_pct[c.company_id] = int(mapped_count * 100 / total) if total > 0 else 0
            except Exception:
                self._mapping_pct[c.company_id] = -1

        # Oppdater enkel eliminering-UI
        if self._tk_ok and hasattr(self, "_elim_cb_rl"):
            self._populate_elim_combos()
            self._refresh_simple_elim_tree()

    # ------------------------------------------------------------------
    # Refresh helpers
    # ------------------------------------------------------------------

    def _update_status(self) -> None:
        if self._project is None:
            return
        nc = len(self._project.companies)
        ne = len(self._project.eliminations)
        last_run = ""
        if self._project.runs:
            from datetime import datetime
            r = self._project.runs[-1]
            last_run = f" | Siste run: {datetime.fromtimestamp(r.run_at).strftime('%H:%M')}"
        self._status_var.set(f"{nc} selskaper | {ne} elimineringer{last_run}")

    def _refresh_company_tree(self) -> None:
        tree = self._tree_companies
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
            if pct < 0:
                mapping_text = "\u2014"
                tag = ()
            elif pct >= 100:
                mapping_text = "100%"
                tag = ("done",)
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
                j.name, kind_label, len(j.lines), bal_text,
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
            self._mapping_tab.set_data(
                company_id,
                effective_raw if effective_raw is not None else tb,
                self._mapped_tbs.get(company_id),
                overrides,
                self._regnskapslinjer,
                self._regnr_to_name,
            )

        self._populate_detail_tree(tb, company_id)

        # Also build per-company result (shown if mode == "Valgt selskap")
        self._build_company_result(company_id)
        if self._result_mode_var.get() == "Valgt selskap":
            self._refresh_result_view()

    def _populate_detail_tree(self, tb: pd.DataFrame, company_id: str) -> None:
        """Fyll detalj-treeview med TB-rader, respekter nullstøy-filter."""
        tree = self._tree_detail
        tree.delete(*tree.get_children())
        unmapped = set(self._mapping_unmapped.get(company_id, []))
        hide_zero = self._detail_hide_zero_var.get()
        total = 0
        shown = 0

        for _, row in tb.iterrows():
            total += 1
            try:
                ib = float(row.get("ib", 0) or 0)
                ub = float(row.get("ub", 0) or 0)
                netto = float(row.get("netto", 0) or 0)
            except (ValueError, TypeError):
                ib = ub = netto = 0.0

            # Filtrer bort rader der alle beloep er 0
            if hide_zero and abs(ib) < 0.005 and abs(ub) < 0.005 and abs(netto) < 0.005:
                continue

            shown += 1
            regnr_raw = row.get("regnr", "")
            try:
                regnr_int = int(regnr_raw) if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan") else None
            except (ValueError, TypeError):
                regnr_int = None
            regnr_display = regnr_int if regnr_int is not None else ""
            rl_navn = self._regnr_to_name.get(regnr_int, "") if regnr_int is not None else ""
            konto = str(row.get("konto", ""))
            tag = ("review",) if konto in unmapped else ()
            tree.insert("", "end", values=(
                konto,
                row.get("kontonavn", ""),
                regnr_display,
                rl_navn,
                _fmt_no(ib, 2),
                _fmt_no(netto, 2),
                _fmt_no(ub, 2),
            ), tags=tag)

        if hide_zero and total > shown:
            self._detail_count_var.set(f"{shown}/{total} linjer (0-linjer skjult)")
        else:
            self._detail_count_var.set(f"{total} linjer")

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
        """Bygg regnskapsoppstilling for valgt selskap og lagre i cache."""
        mapped_tb = self._mapped_tbs.get(company_id)
        if mapped_tb is None or self._regnskapslinjer is None:
            self._company_result_df = None
            return

        try:
            from regnskap_mapping import compute_sumlinjer

            valid = mapped_tb.dropna(subset=["regnr"]).copy()
            if valid.empty:
                self._company_result_df = None
                return
            valid["regnr"] = valid["regnr"].astype(int)
            agg = valid.groupby("regnr")["ub"].sum().to_dict()

            rl = self._regnskapslinjer
            skeleton = rl[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
            skeleton["regnr"] = skeleton["regnr"].astype(int)
            result = skeleton.copy()

            leaf_mask = ~result["sumpost"]
            result["UB"] = result["regnr"].map(lambda r: agg.get(int(r), 0.0))
            result.loc[result["sumpost"], "UB"] = 0.0

            base_values = {
                int(r): float(v)
                for r, v in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, "UB"])
            }
            all_values = compute_sumlinjer(base_values=base_values, regnskapslinjer=rl)
            sum_mask = result["sumpost"]
            result.loc[sum_mask, "UB"] = result.loc[sum_mask, "regnr"].map(
                lambda r, av=all_values: float(av.get(int(r), 0.0))
            )

            self._company_result_df = result.sort_values("regnr").reset_index(drop=True)
        except Exception:
            logger.exception("Failed to build company result for %s", company_id)
            self._company_result_df = None

    def _on_ao_toggled(self) -> None:
        """Refresh all views when AO checkbox is toggled."""
        self._compute_mapping_status()
        self._refresh_company_tree()
        # Refresh current detail/mapping/result if a company is selected
        cid = getattr(self, "_current_detail_cid", None)
        if cid:
            self._show_company_detail(cid)

    def _on_result_mode_changed(self) -> None:
        """Switch between 'Valgt selskap' and 'Konsolidert' in result view."""
        self._refresh_result_view()

    def _refresh_result_view(self) -> None:
        """Populate result tree based on current mode, preview state, and hide-zero.

        P6: preview_elim-kolonne vises kun naar preview er aktiv.
        """
        mode = self._result_mode_var.get()
        if mode == "Konsolidert":
            if self._preview_result_df is not None:
                # Preview aktiv — vis ekstra kolonne
                self._preview_label_var.set("Preview aktiv")
                self._populate_result_tree(
                    self._preview_result_df,
                    ["Mor", "Doetre", "eliminering", "preview_elim", "konsolidert"],
                )
            elif self._consolidated_result_df is not None:
                # Ren resultatvisning uten preview
                self._preview_label_var.set("")
                self._populate_result_tree(
                    self._consolidated_result_df,
                    ["Mor", "Doetre", "eliminering", "konsolidert"],
                )
            else:
                self._show_empty_result("Ingen konsolidering kj\u00f8rt enn\u00e5")
        elif self._company_result_df is not None:
            self._preview_label_var.set("")
            self._populate_result_tree(self._company_result_df, ["UB"])
        else:
            self._show_empty_result("Velg et selskap eller kj\u00f8r konsolidering")

    def _show_empty_result(self, message: str = "") -> None:
        """Vis tom resultat-tree med tilbakestilte kolonner og melding."""
        tree = self._tree_result
        tree.delete(*tree.get_children())
        self._preview_label_var.set("")
        # Tilbakestill til standardkolonner
        default_cols = ("regnr", "regnskapslinje", "info")
        tree["columns"] = default_cols
        tree.heading("regnr", text="Regnr")
        tree.heading("regnskapslinje", text="Regnskapslinje")
        tree.heading("info", text="")
        tree.column("regnr", width=60, anchor="center")
        tree.column("regnskapslinje", width=200)
        tree.column("info", width=300)
        if message:
            tree.insert("", "end", values=("", "", message))

    def _populate_result_tree(
        self, result_df: pd.DataFrame, data_cols: list[str] | None = None,
    ) -> None:
        """Populate the result treeview from a regnskapsoppstilling DataFrame."""
        tree = self._tree_result
        tree.delete(*tree.get_children())

        meta_cols = {"regnr", "regnskapslinje", "sumpost", "formel"}
        if data_cols is None:
            data_cols = [c for c in result_df.columns if c not in meta_cols]
        all_cols = ["regnr", "regnskapslinje"] + data_cols

        _col_labels = {
            "Mor": "Mor", "Doetre": "D\u00f8tre",
            "eliminering": "Eliminering", "konsolidert": "Konsolidert",
            "preview_elim": "Preview elim.",
        }

        tree["columns"] = all_cols
        tree.heading("regnr", text="Nr")
        tree.heading("regnskapslinje", text="Regnskapslinje")
        tree.column("regnr", width=50, anchor="e")
        tree.column("regnskapslinje", width=160, anchor="w")
        for dc in data_cols:
            tree.heading(dc, text=_col_labels.get(dc, dc))
            tree.column(dc, width=100, anchor="e")

        hide_zero = self._hide_zero_var.get()

        for _, row in result_df.iterrows():
            is_sum = bool(row.get("sumpost", False))

            # Collect numeric values
            num_vals: list[float] = []
            for dc in data_cols:
                v = row.get(dc, 0.0)
                num_vals.append(float(v) if pd.notna(v) else 0.0)

            # Hide zero lines (non-sum lines where all data cols are ~0)
            if hide_zero and not is_sum:
                if all(abs(v) < 0.005 for v in num_vals):
                    continue

            vals: list = [int(row["regnr"]), row["regnskapslinje"]]
            any_neg = False
            for fv in num_vals:
                vals.append(_fmt_no(fv, 2))
                if fv < -0.005:
                    any_neg = True

            tags = []
            if is_sum:
                tags.append("sumline")
            if any_neg and not is_sum:
                tags.append("neg")
            tree.insert("", "end", values=vals, tags=tuple(tags))

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
        self._result_mode_var.set("Konsolidert")
        self._refresh_result_view()
        self._right_nb.select(2)  # Resultat is tab index 2 (after Detalj, Mapping)

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

    def _on_company_right_click(self, event) -> None:
        iid = self._tree_companies.identify_row(event.y)
        if iid:
            self._tree_companies.selection_set(iid)
            self._company_menu.post(event.x_root, event.y_root)

    def _on_detail_right_click(self, event) -> None:
        iid = self._tree_detail.identify_row(event.y)
        if iid:
            # Add to selection (don't replace) so multi-select works with right-click
            if iid not in self._tree_detail.selection():
                self._tree_detail.selection_set(iid)
            self._detail_menu.post(event.x_root, event.y_root)

    def _on_detail_double_click(self, event) -> None:
        iid = self._tree_detail.identify_row(event.y)
        if iid:
            if iid not in self._tree_detail.selection():
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
        selected_kontos: list[tuple[str, str, str]] = []  # (konto, kontonavn, current_regnr)
        for iid in sel_detail:
            vals = self._tree_detail.item(iid, "values")
            if vals:
                selected_kontos.append((
                    str(vals[0]),
                    str(vals[1]),
                    str(vals[2]) if vals[2] else "",
                ))

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
        self._compute_mapping_status()
        self._refresh_company_tree()
        self._show_company_detail(company_id)

    def _on_mapping_overrides_changed(self, company_id: str, new_overrides: dict[str, int]) -> None:
        """Callback from MappingTab when overrides are changed."""
        if self._project is None:
            return

        # Update project overrides
        if new_overrides:
            self._project.mapping_config.company_overrides[company_id] = new_overrides
        else:
            self._project.mapping_config.company_overrides.pop(company_id, None)

        self._project.touch()
        storage.save_project(self._project)

        # Re-map the company
        raw_tb = self._company_tbs.get(company_id)
        if raw_tb is not None and self._intervals is not None and self._regnskapslinjer is not None:
            try:
                from consolidation.mapping import map_company_tb
                mapped_df, unmapped_list = map_company_tb(
                    raw_tb, new_overrides or None,
                    intervals=self._intervals,
                    regnskapslinjer=self._regnskapslinjer,
                )
                self._mapped_tbs[company_id] = mapped_df
                self._mapping_unmapped[company_id] = unmapped_list
                total = len(mapped_df)
                mapped_count = mapped_df["regnr"].notna().sum()
                self._mapping_pct[company_id] = int(mapped_count * 100 / total) if total > 0 else 0
            except Exception:
                logger.exception("Re-mapping failed for %s", company_id)

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
            self._left_nb.select(0)  # Ensure Selskaper tab is visible
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
        """Vis sum foer elim for valgt regnskapslinje."""
        rn = self._parse_regnr_from_combo(self._elim_line_var.get())
        if rn is not None:
            amt = self._get_sum_foer_elim(rn)
            self._elim_line_sum_var.set(
                f"Sum: {_fmt_no(amt)}" if amt is not None else "(kjoer konsolidering foerst)",
            )
        else:
            self._elim_line_sum_var.set("")

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

        # Clear line input fields for next entry
        self._elim_amount_var.set("")
        self._elim_line_var.set("")
        self._elim_line_desc_var.set("")
        self._elim_line_sum_var.set("")

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
        self._refresh_draft_tree()

    def _refresh_draft_tree(self) -> None:
        """Oppdater utkast-treet, kontrollsummer og opprett-knapp."""
        tree = self._tree_draft_lines
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

    def _on_create_simple_elim(self) -> None:
        """Opprett eliminering fra utkastlinjene."""
        if len(self._draft_lines) < 2:
            return
        netto = sum(d["amount"] for d in self._draft_lines)
        if abs(netto) >= 0.005:
            return

        desc = self._elim_desc_var.get().strip()
        if not desc:
            regnrs = [d["regnr"] for d in self._draft_lines]
            desc = "Elim " + " / ".join(str(r) for r in regnrs)

        proj = self._ensure_project()
        lines = [
            EliminationLine(regnr=d["regnr"], amount=d["amount"], description=d.get("desc", ""))
            for d in self._draft_lines
        ]
        journal = EliminationJournal(name=desc, kind="manual", lines=lines)
        proj.eliminations.append(journal)
        storage.save_project(proj)

        # Toemm utkast og skjema
        self._draft_lines.clear()
        self._draft_edit_idx = None
        self._refresh_draft_tree()
        self._elim_desc_var.set("")
        self._elim_line_desc_var.set("")

        # Oppdater UI
        self._refresh_simple_elim_tree()
        self._refresh_journal_tree()
        self._update_status()

        # Re-kjoer konsolidering automatisk
        self._clear_preview()
        self._ensure_consolidated_result()

    def _on_delete_simple_elim(self) -> None:
        """Slett valgt eliminering fra oversikten."""
        sel = self._tree_simple_elims.selection()
        if not sel or self._project is None:
            return
        jid = sel[0]
        journal = self._project.find_journal(jid)
        if journal is None:
            return
        self._project.eliminations.remove(journal)
        storage.save_project(self._project)
        self._refresh_simple_elim_tree()
        self._refresh_journal_tree()
        self._update_status()

        # Re-kjoer konsolidering automatisk
        self._clear_preview()
        self._ensure_consolidated_result()

    def _refresh_simple_elim_tree(self) -> None:
        """Oppdater oversikten over aktive elimineringer."""
        tree = self._tree_simple_elims
        tree.delete(*tree.get_children())
        if self._project is None:
            return
        for j in self._project.eliminations:
            netto = j.net
            status = "Balansert" if j.is_balanced else f"Netto {_fmt_no(netto, 2)}"
            tags = ("balanced",) if j.is_balanced else ("unbalanced",)
            tree.insert(
                "", "end", iid=j.journal_id,
                values=(j.name, len(j.lines), _fmt_no(netto, 2), status),
                tags=tags,
            )

    def _on_new_journal(self) -> None:
        name = simpledialog.askstring(
            "Ny elimineringsjournal",
            "Journalnavn:",
            initialvalue="Ny eliminering",
        )
        if not name:
            return

        proj = self._ensure_project()
        journal = EliminationJournal(name=name)
        proj.eliminations.append(journal)
        storage.save_project(proj)
        self._refresh_journal_tree()
        self._update_status()

    def _on_delete_journal(self) -> None:
        sel = self._tree_journals.selection()
        if not sel or self._project is None:
            return
        jid = sel[0]
        journal = self._project.find_journal(jid)
        if journal is None:
            return
        if not messagebox.askyesno("Slett journal", f"Slett '{journal.name}'?"):
            return
        self._project.eliminations = [
            j for j in self._project.eliminations if j.journal_id != jid
        ]
        storage.save_project(self._project)
        self._refresh_journal_tree()
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
            tab_idx = 2  # Forslag=0, Journaler=1, Valuta=2
            if self._has_foreign_currency():
                self._elim_nb.tab(tab_idx, state="normal")
            else:
                # Skjul ikke helt — demp visuelt ved aa sette state=hidden
                # Brukeren kan fortsatt navigere dit via andre metoder
                self._elim_nb.tab(tab_idx, state="hidden")
        except Exception:
            pass

    def _refresh_fx_tree(self) -> None:
        tree = self._tree_fx_rates
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

        from consolidation.engine import run_consolidation
        from consolidation.mapping import ConfigNotLoadedError

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

        self._result_df = result_df
        self._project.runs.append(run_result)
        storage.save_project(self._project)

        if run_result.warnings:
            messagebox.showwarning("Advarsler", "\n".join(run_result.warnings))

        self._show_result(result_df)
        self._update_status()

    def _prepare_tbs_for_run(self) -> dict[str, pd.DataFrame]:
        """Forbered TBer for konsolidering, inkludert AO-justeringer."""
        return self._get_effective_tbs()

    def _on_export(self) -> None:
        if self._result_df is None or self._project is None:
            messagebox.showwarning("Eksport", "Kjoer konsolidering foerst.")
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

        run_result = self._project.runs[-1] if self._project.runs else None
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
