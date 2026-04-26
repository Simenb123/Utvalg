from __future__ import annotations

from .support_render_shared import *  # noqa: F403


class A07PageSupportGuidanceMixin:
    def _open_guided_support_target(self, target: str, *, code: str | None = None) -> None:
        target_s = str(target or "").strip().lower()
        code_s = str(code or self._selected_control_code() or "").strip()
        work_level = self._selected_control_work_level()
        if not target_s or target_s == "none":
            return
        if target_s == "saldobalanse":
            self._open_saldobalanse_for_selected_code_classification()
            return
        if target_s == "control_statement":
            open_statement = getattr(self, "_open_control_statement_window", None)
            if callable(open_statement):
                open_statement()
            return
        tab_key = {
            "suggestions": "suggestions",
            "history": "suggestions",
            "mapping": "mapping",
        }.get(target_s)
        if not tab_key:
            return
        self._select_support_tab_key(tab_key, force_render=True)
        if tab_key == "suggestions" and work_level == "rf1022":
            try:
                self.tree_control_suggestions.focus_set()
            except Exception:
                pass
        elif tab_key == "suggestions" and code_s:
            self._select_best_suggestion_row_for_code(code_s)
        elif tab_key == "history" and code_s:
            try:
                self._set_tree_selection(self.tree_history, code_s, reveal=True, focus=True)
            except Exception:
                pass
        elif tab_key == "mapping":
            try:
                self.tree_control_accounts.focus_set()
            except Exception:
                pass

    def _update_control_panel(self) -> None:
        restore_drag_hint = getattr(self, "_restore_control_drag_hint", None)
        work_level = self._selected_control_work_level()
        if work_level == "rf1022":
            group_id = self._selected_rf1022_group()
            if not group_id:
                self.control_summary_var.set("Velg RF-1022-post til høyre.")
                self.control_intro_var.set("")
                self.control_meta_var.set("")
                self.control_match_var.set("")
                self.control_mapping_var.set("")
                self.control_history_var.set("")
                self.control_best_var.set("")
                self.control_next_var.set("")
                if callable(restore_drag_hint):
                    restore_drag_hint()
                self.control_suggestion_effect_var.set("")
                try:
                    best_button = getattr(self, "btn_control_best", None)
                    history_button = getattr(self, "btn_control_history", None)
                    magic_button = getattr(self, "btn_control_magic", None)
                    batch_button = getattr(self, "btn_control_batch_suggestions", None)
                    self._set_control_smart_button(visible=False)
                    for button in (best_button, history_button, magic_button, batch_button):
                        if button is not None:
                            button.state(["disabled"])
                except Exception:
                    pass
                sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
                if callable(sync_control_panel_visibility):
                    sync_control_panel_visibility()
                self._update_control_transfer_buttons()
                return

            selected_accounts_df = build_control_statement_accounts_df(
                self.control_gl_df,
                self.control_statement_df,
                group_id,
            )
            self.control_selected_accounts_df = selected_accounts_df
            rf1022_df = getattr(self, "rf1022_overview_df", None)
            overview_row = None
            if isinstance(rf1022_df, pd.DataFrame) and not rf1022_df.empty:
                matches = rf1022_df.loc[rf1022_df["GroupId"].astype(str).str.strip() == str(group_id).strip()]
                if not matches.empty:
                    overview_row = matches.iloc[0]
            group_label = str((overview_row.get("Kontrollgruppe") if overview_row is not None else "") or "").strip()
            group_label = group_label or rf1022_group_label(group_id) or group_id
            post_text = str((overview_row.get("Post") if overview_row is not None else "") or "").strip()
            filtered_codes = filter_control_queue_by_rf1022_group(
                filter_control_visible_codes_df(self.control_df),
                group_id,
            )
            detail_count = int(len(filtered_codes.index)) if isinstance(filtered_codes, pd.DataFrame) else 0
            badges: list[str] = []
            if overview_row is not None:
                gl_text = self._format_value(overview_row.get("GL_Belop"), "GL_Belop")
                a07_text = self._format_value(overview_row.get("A07"), "A07")
                diff_text = self._format_value(overview_row.get("Diff"), "Diff")
                if gl_text:
                    badges.append(f"SB {gl_text}")
                if a07_text:
                    badges.append(f"A07 {a07_text}")
                if diff_text:
                    badges.append(f"Diff {diff_text}")
            if detail_count:
                badges.append(f"A07-detaljer {detail_count}")
            if not selected_accounts_df.empty:
                badges.append(f"Koblinger {len(selected_accounts_df.index)}")

            action_target = "suggestions" if detail_count else "mapping"
            action_label = "Se A07-detaljer" if detail_count else "Kontroller koblinger"
            self.control_summary_var.set(
                f"{group_label}{f' | Post {post_text}' if post_text else ''}"
            )
            self.control_meta_var.set(" | ".join(part for part in badges if part))
            self.control_next_var.set("")
            self.control_intro_var.set("")
            self.control_mapping_var.set("")
            self.control_match_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            if callable(restore_drag_hint):
                restore_drag_hint()
            self.control_suggestion_effect_var.set("")

            try:
                best_button = getattr(self, "btn_control_best", None)
                history_button = getattr(self, "btn_control_history", None)
                magic_button = getattr(self, "btn_control_magic", None)
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                self._set_control_smart_button(
                    text=action_label,
                    command=lambda target=action_target: self._open_guided_support_target(target),
                    enabled=True,
                    visible=(action_target not in {"suggestions", "history", "control_statement"}),
                )
                for button in (best_button, history_button, magic_button):
                    if button is not None:
                        button.state(["disabled"])
            except Exception:
                pass
            sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
            if callable(sync_control_panel_visibility):
                sync_control_panel_visibility()
            self._update_control_transfer_buttons()
            return

        code = self._selected_code_from_tree(self.tree_a07)
        if not code:
            self.control_summary_var.set("Velg A07-kode til høyre.")
            self.control_intro_var.set("")
            self.control_meta_var.set("")
            self.control_match_var.set("")
            self.control_mapping_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            self.control_next_var.set("")
            if callable(restore_drag_hint):
                restore_drag_hint()
            self.control_suggestion_effect_var.set("Velg et forslag for å se hva som blir koblet.")
            try:
                best_button = getattr(self, "btn_control_best", None)
                history_button = getattr(self, "btn_control_history", None)
                magic_button = getattr(self, "btn_control_magic", None)
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                self._set_control_smart_button(visible=False)
                if best_button is not None:
                    best_button.state(["disabled"])
                if history_button is not None:
                    history_button.state(["disabled"])
                if magic_button is not None:
                    magic_button.state(["disabled"])
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
        navn = str((overview_row.get("Navn") if overview_row is not None else "") or "").strip() or code
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
        code_suggestions = suggestions_df.loc[
            suggestions_df.get("Kode", pd.Series("", index=suggestions_df.index)).astype(str).str.strip() == code
        ].copy()

        next_action = str((control_row.get("NesteHandling") if control_row is not None else "") or "").strip()
        panel_state = build_control_panel_state(
            code=code,
            navn=navn,
            guided_status=(control_row.get("GuidetStatus") if control_row is not None else ""),
            guided_next=(control_row.get("GuidetNeste") if control_row is not None else ""),
            why_text=(control_row.get("Hvorfor") if control_row is not None else ""),
            next_action=next_action,
            linked_accounts_df=self.control_selected_accounts_df,
            basis_col=self.workspace.basis_col,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
            matching_ready=bool(not code_suggestions.empty),
            suggestion_count=int(len(code_suggestions.index)),
            current_mapping_suspicious=bool(
                control_row.get("CurrentMappingSuspicious") if control_row is not None else False
            ),
            current_mapping_suspicious_reason=(
                control_row.get("CurrentMappingSuspiciousReason") if control_row is not None else ""
            ),
            is_locked=bool(code in self._locked_codes()),
        )
        next_action = str(panel_state.next_action or "").strip()
        self.control_summary_var.set(panel_state.summary_text)
        self.control_meta_var.set(panel_state.badges_text)
        self.control_next_var.set(panel_state.reason_text)
        self.control_intro_var.set("")
        self.control_mapping_var.set("")
        self.control_match_var.set("")
        self.control_history_var.set("")
        self.control_best_var.set("")
        if callable(restore_drag_hint):
            restore_drag_hint()

        try:
            best_button = getattr(self, "btn_control_best", None)
            history_button = getattr(self, "btn_control_history", None)
            magic_button = getattr(self, "btn_control_magic", None)
            batch_button = getattr(self, "btn_control_batch_suggestions", None)
            action_label = str(panel_state.action_label or "").strip() or "Kontroller kobling"
            action_target = str(panel_state.action_target or "mapping").strip()
            self._set_control_smart_button(
                text=action_label,
                command=lambda target=action_target, code_s=code: self._open_guided_support_target(
                    target,
                    code=code_s,
                ),
                enabled=bool(code and action_target != "none"),
                visible=(action_target not in {"suggestions", "history", "control_statement", "none"}),
            )
            if best_button is not None:
                best_button.configure(text="Bruk trygg kandidat")
            if history_button is not None:
                if panel_state.has_history:
                    history_button.state(["!disabled"])
                else:
                    history_button.state(["disabled"])
            if magic_button is not None:
                magic_button.configure(text="Tryllestav: finn 0-diff")
            if batch_button is not None:
                batch_button.configure(text=_batch_auto_button_text_for(self))
        except Exception:
            pass
        self._update_a07_action_button_state()
        sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
        if callable(sync_control_panel_visibility):
            sync_control_panel_visibility()
        self._update_control_transfer_buttons()

