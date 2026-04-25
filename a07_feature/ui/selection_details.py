from __future__ import annotations

from .selection_shared import *  # noqa: F403


class A07PageSelectionDetailsMixin:
    def _update_selected_suggestion_details(self) -> None:
        row = self._selected_suggestion_row()
        if row is None:
            self.suggestion_details_var.set("Velg et forslag for aa se hvorfor det passer og hva som blir koblet.")
            return

        suggested_accounts = str(row.get("ForslagVisning") or row.get("ForslagKontoer") or "").strip()
        explain = str(row.get("Explain") or "").strip()
        hit_tokens = str(row.get("HitTokens") or "").strip()
        history_accounts = str(row.get("HistoryAccountsVisning") or row.get("HistoryAccounts") or "").strip()
        basis = str(row.get("Basis") or "").strip()
        action = str(row.get("ResidualAction") or "").strip()
        group_codes = str(row.get("ResidualGroupCodes") or "").strip()

        parts = []
        if action == "group_review":
            if group_codes:
                parts.append(f"Gruppeforslag: {group_codes}")
            if suggested_accounts:
                parts.append(f"Kontoer som bør vurderes: {suggested_accounts}")
        elif suggested_accounts:
            parts.append(f"Beste kandidat: {suggested_accounts}")
        if basis:
            parts.append(f"Belopstype: {basis}")
        if hit_tokens:
            parts.append(f"Navnetreff: {hit_tokens}")
        if history_accounts:
            parts.append(f"I fjor: {history_accounts}")
        if explain:
            parts.append(f"Begrunnelse: {explain}")

        self.suggestion_details_var.set(" | ".join(parts) if parts else "Ingen detaljforklaring tilgjengelig.")

    def _selected_code_from_tree(self, tree: ttk.Treeview) -> str | None:
        if tree is getattr(self, "tree_a07", None):
            def _is_summary_iid(iid: str) -> bool:
                if str(iid or "").strip() == _CONTROL_A07_TOTAL_IID:
                    return True
                tag_checker = getattr(self, "_tree_item_has_tag", None)
                if callable(tag_checker):
                    try:
                        return bool(tag_checker(tree, iid, _SUMMARY_TOTAL_TAG))
                    except Exception:
                        pass
                try:
                    tags = tree.item(iid, "tags") or ()
                except Exception:
                    tags = ()
                if isinstance(tags, str):
                    return tags == _SUMMARY_TOTAL_TAG
                return _SUMMARY_TOTAL_TAG in {str(tag) for tag in tags}

            selected_work_level = getattr(self, "_selected_control_work_level", None)
            if callable(selected_work_level):
                try:
                    if selected_work_level() != "a07":
                        resolver = getattr(type(self), "_selected_control_code", None)
                        if callable(resolver):
                            return resolver(self)
                except Exception:
                    pass
            value_getter = getattr(self, "_selected_tree_values", None)
            if callable(value_getter):
                values = value_getter(tree)
            else:
                try:
                    selection = tree.selection()
                except Exception:
                    selection = ()
                values = tree.item(selection[0], "values") if selection else ()
            try:
                selection = tree.selection()
            except Exception:
                selection = ()
            if selection:
                selected_iid = str(selection[0] or "").strip()
                if selected_iid:
                    if _is_summary_iid(selected_iid):
                        return None
                    return selected_iid
            try:
                focused_code = str(tree.focus() or "").strip()
            except Exception:
                focused_code = ""
            if focused_code:
                if _is_summary_iid(focused_code):
                    return None
                return focused_code or None
            if values:
                code = str(values[0]).strip()
                if code:
                    return code
        values = self._selected_tree_values(tree)
        if not values:
            return None
        code = str(values[0]).strip()
        return code or None

    def _selected_suggestion_row(self) -> pd.Series | None:
        control_tree = getattr(self, "tree_control_suggestions", None)
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        if callable(active_tab_getter):
            try:
                active_tab = active_tab_getter()
            except Exception:
                active_tab = None
        else:
            active_tab = None
        focused = None
        try:
            focused = self.focus_get()
        except Exception:
            focused = None

        if focused is control_tree:
            row = self._selected_suggestion_row_from_tree(control_tree)
            if row is not None:
                return row
        if active_tab == "suggestions" and control_tree is not None:
            row = self._selected_suggestion_row_from_tree(control_tree)
            if row is not None:
                return row

        row = self._selected_suggestion_row_from_tree(control_tree) if control_tree is not None else None
        if row is not None:
            return row
        return self._best_suggestion_row_for_selected_control_code()

    def _best_suggestion_row_for_selected_control_code(self) -> pd.Series | None:
        code = self._selected_control_code()
        code_s = str(code or "").strip()
        indexes = getattr(self, "_a07_refresh_indexes", {})
        if code_s and isinstance(indexes, dict):
            best_lookup = indexes.get("best_suggestion_by_code")
            if isinstance(best_lookup, dict):
                cached = best_lookup.get(code_s)
                if cached is not None:
                    return cached
        ensure_display = getattr(self, "_ensure_suggestion_display_fields", None)
        if callable(ensure_display):
            suggestions_df = ensure_display()
        else:
            suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
            if not isinstance(suggestions_df, pd.DataFrame):
                suggestions_df = _empty_suggestions_df()
        return best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=self._locked_codes(),
        )

    def _select_best_suggestion_row_for_code(self, code: str | None = None) -> pd.Series | None:
        code_s = str(code or self._selected_control_code() or "").strip()
        if not code_s:
            return None
        if code is None:
            best_row = self._best_suggestion_row_for_selected_control_code()
        else:
            indexes = getattr(self, "_a07_refresh_indexes", {})
            best_lookup = indexes.get("best_suggestion_by_code") if isinstance(indexes, dict) else None
            best_row = best_lookup.get(code_s) if isinstance(best_lookup, dict) else None
            if best_row is None:
                best_row = best_suggestion_row_for_code(
                    self._ensure_suggestion_display_fields(),
                    code_s,
                    locked_codes=self._locked_codes(),
                )
        if best_row is None:
            return None
        tree = getattr(self, "tree_control_suggestions", None)
        if tree is not None:
            try:
                iid = str(best_row.name).strip()
            except Exception:
                iid = ""
            if iid:
                try:
                    self._set_tree_selection(tree, iid, reveal=True, focus=True)
                except Exception:
                    pass
        return best_row

    def _selected_control_gl_account(self) -> str | None:
        values = self._selected_tree_values(self.tree_control_gl)
        if not values:
            return None
        konto = str(values[0]).strip()
        return konto or None

    def _selected_control_gl_accounts(self) -> list[str]:
        try:
            selection = self.tree_control_gl.selection()
        except Exception:
            selection = ()

        accounts: list[str] = []
        seen: set[str] = set()
        for iid in selection:
            konto = str(iid).strip()
            if not konto or konto in seen:
                continue
            accounts.append(konto)
            seen.add(konto)
        return accounts

    def _selected_control_suggestion_accounts(self) -> list[str]:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    return []
            except Exception:
                pass
        row = self._selected_suggestion_row()
        if row is None:
            return []
        return _parse_konto_tokens(row.get("ForslagKontoer"))

    def _set_control_details_visible(self, visible: bool) -> None:
        self._control_details_visible = bool(visible)
        self._support_requested = self._control_details_visible
        self._diag(f"set_control_details_visible visible={self._control_details_visible}")
        support_nb = getattr(self, "control_support_nb", None)
        if support_nb is not None and self._control_details_visible:
            try:
                support_nb.update_idletasks()
            except Exception:
                pass
        if self._control_details_visible:
            try:
                if self._support_views_ready:
                    schedule_render = getattr(self, "_schedule_active_support_render", None)
                    if callable(schedule_render):
                        self.after_idle(lambda: schedule_render(force=True))
                    else:
                        self.after_idle(lambda: self._refresh_control_support_trees())
                        self.after_idle(lambda: self._render_active_support_tab(force=True))
                else:
                    self._schedule_support_refresh()
            except Exception:
                pass

    def _sync_control_work_level_ui(self) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        view_widget = getattr(self, "a07_filter_widget", None)
        if view_widget is not None:
            try:
                view_widget.configure(state=("disabled" if work_level == "rf1022" else "readonly"))
            except Exception:
                pass
        view_label = getattr(self, "lbl_control_view_caption", None)
        if view_label is not None:
            try:
                view_label.configure(style=("Muted.TLabel" if work_level == "rf1022" else "TLabel"))
            except Exception:
                pass
        sync_gl_scope = getattr(self, "_sync_control_gl_scope_widget", None)
        if callable(sync_gl_scope):
            sync_gl_scope()

    def _set_control_advanced_visible(self, visible: bool) -> None:
        self._control_advanced_visible = bool(visible)
        button = getattr(self, "btn_control_toggle_advanced", None)
        if button is not None:
            try:
                button.configure(text="Skjul avansert" if self._control_advanced_visible else "Vis avansert")
            except Exception:
                pass
        sync_tabs = getattr(self, "_sync_support_notebook_tabs", None)
        if callable(sync_tabs):
            sync_tabs()
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()

    def _toggle_control_advanced(self) -> None:
        self._set_control_advanced_visible(not bool(getattr(self, "_control_advanced_visible", False)))

    def _sync_support_notebook_tabs(self) -> None:
        notebook = getattr(self, "control_support_nb", None)
        if notebook is None:
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        work_level = "a07"
        if callable(selected_work_level):
            try:
                work_level = selected_work_level()
            except Exception:
                work_level = "a07"
        try:
            notebook.tab(getattr(self, "tab_suggestions", None), text="Forslag")
            notebook.tab(getattr(self, "tab_mapping", None), text="Koblinger")
        except Exception:
            pass
        active_tab = None
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        if callable(active_tab_getter):
            try:
                active_tab = active_tab_getter()
            except Exception:
                active_tab = None
        if active_tab not in {"suggestions", "mapping"}:
            try:
                notebook.select(getattr(self, "tab_suggestions", None))
            except Exception:
                pass

    def _update_control_transfer_buttons(self) -> None:
        assign_button = getattr(self, "btn_control_assign", None)
        clear_button = getattr(self, "btn_control_clear", None)
        if assign_button is None and clear_button is None:
            return

        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        accounts = self._selected_control_gl_accounts()
        code = self._selected_control_code()
        selected_group_getter = getattr(self, "_selected_rf1022_group", None)
        try:
            selected_group = selected_group_getter() if callable(selected_group_getter) else ""
        except Exception:
            selected_group = ""
        effective_mapping = self._effective_mapping()
        has_mapped_account = any(str(effective_mapping.get(account) or "").strip() for account in accounts)

        try:
            if assign_button is not None:
                can_assign = (work_level == "a07" and bool(accounts and code)) or (
                    work_level == "rf1022" and bool(accounts and selected_group)
                )
                if can_assign:
                    assign_button.state(["!disabled"])
                else:
                    assign_button.state(["disabled"])
            if clear_button is not None:
                if has_mapped_account:
                    clear_button.state(["!disabled"])
                else:
                    clear_button.state(["disabled"])
        except Exception:
            return

