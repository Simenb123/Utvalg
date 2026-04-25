from __future__ import annotations

from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import app_paths
import pandas as pd
try:
    import client_store
except Exception:
    client_store = None
import session

from a07_feature import page_a07_env as _env
from a07_feature import page_a07_shared as _shared
from a07_feature import page_a07_background as _background
from a07_feature.control import statement_ui as _control_statement
from a07_feature import page_a07_methods as _methods
from a07_feature import page_a07_context as _context
from a07_feature import page_a07_context_core as _context_core
from a07_feature import page_a07_context_shared as _context_shared
from a07_feature import page_a07_dialogs as _dialogs
from a07_feature import page_a07_dialogs_editors as _dialogs_editors
from a07_feature import page_a07_dialogs_shared as _dialogs_shared
from a07_feature import page_a07_manual_mapping_dialog as _manual_mapping_dialog
from a07_feature import page_a07_mapping_actions as _mapping_actions
from a07_feature import page_a07_mapping_assign as _mapping_assign
from a07_feature import page_a07_mapping_batch as _mapping_batch
from a07_feature import page_a07_mapping_candidate_apply as _mapping_candidate_apply
from a07_feature import page_a07_mapping_candidates as _mapping_candidates
from a07_feature import page_a07_mapping_control_actions as _mapping_control_actions
from a07_feature import page_a07_mapping_learning as _mapping_learning
from a07_feature import page_a07_mapping_learning_accounts as _mapping_learning_accounts
from a07_feature import page_a07_mapping_learning_gl as _mapping_learning_gl
from a07_feature import page_a07_mapping_shared as _mapping_shared
from a07_feature import page_a07_navigation as _navigation
from a07_feature import page_a07_project_actions as _project_actions
from a07_feature import page_a07_project_io as _project_io
from a07_feature import page_a07_group_actions as _project_group_actions
from a07_feature import page_a07_project_tools as _project_tools
from a07_feature import page_a07_refresh as _refresh
from a07_feature import page_a07_refresh_services as _refresh_services
from a07_feature import page_a07_refresh_state as _refresh_state
from a07_feature import page_paths as _page_paths
from a07_feature import path_context as _path_context
from a07_feature import path_history as _path_history
from a07_feature import path_rulebook as _path_rulebook
from a07_feature import path_shared as _path_shared
from a07_feature import path_snapshots as _path_snapshots
from a07_feature import path_trial_balance as _path_trial_balance
from a07_feature import page_a07_runtime_helpers as _runtime_helpers
from a07_feature.ui import canonical_layout as _ui_canonical
from a07_feature.ui import drag_drop_helpers as _ui_drag_drop_helpers
from a07_feature.ui import focus_helpers as _ui_focus_helpers
from a07_feature.ui import helpers as _ui_helpers
from a07_feature.ui import manual_mapping_defaults as _ui_manual_mapping_defaults
from a07_feature.ui import page as _ui
from a07_feature.ui import render as _render
from a07_feature.ui import selection as _selection
from a07_feature.ui import selection_context as _selection_context
from a07_feature.ui import selection_controls as _selection_controls
from a07_feature.ui import selection_details as _selection_details
from a07_feature.ui import selection_events as _selection_events
from a07_feature.ui import selection_scope as _selection_scope
from a07_feature.ui import selection_shared as _selection_shared
from a07_feature.ui import selection_tree as _selection_tree
from a07_feature.ui import support_render as _support_render
from a07_feature.ui import support_filters as _support_filters
from a07_feature.ui import support_guidance as _support_guidance
from a07_feature.ui import support_panel as _support_panel
from a07_feature.ui import support_render_shared as _support_render_shared
from a07_feature.ui import support_suggestions as _support_suggestions
from a07_feature.ui import support_trees as _support_trees
from a07_feature.ui import tree_builders as _ui_tree_builders
from a07_feature.ui import tree_render as _tree_render
from a07_feature.ui import tree_selection_helpers as _ui_tree_selection_helpers
from a07_feature.ui import tree_sorting as _ui_tree_sorting
from a07_feature.page_a07_methods import A07PageMethodsMixin

from . import rf1022 as _rf1022

