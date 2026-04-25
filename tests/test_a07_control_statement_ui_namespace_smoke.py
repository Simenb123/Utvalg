from __future__ import annotations

import importlib


def test_control_statement_ui_facade_points_to_split_mixins() -> None:
    facade = importlib.import_module("a07_feature.control.statement_ui")
    state = importlib.import_module("a07_feature.control.statement_view_state")
    window = importlib.import_module("a07_feature.control.statement_window_ui")
    panel = importlib.import_module("a07_feature.control.statement_panel_ui")
    compat = importlib.import_module("a07_feature.page_a07_control_statement")

    assert compat.A07PageControlStatementMixin is facade.A07PageControlStatementMixin
    assert issubclass(facade.A07PageControlStatementMixin, state.A07PageControlStatementViewStateMixin)
    assert issubclass(facade.A07PageControlStatementMixin, window.A07PageControlStatementWindowMixin)
    assert issubclass(facade.A07PageControlStatementMixin, panel.A07PageControlStatementPanelMixin)
