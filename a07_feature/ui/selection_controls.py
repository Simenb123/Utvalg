from __future__ import annotations

from .selection_shared import *  # noqa: F403


class A07PageSelectionControlsMixin:
    def _sync_control_work_level_vars(self, level: str | None) -> str:
        level_s = str(level or "").strip().lower()
        if level_s not in _CONTROL_WORK_LEVEL_LABELS:
            level_s = "a07"
        try:
            self.control_work_level_var.set(level_s)
        except Exception:
            pass
        try:
            self.control_work_level_label_var.set(_CONTROL_WORK_LEVEL_LABELS[level_s])
        except Exception:
            pass
        widget = getattr(self, "control_work_level_widget", None)
        if widget is not None:
            try:
                widget.set(_CONTROL_WORK_LEVEL_LABELS[level_s])
            except Exception:
                pass
        return level_s

    def _selected_control_work_level(self) -> str:
        widget = getattr(self, "control_work_level_widget", None)
        try:
            raw = str(widget.get() or "").strip() if widget is not None else ""
        except Exception:
            raw = ""
        if raw:
            for key, value in _CONTROL_WORK_LEVEL_LABELS.items():
                if raw == value:
                    return key
            if raw in _CONTROL_WORK_LEVEL_LABELS:
                return raw
        try:
            fallback = str(self.control_work_level_var.get() or "").strip().lower()
        except Exception:
            fallback = ""
        return fallback if fallback in _CONTROL_WORK_LEVEL_LABELS else "a07"

    def _selected_rf1022_group(self) -> str | None:
        work_level = self._selected_control_work_level()
        valid_groups: set[str] = set()
        if work_level == "rf1022":
            try:
                valid_groups = {str(value).strip() for value in self.tree_a07.get_children()}
            except Exception:
                valid_groups = set()
            try:
                selection = self.tree_a07.selection()
            except Exception:
                selection = ()
            if selection:
                selected_group = str(selection[0] or "").strip()
                if selected_group and (not valid_groups or selected_group in valid_groups):
                    self._selected_rf1022_group_id = selected_group
                    return selected_group
            try:
                focused_group = str(self.tree_a07.focus() or "").strip()
            except Exception:
                focused_group = ""
            if focused_group and (not valid_groups or focused_group in valid_groups):
                self._selected_rf1022_group_id = focused_group
                return focused_group
        stored_group = str(getattr(self, "_selected_rf1022_group_id", "") or "").strip()
        if work_level == "rf1022" and stored_group and (not valid_groups or stored_group in valid_groups):
            return stored_group
        if work_level != "rf1022":
            return None
        code = str(getattr(getattr(self, "workspace", None), "selected_code", None) or "").strip()
        if not code:
            return None
        control_df = getattr(self, "control_df", None)
        if control_df is None or getattr(control_df, "empty", True):
            return None
        try:
            matches = control_df.loc[control_df["Kode"].astype(str).str.strip() == code]
        except Exception:
            return None
        if matches.empty:
            return None
        group_id = str(matches.iloc[0].get("Rf1022GroupId") or "").strip()
        if group_id:
            self._selected_rf1022_group_id = group_id
        return group_id or None

    def _first_control_code_for_group(self, group_id: str | None) -> str | None:
        group_s = str(group_id or "").strip()
        if not group_s:
            return None
        control_df = getattr(self, "control_df", None)
        if control_df is None or getattr(control_df, "empty", True):
            return None
        try:
            matches = control_df.loc[
                control_df["Rf1022GroupId"].fillna("").astype(str).str.strip() == group_s
            ]
        except Exception:
            return None
        if matches.empty:
            return None
        preferred_code = str(getattr(getattr(self, "workspace", None), "selected_code", None) or "").strip()
        if preferred_code:
            preferred_matches = matches.loc[matches["Kode"].astype(str).str.strip() == preferred_code]
            if not preferred_matches.empty:
                return preferred_code
        try:
            code = str(matches.iloc[0].get("Kode") or "").strip()
        except Exception:
            code = ""
        return code or None

    def _on_control_work_level_changed(self) -> None:
        level = self._sync_control_work_level_vars(self._selected_control_work_level())
        if level == "rf1022":
            group_id = self._selected_rf1022_group() or self._selected_rf1022_group_id
            self._selected_rf1022_group_id = str(group_id or "").strip() or None
        else:
            self.workspace.selected_code = self._selected_control_code()
        invalidate = getattr(self, "_invalidate_control_support", None)
        if callable(invalidate):
            invalidate("work-level", rerender=False)
        elif bool(getattr(self, "_control_details_visible", False)):
            self._support_requested = True
            loaded_tabs = getattr(self, "_loaded_support_tabs", None)
            if isinstance(loaded_tabs, set):
                loaded_tabs.discard("suggestions")
                loaded_tabs.discard("mapping")
        sync_work_level_ui = getattr(self, "_sync_control_work_level_ui", None)
        if callable(sync_work_level_ui):
            sync_work_level_ui()
        sync_tabs = getattr(self, "_sync_support_notebook_tabs", None)
        if callable(sync_tabs):
            sync_tabs()
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._refresh_a07_tree()
        self._on_control_selection_changed()
        self._update_control_transfer_buttons()

    def _update_selected_code_status_message(self) -> None:
        status_var = getattr(self, "status_var", None)
        if status_var is None:
            return
        code = str(self._selected_control_code() or "").strip()
        if not code:
            return
        accounts_df = pd.DataFrame(columns=["Konto", "Navn", "Endring"])
        try:
            if self.control_gl_df is not None and not self.control_gl_df.empty:
                accounts_df = self.control_gl_df.loc[
                    self.control_gl_df["Kode"].astype(str).str.strip() == code
                ].copy()
                if not accounts_df.empty:
                    keep_columns = [column for column in ("Konto", "Navn", "Endring", "IB", "UB") if column in accounts_df.columns]
                    if keep_columns:
                        accounts_df = accounts_df[keep_columns].reset_index(drop=True)
        except Exception:
            accounts_df = pd.DataFrame(columns=["Konto", "Navn", "Endring"])
        try:
            status_var.set(
                build_selected_code_status_message(
                    code=code,
                    accounts_df=accounts_df,
                    basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
                )
            )
        except Exception:
            pass

    def _ensure_suggestion_display_fields(self) -> pd.DataFrame:
        suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
        if not isinstance(suggestions_df, pd.DataFrame) or suggestions_df.empty:
            return _empty_suggestions_df()
        if "ForslagVisning" in suggestions_df.columns:
            return suggestions_df.copy(deep=True)
        gl_df = getattr(getattr(self, "workspace", None), "gl_df", None)
        if not isinstance(gl_df, pd.DataFrame):
            gl_df = _empty_gl_df()
        try:
            decorated = decorate_suggestions_for_display(suggestions_df, gl_df).reset_index(drop=True)
        except Exception:
            decorated = suggestions_df.copy(deep=True).reset_index(drop=True)
        try:
            self.workspace.suggestions = decorated
        except Exception:
            pass
        return decorated.copy(deep=True)

    def _sync_control_alternative_view(self) -> None:
        mode = self._selected_control_alternative_mode()
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        if callable(active_tab_getter):
            try:
                active_tab = active_tab_getter()
            except Exception:
                active_tab = None
            if active_tab in {"suggestions", "history"}:
                mode = active_tab
        try:
            self.control_alternative_mode_var.set(mode)
        except Exception:
            pass
        try:
            self.control_alternative_mode_label_var.set(_CONTROL_ALTERNATIVE_MODE_LABELS.get(mode, _CONTROL_ALTERNATIVE_MODE_LABELS["suggestions"]))
        except Exception:
            pass

        history_var = getattr(self, "history_details_var", None)
        suggestion_var = getattr(self, "control_suggestion_summary_var", None)
        if mode == "history":
            try:
                summary_text = str(history_var.get() or "").strip()
            except Exception:
                summary_text = ""
            if not summary_text:
                summary_text = "Velg en kode for aa se historikk."
        else:
            try:
                summary_text = str(suggestion_var.get() or "").strip()
            except Exception:
                summary_text = ""
            if not summary_text:
                summary_text = "Velg A07-kode til hoyre for aa se beste forslag."
        try:
            self.control_alternative_summary_var.set(summary_text)
        except Exception:
            pass

    def _preferred_support_tab_for_selected_code(self) -> str:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if bool(getattr(self, "_control_details_visible", False)):
            self._support_requested = True
        loaded_tabs = getattr(self, "_loaded_support_tabs", None)
        if isinstance(loaded_tabs, set):
            loaded_tabs.discard("suggestions")
            loaded_tabs.discard("mapping")
        if work_level == "rf1022":
            return "suggestions"
        row = self._selected_control_row()
        guided_status = str((row.get("GuidetStatus") if row is not None else "") or "").strip()
        if guided_status in {"Mistenkelig kobling", "Har forslag"}:
            return "suggestions"
        if guided_status == "Lonnskontroll":
            return "mapping"
        return "mapping"

    def _select_support_tab_key(self, tab_key: str | None, *, force_render: bool = True) -> None:
        key = str(tab_key or "").strip().lower()
        if not key:
            return
        if key in {"reconcile", "control_statement", "unmapped"}:
            key = "mapping"
        elif key == "history":
            key = "suggestions"
        if key == "groups":
            set_advanced_visible = getattr(self, "_set_control_advanced_visible", None)
            if callable(set_advanced_visible):
                set_advanced_visible(True)

        if key in {"suggestions"}:
            try:
                self.control_alternative_mode_var.set(key)
                self.control_alternative_mode_label_var.set(_CONTROL_ALTERNATIVE_MODE_LABELS[key])
            except Exception:
                pass
            widget = getattr(self, "control_alternative_mode_widget", None)
            if widget is not None:
                try:
                    widget.set(_CONTROL_ALTERNATIVE_MODE_LABELS[key])
                except Exception:
                    pass
            sync_alternative_view = getattr(self, "_sync_control_alternative_view", None)
            if callable(sync_alternative_view):
                sync_alternative_view()

        notebook = getattr(self, "control_support_nb", None)
        if notebook is None:
            if key == "groups":
                opener = getattr(self, "_open_groups_popup", None)
                if callable(opener):
                    opener()
                return
            if force_render and bool(getattr(self, "_control_details_visible", False)):
                if bool(getattr(self, "_support_views_ready", False)):
                    schedule_render = getattr(self, "_schedule_active_support_render", None)
                    if callable(schedule_render):
                        schedule_render(force=True)
                    else:
                        self._render_active_support_tab(force=True)
                else:
                    self._schedule_support_refresh()
            focus_target = getattr(
                self,
                "tree_control_suggestions" if key == "suggestions" else "tree_control_accounts",
                None,
            )
            if focus_target is not None:
                try:
                    focus_target.focus_set()
                except Exception:
                    pass
            return

        target = None
        if key == "suggestions":
            target = getattr(self, "tab_suggestions", None)
        elif key == "mapping":
            target = getattr(self, "tab_mapping", None)
        elif key == "groups":
            tree_groups = getattr(self, "tree_groups", None)
            if tree_groups is not None:
                try:
                    tree_groups.focus_set()
                except Exception:
                    pass
            refresh_groups_tree = getattr(self, "_refresh_groups_tree", None)
            if callable(refresh_groups_tree):
                refresh_groups_tree()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return

        if target is None:
            if key in {"mapping"}:
                target = getattr(self, "tab_mapping", None)
        if target is None:
            return
        try:
            notebook.select(target)
        except Exception:
            return

        if not force_render:
            return
        if bool(getattr(self, "_support_views_ready", False)):
            schedule_render = getattr(self, "_schedule_active_support_render", None)
            if callable(schedule_render):
                schedule_render(force=True)
            else:
                self._render_active_support_tab(force=True)
        else:
            self._schedule_support_refresh()

