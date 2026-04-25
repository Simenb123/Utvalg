from __future__ import annotations

import importlib


def test_mapping_audit_facade_points_to_split_modules() -> None:
    facade = importlib.import_module("a07_feature.control.mapping_audit")
    rules = importlib.import_module("a07_feature.control.mapping_audit_rules")
    status = importlib.import_module("a07_feature.control.mapping_audit_status")
    review = importlib.import_module("a07_feature.control.mapping_review")
    projection = importlib.import_module("a07_feature.control.mapping_audit_projection")

    assert callable(facade.build_mapping_audit_df)
    assert callable(facade.sort_mapping_rows_by_audit_status)
    assert callable(facade.filter_mapping_rows_by_audit_status)
    assert callable(facade.build_mapping_review_df)
    assert callable(facade.build_mapping_review_summary)
    assert callable(facade.next_mapping_review_problem_account)
    assert callable(facade.apply_mapping_audit_to_control_gl_df)
    assert callable(rules.build_mapping_audit_df)
    assert callable(status.sort_mapping_rows_by_audit_status)
    assert callable(review.build_mapping_review_df)
    assert callable(projection.apply_mapping_audit_to_control_gl_df)
