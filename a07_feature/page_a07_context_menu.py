from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .control.data import rf1022_group_label
from .page_a07_constants import (
    _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL,
    _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL,
)


class A07PageContextMenuMixin:
    def _prepare_tree_context_selection(
        self,
        tree: ttk.Treeview,
        event: tk.Event | None = None,
        *,
        preserve_existing_selection: bool = True,
        on_selected: Callable[[], None] | None = None,
    ) -> str | None:
        iid = self._tree_iid_from_event(tree, event)
        if not iid:
            return None

        try:
            current_selection = tuple(str(value).strip() for value in tree.selection())
        except Exception:
            current_selection = ()
        already_selected = iid in current_selection

        try:
            if preserve_existing_selection and already_selected:
                tree.focus(iid)
                tree.see(iid)
            else:
                self._set_tree_selection(tree, iid)
        except Exception:
            return None

        try:
            tree.focus_set()
        except Exception:
            pass

        if callable(on_selected):
            try:
                on_selected()
            except Exception:
                pass
        return iid

    def _post_context_menu(self, menu: tk.Menu, event: tk.Event) -> str:
        self._active_context_menu = menu
        try:
            menu.tk_popup(int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0)))
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    def _show_control_gl_context_menu(self, event: tk.Event) -> str | None:
        iid = self._prepare_tree_context_selection(
            self.tree_control_gl,
            event,
            preserve_existing_selection=True,
        )
        if not iid:
            return None

        accounts = self._selected_control_gl_accounts()
        selected_code = str(self._selected_control_code() or "").strip()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        selected_group_getter = getattr(self, "_selected_rf1022_group", None)
        try:
            selected_group = selected_group_getter() if callable(selected_group_getter) else ""
        except Exception:
            selected_group = ""
        has_mapped_accounts = any(str(self._effective_mapping().get(account) or "").strip() for account in accounts)
        can_focus_mapped_code = len(accounts) == 1 and has_mapped_accounts
        menu = tk.Menu(self, tearoff=0)
        assign_label = "Tildel til valgt kode (->)"
        assign_state = "normal" if accounts and selected_code else "disabled"
        assign_command = self._assign_selected_control_mapping
        if work_level == "rf1022":
            assign_label = "Tildel til valgt RF-1022-post (->)"
            if selected_group:
                assign_label = f"Tildel til {rf1022_group_label(selected_group) or selected_group} (->)"
            assign_state = "normal" if accounts and selected_group else "disabled"
        elif selected_code:
            assign_label = f"Tildel til {selected_code} (->)"
        menu.add_command(
            label=assign_label,
            command=assign_command,
            state=assign_state,
        )
        if work_level == "rf1022":
            group_choices_getter = getattr(self, "_rf1022_group_menu_choices", None)
            try:
                group_choices = group_choices_getter() if callable(group_choices_getter) else []
            except Exception:
                group_choices = []
            if group_choices:
                group_menu = tk.Menu(menu, tearoff=0)
                for group_id, group_label in group_choices:
                    group_menu.add_command(
                        label=group_label,
                        command=lambda group_id=group_id: self._assign_selected_accounts_to_rf1022_group(group_id),
                        state=("normal" if accounts else "disabled"),
                    )
                menu.add_cascade(label="Velg RF-1022-post", menu=group_menu)
        code_choices_getter = getattr(self, "_a07_code_menu_choices", None)
        try:
            code_choices = code_choices_getter() if callable(code_choices_getter) else []
        except Exception:
            code_choices = []
        if code_choices:
            code_menu = tk.Menu(menu, tearoff=0)
            for code, code_label in code_choices:
                code_menu.add_command(
                    label=code_label,
                    command=lambda code=code: self._assign_selected_accounts_to_a07_code(code),
                    state=("normal" if accounts else "disabled"),
                )
            menu.add_cascade(label="Velg A07-kode", menu=code_menu)
        menu.add_command(
            label="Fjern mapping (<-)",
            command=self._clear_selected_control_mapping,
            state=("normal" if has_mapped_accounts else "disabled"),
        )
        menu.add_command(
            label="Ga til koblet A07-kode",
            command=self._focus_linked_code_for_selected_gl_account,
            state=("normal" if can_focus_mapped_code else "disabled"),
        )
        scope_menu = tk.Menu(menu, tearoff=0)
        scope_keys = _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL.get(work_level, _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL["rf1022"])
        scope_labels = _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL.get(work_level, _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL["rf1022"])
        for scope_key in scope_keys:
            scope_menu.add_command(
                label=scope_labels.get(scope_key, scope_key),
                command=lambda scope_key=scope_key: self._set_control_gl_scope(scope_key),
            )
        menu.add_separator()
        menu.add_cascade(label="Vis i venstre liste", menu=scope_menu)
        menu.add_separator()
        menu.add_command(
            label="Smartmapping for valgt kode",
            command=self._run_selected_control_action,
            state=("normal" if selected_code else "disabled"),
        )
        menu.add_command(
            label="Bruk beste forslag",
            command=self._apply_best_suggestion_for_selected_code,
            state=("normal" if selected_code else "disabled"),
        )
        menu.add_command(
            label="Bruk historikk",
            command=self._apply_history_for_selected_code,
            state=("normal" if selected_code else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Avansert mapping...",
            command=self._open_manual_mapping_clicked,
            state=("normal" if accounts else "disabled"),
        )
        return self._post_context_menu(menu, event)

    def _show_control_accounts_context_menu(self, event: tk.Event) -> str | None:
        tree = getattr(self, "tree_control_accounts", None)
        if tree is None:
            return None
        iid = self._prepare_tree_context_selection(tree, event, preserve_existing_selection=True)
        if not iid:
            return None
        accounts_getter = getattr(self, "_selected_control_account_ids", None)
        try:
            accounts = accounts_getter() if callable(accounts_getter) else []
        except Exception:
            accounts = []

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Vis i GL",
            command=self._focus_selected_control_account_in_gl,
            state=("normal" if accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern valgt",
            command=self._remove_selected_control_accounts,
            state=("normal" if accounts else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Avansert mapping...",
            command=self._open_manual_mapping_clicked,
            state=("normal" if accounts else "disabled"),
        )
        return self._post_context_menu(menu, event)

    def _show_control_statement_accounts_context_menu(self, event: tk.Event) -> str | None:
        tree = getattr(self, "tree_control_statement_accounts", None)
        if tree is None:
            return None
        iid = self._prepare_tree_context_selection(tree, event, preserve_existing_selection=True)
        if not iid:
            return None
        accounts_getter = getattr(self, "_selected_control_statement_account_ids", None)
        try:
            accounts = accounts_getter() if callable(accounts_getter) else []
        except Exception:
            accounts = []

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Vis i GL",
            command=self._focus_selected_control_statement_account_in_gl,
            state=("normal" if accounts else "disabled"),
        )
        return self._post_context_menu(menu, event)

    def _show_control_code_context_menu(self, event: tk.Event) -> str | None:
        iid = self._prepare_tree_context_selection(
            self.tree_a07,
            event,
            preserve_existing_selection=True,
            on_selected=self._on_control_selection_changed,
        )
        if not iid:
            return None

        code = str(self._selected_control_code() or "").strip()
        is_group = code.startswith("A07_GROUP:")
        selected_codes = self._groupable_selected_control_codes()
        selected_accounts = self._selected_control_gl_accounts()
        has_group_selection = len(selected_codes) >= 2
        has_account_mapping = any(str(self._effective_mapping().get(account) or "").strip() for account in selected_accounts)
        is_locked = code in self._locked_codes()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=("Tildel valgte kontoer hit (RF-1022 ->)" if work_level == "rf1022" else "Tildel valgte kontoer hit (->)"),
            command=self._assign_selected_control_mapping,
            state=("normal" if code and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=self._clear_selected_control_mapping,
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Smartmapping for valgt kode",
            command=self._run_selected_control_action,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_command(
            label="Bruk beste forslag",
            command=self._apply_best_suggestion_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_command(
            label="Bruk historikk",
            command=self._apply_history_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Opprett gruppe fra valgte koder",
            command=self._create_group_from_selection,
            state=("normal" if has_group_selection else "disabled"),
        )
        menu.add_command(
            label="Gi nytt navn til gruppe...",
            command=self._rename_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_command(
            label="Oppløs gruppe",
            command=self._remove_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label=("Lås opp kode" if is_locked else "Lås kode"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
            state=("normal" if code else "disabled"),
        )
        return self._post_context_menu(menu, event)

    def _show_group_context_menu(self, event: tk.Event) -> str | None:
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is None:
            return None
        iid = self._prepare_tree_context_selection(
            tree_groups,
            event,
            preserve_existing_selection=False,
            on_selected=self._on_group_selection_changed,
        )
        if not iid:
            return None

        group_id = str(self._selected_group_id() or "").strip()
        selected_accounts = self._selected_control_gl_accounts()
        has_account_mapping = any(str(self._effective_mapping().get(account) or "").strip() for account in selected_accounts)
        is_locked = group_id in self._locked_codes()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Tildel valgte kontoer hit (->)",
            command=self._assign_selected_control_mapping,
            state=("normal" if group_id and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=self._clear_selected_control_mapping,
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        menu.add_command(label="Gi nytt navn til gruppe...", command=self._rename_selected_group)
        menu.add_command(label="Oppløs gruppe", command=self._remove_selected_group)
        menu.add_command(
            label=("Lås opp gruppe" if is_locked else "Lås gruppe"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
        )
        return self._post_context_menu(menu, event)
