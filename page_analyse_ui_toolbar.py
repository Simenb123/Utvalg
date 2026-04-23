"""page_analyse_ui_toolbar.py

Filterlinje + Rapporter/Handlinger-menyer utskilt fra page_analyse_ui.build_ui.

Returnerer en SimpleNamespace med vars/widgets som panels-seksjonen trenger
(var_agg, var_rb, ent_search, ent_bilag, ent_date_from/to, cmb_dir, cmb_mva osv.).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Sequence

from page_analyse_ui_helpers import _build_period_range_picker


def build_toolbar(
    page: Any,
    *,
    tk: Any,
    ttk: Any,
    dir_labels: Sequence[str],
) -> SimpleNamespace:
    """Bygg filterlinje og menyer på `page`. Returnerer referansepakke.

    Args:
        page: AnalysePage-instans (ttk.Frame).
        tk, ttk: tkinter-moduler (lazy-injisert av build_ui).
        dir_labels: Retning-labels for combobox.
    """

    # -------------------------------------------------
    # Knyt widgetene til AnalysePage sine Tk-variabler
    # -------------------------------------------------
    var_search = getattr(page, "_var_search", None)
    if var_search is None:
        var_search = tk.StringVar(master=page, value="")

    var_dir = getattr(page, "_var_direction", None)
    if var_dir is None:
        var_dir = tk.StringVar(master=page, value=str(dir_labels[0]) if dir_labels else "Alle")

    var_bilag = getattr(page, "_var_bilag", None)
    if var_bilag is None:
        var_bilag = tk.StringVar(master=page, value="")

    var_motpart = getattr(page, "_var_motpart", None)
    if var_motpart is None:
        var_motpart = tk.StringVar(master=page, value="")

    var_date_from = getattr(page, "_var_date_from", None)
    if var_date_from is None:
        var_date_from = tk.StringVar(master=page, value="")

    var_date_to = getattr(page, "_var_date_to", None)
    if var_date_to is None:
        var_date_to = tk.StringVar(master=page, value="")

    var_max_rows = getattr(page, "_var_max_rows", None)
    if var_max_rows is None:
        var_max_rows = tk.IntVar(master=page, value=200)

    var_min = getattr(page, "_var_min", None)
    if var_min is None:
        var_min = tk.StringVar(master=page, value="")

    var_max = getattr(page, "_var_max", None)
    if var_max is None:
        var_max = tk.StringVar(master=page, value="")

    rb_filter_options = ("Alle", "Balanse", "Resultat")
    var_rb = getattr(page, "_var_rb", None)
    if var_rb is None:
        var_rb = tk.StringVar(master=page, value=rb_filter_options[0])

    mva_code_all_label = str(getattr(page, "MVA_CODE_ALL_LABEL", "Alle"))
    var_mva_code = getattr(page, "_var_mva_code", None)
    if var_mva_code is None:
        var_mva_code = tk.StringVar(master=page, value=mva_code_all_label)

    mva_code_values = list(getattr(page, "_mva_code_values", (mva_code_all_label,)))
    if not mva_code_values:
        mva_code_values = [mva_code_all_label]

    mva_filter_options = list(
        getattr(
            page,
            "MVA_FILTER_OPTIONS",
            (
                "Alle",
                "Med MVA-kode",
                "Uten MVA-kode",
                "Med MVA-beløp",
                "Uten MVA-beløp",
                "MVA-avvik",
            ),
        )
    )
    var_mva_mode = getattr(page, "_var_mva_mode", None)
    if var_mva_mode is None:
        default_mva = str(mva_filter_options[0]) if mva_filter_options else "Alle"
        var_mva_mode = tk.StringVar(master=page, value=default_mva)

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

    try:
        cur_mva_label = str(var_mva_mode.get())
    except Exception:
        cur_mva_label = ""
    if mva_filter_options and cur_mva_label not in [str(x) for x in mva_filter_options]:
        try:
            var_mva_mode.set(str(mva_filter_options[0]))
        except Exception:
            pass

    try:
        cur_mva_code = str(var_mva_code.get())
    except Exception:
        cur_mva_code = ""
    if mva_code_values and cur_mva_code not in [str(x) for x in mva_code_values]:
        try:
            var_mva_code.set(str(mva_code_values[0]))
        except Exception:
            pass

    # -------------------------------------------------
    # Helper: variabel-trace (programmatisk set() skal trigge filter/refresh)
    # -------------------------------------------------
    def _bind_var_write(var: Any, callback) -> None:
        """Best-effort bind til Tk variable endringer."""
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
    filter_frame = ttk.Frame(page)
    filter_frame.pack(fill="x", padx=6, pady=(6, 2))

    # Row 1: quick search + core filters + actions (right aligned)
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

    # Aggregering flyttes til over venstre pivot-panel (se lenger ned)
    var_agg = getattr(page, "_var_aggregering", None)
    if var_agg is None:
        var_agg = tk.StringVar(master=page, value="Saldobalanse")
    page._var_aggregering = var_agg

    # MVA-kode + Min/Maks beløp + MVA-filter er flyttet til "Mer filter…"-popup.
    # StringVars beholdes og leses fortsatt av filter-logikken.
    cmb_mva_code = None  # opprettes i popup ved behov, refereres ikke lenger her

    # Spacer to push buttons to the right
    row1.grid_columnconfigure(6, weight=1)

    advanced_cmd = getattr(page, "_open_advanced_filters", None)
    btn_advanced = ttk.Button(
        row1,
        text="Mer filter…",
        command=advanced_cmd if callable(advanced_cmd) else None,
        state=("normal" if callable(advanced_cmd) else "disabled"),
    )
    btn_advanced.grid(row=0, column=7, padx=(0, 6), sticky="e")

    # Visning-menubutton: samler de små av/på-bryterne (Skjul Σ, Vis nullsaldo,
    # Inkl. ÅO, Vis kun umappede, Desimaler) bak ett dropdown-element.
    view_btn = ttk.Menubutton(row1, text="Visning ▾", direction="below")
    view_btn.grid(row=0, column=8, padx=(0, 6), sticky="e")
    view_menu = tk.Menu(view_btn, tearoff=False)
    view_btn["menu"] = view_menu
    page._view_menu_btn = view_btn
    page._view_menu = view_menu

    columns_cmd = (
        getattr(page, "_open_column_chooser", None)
        or getattr(page, "_open_tx_column_chooser", None)
    )
    btn_columns = ttk.Button(
        row1,
        text="Kolonner...",
        command=columns_cmd if callable(columns_cmd) else None,
        state=("normal" if callable(columns_cmd) else "disabled"),
    )
    btn_columns.grid(row=0, column=9, padx=(0, 6), sticky="e")

    btn_reset = ttk.Button(row1, text="Nullstill", command=page._reset_filters)
    btn_reset.grid(row=0, column=10, padx=(0, 6), sticky="e")

    btn_select_all = ttk.Button(row1, text="Marker alle", command=page._select_all_accounts)
    btn_select_all.grid(row=0, column=11, padx=(0, 6), sticky="e")

    reports_btn = ttk.Menubutton(row1, text="Rapporter ▾", direction="below")
    reports_btn.grid(row=0, column=12, padx=(0, 6), sticky="e")

    actions_btn = ttk.Menubutton(row1, text="Handlinger ▾", direction="below")
    actions_btn.grid(row=0, column=13, sticky="e")

    # Datanivå-indikator (Hovedbok / Kun saldobalanse) — fjernet fra UI.
    # StringVar (_var_data_level) beholdes for bakoverkompat med eksisterende kode.

    actions_menu = tk.Menu(actions_btn, tearoff=False)
    actions_btn["menu"] = actions_menu
    reports_menu = tk.Menu(reports_btn, tearoff=False)
    reports_btn["menu"] = reports_menu

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

    rl_drill_cmd = getattr(page, "_open_rl_drilldown_from_pivot_selection", None)
    if callable(rl_drill_cmd):
        actions_menu.add_command(label="RL-drilldown til kontoer", command=rl_drill_cmd)
    else:
        actions_menu.add_command(label="RL-drilldown til kontoer", state="disabled")

    open_handl_cmd = getattr(page, "_open_handlinger_for_selected_rl", None)
    if callable(open_handl_cmd):
        actions_menu.add_command(label="Åpne Handlinger for valgt RL", command=open_handl_cmd)
    else:
        actions_menu.add_command(label="Åpne Handlinger for valgt RL", state="disabled")

    nr_series_cmd = getattr(page, "_open_nr_series_control", None)
    if callable(nr_series_cmd):
        actions_menu.add_command(label="Nr.-seriekontroll (valgt scope)", command=nr_series_cmd)
    else:
        actions_menu.add_command(label="Nr.-seriekontroll (valgt scope)", state="disabled")

    export_rl_cmd = getattr(page, "_export_regnskapsoppstilling_excel", None)
    if callable(export_rl_cmd):
        reports_menu.add_command(label="Eksporter regnskapsoppstilling til Excel", command=export_rl_cmd)
    else:
        reports_menu.add_command(label="Eksporter regnskapsoppstilling til Excel", state="disabled")

    export_nk_cmd = getattr(page, "_export_nokkeltall_html", None)
    if callable(export_nk_cmd):
        reports_menu.add_command(label="Nøkkeltallsrapport (HTML)", command=export_nk_cmd)
    else:
        reports_menu.add_command(label="Nøkkeltallsrapport (HTML)", state="disabled")

    export_nk_pdf_cmd = getattr(page, "_export_nokkeltall_pdf", None)
    if callable(export_nk_pdf_cmd):
        reports_menu.add_command(label="Nøkkeltallsrapport (PDF)", command=export_nk_pdf_cmd)
    else:
        reports_menu.add_command(label="Nøkkeltallsrapport (PDF)", state="disabled")

    flowchart_html_cmd = getattr(page, "_export_motpost_flowchart_html", None)
    if callable(flowchart_html_cmd):
        reports_menu.add_command(label="Motpost-flytdiagram (HTML)", command=flowchart_html_cmd)
    else:
        reports_menu.add_command(label="Motpost-flytdiagram (HTML)", state="disabled")

    flowchart_pdf_cmd = getattr(page, "_export_motpost_flowchart_pdf", None)
    if callable(flowchart_pdf_cmd):
        reports_menu.add_command(label="Motpost-flytdiagram (PDF)", command=flowchart_pdf_cmd)
    else:
        reports_menu.add_command(label="Motpost-flytdiagram (PDF)", state="disabled")

    ib_ub_cmd = getattr(page, "_export_ib_ub_control", None)
    if callable(ib_ub_cmd):
        reports_menu.add_command(label="SB/HB Avstemming", command=ib_ub_cmd)
    else:
        reports_menu.add_command(label="SB/HB Avstemming", state="disabled")

    continuity_cmd = getattr(page, "_export_ib_ub_continuity", None)
    if callable(continuity_cmd):
        reports_menu.add_command(label="IB/UB-kontinuitetskontroll", command=continuity_cmd)
    else:
        reports_menu.add_command(label="IB/UB-kontinuitetskontroll", state="disabled")

    hb_diff_cmd = getattr(page, "_export_hb_version_diff", None)
    if callable(hb_diff_cmd):
        reports_menu.add_command(label="HB Versjonsdiff", command=hb_diff_cmd)
    else:
        reports_menu.add_command(label="HB Versjonsdiff", state="disabled")

    ao_cmd = getattr(page, "_open_tilleggsposteringer", None)
    if callable(ao_cmd):
        actions_menu.add_command(label="Tilleggsposteringer (\u00c5O)\u2026", command=ao_cmd)
    else:
        actions_menu.add_command(label="Tilleggsposteringer (\u00c5O)\u2026", state="disabled")

    disposition_cmd = getattr(page, "_open_disponering_via_ao", None)
    if callable(disposition_cmd):
        actions_menu.add_command(label="Disponering via \u00c5O\u2026", command=disposition_cmd)
    else:
        actions_menu.add_command(label="Disponering via \u00c5O\u2026", state="disabled")

    actions_menu.add_separator()

    reset_columns_cmd      = getattr(page, "_reset_tx_columns_to_default", None)
    auto_fit_columns_cmd   = getattr(page, "_auto_fit_analyse_columns",    None)
    reset_widths_cmd       = getattr(page, "_reset_all_column_widths",     None)
    if callable(columns_cmd):
        actions_menu.add_command(label="Velg kolonner…", command=columns_cmd)
    else:
        actions_menu.add_command(label="Velg kolonner…", state="disabled")

    if callable(reset_columns_cmd):
        actions_menu.add_command(label="Standard kolonner", command=reset_columns_cmd)
    else:
        actions_menu.add_command(label="Standard kolonner", state="disabled")

    if callable(auto_fit_columns_cmd):
        actions_menu.add_command(label="Autotilpass kolonner", command=auto_fit_columns_cmd)
    else:
        actions_menu.add_command(label="Autotilpass kolonner", state="disabled")

    if callable(reset_widths_cmd):
        actions_menu.add_command(label="Tilbakestill kolonnebredder", command=reset_widths_cmd)
    else:
        actions_menu.add_command(label="Tilbakestill kolonnebredder", state="disabled")

    actions_menu.add_separator()

    # Overstyringssjekker
    override_cmd = getattr(page, "_open_override_checks", None)
    if callable(override_cmd):
        actions_menu.add_command(label="Overstyringssjekker", command=override_cmd)
    else:
        actions_menu.add_command(label="Overstyringssjekker", state="disabled")

    # Row 2: series + numeric/MVA filters
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

    # "Vis: <antall>" er flyttet til høyre panels header (over kolonnene).
    # Widget-referansen beholdes som None — page._var_max_rows leses fortsatt
    # av filter-logikken, og widget settes på page._spn_max fra panels.py.
    spn_max = None

    # Min/Maks beløp og MVA-filter er flyttet til "Mer filter…"-popup.
    # Widget-referansene beholdes som None — filter-logikken leser StringVars direkte.
    ent_min = None
    ent_max = None
    cmb_mva = None

    # Visning-bryterne (Skjul Σ, Vis nullsaldo, Inkl. ÅO, Vis kun umappede,
    # Desimaler) er flyttet til "Visning ▾"-menyen på rad 1.
    # _ao_count_label er fjernet (sjelden informativ).
    var_hide_sumposter = getattr(page, "_var_hide_sumposter", None)
    if var_hide_sumposter is not None:
        view_menu.add_checkbutton(
            label="Skjul Σ",
            variable=var_hide_sumposter,
            command=page._on_hide_sumposter_changed,
        )

    # Vis nullsaldo (speiler _var_hide_zero — checked = vis, unchecked = skjul).
    var_hide_zero = getattr(page, "_var_hide_zero", None)
    if var_hide_zero is not None:
        var_show_zero = getattr(page, "_var_show_zero", None)
        if var_show_zero is None:
            try:
                var_show_zero = tk.BooleanVar(master=page, value=not bool(var_hide_zero.get()))
            except Exception:
                var_show_zero = tk.BooleanVar(value=not bool(var_hide_zero.get()))
            page._var_show_zero = var_show_zero

        def _on_show_zero_toggle() -> None:
            try:
                var_hide_zero.set(not bool(var_show_zero.get()))
            except Exception:
                pass
            try:
                page._on_hide_zero_changed()
            except Exception:
                pass

        view_menu.add_checkbutton(
            label="Vis nullsaldo",
            variable=var_show_zero,
            command=_on_show_zero_toggle,
        )

    var_include_ao = getattr(page, "_var_include_ao", None)
    if var_include_ao is not None:
        view_menu.add_checkbutton(
            label="Inkl. ÅO",
            variable=var_include_ao,
            command=page._on_include_ao_changed,
        )

    var_show_only_unmapped = getattr(page, "_var_show_only_unmapped", None)
    if var_show_only_unmapped is not None:
        view_menu.add_checkbutton(
            label="Vis kun umappede",
            variable=var_show_only_unmapped,
            command=page._on_show_only_unmapped_changed,
        )

    var_decimals = getattr(page, "_var_decimals", None)
    if var_decimals is not None:
        def _on_decimals_toggle() -> None:
            try:
                page._on_tx_view_mode_changed()
            except Exception:
                pass
            try:
                page._refresh_pivot()
            except Exception:
                pass

        view_menu.add_checkbutton(
            label="Desimaler",
            variable=var_decimals,
            command=_on_decimals_toggle,
        )

    row2.grid_columnconfigure(4, weight=1)

    # Bilag/Motpart-feltene er fjernet fra toolbar (sjelden brukt i Analyse-fanen).
    # StringVars beholdes (var_bilag, var_motpart) som tomme — filter blir no-op.
    ent_bilag = None
    ent_motpart = None

    row3 = ttk.Frame(filter_frame)
    row3.pack(fill="x", pady=(4, 0))

    period_values = ["", *[str(i) for i in range(1, 13)]]
    period_picker, period_focus_widget = _build_period_range_picker(
        row3,
        tk=tk,
        ttk=ttk,
        var_date_from=var_date_from,
        var_date_to=var_date_to,
    )
    if period_picker is not None:
        period_picker.grid(row=0, column=0, sticky="w")
        ent_date_from = period_focus_widget
        ent_date_to = period_focus_widget
    else:
        ttk.Label(row3, text="Periode fra:").grid(row=0, column=0, sticky="w")
        ent_date_from = ttk.Combobox(
            row3,
            textvariable=var_date_from,
            values=period_values,
            width=5,
            state="readonly",
        )
        ent_date_from.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(row3, text="Periode til:").grid(row=0, column=2, sticky="w")
        ent_date_to = ttk.Combobox(
            row3,
            textvariable=var_date_to,
            values=period_values,
            width=5,
            state="readonly",
        )
        ent_date_to.grid(row=0, column=3, sticky="w", padx=(4, 0))

    row3.grid_columnconfigure(4, weight=1)

    # Ctrl+A i tekstfelt
    page._bind_entry_select_all(ent_search)

    # live filtering (debounced) + Enter for "apply now"
    ent_search.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())

    ent_search.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_date_from.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_date_to.bind("<Return>", lambda _e: page._apply_filters_now())

    cmb_dir.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    ent_date_from.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    ent_date_to.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    # NB: cmb_mva_code, ent_min, ent_max, cmb_mva, ent_bilag, ent_motpart har egne
    # bindings i "Mer filter…"-popup eller er fjernet — StringVar-trace under
    # sikrer at endringer fra popup eller programmatisk set() trigger filteret.

    # Variabel-trace: gjør at paste/programmatisk set() også trigger
    _bind_var_write(var_search, _live_filter_cb)
    _bind_var_write(var_bilag, _live_filter_cb)
    _bind_var_write(var_motpart, _live_filter_cb)
    _bind_var_write(var_date_from, _live_filter_cb)
    _bind_var_write(var_date_to, _live_filter_cb)
    _bind_var_write(var_min, _live_filter_cb)
    _bind_var_write(var_max, _live_filter_cb)
    _bind_var_write(var_mva_code, _live_filter_cb)
    _bind_var_write(var_mva_mode, _live_filter_cb)
    _bind_var_write(var_rb, _live_filter_cb)
    _bind_var_write(var_max_rows, _max_rows_cb)

    # Expose key widgets for tests / senere tweaks
    page._actions_btn = actions_btn
    page._actions_menu = actions_menu
    page._btn_columns = btn_columns
    page._ent_search = ent_search
    page._ent_bilag = ent_bilag
    page._ent_motpart = ent_motpart
    page._ent_date_from = ent_date_from
    page._ent_date_to = ent_date_to
    page._ent_mva = cmb_mva_code
    page._cmb_mva_code = cmb_mva_code
    page._cmb_dir = cmb_dir
    page._cmb_mva = cmb_mva
    page._spn_max = spn_max
    page._btn_reset = btn_reset
    page._btn_select_all = btn_select_all

    return SimpleNamespace(
        rb_filter_options=rb_filter_options,
        var_search=var_search,
        var_dir=var_dir,
        var_bilag=var_bilag,
        var_motpart=var_motpart,
        var_date_from=var_date_from,
        var_date_to=var_date_to,
        var_max_rows=var_max_rows,
        var_min=var_min,
        var_max=var_max,
        var_rb=var_rb,
        var_mva_code=var_mva_code,
        var_mva_mode=var_mva_mode,
        var_agg=var_agg,
        ent_search=ent_search,
        ent_bilag=ent_bilag,
        ent_motpart=ent_motpart,
        ent_date_from=ent_date_from,
        ent_date_to=ent_date_to,
        ent_min=ent_min,
        ent_max=ent_max,
        cmb_dir=cmb_dir,
        cmb_mva_code=cmb_mva_code,
        cmb_mva=cmb_mva,
        spn_max=spn_max,
        btn_reset=btn_reset,
        btn_select_all=btn_select_all,
    )
