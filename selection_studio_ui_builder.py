"""
selection_studio_ui_builder

Bygger GUI-elementer for SelectionStudio.

Denne modulen er et rent refaktoreringstiltak: vi flytter den store UI-byggingen
ut av views_selection_studio_ui.py, slik at den filen blir lettere å lese og videreutvikle.
"""

from __future__ import annotations

from tkinter import ttk
from typing import Any


def build_ui(studio: Any) -> None:
    """Bygg UI for en SelectionStudio-instans."""
    studio.columnconfigure(1, weight=1)
    studio.rowconfigure(1, weight=1)

    # Top summary
    lbl = ttk.Label(studio, textvariable=studio.var_base_summary)
    lbl.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))

    # Left panel
    left = ttk.Frame(studio)
    left.grid(row=1, column=0, sticky="nsw", padx=(8, 4), pady=(0, 8))
    left.columnconfigure(0, weight=1)

    # --- Filters section
    lf_filters = ttk.LabelFrame(left, text="Filtre")
    lf_filters.grid(row=0, column=0, sticky="ew", pady=(0, 8))
    lf_filters.columnconfigure(1, weight=1)

    ttk.Label(lf_filters, text="Retning").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
    frm_dir = ttk.Frame(lf_filters)
    frm_dir.grid(row=0, column=1, sticky="w", padx=6, pady=(6, 2))
    ttk.Checkbutton(frm_dir, text="Kun debet", variable=studio.var_only_debit).grid(row=0, column=0, sticky="w")
    ttk.Checkbutton(frm_dir, text="Kun kredit", variable=studio.var_only_credit).grid(
        row=0, column=1, sticky="w", padx=(12, 0)
    )

    ttk.Label(lf_filters, text="Beløp (netto) fra/til").grid(row=1, column=0, sticky="w", padx=6, pady=(6, 2))
    frm_amt = ttk.Frame(lf_filters)
    frm_amt.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 2))
    frm_amt.columnconfigure(0, weight=1)
    frm_amt.columnconfigure(2, weight=1)
    ttk.Entry(frm_amt, textvariable=studio.var_min_amount, width=10).grid(row=0, column=0, sticky="ew")
    ttk.Label(frm_amt, text="til").grid(row=0, column=1, padx=4)
    ttk.Entry(frm_amt, textvariable=studio.var_max_amount, width=10).grid(row=0, column=2, sticky="ew")

    # --- Selection section
    lf_sel = ttk.LabelFrame(left, text="Utvalg")
    lf_sel.grid(row=1, column=0, sticky="ew", pady=(0, 8))
    lf_sel.columnconfigure(1, weight=1)

    ttk.Label(lf_sel, text="Risiko").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
    cmb_risk = ttk.Combobox(
        lf_sel,
        textvariable=studio.var_risk,
        values=["Lav", "Middels", "Høy"],
        width=12,
        state="readonly",
    )
    cmb_risk.grid(row=0, column=1, sticky="ew", padx=6, pady=(6, 2))

    ttk.Label(lf_sel, text="Sikkerhet").grid(row=1, column=0, sticky="w", padx=6, pady=(6, 2))
    cmb_conf = ttk.Combobox(
        lf_sel,
        textvariable=studio.var_confidence,
        values=["80%", "90%", "95%"],
        width=12,
        state="readonly",
    )
    cmb_conf.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 2))

    ttk.Label(lf_sel, text="Tolererbar feil").grid(row=2, column=0, sticky="w", padx=6, pady=(6, 2))
    ent_tol = ttk.Entry(lf_sel, textvariable=studio.var_tolerable_error)
    ent_tol.grid(row=2, column=1, sticky="ew", padx=6, pady=(6, 2))
    ent_tol.bind("<FocusOut>", lambda _e: studio._format_tolerable_error_entry())

    ttk.Label(lf_sel, text="Metode").grid(row=3, column=0, sticky="w", padx=6, pady=(6, 2))
    cmb_method = ttk.Combobox(
        lf_sel,
        textvariable=studio.var_method,
        values=["quantile", "equal_width"],
        state="readonly",
        width=12,
    )
    cmb_method.grid(row=3, column=1, sticky="ew", padx=6, pady=(6, 2))

    ttk.Label(lf_sel, text="Antall grupper (k)").grid(row=4, column=0, sticky="w", padx=6, pady=(6, 2))
    spn_k = ttk.Spinbox(lf_sel, from_=1, to=12, textvariable=studio.var_k, width=6)
    spn_k.grid(row=4, column=1, sticky="w", padx=6, pady=(6, 2))

    ttk.Label(lf_sel, text="Utvalgsstørrelse").grid(row=5, column=0, sticky="w", padx=6, pady=(6, 2))
    spn_n = ttk.Spinbox(lf_sel, from_=0, to=99999, textvariable=studio.var_sample_n, width=8)
    spn_n.grid(row=5, column=1, sticky="w", padx=6, pady=(6, 2))
    spn_n.bind("<KeyRelease>", lambda _e: studio._sample_size_touched())

    lbl_rec = ttk.Label(lf_sel, textvariable=studio.var_recommendation, wraplength=260)
    lbl_rec.grid(row=6, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 6))

    # Buttons
    frm_btn = ttk.Frame(left)
    frm_btn.grid(row=2, column=0, sticky="ew")
    frm_btn.columnconfigure(0, weight=1)
    frm_btn.columnconfigure(1, weight=1)

    ttk.Button(frm_btn, text="Kjør utvalg", command=studio._run_selection).grid(
        row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4)
    )
    ttk.Button(frm_btn, text="Legg i utvalg", command=studio._commit_selection).grid(
        row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4)
    )
    ttk.Button(frm_btn, text="Eksporter Excel", command=studio._export_excel).grid(
        row=1, column=0, columnspan=2, sticky="ew"
    )

    # Right panel (tabs)
    right = ttk.Frame(studio)
    right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
    right.columnconfigure(0, weight=1)
    right.rowconfigure(0, weight=1)

    studio.nb = ttk.Notebook(right)
    studio.nb.grid(row=0, column=0, sticky="nsew")

    # Tab: Utvalg
    tab_utvalg = ttk.Frame(studio.nb)
    tab_utvalg.columnconfigure(0, weight=1)
    tab_utvalg.rowconfigure(1, weight=1)
    studio.nb.add(tab_utvalg, text="Utvalg")

    frm_top = ttk.Frame(tab_utvalg)
    frm_top.grid(row=0, column=0, sticky="ew", pady=(4, 0))
    frm_top.columnconfigure(0, weight=1)
    ttk.Button(frm_top, text="Vis kontorer", command=studio._show_accounts).grid(row=0, column=1, padx=(6, 0))
    ttk.Button(frm_top, text="Drilldown", command=studio._open_drilldown).grid(row=0, column=2, padx=(6, 0))

    columns = ("Bilag", "Dato", "Tekst", "SumBeløp", "Gruppe", "Intervall")
    studio.tree = ttk.Treeview(tab_utvalg, columns=columns, show="headings", height=18)
    for c in columns:
        studio.tree.heading(c, text=c)
        studio.tree.column(c, anchor="w", width=120)
    studio.tree.column("Bilag", width=80, anchor="e")
    studio.tree.column("SumBeløp", width=120, anchor="e")
    studio.tree.column("Dato", width=100, anchor="w")

    vsb = ttk.Scrollbar(tab_utvalg, orient="vertical", command=studio.tree.yview)
    studio.tree.configure(yscrollcommand=vsb.set)
    studio.tree.grid(row=1, column=0, sticky="nsew")
    vsb.grid(row=1, column=1, sticky="ns")

    # Double-click opens drilldown for the selected bilag
    studio.tree.bind("<Double-1>", lambda _evt: studio._open_drilldown())

    # Tab: Grupper
    tab_grp = ttk.Frame(studio.nb)
    tab_grp.columnconfigure(0, weight=1)
    tab_grp.rowconfigure(0, weight=1)
    studio.nb.add(tab_grp, text="Grupper")

    grp_cols = ("Gruppe", "Intervall", "Antall", "SumBeløp")
    studio.tree_groups = ttk.Treeview(tab_grp, columns=grp_cols, show="headings", height=10)
    for c in grp_cols:
        studio.tree_groups.heading(c, text=c)
        studio.tree_groups.column(c, anchor="w", width=160)
    studio.tree_groups.column("Antall", anchor="e", width=80)
    studio.tree_groups.column("SumBeløp", anchor="e", width=120)
    vsb2 = ttk.Scrollbar(tab_grp, orient="vertical", command=studio.tree_groups.yview)
    studio.tree_groups.configure(yscrollcommand=vsb2.set)
    studio.tree_groups.grid(row=0, column=0, sticky="nsew")
    vsb2.grid(row=0, column=1, sticky="ns")

