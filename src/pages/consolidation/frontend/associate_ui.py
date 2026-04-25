"""Associate UI builders."""

from __future__ import annotations

from typing import TYPE_CHECKING

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from .associate_actions import (
    on_add_associate_adjustment,
    on_associate_case_selected,
    on_delete_associate_adjustment,
    on_delete_associate_case,
    on_edit_associate_adjustment,
    on_generate_associate_journal,
    on_new_associate_case,
    on_open_associate_journal,
    on_save_associate_case,
)
from .associate_ar import on_import_associate_line_support, on_import_associate_pdf_support
from .associate_state import (
    _on_apply_goodwill_amortization,
    _on_compute_goodwill,
    _on_save_default_line_mapping,
    _refresh_mapping_summary,
    _set_mapping_visibility,
    on_reset_associate_mapping,
    on_toggle_associate_mapping,
    refresh_associate_case_actions,
)
from ui_managed_treeview import ColumnSpec, ManagedTreeview

if TYPE_CHECKING:
    from .page import ConsolidationPage


def build_associate_cases_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    """Tilknyttede selskaper / EK-metode."""
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(0, weight=1)

    pw = ttk.PanedWindow(parent, orient="horizontal")
    pw.grid(row=0, column=0, sticky="nsew")

    left = ttk.Frame(pw, padding=4)
    left.columnconfigure(0, weight=1)
    left.rowconfigure(2, weight=1)
    pw.add(left, weight=1)

    left_bar = ttk.Frame(left)
    left_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    ttk.Button(left_bar, text="Ny sak", command=lambda: on_new_associate_case(page)).pack(side="left")
    page._btn_save_associate = ttk.Button(left_bar, text="Lagre", command=lambda: on_save_associate_case(page))
    page._btn_save_associate.pack(side="left", padx=(4, 0))
    page._btn_generate_associate = ttk.Button(left_bar, text="Generer EK-føring", command=lambda: on_generate_associate_journal(page))
    page._btn_generate_associate.pack(side="left", padx=(4, 0))
    page._btn_delete_associate = ttk.Button(left_bar, text="Slett", command=lambda: on_delete_associate_case(page))
    page._btn_delete_associate.pack(side="right")

    page._associate_intro_var = tk.StringVar(
        value=(
            "Bruk denne fanen bare for selskaper som skal føres etter EK-metoden. "
            "Døtre skal importeres som vanlige selskaper."
        )
    )
    ttk.Label(
        left,
        textvariable=page._associate_intro_var,
        foreground="#666666",
        justify="left",
        wraplength=320,
    ).grid(row=1, column=0, sticky="ew", pady=(0, 4))

    cols = ("name", "investor", "ownership", "status")
    tree = ttk.Treeview(left, columns=cols, show="headings", height=10)
    tree.heading("name", text="Tilknyttet")
    tree.heading("investor", text="Investor")
    tree.heading("ownership", text="Eierandel")
    tree.heading("status", text="Status")
    tree.column("name", width=170, stretch=True)
    tree.column("investor", width=120, stretch=True)
    tree.column("ownership", width=75, anchor="e")
    tree.column("status", width=80)
    tree.tag_configure("generated", background="#E2F1EB")
    tree.tag_configure("stale", background="#FFF4E5")
    tree.tag_configure("draft", background="#FFFFFF")
    tree.grid(row=2, column=0, sticky="nsew")
    tree.bind("<<TreeviewSelect>>", lambda _e: on_associate_case_selected(page))
    page._tree_associate_cases = tree

    page._associate_cases_tree_mgr = ManagedTreeview(
        tree,
        view_id="associate_cases",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("name", "Tilknyttet", width=170, pinned=True, stretch=True),
            ColumnSpec("investor", "Investor", width=120, stretch=True),
            ColumnSpec("ownership", "Eierandel", width=75, anchor="e"),
            ColumnSpec("status", "Status", width=80),
        ],
    )
    page._associate_cases_col_mgr = page._associate_cases_tree_mgr.column_manager

    settings = ttk.LabelFrame(left, text="Standard regnskapslinjer for nye saker", padding=6)
    settings.grid(row=3, column=0, sticky="ew", pady=(6, 0))
    settings.columnconfigure(1, weight=1)

    page._default_investment_regnr_var = tk.StringVar(value="575")
    page._default_result_regnr_var = tk.StringVar(value="100")
    page._default_other_equity_regnr_var = tk.StringVar(value="695")
    page._default_retained_regnr_var = tk.StringVar(value="705")

    default_rows = [
        ("Investering i tilknyttet", page._default_investment_regnr_var),
        ("Andel resultat", page._default_result_regnr_var),
        ("Andre EK-bevegelser", page._default_other_equity_regnr_var),
        ("Utbytte / disponering", page._default_retained_regnr_var),
    ]
    for idx, (label, var) in enumerate(default_rows):
        ttk.Label(settings, text=label).grid(row=idx, column=0, sticky="w", pady=1)
        ttk.Entry(settings, textvariable=var, width=8).grid(row=idx, column=1, sticky="w", padx=(6, 0), pady=1)

    ttk.Button(settings, text="Lagre som standard", command=lambda: _on_save_default_line_mapping(page)).grid(
        row=len(default_rows), column=0, columnspan=2, sticky="w", pady=(4, 0)
    )

    right = ttk.Frame(pw, padding=4)
    right.columnconfigure(0, weight=1)
    right.rowconfigure(1, weight=1)
    pw.add(right, weight=3)

    header = ttk.Frame(right)
    header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    header.columnconfigure(0, weight=1)
    page._associate_header_var = tk.StringVar(value="Ingen tilknyttet sak valgt.")
    page._associate_status_var = tk.StringVar(value="")
    page._associate_next_step_var = tk.StringVar(
        value="Opprett saken fra AR eller med 'Ny sak'. Fyll deretter årets EK-bevegelser og generer EK-føring."
    )
    ttk.Label(header, textvariable=page._associate_header_var, font=("", 10, "bold")).grid(
        row=0, column=0, sticky="w"
    )
    ttk.Label(header, textvariable=page._associate_status_var, foreground="#666666").grid(
        row=1, column=0, sticky="w"
    )
    ttk.Label(
        header,
        textvariable=page._associate_next_step_var,
        foreground="#1F5F8B",
        justify="left",
        wraplength=720,
    ).grid(row=2, column=0, sticky="w", pady=(2, 0))
    page._btn_open_associate_journal = ttk.Button(header, text="Åpne journal", command=lambda: on_open_associate_journal(page))
    page._btn_open_associate_journal.grid(row=0, column=1, rowspan=3, sticky="e")

    nb = ttk.Notebook(right)
    nb.grid(row=1, column=0, sticky="nsew")
    page._associate_nb = nb

    frm_workpaper = ttk.Frame(nb)
    nb.add(frm_workpaper, text="Grunnlag")
    _build_workpaper_tab(page, frm_workpaper)

    frm_calc = ttk.Frame(nb)
    nb.add(frm_calc, text="Beregning")
    _build_calc_tab(page, frm_calc)

    frm_journal = ttk.Frame(nb)
    nb.add(frm_journal, text="Generert føring")
    _build_journal_tab(page, frm_journal)
    refresh_associate_case_actions(page, None)


