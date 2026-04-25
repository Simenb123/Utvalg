from __future__ import annotations

from a07_feature.suggest.api import AccountUsageFeatures
from a07_feature.suggest.rulebook import RulebookRule
from account_profile import (
    AccountClassificationCatalog,
    AccountClassificationCatalogEntry,
    AccountProfile,
    AccountProfileDocument,
    AccountProfileSuggestion,
)

from .classification_a07_engine import _direct_hint_code, _score_rule_match, suggest_a07_code
from .classification_audit import (
    confidence_label,
    profile_source_label,
    rf1022_tag_totals,
    strict_auto_profile_updates,
    suspicious_saved_payroll_profile_issue,
)
from .classification_catalog import (
    _catalog_entry_exclude_terms,
    _catalog_entry_terms,
    _direct_catalog_exclude_hits,
    _direct_catalog_signals,
    _fallback_group_entries,
    _fallback_tag_entries,
    _format_direct_reason,
    _payroll_group_entries,
    _payroll_tag_entries,
    _suggest_control_group_from_catalog,
    _suggest_control_tags_from_catalog,
    _usage_signal_text,
    control_group_for_code,
    detect_rf1022_exclude_blocks,
    format_control_group,
    format_control_tags,
    payroll_group_options,
    payroll_tag_options,
    required_control_tags_for_code,
)
from .classification_engine import _iter_account_rows, build_payroll_suggestion_map, classify_payroll_account
from .classification_guardrails import (
    _a07_suggestion_allowed_for_account,
    _has_payroll_profile_state,
    _heuristic_allowed_for_account,
    is_actionable_payroll_suggestion,
    is_strict_auto_suggestion,
    payroll_relevant_for_account,
)
from .classification_shared import (
    PAYROLL_CODE_DEFAULTS,
    PAYROLL_GROUP_IDS,
    PAYROLL_RF1022_GROUPS,
    PAYROLL_TAG_IDS,
    PAYROLL_TAG_LABELS,
    PayrollSuggestionResult,
    _DIRECT_HINT_SCORES,
    _DIRECT_NAME_HINTS,
    _account_no_int,
    _clean_text,
    _code_tokens_for_rule,
    _default_rulebook,
    _has_non_payroll_operating_expense_signal,
    _has_strong_expense_payroll_signal,
    _in_allowed_ranges,
    _matching_terms,
    _normalize_text,
    _normalize_text_shared,
    _normalized_phrase_match,
    _sign,
    _to_number,
    invalidate_runtime_caches,
)

__all__ = [name for name in globals() if not name.startswith('__')]
