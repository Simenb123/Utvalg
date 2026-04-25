from __future__ import annotations

from .support_render_shared import *  # noqa: F403


class A07PageSupportTreesMixin:
    def _refresh_control_support_trees(self) -> None:
        active_tab = self._active_support_tab_key()
        work_level = self._selected_control_work_level()
        selected_group = self._selected_rf1022_group()
        selected_code = self._selected_control_code()

        if active_tab == "control_statement":
            self._set_control_accounts_mode("control_statement")
            empty_columns = _CONTROL_COLUMNS if work_level == "rf1022" else _CONTROL_SUGGESTION_COLUMNS
            self._reconfigure_tree_columns(self.tree_control_suggestions, empty_columns)
            self._fill_tree(
                self.tree_control_suggestions,
                pd.DataFrame(columns=[c[0] for c in empty_columns]),
                empty_columns,
            )
            if work_level == "rf1022":
                group_label = rf1022_group_label(selected_group) or "valgt RF-1022-post"
                self.control_suggestion_summary_var.set(
                    f"{group_label} | Kontrolloppstillingen er det styrende kontrollnivaet."
                )
                self.suggestion_details_var.set("")
            else:
                self.control_suggestion_summary_var.set(
                    "Kontrolloppstillingen bygger paa gjeldende klassifisering, ikke A07-forslag."
                )
                self.suggestion_details_var.set("")
            self.control_suggestion_effect_var.set("")
            self._update_control_statement_overview()
            self._refresh_control_statement_details()
            return

        self._set_control_accounts_mode("mapping")
        tree_control_accounts = getattr(self, "tree_control_accounts", None)
        if tree_control_accounts is None:
            self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
            self.control_accounts_summary_var.set(
                self._control_accounts_summary_text(
                    self.control_selected_accounts_df,
                    self._selected_code_from_tree(self.tree_a07),
                )
            )
            self._update_mapping_review_buttons()
            return
        selected_account = None
        try:
            current_accounts = tree_control_accounts.selection()
            if current_accounts:
                selected_account = str(current_accounts[0]).strip() or None
        except Exception:
            selected_account = None
        if active_tab in {"suggestions", "both"}:
            self._refresh_suggestions_tree()

        if work_level == "rf1022":
            accounts_df = build_control_statement_accounts_df(
                self.control_gl_df,
                self.control_statement_df,
                selected_group,
            )
            self.control_selected_accounts_df = self._filter_visible_mapping_accounts_df(accounts_df)
            summary_label = rf1022_group_label(selected_group) or "valgt RF-1022-post"
        else:
            if self.control_gl_df is not None and not self.control_gl_df.empty and selected_code:
                selected_accounts = self.control_gl_df.loc[
                    self.control_gl_df["Kode"].astype(str).str.strip() == str(selected_code).strip()
                ].copy()
                if selected_accounts.empty:
                    self.control_selected_accounts_df = pd.DataFrame(
                        columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                    )
                else:
                    self.control_selected_accounts_df = self._filter_visible_mapping_accounts_df(selected_accounts)
            else:
                self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
            summary_label = selected_code

        self.control_accounts_summary_var.set(
            self._control_accounts_summary_text(
                self.control_selected_accounts_df,
                summary_label,
            )
        )
        self._update_mapping_review_buttons()
        self._fill_tree(
            tree_control_accounts,
            self.control_selected_accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
            row_tag_fn=control_gl_family_tree_tag,
        )
        children = tree_control_accounts.get_children()
        target_account = (
            selected_account
            or self._selected_control_gl_account()
        )
        if work_level != "rf1022" and target_account and target_account in children:
            try:
                self._set_tree_selection(tree_control_accounts, target_account, reveal=False)
            except TypeError:
                self._set_tree_selection(tree_control_accounts, target_account)
        self._update_a07_action_button_state()

    def _refresh_groups_tree(self, *, force: bool = False) -> None:
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is None:
            return
        df = getattr(self, "groups_df", None)
        if df is None:
            signature: tuple[tuple[object, ...], ...] = ()
        elif df.empty:
            signature = ()
        else:
            signature = tuple(
                tuple(str(row.get(column, "") or "") for column, *_rest in _GROUP_COLUMNS)
                for _, row in df.iterrows()
            )
        try:
            children = tuple(tree_groups.get_children())
        except Exception:
            children = ()
        if (
            not force
            and getattr(self, "_groups_tree_signature", None) == signature
            and (children or not signature)
        ):
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return
        try:
            selected = tuple(str(value) for value in tree_groups.selection())
        except Exception:
            selected = ()
        self._groups_tree_signature = signature
        self._fill_tree(
            tree_groups,
            df,
            _GROUP_COLUMNS,
            iid_column="GroupId",
        )
        try:
            new_children = set(str(value) for value in tree_groups.get_children())
            kept = [value for value in selected if value in new_children]
            if kept:
                tree_groups.selection_set(tuple(kept))
        except Exception:
            pass
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()

    def _render_active_support_tab(self, *, force: bool = False) -> None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        tab_key = self._active_support_tab_key()
        if not tab_key:
            return
        self._refresh_groups_tree()
        context_key = self._support_tab_context_key(tab_key)
        loaded_context_keys = getattr(self, "_loaded_support_context_keys", None)
        if not isinstance(loaded_context_keys, dict):
            loaded_context_keys = {}
            self._loaded_support_context_keys = loaded_context_keys
        if (
            not force
            and tab_key in self._loaded_support_tabs
            and loaded_context_keys.get(tab_key) == context_key
        ):
            return

        def _mark_loaded(current_key: str = tab_key) -> None:
            self._loaded_support_tabs.add(current_key)
            self._loaded_support_context_keys[current_key] = self._support_tab_context_key(current_key)

        if tab_key == "history":
            self._fill_tree_chunked(
                self.tree_history,
                self.history_compare_df,
                _HISTORY_COLUMNS,
                iid_column="Kode",
                on_complete=lambda: (_mark_loaded(), self._update_history_details_from_selection()),
            )
            return
        if tab_key == "control_statement":
            _mark_loaded()
            self._refresh_control_statement_details()
            return
        if tab_key == "unmapped":
            self._fill_tree_chunked(
                self.tree_unmapped,
                self.unmapped_df,
                _UNMAPPED_COLUMNS,
                iid_column="Konto",
                on_complete=_mark_loaded,
            )
            return
        if tab_key == "both":
            self._refresh_control_support_trees()
            _mark_loaded()
            return
        if tab_key == "mapping":
            self._refresh_control_support_trees()
            _mark_loaded()
            return
        if tab_key == "suggestions":
            self._refresh_control_support_trees()
            _mark_loaded()
            return
        self._loaded_support_tabs.add(tab_key)

