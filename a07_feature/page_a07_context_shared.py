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

__all__ = [name for name in globals() if name not in {'__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__', '__all__'}]