app_paths = app_paths
client_store = client_store
session = session
filedialog = filedialog
messagebox = messagebox
simpledialog = simpledialog
konto_klassifisering = _shared.konto_klassifisering
_A07_DIAGNOSTICS_ENABLED = _shared._A07_DIAGNOSTICS_ENABLED
_A07_DIAGNOSTICS_LOG = _shared._A07_DIAGNOSTICS_LOG
_CONTROL_GL_DATA_COLUMNS = _shared._CONTROL_GL_DATA_COLUMNS
_CONTROL_SELECTED_ACCOUNT_COLUMNS = _shared._CONTROL_SELECTED_ACCOUNT_COLUMNS
_CONTROL_DRAG_IDLE_HINT = _shared._CONTROL_DRAG_IDLE_HINT
_CONTROL_VIEW_LABELS = _shared._CONTROL_VIEW_LABELS
_CONTROL_WORK_LEVEL_LABELS = _shared._CONTROL_WORK_LEVEL_LABELS
_CONTROL_GL_SCOPE_LABELS = _shared._CONTROL_GL_SCOPE_LABELS
_CONTROL_GL_MAPPING_LABELS = _shared._CONTROL_GL_MAPPING_LABELS
_CONTROL_GL_SERIES_LABELS = _shared._CONTROL_GL_SERIES_LABELS
_A07_MATCH_FILTER_LABELS = _shared._A07_MATCH_FILTER_LABELS
_MAPPING_FILTER_LABELS = _shared._MAPPING_FILTER_LABELS
_CONTROL_ALTERNATIVE_MODE_LABELS = _shared._CONTROL_ALTERNATIVE_MODE_LABELS
_CONTROL_STATEMENT_VIEW_LABELS = _shared._CONTROL_STATEMENT_VIEW_LABELS
_SUGGESTION_SCOPE_LABELS = _shared._SUGGESTION_SCOPE_LABELS
_BASIS_LABELS = _shared._BASIS_LABELS
CONTROL_STATEMENT_VIEW_ALL = _shared.CONTROL_STATEMENT_VIEW_ALL
CONTROL_STATEMENT_VIEW_PAYROLL = _shared.CONTROL_STATEMENT_VIEW_PAYROLL
CONTROL_STATEMENT_VIEW_LEGACY = _shared.CONTROL_STATEMENT_VIEW_LEGACY
CONTROL_STATEMENT_VIEW_UNCLASSIFIED = _shared.CONTROL_STATEMENT_VIEW_UNCLASSIFIED
control_statement_view_requires_unclassified = _shared.control_statement_view_requires_unclassified


def _sync_shared_refs() -> None:
    _env.set_runtime_refs(
        app_paths_ref=app_paths,
        client_store_ref=client_store,
        session_ref=session,
        filedialog_ref=filedialog,
        messagebox_ref=messagebox,
        simpledialog_ref=simpledialog,
        konto_klassifisering_ref=konto_klassifisering,
    )
    target_modules = (
        _env,
        _shared,
        _background,
        _control_statement,
        _methods,
        _ui,
        _ui_helpers,
        _ui_canonical,
        _ui_tree_builders,
        _ui_tree_sorting,
        _ui_tree_selection_helpers,
        _ui_manual_mapping_defaults,
        _ui_focus_helpers,
        _ui_drag_drop_helpers,
        _context,
        _context_core,
        _context_shared,
        _dialogs,
        _dialogs_editors,
        _dialogs_shared,
        _manual_mapping_dialog,
        _refresh,
        _refresh_services,
        _refresh_state,
        _page_paths,
        _path_context,
        _path_history,
        _path_rulebook,
        _path_shared,
        _path_snapshots,
        _path_trial_balance,
        _render,
        _support_render,
        _support_filters,
        _support_guidance,
        _support_panel,
        _support_render_shared,
        _support_suggestions,
        _support_trees,
        _tree_render,
        _selection,
        _selection_context,
        _selection_controls,
        _selection_details,
        _selection_events,
        _selection_scope,
        _selection_shared,
        _selection_tree,
        _runtime_helpers,
        _mapping_actions,
        _mapping_assign,
        _mapping_batch,
        _mapping_candidate_apply,
        _mapping_candidates,
        _mapping_control_actions,
        _mapping_learning,
        _mapping_learning_accounts,
        _mapping_learning_gl,
        _mapping_shared,
        _navigation,
        _project_actions,
        _project_io,
        _project_group_actions,
        _project_tools,
        _rf1022,
    )
    for module in target_modules:
        if hasattr(module, "app_paths"):
            module.app_paths = app_paths
        if hasattr(module, "client_store"):
            module.client_store = client_store
        if hasattr(module, "session"):
            module.session = session
        if hasattr(module, "filedialog"):
            module.filedialog = filedialog
        if hasattr(module, "messagebox"):
            module.messagebox = messagebox
        if hasattr(module, "simpledialog"):
            module.simpledialog = simpledialog
        if hasattr(module, "konto_klassifisering"):
            module.konto_klassifisering = konto_klassifisering
    for name in _FORWARD_NAMES:
        if name in globals():
            value = globals()[name]
            for module in target_modules:
                setattr(module, name, value)


