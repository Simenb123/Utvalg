"""page_analyse_ui_panels.py

Panels-seksjonen (pivot, detail, TX/SB/NK/MP-frames, bindings, selection summary,
sortering, shortcuts) utskilt fra page_analyse_ui.build_ui.

Funksjonen `build_panels` tar `page` + `refs` fra `build_toolbar` og installerer
widget-treet samt bindinger rett på `page`.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import analyse_treewidths
from page_analyse_ui_helpers import _nk_fetch_brreg


def build_panels(page: Any, *, tk: Any, ttk: Any, refs: SimpleNamespace) -> None:
    """Bygg panels (pivot + detail + TX/SB/NK/MP frames) og install bindinger."""

    var_search = refs.var_search
    var_dir = refs.var_dir
    var_bilag = refs.var_bilag
    var_motpart = refs.var_motpart
    var_date_from = refs.var_date_from
    var_date_to = refs.var_date_to
    var_max_rows = refs.var_max_rows
    var_min = refs.var_min
    var_max = refs.var_max
    var_rb = refs.var_rb
    var_mva_code = refs.var_mva_code
    var_mva_mode = refs.var_mva_mode
    var_agg = refs.var_agg
    rb_filter_options = refs.rb_filter_options
    ent_search = refs.ent_search
    ent_bilag = refs.ent_bilag
    ent_motpart = refs.ent_motpart
    ent_date_from = refs.ent_date_from
    ent_date_to = refs.ent_date_to
    ent_min = refs.ent_min
    ent_max = refs.ent_max
    cmb_dir = refs.cmb_dir
    cmb_mva_code = refs.cmb_mva_code
    cmb_mva = refs.cmb_mva
    spn_max = refs.spn_max

    # Visual separation from the lists below
    ttk.Separator(page, orient="horizontal").pack(fill="x", padx=6, pady=(0, 2))
    body = ttk.Frame(page)
    body.pack(fill="both", expand=True, padx=6, pady=(2, 6))
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)

    lbl_tx_summary = ttk.Label(body, text="Ingen kontoer valgt.")

    mapping_banner = ttk.Frame(body, style="Card.TFrame")
    mapping_banner.grid(row=0, column=0, sticky="ew", pady=(0, 4))
    mapping_banner.grid_remove()
    mapping_banner.columnconfigure(1, weight=1)
    ttk.Label(mapping_banner, text="Mappingkontroll:", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(8, 6), pady=6)
    lbl_mapping_warning = ttk.Label(
        mapping_banner,
        textvariable=getattr(page, "_mapping_warning_var", None),
        foreground="#9C1C1C",
    )
    lbl_mapping_warning.grid(row=0, column=1, sticky="w", pady=6)
    btn_show_unmapped = ttk.Button(mapping_banner, text="Vis umappede", command=page._show_only_unmapped_accounts)
    btn_show_unmapped.grid(row=0, column=2, sticky="e", padx=(8, 4), pady=4)
    btn_map_problem = ttk.Button(mapping_banner, text="Map valgt konto...", command=page._map_selected_problem_account)
    btn_map_problem.grid(row=0, column=3, sticky="e", padx=4, pady=4)
    btn_bulk_problem = ttk.Button(mapping_banner, text="Flytt valgte...", command=page._bulk_map_selected_problem_accounts)
    btn_bulk_problem.grid(row=0, column=4, sticky="e", padx=(4, 8), pady=4)
    btn_mapping_drift = ttk.Button(
        mapping_banner, text="Se endret mapping...",
        command=getattr(page, "_show_mapping_drift_dialog", lambda: None),
    )
    btn_mapping_drift.grid(row=0, column=5, sticky="e", padx=(4, 8), pady=4)
    try:
        btn_mapping_drift.grid_remove()
    except Exception:
        pass
    page._mapping_banner_frame = mapping_banner
    page._btn_show_only_unmapped = btn_show_unmapped
    page._btn_map_selected_problem = btn_map_problem
    page._btn_bulk_map_problem = btn_bulk_problem
    page._btn_show_mapping_drift = btn_mapping_drift

    paned_cls = getattr(ttk, "Panedwindow", None)
    if paned_cls is not None:
        split_body = paned_cls(body, orient="horizontal")
        split_body.grid(row=1, column=0, sticky="nsew")
        pivot_frame = ttk.Frame(split_body)
        tx_frame = ttk.Frame(split_body)
        try:
            split_body.add(pivot_frame, weight=1)
        except Exception:
            split_body.add(pivot_frame)
        try:
            split_body.add(tx_frame, weight=3)
        except Exception:
            split_body.add(tx_frame)
    else:
        body.columnconfigure(0, weight=1, uniform="analyse")
        body.columnconfigure(1, weight=3, uniform="analyse")
        pivot_frame = ttk.Frame(body)
        pivot_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
        tx_frame = ttk.Frame(body)
        tx_frame.grid(row=1, column=1, sticky="nsew")
        split_body = None

    # Pivot (konto-sammendrag)
    pivot_frame.rowconfigure(2, weight=1)
    pivot_frame.columnconfigure(0, weight=1)

    # Header med Aggregering-dropdown + sammendrag over pivottreet
    pivot_header = ttk.Frame(pivot_frame)
    pivot_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 2))

    ttk.Label(pivot_header, text="Visning:").grid(row=0, column=0, padx=(0, 6))
    _agg_changed = getattr(page, "_on_aggregering_changed", None)
    _agg_cb = (lambda: _agg_changed()) if callable(_agg_changed) else None
    # Regnskapslinje først (default-visning), Saldobalanse som sekundærvalg.
    rb_agg_rl = ttk.Radiobutton(
        pivot_header,
        text="Regnskapslinje",
        variable=var_agg,
        value="Regnskapslinje",
        command=_agg_cb,
    )
    rb_agg_rl.grid(row=0, column=1, sticky="w", padx=(0, 8))
    rb_agg_sb = ttk.Radiobutton(
        pivot_header,
        text="Saldobalanse",
        variable=var_agg,
        value="Saldobalanse",
        command=_agg_cb,
    )
    rb_agg_sb.grid(row=0, column=2, sticky="w")
    page._cmb_agg = None  # tidligere Combobox — beholdes som None for bakoverkompat
    page._rb_agg_sb = rb_agg_sb
    page._rb_agg_rl = rb_agg_rl

    ttk.Label(pivot_header, text="Type:").grid(row=0, column=3, padx=(12, 4))
    cmb_rb = ttk.Combobox(
        pivot_header,
        textvariable=var_rb,
        values=list(rb_filter_options),
        width=10,
        state="readonly",
    )
    cmb_rb.grid(row=0, column=4, sticky="w")
    _rb_changed = (
        getattr(page, "_on_rb_filter_changed", None)
        or getattr(page, "_schedule_apply_filters", None)
    )
    if callable(_rb_changed):
        cmb_rb.bind("<<ComboboxSelected>>", lambda _e: _rb_changed())
    page._cmb_rb = cmb_rb

    # Sammendragsetikett (f.eks. "74 kontoer | Sum UB: -12 643 322,74")
    pivot_header.columnconfigure(5, weight=1)
    lbl_tx_summary.grid(in_=pivot_header, row=0, column=6, sticky="e", padx=(8, 0))

    # Søkefelt over pivot-treet (Ctrl+F fokuserer hit)
    _pivot_search_var = tk.StringVar()
    pivot_search_entry = ttk.Entry(pivot_frame, textvariable=_pivot_search_var)
    pivot_search_entry.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 2))
    pivot_search_entry.insert(0, "Sok konto...")
    pivot_search_entry.configure(foreground="gray")
    page._pivot_search_var = _pivot_search_var  # type: ignore[attr-defined]
    page._pivot_search_entry = pivot_search_entry  # type: ignore[attr-defined]

    _pivot_search_placeholder = [True]

    def _pivot_search_focus_in(_e=None):
        if _pivot_search_placeholder[0]:
            pivot_search_entry.delete(0, "end")
            pivot_search_entry.configure(foreground="")
            _pivot_search_placeholder[0] = False

    def _pivot_search_focus_out(_e=None):
        if not _pivot_search_var.get().strip():
            pivot_search_entry.insert(0, "Sok konto...")
            pivot_search_entry.configure(foreground="gray")
            _pivot_search_placeholder[0] = True

    def _pivot_search_changed(*_args):
        if _pivot_search_placeholder[0]:
            return
        query = _pivot_search_var.get().strip().lower()
        if not query:
            # Fjern filter — vis alle (kall page._apply_pivot_filter hvis finnes)
            _fn = getattr(page, "_on_pivot_search", None)
            if callable(_fn):
                _fn("")
            return
        _fn = getattr(page, "_on_pivot_search", None)
        if callable(_fn):
            _fn(query)

    pivot_search_entry.bind("<FocusIn>", _pivot_search_focus_in)
    pivot_search_entry.bind("<FocusOut>", _pivot_search_focus_out)
    _pivot_search_var.trace_add("write", _pivot_search_changed)

    pivot_tree = ttk.Treeview(
        pivot_frame,
        columns=getattr(page, "PIVOT_COLS", ("Konto", "Kontonavn", "Sum", "Antall")),
        show="headings",
        selectmode="extended",
    )
    pivot_tree.grid(row=2, column=0, sticky="nsew")
    for col in pivot_tree["columns"]:
        pivot_tree.heading(col, text=col)
        pivot_tree.column(
            col,
            width=analyse_treewidths.default_column_width(col),
            anchor=analyse_treewidths.column_anchor(col),
            stretch=(col == "Kontonavn"),
        )

    try:
        from theme import style_treeview_tags

        style_treeview_tags(
            pivot_tree, "sumline", "sumline_major", "sumline_total", "commented", "zebra"
        )
    except Exception:
        pass

    pv_scroll = ttk.Scrollbar(pivot_frame, orient="vertical", command=pivot_tree.yview)
    pv_scroll.grid(row=2, column=1, sticky="ns")
    pv_hscroll = ttk.Scrollbar(pivot_frame, orient="horizontal", command=pivot_tree.xview)
    pv_hscroll.grid(row=3, column=0, sticky="ew")
    pivot_tree.configure(yscrollcommand=pv_scroll.set, xscrollcommand=pv_hscroll.set)

    # Høyreklikkmeny for pivot-kolonner (vis/skjul)
    _pivot_col_menu_fn = getattr(page, "_show_pivot_column_menu", None)
    if callable(_pivot_col_menu_fn):
        pivot_tree.bind("<Button-3>", _pivot_col_menu_fn)
    _pivot_resize_fn = getattr(page, "_schedule_balance_pivot_tree", None)
    if callable(_pivot_resize_fn):
        pivot_tree.bind("<Configure>", lambda _e=None: _pivot_resize_fn(), add="+")

    # Appliser lagret kolonne-synlighet
    _apply_pivot_vis = getattr(page, "_apply_pivot_visible_columns", None)
    if callable(_apply_pivot_vis):
        _apply_pivot_vis()

    # Høyre arbeidsflate: detaljer + transaksjoner
    tx_frame.columnconfigure(0, weight=1)
    tx_frame.rowconfigure(2, weight=1)

    detail_header = ttk.Frame(tx_frame)
    detail_header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
    detail_header.columnconfigure(0, weight=1)

    lbl_detail_summary = ttk.Label(detail_header, textvariable=getattr(page, "_detail_summary_var", None))
    lbl_detail_summary.grid(row=0, column=0, sticky="w")
    lbl_detail_status = ttk.Label(detail_header, textvariable=getattr(page, "_detail_status_var", None))
    lbl_detail_status.grid(row=1, column=0, sticky="w", pady=(2, 0))

    detail_toolbar = ttk.Frame(tx_frame)
    detail_toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
    detail_toolbar.columnconfigure(8, weight=1)

    ttk.Checkbutton(
        detail_toolbar,
        text="Kun avvik",
        variable=getattr(page, "_detail_only_flagged_var", None),
        command=getattr(page, "_refresh_detail_panel", None),
    ).grid(row=0, column=0, sticky="w")

    btn_map = ttk.Button(
        detail_toolbar,
        text="Endre mapping...",
        command=getattr(page, "_open_mapping_dialog_for_selected_detail_account", None),
    )
    btn_map.grid(row=0, column=1, sticky="w", padx=(8, 0))

    btn_remove_override = ttk.Button(
        detail_toolbar,
        text="Fjern override",
        command=getattr(page, "_remove_override_for_selected_detail_account", None),
    )
    btn_remove_override.grid(row=0, column=2, sticky="w", padx=(8, 0))

    btn_apply_suggestion = ttk.Button(
        detail_toolbar,
        text="Bruk forslag",
        command=getattr(page, "_apply_suggestion_for_selected_detail_account", None),
    )
    btn_apply_suggestion.grid(row=0, column=3, sticky="w", padx=(8, 0))

    btn_reject_suggestion = ttk.Button(
        detail_toolbar,
        text="Avvis forslag",
        command=getattr(page, "_reject_suggestion_for_selected_detail_account", None),
    )
    btn_reject_suggestion.grid(row=0, column=4, sticky="w", padx=(8, 0))

    btn_explain = ttk.Button(
        detail_toolbar,
        text="Åpne forklaring",
        command=getattr(page, "_explain_selected_detail_account", None),
    )
    btn_explain.grid(row=0, column=5, sticky="w", padx=(8, 0))

    paned_vertical_cls = getattr(ttk, "Panedwindow", None)
    detail_split = None
    if paned_vertical_cls is not None:
        detail_split = paned_vertical_cls(tx_frame, orient="vertical")
        detail_split.grid(row=2, column=0, sticky="nsew")
        accounts_outer = ttk.Frame(detail_split)
        suggestion_outer = ttk.Frame(detail_split)
        tx_outer = ttk.Frame(detail_split)
        try:
            detail_split.add(accounts_outer, weight=3)
        except Exception:
            detail_split.add(accounts_outer)
        try:
            detail_split.add(suggestion_outer, weight=2)
        except Exception:
            detail_split.add(suggestion_outer)
        try:
            detail_split.add(tx_outer, weight=4)
        except Exception:
            detail_split.add(tx_outer)
    else:
        tx_frame.rowconfigure(2, weight=2)
        tx_frame.rowconfigure(3, weight=1)
        tx_frame.rowconfigure(4, weight=3)
        accounts_outer = ttk.Frame(tx_frame)
        suggestion_outer = ttk.Frame(tx_frame)
        tx_outer = ttk.Frame(tx_frame)
        accounts_outer.grid(row=2, column=0, sticky="nsew", pady=(0, 6))
        suggestion_outer.grid(row=3, column=0, sticky="nsew", pady=(0, 6))
        tx_outer.grid(row=4, column=0, sticky="nsew")

    ttk.Label(accounts_outer, text="Kontoer i valgt scope").grid(row=0, column=0, sticky="w", pady=(0, 2))
    accounts_outer.columnconfigure(0, weight=1)
    accounts_outer.rowconfigure(1, weight=1)

    detail_accounts_tree = ttk.Treeview(
        accounts_outer,
        columns=("Konto", "Kontonavn", "OppfortSom", "OppforerSegSom", "ForslattRL", "Confidence", "Review", "Avvik", "IB", "Endring", "UB", "Antall"),
        show="headings",
        selectmode="browse",
    )
    detail_accounts_tree.grid(row=1, column=0, sticky="nsew")
    detail_account_scroll = ttk.Scrollbar(accounts_outer, orient="vertical", command=detail_accounts_tree.yview)
    detail_account_scroll.grid(row=1, column=1, sticky="ns")
    detail_accounts_tree.configure(yscrollcommand=detail_account_scroll.set)
    for col, heading, width, anchor in [
        ("Konto", "Konto", 90, "w"),
        ("Kontonavn", "Kontonavn", 190, "w"),
        ("OppfortSom", "Oppført som", 180, "w"),
        ("OppforerSegSom", "Oppfører seg som", 150, "w"),
        ("ForslattRL", "Foreslått RL", 190, "w"),
        ("Confidence", "Confidence", 90, "w"),
        ("Review", "Review", 90, "w"),
        ("Avvik", "Avvik", 240, "w"),
        ("IB", "IB", 110, "e"),
        ("Endring", "Endring", 110, "e"),
        ("UB", "UB", 110, "e"),
        ("Antall", "Antall", 70, "e"),
    ]:
        detail_accounts_tree.heading(col, text=heading)
        detail_accounts_tree.column(col, width=width, anchor=anchor, stretch=True)

    ttk.Label(suggestion_outer, text="Handlinger og forslag").grid(row=0, column=0, sticky="w", pady=(0, 2))
    suggestion_outer.columnconfigure(0, weight=1)
    suggestion_outer.rowconfigure(1, weight=1)

    detail_suggestion_tree = ttk.Treeview(
        suggestion_outer,
        columns=("Type", "Status", "Detalj"),
        show="headings",
        selectmode="browse",
    )
    detail_suggestion_tree.grid(row=1, column=0, sticky="nsew")
    detail_suggestion_scroll = ttk.Scrollbar(suggestion_outer, orient="vertical", command=detail_suggestion_tree.yview)
    detail_suggestion_scroll.grid(row=1, column=1, sticky="ns")
    detail_suggestion_tree.configure(yscrollcommand=detail_suggestion_scroll.set)
    for col, width in [("Type", 120), ("Status", 90), ("Detalj", 620)]:
        detail_suggestion_tree.heading(col, text=col)
        detail_suggestion_tree.column(col, width=width, anchor="w", stretch=True)

    # Header for transaksjoner/SB-visning med toggle
    tx_header = ttk.Frame(tx_outer)
    tx_header.grid(row=0, column=0, sticky="ew", pady=(0, 2))
    # Spacer-kolonne mellom visning-kontroller (venstre) og Vis-feltet (høyre).
    # col 1-3: Visning-kontroller (Saldobalanse/Transaksjoner/Annet)
    # col 4: spacer som tar all overflødig plass
    # col 5-6: "Vis: <antall>"-spinbox ved høyre kant
    tx_header.columnconfigure(4, weight=1)

    ttk.Label(tx_header, text="Visning:").grid(row=0, column=0, padx=(0, 6))

    _var_tx_mode = getattr(page, "_var_tx_view_mode", None)
    if _var_tx_mode is not None:
        _on_tx_mode_fn = getattr(page, "_on_tx_view_mode_changed", None)
        _tx_mode_cb_call = (lambda: _on_tx_mode_fn()) if callable(_on_tx_mode_fn) else None

        # To primær-radios: Saldobalanse, Transaksjoner.
        rb_tx_sb = ttk.Radiobutton(
            tx_header, text="Saldobalanse",
            variable=_var_tx_mode, value="Saldobalanse",
            command=_tx_mode_cb_call,
        )
        rb_tx_sb.grid(row=0, column=1, sticky="w", padx=(0, 8))
        rb_tx_tx = ttk.Radiobutton(
            tx_header, text="Transaksjoner",
            variable=_var_tx_mode, value="Transaksjoner",
            command=_tx_mode_cb_call,
        )
        rb_tx_tx.grid(row=0, column=2, sticky="w", padx=(0, 8))

        # "Annet ▾"-menubutton: Motposter, Motposter (kontonivå), Nøkkeltall.
        adv_btn = ttk.Menubutton(tx_header, text="Annet ▾", direction="below")
        adv_btn.grid(row=0, column=3, sticky="w")
        adv_menu = tk.Menu(adv_btn, tearoff=False)
        adv_btn["menu"] = adv_menu
        _adv_options = ("Motposter", "Motposter (kontonivå)", "Nøkkeltall")
        for label in _adv_options:
            adv_menu.add_radiobutton(
                label=label,
                variable=_var_tx_mode,
                value=label,
                command=_tx_mode_cb_call,
            )

        # Sync menubutton-tekst med aktiv visning.
        def _sync_adv_btn_text(*_args) -> None:
            try:
                val = _var_tx_mode.get()
            except Exception:
                val = ""
            try:
                if val in _adv_options:
                    adv_btn.configure(text=f"{val} ▾")
                else:
                    adv_btn.configure(text="Annet ▾")
            except Exception:
                pass

        try:
            _var_tx_mode.trace_add("write", _sync_adv_btn_text)
        except Exception:
            pass
        _sync_adv_btn_text()

        # Bakoverkompat — _tx_view_combo brukes av eksisterende kode (f.eks.
        # disabling i TB-only). Vi setter den til menubuttonen så .configure(state=...)
        # fortsatt virker — men kun "Annet"-knappen påvirkes; radioene er separate.
        page._tx_view_combo = adv_btn
        page._rb_tx_sb = rb_tx_sb
        page._rb_tx_tx = rb_tx_tx
        page._tx_view_adv_btn = adv_btn
        page._tx_view_adv_menu = adv_menu

    # "Vis: <antall>" — ligger helt til høyre, med spacer-kolonne 4 imellom.
    _var_max_rows = getattr(page, "_var_max_rows", None)
    if _var_max_rows is not None:
        ttk.Label(tx_header, text="Vis:").grid(row=0, column=5, sticky="e", padx=(12, 4))
        _spn_max = ttk.Spinbox(
            tx_header,
            from_=50,
            to=5000,
            increment=50,
            textvariable=_var_max_rows,
            width=8,
            command=page._on_max_rows_changed,
        )
        _spn_max.grid(row=0, column=6, sticky="e")
        _spn_max.bind("<FocusOut>", lambda _e: page._on_max_rows_changed())
        _spn_max.bind("<Return>", lambda _e: page._on_max_rows_changed())
        page._spn_max = _spn_max

    # "Klassifiser kontoer..."-knappen er fjernet fra Analyse-fanen.
    # Saldobalanse-fanen har fortsatt sin egen "Avansert klassifisering"-handling
    # (saldobalanse_actions.open_advanced_classification) som bruker samme
    # views_konto_klassifisering-modulen.

    # Desimaler-toggle og "Eksporter..."-knapp er flyttet til "Visning ▾"-menyen
    # på rad 1 i toolbaren (eksport håndteres via Rapporter-/Handlinger-menyen).

    # Søkefelt over høyre listbox — deler _var_search med toolbar-søket slik
    # at endring ett sted synkes til begge. Bruker liten "Søk:"-label i stedet
    # for placeholder-tekst (placeholder via Entry.insert ville skrevet teksten
    # inn i den delte StringVar-en og blitt tolket som filterverdi).
    _var_search_shared = getattr(page, "_var_search", None)
    if _var_search_shared is not None:
        tx_search_row = ttk.Frame(tx_outer)
        tx_search_row.grid(row=1, column=0, sticky="ew", pady=(0, 2))
        tx_search_row.columnconfigure(1, weight=1)
        ttk.Label(tx_search_row, text="Søk:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        tx_search_entry = ttk.Entry(tx_search_row, textvariable=_var_search_shared)
        tx_search_entry.grid(row=0, column=1, sticky="ew")
        page._tx_search_entry = tx_search_entry  # type: ignore[attr-defined]

    tx_outer.rowconfigure(2, weight=1)
    tx_outer.columnconfigure(0, weight=1)

    # --- TX-frame (transaksjoner) ---
    tx_frame = ttk.Frame(tx_outer)
    tx_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
    tx_frame.rowconfigure(0, weight=1)
    tx_frame.columnconfigure(0, weight=1)

    tx_tree = ttk.Treeview(
        tx_frame,
        columns=getattr(page, "TX_COLS", ("Dato", "Bilag", "Tekst", "Beløp")),
        show="headings",
        selectmode="extended",
    )
    tx_tree.grid(row=0, column=0, sticky="nsew")
    for col in tx_tree["columns"]:
        tx_tree.heading(col, text=col)
        tx_tree.column(col, width=140, anchor="w")

    # Standard-bredder
    for col, w, a in [
        ("Konto", 70, "w"),
        ("Kontonavn", 180, "w"),
        ("Dato", 90, "w"),
        ("Bilag", 90, "w"),
        ("Tekst", 320, "w"),
        ("Beløp", 110, "e"),
    ]:
        if col in tx_tree["columns"]:
            tx_tree.column(col, width=w, anchor=a)

    try:
        tx_tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    tx_scroll = ttk.Scrollbar(tx_frame, orient="vertical", command=tx_tree.yview)
    tx_scroll.grid(row=0, column=1, sticky="ns")
    tx_hscroll = ttk.Scrollbar(tx_frame, orient="horizontal", command=tx_tree.xview)
    tx_hscroll.grid(row=1, column=0, sticky="ew")
    tx_tree.configure(yscrollcommand=tx_scroll.set, xscrollcommand=tx_hscroll.set)

    page._tx_frame = tx_frame

    # --- SB-frame (saldobalanse) ---
    try:
        import page_analyse_sb
        sb_frame = page_analyse_sb.create_sb_tree(tx_outer)
        if sb_frame is not None:
            sb_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
            sb_frame.grid_remove()  # Skjult som standard
            page._sb_frame = sb_frame
            page._sb_tree = getattr(sb_frame, "_sb_tree", None)
        else:
            page._sb_frame = None
            page._sb_tree = None
    except Exception:
        page._sb_frame = None
        page._sb_tree = None

    # --- NK-frame (nøkkeltall) ---
    try:
        nk_frame = ttk.Frame(tx_outer)
        nk_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        nk_frame.rowconfigure(1, weight=1)
        nk_frame.columnconfigure(0, weight=1)
        nk_frame.grid_remove()  # Skjult som standard

        # Kompakt toolbar for BRREG-henting
        nk_toolbar = tk.Frame(nk_frame, background="#FFFDF8", padx=8, pady=2)
        nk_toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")

        nk_brreg_btn = ttk.Button(
            nk_toolbar, text="Hent BRREG-tall",
            command=lambda: _nk_fetch_brreg(page), width=16)
        nk_brreg_btn.pack(side=tk.RIGHT, padx=(4, 0))

        nk_brreg_label = tk.Label(
            nk_toolbar, text="", font=("Segoe UI", 8),
            foreground="#667085", background="#FFFDF8")
        nk_brreg_label.pack(side=tk.RIGHT, padx=(0, 6))

        nk_text = tk.Text(
            nk_frame,
            wrap="word",
            state="disabled",
            relief="flat",
            bg="#FFFDF8",
            padx=12,
            pady=6,
            font=("Segoe UI", 10),
        )
        nk_text.grid(row=1, column=0, sticky="nsew")
        nk_scroll = ttk.Scrollbar(nk_frame, orient="vertical", command=nk_text.yview)
        nk_scroll.grid(row=1, column=1, sticky="ns")
        nk_text.configure(yscrollcommand=nk_scroll.set)
        page._nk_frame = nk_frame
        page._nk_text = nk_text
        page._nk_brreg_btn = nk_brreg_btn
        page._nk_brreg_label = nk_brreg_label
        page._nk_brreg_data = None  # cached BRREG regnskap
    except Exception:
        page._nk_frame = None
        page._nk_text = None

    # --- MP-frame (motposter) ---
    try:
        import page_analyse_sb as _sb_mod
        mp_frame = _sb_mod.create_mp_tree(tx_outer)
        if mp_frame is not None:
            mp_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
            mp_frame.grid_remove()
            page._mp_frame = mp_frame
        else:
            page._mp_frame = None
    except Exception:
        page._mp_frame = None

    # Motposter (kontonivå) — aggregert motpost per konto
    try:
        import page_analyse_sb as _sb_mod2
        mp_acct_frame = _sb_mod2.create_mp_account_tree(tx_outer)
        if mp_acct_frame is not None:
            mp_acct_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
            mp_acct_frame.grid_remove()
            page._mp_acct_frame = mp_acct_frame
        else:
            page._mp_acct_frame = None
    except Exception:
        page._mp_acct_frame = None

    # Analyse skal holdes som en ren analyseflate.
    # Mapping-/forslagspanelene bygges fortsatt her som kompatibilitets-shim,
    # men skjules fra selve Analyse-visningen.
    try:
        detail_header.grid_remove()
    except Exception:
        pass
    try:
        detail_toolbar.grid_remove()
    except Exception:
        pass
    # Fjern mapping-paneler fra PanedWindow, behold kun tx_outer
    if detail_split is not None:
        try:
            detail_split.forget(accounts_outer)
        except Exception:
            pass
        try:
            detail_split.forget(suggestion_outer)
        except Exception:
            pass
    else:
        try:
            accounts_outer.grid_remove()
        except Exception:
            pass
        try:
            suggestion_outer.grid_remove()
        except Exception:
            pass
        try:
            tx_outer.grid_configure(row=0, column=0, sticky="nsew")
        except Exception:
            pass

    # Bindings
    # Konto-klikk skal oppdatere transaksjonslisten (bruk hook hvis den finnes, ellers fallback)
    _pivot_select_fn = getattr(page, "_on_pivot_select", None) or getattr(page, "_refresh_transactions_view", None)
    if callable(_pivot_select_fn):
        pivot_tree.bind("<<TreeviewSelect>>", lambda _e=None: _pivot_select_fn())
    else:  # pragma: no cover - defensive
        pivot_tree.bind("<<TreeviewSelect>>", lambda _e=None: None)

    _pivot_double_click_fn = getattr(page, "_on_pivot_tree_double_click", None)
    _open_rl_drill_fn = getattr(page, "_open_rl_drilldown_from_pivot_selection", None)
    if callable(_pivot_double_click_fn) or callable(_open_rl_drill_fn):
        def _open_pivot_drill(_e=None):  # noqa: ANN001
            if callable(_pivot_double_click_fn):
                try:
                    res = _pivot_double_click_fn(_e)
                    if res == "break":
                        return "break"
                except Exception:
                    pass
            if callable(_open_rl_drill_fn):
                try:
                    _open_rl_drill_fn()
                except Exception:
                    pass
            return "break"

        pivot_tree.bind("<Double-1>", _open_pivot_drill)
        pivot_tree.bind("<Return>", _open_pivot_drill)
        pivot_tree.bind("<KP_Enter>", _open_pivot_drill)

    _pivot_press_fn   = getattr(page, "_on_pivot_tree_mouse_press",   None)
    _pivot_drag_fn    = getattr(page, "_on_pivot_tree_mouse_drag",    None)
    _pivot_release_fn = getattr(page, "_on_pivot_tree_mouse_release", None)
    if callable(_pivot_press_fn):
        pivot_tree.bind("<ButtonPress-1>",  lambda e: _pivot_press_fn(e))
    if callable(_pivot_drag_fn):
        pivot_tree.bind("<B1-Motion>",      lambda e: _pivot_drag_fn(e))
    if callable(_pivot_release_fn):
        pivot_tree.bind("<ButtonRelease-1>", lambda e: _pivot_release_fn(e))

    _tx_select_fn = getattr(page, "_on_tx_select", None)
    if callable(_tx_select_fn):
        tx_tree.bind("<<TreeviewSelect>>", lambda _e=None: _tx_select_fn())

    _detail_select_fn = getattr(page, "_on_detail_account_select", None)
    if callable(_detail_select_fn):
        detail_accounts_tree.bind("<<TreeviewSelect>>", lambda _e=None: _detail_select_fn())

    _tx_double_click_fn = getattr(page, "_on_tx_tree_double_click", None)
    _tx_press_fn = getattr(page, "_on_tx_tree_mouse_press", None)
    _tx_drag_fn = getattr(page, "_on_tx_tree_mouse_drag", None)
    _tx_release_fn = getattr(page, "_on_tx_tree_mouse_release", None)
    if callable(_tx_press_fn):
        tx_tree.bind("<ButtonPress-1>", lambda e: _tx_press_fn(e))
    if callable(_tx_drag_fn):
        tx_tree.bind("<B1-Motion>", lambda e: _tx_drag_fn(e))
    if callable(_tx_release_fn):
        tx_tree.bind("<ButtonRelease-1>", lambda e: _tx_release_fn(e))

    # Bilag drilldown: dobbelklikk / Enter på transaksjonslisten
    _open_drill_fn = getattr(page, "_open_bilag_drilldown_from_tx_selection", None)
    if callable(_open_drill_fn):
        def _open_drill(_e=None):  # noqa: ANN001
            if callable(_tx_double_click_fn):
                try:
                    res = _tx_double_click_fn(_e)
                    if res == "break":
                        return "break"
                except Exception:
                    pass
            try:
                _open_drill_fn()
            except Exception:
                pass
            return "break"

        tx_tree.bind("<Double-1>", _open_drill)
        tx_tree.bind("<Return>", _open_drill)
        tx_tree.bind("<KP_Enter>", _open_drill)
    elif callable(_tx_double_click_fn):
        tx_tree.bind("<Double-1>", lambda e: _tx_double_click_fn(e))

    # Eksponer widgets til page_analyse
    page._var_search = var_search
    page._var_direction = var_dir
    page._var_bilag = var_bilag
    page._var_motpart = var_motpart
    page._var_date_from = var_date_from
    page._var_date_to = var_date_to
    page._var_max_rows = var_max_rows
    page._var_min = var_min
    page._var_max = var_max
    page._var_mva_code = var_mva_code
    page._var_mva_mode = var_mva_mode
    page._var_rb = var_rb
    page._ent_search = ent_search
    page._lbl_tx_summary = lbl_tx_summary
    page._body_split = split_body
    page._detail_panel = None
    page._detail_split = None
    page._detail_accounts_tree = None
    page._detail_suggestion_tree = None
    page._pivot_tree = pivot_tree
    page._tx_tree = tx_tree

    # Registrer Analyse-Treeviews i global selection-summary (opt-in).
    # Hver registrering får en profil som styrer prioritering, row_noun,
    # max_items og hide_zero. Pivot-treet bruker en kontekst-resolver som
    # leser aktiv aggregeringsmodus slik at footer-teksten alltid speiler
    # den synlige konteksten.
    try:
        import ui_selection_summary as _uiss

        def _pivot_priority_resolver(_tree: Any) -> tuple[str, ...]:
            try:
                import page_analyse_columns as _pac

                agg = _pac._read_agg_mode(page)
                has_prev = _pac._has_prev_year(page)
            except Exception:
                agg = ""
                has_prev = False
            if agg == "HB-konto":
                return ("Sum", "Antall")
            if agg in ("SB-konto", "Regnskapslinje"):
                if has_prev:
                    return ("Sum", "UB_fjor", "Endring_fjor")
                return ("Sum", "Endring")
            # MVA-kode / ukjent: fall tilbake til de mest relevante summerbare
            return ("Sum", "Antall")

        _uiss.register_treeview_selection_summary(
            pivot_tree,
            columns=(
                "IB", "Endring", "Sum", "AO_belop",
                "UB_for_ao", "UB_etter_ao", "Antall",
                "UB_fjor", "Endring_fjor",
            ),
            priority_columns=_pivot_priority_resolver,
            row_noun="rader",
            max_items=3,
            hide_zero=True,
        )
        _uiss.register_treeview_selection_summary(
            tx_tree,
            columns=("Beløp", "MVA-beløp"),
            priority_columns=("Beløp", "MVA-beløp"),
            row_noun="transaksjoner",
            max_items=2,
            hide_zero=True,
        )
        sb_tree = getattr(page, "_sb_tree", None)
        if sb_tree is not None:
            _uiss.register_treeview_selection_summary(
                sb_tree,
                columns=("IB", "Endring", "UB", "UB_fjor", "Antall"),
                priority_columns=("UB", "UB_fjor", "Endring"),
                row_noun="kontoer",
                max_items=3,
                hide_zero=True,
            )
        mp_frame = getattr(page, "_mp_frame", None)
        mp_tree = getattr(mp_frame, "_mp_tree", None) if mp_frame is not None else None
        if mp_tree is not None:
            _uiss.register_treeview_selection_summary(
                mp_tree,
                columns=("Beløp",),
                priority_columns=("Beløp",),
                row_noun="poster",
                max_items=1,
                hide_zero=True,
            )
        mp_acct_frame = getattr(page, "_mp_acct_frame", None)
        mp_acct_tree = (
            getattr(mp_acct_frame, "_mp_acct_tree", None)
            if mp_acct_frame is not None
            else None
        )
        if mp_acct_tree is not None:
            _uiss.register_treeview_selection_summary(
                mp_acct_tree,
                columns=("Sum", "Antall bilag"),
                priority_columns=("Sum", "Antall bilag"),
                row_noun="kontoer",
                max_items=2,
                hide_zero=True,
            )
    except Exception:
        pass

    # Sortering (kolonneklikk)
    try:
        getattr(page, "_enable_pivot_sorting")()
    except Exception:
        pass

    try:
        getattr(page, "_enable_tx_sorting")()
    except Exception:
        pass

    # Tastatursnarveier
    try:
        getattr(page, "_bind_shortcuts")(
            ent_search=ent_search,
            ent_bilag=ent_bilag,
            ent_motpart=ent_motpart,
            ent_date_from=ent_date_from,
            ent_date_to=ent_date_to,
            ent_min=ent_min,
            ent_max=ent_max,
            ent_mva=cmb_mva_code,
            cmb_dir=cmb_dir,
            cmb_mva=cmb_mva,
            spn_max=spn_max,
        )
    except Exception:
        pass
