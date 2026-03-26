"""Motpostanalyse (GUI) - UI building.

Denne modulen inneholder kun Tkinter/ttk-bygging av widgets.

Mål:
    - Gjøre :mod:`views_motpost_konto` mindre og mer vedlikeholdbar.
    - Unngå at lange tekster (mange valgte kontoer) presser vinduet bredt.

NB:
    - Kjerneberegninger ligger i :mod:`motpost.konto_core`.
    - Visningen (render) ligger i :mod:`motpost.view_konto_render`.
"""

from __future__ import annotations

from typing import Any, Callable

import tkinter as tk
from tkinter import ttk

from formatting import fmt_amount
from motpost_konto_core import MotpostData


def build_motpost_header_metrics_text(data: MotpostData) -> str:
    """Bygg kompakt metrikk-tekst (uten konto-listen).

    Konto-listen kan bli veldig lang og bør ikke være en del av en Label som
    bestemmer vinduets min-bredde.
    """

    dir_label = getattr(data, "selected_direction", "Alle")
    sum_label = "Sum valgte kontoer" if dir_label == "Alle" else f"Sum valgte kontoer ({str(dir_label).lower()})"
    return (
        f"Bilag i grunnlag: {getattr(data, 'bilag_count', 0)}  |  "
        f"{sum_label}: {fmt_amount(getattr(data, 'selected_sum', 0.0))}  |  "
        f"Kontroll (valgt + mot): {fmt_amount(getattr(data, 'control_sum', 0.0))}"
    )


def build_motpost_selected_accounts_label(data: MotpostData) -> str:
    accounts = list(getattr(data, "selected_accounts", ()) or ())
    return f"Valgte kontoer ({len(accounts)}):"


def build_motpost_selected_accounts_value(data: MotpostData) -> str:
    accounts = list(getattr(data, "selected_accounts", ()) or ())
    return ", ".join([str(a) for a in accounts])


def build_motpost_scope_label(scope_items: list[str] | tuple[str, ...] | None, *, scope_mode: str = "konto") -> str:
    items = [str(x).strip() for x in (scope_items or ()) if str(x).strip()]
    noun = "regnskapslinjer" if str(scope_mode or "").strip().lower().startswith("regn") else "valg"
    return f"Valgte {noun} ({len(items)}):"


def build_motpost_scope_value(scope_items: list[str] | tuple[str, ...] | None) -> str:
    return ", ".join([str(x).strip() for x in (scope_items or ()) if str(x).strip()])


def build_motpost_expected_label(expected_items: list[str] | tuple[str, ...] | None) -> str:
    items = [str(x).strip() for x in (expected_items or ()) if str(x).strip()]
    return f"Forventede regnskapslinjer ({len(items)}):"


def build_motpost_expected_value(expected_items: list[str] | tuple[str, ...] | None) -> str:
    return ", ".join([str(x).strip() for x in (expected_items or ()) if str(x).strip()])


def bind_entry_select_all(entry: Any) -> None:
    """Binder Ctrl+A til "marker alt" på en ttk.Entry.

    Duck typing: fungerer i tester med DummyEntry som har bind/selection_range/icursor.
    """

    def _select_all(_event=None):
        try:
            entry.selection_range(0, "end")
            entry.icursor("end")
        except Exception:
            pass
        return "break"

    try:
        entry.bind("<Control-a>", _select_all)
        entry.bind("<Control-A>", _select_all)
    except Exception:
        # Ikke kritisk om dette feiler (f.eks. i headless tester).
        pass


