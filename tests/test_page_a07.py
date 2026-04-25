from __future__ import annotations

import importlib

import page_a07


def test_page_a07_split_suite_smoke_imports() -> None:
    modules = [
        'tests.a07.test_paths_and_storage',
        'tests.a07.test_overview_and_history_engine',
        'tests.a07.test_control_queue_engine',
        'tests.a07.test_tree_and_labels',
        'tests.a07.test_refresh_and_apply',
        'tests.a07.test_support_refresh',
        'tests.a07.test_support_render',
        'tests.a07.test_context_and_selection',
        'tests.a07.test_focus_and_navigation',
        'tests.a07.test_mapping_actions',
        'tests.a07.test_rf1022_runtime',
        'tests.a07.test_rf1022_statement_engine',
        'tests.a07.test_manual_mapping_and_learning',
        'tests.a07.test_facade_and_compat',
    ]
    for module_name in modules:
        importlib.import_module(module_name)


def test_page_a07_facade_still_exposes_public_entrypoint() -> None:
    assert hasattr(page_a07, 'A07Page')
    assert callable(page_a07._sync_shared_refs)