_PUBLIC_HELPER_NAMES = (
    "A07Group",
    "AccountProfileLegacyApi",
    "AccountUsageFeatures",
    "A07WorkspaceData",
    "SuggestConfig",
    "EXCLUDED_A07_CODES",
    "a07_code_rf1022_group",
    "build_a07_overview_df",
    "build_control_accounts_summary",
    "build_control_gl_df",
    "build_control_queue_df",
    "build_control_selected_account_df",
    "build_control_statement_accounts_df",
    "build_control_statement_export_df",
    "build_control_statement_overview",
    "build_control_statement_summary",
    "build_global_auto_mapping_plan",
    "build_mapping_audit_df",
    "build_mapping_review_df",
    "build_mapping_review_summary",
    "build_mapping_review_summary_text",
    "build_rf1022_candidate_df",
    "build_control_bucket_summary",
    "build_control_suggestion_effect_summary",
    "build_control_suggestion_summary",
    "build_default_group_name",
    "build_gl_picker_options",
    "build_a07_picker_options",
    "build_history_comparison_df",
    "build_mapping_history_details",
    "build_rf1022_accounts_df",
    "build_rf1022_statement_df",
    "build_rf1022_statement_summary",
    "build_source_overview_rows",
    "build_suggest_config",
    "build_rule_payload",
    "compact_control_next_action",
    "control_action_style",
    "control_gl_tree_tag",
    "control_intro_text",
    "control_next_action_label",
    "control_queue_tree_tag",
    "control_recommendation_label",
    "control_tree_tag",
    "count_pending_control_items",
    "count_unsolved_a07_codes",
    "copy_a07_source_to_workspace",
    "copy_rulebook_to_storage",
    "decorate_suggestions_for_display",
    "default_a07_export_path",
    "default_a07_groups_path",
    "default_a07_locks_path",
    "default_a07_project_path",
    "default_a07_source_path",
    "bundled_default_rulebook_path",
    "filter_a07_overview_df",
    "filter_control_gl_df",
    "filter_control_queue_df",
    "filter_control_visible_codes_df",
    "filter_mapping_rows_by_audit_status",
    "filter_suggestions_df",
    "find_previous_year_context",
    "find_previous_year_mapping_path",
    "get_a07_workspace_dir",
    "get_active_trial_balance_path_for_context",
    "get_context_snapshot",
    "legacy_global_a07_mapping_path",
    "legacy_global_a07_source_path",
    "load_active_trial_balance_for_context",
    "load_a07_groups",
    "load_locks",
    "load_matcher_settings",
    "load_previous_year_mapping_for_context",
    "normalize_matcher_settings",
    "next_mapping_review_problem_account",
    "open_manual_mapping_dialog",
    "parse_a07_json",
    "reconcile_tree_tag",
    "remove_mapping_accounts",
    "resolve_autosave_mapping_path",
    "resolve_context_mapping_path",
    "resolve_context_source_path",
    "resolve_rulebook_path",
    "rf1022_post_for_group",
    "rf1022_candidate_tree_tag",
    "rf1022_overview_tree_tag",
    "safe_previous_accounts_for_code",
    "select_batch_suggestion_rows",
    "select_magic_wand_suggestion_rows",
    "select_safe_history_codes",
    "sort_mapping_rows_by_audit_status",
    "suggest_default_mapping_path",
    "suggestion_tree_tag",
    "control_gl_family_tree_tag",
    "ui_suggestion_row_from_series",
    "unresolved_codes",
    "best_suggestion_row_for_code",
    "a07_suggestion_is_strict_auto",
    "apply_mapping_audit_to_control_gl_df",
    "apply_mapping_audit_to_mapping_df",
    "_build_usage_features_for_a07",
    "_empty_a07_df",
    "_empty_control_df",
    "_empty_gl_df",
    "_empty_groups_df",
    "_empty_history_df",
    "_empty_mapping_df",
    "_empty_reconcile_df",
    "_empty_rf1022_accounts_df",
    "_empty_rf1022_overview_df",
    "_empty_suggestions_df",
    "_empty_unmapped_df",
    "_empty_control_statement_df",
    "_format_aliases_editor",
    "_parse_aliases_editor",
    "_format_picker_amount",
    "_load_code_profile_state",
    "_account_profile_api_for_a07",
    "apply_manual_mapping_choice",
    "apply_manual_mapping_choices",
)

