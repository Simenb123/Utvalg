from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from .. import select_batch_suggestions, select_magic_wand_suggestions
from . import status as a07_control_status
from .data import (
    EXCLUDED_A07_CODES,
    RF1022_UNKNOWN_GROUP,
    _CONTROL_COLUMNS,
    _CONTROL_EXTRA_COLUMNS,
    _CONTROL_GL_DATA_COLUMNS,
    _CONTROL_HIDDEN_CODES,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _HISTORY_COLUMNS,
    _empty_a07_df,
    _empty_control_df,
    _empty_history_df,
    _empty_suggestions_df,
    _format_aga_pliktig,
    _format_amount,
    _gl_accounts,
    _optional_bool,
    _rulebook_aga_pliktig,
    a07_code_rf1022_group,
    control_gl_basis_column_for_account,
    work_family_for_a07_code,
    work_family_for_rf1022_group,
)
from .matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_account_name_lookup,
    decorate_suggestions_for_display,
    evaluate_current_mapping_suspicion,
    safe_previous_accounts_for_code,
    ui_suggestion_row_from_series,
)
from .rf1022_bridge import rf1022_group_a07_codes

def _load_effective_rulebook(rulebook: object | None) -> object:
    if rulebook is not None:
        return rulebook
    try:
        from . import data as control_data

        return control_data.load_rulebook(None)
    except Exception:
        return {}

def _evaluate_alias_status(code: object, name: object, effective_rulebook: object) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return ""
    try:
        from . import data as control_data

        return str(control_data.evaluate_a07_rule_name_status(code_s, name, effective_rulebook) or "").strip()
    except Exception:
        return ""


__all__ = [name for name in globals() if name not in {"__builtins__", "__cached__", "__doc__", "__file__", "__loader__", "__name__", "__package__", "__spec__", "__all__"}]

