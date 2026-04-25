from __future__ import annotations

from .adapters import from_trial_balance
from .export import export_a07_workbook
from .groups import (
    A07Group,
    a07_code_aliases,
    a07_group_member_signature,
    apply_groups_to_mapping,
    build_grouped_a07_df,
    build_smart_a07_groups,
    canonical_a07_code,
    default_a07_groups,
    derive_groups_path,
    load_a07_groups,
    save_a07_groups,
)
from .parser import build_monthly_summary, parse_a07_json
from .reconcile import (
    mapping_to_assigned_df,
    reconcile_a07_vs_gl,
    unmapped_accounts_df,
)
from .suggest import (
    AccountUsageFeatures,
    ResidualAnalysis,
    ResidualChange,
    ResidualGroupScenario,
    SuggestConfig,
    SuggestionRow,
    UiSuggestionRow,
    analyze_a07_residuals,
    apply_suggestion_to_mapping,
    build_account_usage_features,
    clear_rulebook_cache,
    load_rulebook,
    score_usage_signal,
    select_batch_suggestions,
    select_best_suggestion_for_code,
    select_magic_wand_suggestions,
    suggest_mapping_candidates,
    suggest_mappings,
)
from .storage import load_mapping, save_mapping
from .storage import load_locks, load_project_state, save_locks, save_project_state
from .workspace import A07WorkspaceData


def load_a07_codes(path):
    return parse_a07_json(path)


def load_a07_monthly_summary(path):
    return build_monthly_summary(path)


__all__ = [
    "A07Group",
    "A07WorkspaceData",
    "AccountUsageFeatures",
    "ResidualAnalysis",
    "ResidualChange",
    "ResidualGroupScenario",
    "SuggestConfig",
    "SuggestionRow",
    "UiSuggestionRow",
    "a07_code_aliases",
    "analyze_a07_residuals",
    "a07_group_member_signature",
    "apply_groups_to_mapping",
    "apply_suggestion_to_mapping",
    "build_account_usage_features",
    "clear_rulebook_cache",
    "build_grouped_a07_df",
    "build_monthly_summary",
    "build_smart_a07_groups",
    "canonical_a07_code",
    "default_a07_groups",
    "derive_groups_path",
    "export_a07_workbook",
    "from_trial_balance",
    "load_a07_codes",
    "load_a07_groups",
    "load_a07_monthly_summary",
    "load_mapping",
    "load_locks",
    "load_project_state",
    "load_rulebook",
    "mapping_to_assigned_df",
    "parse_a07_json",
    "reconcile_a07_vs_gl",
    "save_a07_groups",
    "save_locks",
    "save_mapping",
    "save_project_state",
    "score_usage_signal",
    "select_batch_suggestions",
    "select_best_suggestion_for_code",
    "select_magic_wand_suggestions",
    "suggest_mapping_candidates",
    "suggest_mappings",
    "unmapped_accounts_df",
]
