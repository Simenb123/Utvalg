"""page_analyse_ui.py

UI-bygging for Analyse-fanen.

Designmål
---------
* Lav risiko: kun layout/visuelle grep, og kobling mot eksisterende logikk i
  ``page_analyse.py``.
* Testbarhet: ``build_ui`` kan få injisert ``tk``/``ttk``-moduler og
  ``dir_options`` fra ``page_analyse``.
"""

from __future__ import annotations

from typing import Any, Optional, Sequence


def build_ui(
    page: Any,
    tk=None,
    ttk=None,
    dir_options: Optional[Sequence[Any]] = None,
) -> None:
    """Bygg UI for Analyse-fanen.

    Args:
        page: AnalysePage-instans (ttk.Frame)
        tk: tkinter-modul (valgfri, for injisering i tester)
        ttk: tkinter.ttk-modul (valgfri, for injisering i tester)
        dir_options: Liste med objekter som har ``label`` (valgfri)
    """

    # Lazy import (og støtte for injisering)
    if tk is None:
        import tkinter as tk  # type: ignore

    if ttk is None:
        from tkinter import ttk  # type: ignore

    # Retning-labels: bruk dir_options hvis tilgjengelig, ellers fallback
    dir_labels: list[str] = []
    if dir_options:
        try:
            dir_labels = [str(getattr(opt, "label")) for opt in dir_options if getattr(opt, "label", None)]
        except Exception:
            dir_labels = []
    if not dir_labels:
        dir_labels = ["Alle", "+", "-"]

    # -------------------------------------------------
    # Knyt widgetene til AnalysePage sine Tk-variabler
    # -------------------------------------------------
    # AnalysePage oppretter disse i __init__. Hvis vi ikke binder
    # textvariable til disse vil filtrene ikke fungere, og frie navn
    # kan gi NameError når UI bygges.
    var_search = getattr(page, "_var_search", None)
    if var_search is None:
        var_search = tk.StringVar(master=page, value="")

    var_dir = getattr(page, "_var_direction", None)
    if var_dir is None:
        var_dir = tk.StringVar(master=page, value=str(dir_labels[0]) if dir_labels else "Alle")

    var_max_rows = getattr(page, "_var_max_rows", None)
    if var_max_rows is None:
        var_max_rows = tk.IntVar(master=page, value=200)

    var_min = getattr(page, "_var_min", None)
    if var_min is None:
        var_min = tk.StringVar(master=page, value="")

    var_max = getattr(page, "_var_max", None)
    if var_max is None:
        var_max = tk.StringVar(master=page, value="")

    # Hvis valgt verdi ikke finnes i listen (f.eks. etter endringer), fall tilbake.
    try:
        cur_label = str(var_dir.get())
    except Exception:
        cur_label = ""
    if dir_labels and cur_label not in [str(x) for x in dir_labels]:
        try:
            var_dir.set(str(dir_labels[0]))
        except Exception:
            pass

    # -------------------------------------------------
    # Helper: variabel-trace (programmatisk set() skal trigge filter/refresh)
    # -------------------------------------------------
    def _bind_var_write(var: Any, callback) -> None:
        """Best-effort bind til Tk variable endringer.

        Bruker trace_add når tilgjengelig, ellers trace (eldre API).
        """
        if var is None or callback is None:
            return
        try:
            var.trace_add("write", lambda *_: callback())
            return
        except Exception:
            pass
        try:
            var.trace("w", lambda *_: callback())
        except Exception:
            pass

    def _live_filter_cb() -> None:
        fn = getattr(page, "_on_live_filter_var_changed", None) or getattr(page, "_schedule_apply_filters", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    def _max_rows_cb() -> None:
        # Unngå ekstra refresh under reset (reset setter flere vars i en blokk)
        if getattr(page, "_suspend_live_filter", False):
            return
        fn = getattr(page, "_on_max_rows_changed", None) or getattr(page, "_refresh_transactions_view", None)
        if callable(fn):
            try:
                fn()
            except Exception:
                pass

    # ----------------------
    # Filterlinje (øverst)
    # ----------------------
    # Top filters (two rows for better spacing & room for future filters like date/periode)
    filter_frame = ttk.Frame(page)
    filter_frame.pack(fill="x", padx=6, pady=(6, 2))

    # Row 1: quick search + direction + actions (right aligned)
    row1 = ttk.Frame(filter_frame)
    row1.pack(fill="x")

    ttk.Label(row1, text="Søk:").grid(row=0, column=0, sticky="w")
    ent_search = ttk.Entry(row1, width=28, textvariable=var_search)
    ent_search.grid(row=0, column=1, sticky="w", padx=(4, 12))

    ttk.Label(row1, text="Retning:").grid(row=0, column=2, sticky="w")
    cmb_dir = ttk.Combobox(
        row1,
        textvariable=var_dir,
        values=list(dir_labels),
        width=12,
        state="readonly",
    )
    cmb_dir.grid(row=0, column=3, sticky="w", padx=(4, 12))

    # Spacer to push buttons to the right (keeps room for e.g. date/periode filters later)
    row1.grid_columnconfigure(4, weight=1)

    btn_reset = ttk.Button(row1, text="Nullstill", command=page._reset_filters)
    btn_reset.grid(row=0, column=5, padx=(0, 6), sticky="e")

    btn_select_all = ttk.Button(row1, text="Marker alle", command=page._select_all_accounts)
    btn_select_all.grid(row=0, column=6, padx=(0, 6), sticky="e")

    actions_btn = ttk.Menubutton(row1, text="Handlinger ▾", direction="below")
    actions_btn.grid(row=0, column=7, sticky="e")

    actions_menu = tk.Menu(actions_btn, tearoff=False)
    actions_btn["menu"] = actions_menu

    # Send markerte kontoer til Utvalg (støtter flere metode-navn)
    send_to_utvalg_cmd = getattr(page, "_send_to_utvalg", None) or getattr(page, "_send_selected_to_utvalg", None)
    if callable(send_to_utvalg_cmd):
        actions_menu.add_command(label="Send markerte kontoer til Utvalg", command=send_to_utvalg_cmd)
    else:
        actions_menu.add_command(label="Send markerte kontoer til Utvalg", state="disabled")

    # Motpost-analyse (støtter flere metode-navn)
    motpost_cmd = getattr(page, "_open_motpost_analysis", None) or getattr(page, "_open_motpost", None)
    if callable(motpost_cmd):
        actions_menu.add_command(label="Motpost-analyse (valgte kontoer)", command=motpost_cmd)
    else:
        actions_menu.add_command(label="Motpost-analyse (valgte kontoer)", state="disabled")

    actions_menu.add_separator()

    # Overstyringssjekker
    override_cmd = getattr(page, "_open_override_checks", None)
    if callable(override_cmd):
        actions_menu.add_command(label="Overstyringssjekker", command=override_cmd)
    else:
        actions_menu.add_command(label="Overstyringssjekker", state="disabled")

    # Row 2: series + numeric filters (Vis/Min/Maks)
    row2 = ttk.Frame(filter_frame)
    row2.pack(fill="x", pady=(4, 0))

    ttk.Label(row2, text="Kontoserier:").grid(row=0, column=0, sticky="w")

    series_vars = getattr(page, "_series_vars", [])
    if not series_vars:
        # Fallback (best-effort): bool vars
        series_vars = [tk.BooleanVar(value=True) for _ in range(10)]
        page._series_vars = series_vars

    series_frame = ttk.Frame(row2)
    series_frame.grid(row=0, column=1, sticky="w", padx=(4, 12))
    for i, var in enumerate(series_vars):
        cb = ttk.Checkbutton(series_frame, text=str(i), variable=var, command=page._apply_filters_now)
        cb.grid(row=0, column=i, sticky="w")

    ttk.Label(row2, text="Vis:").grid(row=0, column=2, sticky="w")
    spn_max = ttk.Spinbox(
        row2,
        from_=50,
        to=5000,
        increment=50,
        textvariable=var_max_rows,
        width=8,
        command=page._on_max_rows_changed,
    )
    spn_max.grid(row=0, column=3, sticky="w", padx=(4, 12))
    spn_max.bind("<FocusOut>", lambda _e: page._on_max_rows_changed())
    spn_max.bind("<Return>", lambda _e: page._on_max_rows_changed())

    ttk.Label(row2, text="Min beløp:").grid(row=0, column=4, sticky="w")
    ent_min = ttk.Entry(row2, textvariable=var_min, width=10)
    ent_min.grid(row=0, column=5, sticky="w", padx=(4, 12))

    ttk.Label(row2, text="Maks beløp:").grid(row=0, column=6, sticky="w")
    ent_max = ttk.Entry(row2, textvariable=var_max, width=10)
    ent_max.grid(row=0, column=7, sticky="w", padx=(4, 0))

    row2.grid_columnconfigure(8, weight=1)

    # Ctrl+A i tekstfelt
    page._bind_entry_select_all(ent_search)
    page._bind_entry_select_all(ent_min)
    page._bind_entry_select_all(ent_max)

    # live filtering (debounced) + Enter for "apply now"
    ent_search.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_min.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_max.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())

    ent_search.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_min.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_max.bind("<Return>", lambda _e: page._apply_filters_now())

    cmb_dir.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())

    # Variabel-trace: gjør at paste/programmatisk set() også trigger
    _bind_var_write(var_search, _live_filter_cb)
    _bind_var_write(var_min, _live_filter_cb)
    _bind_var_write(var_max, _live_filter_cb)
    _bind_var_write(var_max_rows, _max_rows_cb)

    # Expose key widgets for tests / senere tweaks
    page._actions_btn = actions_btn
    page._ent_search = ent_search
    page._cmb_dir = cmb_dir
    page._spn_max = spn_max
    page._btn_reset = btn_reset
    page._btn_select_all = btn_select_all

    # Visual separation from the lists below
    ttk.Separator(page, orient="horizontal").pack(fill="x", padx=6, pady=(0, 2))
    body = ttk.Frame(page)
    body.pack(fill="both", expand=True, padx=6, pady=(2, 6))
    body.columnconfigure(0, weight=1, uniform="analyse")
    body.columnconfigure(1, weight=3, uniform="analyse")
    body.rowconfigure(1, weight=1)

    lbl_tx_summary = ttk.Label(body, text="Ingen kontoer valgt.")
    lbl_tx_summary.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 4))

    # Pivot (konto-sammendrag)
    pivot_frame = ttk.Frame(body)
    pivot_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 6))
    pivot_frame.rowconfigure(0, weight=1)
    pivot_frame.columnconfigure(0, weight=1)

    pivot_tree = ttk.Treeview(
        pivot_frame,
        columns=getattr(page, "PIVOT_COLS", ("Konto", "Kontonavn", "Sum", "Antall")),
        show="headings",
        selectmode="extended",
    )
    pivot_tree.grid(row=0, column=0, sticky="nsew")
    for col in pivot_tree["columns"]:
        pivot_tree.heading(col, text=col)
        pivot_tree.column(col, width=140, anchor="w")
    pivot_tree.column("Konto", width=80)
    pivot_tree.column("Sum", width=110, anchor="e")
    pivot_tree.column("Antall", width=60, anchor="e")

    pv_scroll = ttk.Scrollbar(pivot_frame, orient="vertical", command=pivot_tree.yview)
    pv_scroll.grid(row=0, column=1, sticky="ns")
    pivot_tree.configure(yscrollcommand=pv_scroll.set)

    # Transaksjoner
    tx_frame = ttk.Frame(body)
    tx_frame.grid(row=1, column=1, sticky="nsew")
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

    # Tag for negative beløp (kredit) – brukes av page_analyse_transactions.refresh_transactions_view()
    try:
        tx_tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    tx_scroll = ttk.Scrollbar(tx_frame, orient="vertical", command=tx_tree.yview)
    tx_scroll.grid(row=0, column=1, sticky="ns")
    tx_tree.configure(yscrollcommand=tx_scroll.set)

    # Bindings
    # Konto-klikk skal oppdatere transaksjonslisten (bruk hook hvis den finnes, ellers fallback)
    _pivot_select_fn = getattr(page, "_on_pivot_select", None) or getattr(page, "_refresh_transactions_view", None)
    if callable(_pivot_select_fn):
        pivot_tree.bind("<<TreeviewSelect>>", lambda _e=None: _pivot_select_fn())
    else:  # pragma: no cover - defensive
        pivot_tree.bind("<<TreeviewSelect>>", lambda _e=None: None)

    _tx_select_fn = getattr(page, "_on_tx_select", None)
    if callable(_tx_select_fn):
        tx_tree.bind("<<TreeviewSelect>>", lambda _e=None: _tx_select_fn())

    # Bilag drilldown: dobbelklikk / Enter på transaksjonslisten
    _open_drill_fn = getattr(page, "_open_bilag_drilldown_from_tx_selection", None)
    if callable(_open_drill_fn):
        def _open_drill(_e=None):  # noqa: ANN001
            try:
                _open_drill_fn()
            except Exception:
                pass
            return "break"

        tx_tree.bind("<Double-1>", _open_drill)
        tx_tree.bind("<Return>", _open_drill)
        tx_tree.bind("<KP_Enter>", _open_drill)

    # Eksponer widgets til page_analyse
    page._var_search = var_search
    page._var_direction = var_dir
    page._var_max_rows = var_max_rows
    page._var_min = var_min
    page._var_max = var_max
    page._ent_search = ent_search
    page._lbl_tx_summary = lbl_tx_summary
    page._pivot_tree = pivot_tree
    page._tx_tree = tx_tree

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
            ent_min=ent_min,
            ent_max=ent_max,
            cmb_dir=cmb_dir,
            spn_max=spn_max,
        )
    except Exception:
        pass
