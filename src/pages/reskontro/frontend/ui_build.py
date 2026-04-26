"""reskontro_ui_build.py — UI-bygging for Reskontro-fanen.

Modulfunksjoner som tar `page` (ReskontroPage) som første argument og
setter widgets direkte på `page`. Speiler saldobalanse-splitt-mønsteret.
"""

from __future__ import annotations

from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

from .tree_helpers import (
    _COL_ANT,
    _COL_BEV,
    _COL_BRANSJE,
    _COL_IB,
    _COL_KONTO,
    _COL_MVA,
    _COL_NAVN,
    _COL_NR,
    _COL_ORGNR,
    _COL_STATUS,
    _COL_UB,
    _DETAIL_COLS,
    _LOWER_VIEW_BETALT,
    _LOWER_VIEW_BRREG,
    _LOWER_VIEW_NESTE,
    _MASTER_COLS,
    _OPEN_ITEMS_COLS,
    _PAYMENTS_COLS,
    _SUBSEQ_COLS,
    _TAG_BRREG_WARN,
    _TAG_HEADER,
    _TAG_MVA_FRADRAG,
    _TAG_MVA_LINE,
    _TAG_MVA_WARN,
    _TAG_NEG,
    _TAG_ZERO,
    _UPPER_VIEW_ALLE,
    _UPPER_VIEW_APNE,
    _setup_tree,
)