def build_ui(
    view: Any,
    *,
    enable_treeview_sorting_fn: Callable[[Any], None],
    configure_bilag_details_tree_fn: Callable[..., None],
) -> None:
    """Bygg widgets i MotpostKontoView.

    view forventes å ha:
        - _data (MotpostData)
        - _details_limit_var (tk.IntVar)
        - callbacks: _show_combinations, _mark_outlier, _clear_outliers,
          _export_excel, destroy, _on_select_motkonto, _drilldown, _open_bilag_drilldown
    """

    top = ttk.Frame(view)
    top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=8)
    top.columnconfigure(0, weight=1)

    # Rad 0: kompakt metrikk til venstre, knapper til høyre
    metrics_txt = build_motpost_header_metrics_text(view._data)
    view._info_label = ttk.Label(top, text=metrics_txt)
    view._info_label.grid(row=0, column=0, sticky="w")

    btn_frame = ttk.Frame(top)
    btn_frame.grid(row=0, column=1, sticky="e")

    ttk.Button(btn_frame, text="Kombinasjoner", command=view._show_combinations).pack(side=tk.LEFT, padx=(0, 12))
    ttk.Button(btn_frame, text="Merk outlier", command=view._mark_outlier).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_frame, text="Nullstill outliers", command=view._clear_outliers).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_frame, text="Eksporter Excel", command=view._export_excel).pack(side=tk.LEFT, padx=(0, 6))
    ttk.Button(btn_frame, text="Lukk", command=view.destroy).pack(side=tk.LEFT)

    current_row = 1
    if getattr(view, "_scope_mode", "konto") == "regnskapslinje" and getattr(view, "_scope_items", ()):
        scope_row = ttk.Frame(top)
        scope_row.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        scope_row.columnconfigure(1, weight=1)

        ttk.Label(
            scope_row,
            text=build_motpost_scope_label(getattr(view, "_scope_items", ()), scope_mode="regnskapslinje"),
        ).grid(row=0, column=0, sticky="w")
        view._scope_var = tk.StringVar(value=build_motpost_scope_value(getattr(view, "_scope_items", ())))
        view._scope_entry = ttk.Entry(scope_row, textvariable=view._scope_var, state="readonly")
        view._scope_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        bind_entry_select_all(view._scope_entry)
        current_row += 1

    if getattr(view, "_expected_regnskapslinjer", ()):
        expected_row = ttk.Frame(top)
        expected_row.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        expected_row.columnconfigure(1, weight=1)

        ttk.Label(
            expected_row,
            text=build_motpost_expected_label(getattr(view, "_expected_regnskapslinjer", ())),
        ).grid(row=0, column=0, sticky="w")
        view._expected_regnskapslinjer_var = tk.StringVar(
            value=build_motpost_expected_value(getattr(view, "_expected_regnskapslinjer", ()))
        )
        view._expected_regnskapslinjer_entry = ttk.Entry(
            expected_row,
            textvariable=view._expected_regnskapslinjer_var,
            state="readonly",
        )
        view._expected_regnskapslinjer_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        bind_entry_select_all(view._expected_regnskapslinjer_entry)
        current_row += 1

    # Neste rad: konto-liste i readonly entry (hindrer at vinduet blir altfor bredt)
    accounts_row = ttk.Frame(top)
    accounts_row.grid(row=current_row, column=0, columnspan=2, sticky="ew", pady=(6, 0))
    accounts_row.columnconfigure(1, weight=1)

    selected_account_count = len(list(getattr(view._data, "selected_accounts", ()) or ()))
    accounts_label = (
        f"Underliggende kontoer ({selected_account_count}):"
        if getattr(view, "_scope_mode", "konto") == "regnskapslinje"
        else build_motpost_selected_accounts_label(view._data)
    )
    ttk.Label(accounts_row, text=accounts_label).grid(row=0, column=0, sticky="w")
    view._selected_accounts_var = tk.StringVar(value=build_motpost_selected_accounts_value(view._data))
    view._selected_accounts_entry = ttk.Entry(accounts_row, textvariable=view._selected_accounts_var, state="readonly")
    view._selected_accounts_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    bind_entry_select_all(view._selected_accounts_entry)

    # Mid: motkonto pivot
    mid = ttk.Frame(view)
    mid.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10)
    ttk.Label(mid, text="Motkonto (pivot)").pack(anchor=tk.W)

    columns = ("Motkonto", "Kontonavn", "Sum", "% andel", "Antall bilag", "Outlier")
    view._tree_summary = ttk.Treeview(mid, columns=columns, show="headings", selectmode="extended")
    for c in columns:
        view._tree_summary.heading(c, text=c)
        view._tree_summary.column(c, width=120 if c != "Tekst" else 300, anchor=tk.W)

    view._tree_summary.column("Sum", anchor=tk.E, width=140)
    view._tree_summary.column("% andel", anchor=tk.E, width=90)
    view._tree_summary.column("Antall bilag", anchor=tk.E, width=90)
    view._tree_summary.column("Outlier", anchor=tk.W, width=70)

    enable_treeview_sorting_fn(view._tree_summary)

    yscroll = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=view._tree_summary.yview)
    view._tree_summary.configure(yscrollcommand=yscroll.set)

    view._tree_summary.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    yscroll.pack(side=tk.RIGHT, fill=tk.Y)

    view._tree_summary.tag_configure("neg", foreground="red")
    view._tree_summary.tag_configure("expected", background="#C6EFCE")
    view._tree_summary.tag_configure("outlier", background="#FFF2CC")
    view._tree_summary.bind("<<TreeviewSelect>>", view._on_select_motkonto)

    # Bottom: bilag-liste for valgt motkonto
    bottom = ttk.Frame(view)
    bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=(8, 10))

    header = ttk.Frame(bottom)
    header.pack(side=tk.TOP, fill=tk.X)

    def _bind_refresh(widget: Any) -> None:
        try:
            widget.bind("<<ComboboxSelected>>", lambda _event=None: view._refresh_details(), add="+")
            return
        except Exception:
            pass
        try:
            widget.bind("<<ComboboxSelected>>", lambda _event=None: view._refresh_details())
        except Exception:
            pass

    ttk.Label(header, text="Bilag for valgt motkonto").pack(side=tk.LEFT)
    ttk.Label(header, text="Vis:").pack(side=tk.LEFT, padx=(10, 2))

    sp = ttk.Spinbox(
        header,
        from_=50,
        to=5000,
        increment=50,
        width=7,
        textvariable=view._details_limit_var,
        command=view._refresh_details,
    )
    sp.pack(side=tk.LEFT)

    ttk.Label(header, text="MVA-kode:").pack(side=tk.LEFT, padx=(10, 2))
    view._details_mva_code_combo = ttk.Combobox(
        header,
        width=8,
        state="readonly",
        textvariable=view._details_mva_code_var,
        values=tuple(getattr(view, "_details_mva_code_values", ["Alle"])),
    )
    view._details_mva_code_combo.pack(side=tk.LEFT)
    _bind_refresh(view._details_mva_code_combo)

    ttk.Label(header, text="Forventet %:").pack(side=tk.LEFT, padx=(10, 2))
    view._details_expected_mva_combo = ttk.Combobox(
        header,
        width=6,
        state="readonly",
        textvariable=view._details_expected_mva_var,
        values=tuple(getattr(view, "_details_expected_mva_values", ["25", "15", "12", "0"])),
    )
    view._details_expected_mva_combo.pack(side=tk.LEFT)
    _bind_refresh(view._details_expected_mva_combo)

    ttk.Label(header, text="MVA-visning:").pack(side=tk.LEFT, padx=(10, 2))
    view._details_mva_mode_combo = ttk.Combobox(
        header,
        width=18,
        state="readonly",
        textvariable=view._details_mva_mode_var,
        values=tuple(
            getattr(
                view,
                "_details_mva_mode_values",
                ["Alle", "Med MVA-kode", "Uten MVA-kode", "Treffer forventet", "Avvik fra forventet"],
            )
        ),
    )
    view._details_mva_mode_combo.pack(side=tk.LEFT)
    _bind_refresh(view._details_mva_mode_combo)

    ttk.Button(header, text="Drilldown", command=view._drilldown).pack(side=tk.RIGHT)

    columns2 = (
        "Bilag",
        "Dato",
        "Tekst",
        "Beløp (valgte kontoer)",
        "Motbeløp",
        "MVA-kode",
        "MVA-prosent",
        "MVA-beløp",
        "Kontoer i bilag",
    )
    tree_wrap = ttk.Frame(bottom)
    tree_wrap.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    view._tree_details = ttk.Treeview(tree_wrap, columns=columns2, show="headings", selectmode="extended")
    for c in columns2:
        view._tree_details.heading(c, text=c)
        view._tree_details.column(c, width=120, anchor=tk.W)

    view._tree_details.column("Tekst", width=260)
    view._tree_details.column("Beløp (valgte kontoer)", anchor=tk.E, width=150)
    view._tree_details.column("Motbeløp", anchor=tk.E, width=120)
    view._tree_details.column("MVA-kode", anchor=tk.CENTER, width=85)
    view._tree_details.column("MVA-prosent", anchor=tk.CENTER, width=95)
    view._tree_details.column("MVA-beløp", anchor=tk.E, width=120)
    view._tree_details.column("Kontoer i bilag", width=145)

    enable_treeview_sorting_fn(view._tree_details)

    yscroll2 = ttk.Scrollbar(tree_wrap, orient=tk.VERTICAL, command=view._tree_details.yview)
    xscroll2 = ttk.Scrollbar(bottom, orient=tk.HORIZONTAL, command=view._tree_details.xview)
    view._tree_details.configure(yscrollcommand=yscroll2.set, xscrollcommand=xscroll2.set)

    view._tree_details.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    yscroll2.pack(side=tk.RIGHT, fill=tk.Y)
    xscroll2.pack(side=tk.TOP, fill=tk.X, pady=(2, 0))

    view._tree_details.tag_configure("neg", foreground="red")
    view._tree_details.tag_configure("mva_avvik", background="#FCE4D6")

    configure_bilag_details_tree_fn(view._tree_details, open_bilag_callback=view._open_bilag_drilldown)
