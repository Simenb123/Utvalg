from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .page_a07_shared import *  # noqa: F401,F403


class A07PageCanonicalUiMixin:
    """Canonical A07 layout.

    Direct support tabs (Forslag/Historikk/Koble kontoer/Kontroll/Umappet)
    and a fixed A07-grupper panel on the right of the lower workspace.
    """

    def _build_ui_canonical(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Last A07", command=self._load_a07_clicked).pack(side="left")
        ttk.Button(toolbar, text="Oppdater", command=self._refresh_clicked).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Eksporter", command=self._export_clicked).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, text="Basis:").pack(side="right", padx=(12, 4))
        self.basis_widget = ttk.Combobox(
            toolbar,
            state="readonly",
            width=10,
            values=[_BASIS_LABELS[key] for key in _BASIS_LABELS],
            textvariable=self.basis_var,
        )
        self.basis_widget.pack(side="right")
        self.basis_widget.bind("<<ComboboxSelected>>", lambda _event: self._on_basis_changed())

        tools_btn = ttk.Menubutton(toolbar, text="Mer...")
        tools_menu = tk.Menu(tools_btn, tearoff=0)
        tools_menu.add_command(label="Avansert mapping", command=self._open_manual_mapping_clicked)
        tools_menu.add_command(
            label="Apne Saldobalanse",
            command=lambda: self._open_saldobalanse_workspace(status_text="Apnet Saldobalanse."),
        )
        tools_menu.add_command(label="Kilder...", command=self._open_source_overview)
        tools_menu.add_command(label="Kontrolloppstilling...", command=self._open_control_statement_window)
        tools_menu.add_command(
            label="Lonns- og kontrolloppstilling...",
            command=self._open_rf1022_window,
        )
        tools_menu.add_separator()
        tools_menu.add_command(label="Bruk aktiv saldobalanse", command=self._sync_active_tb_clicked)
        tools_menu.add_separator()
        tools_menu.add_command(label="Last mapping", command=self._load_mapping_clicked)
        tools_menu.add_command(label="Lagre mapping", command=self._save_mapping_clicked)
        tools_menu.add_command(label="Vis mappinger", command=self._open_mapping_overview)
        tools_menu.add_command(label="Last rulebook", command=self._load_rulebook_clicked)
        tools_menu.add_command(label="Matcher-admin", command=self._open_matcher_admin)
        tools_menu.add_separator()
        tools_menu.add_command(label="Tryllestav", command=self._magic_match_clicked)
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

        control_top = ttk.Panedwindow(control_top_host, orient="horizontal")
        control_top.pack(fill="both", expand=True)

        control_gl_panel = ttk.LabelFrame(control_top, text="1. Saldobalansekontoer", padding=(6, 6))
        control_assign_panel = ttk.Frame(control_top, width=34, padding=(0, 6, 0, 0))
        control_a07_panel = ttk.LabelFrame(control_top, text="2. Velg A07-kode", padding=(6, 6))
        control_top.add(control_gl_panel, weight=4)
        control_top.add(control_assign_panel, weight=0)
        control_top.add(control_a07_panel, weight=5)
        try:
            control_assign_panel.pack_propagate(False)
        except Exception:
            pass

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
        ttk.Checkbutton(
            control_gl_filters,
            text="Kun aktive",
            variable=self.control_gl_active_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left")
        ttk.Checkbutton(
            control_gl_filters,
            text="Kun umappede",
            variable=self.control_gl_unmapped_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(control_gl_filters, text="Vis kontoer:").pack(side="left", padx=(12, 0))
        control_gl_scope = ttk.Combobox(
            control_gl_filters,
            state="readonly",
            width=24,
            values=[_CONTROL_GL_SCOPE_LABELS[key] for key in _CONTROL_GL_SCOPE_LABELS],
            textvariable=self.control_gl_scope_label_var,
        )
        control_gl_scope.pack(side="left", padx=(6, 0))
        self.control_gl_scope_widget = control_gl_scope
        control_gl_scope.set(_CONTROL_GL_SCOPE_LABELS["alle"])
        control_gl_scope.bind("<<ComboboxSelected>>", lambda _event: self._on_control_gl_scope_changed())
        self.tree_control_gl = self._build_tree_tab(control_gl_panel, _CONTROL_GL_COLUMNS)
        try:
            import vaak_tokens as vt  # type: ignore

            self.tree_control_gl.tag_configure("control_gl_unmapped", background=vt.hex_gui(vt.WARN_SOFT), foreground=vt.hex_gui(vt.WARN_TEXT))
            self.tree_control_gl.tag_configure("control_gl_mapped", background=vt.hex_gui(vt.BG_DATA), foreground=vt.hex_gui(vt.TEXT_PRIMARY))
            self.tree_control_gl.tag_configure("control_gl_selected", background=vt.hex_gui(vt.BG_SAND), foreground=vt.hex_gui(vt.TEXT_PRIMARY))
            self.tree_control_gl.tag_configure("control_gl_suggestion", background=vt.hex_gui(vt.POS_SOFT), foreground=vt.hex_gui(vt.POS_TEXT))
        except Exception:
            pass

        control_a07_filters = ttk.Frame(control_a07_panel)
        control_a07_filters.pack(fill="x", pady=(0, 4))
        ttk.Label(control_a07_filters, text="Vis:").pack(side="left")
        a07_filter = ttk.Combobox(
            control_a07_filters,
            state="readonly",
            width=14,
            values=[_CONTROL_VIEW_LABELS[key] for key in _CONTROL_VIEW_LABELS],
            textvariable=self.a07_filter_label_var,
        )
        a07_filter.pack(side="left", padx=(6, 0))
        self.a07_filter_widget = a07_filter
        a07_filter.set(_CONTROL_VIEW_LABELS["neste"])
        a07_filter.bind("<<ComboboxSelected>>", lambda _event: self._on_a07_filter_changed())
        ttk.Label(control_a07_filters, text="Sok:").pack(side="left", padx=(12, 0))
        self.entry_control_code_filter = ttk.Entry(
            control_a07_filters,
            textvariable=self.control_code_filter_var,
            width=14,
        )
        self.entry_control_code_filter.pack(side="left", padx=(6, 0))
        self.entry_control_code_filter.bind("<KeyRelease>", lambda _event: self._on_control_code_filter_changed())
        self.btn_control_toggle_details = ttk.Button(
            control_a07_filters,
            text="Vis detaljer",
            command=self._toggle_control_details,
        )
        self.btn_control_toggle_details.pack(side="right")
        ttk.Label(
            control_a07_filters,
            textvariable=self.control_bucket_var,
            style="Muted.TLabel",
            justify="right",
        ).pack(side="right", padx=(0, 10))

        self.tree_a07 = self._build_tree_tab(control_a07_panel, _CONTROL_COLUMNS)
        self.tree_a07.configure(selectmode="extended")
        try:
            import vaak_tokens as vt  # type: ignore

            self.tree_a07.tag_configure("control_done", background=vt.hex_gui(vt.POS_SOFT), foreground=vt.hex_gui(vt.POS_TEXT))
            self.tree_a07.tag_configure("control_review", background=vt.hex_gui(vt.WARN_SOFT), foreground=vt.hex_gui(vt.WARN_TEXT))
            self.tree_a07.tag_configure("control_manual", background=vt.hex_gui(vt.NEG_SOFT), foreground=vt.hex_gui(vt.NEG_TEXT))
            self.tree_a07.tag_configure("control_default", background=vt.hex_gui(vt.BG_DATA), foreground=vt.hex_gui(vt.TEXT_PRIMARY))
        except Exception:
            pass

        self.btn_control_assign = ttk.Button(
            control_assign_panel,
            text="->",
            width=4,
            command=self._assign_selected_control_mapping,
        )
        self.btn_control_assign.pack(fill="x", pady=(28, 0))
        self.btn_control_clear = ttk.Button(
            control_assign_panel,
            text="<-",
            width=4,
            command=self._clear_selected_control_mapping,
        )
        self.btn_control_clear.pack(fill="x", pady=(8, 0))
        for button in (self.btn_control_assign, self.btn_control_clear):
            button.state(["disabled"])

        control_status = ttk.Frame(control_lower, padding=(0, 2, 0, 0))
        control_status.pack(fill="x", pady=(2, 0))
        self.control_panel = control_status

        control_status_actions = ttk.Frame(control_status)
        control_status_actions.pack(side="right", anchor="ne")
        control_status_left = ttk.Frame(control_status)
        control_status_left.pack(side="left", fill="x", expand=True)
        self.lbl_control_summary = ttk.Label(
            control_status_left,
            textvariable=self.control_summary_var,
            style="Section.TLabel",
            wraplength=900,
            justify="left",
        )
        self.lbl_control_summary.pack(anchor="w")
        self.lbl_control_intro = ttk.Label(
            control_status_left,
            textvariable=self.control_intro_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_meta = ttk.Label(
            control_status_left,
            textvariable=self.control_meta_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_match = ttk.Label(
            control_status_left,
            textvariable=self.control_match_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_mapping = ttk.Label(
            control_status_left,
            textvariable=self.control_mapping_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_best = ttk.Label(
            control_status_left,
            textvariable=self.control_best_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_next = ttk.Label(
            control_status_left,
            textvariable=self.control_next_var,
            style="Section.TLabel",
            wraplength=980,
            justify="left",
        )
        self.lbl_control_drag = ttk.Label(
            control_status_left,
            textvariable=self.control_drag_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        )

        self.btn_control_smart = ttk.Button(
            control_status_actions,
            text="Prov automatisk",
            command=self._run_selected_control_action,
        )
        self.btn_control_smart.pack(side="right")
        for button in (self.btn_control_smart,):
            button.state(["disabled"])

        lower_body = ttk.Panedwindow(control_lower, orient="horizontal")
        lower_body.pack(fill="both", expand=True, pady=(2, 0))
        self.control_lower_body = lower_body

        support_host = ttk.Frame(lower_body)
        groups_side = ttk.LabelFrame(lower_body, text="A07-grupper", padding=(6, 6))
        lower_body.add(support_host, weight=4)
        lower_body.add(groups_side, weight=1)
        self.control_groups_panel = groups_side

        control_support_nb = ttk.Notebook(support_host)
        control_support_nb.pack(fill="both", expand=True)
        self.control_support_nb = control_support_nb

        tab_suggestions = ttk.Frame(control_support_nb)
        tab_history = ttk.Frame(control_support_nb)
        tab_mapping = ttk.Frame(control_support_nb)
        tab_control_statement = ttk.Frame(control_support_nb)
        tab_unmapped = ttk.Frame(control_support_nb)
        self.tab_suggestions = tab_suggestions
        self.tab_history = tab_history
        self.tab_mapping = tab_mapping
        self.tab_control_statement = tab_control_statement
        self.tab_unmapped = tab_unmapped
        # Legacy alias: surface the direct Forslag tab as tab_alternatives so
        # existing call sites that still reference the legacy container stay
        # wired to the visible Forslag tab (no nested mode picker anymore).
        self.tab_alternatives = tab_suggestions

        # Off-notebook compat frames (kept alive so legacy sync/render logic
        # that still references these attributes doesn't have to branch on
        # their existence; they are never shown in the A07-3A layout).
        self.tab_reconcile = ttk.Frame(self)
        self.control_alternative_history_actions = None
        self.control_alternative_suggestion_actions = None
        self.control_alternative_mode_widget = None

        suggestions_actions = ttk.Frame(tab_suggestions, padding=(8, 8, 8, 4))
        suggestions_actions.pack(fill="x")
        self.btn_control_batch_suggestions = ttk.Button(
            suggestions_actions,
            text="Bruk sikre forslag",
            command=self._apply_batch_suggestions_clicked,
        )
        self.btn_control_batch_suggestions.pack(side="right", padx=(6, 0))
        self.btn_control_best = ttk.Button(
            suggestions_actions,
            text="Bruk forslag",
            command=self._apply_selected_suggestion,
        )
        self.btn_control_best.pack(side="right")
        ttk.Label(
            suggestions_actions,
            textvariable=self.control_alternative_summary_var,
            style="Muted.TLabel",
            wraplength=760,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        for button in (self.btn_control_best, self.btn_control_batch_suggestions):
            button.state(["disabled"])

        self.tree_control_suggestions = self._build_tree_tab(tab_suggestions, _CONTROL_SUGGESTION_COLUMNS)
        self.tree_control_suggestions.configure(height=6)
        try:
            import vaak_tokens as vt  # type: ignore

            self.tree_control_suggestions.tag_configure("suggestion_ok", background=vt.hex_gui(vt.POS_SOFT), foreground=vt.hex_gui(vt.POS_TEXT))
            self.tree_control_suggestions.tag_configure("suggestion_review", background=vt.hex_gui(vt.WARN_SOFT), foreground=vt.hex_gui(vt.WARN_TEXT))
            self.tree_control_suggestions.tag_configure("suggestion_default", background=vt.hex_gui(vt.BG_DATA), foreground=vt.hex_gui(vt.TEXT_PRIMARY))
        except Exception:
            pass

        hidden_suggestions_host = ttk.Frame(self)
        self.tree_suggestions = self._build_tree_tab(hidden_suggestions_host, _SUGGESTION_COLUMNS)
        self.tree_suggestions.configure(height=1)
        try:
            import vaak_tokens as vt  # type: ignore

            self.tree_suggestions.tag_configure("suggestion_ok", background=vt.hex_gui(vt.POS_SOFT), foreground=vt.hex_gui(vt.POS_TEXT))
            self.tree_suggestions.tag_configure("suggestion_review", background=vt.hex_gui(vt.WARN_SOFT), foreground=vt.hex_gui(vt.WARN_TEXT))
            self.tree_suggestions.tag_configure("suggestion_default", background=vt.hex_gui(vt.BG_DATA), foreground=vt.hex_gui(vt.TEXT_PRIMARY))
        except Exception:
            pass

        suggestions_details = ttk.Frame(tab_suggestions, padding=(8, 6, 8, 8))
        suggestions_details.pack(fill="x")
        ttk.Label(
            suggestions_details,
            textvariable=self.control_suggestion_effect_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(anchor="w")
        ttk.Label(
            suggestions_details,
            textvariable=self.suggestion_details_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        history_actions = ttk.Frame(tab_history, padding=(8, 8, 8, 4))
        history_actions.pack(fill="x")
        self.btn_control_history = ttk.Button(
            history_actions,
            text="Bruk historikk",
            command=self._apply_selected_history_mapping,
        )
        self.btn_control_history.pack(side="right")
        self.btn_control_history.state(["disabled"])
        ttk.Label(
            history_actions,
            textvariable=self.history_details_var,
            style="Muted.TLabel",
            wraplength=760,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        self.tree_history = self._build_tree_tab(tab_history, _HISTORY_COLUMNS)
        self.tree_history.configure(height=6)

        control_accounts_panel = ttk.LabelFrame(tab_mapping, text="Koblede kontoer", padding=(8, 6))
        control_accounts_panel.pack(fill="both", expand=True, padx=8, pady=(8, 8))
        self.control_accounts_panel = control_accounts_panel
        control_accounts_top = ttk.Frame(control_accounts_panel)
        control_accounts_top.pack(fill="x", pady=(0, 6))
        ttk.Label(
            control_accounts_top,
            textvariable=self.control_accounts_summary_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        mapping_actions = ttk.Frame(control_accounts_top)
        mapping_actions.pack(side="right")
        ttk.Button(
            mapping_actions,
            text="Vis i GL",
            command=self._focus_selected_control_account_in_gl,
        ).pack(side="left")
        self.btn_control_remove_accounts = ttk.Button(
            mapping_actions,
            text="Fjern valgt",
            command=self._remove_selected_control_accounts,
        )
        self.btn_control_remove_accounts.pack(side="left", padx=(6, 0))
        self.tree_control_accounts = self._build_tree_tab(control_accounts_panel, _CONTROL_SELECTED_ACCOUNT_COLUMNS)
        self.tree_control_accounts.configure(height=6)

        self.tree_reconcile = self._build_tree_tab(self.tab_reconcile, _RECONCILE_COLUMNS)
        self.tree_reconcile.configure(height=6)
        try:
            import vaak_tokens as vt  # type: ignore

            self.tree_reconcile.tag_configure("reconcile_ok", background=vt.hex_gui(vt.POS_SOFT), foreground=vt.hex_gui(vt.POS_TEXT))
            self.tree_reconcile.tag_configure("reconcile_diff", background=vt.hex_gui(vt.NEG_SOFT), foreground=vt.hex_gui(vt.NEG_TEXT))
        except Exception:
            pass

        control_statement_top = ttk.Frame(tab_control_statement, padding=(8, 8, 8, 4))
        control_statement_top.pack(fill="x")
        ttk.Label(
            control_statement_top,
            textvariable=self.control_statement_summary_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            control_statement_top,
            text="Apne vindu",
            command=self._open_control_statement_window,
        ).pack(side="right")
        ttk.Button(
            control_statement_top,
            text="RF-1022...",
            command=self._open_rf1022_window,
        ).pack(side="right", padx=(8, 0))
        ttk.Label(control_statement_top, text="Visning:").pack(side="right", padx=(8, 4))
        control_statement_view = ttk.Combobox(
            control_statement_top,
            state="readonly",
            width=18,
            values=[_CONTROL_STATEMENT_VIEW_LABELS[key] for key in _CONTROL_STATEMENT_VIEW_LABELS],
            textvariable=self.control_statement_view_label_var,
        )
        control_statement_view.pack(side="right", padx=(8, 8))
        self.control_statement_view_widget = control_statement_view
        control_statement_view.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        control_statement_view.bind(
            "<<ComboboxSelected>>",
            lambda _event: self._on_control_statement_view_changed(),
        )
        self.tree_control_statement = self._build_tree_tab(tab_control_statement, _CONTROL_STATEMENT_COLUMNS)
        self.tree_control_statement.configure(height=5)
        control_statement_accounts_panel = ttk.LabelFrame(
            tab_control_statement,
            text="Konti i kontrolloppstilling",
            padding=(8, 6),
        )
        control_statement_accounts_panel.pack(fill="both", expand=True, padx=8, pady=(8, 8))
        control_statement_accounts_top = ttk.Frame(control_statement_accounts_panel)
        control_statement_accounts_top.pack(fill="x", pady=(0, 6))
        ttk.Label(
            control_statement_accounts_top,
            textvariable=self.control_statement_accounts_summary_var,
            style="Muted.TLabel",
            wraplength=980,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            control_statement_accounts_top,
            text="Vis i GL",
            command=self._focus_selected_control_account_in_gl,
        ).pack(side="right")
        self.tree_control_statement_accounts = self._build_tree_tab(
            control_statement_accounts_panel,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
        )
        self.tree_control_statement_accounts.configure(height=5)

        unmapped_intro = ttk.Label(
            tab_unmapped,
            text="Umappede kontoer fra gjeldende arbeidsgrunnlag. Bruk denne for a rydde opp kontoer som ikke er koblet enna.",
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        )
        unmapped_intro.pack(anchor="w", fill="x", padx=8, pady=(8, 4))
        self.tree_unmapped = self._build_tree_tab(tab_unmapped, _UNMAPPED_COLUMNS)
        self.tree_unmapped.configure(height=6)

        groups_intro = ttk.Label(
            groups_side,
            text="Grupper koder for aa behandle dem sammen.",
            style="Muted.TLabel",
            wraplength=260,
            justify="left",
        )
        groups_intro.pack(anchor="w", fill="x", pady=(0, 4))
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
            text="Opplos",
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

        hidden_mapping_host = ttk.Frame(self)
        self.tree_mapping = self._build_tree_tab(hidden_mapping_host, _MAPPING_COLUMNS)
        self.tree_mapping.configure(height=1)

        control_support_nb.add(tab_suggestions, text="Forslag")
        control_support_nb.add(tab_history, text="Historikk")
        control_support_nb.add(tab_mapping, text="Koble kontoer")
        control_support_nb.add(tab_control_statement, text="Kontroll")
        control_support_nb.add(tab_unmapped, text="Umappet")
        self.control_support_nb.bind("<<NotebookTabChanged>>", lambda _event: self._on_support_tab_changed(), add="+")

        self.tree_control_gl.bind("<<TreeviewSelect>>", lambda _event: self._on_control_gl_selection_changed())
        self.tree_control_gl.bind("<Double-1>", lambda _event: self._run_selected_control_gl_action())
        self.tree_control_gl.bind("<Return>", lambda _event: self._assign_selected_control_mapping())
        self.tree_control_gl.bind("<Delete>", lambda _event: self._clear_selected_control_mapping())
        self.tree_control_gl.bind("<B1-Motion>", self._start_control_gl_drag, add="+")
        self.tree_a07.bind("<<TreeviewSelect>>", lambda _event: self._on_control_selection_changed())
        self.tree_a07.bind("<Double-1>", lambda _event: self._run_selected_control_action())
        self.tree_a07.bind("<Motion>", self._track_unmapped_drop_target, add="+")
        self.tree_a07.bind("<ButtonRelease-1>", self._drop_unmapped_on_control, add="+")
        self.tree_history.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_history.bind("<Double-1>", lambda _event: self._apply_selected_history_mapping())
        self.tree_control_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_control_accounts.bind("<<TreeviewSelect>>", lambda _event: self._focus_selected_control_account_in_gl())
        self.tree_control_accounts.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_control_accounts.bind("<Delete>", lambda _event: self._remove_selected_control_accounts())
        self.tree_reconcile.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_control_statement.bind("<<TreeviewSelect>>", lambda _event: self._on_control_statement_selected())
        self.tree_control_statement_accounts.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._focus_selected_control_account_in_gl(),
        )
        self.tree_unmapped.bind("<B1-Motion>", self._start_unmapped_drag, add="+")
        self.tree_unmapped.bind("<Double-1>", lambda _event: self._map_selected_unmapped())
        self.tree_groups.bind("<<TreeviewSelect>>", lambda _event: self._on_group_selection_changed())
        self.tree_groups.bind("<Double-1>", lambda _event: self._focus_selected_group_code())
        self.tree_mapping.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_mapping.bind("<Delete>", lambda _event: self._remove_selected_mapping())

        self._sync_control_alternative_view()
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
