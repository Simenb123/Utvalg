from __future__ import annotations

import pandas as pd
from tkinter import ttk

from ..control import status as a07_control_status
from ..control.data import (
    a07_suggestion_is_strict_auto,
    build_control_accounts_summary,
    build_rf1022_candidate_df,
    build_rf1022_candidate_df_for_groups,
    build_control_statement_accounts_df,
    build_mapping_history_details,
    filter_control_queue_by_rf1022_group,
    filter_control_visible_codes_df,
    filter_suggestions_df,
    filter_suggestions_for_rf1022_group,
    control_family_tree_tag,
    control_gl_family_tree_tag,
    rf1022_group_label,
    rf1022_candidate_tree_tag,
    suggestion_tree_tag,
    unresolved_codes,
)
from ..control.matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_control_suggestion_effect_summary,
    build_control_suggestion_summary,
    safe_previous_accounts_for_code,
)
from ..control.presenter import build_control_panel_state
from ..page_a07_constants import (
    _CONTROL_COLUMNS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_SUGGESTION_COLUMNS,
    _RF1022_CANDIDATE_COLUMNS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_COLUMNS,
    _UNMAPPED_COLUMNS,
    _SUGGESTION_COLUMNS,
)
from ..page_a07_env import session
from ..page_a07_frames import _empty_suggestions_df
from ..page_a07_runtime_helpers import default_global_rulebook_path
from ..page_paths import default_a07_source_path, suggest_default_mapping_path


