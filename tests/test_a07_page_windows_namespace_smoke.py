from __future__ import annotations

import importlib


def test_page_windows_facade_points_to_split_window_modules() -> None:
    facade = importlib.import_module("a07_feature.page_windows")
    source = importlib.import_module("a07_feature.page_windows_source")
    mapping = importlib.import_module("a07_feature.page_windows_mapping")
    matcher = importlib.import_module("a07_feature.page_windows_matcher_admin")

    assert facade.build_source_overview_rows is source.build_source_overview_rows
    assert facade.open_source_overview is source.open_source_overview
    assert facade.open_mapping_overview is mapping.open_mapping_overview
    assert facade.open_matcher_admin is matcher.open_matcher_admin
