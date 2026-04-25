from __future__ import annotations

import tkinter as tk

from .control.data import rf1022_group_label


class A07PageCodeAndGroupContextMenuMixin:
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
        selected_codes_getter = getattr(self, "_groupable_selected_control_codes", None)
        try:
            selected_codes = selected_codes_getter() if callable(selected_codes_getter) else []
        except Exception:
            selected_codes = []
        selected_accounts = self._selected_control_gl_accounts()
        has_group_selection = bool(selected_codes)
        has_account_mapping = any(str(self._effective_mapping().get(account) or "").strip() for account in selected_accounts)
        is_locked = code in self._locked_codes()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"

        menu = tk.Menu(self, tearoff=0)
        if work_level == "rf1022":
            group_getter = getattr(self, "_selected_rf1022_group", None)
            try:
                group_id = group_getter() if callable(group_getter) else ""
            except Exception:
                group_id = ""
            group_label = rf1022_group_label(group_id) or str(group_id or "").strip()
            assign_label = "Tildel valgte kontoer hit (RF-1022 ->)"
            if group_label:
                assign_label = f"Tildel valgte kontoer til {group_label} (RF-1022 ->)"
            try:
                target_code = self._resolve_rf1022_target_code(group_id, selected_accounts)
            except Exception:
                target_code = None
            menu.add_command(
                label=assign_label,
                command=lambda accounts=tuple(selected_accounts), group_id=group_id: self._assign_accounts_to_rf1022_group(
                    accounts,
                    group_id,
                    source_label="RF-1022-mapping",
                ),
                state=("normal" if group_id and selected_accounts and target_code else "disabled"),
            )
            menu.add_command(
                label="Fjern mapping fra valgte kontoer (<-)",
                command=lambda accounts=tuple(selected_accounts): self._remove_mapping_accounts_checked(
                    accounts,
                    focus_widget=self.tree_control_gl,
                    refresh="core",
                    source_label="Fjernet kode fra",
                ),
                state=("normal" if has_account_mapping else "disabled"),
            )
            menu.add_separator()
            advanced_menu = tk.Menu(menu, tearoff=0)
            advanced_menu.add_command(
                label="Vis RF-1022-kandidater",
                command=self._run_selected_control_action,
                state=("normal" if group_id else "disabled"),
            )
            menu.add_cascade(label="Avansert", menu=advanced_menu)
            return self._post_context_menu(menu, event)

        menu.add_command(
            label="Tildel valgte kontoer hit (->)",
            command=lambda accounts=tuple(selected_accounts), code=code: self._assign_accounts_to_a07_code(
                accounts,
                code,
                source_label="Mapping",
            ),
            state=("normal" if code and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=lambda accounts=tuple(selected_accounts): self._remove_mapping_accounts_checked(
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            ),
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        advanced_menu = tk.Menu(menu, tearoff=0)
        advanced_menu.add_command(
            label="Smartmapping for valgt kode",
            command=self._run_selected_control_action,
            state=("normal" if code and not is_group else "disabled"),
        )
        advanced_menu.add_command(
            label="Bruk beste forslag",
            command=self._apply_best_suggestion_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        advanced_menu.add_command(
            label="Bruk historikk",
            command=self._apply_history_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_separator()
        group_menu = tk.Menu(menu, tearoff=0)
        group_menu.add_command(
            label="Opprett A07-gruppe fra valgte koder",
            command=self._create_group_from_selection,
            state=("normal" if has_group_selection else "disabled"),
        )
        group_choices_getter = getattr(self, "_a07_group_menu_choices", None)
        try:
            group_choices = group_choices_getter() if callable(group_choices_getter) else []
        except Exception:
            group_choices = []
        if group_choices:
            add_to_group_menu = tk.Menu(group_menu, tearoff=0)
            for group_id, group_label in group_choices:
                add_to_group_menu.add_command(
                    label=group_label,
                    command=lambda target_group_id=group_id: self._add_selected_codes_to_group(target_group_id),
                    state=("normal" if selected_codes else "disabled"),
                )
            group_menu.add_cascade(
                label="Legg til i eksisterende gruppe",
                menu=add_to_group_menu,
                state=("normal" if selected_codes else "disabled"),
            )
        else:
            group_menu.add_command(label="Legg til i eksisterende gruppe", state="disabled")
        group_menu.add_command(
            label="Gi nytt navn til gruppe...",
            command=self._rename_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        group_menu.add_command(
            label="Oppløs gruppe",
            command=self._remove_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_cascade(label="Gruppe", menu=group_menu)
        menu.add_separator()
        advanced_menu.add_command(
            label=("Lås opp kode" if is_locked else "Lås kode"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
            state=("normal" if code else "disabled"),
        )
        menu.add_cascade(label="Avansert", menu=advanced_menu)
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
            command=lambda accounts=tuple(selected_accounts), group_id=group_id: self._assign_accounts_to_a07_code(
                accounts,
                group_id,
                source_label="Mapping",
            ),
            state=("normal" if group_id and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=lambda accounts=tuple(selected_accounts): self._remove_mapping_accounts_checked(
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            ),
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        selected_codes = self._groupable_selected_control_codes()
        menu.add_command(
            label="Legg valgte A07-koder til gruppen",
            command=lambda group_id=group_id: self._add_selected_codes_to_group(group_id),
            state=("normal" if group_id and selected_codes else "disabled"),
        )
        menu.add_command(label="Gi nytt navn til gruppe...", command=self._rename_selected_group)
        menu.add_command(label="Oppløs gruppe", command=self._remove_selected_group)
        menu.add_command(
            label=("Lås opp gruppe" if is_locked else "Lås gruppe"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
        )
        return self._post_context_menu(menu, event)
