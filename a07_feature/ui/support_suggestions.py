from __future__ import annotations

from .support_render_shared import *  # noqa: F403


class A07PageSupportSuggestionsMixin:
    def _refresh_unresolved_rf1022_suggestions(self, group_id: object) -> None:
        codes_df = filter_control_queue_by_rf1022_group(
            filter_control_visible_codes_df(getattr(self, "control_df", None)),
            group_id,
        )
        self.rf1022_candidate_df = pd.DataFrame(columns=[c[0] for c in _RF1022_CANDIDATE_COLUMNS])
        self._reconfigure_tree_columns(self.tree_control_suggestions, _CONTROL_COLUMNS)
        self._fill_tree(
            self.tree_control_suggestions,
            codes_df,
            _CONTROL_COLUMNS,
            iid_column="Kode",
            row_tag_fn=control_family_tree_tag,
        )
        count = int(len(codes_df.index)) if isinstance(codes_df, pd.DataFrame) else 0
        self.control_suggestion_summary_var.set(
            f"Uavklart RF-1022 | {count} A07-koder maa avklares | trygg auto er deaktivert"
        )
        self.control_suggestion_effect_var.set("")
        self.suggestion_details_var.set("")
        for button_name in ("btn_control_best", "btn_control_magic", "btn_control_batch_suggestions"):
            button = getattr(self, button_name, None)
            if button is not None:
                try:
                    if button_name == "btn_control_best":
                        button.configure(text="Bruk trygg kandidat")
                    elif button_name == "btn_control_batch_suggestions":
                        button.configure(text=_batch_auto_button_text_for(self))
                    else:
                        button.configure(text="Tryllestav: finn 0-diff")
                    button.state(["disabled"])
                except Exception:
                    pass

    def _refresh_suggestions_tree(self) -> None:
        work_level = self._selected_control_work_level()
        current_selection = self.tree_control_suggestions.selection()
        selected_id = str(current_selection[0]).strip() if current_selection else ""
        selected_code = self._selected_control_code()
        suggestions_actions = getattr(self, "control_suggestions_actions", None)
        if work_level == "rf1022":
            selected_group = self._selected_rf1022_group()
            if str(selected_group or "").strip() == RF1022_UNKNOWN_GROUP:
                self._refresh_unresolved_rf1022_suggestions(selected_group)
                return
            suggestions_df = self._ensure_suggestion_display_fields()
            filtered = build_rf1022_candidate_df(
                self.control_gl_df,
                suggestions_df,
                selected_group,
                basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            )
            self.rf1022_candidate_df = filtered
            try:
                group_ids = [group_id for group_id, _label in self._rf1022_group_menu_choices()]
                all_candidates = build_rf1022_candidate_df_for_groups(
                    self.control_gl_df,
                    suggestions_df,
                    group_ids,
                    basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
                )
            except Exception:
                all_candidates = filtered
            self.rf1022_all_candidate_df = all_candidates
            if suggestions_actions is not None:
                try:
                    if not bool(suggestions_actions.winfo_manager()):
                        suggestions_actions.pack(fill="x", before=self.tree_control_suggestions.master, padx=0, pady=0)
                except Exception:
                    pass
            count = int(len(filtered.index)) if isinstance(filtered, pd.DataFrame) else 0
            safe_count = 0
            if count and "Forslagsstatus" in filtered.columns:
                safe_count = int((filtered["Forslagsstatus"].astype(str).str.strip() == "Trygt forslag").sum())
            global_safe_count = 0
            if isinstance(all_candidates, pd.DataFrame) and not all_candidates.empty and "Forslagsstatus" in all_candidates.columns:
                global_safe_count = int(
                    (all_candidates["Forslagsstatus"].astype(str).str.strip() == "Trygt forslag").sum()
                )
            action_counts = {"actionable": global_safe_count}
            actionable_count = global_safe_count
            action_counter = getattr(self, "_rf1022_candidate_action_counts", None)
            if callable(action_counter):
                try:
                    action_counts = action_counter(all_candidates)
                    actionable_count = int(action_counts.get("actionable", 0))
                except Exception:
                    action_counts = {"actionable": global_safe_count}
                    actionable_count = global_safe_count
            best_button = getattr(self, "btn_control_best", None)
            if best_button is not None:
                try:
                    best_button.configure(text="Bruk trygg kandidat")
                    best_button.state(["disabled"])
                except Exception:
                    pass
            batch_button = getattr(self, "btn_control_batch_suggestions", None)
            if batch_button is not None:
                try:
                    batch_button.configure(text=_batch_auto_button_text_for(self))
                    batch_button.state(["!disabled"] if actionable_count and _page_safe_auto_matching_is_active(self) else ["disabled"])
                except Exception:
                    pass
            magic_button = getattr(self, "btn_control_magic", None)
            if magic_button is not None:
                try:
                    magic_button.configure(text="Tryllestav: finn 0-diff")
                    magic_button.state(["disabled"])
                except Exception:
                    pass
            self._reconfigure_tree_columns(self.tree_control_suggestions, _RF1022_CANDIDATE_COLUMNS)
            self._fill_tree(
                self.tree_control_suggestions,
                filtered,
                _RF1022_CANDIDATE_COLUMNS,
                iid_column="Konto",
                row_tag_fn=rf1022_candidate_tree_tag,
            )
            group_label = rf1022_group_label(selected_group) or "valgt RF-1022-post"
            if count:
                if safe_count == count:
                    self.control_suggestion_summary_var.set(
                        f"{group_label} | {count} trygge RF-1022-kandidater | {global_safe_count} trygge totalt"
                    )
                else:
                    self.control_suggestion_summary_var.set(
                        f"{group_label} | {count} RF-1022-kandidater, {safe_count} trygge | {global_safe_count} trygge totalt"
                    )
            else:
                self.control_suggestion_summary_var.set(
                    f"{group_label} | Ingen trygge RF-1022-kandidater | {global_safe_count} trygge totalt"
                )
            self.control_suggestion_effect_var.set("")
            self.suggestion_details_var.set("")
            self._update_a07_action_button_state(summary=action_counts)
            return

        if suggestions_actions is not None:
            try:
                if not bool(suggestions_actions.winfo_manager()):
                    suggestions_actions.pack(fill="x", before=self.tree_control_suggestions.master, padx=0, pady=0)
            except Exception:
                pass
        best_button = getattr(self, "btn_control_best", None)
        if best_button is not None:
            try:
                best_button.configure(text="Bruk trygg kandidat")
            except Exception:
                pass
        batch_button = getattr(self, "btn_control_batch_suggestions", None)
        if batch_button is not None:
            try:
                batch_button.configure(text=_batch_auto_button_text_for(self))
            except Exception:
                pass
        magic_button = getattr(self, "btn_control_magic", None)
        if magic_button is not None:
            try:
                magic_button.configure(text="Tryllestav: finn 0-diff")
            except Exception:
                pass
        suggestions_df = self._ensure_suggestion_display_fields()
        filtered = filter_suggestions_df(
            suggestions_df,
            scope_key="valgt_kode",
            selected_code=selected_code,
            unresolved_code_values=unresolved_codes(self.a07_overview_df),
        )
        self._reconfigure_tree_columns(self.tree_control_suggestions, _CONTROL_SUGGESTION_COLUMNS)
        self._fill_tree(
            self.tree_control_suggestions,
            filtered,
            _CONTROL_SUGGESTION_COLUMNS,
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
                for button in (
                    getattr(self, "btn_control_batch_suggestions", None),
                    getattr(self, "btn_control_magic", None),
                ):
                    if button is not None:
                        button.state(["disabled"])
            except Exception:
                pass
            if self._selected_control_alternative_mode() == "suggestions":
                self.control_alternative_summary_var.set(str(self.control_suggestion_summary_var.get() or "").strip())
            self._update_a07_action_button_state()
            return

        target = selected_id if selected_id and selected_id in children else ""
        if target:
            try:
                self._set_tree_selection(self.tree_control_suggestions, target, reveal=False)
            except TypeError:
                self._set_tree_selection(self.tree_control_suggestions, target)
        else:
            try:
                self.tree_control_suggestions.selection_remove(self.tree_control_suggestions.selection())
            except Exception:
                pass
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
                action_counter = getattr(self, "_rf1022_candidate_action_counts", None)
                all_candidate_getter = getattr(self, "_all_rf1022_candidate_df", None)
                actionable_count = 0
                if callable(action_counter) and callable(all_candidate_getter):
                    try:
                        actionable_count = int(action_counter(all_candidate_getter()).get("actionable", 0))
                    except Exception:
                        actionable_count = 0
                batch_button.state(["!disabled"] if actionable_count and _page_safe_auto_matching_is_active(self) else ["disabled"])
        except Exception:
            pass
        try:
            magic_button = getattr(self, "btn_control_magic", None)
            if magic_button is not None:
                unresolved_count = len(unresolved_codes(self.a07_overview_df))
                magic_button.state(
                    ["!disabled"]
                    if unresolved_count and _page_safe_auto_matching_is_active(self)
                    else ["disabled"]
                )
        except Exception:
            pass
        if self._selected_control_alternative_mode() == "suggestions":
            self.control_alternative_summary_var.set(str(self.control_suggestion_summary_var.get() or "").strip())
        self._update_a07_action_button_state()

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
        )
        self._update_history_details(code)

