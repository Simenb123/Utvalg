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


def _safe_period_value(raw: object) -> int | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = int(text)
    except Exception:
        return None
    if 1 <= value <= 12:
        return value
    return None


def _build_period_range_picker(
    master: Any,
    *,
    tk: Any,
    ttk: Any,
    var_date_from: Any,
    var_date_to: Any,
) -> tuple[Any | None, Any | None]:
    canvas_cls = getattr(tk, "Canvas", None)
    if canvas_cls is None:
        return None, None

    outer = ttk.Frame(master)
    ttk.Label(outer, text="Periode:").pack(side="left")

    canvas_width = 380
    canvas_height = 52

    canvas = canvas_cls(
        outer,
        width=canvas_width,
        height=canvas_height,
        highlightthickness=0,
        bd=0,
        relief="flat",
        background="#FFFFFF",
    )
    canvas.pack(side="left", padx=(8, 10))

    btn_reset = ttk.Button(
        outer,
        text="Hele året",
        command=lambda: _set_range(None, None),
    )
    btn_reset.pack(side="left")

    left_pad = 18
    right_pad = 18
    base_y = 24
    marker_r = 5

    def _month_x(month: int) -> float:
        usable = canvas_width - left_pad - right_pad
        if usable <= 0:
            return float(left_pad)
        return float(left_pad + ((month - 1) / 11.0) * usable)

    def _current_range() -> tuple[int | None, int | None]:
        from_value = _safe_period_value(getattr(var_date_from, "get", lambda: "")())
        to_value = _safe_period_value(getattr(var_date_to, "get", lambda: "")())
        if from_value is None or to_value is None:
            return (None, None)
        if from_value <= to_value:
            return (from_value, to_value)
        return (to_value, from_value)

    def _set_range(from_value: int | None, to_value: int | None) -> None:
        try:
            var_date_from.set("" if from_value is None else str(int(from_value)))
            var_date_to.set("" if to_value is None else str(int(to_value)))
        except Exception:
            return
        _redraw()

    def _closest_month(x_value: float) -> int:
        positions = [(month, abs(x_value - _month_x(month))) for month in range(1, 13)]
        return min(positions, key=lambda item: item[1])[0]

    def _on_click(event) -> str:  # noqa: ANN001
        month = _closest_month(float(getattr(event, "x", 0)))
        from_value, to_value = _current_range()
        if from_value is None or to_value is None:
            _set_range(month, month)
            return "break"
        if abs(month - from_value) <= abs(month - to_value):
            from_value = month
        else:
            to_value = month
        if from_value > to_value:
            from_value, to_value = to_value, from_value
        _set_range(from_value, to_value)
        return "break"

    def _on_double_click(_event=None) -> str:
        _set_range(None, None)
        return "break"

    def _redraw() -> None:
        try:
            canvas.delete("all")
        except Exception:
            return

        from_value, to_value = _current_range()
        line_start = _month_x(1)
        line_end = _month_x(12)

        canvas.create_line(line_start, base_y, line_end, base_y, fill="#7A869A", width=2)

        if from_value is not None and to_value is not None:
            canvas.create_line(
                _month_x(from_value),
                base_y,
                _month_x(to_value),
                base_y,
                fill="#2F6FED",
                width=6,
                capstyle="round",
            )

        for month in range(1, 13):
            x = _month_x(month)
            canvas.create_line(x, base_y - 8, x, base_y + 8, fill="#4C6A91", width=1)
            if from_value is None or to_value is None:
                fill = "#FFFFFF"
                outline = "#4C6A91"
            elif from_value <= month <= to_value:
                fill = "#FFF59D" if month not in {from_value, to_value} else "#2F6FED"
                outline = "#2F6FED"
            else:
                fill = "#FFFFFF"
                outline = "#4C6A91"
            canvas.create_oval(
                x - marker_r,
                base_y - marker_r,
                x + marker_r,
                base_y + marker_r,
                fill=fill,
                outline=outline,
                width=2 if month in {from_value, to_value} else 1,
            )
            canvas.create_text(x, base_y + 16, text=str(month), fill="#42526E")

        status_text = "Hele året" if from_value is None or to_value is None else f"{from_value}-{to_value}"
        canvas.create_text(line_end, 8, text=status_text, anchor="e", fill="#2F6FED")

    try:
        canvas.bind("<Button-1>", _on_click)
        canvas.bind("<Double-1>", _on_double_click)
    except Exception:
        pass

    try:
        var_date_from.trace_add("write", lambda *_: _redraw())
        var_date_to.trace_add("write", lambda *_: _redraw())
    except Exception:
        pass

    _redraw()
    return outer, canvas


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

    ttk.Label(row1, text="Aggregering:").grid(row=0, column=4, sticky="w", padx=(0, 2))
    var_agg = getattr(page, "_var_aggregering", None)
    if var_agg is None:
        var_agg = tk.StringVar(master=page, value="Konto")
    cmb_agg = ttk.Combobox(
        row1,
        textvariable=var_agg,
        values=["Konto", "Regnskapslinje", "MVA-kode"],
        width=16,
        state="readonly",
    )
    cmb_agg.grid(row=0, column=5, sticky="w", padx=(0, 12))
    _agg_changed = getattr(page, "_on_aggregering_changed", None)
    if callable(_agg_changed):
        cmb_agg.bind("<<ComboboxSelected>>", lambda _e: _agg_changed())
    page._cmb_agg = cmb_agg
    page._var_aggregering = var_agg

    ttk.Label(row1, text="MVA-kode:").grid(row=0, column=6, sticky="w", padx=(0, 2))
    cmb_mva_code = ttk.Combobox(
        row1,
        textvariable=var_mva_code,
        values=mva_code_values,
        width=12,
        state="readonly",
    )
    cmb_mva_code.grid(row=0, column=7, sticky="w", padx=(0, 12))

    # Spacer to push buttons to the right (keeps room for e.g. date/periode filters later)
    row1.grid_columnconfigure(8, weight=1)

    columns_cmd = getattr(page, "_open_tx_column_chooser", None)
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

    actions_btn = ttk.Menubutton(row1, text="Handlinger ▾", direction="below")
    actions_btn.grid(row=0, column=12, sticky="e")

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

    rl_drill_cmd = getattr(page, "_open_rl_drilldown_from_pivot_selection", None)
    if callable(rl_drill_cmd):
        actions_menu.add_command(label="RL-drilldown til kontoer", command=rl_drill_cmd)
    else:
        actions_menu.add_command(label="RL-drilldown til kontoer", state="disabled")

    nr_series_cmd = getattr(page, "_open_nr_series_control", None)
    if callable(nr_series_cmd):
        actions_menu.add_command(label="Nr.-seriekontroll (valgt scope)", command=nr_series_cmd)
    else:
        actions_menu.add_command(label="Nr.-seriekontroll (valgt scope)", state="disabled")

    export_rl_cmd = getattr(page, "_export_regnskapsoppstilling_excel", None)
    if callable(export_rl_cmd):
        actions_menu.add_command(label="Eksporter regnskapsoppstilling til Excel", command=export_rl_cmd)
    else:
        actions_menu.add_command(label="Eksporter regnskapsoppstilling til Excel", state="disabled")

    ib_ub_cmd = getattr(page, "_export_ib_ub_control", None)
    if callable(ib_ub_cmd):
        actions_menu.add_command(label="SB/HB Avstemming (IB/UB-kontroll)", command=ib_ub_cmd)
    else:
        actions_menu.add_command(label="SB/HB Avstemming (IB/UB-kontroll)", state="disabled")

    hb_diff_cmd = getattr(page, "_export_hb_version_diff", None)
    if callable(hb_diff_cmd):
        actions_menu.add_command(label="HB Versjonsdiff", command=hb_diff_cmd)
    else:
        actions_menu.add_command(label="HB Versjonsdiff", state="disabled")

    mva_avstemming_cmd = getattr(page, "_open_mva_avstemming", None)
    if callable(mva_avstemming_cmd):
        actions_menu.add_command(label="MVA-avstemming (Skatteetaten)", command=mva_avstemming_cmd)
    else:
        actions_menu.add_command(label="MVA-avstemming (Skatteetaten)", state="disabled")

    ao_cmd = getattr(page, "_open_tilleggsposteringer", None)
    if callable(ao_cmd):
        actions_menu.add_command(label="Tilleggsposteringer (\u00c5O)\u2026", command=ao_cmd)
    else:
        actions_menu.add_command(label="Tilleggsposteringer (\u00c5O)\u2026", state="disabled")

    actions_menu.add_separator()

    reset_columns_cmd = getattr(page, "_reset_tx_columns_to_default", None)
    auto_fit_columns_cmd = getattr(page, "_auto_fit_analyse_columns", None)
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
    ent_max.grid(row=0, column=7, sticky="w", padx=(4, 12))

    ttk.Label(row2, text="MVA-filter:").grid(row=0, column=8, sticky="w")
    cmb_mva = ttk.Combobox(
        row2,
        textvariable=var_mva_mode,
        values=mva_filter_options,
        width=18,
        state="readonly",
    )
    cmb_mva.grid(row=0, column=9, sticky="w", padx=(4, 0))

    btn_mva_setup = ttk.Button(
        row2,
        text="MVA-oppsett\u2026",
        command=page._open_mva_config,
        style="Secondary.TButton",
    )
    btn_mva_setup.grid(row=0, column=10, sticky="w", padx=(8, 0))

    # Skjul sumposter (kun relevant for Regnskapslinje-aggregering)
    var_hide_sumposter = getattr(page, "_var_hide_sumposter", None)
    if var_hide_sumposter is not None:
        cb_hide_sum = ttk.Checkbutton(
            row2, text="Skjul \u03a3",
            variable=var_hide_sumposter,
            command=page._on_hide_sumposter_changed,
        )
        cb_hide_sum.grid(row=0, column=11, sticky="w", padx=(12, 0))
        page._cb_hide_sumposter = cb_hide_sum

    # Inkluder tilleggsposteringer (ÅO)
    var_include_ao = getattr(page, "_var_include_ao", None)
    if var_include_ao is not None:
        cb_ao = ttk.Checkbutton(
            row2, text="Inkl. \u00c5O",
            variable=var_include_ao,
            command=page._on_include_ao_changed,
        )
        cb_ao.grid(row=0, column=12, sticky="w", padx=(8, 0))

    row2.grid_columnconfigure(13, weight=1)

    row3 = ttk.Frame(filter_frame)
    row3.pack(fill="x", pady=(4, 0))

    ttk.Label(row3, text="Bilag:").grid(row=0, column=0, sticky="w")
    ent_bilag = ttk.Entry(row3, width=14, textvariable=var_bilag)
    ent_bilag.grid(row=0, column=1, sticky="w", padx=(4, 12))

    ttk.Label(row3, text="Motpart:").grid(row=0, column=2, sticky="w")
    ent_motpart = ttk.Entry(row3, width=24, textvariable=var_motpart)
    ent_motpart.grid(row=0, column=3, sticky="w", padx=(4, 12))

    row3.grid_columnconfigure(4, weight=1)

    row4 = ttk.Frame(filter_frame)
    row4.pack(fill="x", pady=(4, 0))

    period_values = ["", *[str(i) for i in range(1, 13)]]
    period_picker, period_focus_widget = _build_period_range_picker(
        row4,
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
        ttk.Label(row4, text="Periode fra:").grid(row=0, column=0, sticky="w")
        ent_date_from = ttk.Combobox(
            row4,
            textvariable=var_date_from,
            values=period_values,
            width=5,
            state="readonly",
        )
        ent_date_from.grid(row=0, column=1, sticky="w", padx=(4, 12))

        ttk.Label(row4, text="Periode til:").grid(row=0, column=2, sticky="w")
        ent_date_to = ttk.Combobox(
            row4,
            textvariable=var_date_to,
            values=period_values,
            width=5,
            state="readonly",
        )
        ent_date_to.grid(row=0, column=3, sticky="w", padx=(4, 0))

    row4.grid_columnconfigure(4, weight=1)

    # Ctrl+A i tekstfelt
    page._bind_entry_select_all(ent_search)
    page._bind_entry_select_all(ent_bilag)
    page._bind_entry_select_all(ent_motpart)
    page._bind_entry_select_all(ent_min)
    page._bind_entry_select_all(ent_max)

    # live filtering (debounced) + Enter for "apply now"
    ent_search.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_bilag.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_motpart.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_min.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())
    ent_max.bind("<KeyRelease>", lambda _e: page._schedule_apply_filters())

    ent_search.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_bilag.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_motpart.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_date_from.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_date_to.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_min.bind("<Return>", lambda _e: page._apply_filters_now())
    ent_max.bind("<Return>", lambda _e: page._apply_filters_now())
    cmb_mva_code.bind("<Return>", lambda _e: page._apply_filters_now())

    cmb_mva_code.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    cmb_dir.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    ent_date_from.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    ent_date_to.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())
    cmb_mva.bind("<<ComboboxSelected>>", lambda _e: page._apply_filters_now())

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

    # Visual separation from the lists below
    ttk.Separator(page, orient="horizontal").pack(fill="x", padx=6, pady=(0, 2))
    body = ttk.Frame(page)
    body.pack(fill="both", expand=True, padx=6, pady=(2, 6))
    body.columnconfigure(0, weight=1)
    body.rowconfigure(1, weight=1)

    lbl_tx_summary = ttk.Label(body, text="Ingen kontoer valgt.")
    lbl_tx_summary.grid(row=0, column=0, sticky="w", pady=(0, 4))

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

    try:
        import tkinter.font as tkfont  # type: ignore

        sum_font = tkfont.nametofont("TkDefaultFont").copy()
        sum_font.configure(weight="bold")
        major_font = tkfont.nametofont("TkDefaultFont").copy()
        major_font.configure(weight="bold")
        # Delsummer: subtil bakgrunn
        pivot_tree.tag_configure("sumline", background="#EDF1F5", foreground="#2C4A6E", font=sum_font)
        # Hovedsummer (Driftsresultat, Årsresultat etc.): sterkere visuell markering
        pivot_tree.tag_configure("sumline_major", background="#D6E2EF", foreground="#1A3350", font=major_font)
    except Exception:
        try:
            pivot_tree.tag_configure("sumline", background="#EDF1F5", foreground="#2C4A6E")
            pivot_tree.tag_configure("sumline_major", background="#D6E2EF", foreground="#1A3350")
        except Exception:
            pass

    pv_scroll = ttk.Scrollbar(pivot_frame, orient="vertical", command=pivot_tree.yview)
    pv_scroll.grid(row=0, column=1, sticky="ns")
    pv_hscroll = ttk.Scrollbar(pivot_frame, orient="horizontal", command=pivot_tree.xview)
    pv_hscroll.grid(row=1, column=0, sticky="ew")
    pivot_tree.configure(yscrollcommand=pv_scroll.set, xscrollcommand=pv_hscroll.set)

    # Høyreklikkmeny for pivot-kolonner (vis/skjul)
    _pivot_col_menu_fn = getattr(page, "_show_pivot_column_menu", None)
    if callable(_pivot_col_menu_fn):
        pivot_tree.bind("<Button-3>", _pivot_col_menu_fn)

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
    tx_header.columnconfigure(1, weight=1)

    ttk.Label(tx_header, text="Visning:").grid(row=0, column=0, padx=(0, 4))

    _var_tx_mode = getattr(page, "_var_tx_view_mode", None)
    if _var_tx_mode is not None:
        _tx_mode_cb = ttk.Combobox(
            tx_header,
            textvariable=_var_tx_mode,
            values=["Transaksjoner", "Saldobalansekontoer"],
            state="readonly",
            width=20,
        )
        _tx_mode_cb.grid(row=0, column=1, sticky="w")

        _on_tx_mode_fn = getattr(page, "_on_tx_view_mode_changed", None)
        if callable(_on_tx_mode_fn):
            _tx_mode_cb.bind("<<ComboboxSelected>>", lambda _e: _on_tx_mode_fn())
    else:
        ttk.Label(tx_header, text="Transaksjoner").grid(row=0, column=1, sticky="w")

    tx_outer.rowconfigure(1, weight=1)
    tx_outer.columnconfigure(0, weight=1)

    # --- TX-frame (transaksjoner) ---
    tx_frame = ttk.Frame(tx_outer)
    tx_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
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

    _pivot_release_fn = getattr(page, "_on_pivot_tree_mouse_release", None)
    if callable(_pivot_release_fn):
        pivot_tree.bind("<ButtonRelease-1>", lambda e: _pivot_release_fn(e))

    _tx_select_fn = getattr(page, "_on_tx_select", None)
    if callable(_tx_select_fn):
        tx_tree.bind("<<TreeviewSelect>>", lambda _e=None: _tx_select_fn())

    _detail_select_fn = getattr(page, "_on_detail_account_select", None)
    if callable(_detail_select_fn):
        detail_accounts_tree.bind("<<TreeviewSelect>>", lambda _e=None: _detail_select_fn())

    _tx_double_click_fn = getattr(page, "_on_tx_tree_double_click", None)
    _tx_release_fn = getattr(page, "_on_tx_tree_mouse_release", None)
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
    page._ent_search = ent_search
    page._lbl_tx_summary = lbl_tx_summary
    page._body_split = split_body
    page._detail_panel = None
    page._detail_split = None
    page._detail_accounts_tree = None
    page._detail_suggestion_tree = None
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
