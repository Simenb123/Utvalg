"""Shell/UI builders for the consolidation page."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from .mapping_tab import MappingTab
from .common import DETAIL_TB_COLUMN_SPECS
from treeview_column_manager import TreeviewColumnManager
from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview

if TYPE_CHECKING:
    from .page import ConsolidationPage


def build_ui(page: "ConsolidationPage") -> None:
    from src.shared.ui.page_header import PageHeader

    page.columnconfigure(0, weight=1)
    page.rowconfigure(3, weight=1)

    header = PageHeader(
        page,
        title="Konsolidering",
        subtitle="Konsernregnskap fra datterselskaper",
    )
    header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 0))
    header.set_refresh(
        command=lambda: page.refresh_from_session(__import__("session")),
        key="<F5>",
    )
    page._page_header = header

    # Side-spesifikk toolbar under headeren — beholder import-meny, Kjør,
    # ÅO-toggle og statusvisning. Eksport-knappen er flyttet til PageHeader.
    toolbar = ttk.Frame(page)
    toolbar.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 0))

    page._import_menu_btn = ttk.Menubutton(toolbar, text="Importer grunnlag")
    page._import_menu_btn.pack(side="left", padx=(0, 4))
    page._import_menu = tk.Menu(page._import_menu_btn, tearoff=0)
    page._import_menu.add_command(label="Importer saldobalanse (TB)", command=page._on_import_company)
    page._import_menu.add_command(label="Importer fra klientliste (aktiv SB)", command=page._on_import_company_from_client_list)
    page._import_menu.add_command(label="Importer regnskapslinjer (Excel/CSV)", command=page._on_import_company_lines)
    page._import_menu.add_command(label="Importer fra PDF-regnskap (assistert)", command=page._on_import_company_pdf)
    page._import_menu.add_separator()
    page._import_menu.add_command(label="Eksporter regnskapslinje-mal", command=page._on_export_company_line_template)
    page._import_menu_btn.configure(menu=page._import_menu)

    page._btn_use_session_tb = ttk.Button(toolbar, text="Bruk aktiv klient som mor", command=page._on_use_session_tb)
    page._btn_use_session_tb.pack(side="left", padx=(0, 4))
    page._btn_use_session_tb.pack_forget()

    page._btn_run = ttk.Button(toolbar, text="Kjoer konsolidering", command=page._on_run)
    page._btn_run.pack(side="left", padx=(0, 4))
    # _btn_export beholdes som no-op-attributt for bakoverkomp; eksport
    # går nå via PageHeader.add_export.
    header.add_export("Konsolidert resultat", command=page._on_export)
    page._btn_export = page._btn_run  # placeholder ref — kjøremåten er menyen i header

    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8, pady=2)
    page._include_ao_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(
        toolbar,
        text="Inkl. AO (mor)",
        variable=page._include_ao_var,
        command=page._on_ao_toggled,
    ).pack(side="left", padx=(0, 8))
    ttk.Label(toolbar, textvariable=page._status_var).pack(side="left")

    readiness_strip = ttk.Frame(page)
    readiness_strip.grid(row=2, column=0, sticky="ew", padx=8, pady=(4, 0))
    ttk.Label(readiness_strip, textvariable=page._readiness_status_var, anchor="w").pack(fill="x")

    page._main_pw = ttk.PanedWindow(page, orient="horizontal")
    page._right_panel_visible = True
    page._main_pw.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)

    page._left_nb = ttk.Notebook(page._main_pw)
    page._left_tab_companies = ttk.Frame(page._left_nb)
    page._left_nb.add(page._left_tab_companies, text="Selskaper")
    page._tree_companies = page._make_company_tree(page._left_tab_companies)

    page._left_tab_controls = ttk.Frame(page._left_nb)
    page._left_nb.add(page._left_tab_controls, text="Kontroller")
    page._build_controls_tab(page._left_tab_controls)

    page._left_tab_elim = ttk.Frame(page._left_nb)
    page._left_nb.add(page._left_tab_elim, text="Eliminering")
    page._build_elimination_tab(page._left_tab_elim)

    page._left_tab_grunnlag = ttk.Frame(page._left_nb)
    page._left_nb.add(page._left_tab_grunnlag, text="Grunnlag")
    page._build_grunnlag_tab(page._left_tab_grunnlag)
    page._left_nb.bind("<<NotebookTabChanged>>", page._on_left_tab_changed)
    page._main_pw.add(page._left_nb, weight=3)

    page._right_nb = ttk.Notebook(page._main_pw)
    page._right_tab_detail = ttk.Frame(page._right_nb)
    page._right_nb.add(page._right_tab_detail, text="Detalj")

    detail_toolbar = ttk.Frame(page._right_tab_detail)
    detail_toolbar.pack(side="top", fill="x", padx=4, pady=(4, 0))
    page._detail_hide_zero_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(
        detail_toolbar,
        text="Kun linjer med verdi",
        variable=page._detail_hide_zero_var,
        command=page._on_detail_filter_changed,
    ).pack(side="left")
    page._detail_meta_var = tk.StringVar(value="")
    ttk.Label(detail_toolbar, textvariable=page._detail_meta_var).pack(side="left", padx=(12, 0))
    page._detail_count_var = tk.StringVar(value="")
    ttk.Label(detail_toolbar, textvariable=page._detail_count_var).pack(side="right")
    page._tree_detail = page._make_detail_tree(page._right_tab_detail)

    page._mapping_tab = MappingTab(page._right_nb, on_overrides_changed=page._on_mapping_overrides_changed)
    page._right_tab_mapping = page._mapping_tab
    page._right_nb.add(page._mapping_tab, text="Mapping")

    page._right_tab_result = ttk.Frame(page._right_nb)
    page._right_nb.add(page._right_tab_result, text="Resultat")
    page._build_result_tab(page._right_tab_result)
    page._main_pw.add(page._right_nb, weight=5)
    page._update_workspace_layout()

    status_bar = ttk.Frame(page)
    status_bar.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 4))
    page._lbl_statusbar = ttk.Label(status_bar, text="Konsolidering | TB-only", anchor="w")
    page._lbl_statusbar.pack(fill="x")


def select_left_tab(page: "ConsolidationPage", fallback_index: int, tab_ref_attr: str) -> None:
    nb = getattr(page, "_left_nb", None)
    if nb is None:
        return
    tab_ref = getattr(page, tab_ref_attr, None)
    try:
        nb.select(tab_ref if tab_ref is not None else fallback_index)
    except Exception:
        pass
    page._update_workspace_layout()


def select_right_tab(page: "ConsolidationPage", fallback_index: int, tab_ref_attr: str) -> None:
    nb = getattr(page, "_right_nb", None)
    if nb is None:
        return
    tab_ref = getattr(page, tab_ref_attr, None)
    try:
        nb.select(tab_ref if tab_ref is not None else fallback_index)
    except Exception:
        pass


def select_elim_tab(page: "ConsolidationPage", fallback_index: int, tab_ref_attr: str) -> None:
    nb = getattr(page, "_elim_nb", None)
    if nb is None:
        return
    tab_ref = getattr(page, tab_ref_attr, None)
    try:
        nb.select(tab_ref if tab_ref is not None else fallback_index)
    except Exception:
        pass
    page._update_workspace_layout()


def is_associate_workspace_active(page: "ConsolidationPage") -> bool:
    left_nb = getattr(page, "_left_nb", None)
    elim_nb = getattr(page, "_elim_nb", None)
    left_elim = getattr(page, "_left_tab_elim", None)
    elim_associates = getattr(page, "_elim_tab_associates", None)
    if left_nb is None or elim_nb is None or left_elim is None or elim_associates is None:
        return False
    try:
        return str(left_nb.select()) == str(left_elim) and str(elim_nb.select()) == str(elim_associates)
    except Exception:
        return False


def update_workspace_layout(page: "ConsolidationPage") -> None:
    pw = getattr(page, "_main_pw", None)
    right_nb = getattr(page, "_right_nb", None)
    if pw is None or right_nb is None:
        return
    try:
        panes = [str(pane) for pane in pw.panes()]
    except Exception:
        return

    right_visible = str(right_nb) in panes
    associate_active = page._is_associate_workspace_active()
    if associate_active and right_visible:
        try:
            pw.forget(right_nb)
            page._right_panel_visible = False
        except Exception:
            return
    elif not associate_active and not right_visible:
        try:
            pw.add(right_nb, weight=5)
            page._right_panel_visible = True
        except Exception:
            return


def on_left_tab_changed(page: "ConsolidationPage", _event=None) -> None:
    page._update_workspace_layout()


def on_elim_tab_changed(page: "ConsolidationPage", _event=None) -> None:
    page._update_workspace_layout()


def make_company_tree(page: "ConsolidationPage", parent: ttk.Frame) -> ttk.Treeview:
    tree = ttk.Treeview(parent, columns=("name", "source", "rows", "mapping"), show="headings", selectmode="browse")
    tree.heading("name", text="Selskap")
    tree.heading("source", text="Import")
    tree.heading("rows", text="Grunnlag")
    tree.heading("mapping", text="Status")
    tree.column("name", width=160)
    tree.column("source", width=110)
    tree.column("rows", width=95, anchor="w")
    tree.column("mapping", width=115)
    tree.tag_configure("done", background="#E2F1EB")
    tree.tag_configure("review", background="#FCEBD9")

    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.bind("<<TreeviewSelect>>", page._on_company_select)
    tree.bind("<Delete>", page._on_delete_company)
    tree.bind("<Return>", page._on_company_select)

    page._company_menu = tk.Menu(tree, tearoff=0)
    page._company_menu.add_command(label="Vis detalj", command=page._on_company_select)
    page._company_menu.add_command(label="Sett som morselskap", command=page._on_set_parent)
    page._company_menu.add_command(label="Hent fra klientliste", command=page._on_import_selected_company_from_client_list)
    page._company_menu.add_command(label="Importer paa nytt", command=page._on_reimport_company)
    page._company_menu.add_command(label="Vis umappede", command=page._on_show_unmapped)
    page._company_menu.add_separator()
    page._company_menu.add_command(label="Slett selskap", command=page._on_delete_company)
    page._companies_tree_mgr = ManagedTreeview(
        tree,
        view_id="companies",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("name", "Selskap", width=160, pinned=True, stretch=True),
            ColumnSpec("source", "Import", width=110),
            ColumnSpec("rows", "Grunnlag", width=95),
            ColumnSpec("mapping", "Status", width=115),
        ],
        on_body_right_click=page._on_company_right_click,
    )
    page._companies_col_mgr = page._companies_tree_mgr.column_manager
    return tree


def build_controls_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    toolbar = ttk.Frame(parent)
    toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
    toolbar.columnconfigure(0, weight=1)
    page._readiness_summary_var = tk.StringVar(value="Ingen kontroller kjoert ennaa.")
    ttk.Label(toolbar, textvariable=page._readiness_summary_var).grid(row=0, column=0, sticky="w")
    ttk.Button(toolbar, text="Aapne valgt", command=page._open_selected_readiness_issue).grid(
        row=0,
        column=1,
        sticky="e",
        padx=(8, 0),
    )

    tree_frame = ttk.Frame(parent)
    tree_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
    tree_frame.columnconfigure(0, weight=1)
    tree_frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(
        tree_frame,
        columns=("severity", "category", "company", "message", "action"),
        show="headings",
        selectmode="browse",
    )
    tree.grid(row=0, column=0, sticky="nsew")
    sb = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    sb.grid(row=0, column=1, sticky="ns")
    tree.configure(yscrollcommand=sb.set)
    tree.tag_configure("blocking", background="#FCE4E4")
    tree.tag_configure("warning", background="#FFF4D6")
    tree.tag_configure("info", background="#E9F2FF")
    page._tree_controls = tree
    page._readiness_issue_map = {}
    page._controls_tree_mgr = ManagedTreeview(
        tree,
        view_id="consolidation.controls",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("severity", "Nivaa", width=90, pinned=True),
            ColumnSpec("category", "Kategori", width=100, pinned=True),
            ColumnSpec("company", "Selskap", width=150, stretch=True),
            ColumnSpec("message", "Melding", width=360, stretch=True),
            ColumnSpec("action", "Handling", width=120),
        ],
    )
    tree.bind("<Double-1>", lambda _e=None: page._open_selected_readiness_issue())


def make_detail_tree(page: "ConsolidationPage", parent: ttk.Frame) -> ttk.Treeview:
    cols = ("konto", "kontonavn", "regnr", "rl_navn", "ib", "netto", "ub")
    tree = ttk.Treeview(parent, columns=cols, show="headings", selectmode="extended")
    headings = {
        "konto": "Konto",
        "kontonavn": "Kontonavn",
        "regnr": "Regnr",
        "rl_navn": "Regnskapslinje",
        "ib": "IB",
        "netto": "Bevegelse",
        "ub": "UB",
    }
    for col in cols:
        tree.heading(col, text=headings.get(col, col.capitalize()))
        width = {"konto": 80, "kontonavn": 140, "regnr": 55, "rl_navn": 150}.get(col, 80)
        anchor = "w" if col in ("kontonavn", "rl_navn") else "e"
        tree.column(col, width=width, anchor=anchor)
    tree.tag_configure("review", background="#FCEBD9")
    tree.tag_configure("approved", background="#E2F1EB")

    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.bind("<Control-c>", lambda _e: page._copy_tree_to_clipboard(tree))
    tree.bind("<Double-1>", page._on_detail_double_click)

    page._detail_menu = tk.Menu(tree, tearoff=0)
    page._detail_menu.add_command(label="Endre regnskapslinje...", command=page._on_change_mapping)
    page._detail_tree_mgr = ManagedTreeview(
        tree,
        view_id="detail",
        pref_prefix="ui",
        column_specs=DETAIL_TB_COLUMN_SPECS,
        on_body_right_click=page._on_detail_right_click,
    )
    page._detail_col_mgr = page._detail_tree_mgr.column_manager
    page._detail_tree_mode = "tb"
    return tree


def build_result_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    toolbar = ttk.Frame(parent)
    toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))

    ttk.Label(toolbar, text="Visning:").pack(side="left", padx=(0, 4))
    page._result_mode_var = tk.StringVar(value="company")
    mode_combo = ttk.Combobox(
        toolbar,
        textvariable=page._result_mode_var,
        values=["Valgt selskap", "Konsolidert", "Per selskap"],
        state="readonly",
        width=16,
    )
    mode_combo.set("Valgt selskap")
    mode_combo.pack(side="left", padx=(0, 12))
    mode_combo.bind("<<ComboboxSelected>>", lambda _e: page._on_result_mode_changed())
    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

    page._col_before_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(toolbar, text="Foer omr.", variable=page._col_before_var, command=page._on_result_mode_changed).pack(side="left", padx=(0, 4))
    page._col_kurs_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(toolbar, text="Kurs", variable=page._col_kurs_var, command=page._on_result_mode_changed).pack(side="left", padx=(0, 4))
    page._col_fx_effect_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(toolbar, text="Valutaeffekt", variable=page._col_fx_effect_var, command=page._on_result_mode_changed).pack(side="left", padx=(0, 8))
    ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)
    page._hide_zero_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(toolbar, text="Kun m/verdi", variable=page._hide_zero_var, command=page._on_result_mode_changed).pack(side="left")

    page._preview_label_var = tk.StringVar(value="")
    page._preview_label = ttk.Label(toolbar, textvariable=page._preview_label_var, foreground="#0066CC")
    page._preview_label.pack(side="right")

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
    tree.bind("<Control-c>", lambda _e: page._copy_tree_to_clipboard(tree))
    tree.bind("<<TreeviewSelect>>", page._on_result_line_select)
    tree.bind("<Button-3>", page._on_result_right_click)
    page._tree_result = tree
    pinned_cols = ("regnr", "regnskapslinje")
    page._result_col_mgrs = {
        key: TreeviewColumnManager(tree, view_id=f"result.{key}", all_cols=(), pinned_cols=pinned_cols)
        for key in ("company", "consolidated", "per_company")
    }
    page._company_result_df = None
    page._consolidated_result_df = None
    page._preview_result_df = None


def build_grunnlag_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    toolbar = ttk.Frame(parent)
    toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 2))
    page._grunnlag_label_var = tk.StringVar(value="Velg regnskapslinje i Resultat")
    ttk.Label(toolbar, textvariable=page._grunnlag_label_var).pack(side="left")

    tree_frm = ttk.Frame(parent)
    tree_frm.grid(row=1, column=0, sticky="nsew")
    cols = (
        "selskap",
        "konto",
        "kontonavn",
        "regnr",
        "regnskapslinje",
        "ib",
        "bevegelse",
        "ub_original",
        "valuta",
        "kurs",
        "ub_konvertert",
        "valutaeffekt",
    )
    headings = {
        "selskap": "Selskap",
        "konto": "Konto",
        "kontonavn": "Kontonavn",
        "regnr": "Regnr",
        "regnskapslinje": "Regnskapslinje",
        "ib": "IB",
        "bevegelse": "Bevegelse",
        "ub_original": "Beloep foer",
        "valuta": "Valuta",
        "kurs": "Kurs",
        "ub_konvertert": "Beloep etter",
        "valutaeffekt": "Valutaeffekt",
    }
    widths = {
        "selskap": 120,
        "konto": 70,
        "kontonavn": 140,
        "regnr": 50,
        "regnskapslinje": 120,
        "ib": 80,
        "bevegelse": 80,
        "ub_original": 90,
        "valuta": 50,
        "kurs": 55,
        "ub_konvertert": 90,
        "valutaeffekt": 85,
    }
    tree = ttk.Treeview(tree_frm, columns=cols, show="headings", selectmode="browse")
    for col in cols:
        tree.heading(col, text=headings.get(col, col))
        anchor = "w" if col in ("selskap", "kontonavn", "regnskapslinje", "valuta") else "e"
        tree.column(col, width=widths.get(col, 80), anchor=anchor)
    tree.tag_configure("neg", foreground="red")
    sb = ttk.Scrollbar(tree_frm, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    tree.bind("<Control-c>", lambda _e: page._copy_tree_to_clipboard(tree))
    page._tree_grunnlag = tree
    page._grunnlag_tree_mgr = ManagedTreeview(
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
            ColumnSpec("ub_original", "Beloep foer", width=90, anchor="e"),
            ColumnSpec("valuta", "Valuta", width=50),
            ColumnSpec("kurs", "Kurs", width=55, anchor="e"),
            ColumnSpec("ub_konvertert", "Beloep etter", width=90, anchor="e"),
            ColumnSpec("valutaeffekt", "Valutaeffekt", width=85, anchor="e"),
        ],
    )
    page._grunnlag_col_mgr = page._grunnlag_tree_mgr.column_manager


def on_result_line_select(page: "ConsolidationPage", event=None) -> None:
    sel = page._tree_result.selection()
    if not sel:
        return
    item = sel[0]
    vals = page._tree_result.item(item, "values")
    tags = page._tree_result.item(item, "tags")
    if not vals:
        return
    try:
        regnr = int(vals[0])
    except (TypeError, ValueError):
        return
    page._populate_grunnlag(regnr, is_sumpost="sumline" in tags or "sumline_major" in tags)
    page._select_left_tab(2, "_left_tab_grunnlag")
