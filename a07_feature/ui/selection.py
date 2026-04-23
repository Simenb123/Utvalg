from __future__ import annotations


import copy
import faulthandler
import json
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Sequence

import pandas as pd

import app_paths
import payroll_classification
import session
from account_profile_legacy_api import AccountProfileLegacyApi
try:
    import konto_klassifisering as konto_klassifisering
except Exception:
    konto_klassifisering = None
from a07_feature import (
    A07Group,
    AccountUsageFeatures,
    A07WorkspaceData,
    SuggestConfig,
    apply_groups_to_mapping,
    apply_suggestion_to_mapping,
    build_account_usage_features,
    build_grouped_a07_df,
    derive_groups_path,
    export_a07_workbook,
    from_trial_balance,
    load_a07_groups,
    load_locks,
    load_mapping,
    load_project_state,
    mapping_to_assigned_df,
    parse_a07_json,
    reconcile_a07_vs_gl,
    save_a07_groups,
    save_locks,
    save_mapping,
    save_project_state,
    select_batch_suggestions,
    select_magic_wand_suggestions,
    suggest_mapping_candidates,
    unmapped_accounts_df,
)
from a07_feature.control import status as a07_control_status
from a07_feature.control.data import (
    a07_suggestion_is_strict_auto,
    build_a07_overview_df,
    build_control_accounts_summary,
    build_control_gl_df,
    build_control_queue_df,
    build_control_selected_account_df,
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    build_history_comparison_df,
    build_mapping_history_details,
    build_rf1022_accounts_df,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
    control_gl_tree_tag,
    control_queue_tree_tag,
    filter_a07_overview_df,
    filter_control_gl_df,
    filter_control_search_df,
    filter_control_visible_codes_df,
    filter_suggestions_df,
    reconcile_tree_tag,
    rf1022_post_for_group,
    select_batch_suggestion_rows,
    select_magic_wand_suggestion_rows,
    suggestion_tree_tag,
    unresolved_codes,
)
from a07_feature.control.matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_suggestion_reason_label,
    build_suggestion_status_label,
    decorate_suggestions_for_display,
    build_control_suggestion_effect_summary,
    build_control_suggestion_summary,
    build_smartmapping_fallback,
    compact_accounts,
    preferred_support_tab_key,
    safe_previous_accounts_for_code,
    select_safe_history_codes,
    ui_suggestion_row_from_series,
)
from a07_feature.page_paths import (
    MATCHER_SETTINGS_DEFAULTS as _MATCHER_SETTINGS_DEFAULTS,
    _path_signature,
    bundled_default_rulebook_path as _bundled_default_rulebook_path,
    build_default_group_name,
    build_groups_df,
    build_rule_form_values,
    build_rule_payload,
    build_suggest_config,
    copy_a07_source_to_workspace,
    copy_rulebook_to_storage,
    default_a07_export_path,
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    default_a07_source_path,
    default_global_rulebook_path,
    ensure_default_rulebook_exists,
    find_previous_year_context as _find_previous_year_context,
    find_previous_year_mapping_path as _find_previous_year_mapping_path,
    get_a07_workspace_dir,
    get_active_trial_balance_path_for_context,
    get_context_snapshot,
    get_context_snapshot_with_paths,
    legacy_global_a07_mapping_path,
    legacy_global_a07_source_path,
    load_active_trial_balance_for_context,
    load_matcher_settings,
    load_previous_year_mapping_for_context,
    load_rulebook_document,
    normalize_matcher_settings,
    resolve_context_mapping_path,
    resolve_context_source_path,
    resolve_autosave_mapping_path,
    resolve_rulebook_path,
    save_matcher_settings,
    save_rulebook_document,
    suggest_default_mapping_path,
)
from a07_feature.page_windows import (
    build_source_overview_rows,
    open_mapping_overview,
    open_matcher_admin,
    open_source_overview,
)
from a07_feature.suggest.models import EXCLUDED_A07_CODES
from formatting import format_number_no
from trial_balance_reader import read_trial_balance

try:
    import client_store
except Exception:
    client_store = None

from ..page_a07_constants import _CONTROL_ALTERNATIVE_MODE_LABELS, _CONTROL_WORK_LEVEL_LABELS
from ..page_a07_frames import _empty_gl_df, _empty_suggestions_df
from ..control.presenter import (
    build_gl_selection_amount_summary,
    build_gl_selection_status_message,
    build_selected_code_status_message,
)

class A07PageSelectionMixin:
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
            self._render_active_support_tab(force=True)
        else:
            self._schedule_support_refresh()

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
                A07PageSelectionMixin._update_selected_code_status_message(self)
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
                A07PageSelectionMixin._update_selected_code_status_message(self)
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
            A07PageSelectionMixin._update_selected_code_status_message(self)
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
            self._render_active_support_tab(force=True)
            return
        if self._active_support_tab_key() == "history" and not bool(getattr(self, "_history_compare_ready", False)):
            self._schedule_support_refresh()
            return
        if self._support_views_ready:
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
            self._render_active_support_tab(force=True)
            return
        self._schedule_support_refresh()

    def _selected_control_code(self) -> str | None:
        if self._selected_control_work_level() == "a07":
            return self._selected_code_from_tree(self.tree_a07)
        group_id = self._selected_rf1022_group()
        return self._first_control_code_for_group(group_id)

    def _tree_selection_key(self, tree: ttk.Treeview | None) -> str:
        try:
            return str(tree) if tree is not None else ""
        except Exception:
            return ""

    def _release_tree_selection_suppression(self, tree: ttk.Treeview | None) -> None:
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.discard(key)

    def _is_tree_selection_suppressed(self, tree: ttk.Treeview | None) -> bool:
        key = self._tree_selection_key(tree)
        return bool(key) and key in self._suppressed_tree_select_keys

    def _set_tree_selection(
        self,
        tree: ttk.Treeview,
        target: str | None,
        *,
        reveal: bool = False,
        focus: bool = False,
    ) -> bool:
        target_s = str(target or "").strip()
        if not target_s:
            return False
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.add(key)
        previous = bool(getattr(self, "_suspend_selection_sync", False))
        self._suspend_selection_sync = True
        try:
            tree.selection_set(target_s)
            if focus:
                tree.focus(target_s)
            if reveal:
                tree.see(target_s)
            try:
                self.after_idle(lambda t=tree: self._release_tree_selection_suppression(t))
            except Exception:
                self._release_tree_selection_suppression(tree)
            return True
        except Exception:
            self._release_tree_selection_suppression(tree)
            return False
        finally:
            self._suspend_selection_sync = previous

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
            selected_code = self._selected_code_from_tree(self.tree_a07)
            selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
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
