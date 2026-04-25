from __future__ import annotations

import importlib


def test_ui_canonical_split_modules_and_facades_are_importable() -> None:
    canonical = importlib.import_module("a07_feature.ui.canonical_layout")
    control = importlib.import_module("a07_feature.ui.control_layout")
    support = importlib.import_module("a07_feature.ui.support_layout")
    groups = importlib.import_module("a07_feature.ui.groups_popup")
    compat = importlib.import_module("a07_feature.page_a07_ui_canonical")

    assert compat.A07PageCanonicalUiMixin is canonical.A07PageCanonicalUiMixin
    assert issubclass(canonical.A07PageCanonicalUiMixin, control.A07PageControlLayoutMixin)
    assert issubclass(canonical.A07PageCanonicalUiMixin, support.A07PageSupportLayoutMixin)
    assert issubclass(canonical.A07PageCanonicalUiMixin, groups.A07PageGroupsPopupMixin)
