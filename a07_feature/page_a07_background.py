from __future__ import annotations

import copy
import threading

import pandas as pd

from .page_a07_env import session
from .page_a07_refresh_apply import (
    apply_context_restore_payload,
    apply_core_refresh_payload,
    apply_support_refresh_payload,
)
from .page_a07_refresh_services import (
    build_context_restore_payload,
    build_core_refresh_payload,
    build_support_refresh_payload,
)
from .page_a07_runtime_helpers import _load_code_profile_state, resolve_rulebook_path
from .control.matching import best_suggestion_row_for_code, build_account_name_lookup


class A07PageBackgroundMixin:
    def _rebuild_a07_refresh_indexes(self) -> None:
        suggestions = getattr(getattr(self, "workspace", None), "suggestions", None)
        suggestions_by_code: dict[str, pd.DataFrame] = {}
        if isinstance(suggestions, pd.DataFrame) and not suggestions.empty and "Kode" in suggestions.columns:
            work = suggestions.copy()
            work["_code_key"] = work["Kode"].fillna("").astype(str).str.strip()
            suggestions_by_code = {
                str(code).strip(): group.drop(columns=["_code_key"], errors="ignore").copy()
                for code, group in work.groupby("_code_key", sort=False)
                if str(code).strip()
            }
        try:
            locked = set(self._locked_codes())
        except Exception:
            locked = set()
        best_by_code: dict[str, pd.Series] = {}
        for code, code_suggestions in suggestions_by_code.items():
            best = best_suggestion_row_for_code(code_suggestions, code, locked_codes=locked)
            if best is not None:
                best_by_code[code] = best

        def _accounts_by_code(mapping: object) -> dict[str, list[str]]:
            out: dict[str, set[str]] = {}
            if not isinstance(mapping, dict):
                return {}
            for account, code in mapping.items():
                account_s = str(account or "").strip()
                code_s = str(code or "").strip()
                if account_s and code_s:
                    out.setdefault(code_s, set()).add(account_s)
            return {
                code: sorted(accounts, key=lambda value: (len(value), value))
                for code, accounts in out.items()
            }

        current_mapping = getattr(self, "effective_a07_mapping", None)
        if not isinstance(current_mapping, dict):
            current_mapping = getattr(getattr(self, "workspace", None), "mapping", {}) or {}
        previous_mapping = getattr(self, "effective_previous_a07_mapping", None)
        if not isinstance(previous_mapping, dict):
            previous_mapping = getattr(self, "previous_mapping", {}) or {}
        gl_df = getattr(getattr(self, "workspace", None), "gl_df", pd.DataFrame())
        try:
            account_name_lookup = build_account_name_lookup(gl_df)
        except Exception:
            account_name_lookup = {}
        self._a07_refresh_indexes = {
            "suggestions_by_code": suggestions_by_code,
            "best_suggestion_by_code": best_by_code,
            "current_accounts_by_code": _accounts_by_code(current_mapping),
            "previous_accounts_by_code": _accounts_by_code(previous_mapping),
            "account_name_lookup": account_name_lookup,
        }

    def _auto_refresh_signature(self, auto_result: dict[str, object] | None = None) -> tuple[object, ...]:
        workspace = getattr(self, "workspace", None)
        mapping = getattr(workspace, "mapping", None)
        if not isinstance(mapping, dict):
            mapping = getattr(self, "effective_a07_mapping", {}) or {}
        mapping_items = tuple(
            sorted((str(account).strip(), str(code).strip()) for account, code in mapping.items())
        )
        result = auto_result if isinstance(auto_result, dict) else {}
        accounts = tuple(
            sorted({str(account).strip() for account in result.get("accounts", []) if str(account).strip()})
        )
        codes = tuple(
            sorted({str(code).strip() for code in result.get("codes", []) if str(code).strip()})
        )
        context_key = getattr(self, "_context_key", (None, None))
        if not isinstance(context_key, tuple):
            context_key = (str(context_key),)
        basis_col = str(getattr(workspace, "basis_col", "") or "").strip()
        focus_code = str(result.get("focus_code") or "").strip()
        return (context_key, basis_col, mapping_items, accounts, codes, focus_code)

    def _claim_auto_refresh_signature(self, signature: tuple[object, ...]) -> bool:
        seen = getattr(self, "_auto_refresh_signatures", None)
        if not isinstance(seen, set):
            seen = set()
            self._auto_refresh_signatures = seen
        if signature in seen:
            return False
        if len(seen) > 64:
            seen.clear()
        seen.add(signature)
        return True

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
        apply_context_restore_payload(self, payload)

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
        apply_core_refresh_payload(self, payload)

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
        apply_support_refresh_payload(self, payload)
