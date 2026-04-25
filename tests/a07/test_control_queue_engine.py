from __future__ import annotations

import importlib


def test_control_queue_split_modules_are_importable() -> None:
    modules = [
        "tests.a07.test_mapping_audit_review",
        "tests.a07.test_global_auto_plan",
        "tests.a07.test_control_queue_data",
        "tests.a07.test_control_gl_data",
        "tests.a07.test_control_filters",
        "tests.a07.test_mapping_action_guardrails",
    ]
    for module_name in modules:
        importlib.import_module(module_name)
