from __future__ import annotations

import importlib


def test_suggest_engine_split_modules_and_facades_are_importable() -> None:
    root_pkg = importlib.import_module("a07_feature")
    suggest_pkg = importlib.import_module("a07_feature.suggest")
    api = importlib.import_module("a07_feature.suggest.api")
    engine = importlib.import_module("a07_feature.suggest.engine")
    solver = importlib.import_module("a07_feature.suggest.solver")
    solver_prepare = importlib.import_module("a07_feature.suggest.solver_prepare")
    solver_code = importlib.import_module("a07_feature.suggest.solver_code")
    explain = importlib.import_module("a07_feature.suggest.explain")
    rule_lookup = importlib.import_module("a07_feature.suggest.rule_lookup")
    special_add = importlib.import_module("a07_feature.suggest.special_add")

    assert root_pkg.suggest_mappings is solver.suggest_mappings
    assert suggest_pkg.suggest_mappings is solver.suggest_mappings
    assert api.suggest_mappings is solver.suggest_mappings
    assert engine.suggest_mappings is solver.suggest_mappings
    assert engine._build_explain_text is explain._build_explain_text
    assert engine._lookup_rule is rule_lookup._lookup_rule
    assert engine._effective_target_value is rule_lookup._effective_target_value
    assert engine._a07_group_members is rule_lookup._a07_group_members
    assert engine._special_add_total is special_add._special_add_total
    assert engine._special_add_ranges is special_add._special_add_ranges
    assert engine._special_add_matches_row is special_add._special_add_matches_row
    assert engine._special_add_details is special_add._special_add_details
    assert callable(solver_prepare.build_engine_context)
    assert callable(solver_code.build_code_suggestion_rows)
