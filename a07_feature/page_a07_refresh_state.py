from __future__ import annotations

import pandas as pd
from pathlib import Path
from typing import Callable

from trial_balance_reader import read_trial_balance

from a07_feature import from_trial_balance, load_mapping, parse_a07_json

from .page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _BASIS_LABELS,
    _CONTROL_COLUMNS,
    _CONTROL_GL_COLUMNS,
    _CONTROL_GL_DATA_COLUMNS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_STATEMENT_VIEW_LABELS,
    _CONTROL_SUGGESTION_COLUMNS,
    _CONTROL_VIEW_LABELS,
    _CONTROL_WORK_LEVEL_LABELS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_COLUMNS,
    _RECONCILE_COLUMNS,
    _SUGGESTION_COLUMNS,
    _SUGGESTION_SCOPE_LABELS,
    _UNMAPPED_COLUMNS,
    control_statement_view_requires_unclassified,
)
from .page_a07_env import session
from .page_a07_frames import (
    _empty_a07_df,
    _empty_control_df,
    _empty_control_statement_df,
    _empty_gl_df,
    _empty_groups_df,
    _empty_history_df,
    _empty_mapping_df,
    _empty_reconcile_df,
    _empty_rf1022_overview_df,
    _empty_suggestions_df,
    _empty_unmapped_df,
)
from .page_a07_runtime_helpers import (
    _clean_context_value,
    load_previous_year_mapping_for_context,
    resolve_rulebook_path,
)
from .control.data import control_queue_tree_tag, filter_control_visible_codes_df
from .page_paths import (
    _path_signature,
    get_active_trial_balance_path_for_context,
    get_context_snapshot_with_paths,
)