_WRAP_NAMES = [name for name in _PUBLIC_HELPER_NAMES if hasattr(_shared, name)]

_FORWARD_NAMES = {
    "konto_klassifisering",
    "_account_profile_api_for_a07",
    "bundled_default_rulebook_path",
    "copy_a07_source_to_workspace",
    "copy_rulebook_to_storage",
    "default_a07_groups_path",
    "default_a07_locks_path",
    "default_a07_source_path",
    "find_previous_year_context",
    "find_previous_year_mapping_path",
    "get_a07_workspace_dir",
    "get_active_trial_balance_path_for_context",
    "get_context_snapshot",
    "load_a07_groups",
    "load_locks",
    "load_previous_year_mapping_for_context",
    "resolve_autosave_mapping_path",
    "resolve_context_source_path",
    "resolve_rulebook_path",
    "suggest_default_mapping_path",
}
_SHARED_ORIGINALS = {name: getattr(_shared, name) for name in _WRAP_NAMES}


def _make_wrapper(name: str):
    def _wrapped(*args, **kwargs):
        _sync_shared_refs()
        return _SHARED_ORIGINALS[name](*args, **kwargs)
    _wrapped.__name__ = name
    _wrapped.__qualname__ = name
    return _wrapped


for _name in _WRAP_NAMES:
    globals()[_name] = _make_wrapper(_name)

_sync_shared_refs()


