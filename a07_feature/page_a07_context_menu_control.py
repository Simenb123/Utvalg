from __future__ import annotations

import tkinter as tk

from .control.data import rf1022_group_label


class A07PageControlContextMenuMixin:
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
            try:
                rf_target_code = self._resolve_rf1022_target_code(selected_group, accounts) if selected_group else None
            except Exception:
                rf_target_code = None
            assign_state = "normal" if accounts and selected_group and rf_target_code else "disabled"
            assign_command = (
                lambda accounts=tuple(accounts), selected_group=selected_group: self._assign_accounts_to_rf1022_group(
                    accounts,
                    selected_group,
                    source_label="RF-1022-mapping",
                )
            )
        elif selected_code:
            assign_label = f"Tildel til {selected_code} (->)"
            assign_command = (
                lambda accounts=tuple(accounts), selected_code=selected_code: self._assign_accounts_to_a07_code(
                    accounts,
                    selected_code,
                    source_label="Mapping",
                )
            )
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
                    try:
                        group_target_code = self._resolve_rf1022_target_code(group_id, accounts)
                    except Exception:
                        group_target_code = None
                    group_menu.add_command(
                        label=group_label,
                        command=lambda group_id=group_id, accounts=tuple(accounts): self._assign_accounts_to_rf1022_group(
                            accounts,
                            group_id,
                            source_label="RF-1022-mapping",
                        ),
                        state=("normal" if accounts and group_target_code else "disabled"),
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
                    command=lambda code=code, accounts=tuple(accounts): self._assign_accounts_to_a07_code(
                        accounts,
                        code,
                        source_label="Mapping",
                    ),
                    state=("normal" if accounts else "disabled"),
                )
            menu.add_cascade(label="Velg A07-kode", menu=code_menu)
        menu.add_command(
            label="Fjern mapping (<-)",
            command=lambda accounts=tuple(accounts): self._remove_mapping_accounts_checked(
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            ),
            state=("normal" if has_mapped_accounts else "disabled"),
        )
        menu.add_command(
            label="Gå til koblet A07-kode",
            command=self._focus_linked_code_for_selected_gl_account,
            state=("normal" if can_focus_mapped_code else "disabled"),
        )
        learning_context_getter = getattr(self, "_selected_control_gl_learning_context", None)
        try:
            learning_context = learning_context_getter() if callable(learning_context_getter) else {}
        except Exception:
            learning_context = {}
        learning_enabled = bool(learning_context.get("enabled")) if isinstance(learning_context, dict) else False
        remove_learning_enabled = bool(learning_context.get("remove_enabled")) if isinstance(learning_context, dict) else False
        code_label = (
            str(learning_context.get("code_label") or "A07-kode").strip()
            if isinstance(learning_context, dict)
            else "A07-kode"
        )
        multi = len(accounts) > 1
        learning_state = "normal" if accounts and learning_enabled else "disabled"
        append_gl_alias = getattr(self, "_append_selected_control_gl_names_to_a07_alias", lambda: None)
        exclude_gl_alias = getattr(self, "_exclude_selected_control_gl_names_from_a07_code", lambda: None)
        remove_gl_alias = getattr(self, "_remove_selected_control_gl_accounts_and_exclude_alias", lambda: None)
        learn_menu = tk.Menu(menu, tearoff=0)
        learn_menu.add_command(
            label=(
                f"Lær valgte kontonavn som alias for {code_label}"
                if multi
                else f"Lær kontonavn som alias for {code_label}"
            ),
            command=append_gl_alias,
            state=learning_state,
        )
        learn_menu.add_command(
            label=(
                f"Ekskluder valgte kontonavn fra {code_label}"
                if multi
                else f"Ekskluder kontonavn fra {code_label}"
            ),
            command=exclude_gl_alias,
            state=learning_state,
        )
        learn_menu.add_separator()
        learn_menu.add_command(
            label=(
                f"Fjern mapping og ekskluder valgte kontonavn fra {code_label}"
                if multi
                else f"Fjern mapping og ekskluder kontonavn fra {code_label}"
            ),
            command=remove_gl_alias,
            state=("normal" if learning_enabled and remove_learning_enabled else "disabled"),
        )
        menu.add_cascade(label="Lær regel", menu=learn_menu)
        menu.add_separator()
        advanced_menu = tk.Menu(menu, tearoff=0)
        if work_level == "rf1022":
            advanced_menu.add_command(
                label="Vis RF-1022-kandidater",
                command=self._run_selected_control_action,
                state=("normal" if selected_group else "disabled"),
            )
        else:
            advanced_menu.add_command(
                label="Smartmapping for valgt kode",
                command=self._run_selected_control_action,
                state=("normal" if selected_code else "disabled"),
            )
            advanced_menu.add_command(
                label="Bruk beste forslag",
                command=self._apply_best_suggestion_for_selected_code,
                state=("normal" if selected_code else "disabled"),
            )
            advanced_menu.add_command(
                label="Bruk historikk",
                command=self._apply_history_for_selected_code,
                state=("normal" if selected_code else "disabled"),
            )
        advanced_menu.add_separator()
        advanced_menu.add_command(
            label="Avansert mapping...",
            command=lambda account=(accounts[0] if accounts else None), code=(selected_code or None): self._open_manual_mapping_clicked(
                initial_account=account,
                initial_code=code,
            ),
            state=("normal" if accounts else "disabled"),
        )
        menu.add_cascade(label="Avansert", menu=advanced_menu)
        return self._post_context_menu(menu, event)

    def _show_control_suggestions_context_menu(self, event: tk.Event) -> str | None:
        event_widget = getattr(event, "widget", None)
        control_tree = getattr(self, "tree_control_suggestions", None)
        tree = event_widget if event_widget is control_tree else control_tree
        if tree is None:
            return None
        iid = self._prepare_tree_context_selection(
            tree,
            event,
            preserve_existing_selection=True,
            on_selected=getattr(self, "_on_suggestion_selected", None),
        )
        if not iid:
            return None

        row = self._selected_suggestion_row_from_tree(tree)
        if row is None:
            return None

        try:
            code = str(row.get("Kode") or "").strip() or str(self._selected_control_code() or "").strip()
        except Exception:
            code = ""
        try:
            accounts = list(self._selected_control_suggestion_accounts())
        except Exception:
            accounts = []

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Bruk forslag",
            command=self._apply_selected_suggestion,
            state="normal",
        )
        menu.add_command(
            label="Vis foreslått konto i saldobalanse"
            if len(accounts) <= 1
            else "Vis første foreslåtte konto i saldobalanse",
            command=lambda account=(accounts[0] if accounts else ""): self._focus_mapping_account(account),
            state=("normal" if accounts else "disabled"),
        )
        menu.add_command(
            label="Gå til A07-kode",
            command=lambda code=code: self._focus_control_code(code),
            state=("normal" if code else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Avansert mapping...",
            command=lambda account=(accounts[0] if accounts else None), code=(code or None): self._open_manual_mapping_clicked(
                initial_account=account,
                initial_code=code,
            ),
            state=("normal" if accounts or code else "disabled"),
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

        account_count = len(accounts)
        multi = account_count > 1
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Vis første i saldobalanse" if multi else "Vis i saldobalanse",
            command=self._focus_selected_control_account_in_gl,
            state=("normal" if accounts else "disabled"),
        )
        menu.add_command(
            label=f"Fjern mapping fra {account_count} valgte" if multi else "Fjern mapping",
            command=lambda accounts=tuple(accounts): self._remove_mapping_accounts_checked(
                accounts,
                focus_widget=tree,
                refresh="all",
                source_label="Fjernet mapping fra",
            ),
            state=("normal" if accounts else "disabled"),
        )
        learning_context_getter = getattr(self, "_selected_control_account_learning_context", None)
        try:
            learning_context = learning_context_getter() if callable(learning_context_getter) else {}
        except Exception:
            learning_context = {}
        learning_enabled = bool(learning_context.get("enabled")) if isinstance(learning_context, dict) else False
        code_label = (
            str(learning_context.get("code_label") or "A07-kode").strip()
            if isinstance(learning_context, dict)
            else "A07-kode"
        )
        learning_state = "normal" if accounts and learning_enabled else "disabled"
        learn_menu = tk.Menu(menu, tearoff=0)
        learn_menu.add_command(
            label=(
                f"Lær valgte kontonavn som alias for {code_label}"
                if multi
                else f"Lær kontonavn som alias for {code_label}"
            ),
            command=self._append_selected_control_account_names_to_a07_alias,
            state=learning_state,
        )
        learn_menu.add_command(
            label=(
                f"Ekskluder valgte kontonavn fra {code_label}"
                if multi
                else f"Ekskluder kontonavn fra {code_label}"
            ),
            command=self._exclude_selected_control_account_names_from_a07_code,
            state=learning_state,
        )
        learn_menu.add_separator()
        learn_menu.add_command(
            label=(
                f"Fjern mapping og ekskluder valgte kontonavn fra {code_label}"
                if multi
                else f"Fjern mapping og ekskluder kontonavn fra {code_label}"
            ),
            command=self._remove_selected_control_accounts_and_exclude_alias,
            state=learning_state,
        )
        menu.add_cascade(
            label="Lær regel",
            menu=learn_menu,
            state=("normal" if accounts else "disabled"),
        )
        advanced_menu = tk.Menu(menu, tearoff=0)
        advanced_menu.add_command(
            label="Avansert mapping...",
            command=lambda account=(accounts[0] if accounts else None): self._open_manual_mapping_clicked(
                initial_account=account,
                initial_code=self._mapped_a07_code_for_account(account) if account else None,
            ),
            state=("normal" if accounts else "disabled"),
        )
        menu.add_cascade(label="Avansert", menu=advanced_menu)
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
            label="Vis i saldobalanse",
            command=self._focus_selected_control_statement_account_in_gl,
            state=("normal" if accounts else "disabled"),
        )
        return self._post_context_menu(menu, event)
