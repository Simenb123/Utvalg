from __future__ import annotations

import importlib


def test_context_menu_facade_points_to_split_mixins() -> None:
    facade = importlib.import_module("a07_feature.page_a07_context_menu")
    base = importlib.import_module("a07_feature.page_a07_context_menu_base")
    control = importlib.import_module("a07_feature.page_a07_context_menu_control")
    codes = importlib.import_module("a07_feature.page_a07_context_menu_codes")

    assert issubclass(facade.A07PageContextMenuMixin, base.A07PageContextMenuBaseMixin)
    assert issubclass(facade.A07PageContextMenuMixin, control.A07PageControlContextMenuMixin)
    assert issubclass(facade.A07PageContextMenuMixin, codes.A07PageCodeAndGroupContextMenuMixin)
