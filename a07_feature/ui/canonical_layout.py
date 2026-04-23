from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import ui_selection_summary

from ..page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _BASIS_LABELS,
    _CONTROL_COLUMNS,
    _CONTROL_GL_COLUMNS,
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_GL_SERIES_LABELS,
    _CONTROL_RF1022_COLUMNS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_STATEMENT_VIEW_LABELS,
    _CONTROL_SUGGESTION_COLUMNS,
    _CONTROL_VIEW_LABELS,
    _CONTROL_WORK_LEVEL_LABELS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_COLUMNS,
    _MAPPING_FILTER_LABELS,
    _RECONCILE_COLUMNS,
    _SUGGESTION_COLUMNS,
    _UNMAPPED_COLUMNS,
)


class A07PageCanonicalUiMixin:
    """Canonical A07 layout.

    Guided workspace with direct tabs for Forslag/Koblinger/Kontroll.
    Historikk, Umappet and grupper remain available as advanced surfaces.
    """

    def _build_ui_canonical(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Last A07", command=self._load_a07_clicked).pack(side="left")
        ttk.Button(toolbar, text="Oppdater", command=self._refresh_clicked).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, text="Beløpsbasis:").pack(side="right", padx=(12, 4))
        self.basis_widget = ttk.Combobox(
            toolbar,
            state="readonly",
            width=10,
            values=[_BASIS_LABELS[key] for key in _BASIS_LABELS],
            textvariable=self.basis_var,
        )
        self.basis_widget.pack(side="right")
        self.basis_widget.bind("<<ComboboxSelected>>", lambda _event: self._on_basis_changed())

        tools_btn = ttk.Menubutton(toolbar, text="Verktøy")
        tools_menu = tk.Menu(tools_btn, tearoff=0)
        tools_menu.add_command(label="Avansert mapping", command=self._open_manual_mapping_clicked)
        tools_menu.add_command(label="Eksporter", command=self._export_clicked)
        tools_menu.add_command(
            label="Åpne saldobalanse",
            command=lambda: self._open_saldobalanse_workspace(status_text="Apnet Saldobalanse."),
        )
        tools_menu.add_command(label="Kilder...", command=self._open_source_overview)
        tools_menu.add_command(label="Kontrolloppstilling...", command=self._open_control_statement_window)
        tools_menu.add_command(
            label="Lønns- og kontrolloppstilling...",
            command=self._open_rf1022_window,
        )
        tools_menu.add_separator()
        self._add_control_statement_view_menu(tools_menu)
        tools_menu.add_command(label="Bruk aktiv saldobalanse", command=self._sync_active_tb_clicked)
        tools_menu.add_separator()
        tools_menu.add_command(label="Last mapping", command=self._load_mapping_clicked)
        tools_menu.add_command(label="Lagre mapping", command=self._save_mapping_clicked)
        tools_menu.add_command(label="Vis mappinger", command=self._open_mapping_overview)
        advanced_menu = tk.Menu(tools_menu, tearoff=0)
        advanced_menu.add_command(label="Last regelsett", command=self._load_rulebook_clicked)
        tools_menu.add_cascade(label="Avansert", menu=advanced_menu)
        tools_menu.add_command(label="A07-regler...", command=self._open_a07_rulebook_admin)
        tools_btn["menu"] = tools_menu
        tools_btn.pack(side="left", padx=(12, 0))
        ttk.Label(
            toolbar,
            textvariable=self.summary_var,
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))

        workspace_host = ttk.Frame(self, padding=(8, 0, 8, 8))
        workspace_host.pack(fill="both", expand=True)

        tab_control = ttk.Frame(workspace_host)
        tab_control.pack(fill="both", expand=True)
        self.tab_control = tab_control

        control_workspace = ttk.Frame(tab_control)
        control_workspace.pack(fill="both", expand=True, pady=(2, 0))
        self.control_workspace = control_workspace

        control_vertical = ttk.Panedwindow(control_workspace, orient="vertical")
        control_vertical.pack(fill="both", expand=True)
        control_top_host = ttk.Frame(control_vertical)
        control_lower = ttk.Frame(control_vertical)
        control_vertical.add(control_top_host, weight=5)
        control_vertical.add(control_lower, weight=2)
        self.control_vertical_panes = control_vertical
        self.control_lower_panel = control_lower

        self._build_control_top_panel(control_top_host)
        self._build_control_status_panel(control_lower)

        lower_body = ttk.Panedwindow(control_lower, orient="horizontal")
        lower_body.pack(fill="both", expand=True, pady=(2, 0))
        self.control_lower_body = lower_body

        support_host = ttk.Frame(lower_body)
        groups_side = ttk.LabelFrame(lower_body, text="A07-grupper", padding=(6, 6))
        lower_body.add(support_host, weight=4)
        lower_body.add(groups_side, weight=1)
        self.control_groups_panel = groups_side

        self._build_support_notebook(support_host)
        self._build_groups_sidepanel(groups_side)
        self._build_hidden_compat_surfaces()
        self._bind_canonical_events()

        self._sync_control_alternative_view()
        sync_work_level_ui = getattr(self, "_sync_control_work_level_ui", None)
        if callable(sync_work_level_ui):
            sync_work_level_ui()
        self._set_control_advanced_visible(False)
        self._set_control_details_visible(True)
        self._sync_control_panel_visibility()
        self._sync_groups_panel_visibility()

        ttk.Label(
            self,
            textvariable=self.status_var,
            style="Muted.TLabel",
            anchor="w",
            justify="left",
            padding=(10, 0, 10, 8),
        ).pack(fill="x")

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
        ttk.Label(control_gl_filters, text="Kontoserie:").pack(side="left")
        control_gl_series_filter = ttk.Combobox(
            control_gl_filters,
            state="readonly",
            width=11,
            values=list(_CONTROL_GL_SERIES_LABELS.values()),
            textvariable=self.control_gl_series_filter_label_var,
        )
        control_gl_series_filter.pack(side="left", padx=(6, 8))
        self.control_gl_series_filter_widget = control_gl_series_filter
        control_gl_series_filter.set(_CONTROL_GL_SERIES_LABELS["alle"])
        control_gl_series_filter.bind("<<ComboboxSelected>>", lambda _event: self._on_control_gl_filter_changed())
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
                "control_gl_selected": ("BG_SAND", "TEXT_PRIMARY"),
                "control_gl_suggestion": ("POS_SOFT", "POS_TEXT"),
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_SAND", "TEXT_PRIMARY"),
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
        self.btn_control_toggle_advanced = ttk.Button(
            control_a07_filters,
            text="Vis avansert",
            command=self._toggle_control_advanced,
        )
        self.btn_control_toggle_advanced.pack(side="right", padx=(6, 0))
        ttk.Label(
            control_a07_filters,
            textvariable=self.control_bucket_var,
            style="Muted.TLabel",
            justify="right",
            wraplength=420,
        ).pack(side="right", padx=(0, 10))

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
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_SAND", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
                "summary_total": ("BG_SAND", "TEXT_PRIMARY"),
            },
        )

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
        self.lbl_control_drag = None

        self.btn_control_smart = ttk.Button(
            control_status_actions,
            text="Kontroller kobling",
            command=self._run_selected_control_action,
        )
        self.btn_control_smart.pack(side="right")
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

    def _build_support_notebook(self, support_host: ttk.Frame) -> None:
        control_support_nb = ttk.Notebook(support_host)
        control_support_nb.pack(fill="both", expand=True)
        self.control_support_nb = control_support_nb

        self.tab_suggestions = ttk.Frame(control_support_nb)
        self.tab_history = ttk.Frame(control_support_nb)
        self.tab_mapping = ttk.Frame(control_support_nb)
        self.tab_control_statement = ttk.Frame(control_support_nb)
        self.tab_unmapped = ttk.Frame(control_support_nb)
        self.tab_alternatives = self.tab_suggestions
        self.control_alternative_history_actions = None
        self.control_alternative_suggestion_actions = None
        self.control_alternative_mode_widget = None

        suggestions_actions = ttk.Frame(self.tab_suggestions, padding=(8, 8, 8, 4))
        suggestions_actions.pack(fill="x")
        self.control_suggestions_actions = suggestions_actions
        ttk.Label(
            suggestions_actions,
            textvariable=self.control_suggestion_summary_var,
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True)
        self.btn_control_batch_suggestions = ttk.Button(
            suggestions_actions,
            text="Kjør trygg auto-matching",
            command=self._apply_batch_suggestions_clicked,
        )
        self.btn_control_batch_suggestions.pack(side="right", padx=(6, 0))
        self.btn_control_best = ttk.Button(
            suggestions_actions,
            text="Bruk trygg kandidat",
            command=self._apply_selected_suggestion,
        )
        self.btn_control_best.pack(side="right")
        for button in (self.btn_control_best, self.btn_control_batch_suggestions):
            button.state(["disabled"])

        self.tree_control_suggestions = self._build_tree_tab(self.tab_suggestions, _CONTROL_SUGGESTION_COLUMNS)
        self.tree_control_suggestions.configure(height=6)
        self._register_selection_summary_tree(
            self.tree_control_suggestions,
            columns=("A07_Belop", "GL_Sum", "Diff"),
            row_noun="forslag",
        )
        self._configure_tree_tags(
            self.tree_control_suggestions,
            {
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
                "suggestion_default": ("BG_DATA", "TEXT_PRIMARY"),
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_SAND", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
            },
        )

        history_actions = ttk.Frame(self.tab_history, padding=(8, 8, 8, 4))
        history_actions.pack(fill="x")
        self.btn_control_history = ttk.Button(
            history_actions,
            text="Bruk historikk",
            command=self._apply_selected_history_mapping,
        )
        self.btn_control_history.pack(side="right")
        self.btn_control_history.state(["disabled"])
        self.tree_history = self._build_tree_tab(self.tab_history, _HISTORY_COLUMNS)
        self.tree_history.configure(height=6)

        control_accounts_panel = ttk.LabelFrame(self.tab_mapping, text="Koblinger", padding=(8, 6))
        control_accounts_panel.pack(fill="both", expand=True, padx=8, pady=(8, 8))
        self.control_accounts_panel = control_accounts_panel
        self.btn_control_remove_accounts = None
        mapping_filter_bar = ttk.Frame(control_accounts_panel)
        mapping_filter_bar.pack(fill="x", pady=(0, 4))
        ttk.Label(mapping_filter_bar, text="Vis:").pack(side="left", padx=(0, 4))
        self.mapping_filter_widget = ttk.Combobox(
            mapping_filter_bar,
            textvariable=self.mapping_filter_label_var,
            values=list(_MAPPING_FILTER_LABELS.values()),
            width=14,
            state="readonly",
        )
        self.mapping_filter_widget.pack(side="left")
        self.mapping_filter_widget.bind("<<ComboboxSelected>>", self._on_mapping_filter_changed, add="+")
        self.btn_next_mapping_problem = ttk.Button(
            mapping_filter_bar,
            text="Neste problem",
            command=self._focus_next_control_account_problem,
        )
        self.btn_next_mapping_problem.pack(side="left", padx=(8, 0))
        self.btn_next_mapping_problem.state(["disabled"])
        ttk.Label(
            mapping_filter_bar,
            textvariable=self.control_accounts_summary_var,
            style="Muted.TLabel",
        ).pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.tree_control_accounts = self._build_tree_tab(control_accounts_panel, _CONTROL_SELECTED_ACCOUNT_COLUMNS)
        self.tree_control_accounts.configure(height=6, selectmode="extended")
        self._register_selection_summary_tree(
            self.tree_control_accounts,
            columns=("IB", "Endring", "UB"),
            row_noun="kontoer",
        )
        self._configure_tree_tags(
            self.tree_control_accounts,
            {
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_SAND", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
            },
        )

        self.control_statement_view_widget = None
        control_statement_accounts_panel = ttk.Frame(
            self.tab_control_statement,
            padding=(0, 0),
        )
        control_statement_accounts_panel.pack(fill="both", expand=True)
        self.control_statement_accounts_panel = control_statement_accounts_panel
        self.tree_control_statement_accounts = self._build_tree_tab(
            control_statement_accounts_panel,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
        )
        self.tree_control_statement_accounts.configure(height=5)
        self._register_selection_summary_tree(
            self.tree_control_statement_accounts,
            columns=("IB", "Endring", "UB"),
            row_noun="kontoer",
        )
        self._configure_tree_tags(
            self.tree_control_statement_accounts,
            {
                "family_payroll": ("SAGE_WASH", "FOREST"),
                "family_refund": ("POS_SOFT", "POS_TEXT"),
                "family_natural": ("WARN_SOFT", "WARN_TEXT"),
                "family_pension": ("BG_SAND", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
            },
        )

        self.tree_unmapped = self._build_tree_tab(self.tab_unmapped, _UNMAPPED_COLUMNS)
        self.tree_unmapped.configure(height=6)

        control_support_nb.add(self.tab_suggestions, text="Forslag")
        control_support_nb.add(self.tab_mapping, text="Koblinger")
        self.control_support_nb.bind("<<NotebookTabChanged>>", lambda _event: self._on_support_tab_changed(), add="+")

    def _build_groups_sidepanel(self, groups_side: ttk.LabelFrame) -> None:
        groups_actions = ttk.Frame(groups_side)
        groups_actions.pack(fill="x", pady=(0, 4))
        self.btn_create_group = ttk.Button(
            groups_actions,
            text="Opprett",
            command=self._create_group_from_selection,
        )
        self.btn_create_group.pack(side="left")
        self.btn_rename_group = ttk.Button(
            groups_actions,
            text="Gi nytt navn",
            command=self._rename_selected_group,
        )
        self.btn_rename_group.pack(side="left", padx=(6, 0))
        self.btn_remove_group = ttk.Button(
            groups_actions,
            text="Oppløs",
            command=self._remove_selected_group,
        )
        self.btn_remove_group.pack(side="left", padx=(6, 0))
        self.btn_focus_group = ttk.Button(
            groups_actions,
            text="Fokuser",
            command=self._focus_selected_group_code,
        )
        self.btn_focus_group.pack(side="left", padx=(6, 0))
        self.tree_groups = self._build_tree_tab(groups_side, _GROUP_COLUMNS)
        self.tree_groups.configure(height=6)

    def _build_hidden_compat_surfaces(self) -> None:
        hidden_suggestions_host = ttk.Frame(self)
        self.tree_suggestions = self._build_tree_tab(hidden_suggestions_host, _SUGGESTION_COLUMNS)
        self.tree_suggestions.configure(height=1)
        self._configure_tree_tags(
            self.tree_suggestions,
            {
                "suggestion_ok": ("POS_SOFT", "POS_TEXT"),
                "suggestion_review": ("WARN_SOFT", "WARN_TEXT"),
                "suggestion_default": ("BG_DATA", "TEXT_PRIMARY"),
            },
        )

        hidden_mapping_host = ttk.Frame(self)
        self.tree_mapping = self._build_tree_tab(hidden_mapping_host, _MAPPING_COLUMNS)
        self.tree_mapping.configure(height=1)

        hidden_control_statement_host = ttk.Frame(self)
        self.tree_control_statement = self._build_tree_tab(hidden_control_statement_host, _CONTROL_STATEMENT_COLUMNS)
        self.tree_control_statement.configure(height=1)

        # Legacy compat only: reconcile is no longer an active support surface.
        self.tab_reconcile = None
        self.tree_reconcile = None

    def _bind_canonical_events(self) -> None:
        self.tree_control_gl.bind("<<TreeviewSelect>>", lambda _event: self._on_control_gl_selection_changed())
        self.tree_control_gl.bind("<Double-1>", lambda _event: self._run_selected_control_gl_action())
        self.tree_control_gl.bind("<Return>", lambda _event: self._assign_selected_control_mapping())
        self.tree_control_gl.bind("<Delete>", lambda _event: self._clear_selected_control_mapping())
        self.tree_control_gl.bind("<Button-3>", self._show_control_gl_context_menu, add="+")
        self.tree_control_gl.bind("<B1-Motion>", self._start_control_gl_drag, add="+")
        self.tree_a07.bind("<<TreeviewSelect>>", lambda _event: self._on_control_selection_changed())
        self.tree_a07.bind("<Double-1>", lambda _event: self._link_selected_control_rows())
        self.tree_a07.bind("<Return>", lambda _event: self._link_selected_control_rows())
        self.tree_a07.bind("<Button-3>", self._show_control_code_context_menu, add="+")
        self.tree_a07.bind("<Motion>", self._track_unmapped_drop_target, add="+")
        self.tree_a07.bind("<ButtonRelease-1>", self._drop_unmapped_on_control, add="+")
        self.tree_history.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_history.bind("<Double-1>", lambda _event: self._apply_selected_history_mapping())
        self.tree_control_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_control_suggestions.bind("<Button-3>", self._show_control_suggestions_context_menu, add="+")
        self.tree_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_suggestions.bind("<Button-3>", self._show_control_suggestions_context_menu, add="+")
        self.tree_control_accounts.bind("<<TreeviewSelect>>", lambda _event: self._update_a07_action_button_state())
        self.tree_control_accounts.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_control_accounts.bind("<Delete>", lambda _event: self._remove_selected_control_accounts())
        self.tree_control_accounts.bind("<Button-3>", self._show_control_accounts_context_menu, add="+")
        self.tree_control_statement.bind("<<TreeviewSelect>>", lambda _event: self._on_control_statement_selected())
        self.tree_control_statement_accounts.bind("<<TreeviewSelect>>", lambda _event: self._update_a07_action_button_state())
        self.tree_control_statement_accounts.bind("<Double-1>", lambda _event: self._focus_selected_control_statement_account_in_gl())
        self.tree_control_statement_accounts.bind("<Return>", lambda _event: self._focus_selected_control_statement_account_in_gl())
        self.tree_control_statement_accounts.bind("<Button-3>", self._show_control_statement_accounts_context_menu, add="+")
        self.tree_unmapped.bind("<B1-Motion>", self._start_unmapped_drag, add="+")
        self.tree_unmapped.bind("<Double-1>", lambda _event: self._map_selected_unmapped())
        self.tree_groups.bind("<<TreeviewSelect>>", lambda _event: self._on_group_selection_changed())
        self.tree_groups.bind("<Double-1>", lambda _event: self._focus_selected_group_code())
        self.tree_groups.bind("<Button-3>", self._show_group_context_menu, add="+")
        self.tree_mapping.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_mapping.bind("<Delete>", lambda _event: self._remove_selected_mapping())

    def _register_selection_summary_tree(
        self,
        tree: ttk.Treeview,
        *,
        columns: tuple[str, ...],
        row_noun: str,
        priority_columns: tuple[str, ...] | None = None,
    ) -> None:
        try:
            ui_selection_summary.register_treeview_selection_summary(
                tree,
                columns=columns,
                row_noun=row_noun,
                max_items=3,
                hide_zero=False,
                priority_columns=priority_columns or columns,
            )
        except Exception:
            pass

    def _configure_tree_tags(
        self,
        tree: ttk.Treeview,
        tag_tokens: dict[str, tuple[str, str]],
    ) -> None:
        try:
            import vaak_tokens as vt  # type: ignore

            for tag_name, (bg_token, fg_token) in tag_tokens.items():
                tree.tag_configure(
                    tag_name,
                    background=vt.hex_gui(getattr(vt, bg_token)),
                    foreground=vt.hex_gui(getattr(vt, fg_token)),
                )
        except Exception:
            pass
