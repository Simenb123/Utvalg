from __future__ import annotations

from .page_a07_shared import *  # noqa: F401,F403


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
        has_mapped_accounts = any(str(self._effective_mapping().get(account) or "").strip() for account in accounts)
        can_focus_mapped_code = len(accounts) == 1 and has_mapped_accounts
        menu = tk.Menu(self, tearoff=0)
        assign_label = "Tildel til valgt kode (->)"
        if selected_code:
            assign_label = f"Tildel til {selected_code} (->)"
        menu.add_command(
            label=assign_label,
            command=self._assign_selected_control_mapping,
            state=("normal" if accounts and selected_code else "disabled"),
        )
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
        scope_menu.add_command(
            label="Relevante for valgt kode",
            command=lambda: self._set_control_gl_scope("relevante"),
        )
        scope_menu.add_command(
            label="Koblet naa",
            command=lambda: self._set_control_gl_scope("koblede"),
        )
        scope_menu.add_command(
            label="Forslag",
            command=lambda: self._set_control_gl_scope("forslag"),
        )
        scope_menu.add_command(
            label="Alle kontoer",
            command=lambda: self._set_control_gl_scope("alle"),
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

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Tildel valgte kontoer hit (->)",
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
            label="Opplos gruppe",
            command=self._remove_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label=("Las opp kode" if is_locked else "Las kode"),
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
        menu.add_command(label="Opplos gruppe", command=self._remove_selected_group)
        menu.add_command(
            label=("Las opp gruppe" if is_locked else "Las gruppe"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
        )
        return self._post_context_menu(menu, event)