def _build_workpaper_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(3, weight=1)

    meta = ttk.LabelFrame(parent, text="Sak", padding=8)
    meta.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
    for idx in range(3):
        meta.columnconfigure(idx, weight=1)

    page._associate_name_var = tk.StringVar()
    page._associate_investor_var = tk.StringVar()
    page._associate_ownership_var = tk.StringVar(value="0")
    page._associate_acquisition_date_var = tk.StringVar()
    page._associate_notes_var = tk.StringVar()
    page._associate_source_mode_var = tk.StringVar(value="manual")
    page._associate_source_ref_var = tk.StringVar(value="")

    ttk.Label(meta, text="Tilknyttet selskap").grid(row=0, column=0, sticky="w")
    ttk.Entry(meta, textvariable=page._associate_name_var).grid(row=1, column=0, sticky="ew", padx=(0, 6))
    ttk.Label(meta, text="Investor").grid(row=0, column=1, sticky="w")
    page._associate_investor_cb = ttk.Combobox(meta, textvariable=page._associate_investor_var, state="readonly")
    page._associate_investor_cb.grid(row=1, column=1, sticky="ew", padx=(0, 6))
    ttk.Label(meta, text="Eierandel %").grid(row=0, column=2, sticky="w")
    ttk.Entry(meta, textvariable=page._associate_ownership_var, width=10).grid(row=1, column=2, sticky="w")

    ttk.Label(meta, text="Anskaffelsesdato").grid(row=2, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(meta, textvariable=page._associate_acquisition_date_var).grid(row=3, column=0, sticky="ew", padx=(0, 6))
    ttk.Label(meta, text="Kilde").grid(row=2, column=1, sticky="w", pady=(8, 0))
    ttk.Label(meta, textvariable=page._associate_source_mode_var).grid(row=3, column=1, sticky="w")
    ttk.Label(meta, text="Referanse").grid(row=2, column=2, sticky="w", pady=(8, 0))
    ttk.Label(meta, textvariable=page._associate_source_ref_var).grid(row=3, column=2, sticky="w")

    ttk.Label(meta, text="Notat").grid(row=4, column=0, sticky="w", pady=(8, 0))
    ttk.Entry(meta, textvariable=page._associate_notes_var).grid(row=5, column=0, columnspan=3, sticky="ew")

    workpaper = ttk.LabelFrame(parent, text="Årets EK-bevegelser", padding=8)
    workpaper.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 4))
    for idx in range(4):
        workpaper.columnconfigure(idx, weight=1)

    page._associate_opening_var = tk.StringVar(value="0")
    page._associate_result_var = tk.StringVar(value="0")
    page._associate_other_equity_var = tk.StringVar(value="0")
    page._associate_dividends_var = tk.StringVar(value="0")
    page._associate_impairment_var = tk.StringVar(value="0")
    page._associate_excess_value_var = tk.StringVar(value="0")
    page._associate_investment_regnr_var = tk.StringVar(value="575")
    page._associate_result_regnr_var = tk.StringVar(value="100")
    page._associate_other_equity_regnr_var = tk.StringVar(value="695")
    page._associate_retained_regnr_var = tk.StringVar(value="705")
    page._associate_mapping_summary_var = tk.StringVar(value="")
    page._associate_mapping_toggle_var = tk.StringVar(value="Vis regnskapslinjer")
    page._associate_mapping_name_vars: dict[str, tk.StringVar] = {}
    page._associate_mapping_visible = False

    for var in (
        page._associate_investment_regnr_var,
        page._associate_result_regnr_var,
        page._associate_other_equity_regnr_var,
        page._associate_retained_regnr_var,
    ):
        var.trace_add("write", lambda *_args: _refresh_mapping_summary(page))

    ttk.Label(
        workpaper,
        text="Fyll normalt bare venstre side. Regnskapslinjene brukes bare hvis du vil overstyre standard EK-mapping.",
        foreground="#666666",
        justify="left",
        wraplength=660,
    ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))

    fixed_rows = [
        ("Inngående bokført verdi", page._associate_opening_var),
        ("Andel resultat", page._associate_result_var),
        ("Andre EK-bevegelser", page._associate_other_equity_var),
        ("Utbytte", page._associate_dividends_var),
        ("Nedskrivning", page._associate_impairment_var),
        ("Merverdi/amortisering", page._associate_excess_value_var),
    ]
    for idx, (label, var) in enumerate(fixed_rows):
        ttk.Label(workpaper, text=label).grid(row=idx + 1, column=0, sticky="w", pady=2)
        ttk.Entry(workpaper, textvariable=var, width=16).grid(row=idx + 1, column=1, sticky="w", padx=(6, 12), pady=2)

    ttk.Label(workpaper, text="Regnskapslinjer (avansert)", font=("", 9, "bold")).grid(
        row=1, column=2, columnspan=2, sticky="w", pady=(2, 0)
    )
    ttk.Label(
        workpaper,
        textvariable=page._associate_mapping_summary_var,
        foreground="#475467",
        justify="left",
        wraplength=280,
    ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(0, 4))

    btn_row = ttk.Frame(workpaper)
    btn_row.grid(row=3, column=2, columnspan=2, sticky="w", pady=(0, 4))
    ttk.Button(btn_row, textvariable=page._associate_mapping_toggle_var, command=lambda: on_toggle_associate_mapping(page)).pack(side="left")
    ttk.Button(btn_row, text="Nullstill til standard", command=lambda: on_reset_associate_mapping(page)).pack(side="left", padx=(4, 0))

    mapping_frame = ttk.LabelFrame(workpaper, text="Avansert overstyring", padding=6)
    mapping_frame.grid(row=4, column=2, columnspan=2, rowspan=4, sticky="nsew", padx=(12, 0), pady=(0, 0))
    for idx in range(3):
        mapping_frame.columnconfigure(idx, weight=1 if idx == 2 else 0)

    mapping_rows = [
        ("investment_regnr", "Investering i tilknyttet", page._associate_investment_regnr_var),
        ("result_regnr", "Andel resultat", page._associate_result_regnr_var),
        ("other_equity_regnr", "Andre EK-bevegelser", page._associate_other_equity_regnr_var),
        ("retained_earnings_regnr", "Utbytte / disponering", page._associate_retained_regnr_var),
    ]
    for idx, (key, label, var) in enumerate(mapping_rows):
        ttk.Label(mapping_frame, text=label).grid(row=idx, column=0, sticky="w", pady=2)
        ttk.Entry(mapping_frame, textvariable=var, width=8).grid(row=idx, column=1, sticky="w", padx=(6, 8), pady=2)
        name_var = tk.StringVar(value="")
        page._associate_mapping_name_vars[key] = name_var
        ttk.Label(mapping_frame, textvariable=name_var, foreground="#667085").grid(row=idx, column=2, sticky="w", pady=2)

    page._associate_mapping_frame = mapping_frame
    _set_mapping_visibility(page, False)
    _refresh_mapping_summary(page)

    gw = ttk.LabelFrame(parent, text="Goodwill / merverdi", padding=8)
    gw.grid(row=2, column=0, sticky="ew", padx=4, pady=(0, 4))
    for idx in range(4):
        gw.columnconfigure(idx, weight=1)

    page._associate_acq_cost_var = tk.StringVar(value="0")
    page._associate_net_assets_var = tk.StringVar(value="0")
    page._associate_gw_years_var = tk.StringVar(value="5")
    page._associate_gw_computed_var = tk.StringVar(value="")
    page._associate_gw_annual_var = tk.StringVar(value="")

    ttk.Label(gw, text="Kostpris investering").grid(row=0, column=0, sticky="w")
    ttk.Entry(gw, textvariable=page._associate_acq_cost_var, width=16).grid(row=0, column=1, sticky="w", padx=(6, 12))
    ttk.Label(gw, text="Andel netto eiendeler v/kjøp").grid(row=0, column=2, sticky="w")
    ttk.Entry(gw, textvariable=page._associate_net_assets_var, width=16).grid(row=0, column=3, sticky="w", padx=(6, 0))

    ttk.Label(gw, text="Avskrivningstid (år)").grid(row=1, column=0, sticky="w", pady=(6, 0))
    gw_years_cb = ttk.Combobox(
        gw,
        textvariable=page._associate_gw_years_var,
        values=[str(y) for y in range(1, 21)],
        state="readonly",
        width=5,
    )
    gw_years_cb.grid(row=1, column=1, sticky="w", padx=(6, 12), pady=(6, 0))

    ttk.Label(gw, text="Beregnet goodwill:").grid(row=1, column=2, sticky="w", pady=(6, 0))
    ttk.Label(gw, textvariable=page._associate_gw_computed_var, foreground="#2F6D62", font=("Segoe UI", 9, "bold")).grid(
        row=1, column=3, sticky="w", padx=(6, 0), pady=(6, 0)
    )

    ttk.Label(gw, text="Årlig amortisering:").grid(row=2, column=0, sticky="w", pady=(4, 0))
    ttk.Label(gw, textvariable=page._associate_gw_annual_var, foreground="#2F6D62", font=("Segoe UI", 9, "bold")).grid(
        row=2, column=1, sticky="w", padx=(6, 0), pady=(4, 0)
    )

    gw_btn_row = ttk.Frame(gw)
    gw_btn_row.grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))
    ttk.Button(gw_btn_row, text="Beregn", command=lambda: _on_compute_goodwill(page)).pack(side="left")
    ttk.Button(gw_btn_row, text="Bruk beregnet amortisering", command=lambda: _on_apply_goodwill_amortization(page)).pack(
        side="left", padx=(6, 0)
    )

    adjust = ttk.LabelFrame(parent, text="Manuelle justeringer", padding=8)
    adjust.grid(row=3, column=0, sticky="nsew", padx=4, pady=(0, 4))
    adjust.columnconfigure(0, weight=1)
    adjust.rowconfigure(1, weight=1)

    bar = ttk.Frame(adjust)
    bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    ttk.Button(bar, text="Legg til", command=lambda: on_add_associate_adjustment(page)).pack(side="left")
    ttk.Button(bar, text="Rediger", command=lambda: on_edit_associate_adjustment(page)).pack(side="left", padx=(4, 0))
    ttk.Button(bar, text="Slett", command=lambda: on_delete_associate_adjustment(page)).pack(side="left", padx=(4, 0))
    ttk.Button(bar, text="Hent regnskapslinjer...", command=lambda: on_import_associate_line_support(page)).pack(side="right")
    ttk.Button(bar, text="Hent fra PDF...", command=lambda: on_import_associate_pdf_support(page)).pack(side="right", padx=(0, 4))

    cols = ("label", "amount", "offset_regnr", "description")
    tree = ttk.Treeview(adjust, columns=cols, show="headings", height=6)
    tree.heading("label", text="Label")
    tree.heading("amount", text="Beløp")
    tree.heading("offset_regnr", text="Motpost")
    tree.heading("description", text="Beskrivelse")
    tree.column("label", width=160, stretch=True)
    tree.column("amount", width=90, anchor="e")
    tree.column("offset_regnr", width=75, anchor="e")
    tree.column("description", width=190, stretch=True)
    tree.grid(row=1, column=0, sticky="nsew")
    page._tree_associate_adjustments = tree
    page._associate_adjustment_tree_mgr = ManagedTreeview(
        tree,
        view_id="associate_adjustments",
        pref_prefix="ui",
        column_specs=[
            ColumnSpec("label", "Label", width=160, pinned=True, stretch=True),
            ColumnSpec("amount", "Beløp", width=90, anchor="e"),
            ColumnSpec("offset_regnr", "Motpost", width=75, anchor="e"),
            ColumnSpec("description", "Beskrivelse", width=190, stretch=True),
        ],
    )
    page._associate_adjustment_col_mgr = page._associate_adjustment_tree_mgr.column_manager


