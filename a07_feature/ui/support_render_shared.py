from __future__ import annotations

import pandas as pd
from tkinter import ttk

from ..control import status as a07_control_status
from ..control.data import (
    a07_suggestion_is_strict_auto,
    build_control_accounts_summary,
    build_rf1022_candidate_df,
    build_rf1022_candidate_df_for_groups,
    build_control_statement_accounts_df,
    build_mapping_history_details,
    build_mapping_review_summary,
    build_mapping_review_summary_text,
    RF1022_UNKNOWN_GROUP,
    filter_control_queue_by_rf1022_group,
    filter_control_visible_codes_df,
    filter_mapping_rows_by_audit_status,
    filter_suggestions_df,
    control_family_tree_tag,
    control_gl_family_tree_tag,
    rf1022_group_label,
    rf1022_candidate_tree_tag,
    next_mapping_review_problem_account,
    suggestion_tree_tag,
    unresolved_codes,
)
from ..control.matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_control_suggestion_effect_summary,
    build_control_suggestion_summary,
    safe_previous_accounts_for_code,
)
from ..control.presenter import build_control_panel_state
from ..page_a07_constants import (
    _CONTROL_COLUMNS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_SUGGESTION_COLUMNS,
    _MAPPING_FILTER_LABELS,
    _RF1022_CANDIDATE_COLUMNS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_COLUMNS,
    _UNMAPPED_COLUMNS,
    _SUGGESTION_COLUMNS,
)
from ..page_a07_env import session
from ..page_a07_frames import _empty_suggestions_df
from ..page_a07_runtime_helpers import default_global_rulebook_path
from ..page_paths import default_a07_source_path, suggest_default_mapping_path


def _page_safe_auto_matching_is_active(page: object) -> bool:
    try:
        return bool(getattr(page, "_safe_auto_matching_enabled", lambda: False)())
    except Exception:
        return False


def _batch_auto_button_text_for(page: object) -> str:
    return "Kjør trygg auto-matching" if _page_safe_auto_matching_is_active(page) else "Auto-matching av"

__all__ = [name for name in globals() if name not in {'__builtins__', '__cached__', '__doc__', '__file__', '__loader__', '__name__', '__package__', '__spec__', '__all__'}]
