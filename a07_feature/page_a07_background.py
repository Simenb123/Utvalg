from __future__ import annotations

import copy
import threading
import traceback

import pandas as pd

from .page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _BASIS_LABELS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_SUGGESTION_COLUMNS,
    _GROUP_COLUMNS,
    _MAPPING_COLUMNS,
)
from .page_a07_env import session
from .page_a07_frames import (
    _empty_control_statement_df,
    _empty_history_df,
    _empty_mapping_df,
    _empty_reconcile_df,
    _empty_rf1022_overview_df,
    _empty_suggestions_df,
    _empty_unmapped_df,
)
from .page_a07_refresh_services import (
    build_context_restore_payload,
    build_core_refresh_payload,
    build_support_refresh_payload,
)
from .page_a07_runtime_helpers import _load_code_profile_state, resolve_rulebook_path
from .page_a07_dialogs import _format_picker_amount
from .control import status as a07_control_status
from .control.data import filter_control_statement_df, preferred_rf1022_overview_group


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
                result_box["payload"] = build_context_restore_payload(
                    client=client,
                    year=year,
                    load_active_trial_balance_cached=self._load_active_trial_balance_cached,
                    load_a07_source_cached=self._load_a07_source_cached,
                    load_mapping_file_cached=self._load_mapping_file_cached,
                    load_previous_year_mapping_cached=self._load_previous_year_mapping_cached,
                    resolve_rulebook_path_cached=self._resolve_rulebook_path_cached,
                )
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
                result_box["payload"] = build_core_refresh_payload(
                    client=client,
                    year=year,
                    source_a07_df=source_a07_df,
                    gl_df=gl_df,
                    groups=groups,
                    mapping=mapping,
                    basis_col=basis_col,
                    locks=locks,
                    previous_mapping=previous_mapping,
                    usage_df=usage_df,
                    previous_mapping_path=previous_mapping_path,
                    previous_mapping_year=previous_mapping_year,
                    rulebook_path=rulebook_path,
                    load_code_profile_state=_load_code_profile_state,
                )
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
        self.effective_rulebook = payload.get("effective_rulebook")
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
        self.mapping_audit_df = payload.get("mapping_audit_df", pd.DataFrame())
        self.mapping_review_df = payload.get("mapping_review_df", pd.DataFrame())
        self.unmapped_df = payload.get("unmapped_df", _empty_unmapped_df())
        self.control_gl_df = payload["control_gl_df"]
        self.a07_overview_df = payload["a07_overview_df"]
        self.control_df = payload["control_df"]
        self.rf1022_overview_df = payload.get("rf1022_overview_df", _empty_rf1022_overview_df())
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
                    a07_control_status.build_control_statement_overview(
                        self.control_statement_df,
                        basis_col=self.workspace.basis_col,
                        amount_formatter=_format_picker_amount,
                    )
                )
            except Exception:
                pass
        self._support_views_ready = True
        self._support_views_dirty = False
        self._history_compare_ready = False
        self._loaded_support_tabs.clear()
        try:
            self._loaded_support_context_keys.clear()
        except Exception:
            self._loaded_support_context_keys = {}
        pending_focus_code = (self._pending_focus_code or "").strip()
        self._pending_focus_code = None
        selected_group_id = str(getattr(self, "_selected_rf1022_group_id", "") or "").strip()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "rf1022"
        except Exception:
            work_level = "rf1022"

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
                    self._support_requested = True
                except Exception:
                    pass

                target_group = ""
                target_code = ""
                try:
                    code_children = tuple(self.tree_a07.get_children())
                except Exception:
                    code_children = ()
                if work_level == "rf1022":
                    if code_children:
                        if selected_group_id and selected_group_id in code_children:
                            target_group = str(selected_group_id)
                        else:
                            target_group = str(
                                preferred_rf1022_overview_group(
                                    getattr(self, "rf1022_overview_df", None),
                                    code_children,
                                )
                                or code_children[0]
                            )
                else:
                    if code_children:
                        if pending_focus_code and pending_focus_code in code_children:
                            target_code = str(pending_focus_code)
                        else:
                            target_code = str(code_children[0])
                if target_group:
                    try:
                        self._set_tree_selection(self.tree_a07, target_group)
                    except Exception:
                        pass
                    try:
                        self._selected_rf1022_group_id = target_group
                        focus_code = pending_focus_code
                        if not focus_code:
                            selected_code_getter = getattr(self, "_selected_control_code", None)
                            if callable(selected_code_getter):
                                try:
                                    focus_code = str(selected_code_getter() or "").strip()
                                except Exception:
                                    focus_code = ""
                        _sync_post_core_selection(focus_code)
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
                elif target_code:
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
                result_box["payload"] = build_support_refresh_payload(
                    a07_df=a07_df,
                    gl_df=gl_df,
                    effective_mapping=effective_mapping,
                    effective_previous_mapping=effective_previous_mapping,
                )
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
        try:
            self._loaded_support_context_keys.pop("history", None)
        except Exception:
            pass

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
