from __future__ import annotations

from tkinter import ttk

import src.shared.ui.selection_summary as ui_selection_summary
from ..page_a07_constants import _SUMMARY_TOTAL_TAG


class A07PageBindingsMixin:
    def _bind_groups_tree_events(self) -> None:
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is None:
            return
        tree_groups.bind("<<TreeviewSelect>>", lambda _event: self._on_group_selection_changed())
        tree_groups.bind("<Double-1>", lambda _event: self._focus_selected_group_code())
        tree_groups.bind("<Return>", lambda _event: self._focus_selected_group_code())
        tree_groups.bind("<Button-3>", self._show_group_context_menu, add="+")

    def _bind_canonical_events(self) -> None:
        self.tree_control_gl.bind("<<TreeviewSelect>>", lambda _event: self._on_control_gl_selection_changed())
        self.tree_control_gl.bind("<Double-1>", lambda _event: self._run_selected_control_gl_action())
        self.tree_control_gl.bind("<Return>", lambda _event: self._assign_selected_control_mapping())
        self.tree_control_gl.bind("<Delete>", lambda _event: self._clear_selected_control_mapping())
        self.tree_control_gl.bind("<Button-3>", self._show_control_gl_context_menu, add="+")
        self.tree_control_gl.bind("<B1-Motion>", self._start_control_gl_drag, add="+")
        self.tree_control_gl.bind("<ButtonRelease-1>", lambda _event: self._clear_control_drag_state(), add="+")
        self.tree_a07.bind("<<TreeviewSelect>>", lambda _event: self._on_control_selection_changed())
        a07_double_click = getattr(self, "_on_a07_tree_double_click", None)
        if callable(a07_double_click):
            self.tree_a07.bind("<Double-1>", a07_double_click)
        else:
            self.tree_a07.bind("<Double-1>", lambda _event: self._link_selected_control_rows())
        self.tree_a07.bind("<Return>", lambda _event: self._link_selected_control_rows())
        self.tree_a07.bind("<Button-3>", self._show_control_code_context_menu, add="+")
        self.tree_a07.bind("<Motion>", self._track_unmapped_drop_target, add="+")
        self.tree_a07.bind("<Leave>", lambda _event: self._on_control_drop_zone_leave(), add="+")
        self.tree_a07.bind("<ButtonRelease-1>", self._drop_unmapped_on_control, add="+")
        self.tree_history.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_history.bind("<Double-1>", lambda _event: self._apply_selected_history_mapping())
        self.tree_control_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_control_suggestions.bind("<Button-3>", self._show_control_suggestions_context_menu, add="+")
        self.tree_control_accounts.bind("<<TreeviewSelect>>", lambda _event: self._update_a07_action_button_state())
        self.tree_control_accounts.bind("<Double-1>", lambda _event: self._focus_selected_control_account_in_gl())
        self.tree_control_accounts.bind("<Delete>", lambda _event: self._remove_selected_control_accounts())
        self.tree_control_accounts.bind("<Button-3>", self._show_control_accounts_context_menu, add="+")
        self.tree_control_statement_accounts.bind(
            "<<TreeviewSelect>>",
            lambda _event: self._update_a07_action_button_state(),
        )
        self.tree_control_statement_accounts.bind(
            "<Double-1>",
            lambda _event: self._focus_selected_control_statement_account_in_gl(),
        )
        self.tree_control_statement_accounts.bind(
            "<Return>",
            lambda _event: self._focus_selected_control_statement_account_in_gl(),
        )
        self.tree_control_statement_accounts.bind(
            "<Button-3>",
            self._show_control_statement_accounts_context_menu,
            add="+",
        )
        self.tree_unmapped.bind("<B1-Motion>", self._start_unmapped_drag, add="+")
        self.tree_unmapped.bind("<ButtonRelease-1>", lambda _event: self._clear_control_drag_state(), add="+")
        self.tree_unmapped.bind("<Double-1>", lambda _event: self._map_selected_unmapped())
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is not None:
            tree_groups.bind("<<TreeviewSelect>>", lambda _event: self._on_group_selection_changed())
            tree_groups.bind("<Double-1>", lambda _event: self._focus_selected_group_code())
            tree_groups.bind("<Button-3>", self._show_group_context_menu, add="+")

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
            import src.shared.ui.tokens as vt  # type: ignore

            for tag_name, (bg_token, fg_token) in tag_tokens.items():
                tree.tag_configure(
                    tag_name,
                    background=vt.hex_gui(getattr(vt, bg_token)),
                    foreground=vt.hex_gui(getattr(vt, fg_token)),
                )
        except Exception:
            pass

    def _configure_summary_total_tag(self, tree: ttk.Treeview) -> None:
        try:
            import tkinter.font as tkfont

            base_font = tkfont.nametofont("TkDefaultFont")
            total_font = base_font.copy()
            total_font.configure(weight="bold")
            tree.tag_configure(_SUMMARY_TOTAL_TAG, font=total_font)
            fonts = getattr(self, "_tree_tag_fonts", [])
            fonts.append(total_font)
            self._tree_tag_fonts = fonts
        except Exception:
            pass


__all__ = ["A07PageBindingsMixin"]
