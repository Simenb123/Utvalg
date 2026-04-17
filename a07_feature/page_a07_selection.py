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
from a07_feature import control_status as a07_control_status
from a07_feature.control_matching import (
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
from a07_feature.page_control_data import (
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

from . import page_a07_shared as _shared
from .page_a07_shared import *  # noqa: F401,F403
from .control_presenter import (
    build_gl_selection_status_message,
    build_selected_code_status_message,
)

class A07PageSelectionMixin:
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
        suggestions_frame = getattr(self, "tab_suggestions", None)
        history_frame = getattr(self, "tab_history", None)
        suggestions_actions = getattr(self, "control_alternative_suggestion_actions", None)
        history_actions = getattr(self, "control_alternative_history_actions", None)

        def _show_frame(frame: object | None, *, selected: bool) -> None:
            if frame is None:
                return
            try:
                visible = bool(frame.winfo_manager())
            except Exception:
                visible = False
            if selected and not visible:
                try:
                    frame.pack(fill="both", expand=True)
                except Exception:
                    pass
            elif not selected and visible:
                try:
                    frame.pack_forget()
                except Exception:
                    pass

        def _show_actions(frame: object | None, *, selected: bool) -> None:
            if frame is None:
                return
            try:
                visible = bool(frame.winfo_manager())
            except Exception:
                visible = False
            if selected and not visible:
                try:
                    frame.pack(side="right")
                except Exception:
                    pass
            elif not selected and visible:
                try:
                    frame.pack_forget()
                except Exception:
                    pass

        _show_frame(suggestions_frame, selected=(mode == "suggestions"))
        _show_frame(history_frame, selected=(mode == "history"))
        _show_actions(suggestions_actions, selected=(mode == "suggestions"))
        _show_actions(history_actions, selected=(mode == "history"))

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
        code = self._selected_control_code()
        current_accounts = accounts_for_code(self._effective_mapping(), code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        best_row = self._best_suggestion_row_for_selected_control_code()
        return preferred_support_tab_key(
            current_accounts=current_accounts,
            history_accounts=history_accounts,
            best_row=best_row,
        )

    def _select_support_tab_key(self, tab_key: str | None, *, force_render: bool = True) -> None:
        key = str(tab_key or "").strip().lower()
        if not key:
            return

        if key in {"suggestions", "history"}:
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
        if key in {"suggestions", "history"} and getattr(self, "tab_alternatives", None) is not None:
            target = getattr(self, "tab_alternatives", None)
        elif key == "suggestions":
            target = getattr(self, "tab_suggestions", None)
        elif key == "history":
            target = getattr(self, "tab_history", None)
        elif key == "mapping":
            target = getattr(self, "tab_mapping", None)
        elif key == "reconcile":
            target = getattr(self, "tab_reconcile", None)
        elif key == "control_statement":
            target = getattr(self, "tab_control_statement", None)
        elif key == "groups":
            target = getattr(self, "tab_groups", None)
        elif key == "unmapped":
            target = getattr(self, "tab_unmapped", None)

        if target is None:
            if key in {"reconcile", "control_statement", "groups", "unmapped"}:
                target = getattr(self, "tab_control_statement", None)
            elif key in {"mapping"}:
                target = getattr(self, "tab_mapping", None)
            elif key in {"suggestions", "history"}:
                target = getattr(self, "tab_alternatives", None)
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
        if bool(getattr(self, "_skip_initial_control_followup", False)):
            self.workspace.selected_code = self._selected_control_code()
            self._update_history_details_from_selection()
            try:
                A07PageSelectionMixin._update_selected_code_status_message(self)
            except Exception:
                pass
            if bool(getattr(self, "_control_details_visible", False)):
                self._select_support_tab_key(self._preferred_support_tab_for_selected_code(), force_render=False)
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return
        self.workspace.selected_code = self._selected_control_code()
        self._update_history_details_from_selection()
        try:
            A07PageSelectionMixin._update_selected_code_status_message(self)
        except Exception:
            pass
        if bool(getattr(self, "_refresh_in_progress", False)):
            if bool(getattr(self, "_control_details_visible", False)):
                self._select_support_tab_key(self._preferred_support_tab_for_selected_code(), force_render=False)
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            return
        schedule_followup = getattr(self, "_schedule_control_selection_followup", None)
        if callable(schedule_followup):
            if bool(getattr(self, "_control_details_visible", False)):
                self._select_support_tab_key(self._preferred_support_tab_for_selected_code(), force_render=False)
            self._update_control_panel()
            self._update_control_transfer_buttons()
            sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
            if callable(sync_groups_panel_visibility):
                sync_groups_panel_visibility()
            schedule_followup()
            return
        if bool(getattr(self, "_control_details_visible", False)):
            self._select_support_tab_key(self._preferred_support_tab_for_selected_code(), force_render=False)
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
        return self._selected_code_from_tree(self.tree_a07)

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

    def _set_tree_selection(self, tree: ttk.Treeview, target: str | None) -> bool:
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
            tree.focus(target_s)
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

    def _on_a07_filter_changed(self) -> None:
        self.a07_filter_var.set(self._selected_a07_filter())
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)

    def _select_primary_tab(self) -> None:
        """No-op: arbeidsflaten bruker ikke interne tabs som kan byttes."""
        pass
