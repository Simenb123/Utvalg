from __future__ import annotations

"""Compatibility re-export layer for legacy `page_a07` helpers.

Active A07 runtime modules should import from canonical `a07_feature.payroll`,
`a07_feature.control`, and `a07_feature.ui` modules directly. This module
stays broad on purpose so the public `page_a07` facade and older call sites can
continue to resolve the historical helper surface during the migration.
"""

from pathlib import Path

import app_paths
import classification_config
import classification_workspace
import pandas as pd
import session

from account_profile_legacy_api import AccountProfileLegacyApi
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
from a07_feature import mapping_source
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
    build_rf1022_candidate_df,
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
    filter_control_statement_df,
    filter_control_visible_codes_df,
    filter_suggestions_df,
    normalize_control_statement_view,
    reconcile_tree_tag,
    rf1022_post_for_group,
    rf1022_candidate_tree_tag,
    select_batch_suggestion_rows,
    select_magic_wand_suggestion_rows,
    suggestion_tree_tag,
    unresolved_codes,
)
from a07_feature.control.matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_control_suggestion_effect_summary,
    build_control_suggestion_summary,
    build_smartmapping_fallback,
    build_suggestion_reason_label,
    build_suggestion_status_label,
    compact_accounts,
    decorate_suggestions_for_display,
    preferred_support_tab_key,
    safe_previous_accounts_for_code,
    select_safe_history_codes,
    ui_suggestion_row_from_series,
)
from a07_feature.page_paths import (
    _path_signature,
    build_default_group_name,
    build_groups_df,
    build_rule_form_values,
    build_rule_payload,
    build_suggest_config,
    copy_a07_source_to_workspace,
    default_a07_export_path,
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    default_a07_source_path,
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
    resolve_autosave_mapping_path,
    resolve_context_mapping_path,
    resolve_context_source_path,
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
from a07_feature.payroll import classification as payroll_classification
from a07_feature.suggest.models import EXCLUDED_A07_CODES
from formatting import format_number_no
from trial_balance_reader import read_trial_balance

from . import page_a07_env as _env
from .page_a07_constants import *
from .page_a07_frames import *
from .page_a07_runtime_helpers import *
from .page_a07_dialogs import (
    _PickerOption,
    _count_nonempty_mapping,
    _editor_list_items,
    _filter_picker_options,
    _format_aliases_editor,
    _format_editor_list,
    _format_editor_ranges,
    _format_picker_amount,
    _format_special_add_editor,
    _numeric_decimals_for_column,
    _parse_aliases_editor,
    _parse_editor_ints,
    _parse_konto_tokens,
    _parse_special_add_editor,
    apply_manual_mapping_choice,
    apply_manual_mapping_choices,
    build_a07_picker_options,
    build_gl_picker_options,
    open_manual_mapping_dialog,
    remove_mapping_accounts,
)

app_paths = _env.app_paths
client_store = _env.client_store
filedialog = _env.filedialog
messagebox = _env.messagebox
simpledialog = _env.simpledialog
konto_klassifisering = _env.konto_klassifisering


def build_control_statement_summary(row, accounts_df, *, basis_col="Endring"):
    return a07_control_status.build_control_statement_summary(
        row,
        accounts_df,
        basis_col=basis_col,
        amount_formatter=_format_picker_amount,
    )


def build_control_statement_overview(
    control_statement_df,
    *,
    basis_col="Endring",
    selected_row=None,
):
    return a07_control_status.build_control_statement_overview(
        control_statement_df,
        basis_col=basis_col,
        selected_row=selected_row,
        amount_formatter=_format_picker_amount,
    )


def control_recommendation_label(*, has_history, best_suggestion):
    return a07_control_status.control_recommendation_label(
        has_history=has_history,
        best_suggestion=best_suggestion,
    )


def control_next_action_label(status, *, has_history, best_suggestion):
    return a07_control_status.control_next_action_label(
        status,
        has_history=has_history,
        best_suggestion=best_suggestion,
    )


def is_saldobalanse_follow_up_action(next_action):
    return a07_control_status.is_saldobalanse_follow_up_action(next_action)


def control_follow_up_guidance(next_action):
    return a07_control_status.control_follow_up_guidance(next_action)


def compact_control_next_action(next_action):
    return a07_control_status.compact_control_next_action(next_action)


def control_intro_text(work_label, *, has_history, best_suggestion):
    return a07_control_status.control_intro_text(
        work_label,
        has_history=has_history,
        best_suggestion=best_suggestion,
    )


def filter_control_queue_df(control_df, view_key):
    if control_df is None:
        return _empty_control_df()
    return a07_control_status.filter_control_queue_df(control_df, view_key)


build_control_bucket_summary = a07_control_status.build_control_bucket_summary
count_pending_control_items = a07_control_status.count_pending_control_items
control_tree_tag = a07_control_status.control_tree_tag
control_action_style = a07_control_status.control_action_style


__all__ = [name for name in globals() if not name.startswith("__")]
