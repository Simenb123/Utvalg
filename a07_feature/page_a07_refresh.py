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
from .page_a07_refresh_state import A07PageRefreshStateMixin

class A07PageRefreshMixin(A07PageRefreshStateMixin):
    def _diag(self, message: str) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        try:
            stamp = time.strftime("%H:%M:%S")
            millis = int((time.time() % 1) * 1000)
            with _A07_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}.{millis:03d}] {message}\n")
        except Exception:
            pass

    def _tree_debug_name(self, tree: ttk.Treeview | None) -> str:
        if tree is None:
            return "<none>"
        try:
            return str(tree.winfo_name() or tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _cancel_refresh_watchdog(self) -> None:
        job = getattr(self, "_refresh_watchdog_job", None)
        if not job:
            return
        if isinstance(job, str):
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._refresh_watchdog_job = None

    def _schedule_refresh_watchdog(self, label: str, token: int) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        self._cancel_refresh_watchdog()

        def _thread_watchdog() -> None:
            time.sleep(2.0)
            if not bool(getattr(self, "_refresh_in_progress", False)):
                return
            active_token = int(getattr(self, "_refresh_generation", 0))
            if active_token != int(token):
                return
            try:
                with _A07_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as handle:
                    stamp = time.strftime("%H:%M:%S")
                    millis = int((time.time() % 1) * 1000)
                    handle.write(
                        f"[{stamp}.{millis:03d}] watchdog {label} token={token} "
                        f"active_token={active_token} "
                        f"pending_session={self._pending_session_refresh} "
                        f"pending_support={self._pending_support_refresh} "
                        f"support_ready={self._support_views_ready} "
                        f"support_dirty={self._support_views_dirty} "
                        f"support_requested={getattr(self, '_support_requested', None)} "
                        f"restore_alive={bool(self._restore_thread and self._restore_thread.is_alive())} "
                        f"core_alive={bool(self._core_refresh_thread and self._core_refresh_thread.is_alive())} "
                        f"support_alive={bool(self._support_refresh_thread and self._support_refresh_thread.is_alive())}\n"
                    )
                    handle.write(f"[{stamp}.{millis:03d}] watchdog-stack {label} token={token}\n")
                    faulthandler.dump_traceback(file=handle, all_threads=True)
                    handle.write("\n")
            except Exception:
                try:
                    stack_dump = ""
                    current_frames = sys._current_frames()
                    thread_frames: list[str] = []
                    for thread in threading.enumerate():
                        ident = getattr(thread, "ident", None)
                        if ident is None:
                            continue
                        frame = current_frames.get(ident)
                        if frame is None:
                            continue
                        rendered = "".join(traceback.format_stack(frame, limit=20))
                        thread_frames.append(
                            f"--- thread={thread.name} ident={ident} alive={thread.is_alive()} ---\n{rendered}"
                        )
                    stack_dump = "\n".join(thread_frames).strip()
                    if stack_dump:
                        self._diag(f"watchdog-stack-fallback {label} token={token}\n{stack_dump}")
                except Exception:
                    pass

        thread = threading.Thread(
            target=_thread_watchdog,
            name=f"A07Watchdog-{label}-{token}",
            daemon=True,
        )
        self._refresh_watchdog_job = thread
        thread.start()

    def refresh_from_session(self, session_module=session) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        context = self._session_context(session_module)
        if context != self._context_key:
            self._context_key = context
            self._restore_context_state(*context)
            return
        snapshot = self._current_context_snapshot(*context)
        if snapshot != self._context_snapshot:
            self._context_snapshot = snapshot
            self._restore_context_state(*context)
            return
        self._update_summary()

    def _schedule_session_refresh(self, delay_ms: int = 1) -> None:
        if self._session_refresh_job is not None:
            try:
                self.after_cancel(self._session_refresh_job)
            except Exception:
                pass
            self._session_refresh_job = None

        def _run() -> None:
            self._session_refresh_job = None
            self.refresh_from_session()

        try:
            self._session_refresh_job = self.after(delay_ms, _run)
        except Exception:
            self.refresh_from_session()

    def _cancel_scheduled_job(self, attr_name: str) -> None:
        job = getattr(self, attr_name, None)
        if not job:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass
        setattr(self, attr_name, None)

    def _schedule_control_gl_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_control_gl_refresh_job")

        def _run() -> None:
            self._control_gl_refresh_job = None
            self._refresh_control_gl_tree_chunked(on_complete=on_complete)

        try:
            self._control_gl_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_a07_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_a07_refresh_job")

        def _run() -> None:
            self._a07_refresh_job = None
            self._refresh_a07_tree_chunked(on_complete=on_complete)

        try:
            self._a07_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_control_selection_followup(self) -> None:
        self._cancel_scheduled_job("_control_selection_followup_job")

        def _run() -> None:
            self._control_selection_followup_job = None
            if bool(getattr(self, "_skip_initial_control_followup", False)):
                self._skip_initial_control_followup = False
                self._diag("skip initial control selection followup")
                self._update_control_transfer_buttons()
                return
            support_requested = bool(getattr(self, "_support_requested", True))
            active_tab = self._active_support_tab_key()
            if (
                bool(getattr(self, "_control_details_visible", False))
                and support_requested
                and self._support_views_ready
                and active_tab == "suggestions"
            ):
                self._refresh_suggestions_tree()
            if bool(getattr(self, "_control_details_visible", False)) and support_requested:
                if active_tab == "history" and not bool(getattr(self, "_history_compare_ready", False)):
                    self._schedule_support_refresh()
                elif self._support_views_ready:
                    self._refresh_control_support_trees()
                else:
                    self._schedule_support_refresh()
            self._update_control_transfer_buttons()

        try:
            self._control_selection_followup_job = self.after(40, _run)
        except Exception:
            _run()

    def _cancel_support_refresh(self) -> None:
        if self._support_refresh_job is None:
            return
        try:
            self.after_cancel(self._support_refresh_job)
        except Exception:
            pass
        self._support_refresh_job = None

    def _schedule_support_refresh(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if (
            self._active_support_tab_key() != "history"
            or bool(getattr(self, "_history_compare_ready", False))
        ):
            if self._support_views_ready and not self._support_views_dirty:
                self._render_active_support_tab(force=True)
            return
        self._cancel_support_refresh()

        def _run() -> None:
            self._support_refresh_job = None
            self._refresh_support_views()

        try:
            self._support_refresh_job = self.after(60, _run)
        except Exception:
            self._refresh_support_views()

    def _cancel_core_refresh_jobs(self) -> None:
        for attr_name in (
            "_session_refresh_job",
            "_control_gl_refresh_job",
            "_a07_refresh_job",
            "_control_selection_followup_job",
        ):
            self._cancel_scheduled_job(attr_name)

        for tree_name in ("tree_control_gl", "tree_a07"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            try:
                self._cancel_tree_fill(tree)
            except Exception:
                pass
            key = self._tree_fill_key(tree)
            try:
                self._tree_fill_tokens[key] = int(self._tree_fill_tokens.get(key, 0)) + 1
            except Exception:
                pass

    def _next_refresh_generation(self) -> int:
        self._refresh_generation += 1
        return self._refresh_generation

    def _on_visible(self, _event: tk.Event | None = None) -> None:
        try:
            if _event is not None and getattr(_event, "widget", None) is not self:
                return
        except Exception:
            pass
        try:
            if not self.winfo_viewable():
                return
        except Exception:
            pass
        if self._refresh_in_progress:
            return
        try:
            if not self._context_has_changed():
                return
        except Exception:
            pass
        self._schedule_session_refresh(delay_ms=50)

    def _on_notebook_tab_changed(self, event: tk.Event | None = None) -> None:
        if event is None:
            return
        try:
            notebook = event.widget
            selected = notebook.nametowidget(notebook.select())
        except Exception:
            return
        if selected is self:
            if self._refresh_in_progress:
                return
            try:
                if not self._context_has_changed():
                    return
            except Exception:
                pass
            self._schedule_session_refresh(delay_ms=50)

    def _refresh_context(self, *, refresh_tb: bool = False) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        client, year = self._session_context(session)
        if refresh_tb:
            self._invalidate_active_tb_path_cache(client, year)
        self._context_key = (client, year)
        self._restore_context_state(client, year)

    def _refresh_core(self, *, focus_code: str | None = None, reason: str | None = None) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            if focus_code:
                self._pending_focus_code = str(focus_code).strip() or None
            if reason:
                self._diag(f"refresh_core deferred reason={reason}")
            return
        if focus_code:
            self._pending_focus_code = str(focus_code).strip() or None
        if reason:
            self._diag(f"refresh_core reason={reason}")
        self._refresh_in_progress = True
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_requested = False
        cancel_job = getattr(self, "_cancel_scheduled_job", None)
        if callable(cancel_job):
            cancel_job("_session_refresh_job")
        self._cancel_core_refresh_jobs()
        self._cancel_support_refresh()
        self._support_views_ready = False
        self._start_core_refresh()

    def _refresh_support(self) -> None:
        self._schedule_support_refresh()

    def _refresh_clicked(self) -> None:
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du oppdaterer.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og sÃƒÂ¸rg for at valgt klient/aar har en aktiv saldobalanse i Utvalg.",
            )
            return

        try:
            selected_code = self._selected_control_code()
            self._pending_focus_code = str(selected_code or "").strip() or None
            refresh_context = getattr(self, "_refresh_context", None)
            if callable(refresh_context):
                refresh_context(refresh_tb=True)
            else:
                self._refresh_all()
            self.status_var.set("A07-kontroll og forslag er oppdatert.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-visningen:\n{exc}")

    def _refresh_all(self) -> None:
        refresh_core = getattr(self, "_refresh_core", None)
        if callable(refresh_core):
            refresh_core()
            return

        cancel_core_refresh_jobs = getattr(self, "_cancel_core_refresh_jobs", None)
        if callable(cancel_core_refresh_jobs):
            cancel_core_refresh_jobs()
        cancel_support_refresh = getattr(self, "_cancel_support_refresh", None)
        if callable(cancel_support_refresh):
            cancel_support_refresh()
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_views_ready = False
        self._refresh_in_progress = True
        start_core_refresh = getattr(self, "_start_core_refresh", None)
        if callable(start_core_refresh):
            start_core_refresh()

    def _refresh_support_views(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        loaded_tabs = getattr(self, "_loaded_support_tabs", set())
        active_tab = active_tab_getter() if callable(active_tab_getter) else None
        history_ready = bool(getattr(self, "_history_compare_ready", False))
        if self._support_views_ready and not self._support_views_dirty:
            if active_tab == "history" and not history_ready:
                if self._support_refresh_thread is not None:
                    return
                self._pending_support_refresh = False
                self._start_support_refresh()
                return
            if not callable(active_tab_getter) or active_tab in loaded_tabs:
                self._render_active_support_tab()
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if self._support_refresh_thread is not None:
            return
        self._pending_support_refresh = False
        self._start_support_refresh()

