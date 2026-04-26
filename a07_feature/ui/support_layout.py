from __future__ import annotations

from tkinter import ttk

from ..page_a07_constants import (
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_SUGGESTION_COLUMNS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_FILTER_LABELS,
    _UNMAPPED_COLUMNS,
)


class A07PageSupportLayoutMixin:
    def _build_support_workspace(
        self,
        suggestions_host: ttk.Frame,
        accounts_host: ttk.Frame,
    ) -> None:
        self.control_support_nb = None

        self.tab_suggestions = suggestions_host
        self.tab_history = ttk.Frame(self)
        self.tab_mapping = accounts_host
        self.tab_control_statement = ttk.Frame(self)
        self.tab_unmapped = ttk.Frame(self)
        self.tab_alternatives = self.tab_suggestions
        self.control_alternative_history_actions = None
        self.control_alternative_suggestion_actions = None
        self.control_alternative_mode_widget = None

        suggestions_actions = ttk.Frame(self.tab_suggestions)
        self.control_suggestions_actions = suggestions_actions
        suggestions_actions.pack(fill="x", pady=(0, 4))
        self.btn_control_batch_suggestions = ttk.Button(
            suggestions_actions,
            text="Kjør trygg auto-matching",
            command=self._apply_batch_suggestions_clicked,
        )
        self.btn_control_batch_suggestions.pack(side="right", padx=(6, 0))
        self.btn_control_magic = ttk.Button(
            suggestions_actions,
            text="Tryllestav: finn 0-diff",
            command=self._magic_match_clicked,
        )
        self.btn_control_magic.pack(side="right", padx=(6, 0))
        self.btn_control_best = ttk.Button(
            suggestions_actions,
            text="Bruk trygg kandidat",
            command=self._apply_selected_suggestion,
        )
        self.btn_control_best.pack(side="right")
        for button in (self.btn_control_best, self.btn_control_magic, self.btn_control_batch_suggestions):
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
                "family_pension": ("BG_ZEBRA", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
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
        self.tree_history = self._build_managed_tree_tab(
            self.tab_history,
            _HISTORY_COLUMNS,
            view_id="history",
            height=6,
        )

        control_accounts_panel = self.tab_mapping
        self.control_accounts_panel = control_accounts_panel
        self.btn_control_remove_accounts = None
        self.mapping_filter_bar = None
        self.mapping_filter_widget = None
        self.btn_next_mapping_problem = None
        try:
            self.mapping_filter_var.set("alle")
            self.mapping_filter_label_var.set(_MAPPING_FILTER_LABELS["alle"])
        except Exception:
            pass
        self.tree_control_accounts = self._build_managed_tree_tab(
            control_accounts_panel,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            view_id="control_accounts",
            height=6,
            selectmode="extended",
        )
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
                "family_pension": ("BG_ZEBRA", "TEXT_PRIMARY"),
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
        self.tree_control_statement_accounts = self._build_managed_tree_tab(
            control_statement_accounts_panel,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            view_id="control_statement_accounts",
            height=5,
        )
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
                "family_pension": ("BG_ZEBRA", "TEXT_PRIMARY"),
                "family_unknown": ("BG_DATA", "TEXT_PRIMARY"),
                "family_warning": ("NEG_SOFT", "NEG_TEXT"),
            },
        )

        self.tree_unmapped = self._build_tree_tab(self.tab_unmapped, _UNMAPPED_COLUMNS)
        self.tree_unmapped.configure(height=6)

    def _build_support_notebook(self, support_host: ttk.Frame) -> None:
        """Compatibility wrapper for older callers.

        The visible support area is now a fixed two-pane workspace rather than
        a notebook.
        """
        split = ttk.Panedwindow(support_host, orient="horizontal")
        split.pack(fill="both", expand=True)
        suggestions_host = ttk.LabelFrame(split, text="Forslag", padding=(6, 6))
        accounts_host = ttk.LabelFrame(split, text="Koblinger", padding=(6, 6))
        split.add(suggestions_host, weight=1)
        split.add(accounts_host, weight=1)
        self._build_support_workspace(suggestions_host, accounts_host)

__all__ = ["A07PageSupportLayoutMixin"]
