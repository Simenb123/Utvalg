from __future__ import annotations

import importlib


def test_a07_namespace_packages_are_importable() -> None:
    payroll = importlib.import_module("a07_feature.payroll")
    control = importlib.import_module("a07_feature.control")
    ui = importlib.import_module("a07_feature.ui")

    assert payroll is not None
    assert control is not None
    assert ui is not None


def test_payroll_phase_two_modules_and_compat_shims_are_importable() -> None:
    pkg_classification = importlib.import_module("a07_feature.payroll.classification")
    pkg_feedback = importlib.import_module("a07_feature.payroll.feedback")
    pkg_bridge = importlib.import_module("a07_feature.payroll.saldobalanse_bridge")
    pkg_profile_state = importlib.import_module("a07_feature.payroll.profile_state")
    pkg_rf1022 = importlib.import_module("a07_feature.payroll.rf1022")
    pkg_control_data = importlib.import_module("a07_feature.control.data")
    pkg_control_matching = importlib.import_module("a07_feature.control.matching")
    pkg_control_status = importlib.import_module("a07_feature.control.status")
    pkg_control_presenter = importlib.import_module("a07_feature.control.presenter")
    pkg_statement_model = importlib.import_module("a07_feature.control.statement_model")
    pkg_statement_source = importlib.import_module("a07_feature.control.statement_source")
    pkg_statement_ui = importlib.import_module("a07_feature.control.statement_ui")
    pkg_ui_page = importlib.import_module("a07_feature.ui.page")
    pkg_ui_canonical = importlib.import_module("a07_feature.ui.canonical_layout")
    pkg_ui_helpers = importlib.import_module("a07_feature.ui.helpers")
    pkg_ui_selection = importlib.import_module("a07_feature.ui.selection")
    pkg_ui_tree_render = importlib.import_module("a07_feature.ui.tree_render")
    pkg_ui_tree_ui = importlib.import_module("a07_feature.ui.tree_ui")
    pkg_ui_support_render = importlib.import_module("a07_feature.ui.support_render")
    pkg_ui_render = importlib.import_module("a07_feature.ui.render")

    root_classification = importlib.import_module("payroll_classification")
    root_feedback = importlib.import_module("payroll_feedback")
    root_bridge = importlib.import_module("saldobalanse_payroll_mode")
    compat_rf1022 = importlib.import_module("a07_feature.page_a07_rf1022")
    compat_runtime_helpers = importlib.import_module("a07_feature.page_a07_runtime_helpers")
    compat_control_data = importlib.import_module("a07_feature.page_control_data")
    compat_control_matching = importlib.import_module("a07_feature.control_matching")
    compat_control_status = importlib.import_module("a07_feature.control_status")
    compat_control_presenter = importlib.import_module("a07_feature.control_presenter")
    compat_statement_model = importlib.import_module("a07_feature.control_statement_model")
    compat_statement_source = importlib.import_module("a07_feature.control_statement_source")
    compat_statement_ui = importlib.import_module("a07_feature.page_a07_control_statement")
    compat_ui_page = importlib.import_module("a07_feature.page_a07_ui")
    compat_ui_canonical = importlib.import_module("a07_feature.page_a07_ui_canonical")
    compat_ui_helpers = importlib.import_module("a07_feature.page_a07_ui_helpers")
    compat_ui_selection = importlib.import_module("a07_feature.page_a07_selection")
    compat_ui_tree_render = importlib.import_module("a07_feature.page_a07_tree_render")
    compat_ui_tree_ui = importlib.import_module("a07_feature.page_a07_tree_ui")
    compat_ui_support_render = importlib.import_module("a07_feature.page_a07_support_render")
    compat_ui_render = importlib.import_module("a07_feature.page_a07_render")

    assert root_classification.suggest_a07_code is pkg_classification.suggest_a07_code
    assert root_classification._has_payroll_profile_state is pkg_classification._has_payroll_profile_state
    assert root_feedback.append_feedback_events is pkg_feedback.append_feedback_events
    assert root_bridge.is_payroll_mode is pkg_bridge.is_payroll_mode
    assert compat_rf1022.A07PageRf1022Mixin is pkg_rf1022.A07PageRf1022Mixin
    assert callable(pkg_profile_state._load_code_profile_state)
    assert callable(compat_runtime_helpers._load_code_profile_state)
    assert compat_control_data.build_control_queue_df is pkg_control_data.build_control_queue_df
    assert compat_control_matching.best_suggestion_row_for_code is pkg_control_matching.best_suggestion_row_for_code
    assert compat_control_status.control_intro_text is pkg_control_status.control_intro_text
    assert compat_control_presenter.build_control_panel_state is pkg_control_presenter.build_control_panel_state
    assert compat_statement_model.normalize_control_statement_view is pkg_statement_model.normalize_control_statement_view
    assert compat_statement_source.build_current_control_statement_rows is pkg_statement_source.build_current_control_statement_rows
    assert compat_statement_ui.A07PageControlStatementMixin is pkg_statement_ui.A07PageControlStatementMixin
    assert compat_ui_page.A07PageUiMixin is pkg_ui_page.A07PageUiMixin
    assert compat_ui_canonical.A07PageCanonicalUiMixin is pkg_ui_canonical.A07PageCanonicalUiMixin
    assert compat_ui_helpers.A07PageUiHelpersMixin is pkg_ui_helpers.A07PageUiHelpersMixin
    assert compat_ui_selection.A07PageSelectionMixin is pkg_ui_selection.A07PageSelectionMixin
    assert compat_ui_tree_render.A07PageTreeRenderMixin is pkg_ui_tree_render.A07PageTreeRenderMixin
    assert compat_ui_tree_ui.A07PageTreeUiMixin is pkg_ui_tree_ui.A07PageTreeUiMixin
    assert compat_ui_support_render.A07PageSupportRenderMixin is pkg_ui_support_render.A07PageSupportRenderMixin
    assert compat_ui_render.A07PageRenderMixin is pkg_ui_render.A07PageRenderMixin


def test_page_a07_facade_points_to_canonical_moved_modules() -> None:
    facade = importlib.import_module("page_a07")
    pkg_rf1022 = importlib.import_module("a07_feature.payroll.rf1022")
    pkg_statement_ui = importlib.import_module("a07_feature.control.statement_ui")
    pkg_ui_page = importlib.import_module("a07_feature.ui.page")
    pkg_ui_canonical = importlib.import_module("a07_feature.ui.canonical_layout")
    pkg_ui_helpers = importlib.import_module("a07_feature.ui.helpers")
    pkg_ui_render = importlib.import_module("a07_feature.ui.render")
    pkg_ui_selection = importlib.import_module("a07_feature.ui.selection")
    pkg_ui_support_render = importlib.import_module("a07_feature.ui.support_render")
    pkg_ui_tree_render = importlib.import_module("a07_feature.ui.tree_render")

    assert facade._rf1022 is pkg_rf1022
    assert facade._control_statement is pkg_statement_ui
    assert facade._ui is pkg_ui_page
    assert facade._ui_canonical is pkg_ui_canonical
    assert facade._ui_helpers is pkg_ui_helpers
    assert facade._render is pkg_ui_render
    assert facade._selection is pkg_ui_selection
    assert facade._support_render is pkg_ui_support_render
    assert facade._tree_render is pkg_ui_tree_render
