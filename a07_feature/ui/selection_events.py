from __future__ import annotations

from .selection_shared import *  # noqa: F403
from .selection_controls import A07PageSelectionControlsMixin


class A07PageSelectionEventsMixin:
    def _on_control_selection_changed(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)) or (
            callable(suppressed_check) and suppressed_check(getattr(self, "tree_a07", None))
        ):
            return
        diag = getattr(self, "_diag", None)
        if callable(diag):
            diag(
                f"control_selection_changed code={self._selected_control_code()!r} "
                f"refresh_in_progress={getattr(self, '_refresh_in_progress', False)} "
                f"details_visible={getattr(self, '_control_details_visible', False)}"
            )
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            selected_group = self._selected_rf1022_group()
            self._selected_rf1022_group_id = str(selected_group or "").strip() or None
            self.workspace.selected_code = self._selected_control_code()
            invalidate = getattr(self, "_invalidate_control_support", None)
            if callable(invalidate):
                invalidate("rf-selection", rerender=False)
            self._update_history_details_from_selection()
            try:
                A07PageSelectionControlsMixin._update_selected_code_status_message(self)
            except Exception:
                pass
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            if bool(getattr(self, "_refresh_in_progress", False)):
                return
            schedule_followup = getattr(self, "_schedule_control_selection_followup", None)
            if callable(schedule_followup):
                schedule_followup()
            elif bool(getattr(self, "_control_details_visible", False)):
                self._refresh_control_support_trees()
            return
        if bool(getattr(self, "_skip_initial_control_followup", False)):
            self.workspace.selected_code = self._selected_control_code()
            self._update_history_details_from_selection()
            try:
                A07PageSelectionControlsMixin._update_selected_code_status_message(self)
            except Exception:
                pass
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return
        self.workspace.selected_code = self._selected_control_code()
        invalidate = getattr(self, "_invalidate_control_support", None)
        if callable(invalidate):
            invalidate("a07-selection", rerender=False)
        self._update_history_details_from_selection()
        try:
            A07PageSelectionControlsMixin._update_selected_code_status_message(self)
        except Exception:
            pass
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return
        schedule_followup = getattr(self, "_schedule_control_selection_followup", None)
        if callable(schedule_followup):
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            schedule_followup()
            return
        if bool(getattr(self, "_control_details_visible", False)):
            self._refresh_control_support_trees()
        self._update_control_panel()
        self._update_control_transfer_buttons()
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()

    def _on_support_tab_changed(self) -> None:
        self._diag(
            f"support_tab_changed details_visible={getattr(self, '_control_details_visible', False)} "
            f"ready={self._support_views_ready} active={self._active_support_tab_key()!r}"
        )
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        self._support_requested = True
        if self._active_support_tab_key() == "control_statement":
            schedule_render = getattr(self, "_schedule_active_support_render", None)
            if callable(schedule_render):
                schedule_render(force=True)
            else:
                self._render_active_support_tab(force=True)
            return
        if self._active_support_tab_key() == "history" and not bool(getattr(self, "_history_compare_ready", False)):
            self._schedule_support_refresh()
            return
        if self._support_views_ready:
            schedule_render = getattr(self, "_schedule_active_support_render", None)
            if callable(schedule_render):
                schedule_render(force=False)
            else:
                self._render_active_support_tab()
            return
        self._schedule_support_refresh()

    def _on_control_alternative_mode_changed(self) -> None:
        try:
            self.control_alternative_mode_var.set(self._selected_control_alternative_mode())
        except Exception:
            pass
        sync_alternative_view = getattr(self, "_sync_control_alternative_view", None)
        if callable(sync_alternative_view):
            sync_alternative_view()
        self._support_requested = True
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        if bool(getattr(self, "_support_views_ready", False)):
            schedule_render = getattr(self, "_schedule_active_support_render", None)
            if callable(schedule_render):
                schedule_render(force=True)
            else:
                self._render_active_support_tab(force=True)
            return
        self._schedule_support_refresh()

    def _on_control_gl_selection_changed(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)) or (
            callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_gl", None))
        ):
            self._update_control_transfer_buttons()
            return
        selected_accounts_getter = getattr(self, "_selected_control_gl_accounts", None)
        if callable(selected_accounts_getter):
            selected_accounts = selected_accounts_getter()
        else:
            selected_accounts = []
        account = self._selected_control_gl_account()
        if not account or self.control_gl_df is None or self.control_gl_df.empty:
            self._update_control_transfer_buttons()
            return
        if not selected_accounts:
            selected_accounts = [account]
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._sync_control_account_selection(account)
            self._update_control_transfer_buttons()
            return
        matches = self.control_gl_df.loc[self.control_gl_df["Konto"].astype(str).str.strip() == account]
        if matches.empty:
            self._sync_control_account_selection(account)
            self._update_control_transfer_buttons()
            return
        code = str(matches.iloc[0].get("Kode") or "").strip()
        self._sync_control_account_selection(account)
        self._update_control_transfer_buttons()

        status_var = getattr(self, "status_var", None)
        if status_var is None:
            return
        try:
            amount_summary = build_gl_selection_amount_summary(
                control_gl_df=self.control_gl_df,
                selected_accounts=selected_accounts,
            )
            if amount_summary:
                status_var.set(amount_summary)
                return
            status_message = build_gl_selection_status_message(
                control_gl_df=self.control_gl_df,
                account=account,
                selected_accounts=selected_accounts,
            )
            if status_message:
                status_var.set(status_message)
        except Exception:
            pass

    def _on_suggestion_scope_changed(self) -> None:
        self.suggestion_scope_var.set(self._selected_suggestion_scope())
        self._refresh_suggestions_tree()
        self._update_selected_suggestion_details()

    def _on_suggestion_selected(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)):
            return
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_suggestions", None)):
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            row = None
            try:
                row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
            except Exception:
                row = None
            update_buttons = getattr(self, "_update_a07_action_button_state", None)
            if callable(update_buttons):
                update_buttons()
            else:
                can_apply = False
                if row is not None:
                    plan_builder = getattr(self, "_build_global_auto_mapping_plan", None)
                    if callable(plan_builder):
                        try:
                            plan = plan_builder(pd.DataFrame([dict(row)]))
                            if plan is not None and not plan.empty and "Action" in plan.columns:
                                can_apply = bool(
                                    (plan["Action"].fillna("").astype(str).str.strip() == "apply").any()
                                )
                        except Exception:
                            can_apply = False
                    else:
                        can_apply = str(row.get("Forslagsstatus") or "").strip() == "Trygt forslag"
                best_button = getattr(self, "btn_control_best", None)
                if best_button is not None:
                    try:
                        best_button.state(["!disabled"] if can_apply else ["disabled"])
                    except Exception:
                        pass
            if row is not None:
                try:
                    self.suggestion_details_var.set(
                        f"Kandidat: {row.get('Konto')} -> {row.get('Kode')} | {row.get('Matchgrunnlag')} | {row.get('Belopsgrunnlag')}"
                    )
                except Exception:
                    pass
            try:
                self.control_suggestion_effect_var.set("")
            except Exception:
                pass
            return
        self._update_selected_suggestion_details()
        if not self._retag_control_gl_tree():
            self._schedule_control_gl_refresh()
        if getattr(self, "tree_control_suggestions", None) is not None:
            selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
            row_code = ""
            if selected_row is not None:
                try:
                    row_code = str(selected_row.get("Kode") or "").strip()
                except Exception:
                    row_code = ""
            selected_code = row_code or self._selected_code_from_tree(self.tree_a07)
            suggestions_df = self._ensure_suggestion_display_fields()
            suggestions_df = filter_suggestions_df(
                suggestions_df,
                scope_key="valgt_kode",
                selected_code=selected_code,
                unresolved_code_values=unresolved_codes(self.a07_overview_df),
            )
            self.control_suggestion_summary_var.set(
                build_control_suggestion_summary(selected_code, suggestions_df, selected_row)
            )
            self.control_suggestion_effect_var.set(
                build_control_suggestion_effect_summary(
                    selected_code,
                    accounts_for_code(self._effective_mapping(), selected_code),
                    selected_row,
                )
            )
            highlight_context_accounts = getattr(self, "_highlight_selected_code_context_accounts", None)
            if callable(highlight_context_accounts):
                highlight_context_accounts(
                    code=selected_code,
                    tab_key="suggestions",
                    best_row=selected_row,
                    current_accounts=accounts_for_code(self._effective_mapping(), selected_code),
                    history_accounts=safe_previous_accounts_for_code(
                        selected_code,
                        mapping_current=self._effective_mapping(),
                        mapping_previous=self._effective_previous_mapping(),
                        gl_df=self.workspace.gl_df,
                    ),
                )
        self._update_history_details_from_selection()
        update_buttons = getattr(self, "_update_a07_action_button_state", None)
        if callable(update_buttons):
            update_buttons()

    def _on_a07_filter_changed(self) -> None:
        self.a07_filter_var.set(self._selected_a07_filter())
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)

    def _select_primary_tab(self) -> None:
        """No-op: arbeidsflaten bruker ikke interne tabs som kan byttes."""
        pass