class A07Page(A07PageMethodsMixin, ttk.Frame):
    def __init__(self, parent: tk.Misc, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        self.workspace = A07WorkspaceData(
            a07_df=_empty_a07_df(),
            gl_df=_empty_gl_df(),
            source_a07_df=_empty_a07_df(),
            mapping={},
            suggestions=None,
        )
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.rf1022_overview_df = _empty_rf1022_overview_df()
        self.control_gl_df = pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.control_statement_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.groups_df = _empty_groups_df()
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.mapping_audit_df = pd.DataFrame()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.previous_mapping: dict[str, str] = {}
        self.effective_a07_mapping: dict[str, str] | None = None
        self.effective_previous_a07_mapping: dict[str, str] | None = None
        self.matcher_settings = load_matcher_settings()
        self.effective_rulebook = None
        self._a07_refresh_indexes: dict[str, object] = {}

        self.a07_path: Path | None = None
        self.tb_path: Path | None = None
        self.mapping_path: Path | None = None
        self.groups_path: Path | None = None
        self.locks_path: Path | None = None
        self.project_path: Path | None = None
        self.rulebook_path: Path | None = None
        self.previous_mapping_path: Path | None = None
        self.previous_mapping_year: str | None = None
        self._context_key: tuple[str | None, str | None] = (None, None)
        self._context_snapshot = get_context_snapshot(None, None)
        self._active_tb_path_cache: dict[tuple[str, str], Path | None] = {}
        self._gl_df_cache: dict[
            tuple[str | None, int | None, int | None],
            pd.DataFrame,
        ] = {}
        self._a07_source_cache: dict[
            tuple[str | None, int | None, int | None],
            pd.DataFrame,
        ] = {}
        self._mapping_file_cache: dict[
            tuple[tuple[str | None, int | None, int | None], str | None, str | None],
            dict[str, str],
        ] = {}
        self._previous_mapping_cache: dict[
            tuple[str, str],
            tuple[dict[str, str], Path | None, str | None],
        ] = {}
        self._rulebook_path_cache: dict[tuple[str, str], Path | None] = {}
        self._matcher_admin_window: tk.Toplevel | None = None
        self._matcher_admin_state: dict[str, object] | None = None
        self._source_overview_window: tk.Toplevel | None = None
        self._control_statement_window: tk.Toplevel | None = None
        self._control_statement_window_state: dict[str, object] | None = None
        self._rf1022_state: dict[str, object] | None = None
        self._drag_unmapped_account: str | None = None
        self._drag_control_accounts: list[str] = []
        self._control_details_auto_revealed = False
        self._session_refresh_job: str | None = None
        self._support_refresh_job: str | None = None
        self._support_render_job: str | None = None
        self._auto_refresh_signatures: set[tuple[object, ...]] = set()
        self._focus_control_code_attempts: dict[str, int] = {}
        self._refresh_in_progress = False
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._a07_refresh_warnings: list[dict[str, str]] = []
        self._support_views_ready = False
        self._support_views_dirty = True
        self._history_compare_ready = False
        self._support_requested = False
        self._refresh_generation = 0
        self._restore_thread: threading.Thread | None = None
        self._restore_result: dict[str, object] | None = None
        self._core_refresh_thread: threading.Thread | None = None
        self._core_refresh_result: dict[str, object] | None = None
        self._support_refresh_thread: threading.Thread | None = None
        self._support_refresh_result: dict[str, object] | None = None
        self._loaded_support_tabs: set[str] = set()
        self._loaded_support_context_keys: dict[str, tuple[object, ...]] = {}
        self._pending_focus_code: str | None = None
        self._suspend_selection_sync = False
        self._suppressed_tree_select_keys: set[str] = set()
        self._tree_fill_jobs: dict[str, str] = {}
        self._tree_fill_tokens: dict[str, int] = {}
        self._control_gl_refresh_job: str | None = None
        self._a07_refresh_job: str | None = None
        self._control_selection_followup_job: str | None = None
        self._skip_initial_control_followup = False
        self._refresh_watchdog_job: str | None = None
        self._control_details_restore_sashpos: int | None = None
        self._control_advanced_visible = False
        self._selected_rf1022_group_id: str | None = None

        self.summary_var = tk.StringVar(value="Ingen A07-data lastet ennÃ¥.")
        self.status_var = tk.StringVar(value="Last A07 JSON for å starte.")
        self.details_var = tk.StringVar(value="Bruk Kilder... for filoversikt.")
        self.a07_path_var = tk.StringVar(value="A07: ikke valgt")
        self.tb_path_var = tk.StringVar(value="Saldobalanse: ingen aktiv SB-versjon")
        self.mapping_path_var = tk.StringVar(value="Mapping: ikke valgt")
        self.rulebook_path_var = tk.StringVar(value="Rulebook: standard heuristikk")
        self.history_path_var = tk.StringVar(value="Historikk: ingen tidligere A07-mapping")
        self.suggestion_details_var = tk.StringVar(value="Velg et forslag for å se hvorfor det passer og hva som blir koblet.")
        self.control_suggestion_summary_var = tk.StringVar(value="Velg A07-kode til høyre for å se beste forslag.")
        self.control_suggestion_effect_var = tk.StringVar(value="Velg et forslag for å se hva som blir koblet.")
        self.history_details_var = tk.StringVar(value="Velg en kode for å se historikk.")
        self.control_summary_var = tk.StringVar(value="Velg A07-kode til høyre.")
        self.control_intro_var = tk.StringVar(value="")
        self.control_meta_var = tk.StringVar(value="")
        self.control_match_var = tk.StringVar(value="")
        self.control_mapping_var = tk.StringVar(value="")
        self.control_history_var = tk.StringVar(value="")
        self.control_best_var = tk.StringVar(value="")
        self.control_next_var = tk.StringVar(value="")
        self.control_accounts_summary_var = tk.StringVar(value="Velg A07-kode til høyre for å se hva som er koblet nå.")
        self.control_statement_summary_var = tk.StringVar(value="Ingen kontrollgrupper er klassifisert enn\u00e5.")
        self.control_statement_accounts_summary_var = tk.StringVar(
            value="Velg gruppe i kontrolloppstillingen for å se kontoene bak raden."
        )
        self.control_drag_var = tk.StringVar(value=_CONTROL_DRAG_IDLE_HINT)
        self.control_bucket_var = tk.StringVar(value="0 åpne")
        self.basis_var = tk.StringVar(value=_BASIS_LABELS["Endring"])
        self.control_work_level_var = tk.StringVar(value="a07")
        self.control_work_level_label_var = tk.StringVar(value=_CONTROL_WORK_LEVEL_LABELS["a07"])
        self.a07_filter_var = tk.StringVar(value="alle")
        self.a07_filter_label_var = tk.StringVar(value=_CONTROL_VIEW_LABELS["alle"])
        self.a07_match_filter_var = tk.StringVar(value="alle")
        self.control_code_filter_var = tk.StringVar(value="")
        self.control_gl_filter_var = tk.StringVar(value="")
        self.control_gl_scope_var = tk.StringVar(value="alle")
        self.control_gl_scope_label_var = tk.StringVar(value=_CONTROL_GL_SCOPE_LABELS["alle"])
        self.control_gl_mapping_filter_var = tk.StringVar(value="alle")
        self.control_gl_mapping_filter_label_var = tk.StringVar(value=_CONTROL_GL_MAPPING_LABELS["alle"])
        self.control_gl_series_filter_var = tk.StringVar(value="alle")
        self.control_gl_series_filter_label_var = tk.StringVar(value=_CONTROL_GL_SERIES_LABELS["alle"])
        self.control_gl_series_vars = [tk.IntVar(value=0) for _ in range(10)]
        self.mapping_filter_var = tk.StringVar(value="alle")
        self.mapping_filter_label_var = tk.StringVar(value=_MAPPING_FILTER_LABELS["alle"])
        self._mapping_filter_user_selected = False
        self.control_gl_active_only_var = tk.BooleanVar(value=True)
        self.control_gl_unmapped_only_var = tk.BooleanVar(value=False)
        self.control_alternative_mode_var = tk.StringVar(value="suggestions")
        self.control_alternative_mode_label_var = tk.StringVar(value=_CONTROL_ALTERNATIVE_MODE_LABELS["suggestions"])
        self.control_alternative_summary_var = tk.StringVar(value="Velg A07-kode til høyre for å se alternativer.")
        self.control_statement_view_var = tk.StringVar(value=CONTROL_STATEMENT_VIEW_PAYROLL)
        self.control_statement_view_label_var = tk.StringVar(
            value=_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL]
        )
        self.control_statement_include_unclassified_var = tk.BooleanVar(
            value=control_statement_view_requires_unclassified(CONTROL_STATEMENT_VIEW_PAYROLL)
        )
        self.suggestion_scope_var = tk.StringVar(value="valgt_kode")
        self.suggestion_scope_label_var = tk.StringVar(value=_SUGGESTION_SCOPE_LABELS["valgt_kode"])

        if _A07_DIAGNOSTICS_ENABLED:
            try:
                _A07_DIAGNOSTICS_LOG.write_text("", encoding="utf-8")
            except Exception:
                pass
        self._build_ui()
        self.bind("<Visibility>", self._on_visible, add="+")
        try:
            parent.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed, add="+")
        except Exception:
            pass
        self._diag("init complete")
        self._schedule_session_refresh()


    # Methods that rely on monkeypatched module globals stay as thin wrappers here.
    def _load_active_trial_balance_cached(self, client, year, *, refresh_path=False):
        _sync_shared_refs()
        return A07PageMethodsMixin._load_active_trial_balance_cached(self, client, year, refresh_path=refresh_path)

    def _sync_active_tb_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._sync_active_tb_clicked(self)

    def _load_a07_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._load_a07_clicked(self)

    def _load_mapping_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._load_mapping_clicked(self)

    def _save_mapping_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._save_mapping_clicked(self)

    def _rename_selected_group(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._rename_selected_group(self)

    def _export_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._export_clicked(self)

    def _load_rulebook_clicked(self):
        _sync_shared_refs()
        return A07PageMethodsMixin._load_rulebook_clicked(self)


__all__ = [
    "A07Page",
    *_WRAP_NAMES,
    "app_paths",
    "client_store",
    "session",
    "filedialog",
    "messagebox",
    "simpledialog",
]