class A07PageSupportRenderMixin:
    def _refresh_suggestions_tree(self) -> None:
        work_level = self._selected_control_work_level()
        current_selection = self.tree_control_suggestions.selection()
        selected_id = str(current_selection[0]).strip() if current_selection else ""
        selected_code = self._selected_control_code()
        suggestions_actions = getattr(self, "control_suggestions_actions", None)
        if work_level == "rf1022":
            selected_group = self._selected_rf1022_group()
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
            actionable_count = global_safe_count
            action_counter = getattr(self, "_rf1022_candidate_action_counts", None)
            if callable(action_counter):
                try:
                    actionable_count = int(action_counter(all_candidates).get("actionable", 0))
                except Exception:
                    actionable_count = global_safe_count
            best_button = getattr(self, "btn_control_best", None)
            if best_button is not None:
                try:
                    best_button.configure(text="Bruk kandidat")
                    best_button.state(["!disabled"] if selected_id and count else ["disabled"])
                except Exception:
                    pass
            batch_button = getattr(self, "btn_control_batch_suggestions", None)
            if batch_button is not None:
                try:
                    batch_button.configure(text="Kjør automatisk matching")
                    batch_button.state(["!disabled"] if actionable_count else ["disabled"])
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
            tree_suggestions = getattr(self, "tree_suggestions", None)
            if tree_suggestions is not None:
                self._fill_tree(
                    tree_suggestions,
                    pd.DataFrame(columns=[c[0] for c in _SUGGESTION_COLUMNS]),
                    _SUGGESTION_COLUMNS,
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
                best_button.configure(text="Bruk forslag")
            except Exception:
                pass
        batch_button = getattr(self, "btn_control_batch_suggestions", None)
        if batch_button is not None:
            try:
                batch_button.configure(text="Bruk sikre forslag")
            except Exception:
                pass
        suggestions_df = self._ensure_suggestion_display_fields()
        filtered = filter_suggestions_df(
            suggestions_df,
            scope_key="valgt_kode",
            selected_code=selected_code,
            unresolved_code_values=unresolved_codes(self.a07_overview_df),
        )
        selected_group = self._selected_rf1022_group()
        filtered = filter_suggestions_for_rf1022_group(filtered, selected_group)
        self._reconfigure_tree_columns(self.tree_control_suggestions, _CONTROL_SUGGESTION_COLUMNS)
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
                has_strict_candidate = any(a07_suggestion_is_strict_auto(row) for _, row in filtered.iterrows())
                if selected_code and selected_code not in self._locked_codes() and has_strict_candidate:
                    batch_button.state(["!disabled"])
                else:
                    batch_button.state(["disabled"])
        except Exception:
            pass
        if self._selected_control_alternative_mode() == "suggestions":
            self.control_alternative_summary_var.set(str(self.control_suggestion_summary_var.get() or "").strip())

    def _refresh_control_support_trees(self) -> None:
        active_tab = self._active_support_tab_key()
        work_level = self._selected_control_work_level()
        selected_group = self._selected_rf1022_group()
        selected_code = self._selected_control_code()

        if active_tab == "control_statement":
            sync_statement_layout = getattr(self, "_sync_control_statement_tab_layout", None)
            if callable(sync_statement_layout):
                sync_statement_layout()
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
            if work_level == "rf1022" and selected_group:
                try:
                    children = self.tree_control_statement.get_children()
                except Exception:
                    children = ()
                if selected_group in children:
                    self._set_tree_selection(self.tree_control_statement, selected_group)
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
        selected_account = None
        try:
            current_accounts = tree_control_accounts.selection()
            if current_accounts:
                selected_account = str(current_accounts[0]).strip() or None
        except Exception:
            selected_account = None
        self._refresh_suggestions_tree()

        if work_level == "rf1022":
            accounts_df = build_control_statement_accounts_df(
                self.control_gl_df,
                self.control_statement_df,
                selected_group,
            )
            self.control_selected_accounts_df = accounts_df
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
                    self.control_selected_accounts_df = selected_accounts[
                        [c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                    ].reset_index(drop=True)
            else:
                self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
            summary_label = selected_code

        self.control_accounts_summary_var.set(
            build_control_accounts_summary(
                self.control_selected_accounts_df,
                summary_label,
                basis_col=self.workspace.basis_col,
            )
        )
        self._fill_tree(
            tree_control_accounts,
            self.control_selected_accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
            row_tag_fn=control_gl_family_tree_tag,
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
        if work_level != "rf1022" and target_account and target_account in children:
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
        if current_tab is self.tab_suggestions:
            return "suggestions"
        if current_tab is self.tab_history:
            return "history"
        if current_tab is self.tab_control_statement:
            return "control_statement"
        if current_tab is self.tab_unmapped:
            return "unmapped"
        if current_tab is self.tab_mapping:
            return "mapping"
        return None

    def _refresh_groups_tree(self) -> None:
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is None:
            return
        self._fill_tree(
            tree_groups,
            self.groups_df,
            _GROUP_COLUMNS,
            iid_column="GroupId",
        )
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
        if tab_key == "control_statement":
            self._fill_tree_chunked(
                self.tree_control_statement,
                self.control_statement_df,
                _CONTROL_STATEMENT_COLUMNS,
                iid_column="Gruppe",
                row_tag_fn=lambda row: a07_control_status.control_tree_tag(row.get("Status")),
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
        )
        self._update_history_details(code)

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
                self._set_tree_selection(self.tree_history, code_s)
            except Exception:
                pass
        elif tab_key == "mapping":
            try:
                self.tree_control_accounts.focus_set()
            except Exception:
                pass
        elif tab_key == "control_statement":
            if work_level == "rf1022":
                selected_group = self._selected_rf1022_group()
                try:
                    children = self.tree_control_statement.get_children()
                except Exception:
                    children = ()
                if selected_group and selected_group in children:
                    try:
                        self._set_tree_selection(self.tree_control_statement, selected_group)
                    except Exception:
                        pass
            try:
                self.tree_control_statement.focus_set()
            except Exception:
                pass

    def _set_control_smart_button(
        self,
        *,
        text: str = "",
        command=None,
        enabled: bool = False,
        visible: bool = True,
    ) -> None:
        smart_button = getattr(self, "btn_control_smart", None)
        if smart_button is None:
            return
        control_panel = getattr(self, "control_panel", None)
        if not visible:
            try:
                smart_button.state(["disabled"])
            except Exception:
                pass
            try:
                smart_button.pack_forget()
            except Exception:
                pass
            if control_panel is not None:
                try:
                    control_panel.pack_forget()
                except Exception:
                    pass
            return
        if control_panel is not None:
            try:
                if not bool(control_panel.winfo_manager()):
                    lower_body = getattr(self, "control_lower_body", None)
                    if lower_body is not None:
                        control_panel.pack(fill="x", pady=(0, 2), before=lower_body)
                    else:
                        control_panel.pack(fill="x", pady=(0, 2))
            except Exception:
                pass
        try:
            if not bool(smart_button.winfo_manager()):
                smart_button.pack(side="right")
        except Exception:
            pass
        try:
            if command is not None:
                smart_button.configure(text=text, command=command)
            else:
                smart_button.configure(text=text)
        except Exception:
            pass
        try:
            smart_button.state(["!disabled"] if enabled else ["disabled"])
        except Exception:
            pass

    def _update_control_panel(self) -> None:
        work_level = self._selected_control_work_level()
        if work_level == "rf1022":
            group_id = self._selected_rf1022_group()
            if not group_id:
                self.control_summary_var.set("Velg RF-1022-post til hoyre.")
                self.control_intro_var.set("")
                self.control_meta_var.set("")
                self.control_match_var.set("")
                self.control_mapping_var.set("")
                self.control_history_var.set("")
                self.control_best_var.set("")
                self.control_next_var.set("")
                self.control_drag_var.set("")
                self.control_suggestion_effect_var.set("")
                try:
                    best_button = getattr(self, "btn_control_best", None)
                    history_button = getattr(self, "btn_control_history", None)
                    batch_button = getattr(self, "btn_control_batch_suggestions", None)
                    self._set_control_smart_button(visible=False)
                    for button in (best_button, history_button, batch_button):
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
                    badges.append(f"GL {gl_text}")
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
            self.control_drag_var.set("")
            self.control_suggestion_effect_var.set("")

            try:
                best_button = getattr(self, "btn_control_best", None)
                history_button = getattr(self, "btn_control_history", None)
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                self._set_control_smart_button(
                    text=action_label,
                    command=lambda target=action_target: self._open_guided_support_target(target),
                    enabled=True,
                    visible=(action_target not in {"suggestions", "history", "control_statement"}),
                )
                for button in (best_button, history_button):
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
            self.control_summary_var.set("Velg A07-kode til hoyre.")
            self.control_intro_var.set("")
            self.control_meta_var.set("")
            self.control_match_var.set("")
            self.control_mapping_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            self.control_next_var.set("")
            self.control_drag_var.set("")
            self.control_suggestion_effect_var.set("Velg et forslag for aa se hva som blir koblet.")
            try:
                best_button = getattr(self, "btn_control_best", None)
                history_button = getattr(self, "btn_control_history", None)
                batch_button = getattr(self, "btn_control_batch_suggestions", None)
                self._set_control_smart_button(visible=False)
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
        self.control_drag_var.set("")

        try:
            best_button = getattr(self, "btn_control_best", None)
            history_button = getattr(self, "btn_control_history", None)
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
                if panel_state.best_suggestion_within_tolerance and code not in self._locked_codes():
                    best_button.state(["!disabled"])
                else:
                    best_button.state(["disabled"])
            if history_button is not None:
                if panel_state.has_history:
                    history_button.state(["!disabled"])
                else:
                    history_button.state(["disabled"])
            if batch_button is not None:
                if (
                    code
                    and code not in self._locked_codes()
                    and best_row is not None
                    and a07_suggestion_is_strict_auto(best_row)
                ):
                    batch_button.state(["!disabled"])
                else:
                    batch_button.state(["disabled"])
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
        unsolved_count = a07_control_status.count_pending_control_items(visible_control_df)
        self.summary_var.set(
            " | ".join(
                [
                    context_text,
                    f"{unsolved_count} åpne",
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

        self.control_bucket_var.set(a07_control_status.build_control_bucket_summary(visible_control_df))
        self.details_var.set("Bruk Kilder... for filoversikt.")
