from __future__ import annotations

import importlib


def test_matching_submodules_and_facades_are_importable() -> None:
    compat_matching = importlib.import_module("a07_feature.control_matching")
    pkg_matching = importlib.import_module("a07_feature.control.matching")
    pkg_matching_display = importlib.import_module("a07_feature.control.matching_display")
    pkg_matching_guardrails = importlib.import_module("a07_feature.control.matching_guardrails")
    pkg_matching_history = importlib.import_module("a07_feature.control.matching_history")
    pkg_matching_shared = importlib.import_module("a07_feature.control.matching_shared")

    assert compat_matching.best_suggestion_row_for_code is pkg_matching.best_suggestion_row_for_code
    assert pkg_matching.best_suggestion_row_for_code is pkg_matching_display.best_suggestion_row_for_code
    assert pkg_matching.decorate_suggestions_for_display is pkg_matching_guardrails.decorate_suggestions_for_display
    assert pkg_matching.evaluate_current_mapping_suspicion is pkg_matching_guardrails.evaluate_current_mapping_suspicion
    assert pkg_matching.safe_previous_accounts_for_code is pkg_matching_history.safe_previous_accounts_for_code
    assert pkg_matching.select_safe_history_codes is pkg_matching_history.select_safe_history_codes
    assert pkg_matching.build_account_name_lookup is pkg_matching_shared.build_account_name_lookup
    assert pkg_matching.infer_semantic_family is pkg_matching_shared.infer_semantic_family
