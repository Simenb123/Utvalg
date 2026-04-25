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
from a07_feature.control import status as a07_control_status
from a07_feature.control.data import (
    a07_code_rf1022_group,
    a07_suggestion_is_strict_auto,
    build_a07_overview_df,
    build_control_accounts_summary,
    build_control_gl_df,
    build_control_queue_df,
    build_control_selected_account_df,
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    build_global_auto_mapping_plan,
    build_history_comparison_df,
    build_mapping_history_details,
    build_rf1022_accounts_df,
    build_rf1022_candidate_df,
    build_rf1022_candidate_df_for_groups,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
    control_gl_tree_tag,
    control_queue_tree_tag,
    filter_a07_overview_df,
    filter_control_gl_df,
    filter_control_search_df,
    filter_control_queue_by_rf1022_group,
    filter_control_visible_codes_df,
    filter_suggestions_for_rf1022_group,
    filter_suggestions_df,
    reconcile_tree_tag,
    rf1022_group_a07_codes,
    rf1022_group_label,
    rf1022_post_for_group,
    RF1022_UNKNOWN_GROUP,
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
    safe_previous_accounts_for_code,
    select_safe_history_codes,
    ui_suggestion_row_from_series,
)
from a07_feature.rule_learning import append_a07_rule_keywords
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

from .page_a07_dialogs import (
    apply_manual_mapping_choice,
    apply_manual_mapping_choices,
    build_a07_picker_options,
    build_gl_picker_options,
    open_manual_mapping_dialog,
    remove_mapping_accounts,
)
from .page_a07_env import messagebox
from .page_a07_frames import _empty_suggestions_df

_RF1022_GROUP_DEFAULT_CODES: dict[str, str] = {
    "100_loenn_ol": "annet",
    "100_refusjon": "sumAvgiftsgrunnlagRefusjon",
    "111_naturalytelser": "elektroniskKommunikasjon",
    "112_pensjon": "tilskuddOgPremieTilPensjon",
}

_RF1022_GROUP_NAME_HINTS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "100_loenn_ol": (
        (("overtid",), "overtidsgodtgjoerelse"),
        (("time", "timelonn", "timelÃ¸nn"), "timeloenn"),
        (("trekk", "ferie"), "trekkloennForFerie"),
        (("ferie", "feriepenger"), "feriepenger"),
        (("styre", "honorar", "verv"), "styrehonorarOgGodtgjoerelseVerv"),
        (("lonn", "lÃ¸nn", "bonus", "etterlonn", "etterlÃ¸nn"), "fastloenn"),
    ),
    "111_naturalytelser": (
        (("telefon", "mobil", "ekom", "elektron"), "elektroniskKommunikasjon"),
        (("forsik", "gruppeliv", "ulykke"), "skattepliktigDelForsikringer"),
    ),
}


def _split_mapping_accounts(value: object) -> set[str]:
    raw = str(value or "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _locked_codes_for(page: object) -> set[str]:
    getter = getattr(page, "_locked_codes", None)
    if callable(getter):
        try:
            return {str(code).strip() for code in getter() if str(code).strip()}
        except Exception:
            pass
    workspace = getattr(page, "workspace", None)
    locked = getattr(workspace, "locks", None) or ()
    return {str(code).strip() for code in locked if str(code).strip()}


def _locked_mapping_conflicts_for(
    page: object,
    accounts: Sequence[object] | None = None,
    *,
    target_code: object | None = None,
) -> list[str]:
    getter = getattr(page, "_locked_mapping_conflicts", None)
    if callable(getter):
        try:
            return getter(accounts, target_code=target_code)
        except Exception:
            pass

    locked = _locked_codes_for(page)
    if not locked:
        return []

    workspace = getattr(page, "workspace", None)
    mapping = getattr(workspace, "mapping", None) or {}
    membership = getattr(workspace, "membership", None) or {}
    effective_mapping_getter = getattr(page, "_effective_mapping", None)
    if callable(effective_mapping_getter):
        try:
            effective_mapping = effective_mapping_getter()
        except Exception:
            effective_mapping = dict(mapping)
    else:
        effective_mapping = dict(mapping)

    conflicts: list[str] = []
    target_code_s = str(target_code or "").strip()
    if target_code_s and target_code_s in locked:
        conflicts.append(target_code_s)
    target_group_code = str(membership.get(target_code_s) or "").strip()
    if target_group_code and target_group_code in locked and target_group_code not in conflicts:
        conflicts.append(target_group_code)
    for account in accounts or ():
        account_s = str(account or "").strip()
        if not account_s:
            continue
        current_code = str(effective_mapping.get(account_s) or mapping.get(account_s) or "").strip()
        if current_code and current_code in locked and current_code not in conflicts:
            conflicts.append(current_code)
    return conflicts


def _notify_locked_conflicts_for(
    page: object,
    conflicts: Sequence[object],
    *,
    focus_widget: object | None = None,
) -> bool:
    notifier = getattr(page, "_notify_locked_conflicts", None)
    if callable(notifier):
        try:
            return bool(notifier(conflicts, focus_widget=focus_widget))
        except Exception:
            pass

    codes = [str(code).strip() for code in conflicts if str(code).strip()]
    if not codes:
        return False
    preview = ", ".join(codes[:3])
    if len(codes) > 3:
        preview += ", ..."
    notify_inline = getattr(page, "_notify_inline", None)
    if callable(notify_inline):
        notify_inline(
            f"Endringen berorer laaste koder: {preview}. Laas opp for du endrer mapping.",
            focus_widget=focus_widget,
        )
        return True
    return False

__all__ = [name for name in globals() if name not in {'__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__', '__all__'}]
