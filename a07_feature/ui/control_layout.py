from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..page_a07_constants import (
    _A07_MATCHED_TAG,
    _A07_MATCH_FILTER_LABELS,
    _BASIS_LABELS,
    _CONTROL_COLUMNS,
    _CONTROL_GL_COLUMNS,
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_STATEMENT_VIEW_LABELS,
    _CONTROL_WORK_LEVEL_LABELS,
)


class A07PageControlLayoutMixin:
    def _build_control_top_panel(self, control_top_host: ttk.Frame) -> None:
        control_top = ttk.Panedwindow(control_top_host, orient="horizontal")
        control_top.pack(fill="both", expand=True)

        control_gl_panel = ttk.LabelFrame(control_top, text="1. Saldobalansekontoer", padding=(6, 6))
        control_a07_panel = ttk.LabelFrame(control_top, text="2. Velg A07-kode", padding=(6, 6))
        control_top.add(control_gl_panel, weight=4)
        control_top.add(control_a07_panel, weight=5)
        self.btn_control_assign = None
        self.btn_control_clear = None

        control_gl_filters = ttk.Frame(control_gl_panel)
        control_gl_filters.pack(fill="x", pady=(0, 4))
        ttk.Label(control_gl_filters, text="Filter:").pack(side="left")
        self.entry_control_gl_filter = ttk.Entry(
            control_gl_filters,
            textvariable=self.control_gl_filter_var,
            width=24,
        )
        self.entry_control_gl_filter.pack(side="left", padx=(6, 8))
        self.entry_control_gl_filter.bind("<KeyRelease>", lambda _event: self._on_control_gl_filter_changed())
        ttk.Label(control_gl_filters, text="Vis:").pack(side="left")
        control_gl_mapping_filter = ttk.Combobox(
            control_gl_filters,
            state="readonly",
            width=12,
            values=list(_CONTROL_GL_MAPPING_LABELS.values()),
            textvariable=self.control_gl_mapping_filter_label_var,
        )
        control_gl_mapping_filter.pack(side="left", padx=(6, 8))
        self.control_gl_mapping_filter_widget = control_gl_mapping_filter
        control_gl_mapping_filter.set(_CONTROL_GL_MAPPING_LABELS["alle"])
        control_gl_mapping_filter.bind("<<ComboboxSelected>>", lambda _event: self._on_control_gl_filter_changed())
        ttk.Checkbutton(
            control_gl_filters,
            text="Skjul null",
            variable=self.control_gl_active_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left", padx=(0, 8))
        ttk.Label(control_gl_filters, text="Kontoserier:").pack(side="left")
        series_frame = ttk.Frame(control_gl_filters)
        series_frame.pack(side="left", padx=(4, 8))
        series_vars = getattr(self, "control_gl_series_vars", None)
        if not isinstance(series_vars, list) or len(series_vars) != 10:
            series_vars = [tk.IntVar(value=0) for _ in range(10)]
            self.control_gl_series_vars = series_vars
        for digit, var in enumerate(series_vars):
            ttk.Checkbutton(
                series_frame,
                text=str(digit),
                variable=var,
                command=self._on_control_gl_series_filter_changed,
            ).grid(row=0, column=digit, sticky="w")
        self.control_gl_series_filter_widget = series_frame
        self._sync_control_gl_series_filter_from_checkboxes()
        self.control_gl_scope_widget = None
        try:
            self.control_gl_scope_var.set("alle")
        except Exception:
            pass
        self.tree_control_gl = self._build_tree_tab(control_gl_panel, _CONTROL_GL_COLUMNS)
        self.tree_control_gl.configure(selectmode="extended")
        self._register_selection_summary_tree(
            self.tree_control_gl,
            columns=("IB", "Endring", "UB"),
            row_noun="kontoer",
        )
        self._configure_tree_tags(
            self.tree_control_gl,
            {
                "control_gl_unmapped": ("WARN_SOFT", "WARN_TEXT"),
                "control_gl_mapped": ("BG_DATA", "TEXT_PRIMARY"),
                "control_gl_selected": ("SAGE_WASH", "FOREST"),
                "control_gl_suggestion": ("POS_SOFT", "POS_TEXT"),
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_ZEBRA", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
                "drop_target": ("WARN_SOFT", "TEXT_PRIMARY"),
            },
        )

        control_a07_filters = ttk.Frame(control_a07_panel)
        control_a07_filters.pack(fill="x", pady=(0, 4))
        self.control_work_level_widget = None
        try:
            self.control_work_level_var.set("a07")
            self.control_work_level_label_var.set(_CONTROL_WORK_LEVEL_LABELS["a07"])
            self.a07_filter_var.set("alle")
            self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
        except Exception:
            pass
        self.lbl_control_view_caption = None
        self.a07_filter_widget = None
        ttk.Label(control_a07_filters, text="Søk:").pack(side="left")
        self.entry_control_code_filter = ttk.Entry(
            control_a07_filters,
            textvariable=self.control_code_filter_var,
            width=18,
        )
        self.entry_control_code_filter.pack(side="left", padx=(6, 0))
        self.entry_control_code_filter.bind("<KeyRelease>", lambda _event: self._on_control_code_filter_changed())
        ttk.Label(control_a07_filters, text="Vis:").pack(side="left", padx=(12, 4))
        for filter_key, filter_label in _A07_MATCH_FILTER_LABELS.items():
            ttk.Radiobutton(
                control_a07_filters,
                text=filter_label,
                value=filter_key,
                variable=self.a07_match_filter_var,
                command=self._on_control_code_filter_changed,
            ).pack(side="left", padx=(0, 6))
        self.btn_control_toggle_advanced = ttk.Button(
            control_a07_filters,
            text="Vis avansert",
            command=self._toggle_control_advanced,
        )
        self.btn_control_toggle_advanced.pack(side="right", padx=(6, 0))
        self.btn_open_groups = ttk.Button(
            control_a07_filters,
            text="Grupper",
            command=lambda: self._open_groups_popup(None),
        )
        self.btn_open_groups.pack(side="right", padx=(6, 0))
        ttk.Label(
            control_a07_filters,
            textvariable=self.control_bucket_var,
            style="Muted.TLabel",
            justify="right",
            wraplength=420,
        ).pack(side="right", padx=(0, 10))
        control_drag_banner = ttk.Frame(control_a07_panel)
        control_drag_banner.pack(fill="x", pady=(0, 4))
        ttk.Label(
            control_drag_banner,
            text="Drag og slipp:",
            style="Section.TLabel",
        ).pack(side="left")
        self.lbl_control_drag = ttk.Label(
            control_drag_banner,
            textvariable=self.control_drag_var,
            style="Muted.TLabel",
            justify="left",
            wraplength=520,
        )
        self.lbl_control_drag.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.tree_a07 = self._build_tree_tab(control_a07_panel, _CONTROL_COLUMNS)
        self.tree_a07.configure(selectmode="extended")
        self._register_selection_summary_tree(
            self.tree_a07,
            columns=("A07_Belop", "A07", "GL_Belop", "Diff"),
            row_noun="poster",
            priority_columns=("A07_Belop", "A07", "GL_Belop", "Diff"),
        )
        self._configure_tree_tags(
            self.tree_a07,
            {
                "control_done": ("POS_SOFT", "POS_TEXT"),
                "control_review": ("WARN_SOFT", "WARN_TEXT"),
                "control_manual": ("NEG_SOFT", "NEG_TEXT"),
                "control_default": ("BG_DATA", "TEXT_PRIMARY"),
                _A07_MATCHED_TAG: ("SAGE", "FOREST"),
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_ZEBRA", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
                "drop_target": ("FOREST", "TEXT_ON_FOREST"),
                "summary_total": ("FOREST", "TEXT_ON_FOREST"),
            },
        )
        self._configure_summary_total_tag(self.tree_a07)

    def _build_control_status_panel(self, control_lower: ttk.Frame) -> None:
        self._compact_control_status = True
        control_status = ttk.Frame(control_lower, padding=(0, 0, 0, 0))
        self.control_panel = control_status

        control_status_body = ttk.Frame(control_status)
        control_status_body.pack(side="left", fill="x", expand=True)
        control_status_actions = ttk.Frame(control_status)
        control_status_actions.pack(side="right", anchor="ne")
        self.lbl_control_summary = ttk.Label(
            control_status_body,
            textvariable=self.control_summary_var,
        )
        self.lbl_control_meta = ttk.Label(
            control_status_body,
            textvariable=self.control_meta_var,
            style="Muted.TLabel",
        )
        self.lbl_control_next = ttk.Label(
            control_status_body,
            textvariable=self.control_next_var,
            style="Muted.TLabel",
            wraplength=860,
            justify="left",
        )
        self.lbl_control_intro = None
        self.lbl_control_match = None
        self.lbl_control_mapping = None
        self.lbl_control_best = None

        self._control_smart_button_removed = True
        self.btn_control_smart = ttk.Button(
            control_status_actions,
            text="Kontroller kobling",
            command=self._run_selected_control_action,
        )
        self.btn_control_smart.state(["disabled"])

    def _add_control_statement_view_menu(self, tools_menu: tk.Menu) -> tk.Menu:
        view_menu = tk.Menu(tools_menu, tearoff=0)
        for view_key, label in _CONTROL_STATEMENT_VIEW_LABELS.items():
            view_menu.add_radiobutton(
                label=label,
                variable=self.control_statement_view_var,
                value=view_key,
                command=lambda view_key=view_key: self._set_control_statement_view_from_menu(view_key),
            )
        tools_menu.add_cascade(label="Kontrollvisning", menu=view_menu)
        return view_menu


__all__ = ["A07PageControlLayoutMixin"]
