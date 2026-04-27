"""UI builders for elimination-related consolidation tabs."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview

if TYPE_CHECKING:
    from .page import ConsolidationPage


def build_elimination_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)
    page._elim_nb = ttk.Notebook(parent)
    page._elim_nb.grid(row=0, column=0, sticky="nsew")

    page._elim_tab_simple = ttk.Frame(page._elim_nb)
    page._elim_nb.add(page._elim_tab_simple, text="Eliminering")
    page._build_enkel_elim_tab(page._elim_tab_simple)

    page._elim_tab_journals = ttk.Frame(page._elim_nb)
    page._elim_nb.add(page._elim_tab_journals, text="Journaler")
    page._build_journaler_tab(page._elim_tab_journals)

    page._elim_tab_suggestions = ttk.Frame(page._elim_nb)
    page._elim_nb.add(page._elim_tab_suggestions, text="Forslag")
    page._build_forslag_tab(page._elim_tab_suggestions)

    page._elim_tab_fx = ttk.Frame(page._elim_nb)
    page._elim_nb.add(page._elim_tab_fx, text="Valuta")
    page._build_valuta_tab(page._elim_tab_fx)

    page._elim_tab_associates = ttk.Frame(page._elim_nb)
    page._elim_nb.add(page._elim_tab_associates, text="Tilknyttede")
    page._build_associate_cases_tab(page._elim_tab_associates)
    page._elim_nb.bind("<<NotebookTabChanged>>", page._on_elim_tab_changed)


def build_enkel_elim_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    parent.rowconfigure(4, weight=2)

    form = ttk.LabelFrame(parent, text="Bilag - legg til linjer", padding=8)
    form.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
    form.columnconfigure(1, weight=1)
    page._draft_source_journal_id = None
    page._draft_voucher_no = 1
    page._elim_mode_var = tk.StringVar(value="Nytt bilag")
    page._elim_voucher_var = tk.StringVar(value="Bilag nr: 1")
    page._elim_save_btn_var = tk.StringVar(value="Opprett bilag")

    header = ttk.Frame(form)
    header.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
    header.columnconfigure(0, weight=1)
    ttk.Label(header, textvariable=page._elim_mode_var).grid(row=0, column=0, sticky="w")
    ttk.Label(header, textvariable=page._elim_voucher_var).grid(row=0, column=1, sticky="w", padx=(12, 0))
    header_btns = ttk.Frame(header)
    header_btns.grid(row=0, column=2, sticky="e")
    ttk.Button(header_btns, text="Nytt bilag", command=page._begin_new_elim_draft).pack(side="left")
    page._btn_create_elim = ttk.Button(
        header_btns,
        textvariable=page._elim_save_btn_var,
        command=page._on_create_simple_elim,
        state="disabled",
    )
    page._btn_create_elim.pack(side="left", padx=(4, 0))
    ttk.Button(header_btns, text="Nullstill utkast", command=page._on_draft_clear).pack(side="left", padx=(4, 0))

    page._elim_desc_var = tk.StringVar()
    page._elim_level_var = tk.StringVar(value="regnr")
    level_frm = ttk.Frame(form)
    level_frm.grid(row=1, column=0, sticky="w", pady=2)
    ttk.Radiobutton(level_frm, text="Regnskapslinje", variable=page._elim_level_var, value="regnr", command=page._on_elim_level_changed).pack(side="left")
    ttk.Radiobutton(level_frm, text="Konto (SB)", variable=page._elim_level_var, value="konto", command=page._on_elim_level_changed).pack(side="left", padx=(6, 0))

    page._elim_line_var = tk.StringVar()
    page._elim_cb_rl = ttk.Combobox(form, textvariable=page._elim_line_var, width=60)
    page._elim_cb_rl.grid(row=1, column=1, sticky="ew", padx=(4, 0), pady=2)
    page._elim_cb_rl.bind("<<ComboboxSelected>>", lambda _e: page._on_elim_line_selected())
    page._elim_cb_rl.bind("<KeyRelease>", page._on_elim_combo_filter)

    rl_btn_frm = ttk.Frame(form)
    rl_btn_frm.grid(row=1, column=2, padx=(4, 0))
    page._elim_line_sum_var = tk.StringVar(value="")
    ttk.Label(rl_btn_frm, textvariable=page._elim_line_sum_var, foreground="#666666").pack(side="left", padx=(0, 6))
    ttk.Button(rl_btn_frm, text="Fra Resultat", command=page._on_use_result_rl).pack(side="left")

    ttk.Label(form, text="Beloep:").grid(row=2, column=0, sticky="w", pady=2)
    amt_frm = ttk.Frame(form)
    amt_frm.grid(row=2, column=1, sticky="w", padx=(4, 0), pady=2)
    page._elim_amount_var = tk.StringVar()
    page._elim_amount_entry = ttk.Entry(amt_frm, textvariable=page._elim_amount_var, width=18)
    page._elim_amount_entry.pack(side="left")
    page._elim_amount_entry.bind("<Return>", lambda _e: page._on_draft_add_line())
    ttk.Label(amt_frm, text="(positiv = debet, negativ = kredit)", foreground="#888888").pack(side="left", padx=(8, 0))

    ttk.Label(form, text="Linjebeskrivelse:").grid(row=3, column=0, sticky="w", pady=2)
    page._elim_line_desc_var = tk.StringVar()
    desc_entry = ttk.Entry(form, textvariable=page._elim_line_desc_var, width=40)
    desc_entry.grid(row=3, column=1, sticky="ew", padx=(4, 0), pady=2)
    desc_entry.bind("<Return>", lambda _e: page._on_draft_add_line())

    btn_frm = ttk.Frame(form)
    btn_frm.grid(row=4, column=0, columnspan=3, sticky="w", pady=(8, 0))
    ttk.Button(btn_frm, text="Legg til linje", command=page._on_draft_add_line).pack(side="left")
    ttk.Button(btn_frm, text="Rediger valgt", command=page._on_draft_edit_line).pack(side="left", padx=(4, 0))
    ttk.Button(btn_frm, text="Fjern valgt linje", command=page._on_draft_remove_line).pack(side="left", padx=(4, 0))

    draft_frm = ttk.Frame(parent)
    draft_frm.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 2))
    draft_frm.columnconfigure(0, weight=1)
    draft_frm.rowconfigure(0, weight=1)
    page._tree_draft_lines = ttk.Treeview(draft_frm, columns=("regnr", "regnskapslinje", "debet", "kredit", "desc"), show="headings", height=5)
    for col, text, width, anchor in (
        ("regnr", "Regnr", 60, "e"),
        ("regnskapslinje", "Regnskapslinje", 200, "w"),
        ("debet", "Debet", 100, "e"),
        ("kredit", "Kredit", 100, "e"),
        ("desc", "Beskrivelse", 180, "w"),
    ):
        page._tree_draft_lines.heading(col, text=text)
        page._tree_draft_lines.column(col, width=width, anchor=anchor)
    page._tree_draft_lines.bind("<Delete>", lambda _e: page._on_draft_remove_line())
    page._tree_draft_lines.bind("<Double-1>", lambda _e: page._on_draft_edit_line())
    page._tree_draft_lines.grid(row=0, column=0, sticky="nsew")
    sb_d = ttk.Scrollbar(draft_frm, orient="vertical", command=page._tree_draft_lines.yview)
    page._tree_draft_lines.configure(yscrollcommand=sb_d.set)
    sb_d.grid(row=0, column=1, sticky="ns")
    page._draft_tree_mgr = ManagedTreeview(
        page._tree_draft_lines,
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
    page._draft_col_mgr = page._draft_tree_mgr.column_manager
    page._draft_lines = []
    page._draft_edit_idx = None

    ctrl_frm = ttk.Frame(parent)
    ctrl_frm.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 2))
    page._elim_ctrl_var = tk.StringVar(value="")
    ttk.Label(ctrl_frm, textvariable=page._elim_ctrl_var, foreground="#444444").pack(side="left")
    page._elim_create_hint_var = tk.StringVar(value="Legg til minst 2 linjer")
    ttk.Label(ctrl_frm, textvariable=page._elim_create_hint_var, foreground="#888888").pack(side="right")

    ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=4, pady=4)
    elim_frm = ttk.Frame(parent)
    elim_frm.grid(row=4, column=0, sticky="nsew", padx=4, pady=(0, 4))
    elim_frm.columnconfigure(0, weight=1)
    elim_frm.rowconfigure(1, weight=1)
    elim_frm.rowconfigure(3, weight=1)
    bar = ttk.Frame(elim_frm)
    bar.grid(row=0, column=0, sticky="ew")
    ttk.Label(bar, text="Lagrede bilag").pack(side="left")
    ttk.Button(bar, text="Slett valgt", command=page._on_delete_simple_elim).pack(side="right")
    ttk.Button(bar, text="Kopier til utkast", command=page._on_copy_journal_to_draft).pack(side="right", padx=(0, 4))
    ttk.Button(bar, text="Last i utkast", command=page._on_load_journal_to_draft).pack(side="right", padx=(0, 4))

    page._tree_simple_elims = ttk.Treeview(elim_frm, columns=("voucher", "lines", "debet", "kredit", "diff", "status"), show="headings", height=4)
    for col, text, width, anchor in (
        ("voucher", "Bilag", 110, "w"),
        ("lines", "Linjer", 60, "e"),
        ("debet", "Debet", 95, "e"),
        ("kredit", "Kredit", 95, "e"),
        ("diff", "Diff", 95, "e"),
        ("status", "Status", 80, "center"),
    ):
        page._tree_simple_elims.heading(col, text=text)
        page._tree_simple_elims.column(col, width=width, anchor=anchor)
    page._tree_simple_elims.tag_configure("balanced", background="#E2F1EB")
    page._tree_simple_elims.tag_configure("unbalanced", background="#FCEBD9")
    page._tree_simple_elims.grid(row=1, column=0, sticky="nsew")
    page._tree_simple_elims.bind("<Delete>", lambda _e: page._on_delete_simple_elim())
    page._tree_simple_elims.bind("<<TreeviewSelect>>", page._on_simple_elim_selected)
    page._simple_elims_tree_mgr = ManagedTreeview(
        page._tree_simple_elims,
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
    page._simple_elims_col_mgr = page._simple_elims_tree_mgr.column_manager
    sb = ttk.Scrollbar(elim_frm, orient="vertical", command=page._tree_simple_elims.yview)
    page._tree_simple_elims.configure(yscrollcommand=sb.set)
    sb.grid(row=1, column=1, sticky="ns")

    page._tree_elim_detail = ttk.Treeview(elim_frm, columns=("regnr", "regnskapslinje", "debet", "kredit", "desc"), show="headings", height=4)
    for col, text, width, anchor in (
        ("regnr", "Regnr", 60, "e"),
        ("regnskapslinje", "Regnskapslinje", 180, "w"),
        ("debet", "Debet", 90, "e"),
        ("kredit", "Kredit", 90, "e"),
        ("desc", "Beskrivelse", 140, "w"),
    ):
        page._tree_elim_detail.heading(col, text=text)
        page._tree_elim_detail.column(col, width=width, anchor=anchor)
    page._tree_elim_detail.grid(row=3, column=0, sticky="nsew", pady=(2, 0))
    sb_det = ttk.Scrollbar(elim_frm, orient="vertical", command=page._tree_elim_detail.yview)
    page._tree_elim_detail.configure(yscrollcommand=sb_det.set)
    sb_det.grid(row=3, column=1, sticky="ns", pady=(2, 0))
    page._elim_detail_tree_mgr = ManagedTreeview(
        page._tree_elim_detail,
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
    page._elim_detail_col_mgr = page._elim_detail_tree_mgr.column_manager


def build_forslag_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    parent.rowconfigure(3, weight=1)

    top = ttk.Frame(parent)
    top.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
    ttk.Button(top, text="Generer forslag", command=page._on_generate_suggestions).pack(side="left")
    ttk.Button(top, text="Opprett journal", command=page._on_create_journal_from_suggestion).pack(side="left", padx=(4, 0))
    ttk.Button(top, text="Ignorer", command=page._on_ignore_suggestion).pack(side="left", padx=(4, 0))
    page._show_all_pairs_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(top, text="Vis alle selskapspar", variable=page._show_all_pairs_var, command=page._refresh_suggestion_tree).pack(side="left", padx=(12, 0))

    page._sug_type_interco_var = tk.BooleanVar(value=True)
    page._sug_type_renter_var = tk.BooleanVar(value=True)
    page._sug_type_bidrag_var = tk.BooleanVar(value=False)
    page._sug_type_invest_var = tk.BooleanVar(value=False)
    type_frm = ttk.Frame(parent)
    type_frm.grid(row=0, column=0, sticky="ew", padx=4, pady=(28, 0))
    ttk.Checkbutton(type_frm, text="Mellomvaerende", variable=page._sug_type_interco_var, command=page._refresh_suggestion_tree).pack(side="left")
    ttk.Checkbutton(type_frm, text="Renter", variable=page._sug_type_renter_var, command=page._refresh_suggestion_tree).pack(side="left", padx=(6, 0))
    ttk.Checkbutton(type_frm, text="Bidrag/Utbytte", variable=page._sug_type_bidrag_var, command=page._refresh_suggestion_tree).pack(side="left", padx=(6, 0))
    ttk.Checkbutton(type_frm, text="Investering/EK", variable=page._sug_type_invest_var, command=page._refresh_suggestion_tree).pack(side="left", padx=(6, 0))
    page._suggestion_count_var = tk.StringVar(value="")
    ttk.Label(type_frm, textvariable=page._suggestion_count_var).pack(side="right")

    page._tree_suggestions = ttk.Treeview(parent, columns=("kind", "counterparty", "line_a", "line_b", "amount_a", "amount_b", "diff", "status"), show="headings", height=8)
    for col, text, width, anchor in (
        ("kind", "Type", 90, "w"),
        ("counterparty", "Motpart", 110, "w"),
        ("line_a", "Linje mor", 120, "w"),
        ("line_b", "Linje motpart", 120, "w"),
        ("amount_a", "Mor", 90, "e"),
        ("amount_b", "Motpart", 90, "e"),
        ("diff", "Diff", 80, "e"),
        ("status", "Status", 70, "w"),
    ):
        page._tree_suggestions.heading(col, text=text)
        page._tree_suggestions.column(col, width=width, anchor=anchor)
    page._tree_suggestions.tag_configure("ny", background="#FFFFFF")
    page._tree_suggestions.tag_configure("ignorert", background="#F0F0F0", foreground="#888888")
    page._tree_suggestions.tag_configure("journalfoert", background="#E2F1EB")
    page._tree_suggestions.tag_configure("diff_warning", foreground="#CC6600")
    page._tree_suggestions.grid(row=2, column=0, sticky="nsew", padx=4)
    page._tree_suggestions.bind("<<TreeviewSelect>>", page._on_suggestion_select)
    page._suggestions_tree_mgr = ManagedTreeview(
        page._tree_suggestions,
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
    page._suggestions_col_mgr = page._suggestions_tree_mgr.column_manager

    ttk.Separator(parent, orient="horizontal").grid(row=3, column=0, sticky="ew", padx=4, pady=4)
    detail_frm = ttk.Frame(parent)
    detail_frm.grid(row=4, column=0, sticky="nsew", padx=4)
    detail_frm.columnconfigure(0, weight=1)
    detail_frm.rowconfigure(1, weight=1)
    parent.rowconfigure(2, weight=2)
    parent.rowconfigure(4, weight=1)
    page._suggestion_detail_var = tk.StringVar(value="Ingen forslag generert.")
    ttk.Label(detail_frm, textvariable=page._suggestion_detail_var, anchor="w").grid(row=0, column=0, sticky="ew")

    page._tree_suggestion_detail = ttk.Treeview(detail_frm, columns=("regnr", "company", "amount", "desc"), show="headings", height=4)
    for col, text, width, anchor in (
        ("regnr", "Regnr", 60, "e"),
        ("company", "Selskap", 120, "w"),
        ("amount", "Beloep", 100, "e"),
        ("desc", "Beskrivelse", 200, "w"),
    ):
        page._tree_suggestion_detail.heading(col, text=text)
        page._tree_suggestion_detail.column(col, width=width, anchor=anchor)
    page._tree_suggestion_detail.grid(row=1, column=0, sticky="nsew")
    page._sug_detail_tree_mgr = ManagedTreeview(
        page._tree_suggestion_detail,
        view_id="suggestion_det",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
            ColumnSpec("company", "Selskap", width=120, stretch=True),
            ColumnSpec("amount", "Beloep", width=100, anchor="e"),
            ColumnSpec("desc", "Beskrivelse", width=200, stretch=True),
        ],
    )
    page._sug_detail_col_mgr = page._sug_detail_tree_mgr.column_manager


def build_journaler_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    top = ttk.Frame(parent)
    top.pack(fill="x", padx=4, pady=4)
    ttk.Button(top, text="Nytt bilag", command=page._on_new_journal).pack(side="left")
    ttk.Button(top, text="Slett bilag", command=page._on_delete_journal).pack(side="left", padx=(4, 0))
    ttk.Button(top, text="Aapne tilknyttet", command=page._on_open_selected_associate_from_journal).pack(side="left", padx=(4, 0))

    page._tree_journals = ttk.Treeview(parent, columns=("voucher", "kind", "lines", "status", "balance"), show="headings", height=6)
    for col, text, width, anchor in (
        ("voucher", "Bilag", 130, "w"),
        ("kind", "Type", 90, "w"),
        ("lines", "Linjer", 50, "e"),
        ("status", "Status", 90, "w"),
        ("balance", "Balanse", 90, "w"),
    ):
        page._tree_journals.heading(col, text=text)
        page._tree_journals.column(col, width=width, anchor=anchor)
    for tag, cfg in (
        ("warning", {"background": "#FCEBD9"}),
        ("done", {"background": "#E2F1EB"}),
        ("template", {"background": "#FFF8E1"}),
        ("locked", {"background": "#EEF5FF"}),
        ("stale", {"background": "#FFF4E5"}),
    ):
        page._tree_journals.tag_configure(tag, **cfg)
    page._tree_journals.pack(fill="x", padx=4)
    page._tree_journals.bind("<<TreeviewSelect>>", page._on_journal_select)
    page._tree_journals.bind("<Delete>", lambda _e: page._on_delete_journal())
    page._journals_tree_mgr = ManagedTreeview(
        page._tree_journals,
        view_id="journals",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("voucher", "Bilag", width=130, pinned=True, stretch=True),
            ColumnSpec("kind", "Type", width=90),
            ColumnSpec("lines", "Linjer", width=50, anchor="e"),
            ColumnSpec("status", "Status", width=90),
            ColumnSpec("balance", "Balanse", width=90),
        ],
    )
    page._journals_col_mgr = page._journals_tree_mgr.column_manager

    ttk.Separator(parent, orient="horizontal").pack(fill="x", padx=4, pady=4)
    line_bar = ttk.Frame(parent)
    line_bar.pack(fill="x", padx=4)
    ttk.Button(line_bar, text="Legg til linje", command=page._on_add_elim_line).pack(side="left")
    ttk.Button(line_bar, text="Slett linje", command=page._on_delete_elim_line).pack(side="left", padx=(4, 0))
    page._elim_balance_var = tk.StringVar(value="")
    ttk.Label(line_bar, textvariable=page._elim_balance_var).pack(side="right")
    page._journal_meta_var = tk.StringVar(value="")
    ttk.Label(line_bar, textvariable=page._journal_meta_var).pack(side="right", padx=(0, 8))

    page._tree_elim_lines = ttk.Treeview(parent, columns=("regnr", "company", "amount", "desc"), show="headings")
    for col, text, width, anchor in (
        ("regnr", "Regnr", 60, "e"),
        ("company", "Selskap", 120, "w"),
        ("amount", "Beloep", 100, "e"),
        ("desc", "Beskrivelse", 160, "w"),
    ):
        page._tree_elim_lines.heading(col, text=text)
        page._tree_elim_lines.column(col, width=width, anchor=anchor)
    page._tree_elim_lines.pack(fill="both", expand=True, padx=4, pady=(4, 0))
    page._tree_elim_lines.bind("<Delete>", lambda _e: page._on_delete_elim_line())
    page._elim_lines_tree_mgr = ManagedTreeview(
        page._tree_elim_lines,
        view_id="elim_lines",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("regnr", "Regnr", width=60, anchor="e", pinned=True),
            ColumnSpec("company", "Selskap", width=120, stretch=True),
            ColumnSpec("amount", "Beloep", width=100, anchor="e"),
            ColumnSpec("desc", "Beskrivelse", width=160, stretch=True),
        ],
    )
    page._elim_lines_col_mgr = page._elim_lines_tree_mgr.column_manager
