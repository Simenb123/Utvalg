from __future__ import annotations

import importlib


def test_ui_helper_submodules_and_facades_are_importable() -> None:
    pkg_ui_drag_drop = importlib.import_module("a07_feature.ui.drag_drop_helpers")
    pkg_ui_focus = importlib.import_module("a07_feature.ui.focus_helpers")
    pkg_ui_helpers = importlib.import_module("a07_feature.ui.helpers")
    pkg_ui_manual_defaults = importlib.import_module("a07_feature.ui.manual_mapping_defaults")
    pkg_ui_tree_builders = importlib.import_module("a07_feature.ui.tree_builders")
    pkg_ui_tree_selection_helpers = importlib.import_module("a07_feature.ui.tree_selection_helpers")
    pkg_ui_tree_sorting = importlib.import_module("a07_feature.ui.tree_sorting")
    compat_ui_helpers = importlib.import_module("a07_feature.page_a07_ui_helpers")
    compat_ui_tree_ui = importlib.import_module("a07_feature.page_a07_tree_ui")
    pkg_ui_tree_ui = importlib.import_module("a07_feature.ui.tree_ui")

    assert compat_ui_helpers.A07PageUiHelpersMixin is pkg_ui_helpers.A07PageUiHelpersMixin
    assert compat_ui_tree_ui.A07PageTreeUiMixin is pkg_ui_tree_ui.A07PageTreeUiMixin
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_tree_builders.A07PageTreeBuilderMixin)
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_tree_sorting.A07PageTreeSortingMixin)
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_tree_selection_helpers.A07PageTreeSelectionHelpersMixin)
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_manual_defaults.A07PageManualMappingDefaultsMixin)
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_focus.A07PageFocusHelpersMixin)
    assert issubclass(pkg_ui_helpers.A07PageUiHelpersMixin, pkg_ui_drag_drop.A07PageDragDropHelpersMixin)


def test_page_a07_facade_tracks_split_ui_helper_modules() -> None:
    facade = importlib.import_module("page_a07")
    pkg_ui_drag_drop = importlib.import_module("a07_feature.ui.drag_drop_helpers")
    pkg_ui_focus = importlib.import_module("a07_feature.ui.focus_helpers")
    pkg_ui_manual_defaults = importlib.import_module("a07_feature.ui.manual_mapping_defaults")
    pkg_ui_tree_builders = importlib.import_module("a07_feature.ui.tree_builders")
    pkg_ui_tree_selection_helpers = importlib.import_module("a07_feature.ui.tree_selection_helpers")
    pkg_ui_tree_sorting = importlib.import_module("a07_feature.ui.tree_sorting")

    assert facade._ui_tree_builders is pkg_ui_tree_builders
    assert facade._ui_tree_sorting is pkg_ui_tree_sorting
    assert facade._ui_tree_selection_helpers is pkg_ui_tree_selection_helpers
    assert facade._ui_manual_mapping_defaults is pkg_ui_manual_defaults
    assert facade._ui_focus_helpers is pkg_ui_focus
    assert facade._ui_drag_drop_helpers is pkg_ui_drag_drop
