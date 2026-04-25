from __future__ import annotations

import importlib


def test_project_actions_split_modules_and_sync_refs_are_importable() -> None:
    facade = importlib.import_module("a07_feature.page_a07_project_actions")
    io = importlib.import_module("a07_feature.page_a07_project_io")
    groups = importlib.import_module("a07_feature.page_a07_group_actions")
    tools = importlib.import_module("a07_feature.page_a07_project_tools")
    page_a07 = importlib.import_module("page_a07")

    assert issubclass(facade.A07PageProjectActionsMixin, io.A07PageProjectIoMixin)
    assert issubclass(facade.A07PageProjectActionsMixin, groups.A07PageGroupActionsMixin)
    assert issubclass(facade.A07PageProjectActionsMixin, tools.A07PageProjectToolsMixin)

    original_filedialog = page_a07.filedialog
    original_simpledialog = page_a07.simpledialog
    original_session = page_a07.session
    try:
        sentinel_filedialog = object()
        sentinel_simpledialog = object()
        sentinel_session = object()
        page_a07.filedialog = sentinel_filedialog
        page_a07.simpledialog = sentinel_simpledialog
        page_a07.session = sentinel_session
        page_a07._sync_shared_refs()

        assert io.filedialog is sentinel_filedialog
        assert groups.simpledialog is sentinel_simpledialog
        assert tools.session is sentinel_session
    finally:
        page_a07.filedialog = original_filedialog
        page_a07.simpledialog = original_simpledialog
        page_a07.session = original_session
        page_a07._sync_shared_refs()