def _build_calc_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    page._associate_calc_summary_var = tk.StringVar(value="Ingen beregning.")
    ttk.Label(parent, textvariable=page._associate_calc_summary_var, anchor="w").grid(
        row=0, column=0, sticky="ew", padx=4, pady=4
    )

    cols = ("label", "movement", "investment_regnr", "offset_regnr")
    tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
    tree.heading("label", text="Bevegelse")
    tree.heading("movement", text="Beløp")
    tree.heading("investment_regnr", text="Investering")
    tree.heading("offset_regnr", text="Motpost")
    tree.column("label", width=220, stretch=True)
    tree.column("movement", width=110, anchor="e")
    tree.column("investment_regnr", width=90, anchor="e")
    tree.column("offset_regnr", width=90, anchor="e")
    tree.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
    page._tree_associate_calc = tree


def _build_journal_tab(page: "ConsolidationPage", parent: ttk.Frame) -> None:
    parent.columnconfigure(0, weight=1)
    parent.rowconfigure(1, weight=1)
    page._associate_journal_summary_var = tk.StringVar(value="Ingen journal generert.")
    ttk.Label(parent, textvariable=page._associate_journal_summary_var, anchor="w").grid(
        row=0, column=0, sticky="ew", padx=4, pady=4
    )

    cols = ("regnr", "regnskapslinje", "amount", "description")
    tree = ttk.Treeview(parent, columns=cols, show="headings", height=10)
    tree.heading("regnr", text="Regnr")
    tree.heading("regnskapslinje", text="Regnskapslinje")
    tree.heading("amount", text="Beløp")
    tree.heading("description", text="Beskrivelse")
    tree.column("regnr", width=70, anchor="e")
    tree.column("regnskapslinje", width=180, stretch=True)
    tree.column("amount", width=100, anchor="e")
    tree.column("description", width=220, stretch=True)
    tree.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
    page._tree_associate_journal = tree