def build_ui(page) -> None:
    tb = ttk.Frame(page, padding=(6, 4))
    tb.grid(row=0, column=0, sticky="ew")

    ttk.Label(tb, text="Reskontro",
              font=("TkDefaultFont", 11, "bold")).pack(side="left", padx=(0, 12))

    page._mode_var = tk.StringVar(value="kunder")
    ttk.Radiobutton(tb, text="Kunder", variable=page._mode_var,
                    value="kunder",
                    command=page._on_mode_change).pack(side="left")
    ttk.Radiobutton(tb, text="Leverandører", variable=page._mode_var,
                    value="leverandorer",
                    command=page._on_mode_change).pack(side="left",
                                                       padx=(6, 12))

    ttk.Label(tb, text="Søk:").pack(side="left")
    page._filter_var = tk.StringVar()
    search = ttk.Entry(tb, textvariable=page._filter_var, width=22)
    search.pack(side="left", padx=(4, 8))
    page._filter_var.trace_add("write", lambda *_: page._apply_filter())

    ttk.Button(tb, text="Oppdater",
               command=page.refresh_from_session,
               width=10).pack(side="left")

    page._brreg_btn = ttk.Button(
        tb, text="BRREG-sjekk\u2026",
        command=page._start_brreg_sjekk, width=14)
    page._brreg_btn.pack(side="left", padx=(6, 0))

    ttk.Button(tb, text="Eksporter til Excel\u2026",
               command=page._export_excel).pack(side="left", padx=(6, 0))

    ttk.Button(tb, text="Reskontrorapport (PDF)\u2026",
               command=page._export_pdf_report).pack(side="left", padx=(6, 0))

    ttk.Separator(tb, orient="vertical").pack(side="left", fill="y",
                                               padx=(8, 8), pady=2)

    page._hide_zero_var = tk.BooleanVar(value=False)
    ttk.Checkbutton(tb, text="Skjul nullposter",
                    variable=page._hide_zero_var,
                    command=page._apply_filter).pack(side="left")

    page._decimals_var = tk.BooleanVar(value=True)
    ttk.Checkbutton(tb, text="Desimaler",
                    variable=page._decimals_var,
                    command=page._on_decimals_toggle).pack(side="left",
                                                            padx=(6, 0))

    ttk.Button(
        tb, text="Saldoliste\u2026", command=page._show_saldoliste_popup,
    ).pack(side="left", padx=(6, 0))

    pane = ttk.PanedWindow(page, orient="horizontal")
    pane.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 0))

    # Statuslinje nederst
    page.rowconfigure(2, weight=0)
    status_bar = ttk.Frame(page, relief="sunken", padding=(4, 1))
    status_bar.grid(row=2, column=0, sticky="ew")
    page._status_lbl = ttk.Label(status_bar, text="", foreground="#555",
                                 font=("TkDefaultFont", 8))
    page._status_lbl.pack(side="left")

    # ---- Venstre: master-liste ----
    left = ttk.Frame(pane)
    left.rowconfigure(0, weight=1)
    left.columnconfigure(0, weight=1)
    pane.add(left, weight=1)

    page._master_tree = make_master_tree(page, left)
    page._master_tree.grid(row=0, column=0, sticky="nsew")
    vsb1 = ttk.Scrollbar(left, orient="vertical",
                          command=page._master_tree.yview)
    vsb1.grid(row=0, column=1, sticky="ns")
    hsb1 = ttk.Scrollbar(left, orient="horizontal",
                          command=page._master_tree.xview)
    hsb1.grid(row=1, column=0, sticky="ew")
    page._master_tree.configure(yscrollcommand=vsb1.set,
                                xscrollcommand=hsb1.set)
    page._master_tree.bind("<<TreeviewSelect>>", page._on_master_select)

    # Sum-rad: IB / Bevegelse / UB totalt + avstemming
    sum_f = ttk.Frame(left, padding=(2, 2))
    sum_f.grid(row=2, column=0, columnspan=2, sticky="ew")
    sum_f.columnconfigure(1, weight=1)
    ttk.Label(sum_f, text="Sum:", font=("TkDefaultFont", 8, "bold"),
              foreground="#333").grid(row=0, column=0, sticky="w", padx=(2, 6))
    page._sum_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                               foreground="#333")
    page._sum_lbl.grid(row=0, column=1, sticky="w")
    page._recon_lbl = ttk.Label(sum_f, text="", font=("TkDefaultFont", 8),
                                 foreground="#777")
    page._recon_lbl.grid(row=0, column=2, sticky="e", padx=(12, 2))

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
    page._detail_lbl = ttk.Label(
        upper_hdr, text="Velg en post for å se transaksjoner",
        font=("TkDefaultFont", 9, "bold"))
    page._detail_lbl.grid(row=0, column=0, sticky="w")
    ttk.Label(upper_hdr, text="Visning:").grid(
        row=0, column=1, sticky="e", padx=(6, 2))
    page._upper_view_var = tk.StringVar(value=_UPPER_VIEW_ALLE)
    page._upper_view_cb = ttk.Combobox(
        upper_hdr, textvariable=page._upper_view_var,
        values=(_UPPER_VIEW_ALLE, _UPPER_VIEW_APNE),
        state="readonly", width=18)
    page._upper_view_cb.grid(row=0, column=2, sticky="e")
    page._upper_view_cb.bind(
        "<<ComboboxSelected>>",
        lambda _e: page._on_upper_view_change())

    # Innholdsflaten i øvre panel — bytter mellom detail_tree og open_items_tree
    page._upper_content = ttk.Frame(upper_container)
    page._upper_content.grid(row=1, column=0, sticky="nsew", padx=(4, 0))
    page._upper_content.columnconfigure(0, weight=1)
    page._upper_content.rowconfigure(0, weight=1)

    page._detail_tree_frame = ttk.Frame(page._upper_content)
    page._detail_tree_frame.columnconfigure(0, weight=1)
    page._detail_tree_frame.rowconfigure(0, weight=1)
    page._detail_tree = make_detail_tree(page, page._detail_tree_frame)
    page._detail_tree.grid(row=0, column=0, sticky="nsew")
    vsb2 = ttk.Scrollbar(page._detail_tree_frame, orient="vertical",
                          command=page._detail_tree.yview)
    vsb2.grid(row=0, column=1, sticky="ns")
    hsb2 = ttk.Scrollbar(page._detail_tree_frame, orient="horizontal",
                          command=page._detail_tree.xview)
    hsb2.grid(row=1, column=0, sticky="ew")
    page._detail_tree.configure(yscrollcommand=vsb2.set,
                                xscrollcommand=hsb2.set)

    page._open_items_frame = ttk.Frame(page._upper_content)
    page._open_items_frame.columnconfigure(0, weight=1)
    page._open_items_frame.rowconfigure(0, weight=1)
    page._open_items_tree = make_open_items_tree(page, page._open_items_frame)
    page._open_items_tree.grid(row=0, column=0, sticky="nsew")
    vsb_oi = ttk.Scrollbar(page._open_items_frame, orient="vertical",
                            command=page._open_items_tree.yview)
    vsb_oi.grid(row=0, column=1, sticky="ns")
    hsb_oi = ttk.Scrollbar(page._open_items_frame, orient="horizontal",
                            command=page._open_items_tree.xview)
    hsb_oi.grid(row=1, column=0, sticky="ew")
    page._open_items_tree.configure(yscrollcommand=vsb_oi.set,
                                    xscrollcommand=hsb_oi.set)

    # Start med Alle transaksjoner synlig
    page._detail_tree_frame.grid(row=0, column=0, sticky="nsew")

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
    page._lower_view_var = tk.StringVar(value=_LOWER_VIEW_BRREG)
    page._lower_view_cb = ttk.Combobox(
        lower_hdr, textvariable=page._lower_view_var,
        values=(_LOWER_VIEW_BRREG, _LOWER_VIEW_NESTE, _LOWER_VIEW_BETALT),
        state="readonly", width=28)
    page._lower_view_cb.grid(row=0, column=1, sticky="w")
    page._lower_view_cb.bind(
        "<<ComboboxSelected>>",
        lambda _e: page._on_lower_view_change())
    page._load_subseq_btn = ttk.Button(
        lower_hdr, text="Last inn etterfølgende periode\u2026",
        command=page._open_subsequent_period)
    # pakkes inn/ut dynamisk i _refresh_lower_panel

    page._lower_content = ttk.Frame(lower_container)
    page._lower_content.grid(row=1, column=0, sticky="nsew", padx=(4, 0))
    page._lower_content.columnconfigure(0, weight=1)
    page._lower_content.rowconfigure(0, weight=1)

    # BRREG
    page._brreg_frame = ttk.Frame(page._lower_content)
    page._brreg_frame.columnconfigure(0, weight=1)
    page._brreg_frame.rowconfigure(0, weight=1)
    page._brreg_info_labels: dict[str, tk.StringVar] = {}
    page._build_brreg_panel()

    # Neste periode
    page._subseq_frame = ttk.Frame(page._lower_content)
    page._subseq_frame.columnconfigure(0, weight=1)
    page._subseq_frame.rowconfigure(1, weight=1)
    page._subseq_empty_lbl = ttk.Label(
        page._subseq_frame, text="", foreground="#666",
        font=("TkDefaultFont", 9))
    page._subseq_empty_lbl.grid(row=0, column=0, columnspan=2,
                                 sticky="w", padx=4, pady=(2, 2))
    page._subseq_tree = make_subseq_tree(page, page._subseq_frame)
    page._subseq_tree.grid(row=1, column=0, sticky="nsew")
    vsb_ss = ttk.Scrollbar(page._subseq_frame, orient="vertical",
                            command=page._subseq_tree.yview)
    vsb_ss.grid(row=1, column=1, sticky="ns")
    hsb_ss = ttk.Scrollbar(page._subseq_frame, orient="horizontal",
                            command=page._subseq_tree.xview)
    hsb_ss.grid(row=2, column=0, sticky="ew")
    page._subseq_tree.configure(yscrollcommand=vsb_ss.set,
                                 xscrollcommand=hsb_ss.set)

    # Betalinger
    page._payments_frame = ttk.Frame(page._lower_content)
    page._payments_frame.columnconfigure(0, weight=1)
    page._payments_frame.rowconfigure(1, weight=1)
    page._payments_empty_lbl = ttk.Label(
        page._payments_frame, text="", foreground="#666",
        font=("TkDefaultFont", 9))
    page._payments_empty_lbl.grid(row=0, column=0, columnspan=2,
                                   sticky="w", padx=4, pady=(2, 2))
    page._payments_tree = make_payments_tree(page, page._payments_frame)
    page._payments_tree.grid(row=1, column=0, sticky="nsew")
    vsb_pm = ttk.Scrollbar(page._payments_frame, orient="vertical",
                            command=page._payments_tree.yview)
    vsb_pm.grid(row=1, column=1, sticky="ns")
    hsb_pm = ttk.Scrollbar(page._payments_frame, orient="horizontal",
                            command=page._payments_tree.xview)
    hsb_pm.grid(row=2, column=0, sticky="ew")
    page._payments_tree.configure(yscrollcommand=vsb_pm.set,
                                   xscrollcommand=hsb_pm.set)

    # Start med BRREG synlig
    page._brreg_frame.grid(row=0, column=0, sticky="nsew")

    right_pane.add(lower_container, weight=1)


def make_master_tree(page, parent: Any) -> Any:
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


def make_detail_tree(page, parent: Any) -> Any:
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
    tree.bind("<Double-1>", page._on_detail_double_click)
    tree.bind("<Return>",   page._on_detail_double_click)
    tree.bind("<<TreeviewSelect>>", page._on_detail_select)
    tree.bind("<Button-3>", page._on_detail_right_click)
    _setup_tree(tree, extended=True)
    return tree


def make_open_items_tree(page, parent: Any) -> Any:
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
    tree.bind("<Double-1>", page._on_detail_double_click)
    _setup_tree(tree, extended=True)
    return tree


def make_subseq_tree(page, parent: Any) -> Any:
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


def make_payments_tree(page, parent: Any) -> Any:
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