class A07PageRefreshStateMixin:
    def _session_context(self, session_module=session) -> tuple[str | None, str | None]:
        client = _clean_context_value(getattr(session_module, "client", None))
        year = _clean_context_value(getattr(session_module, "year", None))
        if client and year:
            return client, year
        store_client, store_year = A07PageRefreshStateMixin._dataset_store_context(self)
        return client or store_client, year or store_year

    def _dataset_store_context(self) -> tuple[str | None, str | None]:
        try:
            host = self.winfo_toplevel()
        except Exception:
            return None, None
        try:
            page_dataset = getattr(host, "page_dataset", None)
            dp = getattr(page_dataset, "dp", None)
            if dp is None:
                dp = getattr(page_dataset, "dataset_pane", None)
            if dp is None:
                dp = getattr(page_dataset, "pane", None)
            sec = getattr(dp, "_store_section", None) if dp else None
            if sec is None:
                return None, None
            client_var = getattr(sec, "client_var", None)
            year_var = getattr(sec, "year_var", None)
            client = _clean_context_value(client_var.get()) if hasattr(client_var, "get") else None
            year = _clean_context_value(year_var.get()) if hasattr(year_var, "get") else None
            return client, year
        except Exception:
            return None, None

    def _active_tb_cache_key(
        self,
        client: str | None,
        year: str | int | None,
    ) -> tuple[str, str] | None:
        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        if not client_s or not year_s:
            return None
        return (client_s, year_s)

    def _invalidate_active_tb_path_cache(
        self,
        client: str | None = None,
        year: str | int | None = None,
    ) -> None:
        key = self._active_tb_cache_key(client, year)
        if key is None:
            self._active_tb_path_cache.clear()
            self._mapping_file_cache.clear()
            self._previous_mapping_cache.clear()
            self._rulebook_path_cache.clear()
            return
        self._active_tb_path_cache.pop(key, None)
        self._mapping_file_cache.clear()
        self._previous_mapping_cache.pop(key, None)
        self._rulebook_path_cache.pop(key, None)

    def _get_cached_gl_df_for_path(self, path: Path | None) -> pd.DataFrame:
        if path is None:
            return _empty_gl_df()
        signature = _path_signature(path)
        cached = self._gl_df_cache.get(signature)
        if cached is not None:
            return cached.copy(deep=True)
        tb_df = read_trial_balance(path)
        gl_df = from_trial_balance(tb_df)
        self._gl_df_cache[signature] = gl_df.copy(deep=True)
        return gl_df.copy(deep=True)

    def _load_a07_source_cached(self, path: Path | None) -> pd.DataFrame:
        if path is None:
            return _empty_a07_df()
        signature = _path_signature(path)
        cached = self._a07_source_cache.get(signature)
        if cached is not None:
            return cached.copy(deep=True)
        source_df = parse_a07_json(path)
        self._a07_source_cache[signature] = source_df.copy(deep=True)
        return source_df.copy(deep=True)

    def _load_mapping_file_cached(
        self,
        path: Path | None,
        *,
        client: str | None = None,
        year: str | int | None = None,
        prefer_profiles: bool = False,
    ) -> dict[str, str]:
        if path is None:
            return {}
        signature = _path_signature(path)
        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        cache_key = (signature, client_s, year_s)
        cached = self._mapping_file_cache.get(cache_key)
        if cached is not None:
            return dict(cached)
        mapping = load_mapping(path, client=client, year=year, prefer_profiles=prefer_profiles)
        self._mapping_file_cache[cache_key] = dict(mapping)
        return dict(mapping)

    def _load_previous_year_mapping_cached(
        self,
        client: str | None,
        year: str | int | None,
        *,
        refresh: bool = False,
    ) -> tuple[dict[str, str], Path | None, str | None]:
        key = self._active_tb_cache_key(client, year)
        if key is None:
            return {}, None, None
        if refresh:
            self._previous_mapping_cache.pop(key, None)
        cached = self._previous_mapping_cache.get(key)
        if cached is not None:
            mapping, path, prior_year = cached
            return dict(mapping), path, prior_year
        mapping, path, prior_year = load_previous_year_mapping_for_context(client, year)
        result = (dict(mapping), path, prior_year)
        self._previous_mapping_cache[key] = result
        return dict(mapping), path, prior_year

    def _resolve_rulebook_path_cached(
        self,
        client: str | None,
        year: str | int | None,
        *,
        refresh: bool = False,
    ) -> Path | None:
        key = self._active_tb_cache_key(client, year)
        if key is None:
            return resolve_rulebook_path(client, year)
        if refresh:
            self._rulebook_path_cache.pop(key, None)
        if key not in self._rulebook_path_cache:
            self._rulebook_path_cache[key] = resolve_rulebook_path(client, year)
        return self._rulebook_path_cache.get(key)

    def _get_cached_active_trial_balance_path(
        self,
        client: str | None,
        year: str | int | None,
        *,
        refresh: bool = False,
    ) -> Path | None:
        key = self._active_tb_cache_key(client, year)
        if key is None:
            return None
        if refresh:
            self._active_tb_path_cache.pop(key, None)
        if key not in self._active_tb_path_cache:
            self._active_tb_path_cache[key] = get_active_trial_balance_path_for_context(*key)
        return self._active_tb_path_cache.get(key)

    def _load_active_trial_balance_cached(
        self,
        client: str | None,
        year: str | int | None,
        *,
        refresh_path: bool = False,
    ) -> tuple[pd.DataFrame, Path | None]:
        path = self._get_cached_active_trial_balance_path(client, year, refresh=refresh_path)
        if path is None:
            tb_df = getattr(session, "tb_df", None)
            if isinstance(tb_df, pd.DataFrame) and not tb_df.empty:
                return from_trial_balance(tb_df), None
            return _empty_gl_df(), None
        try:
            path_exists = path.exists()
        except Exception:
            path_exists = False
        if not path_exists:
            self._invalidate_active_tb_path_cache(client, year)
            tb_df = getattr(session, "tb_df", None)
            if isinstance(tb_df, pd.DataFrame) and not tb_df.empty:
                return from_trial_balance(tb_df), None
            return _empty_gl_df(), None
        try:
            return self._get_cached_gl_df_for_path(path), path
        except Exception:
            tb_df = getattr(session, "tb_df", None)
            if isinstance(tb_df, pd.DataFrame) and not tb_df.empty:
                return from_trial_balance(tb_df), None
            return _empty_gl_df(), path

    def _current_context_snapshot(
        self,
        client: str | None,
        year: str | None,
    ) -> tuple[tuple[str | None, int | None, int | None], ...]:
        tb_candidate = self.tb_path
        if tb_candidate is None:
            tb_candidate = self._get_cached_active_trial_balance_path(client, year)
        return get_context_snapshot_with_paths(
            client,
            year,
            tb_path=tb_candidate,
            source_path=self.a07_path,
            mapping_path=self.mapping_path,
            groups_path=self.groups_path,
            locks_path=self.locks_path,
            project_path=self.project_path,
        )

    def reset_context_runtime_state(self, client: str | None, year: str | None) -> None:
        def _fill_optional_tree(
            attr_name: str,
            df: pd.DataFrame,
            columns: Sequence[tuple[str, str, int, str]],
            *,
            iid_column: str | None = None,
            row_tag_fn: Callable[[pd.Series], str | None] | None = None,
        ) -> None:
            tree = getattr(self, attr_name, None)
            if tree is None:
                return
            self._fill_tree(
                tree,
                df,
                columns,
                iid_column=iid_column,
                row_tag_fn=row_tag_fn,
            )

        self._refresh_in_progress = True
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        cancel_job = getattr(self, "_cancel_scheduled_job", None)
        if callable(cancel_job):
            cancel_job("_session_refresh_job")
        self._cancel_core_refresh_jobs()
        self._cancel_support_refresh()
        self._support_views_ready = False
        self._support_views_dirty = True
        self._history_compare_ready = False
        self._loaded_support_tabs.clear()
        try:
            self._loaded_support_context_keys.clear()
        except Exception:
            self._loaded_support_context_keys = {}
        self.workspace.a07_df = _empty_a07_df()
        self.workspace.source_a07_df = _empty_a07_df()
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.rf1022_overview_df = _empty_rf1022_overview_df()
        self.control_gl_df = pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.control_statement_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.groups_df = _empty_groups_df()
        self.workspace.mapping = {}
        self.workspace.groups = {}
        self.workspace.locks = set()
        self.effective_rulebook = None
        self.workspace.membership = {}
        self.workspace.project_meta = {}
        self.workspace.suggestions = _empty_suggestions_df()
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.mapping_audit_df = pd.DataFrame()
        self.mapping_review_df = pd.DataFrame()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.control_statement_base_df = _empty_control_statement_df()
        self.control_statement_df = _empty_control_statement_df()
        self.effective_a07_mapping = None
        self.effective_previous_a07_mapping = None
        self.a07_path = None
        self.mapping_path = None
        self.groups_path = None
        self.locks_path = None
        self.project_path = None
        self.rulebook_path = resolve_rulebook_path(client, year)
        self.previous_mapping = {}
        self.previous_mapping_path = None
        self.previous_mapping_year = None
        self.history_details_var.set("Velg en kode for aa se historikk.")
        self.control_summary_var.set("Velg A07-kode til hoyre.")
        self.control_intro_var.set("")
        self.control_meta_var.set("")
        self.control_match_var.set("")
        self.control_mapping_var.set("")
        self.control_history_var.set("")
        self.control_best_var.set("")
        self.control_suggestion_summary_var.set("Velg A07-kode til hoyre for aa se beste forslag.")
        self.control_suggestion_effect_var.set("Velg et forslag for aa se hva som blir koblet.")
        self.control_statement_summary_var.set("Ingen kontrollgrupper er klassifisert enn\u00e5.")
        self.control_statement_accounts_summary_var.set("Velg gruppe i kontrolloppstillingen for aa se kontoene bak raden.")
        self.control_next_var.set("")
        self.control_drag_var.set("")
        sync_control_panel_visibility = getattr(self, "_sync_control_panel_visibility", None)
        if callable(sync_control_panel_visibility):
            sync_control_panel_visibility()
        self.control_bucket_var.set("0 åpne")
        self.control_code_filter_var.set("")
        self._control_details_auto_revealed = False
        self._selected_rf1022_group_id = None
        try:
            self._set_control_details_visible(True)
        except Exception:
            pass
        try:
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        self.a07_filter_var.set("alle")
        self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
        try:
            self.a07_match_filter_var.set("alle")
        except Exception:
            pass
        self.basis_var.set(_BASIS_LABELS["Endring"])
        self.workspace.basis_col = "Endring"
        self.control_work_level_var.set("a07")
        self.control_work_level_label_var.set(_CONTROL_WORK_LEVEL_LABELS["a07"])
        self.control_statement_view_var.set(CONTROL_STATEMENT_VIEW_PAYROLL)
        self.control_statement_view_label_var.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        self.control_statement_include_unclassified_var.set(
            control_statement_view_requires_unclassified(CONTROL_STATEMENT_VIEW_PAYROLL)
        )
        self.suggestion_scope_var.set("valgt_kode")
        self.suggestion_scope_label_var.set(_SUGGESTION_SCOPE_LABELS["valgt_kode"])
        try:
            self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["alle"])
        except Exception:
            pass
        try:
            self.suggestion_scope_widget.set(_SUGGESTION_SCOPE_LABELS["valgt_kode"])
        except Exception:
            pass
        try:
            self.control_statement_view_widget.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        except Exception:
            pass
        try:
            self.control_work_level_widget.set(_CONTROL_WORK_LEVEL_LABELS["a07"])
        except Exception:
            pass
        _fill_optional_tree("tree_control_gl", self.control_gl_df, _CONTROL_GL_COLUMNS)
        _fill_optional_tree(
            "tree_a07",
            self.control_df,
            _CONTROL_COLUMNS,
            iid_column="Kode",
        )
        _fill_optional_tree("tree_groups", self.groups_df, _GROUP_COLUMNS, iid_column="GroupId")
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()
        _fill_optional_tree("tree_control_suggestions", _empty_suggestions_df(), _CONTROL_SUGGESTION_COLUMNS)
        _fill_optional_tree(
            "tree_control_accounts",
            pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]),
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )
        _fill_optional_tree(
            "tree_control_statement_accounts",
            pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]),
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )
        _fill_optional_tree("tree_history", _empty_history_df(), _HISTORY_COLUMNS, iid_column="Kode")
        _fill_optional_tree("tree_unmapped", _empty_unmapped_df(), _UNMAPPED_COLUMNS, iid_column="Konto")
        self._update_selected_suggestion_details()
        self._update_control_panel()
        self._update_control_transfer_buttons()
        self._update_summary()
        refresh_control_statement_window = getattr(self, "_refresh_control_statement_window", None)
        if callable(refresh_control_statement_window):
            refresh_control_statement_window()

    def _restore_context_state(self, client: str | None, year: str | None) -> None:
        self.reset_context_runtime_state(client, year)
        self._context_snapshot = self._current_context_snapshot(client, year)
        self._start_context_restore(client, year)
    def _sync_active_tb_clicked(self) -> None:
        ok = self._sync_active_trial_balance(refresh=True)
        if ok and self.tb_path is not None:
            self.status_var.set(f"Bruker aktiv saldobalanse fra {self.tb_path.name}.")
            return
        self._notify_inline(
            "Fant ingen aktiv saldobalanse for valgt klient/aar. Velg eller opprett den via Dataset -> Versjoner.",
            focus_widget=self,
        )

    def _sync_active_trial_balance(self, *, refresh: bool) -> bool:
        client, year = self._session_context(session)
        self.workspace.gl_df, self.tb_path = self._load_active_trial_balance_cached(
            client,
            year,
            refresh_path=refresh,
        )
        self._context_snapshot = self._current_context_snapshot(client, year)
        if refresh:
            self._refresh_core(reason="sync_active_tb")
        return not self.workspace.gl_df.empty

    def _context_has_changed(self) -> bool:
        context = self._session_context(session)
        snapshot = self._current_context_snapshot(*context)
        return context != self._context_key or snapshot != self._context_snapshot
