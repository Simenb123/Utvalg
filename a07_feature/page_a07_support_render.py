from __future__ import annotations

from .page_a07_shared import *  # noqa: F401,F403
from .control_presenter import build_control_panel_state


class A07PageSupportRenderMixin:
    def _refresh_suggestions_tree(self) -> None:
        current_selection = self.tree_control_suggestions.selection()
        selected_id = str(current_selection[0]).strip() if current_selection else ""
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggestions_df = self._ensure_suggestion_display_fields()
        filtered = filter_suggestions_df(
            suggestions_df,
            scope_key="valgt_kode",
            selected_code=selected_code,
            unresolved_code_values=unresolved_codes(self.a07_overview_df),
        )
        self._fill_tree(
            self.tree_control_suggestions,
            filtered,
            _CONTROL_SUGGESTION_COLUMNS,
            row_tag_fn=suggestion_tree_tag,
        )
        tree_suggestions = getattr(self, "tree_suggestions", None)
        if tree_suggestions is not None:
            self._fill_tree(
                tree_suggestions,
                filtered,
                _SUGGESTION_COLUMNS,
                row_tag_fn=suggestion_tree_tag,
            )

        children = self.tree_control_suggestions.get_children()
        if not children:
            self.suggestion_details_var.set("Ingen forslag for valgt kode akkurat naa.")
            self.control_suggestion_summary_var.set(
                build_control_suggestion_summary(selected_code, filtered, None)
            )
            self.control_suggestion_effect_var.set("")
            try:
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                if batch_button is not None:
                    batch_button.state(["disabled"])
            except Exception:
                pass
            if self._selected_control_alternative_mode() == "suggestions":
                self.control_alternative_summary_var.set(str(self.control_suggestion_summary_var.get() or "").strip())
            return

        target = selected_id if selected_id and selected_id in children else children[0]
        self._set_tree_selection(self.tree_control_suggestions, target)
        selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
        self.control_suggestion_summary_var.set(
            build_control_suggestion_summary(selected_code, filtered, selected_row)
        )
        self.control_suggestion_effect_var.set(
            build_control_suggestion_effect_summary(
                selected_code,
                accounts_for_code(self._effective_mapping(), selected_code),
                selected_row,
            )
        )
        try:
            batch_button = getattr(self, "btn_control_batch_suggestions", None)
            if batch_button is not None:
                batch_button.state(["!disabled"])
        except Exception:
            pass
        if self._selected_control_alternative_mode() == "suggestions":
            self.control_alternative_summary_var.set(str(self.control_suggestion_summary_var.get() or "").strip())

    def _refresh_control_support_trees(self) -> None:
        if self._active_support_tab_key() == "control_statement":
            self._set_control_accounts_mode("control_statement")
            self._fill_tree(
                self.tree_control_suggestions,
                pd.DataFrame(columns=[c[0] for c in _CONTROL_SUGGESTION_COLUMNS]),
                _CONTROL_SUGGESTION_COLUMNS,
            )
            self.control_suggestion_summary_var.set(
                "Kontrolloppstillingen bruker kontoklassifisering, ikke A07-forslag."
            )
            self.control_suggestion_effect_var.set("")
            self.suggestion_details_var.set("Velg fanen Forslag for a vurdere forslag for valgt kode.")
            self._update_control_statement_overview()
            self._ensure_control_statement_selection()
            self._refresh_control_statement_details()
            return

        self._set_control_accounts_mode("mapping")
        tree_control_accounts = getattr(self, "tree_control_accounts", None)
        if tree_control_accounts is None:
            self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
            self.control_accounts_summary_var.set(
                build_control_accounts_summary(
                    self.control_selected_accounts_df,
                    self._selected_code_from_tree(self.tree_a07),
                    basis_col=self.workspace.basis_col,
                )
            )
            return
        selected_code = self._selected_code_from_tree(self.tree_a07)
        selected_account = None
        try:
            current_accounts = tree_control_accounts.selection()
            if current_accounts:
                selected_account = str(current_accounts[0]).strip() or None
        except Exception:
            selected_account = None
        self._refresh_suggestions_tree()

        if self.control_gl_df is not None and not self.control_gl_df.empty and selected_code:
            selected_accounts = self.control_gl_df.loc[
                self.control_gl_df["Kode"].astype(str).str.strip() == str(selected_code).strip()
            ].copy()
            if selected_accounts.empty:
                self.control_selected_accounts_df = pd.DataFrame(
                    columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                )
            else:
                self.control_selected_accounts_df = selected_accounts[
                    [c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                ].reset_index(drop=True)
        else:
            self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.control_accounts_summary_var.set(
            build_control_panel_state(
                code=selected_code,
                navn=selected_code,
                status="",
                work_label="",
                why_text="",
                next_action="",
                a07_amount_text="",
                linked_accounts_df=self.control_selected_accounts_df,
                basis_col=self.workspace.basis_col,
            ).linked_accounts_summary
        )
        self._fill_tree(
            tree_control_accounts,
            self.control_selected_accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )
        tree_mapping = getattr(self, "tree_mapping", None)
        if tree_mapping is not None:
            current_mapping = tree_mapping.selection()
            current_mapping_id = str(current_mapping[0]).strip() if current_mapping else ""
            self._fill_tree(tree_mapping, self.mapping_df, _MAPPING_COLUMNS, iid_column="Konto")
            try:
                mapping_children = tree_mapping.get_children()
            except Exception:
                mapping_children = ()
            if current_mapping_id and current_mapping_id in mapping_children:
                self._set_tree_selection(tree_mapping, current_mapping_id)
        children = tree_control_accounts.get_children()
        target_account = (
            selected_account
            or self._selected_control_gl_account()
        )
        if target_account and target_account in children:
            self._set_tree_selection(tree_control_accounts, target_account)

    def _active_support_tab_key(self) -> str | None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return None
        notebook = getattr(self, "control_support_nb", None)
        if notebook is None:
            return None
        try:
            current_tab = notebook.nametowidget(notebook.select())
        except Exception:
            return None
        if current_tab is self.tab_history:
            return "history"
        if current_tab is self.tab_reconcile:
            return "reconcile"
        if current_tab is self.tab_control_statement:
            return "control_statement"
        if current_tab is getattr(self, "tab_groups", None):
            return "groups"
        if current_tab is self.tab_unmapped:
            return "unmapped"
        if current_tab is self.tab_mapping:
            return "mapping"
        if current_tab is getattr(self, "tab_alternatives", None):
            return self._selected_control_alternative_mode()
        return None

    def _render_active_support_tab(self, *, force: bool = False) -> None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        tab_key = self._active_support_tab_key()
        if not tab_key:
            return
        if not force and tab_key in self._loaded_support_tabs:
            return

        def _mark_loaded(current_key: str = tab_key) -> None:
            self._loaded_support_tabs.add(current_key)

        if tab_key == "history":
            self._fill_tree_chunked(
                self.tree_history,
                self.history_compare_df,
                _HISTORY_COLUMNS,
                iid_column="Kode",
                on_complete=lambda: (_mark_loaded(), self._update_history_details_from_selection()),
            )
            return
        if tab_key == "reconcile":
            self._fill_tree_chunked(
                self.tree_reconcile,
                self.reconcile_df,
                _RECONCILE_COLUMNS,
                row_tag_fn=reconcile_tree_tag,
                on_complete=_mark_loaded,
            )
            return
        if tab_key == "control_statement":
            self._fill_tree_chunked(
                self.tree_control_statement,
                self.control_statement_df,
                _CONTROL_STATEMENT_COLUMNS,
                iid_column="Gruppe",
                row_tag_fn=lambda row: control_tree_tag(row.get("Status")),
                on_complete=lambda: (
                    _mark_loaded(),
                    self._ensure_control_statement_selection(),
                    self._refresh_control_statement_details(),
                ),
            )
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
        if tab_key == "groups":
            self._fill_tree(
                self.tree_groups,
                self.groups_df,
                _GROUP_COLUMNS,
                iid_column="GroupId",
            )
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

    def _update_history_details(self, code: str | None) -> None:
        self.history_details_var.set(
            build_mapping_history_details(
                code,
                mapping_current=self._effective_mapping(),
                mapping_previous=self._effective_previous_mapping(),
                previous_year=self.previous_mapping_year,
            )
        )
        if self._selected_control_alternative_mode() == "history":
            self.control_alternative_summary_var.set(str(self.history_details_var.get() or "").strip())

    def _update_history_details_from_selection(self) -> None:
        if bool(getattr(self, "_suspend_selection_sync", False)):
            return

        def _tree_code(tree: ttk.Treeview | None) -> str | None:
            if tree is None:
                return None
            return self._selected_code_from_tree(tree)

        code = (
            _tree_code(getattr(self, "tree_a07", None))
            or _tree_code(getattr(self, "tree_history", None))
            or _tree_code(getattr(self, "tree_control_suggestions", None))
            or _tree_code(getattr(self, "tree_suggestions", None))
            or _tree_code(getattr(self, "tree_reconcile", None))
        )
        self._update_history_details(code)

    def _update_control_panel(self) -> None:
        code = self._selected_code_from_tree(self.tree_a07)
        if not code:
            self.control_intro_var.set("")
            self.control_summary_var.set("Velg A07-kode til hoyre.")
            self.control_meta_var.set("")
            self.control_match_var.set("")
            self.control_mapping_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            self.control_next_var.set("")
            self.control_drag_var.set("")
            self.control_suggestion_effect_var.set("Velg et forslag for aa se hva som blir koblet.")
            try:
                smart_button = getattr(self, "btn_control_smart", None)
                best_button = getattr(self, "btn_control_best", None)
                history_button = getattr(self, "btn_control_history", None)
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                if smart_button is not None:
                    try:
                        smart_button.configure(text="Prov automatisk", command=self._run_selected_control_action)
                    except Exception:
                        pass
                    smart_button.state(["disabled"])
                if best_button is not None:
                    best_button.state(["disabled"])
                if history_button is not None:
                    history_button.state(["disabled"])
                if batch_button is not None:
                    batch_button.state(["disabled"])
                self.lbl_control_drag.configure(style="Muted.TLabel")
            except Exception:
                pass
            sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
            if callable(sync_control_panel_visibility):
                sync_control_panel_visibility()
            self._update_control_transfer_buttons()
            return

        overview_row = None
        if self.a07_overview_df is not None and not self.a07_overview_df.empty:
            matches = self.a07_overview_df.loc[self.a07_overview_df["Kode"].astype(str).str.strip() == code]
            if not matches.empty:
                overview_row = matches.iloc[0]
        control_row = None
        if self.control_df is not None and not self.control_df.empty:
            control_matches = self.control_df.loc[self.control_df["Kode"].astype(str).str.strip() == code]
            if not control_matches.empty:
                control_row = control_matches.iloc[0]
        reconcile_row = None
        if self.reconcile_df is not None and not self.reconcile_df.empty and "Kode" in self.reconcile_df.columns:
            reconcile_matches = self.reconcile_df.loc[self.reconcile_df["Kode"].astype(str).str.strip() == code]
            if not reconcile_matches.empty:
                reconcile_row = reconcile_matches.iloc[0]

        status = str((overview_row.get("Status") if overview_row is not None else "") or "").strip() or "Ukjent"
        navn = str((overview_row.get("Navn") if overview_row is not None else "") or "").strip() or code
        belop = self._format_value(overview_row.get("Belop") if overview_row is not None else None, "Belop")
        current_accounts = accounts_for_code(self._effective_mapping(), code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        ensure_display = getattr(self, "_ensure_suggestion_display_fields", None)
        if callable(ensure_display):
            suggestions_df = ensure_display()
        else:
            suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
            if not isinstance(suggestions_df, pd.DataFrame):
                suggestions_df = _empty_suggestions_df()
        best_row = best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=self._locked_codes(),
        )

        work_label = str((control_row.get("Status") if control_row is not None else "") or "").strip() or status
        next_action = str((control_row.get("NesteHandling") if control_row is not None else "") or "").strip()
        panel_state = build_control_panel_state(
            code=code,
            navn=navn,
            status=status,
            work_label=work_label,
            why_text=(control_row.get("Hvorfor") if control_row is not None else ""),
            next_action=next_action,
            a07_amount_text=belop or "-",
            gl_amount_text=(
                self._format_value(reconcile_row.get("GL_Belop"), "GL_Belop")
                if reconcile_row is not None
                else ""
            ),
            diff_amount_text=(
                self._format_value(reconcile_row.get("Diff"), "Diff")
                if reconcile_row is not None
                else ""
            ),
            linked_accounts_df=self.control_selected_accounts_df,
            basis_col=self.workspace.basis_col,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
            is_locked=bool(code in self._locked_codes()),
        )
        next_action = panel_state.next_action
        self.control_intro_var.set(panel_state.intro_text)
        self.control_meta_var.set(panel_state.meta_text)
        self.control_summary_var.set(panel_state.summary_text)
        self.control_match_var.set(panel_state.match_text)
        self.control_mapping_var.set(panel_state.mapping_text)
        self.control_history_var.set(panel_state.history_text)
        self.control_best_var.set(panel_state.best_text)
        self.control_next_var.set(panel_state.next_text)

        try:
            smart_button = getattr(self, "btn_control_smart", None)
            best_button = getattr(self, "btn_control_best", None)
            history_button = getattr(self, "btn_control_history", None)
            batch_button = getattr(self, "btn_control_batch_suggestions", None)
            if smart_button is not None:
                if panel_state.use_saldobalanse_action:
                    smart_button.configure(
                        text="Apne kontoklassifisering",
                        command=self._open_saldobalanse_for_selected_code_classification,
                    )
                    if code:
                        smart_button.state(["!disabled"])
                    else:
                        smart_button.state(["disabled"])
                else:
                    smart_button.configure(text="Prov automatisk", command=self._run_selected_control_action)
                    if code and code not in self._locked_codes():
                        smart_button.state(["!disabled"])
                    else:
                        smart_button.state(["disabled"])
            if best_button is not None:
                if panel_state.best_suggestion_within_tolerance:
                    best_button.state(["!disabled"])
                else:
                    best_button.state(["disabled"])
            if history_button is not None:
                if panel_state.has_history:
                    history_button.state(["!disabled"])
                else:
                    history_button.state(["disabled"])
            if batch_button is not None:
                if code and code not in self._locked_codes() and panel_state.has_best_suggestion:
                    batch_button.state(["!disabled"])
                else:
                    batch_button.state(["disabled"])
            self.control_drag_var.set("")
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
        if callable(sync_control_panel_visibility):
            sync_control_panel_visibility()
        self._update_control_transfer_buttons()

    def _update_summary(self) -> None:
        client, year = self._session_context(session)
        ctx_parts = [x for x in (client, year) if x]
        context_text = " / ".join(ctx_parts) if ctx_parts else "ingen klientkontekst"

        visible_control_df = filter_control_visible_codes_df(self.control_df)
        unsolved_count = count_pending_control_items(visible_control_df)
        self.summary_var.set(
            " | ".join(
                [
                    context_text,
                    f"Koder {len(self.workspace.a07_df)}",
                    f"Uloste {unsolved_count}",
                    f"Umappede {len(self.unmapped_df)}",
                ]
            )
        )

        if self.a07_path is None:
            if client and year:
                self.a07_path_var.set(
                    f"A07: ingen lagret A07-kilde i {default_a07_source_path(client, year)}"
                )
            else:
                self.a07_path_var.set("A07: ikke valgt")
        else:
            self.a07_path_var.set(f"A07: {self.a07_path}")

        if self.tb_path is None:
            if client and year:
                self.tb_path_var.set("Saldobalanse: ingen aktiv SB-versjon for klient/aar")
            else:
                self.tb_path_var.set("Saldobalanse: klient/aar ikke valgt")
        else:
            self.tb_path_var.set(f"Saldobalanse: aktiv versjon {self.tb_path}")

        if self.mapping_path is None:
            if client and year:
                self.mapping_path_var.set(
                    f"Mapping: ikke lagret enna ({suggest_default_mapping_path(self.a07_path, client=client, year=year)})"
                )
            else:
                self.mapping_path_var.set("Mapping: ikke valgt")
        else:
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")

        if self.rulebook_path is None:
            self.rulebook_path_var.set(f"Rulebook: standard heuristikk ({default_global_rulebook_path()})")
        else:
            self.rulebook_path_var.set(f"Rulebook: {self.rulebook_path}")

        if self.previous_mapping_year is None:
            self.history_path_var.set("Historikk: ingen tidligere A07-mapping funnet")
        elif self.previous_mapping_path is None:
            self.history_path_var.set(
                f"Historikk: bruker profilbasert mapping fra {self.previous_mapping_year}"
            )
        else:
            self.history_path_var.set(
                f"Historikk: bruker prior fra {self.previous_mapping_year} ({self.previous_mapping_path})"
            )

        self.control_bucket_var.set(build_control_bucket_summary(visible_control_df))
        self.details_var.set("Bruk Kilder... for filoversikt.")
