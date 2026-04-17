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


class A07PageBackgroundMixin:
    def _start_context_restore(self, client: str | None, year: str | None) -> None:
        token = self._next_refresh_generation()
        self._diag(f"start_context_restore token={token} client={client!r} year={year!r}")
        self._schedule_refresh_watchdog("context-restore", token)
        self._support_requested = False
        self.status_var.set("Laster A07-kontekst...")
        self.details_var.set("Laster saldobalanse, mapping og prosjektoppsett i bakgrunnen...")
        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                gl_df, tb_path = self._load_active_trial_balance_cached(client, year)
                source_a07_df = _empty_a07_df()
                a07_df = _empty_a07_df()
                a07_path: Path | None = None
                source_path = resolve_context_source_path(client, year)
                if source_path is not None:
                    try:
                        source_a07_df = self._load_a07_source_cached(source_path)
                        a07_df = source_a07_df.copy()
                        a07_path = source_path
                    except Exception:
                        source_a07_df = _empty_a07_df()
                        a07_df = _empty_a07_df()
                        a07_path = None

                mapping: dict[str, str] = {}
                mapping_path: Path | None = None
                mapping_candidate = resolve_context_mapping_path(a07_path, client=client, year=year)
                if mapping_candidate is not None:
                    try:
                        mapping = self._load_mapping_file_cached(
                            mapping_candidate,
                            client=client,
                            year=year,
                        )
                        try:
                            mapping_exists = mapping_candidate.exists()
                        except Exception:
                            mapping_exists = False
                        if mapping_exists:
                            mapping_path = mapping_candidate
                    except Exception:
                        mapping = {}
                        mapping_path = None

                groups: dict[str, A07Group] = {}
                groups_path: Path | None = None
                locks: set[str] = set()
                locks_path: Path | None = None
                project_meta: dict[str, object] = {}
                project_path: Path | None = None
                if client and year:
                    try:
                        groups_path = default_a07_groups_path(client, year)
                        groups = load_a07_groups(groups_path)
                    except Exception:
                        groups = {}
                        groups_path = None
                    try:
                        locks_path = default_a07_locks_path(client, year)
                        locks = load_locks(locks_path)
                    except Exception:
                        locks = set()
                        locks_path = None
                    try:
                        project_path = default_a07_project_path(client, year)
                        project_meta = load_project_state(project_path)
                    except Exception:
                        project_meta = {}
                        project_path = None

                basis_col = str(project_meta.get("basis_col") or "Endring").strip()
                if basis_col not in _BASIS_LABELS:
                    basis_col = "Endring"

                (
                    previous_mapping,
                    previous_mapping_path,
                    previous_mapping_year,
                ) = self._load_previous_year_mapping_cached(client, year)

                result_box["payload"] = {
                    "gl_df": gl_df,
                    "tb_path": tb_path,
                    "source_a07_df": source_a07_df,
                    "a07_df": a07_df,
                    "a07_path": a07_path,
                    "mapping": mapping,
                    "mapping_path": mapping_path,
                    "groups": groups,
                    "groups_path": groups_path,
                    "locks": locks,
                    "locks_path": locks_path,
                    "project_meta": project_meta,
                    "project_path": project_path,
                    "basis_col": basis_col,
                    "previous_mapping": previous_mapping,
                    "previous_mapping_path": previous_mapping_path,
                    "previous_mapping_year": previous_mapping_year,
                    "rulebook_path": self._resolve_rulebook_path_cached(client, year),
                    "pending_focus_code": str(project_meta.get("selected_code") or "").strip() or None,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07ContextRestore-{token}", daemon=True)
        self._restore_thread = thread
        self._restore_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_context_restore(token))

    def _poll_context_restore(self, token: int) -> None:
        if token != self._refresh_generation:
            self._diag(f"poll_context_restore stale token={token} active={self._refresh_generation}")
            self._restore_thread = None
            self._restore_result = None
            return
        thread = self._restore_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_context_restore(token))
            return
        result = self._restore_result or {}
        self._restore_thread = None
        self._restore_result = None
        error = result.get("error")
        if error is not None:
            self._diag(f"context_restore error token={token}: {error}")
            self._refresh_in_progress = False
            self._cancel_refresh_watchdog()
            self.status_var.set("A07-kontekst kunne ikke lastes.")
            self.details_var.set(str(error))
            if self._pending_session_refresh:
                self._pending_session_refresh = False
                self._schedule_session_refresh()
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            self._diag(f"context_restore complete token={token}")
            self._apply_context_restore_payload(payload)

    def _apply_context_restore_payload(self, payload: dict[str, object]) -> None:
        self.workspace.gl_df = payload["gl_df"]
        self.tb_path = payload["tb_path"]
        self.workspace.source_a07_df = payload["source_a07_df"]
        self.workspace.a07_df = payload["a07_df"]
        self.a07_path = payload["a07_path"]
        self.workspace.mapping = payload["mapping"]
        self.mapping_path = payload["mapping_path"]
        self.workspace.groups = payload["groups"]
        self.groups_path = payload["groups_path"]
        self.workspace.locks = payload["locks"]
        self.locks_path = payload["locks_path"]
        self.workspace.project_meta = payload["project_meta"]
        self.project_path = payload["project_path"]
        self.workspace.basis_col = payload["basis_col"]
        self.basis_var.set(_BASIS_LABELS[self.workspace.basis_col])
        self.previous_mapping = payload["previous_mapping"]
        self.previous_mapping_path = payload["previous_mapping_path"]
        self.previous_mapping_year = payload["previous_mapping_year"]
        self.effective_a07_mapping = None
        self.effective_previous_a07_mapping = None
        self.rulebook_path = payload["rulebook_path"]
        self._pending_focus_code = payload["pending_focus_code"]
        client, year = self._session_context(session)
        self._context_snapshot = self._current_context_snapshot(client, year)
        self._start_core_refresh()

    def _start_core_refresh(self) -> None:
        token = self._next_refresh_generation()
        self._diag(f"start_core_refresh token={token}")
        self._schedule_refresh_watchdog("core-refresh", token)
        client, year = self._session_context(session)
        source_a07_df = (
            self.workspace.source_a07_df.copy()
            if self.workspace.source_a07_df is not None
            else self.workspace.a07_df.copy()
        )
        gl_df = self.workspace.gl_df.copy()
        groups = copy.deepcopy(self.workspace.groups)
        mapping = dict(self.workspace.mapping)
        basis_col = str(self.workspace.basis_col or "Endring")
        locks = set(self.workspace.locks)
        previous_mapping = dict(self.previous_mapping)
        usage_df = getattr(session, "dataset", None)
        if isinstance(usage_df, pd.DataFrame):
            usage_df = usage_df.copy()
        else:
            usage_df = None
        previous_mapping_path = self.previous_mapping_path
        previous_mapping_year = self.previous_mapping_year
        rulebook_path = self.rulebook_path or resolve_rulebook_path(client, year)

        self.status_var.set("Oppdaterer A07...")
        self.details_var.set("Beregner kjernevisningene i bakgrunnen...")

        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                matcher_settings = load_matcher_settings()
                grouped_a07_df, membership = build_grouped_a07_df(source_a07_df, groups)
                effective_mapping = apply_groups_to_mapping(mapping, membership)
                effective_previous_mapping = apply_groups_to_mapping(previous_mapping, membership)
                usage_features = _build_usage_features_for_a07(usage_df)

                suggestions = _empty_suggestions_df()
                reconcile_df = _empty_reconcile_df()
                mapping_df = mapping_to_assigned_df(
                    mapping=effective_mapping,
                    gl_df=gl_df,
                    include_empty=False,
                    basis_col=basis_col,
                ).reset_index(drop=True)
                unmapped_df = _empty_unmapped_df()
                if not grouped_a07_df.empty and not gl_df.empty:
                    suggestions = suggest_mapping_candidates(
                        a07_df=grouped_a07_df,
                        gl_df=gl_df,
                        mapping_existing=effective_mapping,
                        config=build_suggest_config(
                            rulebook_path,
                            matcher_settings,
                            basis_col=basis_col,
                        ),
                        mapping_prior=effective_previous_mapping,
                        usage_features=usage_features,
                    ).reset_index(drop=True)
                    suggestions = decorate_suggestions_for_display(suggestions, gl_df).reset_index(drop=True)
                    reconcile_df = reconcile_a07_vs_gl(
                        a07_df=grouped_a07_df,
                        gl_df=gl_df,
                        mapping=effective_mapping,
                        basis_col=basis_col,
                    ).reset_index(drop=True)
                    unmapped_df = unmapped_accounts_df(
                        gl_df=gl_df,
                        mapping=effective_mapping,
                        basis_col=basis_col,
                    ).reset_index(drop=True)
                code_profile_state = _load_code_profile_state(client, year, effective_mapping, gl_df=gl_df)

                control_gl_df = build_control_gl_df(gl_df, effective_mapping).reset_index(drop=True)
                a07_overview_df = build_a07_overview_df(grouped_a07_df, reconcile_df)
                control_df = build_control_queue_df(
                    a07_overview_df,
                    suggestions,
                    mapping_current=effective_mapping,
                    mapping_previous=effective_previous_mapping,
                    gl_df=gl_df,
                    code_profile_state=code_profile_state,
                    locked_codes=locks,
                ).reset_index(drop=True)
                groups_df = build_groups_df(groups, locked_codes=locks).reset_index(drop=True)
                control_statement_base_df = build_control_statement_export_df(
                    client=client,
                    year=year,
                    gl_df=gl_df,
                    reconcile_df=reconcile_df,
                    mapping_current=effective_mapping,
                )
                control_statement_df = filter_control_statement_df(
                    control_statement_base_df,
                    view=CONTROL_STATEMENT_VIEW_PAYROLL,
                )

                result_box["payload"] = {
                    "rulebook_path": rulebook_path,
                    "matcher_settings": matcher_settings,
                    "previous_mapping": previous_mapping,
                    "previous_mapping_path": previous_mapping_path,
                    "previous_mapping_year": previous_mapping_year,
                    "effective_mapping": effective_mapping,
                    "effective_previous_mapping": effective_previous_mapping,
                    "grouped_a07_df": grouped_a07_df.reset_index(drop=True),
                    "membership": membership,
                    "suggestions": suggestions,
                    "reconcile_df": reconcile_df,
                    "mapping_df": mapping_df,
                    "unmapped_df": unmapped_df,
                    "control_gl_df": control_gl_df,
                    "a07_overview_df": a07_overview_df,
                    "control_df": control_df,
                    "groups_df": groups_df,
                    "control_statement_base_df": control_statement_base_df,
                    "control_statement_df": control_statement_df,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07CoreRefresh-{token}", daemon=True)
        self._core_refresh_thread = thread
        self._core_refresh_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_core_refresh(token))

    def _poll_core_refresh(self, token: int) -> None:
        if token != self._refresh_generation:
            self._diag(f"poll_core_refresh stale token={token} active={self._refresh_generation}")
            self._core_refresh_thread = None
            self._core_refresh_result = None
            return
        thread = self._core_refresh_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_core_refresh(token))
            return
        result = self._core_refresh_result or {}
        self._core_refresh_thread = None
        self._core_refresh_result = None
        error = result.get("error")
        if error is not None:
            self._diag(f"core_refresh error token={token}: {error}")
            self._refresh_in_progress = False
            self._cancel_refresh_watchdog()
            self.status_var.set("A07-oppdatering feilet.")
            self.details_var.set(str(error))
            if self._pending_session_refresh:
                self._pending_session_refresh = False
                self._schedule_session_refresh()
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            self._diag(f"core_refresh complete token={token}")
            self._apply_core_refresh_payload(payload)

    def _apply_core_refresh_payload(self, payload: dict[str, object]) -> None:
        self.rulebook_path = payload["rulebook_path"]
        self.matcher_settings = payload["matcher_settings"]
        self.previous_mapping = payload["previous_mapping"]
        self.previous_mapping_path = payload["previous_mapping_path"]
        self.previous_mapping_year = payload["previous_mapping_year"]
        self.effective_a07_mapping = dict(payload.get("effective_mapping") or {})
        self.effective_previous_a07_mapping = dict(payload.get("effective_previous_mapping") or {})
        self.workspace.a07_df = payload["grouped_a07_df"]
        self.workspace.membership = payload["membership"]
        self.workspace.suggestions = payload["suggestions"]
        self.reconcile_df = payload.get("reconcile_df", _empty_reconcile_df())
        self.mapping_df = payload.get("mapping_df", _empty_mapping_df())
        self.unmapped_df = payload.get("unmapped_df", _empty_unmapped_df())
        self.control_gl_df = payload["control_gl_df"]
        self.a07_overview_df = payload["a07_overview_df"]
        self.control_df = payload["control_df"]
        self.groups_df = payload["groups_df"]
        self.control_statement_base_df = payload.get(
            "control_statement_base_df",
            payload.get("control_statement_df", _empty_control_statement_df()),
        )
        current_control_statement_view = CONTROL_STATEMENT_VIEW_PAYROLL
        selected_control_statement_view = getattr(self, "_selected_control_statement_view", None)
        if callable(selected_control_statement_view):
            try:
                current_control_statement_view = selected_control_statement_view()
            except Exception:
                current_control_statement_view = CONTROL_STATEMENT_VIEW_PAYROLL
        if current_control_statement_view == CONTROL_STATEMENT_VIEW_PAYROLL:
            self.control_statement_df = payload.get(
                "control_statement_df",
                filter_control_statement_df(
                    self.control_statement_base_df,
                    view=CONTROL_STATEMENT_VIEW_PAYROLL,
                ),
            ).copy(deep=True)
        else:
            self.control_statement_df = self._build_current_control_statement_df(
                view=current_control_statement_view,
            )
        self.history_compare_df = _empty_history_df()
        self.control_statement_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])

        self.control_suggestion_summary_var.set("Velg A07-kode til hoyre for aa se beste forslag.")
        self.control_suggestion_effect_var.set("Velg et forslag for aa se hva som blir koblet.")
        self.control_accounts_summary_var.set("Velg A07-kode til hoyre for aa se hva som er koblet na.")
        statement_accounts_var = getattr(self, "control_statement_accounts_summary_var", None)
        if statement_accounts_var is not None:
            statement_accounts_var.set("Velg gruppe i kontrolloppstillingen for aa se kontoene bak raden.")
        summary_var = getattr(self, "control_statement_summary_var", None)
        if summary_var is not None:
            try:
                summary_var.set(
                    build_control_statement_overview(
                        self.control_statement_df,
                        basis_col=self.workspace.basis_col,
                    )
                )
            except Exception:
                pass
        self._support_views_ready = True
        self._support_views_dirty = False
        self._history_compare_ready = False
        self._loaded_support_tabs.clear()
        pending_focus_code = (self._pending_focus_code or "").strip()
        self._pending_focus_code = None

        def _sync_post_core_selection(target_code: str) -> None:
            self.workspace.selected_code = target_code or None
            self._update_history_details_from_selection()
            self._update_control_panel()
            self._update_control_transfer_buttons()

        def _finalize_core_refresh() -> None:
            diag = getattr(self, "_diag", lambda *_args, **_kwargs: None)
            cancel_watchdog = getattr(self, "_cancel_refresh_watchdog", lambda: None)
            try:
                diag("finalize_core_refresh start")
                tree_groups = getattr(self, "tree_groups", None)
                if tree_groups is not None:
                    self._fill_tree(tree_groups, self.groups_df, _GROUP_COLUMNS, iid_column="GroupId")
                sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
                if callable(sync_groups_panel_visibility):
                    sync_groups_panel_visibility()
                tree_control_suggestions = getattr(self, "tree_control_suggestions", None)
                if tree_control_suggestions is not None:
                    self._fill_tree(
                        tree_control_suggestions,
                        _empty_suggestions_df(),
                        _CONTROL_SUGGESTION_COLUMNS,
                    )
                tree_mapping = getattr(self, "tree_mapping", None)
                if tree_mapping is not None:
                    self._fill_tree(tree_mapping, self.mapping_df, _MAPPING_COLUMNS, iid_column="Konto")
                tree_control_accounts = getattr(self, "tree_control_accounts", None)
                if tree_control_accounts is not None:
                    self._fill_tree(
                        tree_control_accounts,
                        pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]),
                        _CONTROL_SELECTED_ACCOUNT_COLUMNS,
                        iid_column="Konto",
                    )
                tree_statement_accounts = getattr(self, "tree_control_statement_accounts", None)
                if tree_statement_accounts is not None:
                    self._fill_tree(
                        tree_statement_accounts,
                        pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]),
                        _CONTROL_SELECTED_ACCOUNT_COLUMNS,
                        iid_column="Konto",
                    )
                self._update_control_panel()
                self._update_control_transfer_buttons()
                self._update_summary()
                refresh_rf1022_window = getattr(self, "_refresh_rf1022_window", None)
                if callable(refresh_rf1022_window):
                    refresh_rf1022_window()
                refresh_control_statement_window = getattr(self, "_refresh_control_statement_window", None)
                if callable(refresh_control_statement_window):
                    refresh_control_statement_window()
                self.status_var.set("A07 oppdatert.")
                self.details_var.set("Velg konto og kode for aa jobbe videre. Historikk lastes ved behov.")
                try:
                    self._set_control_details_visible(True)
                except Exception:
                    pass

                target_code = ""
                try:
                    code_children = tuple(self.tree_a07.get_children())
                except Exception:
                    code_children = ()
                if code_children:
                    if pending_focus_code and pending_focus_code in code_children:
                        target_code = str(pending_focus_code)
                    else:
                        target_code = str(code_children[0])
                if target_code:
                    try:
                        self._set_tree_selection(self.tree_a07, target_code)
                    except Exception:
                        pass
                    try:
                        _sync_post_core_selection(target_code)
                        self._skip_initial_control_followup = False
                        if bool(getattr(self, "_control_details_visible", False)):
                            try:
                                self._refresh_control_support_trees()
                            except Exception:
                                pass
                            try:
                                active_tab = self._active_support_tab_key()
                            except Exception:
                                active_tab = None
                            if active_tab:
                                try:
                                    self._render_active_support_tab(force=True)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                self._pending_support_refresh = False
                if self._pending_session_refresh:
                    self._pending_session_refresh = False
                    if self._context_has_changed():
                        self._schedule_session_refresh()
                diag("finalize_core_refresh complete")
            except Exception as exc:
                diag(f"finalize_core_refresh error: {exc}")
                diag(traceback.format_exc())
                self.status_var.set("A07-oppdatering feilet i ferdigstilling.")
                self.details_var.set(str(exc))
            finally:
                self._refresh_in_progress = False
                cancel_watchdog()

        refresh_control_gl = getattr(self, "_refresh_control_gl_tree_chunked", None)
        refresh_a07 = getattr(self, "_refresh_a07_tree_chunked", None)
        if callable(refresh_control_gl) and callable(refresh_a07):
            refresh_control_gl(on_complete=lambda: refresh_a07(on_complete=_finalize_core_refresh))
            return
        self._refresh_control_gl_tree()
        self._refresh_a07_tree()
        _finalize_core_refresh()

    def _start_support_refresh(self) -> None:
        token = self._refresh_generation
        self._diag(f"start_support_refresh token={token}")
        gl_df = self.workspace.gl_df.copy()
        a07_df = self.workspace.a07_df.copy()
        effective_mapping = dict(self._effective_mapping())
        effective_previous_mapping = dict(self._effective_previous_mapping())

        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                history_compare_df = build_history_comparison_df(
                    a07_df,
                    gl_df,
                    mapping_current=effective_mapping,
                    mapping_previous=effective_previous_mapping,
                ).reset_index(drop=True)
                result_box["payload"] = {
                    "history_compare_df": history_compare_df,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07SupportRefresh-{token}", daemon=True)
        self._support_refresh_thread = thread
        self._support_refresh_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_support_refresh(token))

    def _poll_support_refresh(self, token: int) -> None:
        diag = getattr(self, "_diag", lambda *_args, **_kwargs: None)
        if token != self._refresh_generation:
            diag(f"poll_support_refresh stale token={token} active={self._refresh_generation}")
            self._support_refresh_thread = None
            self._support_refresh_result = None
            self._support_views_ready = False
            return
        thread = self._support_refresh_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_support_refresh(token))
            return
        result = self._support_refresh_result or {}
        self._support_refresh_thread = None
        self._support_refresh_result = None
        error = result.get("error")
        if error is not None:
            diag(f"support_refresh error token={token}: {error}")
            self._support_views_ready = False
            self.status_var.set("A07-stottevisninger feilet.")
            self.details_var.set(str(error))
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            diag(f"support_refresh complete token={token}")
            self._apply_support_refresh_payload(payload)

    def _apply_support_refresh_payload(self, payload: dict[str, object]) -> None:
        self.history_compare_df = payload["history_compare_df"]
        self._history_compare_ready = True

        self._support_views_ready = True
        self._support_views_dirty = False
        self._loaded_support_tabs.discard("history")

        def _apply_support_ui_updates() -> None:
            active_tab = self._active_support_tab_key()
            if bool(getattr(self, "_control_details_visible", False)):
                self._refresh_control_support_trees()
                if active_tab:
                    self._render_active_support_tab(force=True)
            self._update_history_details_from_selection()
            self._update_control_panel()
            self._update_control_transfer_buttons()
            self._update_summary()

        try:
            self.after_idle(_apply_support_ui_updates)
        except Exception:
            _apply_support_ui_updates()
