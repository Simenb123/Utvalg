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
import classification_workspace
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
    a07_group_member_signature,
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
    select_safe_history_codes,
    ui_suggestion_row_from_series,
)
from a07_feature.rule_learning import evaluate_a07_rule_name_status
from a07_feature.suggest.rulebook import load_rulebook
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

from .page_a07_context_menu import A07PageContextMenuMixin
from .page_a07_constants import (
    _BASIS_LABELS,
    _CONTROL_A07_TOTAL_IID,
    _CONTROL_ALTERNATIVE_MODE_LABELS,
    _CONTROL_GL_DATA_COLUMNS,
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_GL_SCOPE_ALIASES,
    _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL,
    _CONTROL_GL_SCOPE_LABELS,
    _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL,
    _CONTROL_GL_SERIES_LABELS,
    _CONTROL_VIEW_LABELS,
    _SUGGESTION_SCOPE_LABELS,
    _SUMMARY_TOTAL_TAG,
)
from .control.statement_ui import A07PageControlStatementMixin
from .page_a07_dialogs import _parse_konto_tokens
from .page_a07_env import session
from .page_a07_frames import _empty_suggestions_df


class A07PageContextMixin(A07PageContextMenuMixin, A07PageControlStatementMixin):
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

        parts = []
        if suggested_accounts:
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
        support_tree = getattr(self, "tree_suggestions", None)
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
        if focused is support_tree:
            row = self._selected_suggestion_row_from_tree(support_tree)
            if row is not None:
                return row
        if active_tab == "suggestions" and control_tree is not None:
            row = self._selected_suggestion_row_from_tree(control_tree)
            if row is not None:
                return row

        row = self._selected_suggestion_row_from_tree(control_tree) if control_tree is not None else None
        if row is not None:
            return row
        row = self._selected_suggestion_row_from_tree(support_tree)
        if row is not None:
            return row
        return self._best_suggestion_row_for_selected_control_code()

    def _best_suggestion_row_for_selected_control_code(self) -> pd.Series | None:
        code = self._selected_control_code()
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
        best_row = self._best_suggestion_row_for_selected_control_code() if code is None else best_suggestion_row_for_code(
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

    def _selected_a07_filter(self) -> str:
        if getattr(self, "a07_filter_widget", None) is None:
            return "alle"
        try:
            label = str(self.a07_filter_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _CONTROL_VIEW_LABELS.items():
            if value == label:
                return key

        fallback = str(self.a07_filter_var.get() or "").strip().lower()
        return fallback or "alle"

    def _selected_suggestion_scope(self) -> str:
        try:
            label = str(self.suggestion_scope_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _SUGGESTION_SCOPE_LABELS.items():
            if value == label:
                return key

        fallback = str(self.suggestion_scope_var.get() or "").strip().lower()
        return fallback or "valgt_kode"

    def _control_work_level_for_gl_scope(self) -> str:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        return work_level if work_level in _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL else "a07"

    def _control_gl_scope_keys_for_work_level(self, work_level: str | None = None) -> tuple[str, ...]:
        level = str(work_level or self._control_work_level_for_gl_scope()).strip().lower()
        return _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL.get(level, _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL["a07"])

    def _control_gl_scope_labels_for_work_level(self, work_level: str | None = None) -> dict[str, str]:
        level = str(work_level or self._control_work_level_for_gl_scope()).strip().lower()
        return _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL.get(level, _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL["a07"])

    def _normalize_control_gl_scope(self, scope_key: str | None, *, work_level: str | None = None) -> str:
        scope = str(scope_key or "").strip().lower()
        scope = _CONTROL_GL_SCOPE_ALIASES.get(scope, scope)
        keys = self._control_gl_scope_keys_for_work_level(work_level)
        if scope in keys:
            return scope
        return "alle"

    def _control_gl_scope_label(self, scope_key: str | None, *, work_level: str | None = None) -> str:
        scope = self._normalize_control_gl_scope(scope_key, work_level=work_level)
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        return labels.get(scope, _CONTROL_GL_SCOPE_LABELS.get(scope, _CONTROL_GL_SCOPE_LABELS["alle"]))

    def _sync_control_gl_scope_widget(self) -> None:
        work_level = self._control_work_level_for_gl_scope()
        keys = self._control_gl_scope_keys_for_work_level(work_level)
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        current = self._normalize_control_gl_scope(self._selected_control_gl_scope(), work_level=work_level)
        if current not in keys:
            current = "alle"
        label_values = [labels[key] for key in keys]
        try:
            self.control_gl_scope_var.set(current)
            self.control_gl_scope_label_var.set(labels[current])
        except Exception:
            pass
        widget = getattr(self, "control_gl_scope_widget", None)
        if widget is not None:
            try:
                widget.configure(values=label_values, state="readonly")
                widget.set(labels[current])
            except Exception:
                pass

    def _selected_control_gl_scope(self) -> str:
        widget = getattr(self, "control_gl_scope_widget", None)
        try:
            label = str(widget.get() or "").strip() if widget is not None else ""
        except Exception:
            label = ""

        work_level = self._control_work_level_for_gl_scope()
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        for key, value in labels.items():
            if value == label:
                return self._normalize_control_gl_scope(key, work_level=work_level)
        for key, value in _CONTROL_GL_SCOPE_LABELS.items():
            if value == label:
                return self._normalize_control_gl_scope(key, work_level=work_level)

        fallback = str(self.control_gl_scope_var.get() or "").strip().lower()
        return self._normalize_control_gl_scope(fallback or "alle", work_level=work_level)

    def _set_control_gl_scope(self, scope_key: str | None) -> None:
        scope = self._normalize_control_gl_scope(scope_key)
        label = self._control_gl_scope_label(scope)
        try:
            self.control_gl_scope_var.set(scope)
            self.control_gl_scope_label_var.set(label)
        except Exception:
            pass
        widget = getattr(self, "control_gl_scope_widget", None)
        if widget is not None:
            try:
                widget.set(label)
            except Exception:
                pass
        self._on_control_gl_filter_changed()

    def _on_control_gl_scope_changed(self) -> None:
        scope = self._selected_control_gl_scope()
        try:
            self.control_gl_scope_var.set(scope)
            self.control_gl_scope_label_var.set(self._control_gl_scope_label(scope))
        except Exception:
            pass
        self._on_control_gl_filter_changed()

    def _apply_control_gl_scope(
        self,
        control_gl_df: pd.DataFrame,
        *,
        selected_code: str | None = None,
    ) -> pd.DataFrame:
        if control_gl_df is None or control_gl_df.empty:
            return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

        scope = self._normalize_control_gl_scope(self._selected_control_gl_scope())
        if scope == "alle":
            return control_gl_df.reset_index(drop=True)

        code = str(selected_code or "").strip()
        work = control_gl_df.copy()
        code_values = work.get("Kode", pd.Series("", index=work.index)).fillna("").astype(str).str.strip()
        work_level = self._control_work_level_for_gl_scope()
        group_id = str(getattr(self, "_selected_rf1022_group", lambda: None)() or "").strip() if work_level == "rf1022" else ""
        if work_level == "rf1022" and group_id and "Rf1022GroupId" in work.columns:
            group_values = work["Rf1022GroupId"].fillna("").astype(str).str.strip()
        else:
            group_values = pd.Series("", index=work.index, dtype="object")

        if scope == "koblede":
            if work_level == "rf1022" and group_id and "Rf1022GroupId" in work.columns:
                return work.loc[group_values == group_id].reset_index(drop=True)
            if not code:
                return work.iloc[0:0].copy().reset_index(drop=True)
            return work.loc[code_values == code].reset_index(drop=True)

        if scope == "forslag":
            if work_level == "rf1022":
                return work.iloc[0:0].copy().reset_index(drop=True)
            suggestion_accounts = set(self._selected_control_suggestion_accounts())
            if not suggestion_accounts:
                return work.iloc[0:0].copy().reset_index(drop=True)
            account_values = work.get("Konto", pd.Series("", index=work.index)).fillna("").astype(str).str.strip()
            out = work.loc[account_values.isin(suggestion_accounts)].copy()
            if code and "AliasStatus" in out.columns:
                effective_rulebook = getattr(self, "effective_rulebook", None)
                if effective_rulebook is None:
                    try:
                        effective_rulebook = load_rulebook(str(getattr(self, "rulebook_path", "") or "") or None)
                    except Exception:
                        effective_rulebook = {}
                out["AliasStatus"] = out.apply(
                    lambda row: evaluate_a07_rule_name_status(code, row.get("Navn"), effective_rulebook),
                    axis=1,
                )
            return out.reset_index(drop=True)

        return work.iloc[0:0].copy().reset_index(drop=True)

    def _selected_control_alternative_mode(self) -> str:
        notebook = getattr(self, "control_support_nb", None)
        if notebook is not None:
            try:
                current_tab = notebook.nametowidget(notebook.select())
            except Exception:
                current_tab = None
            if current_tab is getattr(self, "tab_history", None):
                return "history"
            if current_tab is getattr(self, "tab_suggestions", None):
                return "suggestions"
        widget = getattr(self, "control_alternative_mode_widget", None)
        try:
            label = str(widget.get() or "").strip() if widget is not None else ""
        except Exception:
            label = ""

        for key, value in _CONTROL_ALTERNATIVE_MODE_LABELS.items():
            if value == label:
                return key

        fallback = str(self.control_alternative_mode_var.get() or "").strip().lower()
        return fallback or "suggestions"

    def _selected_basis(self) -> str:
        try:
            label = str(self.basis_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _BASIS_LABELS.items():
            if value == label:
                return key

        fallback = str(self.basis_var.get() or "").strip()
        return fallback if fallback in _BASIS_LABELS else "Endring"

    def _selected_control_codes(self) -> list[str]:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    out: list[str] = []
                    seen: set[str] = set()
                    try:
                        selection = self.tree_a07.selection()
                    except Exception:
                        selection = ()
                    groups = [str(item or "").strip() for item in selection or () if str(item or "").strip()]
                    if not groups:
                        current_group = str(getattr(self, "_selected_rf1022_group_id", "") or "").strip()
                        if current_group:
                            groups = [current_group]
                    control_df = getattr(self, "control_df", None)
                    if control_df is None or getattr(control_df, "empty", True):
                        return out
                    for group_id in groups:
                        try:
                            matches = control_df.loc[
                                control_df["Rf1022GroupId"].fillna("").astype(str).str.strip() == group_id
                            ]
                        except Exception:
                            matches = pd.DataFrame()
                        for code in matches.get("Kode", pd.Series(dtype="object")).fillna("").astype(str):
                            code_s = str(code).strip()
                            if not code_s or code_s in seen:
                                continue
                            out.append(code_s)
                            seen.add(code_s)
                    return out
            except Exception:
                pass
        out: list[str] = []
        seen: set[str] = set()
        try:
            selection = self.tree_a07.selection()
        except Exception:
            selection = ()
        for item in selection or ():
            code = str(item or "").strip()
            if not code or code == _CONTROL_A07_TOTAL_IID or code in seen:
                continue
            tag_checker = getattr(self, "_tree_item_has_tag", None)
            if callable(tag_checker):
                try:
                    if tag_checker(self.tree_a07, code, _SUMMARY_TOTAL_TAG):
                        continue
                except Exception:
                    pass
            out.append(code)
            seen.add(code)
        return out

    def _selected_group_id(self) -> str | None:
        try:
            selection = self.tree_groups.selection()
        except Exception:
            selection = ()
        if selection:
            group_id = str(selection[0] or "").strip()
            return group_id or None
        selected_code = str(self._selected_control_code() or "").strip()
        if selected_code.startswith("A07_GROUP:"):
            return selected_code
        return None

    def _groupable_selected_control_codes(self) -> list[str]:
        return [code for code in self._selected_control_codes() if code and not code.startswith("A07_GROUP:")]

    def _control_code_name_map(self) -> dict[str, str]:
        code_names: dict[str, str] = {}
        for df in (
            getattr(self, "control_df", None),
            getattr(self, "a07_overview_df", None),
            getattr(getattr(self, "workspace", None), "a07_df", None),
        ):
            if df is None or getattr(df, "empty", True):
                continue
            if "Kode" not in df.columns or "Navn" not in df.columns:
                continue
            try:
                for _, row in df[["Kode", "Navn"]].dropna(subset=["Kode"]).iterrows():
                    code = str(row.get("Kode") or "").strip()
                    navn = str(row.get("Navn") or "").strip()
                    if code and navn and code not in code_names:
                        code_names[code] = navn
            except Exception:
                continue
        return code_names

    def _default_group_name(self, codes: Sequence[str]) -> str:
        return build_default_group_name(codes, code_names=self._control_code_name_map())

    def _selected_control_row(self) -> pd.Series | None:
        code = str(self._selected_control_code() or "").strip()
        if not code or self.control_df is None or self.control_df.empty:
            return None
        try:
            matches = self.control_df.loc[self.control_df["Kode"].astype(str).str.strip() == code]
        except Exception:
            return None
        if matches.empty:
            return None
        try:
            return matches.iloc[0]
        except Exception:
            return None

    def _selected_code_accounts(self, code: str | None = None) -> list[str]:
        code_s = str(code or self._selected_control_code() or "").strip()
        if not code_s:
            return []
        return accounts_for_code(self._effective_mapping(), code_s)

    def _open_saldobalanse_workspace(
        self,
        *,
        accounts: Sequence[str] | None = None,
        payroll_scope: str | None = None,
        status_text: str | None = None,
    ) -> bool:
        try:
            host = self.winfo_toplevel()
        except Exception:
            host = None
        notebook = getattr(host, "nb", None)
        saldobalanse_page = getattr(host, "page_saldobalanse", None)
        if notebook is None or saldobalanse_page is None:
            return False
        try:
            notebook.select(saldobalanse_page)
        except Exception:
            return False
        refresh = getattr(saldobalanse_page, "refresh_from_session", None)
        if callable(refresh):
            try:
                refresh(session)
            except Exception:
                pass
        focus_accounts = getattr(saldobalanse_page, "focus_payroll_accounts", None)
        if callable(focus_accounts):
            try:
                focus_accounts(
                    list(accounts or ()),
                    payroll_scope=str(payroll_scope or classification_workspace.QUEUE_ALL),
                )
            except TypeError:
                try:
                    focus_accounts(list(accounts or ()))
                except Exception:
                    pass
            except Exception:
                pass
        if status_text:
            try:
                self.status_var.set(status_text)
            except Exception:
                pass
        return True

    def _open_saldobalanse_for_selected_accounts(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        label = (
            f"Apnet Saldobalanse for klassifisering av konto {accounts[0]}."
            if len(accounts) == 1
            else f"Apnet Saldobalanse for klassifisering av {len(accounts)} kontoer."
        )
        if not self._open_saldobalanse_workspace(accounts=accounts, status_text=label):
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_control_gl)

    def _open_saldobalanse_for_selected_code_classification(self) -> None:
        code = str(self._selected_control_code() or "").strip()
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return
        accounts = self._selected_code_accounts(code)
        row = self._selected_control_row()
        next_action = str((row.get("NesteHandling") if row is not None else "") or "").strip()
        if a07_control_status.is_saldobalanse_follow_up_action(next_action):
            label = f"{next_action} A07 viser behovet, men klassifiseringen gjores i Saldobalanse."
            payroll_scope = a07_control_status.saldobalanse_queue_for_control_action(next_action)
        elif accounts:
            label = f"Apnet Saldobalanse for klassifisering av kontoene bak {code}."
            payroll_scope = classification_workspace.QUEUE_ALL
        else:
            label = f"Apnet Saldobalanse for klassifisering av {code}."
            payroll_scope = classification_workspace.QUEUE_ALL
        try:
            opened = self._open_saldobalanse_workspace(
                accounts=accounts,
                payroll_scope=payroll_scope,
                status_text=label,
            )
        except TypeError:
            opened = self._open_saldobalanse_workspace(accounts=accounts, status_text=label)
        if not opened:
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_a07)

    def _open_saldobalanse_for_selected_group_classification(self) -> None:
        group_id = str(self._selected_group_id() or "").strip()
        if not group_id:
            self._notify_inline("Velg en gruppe forst.", focus_widget=self.tree_groups)
            return
        accounts = accounts_for_code(self._effective_mapping(), group_id)
        label = (
            f"Apnet Saldobalanse for klassifisering av kontoene bak gruppen {group_id}."
            if accounts
            else f"Apnet Saldobalanse fra gruppen {group_id}."
        )
        if not self._open_saldobalanse_workspace(accounts=accounts, status_text=label):
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_groups)

    def _sync_groups_panel_visibility(self) -> None:
        try:
            group_count = int(len(self.groups_df.index)) if self.groups_df is not None else 0
        except Exception:
            group_count = 0

        selected_group = str(self._selected_group_id() or "").strip()
        create_button = getattr(self, "btn_create_group", None)
        remove_button = getattr(self, "btn_remove_group", None)
        if create_button is not None:
            try:
                if len(self._groupable_selected_control_codes()) >= 2:
                    create_button.state(["!disabled"])
                else:
                    create_button.state(["disabled"])
            except Exception:
                pass
        if remove_button is not None:
            try:
                if selected_group:
                    remove_button.state(["!disabled"])
                else:
                    remove_button.state(["disabled"])
            except Exception:
                pass
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is not None:
            try:
                tree_groups.configure(height=max(2, min(group_count or 2, 4)))
            except Exception:
                pass
        lower_body = getattr(self, "control_lower_body", None)
        groups_panel = getattr(self, "control_groups_panel", None)
        if lower_body is not None and groups_panel is not None:
            try:
                pane_names = tuple(str(value) for value in lower_body.panes())
            except Exception:
                pane_names = ()
            panel_name = str(groups_panel)
            should_show = bool(getattr(self, "_control_advanced_visible", False))
            if should_show and panel_name not in pane_names:
                try:
                    lower_body.add(groups_panel, weight=1)
                except Exception:
                    pass
            elif not should_show and panel_name in pane_names:
                try:
                    lower_body.forget(groups_panel)
                except Exception:
                    pass

    def _sync_control_panel_visibility(self) -> None:
        label_specs = (
            ("lbl_control_meta", getattr(self, "control_meta_var", None)),
            ("lbl_control_summary", getattr(self, "control_summary_var", None)),
            ("lbl_control_next", getattr(self, "control_next_var", None)),
        )
        if bool(getattr(self, "_compact_control_status", False)):
            for label_name, _variable in label_specs:
                label = getattr(self, label_name, None)
                if label is None:
                    continue
                try:
                    if bool(label.winfo_manager()):
                        label.pack_forget()
                except Exception:
                    pass
            smart_button = getattr(self, "btn_control_smart", None)
            control_panel = getattr(self, "control_panel", None)
            try:
                smart_visible = bool(smart_button.winfo_manager()) if smart_button is not None else False
            except Exception:
                smart_visible = False
            if control_panel is not None and not smart_visible:
                try:
                    control_panel.pack_forget()
                except Exception:
                    pass
            return
        for label_name, variable in label_specs:
            label = getattr(self, label_name, None)
            if label is None or variable is None:
                continue
            try:
                text = str(variable.get() or "").strip()
            except Exception:
                text = ""
            try:
                visible = bool(label.winfo_manager())
            except Exception:
                visible = False
            if text and not visible:
                try:
                    label.pack(anchor="w", pady=(2, 0))
                except Exception:
                    pass
            elif not text and visible:
                try:
                    label.pack_forget()
                except Exception:
                    pass

    def _prepare_tree_context_selection(
        self,
        tree: ttk.Treeview,
        event: tk.Event | None = None,
        *,
        preserve_existing_selection: bool = True,
        on_selected: Callable[[], None] | None = None,
    ) -> str | None:
        iid = self._tree_iid_from_event(tree, event)
        if not iid:
            return None
        tag_checker = getattr(self, "_tree_item_has_tag", None)
        if callable(tag_checker):
            try:
                if tag_checker(tree, iid, _SUMMARY_TOTAL_TAG):
                    return None
            except Exception:
                pass

        try:
            current_selection = tuple(str(value).strip() for value in tree.selection())
        except Exception:
            current_selection = ()
        already_selected = iid in current_selection

        try:
            if preserve_existing_selection and already_selected:
                tree.focus(iid)
            else:
                self._set_tree_selection(tree, iid, reveal=False, focus=True)
        except Exception:
            return None

        try:
            tree.focus_set()
        except Exception:
            pass

        if callable(on_selected):
            try:
                on_selected()
            except Exception:
                pass
        return iid

    def _post_context_menu(self, menu: tk.Menu, event: tk.Event) -> str:
        self._active_context_menu = menu
        try:
            menu.tk_popup(int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0)))
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"

    def _show_control_gl_context_menu(self, event: tk.Event) -> str | None:
        return A07PageContextMenuMixin._show_control_gl_context_menu(self, event)

    def _show_control_code_context_menu(self, event: tk.Event) -> str | None:
        return A07PageContextMenuMixin._show_control_code_context_menu(self, event)

        iid = self._prepare_tree_context_selection(
            self.tree_a07,
            event,
            preserve_existing_selection=True,
            on_selected=self._on_control_selection_changed,
        )
        if not iid:
            return None

        code = str(self._selected_control_code() or "").strip()
        is_group = code.startswith("A07_GROUP:")
        selected_codes = self._groupable_selected_control_codes()
        selected_accounts = self._selected_control_gl_accounts()
        has_group_selection = len(selected_codes) >= 2
        has_account_mapping = any(str(self._effective_mapping().get(account) or "").strip() for account in selected_accounts)
        is_locked = code in self._locked_codes()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Tildel valgte kontoer hit (->)",
            command=self._assign_selected_control_mapping,
            state=("normal" if code and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=self._clear_selected_control_mapping,
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Smartmapping for valgt kode",
            command=self._run_selected_control_action,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_command(
            label="Bruk beste forslag",
            command=self._apply_best_suggestion_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_command(
            label="Bruk historikk",
            command=self._apply_history_for_selected_code,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_command(
            label="Rydd klassifisering i Saldobalanse",
            command=self._open_saldobalanse_for_selected_code_classification,
            state=("normal" if code and not is_group else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Opprett gruppe fra valgte koder",
            command=self._create_group_from_selection,
            state=("normal" if has_group_selection else "disabled"),
        )
        menu.add_command(
            label="Gi nytt navn til gruppe...",
            command=self._rename_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_command(
            label="Opplos gruppe",
            command=self._remove_selected_group,
            state=("normal" if is_group else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label=("LÃƒÂ¥s opp kode" if is_locked else "LÃƒÂ¥s kode"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
            state=("normal" if code else "disabled"),
        )
        return self._post_context_menu(menu, event)

    def _show_group_context_menu(self, event: tk.Event) -> str | None:
        return A07PageContextMenuMixin._show_group_context_menu(self, event)

        iid = self._prepare_tree_context_selection(
            self.tree_groups,
            event,
            preserve_existing_selection=False,
            on_selected=self._on_group_selection_changed,
        )
        if not iid:
            return None

        group_id = str(self._selected_group_id() or "").strip()
        selected_accounts = self._selected_control_gl_accounts()
        has_account_mapping = any(str(self._effective_mapping().get(account) or "").strip() for account in selected_accounts)
        is_locked = group_id in self._locked_codes()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Tildel valgte kontoer hit (->)",
            command=self._assign_selected_control_mapping,
            state=("normal" if group_id and selected_accounts else "disabled"),
        )
        menu.add_command(
            label="Fjern mapping fra valgte kontoer (<-)",
            command=self._clear_selected_control_mapping,
            state=("normal" if has_account_mapping else "disabled"),
        )
        menu.add_separator()
        menu.add_command(
            label="Rydd klassifisering i Saldobalanse",
            command=self._open_saldobalanse_for_selected_group_classification,
        )
        menu.add_separator()
        menu.add_command(label="Gi nytt navn til gruppe...", command=self._rename_selected_group)
        menu.add_command(label="Opplos gruppe", command=self._remove_selected_group)
        menu.add_command(
            label=("LÃƒÂ¥s opp gruppe" if is_locked else "LÃƒÂ¥s gruppe"),
            command=(self._unlock_selected_code if is_locked else self._lock_selected_code),
        )
        return self._post_context_menu(menu, event)

    def _next_group_id(self, codes: Sequence[str]) -> str:
        code_tokens = [str(code).strip() for code in codes if str(code).strip()]
        existing = self._existing_group_id_for_codes(code_tokens)
        if existing:
            return existing
        slug = "+".join(code_tokens[:4]) or "group"
        base = f"A07_GROUP:{slug}"
        if base not in self.workspace.groups:
            return base
        idx = 2
        while f"{base}:{idx}" in self.workspace.groups:
            idx += 1
        return f"{base}:{idx}"

    def _existing_group_id_for_codes(self, codes: Sequence[str]) -> str | None:
        wanted = a07_group_member_signature(codes)
        if not wanted:
            return None
        for group_id, group in (getattr(self.workspace, "groups", {}) or {}).items():
            current = a07_group_member_signature(getattr(group, "member_codes", ()) or ())
            if current == wanted:
                return str(group_id)
        return None

    def _notify_inline(self, message: str, *, focus_widget: object | None = None) -> None:
        self.status_var.set(str(message or "").strip())
        if focus_widget is None:
            return
        try:
            focus_widget.focus_set()
        except Exception:
            return

    def _control_gl_label_key(self, labels: dict[str, str], raw_key: object, raw_label: object, default: str) -> str:
        key_s = str(raw_key or "").strip()
        if key_s in labels:
            return key_s
        label_s = str(raw_label or "").strip()
        for key, label in labels.items():
            if label_s == str(label):
                return key
        return default

    def _control_gl_filter_state(self) -> tuple[str, str, str, bool, bool]:
        try:
            search_text = str(self.control_gl_filter_var.get() or "")
        except Exception:
            search_text = ""
        try:
            mapping_key = self._control_gl_label_key(
                _CONTROL_GL_MAPPING_LABELS,
                self.control_gl_mapping_filter_var.get(),
                self.control_gl_mapping_filter_label_var.get(),
                "alle",
            )
        except Exception:
            mapping_key = "alle"
        try:
            series_key = self._control_gl_label_key(
                _CONTROL_GL_SERIES_LABELS,
                self.control_gl_series_filter_var.get(),
                self.control_gl_series_filter_label_var.get(),
                "alle",
            )
        except Exception:
            series_key = "alle"
        try:
            only_unmapped = bool(self.control_gl_unmapped_only_var.get())
        except Exception:
            only_unmapped = False
        try:
            active_only = bool(self.control_gl_active_only_var.get())
        except Exception:
            active_only = False
        return search_text, mapping_key, series_key, only_unmapped, active_only
