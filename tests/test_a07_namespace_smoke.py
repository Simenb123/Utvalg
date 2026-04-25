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
    pkg_classification_shared = importlib.import_module("a07_feature.payroll.classification_shared")
    pkg_classification_guardrails = importlib.import_module("a07_feature.payroll.classification_guardrails")
    pkg_classification_catalog = importlib.import_module("a07_feature.payroll.classification_catalog")
    pkg_classification_a07_engine = importlib.import_module("a07_feature.payroll.classification_a07_engine")
    pkg_classification_engine = importlib.import_module("a07_feature.payroll.classification_engine")
    pkg_classification_audit = importlib.import_module("a07_feature.payroll.classification_audit")
    pkg_feedback = importlib.import_module("a07_feature.payroll.feedback")
    pkg_bridge = importlib.import_module("a07_feature.payroll.saldobalanse_bridge")
    pkg_profile_state = importlib.import_module("a07_feature.payroll.profile_state")
    pkg_rf1022 = importlib.import_module("a07_feature.payroll.rf1022")
    pkg_control_data = importlib.import_module("a07_feature.control.data")
    pkg_mapping_audit = importlib.import_module("a07_feature.control.mapping_audit")
    pkg_mapping_audit_rules = importlib.import_module("a07_feature.control.mapping_audit_rules")
    pkg_mapping_audit_status = importlib.import_module("a07_feature.control.mapping_audit_status")
    pkg_mapping_review = importlib.import_module("a07_feature.control.mapping_review")
    pkg_mapping_audit_projection = importlib.import_module("a07_feature.control.mapping_audit_projection")
    pkg_control_matching = importlib.import_module("a07_feature.control.matching")
    pkg_control_status = importlib.import_module("a07_feature.control.status")
    pkg_control_presenter = importlib.import_module("a07_feature.control.presenter")
    pkg_global_auto = importlib.import_module("a07_feature.control.global_auto")
    pkg_queue_data = importlib.import_module("a07_feature.control.queue_data")
    pkg_queue_shared = importlib.import_module("a07_feature.control.queue_shared")
    pkg_overview_data = importlib.import_module("a07_feature.control.overview_data")
    pkg_history_data = importlib.import_module("a07_feature.control.history_data")
    pkg_control_filters = importlib.import_module("a07_feature.control.control_filters")
    pkg_control_queue_data = importlib.import_module("a07_feature.control.control_queue_data")
    pkg_control_gl_data = importlib.import_module("a07_feature.control.control_gl_data")
    pkg_control_suggestion_selection = importlib.import_module(
        "a07_feature.control.control_suggestion_selection"
    )
    pkg_rf1022_candidates = importlib.import_module("a07_feature.control.rf1022_candidates")
    pkg_statement_data = importlib.import_module("a07_feature.control.statement_data")
    pkg_statement_model = importlib.import_module("a07_feature.control.statement_model")
    pkg_statement_source = importlib.import_module("a07_feature.control.statement_source")
    pkg_statement_ui = importlib.import_module("a07_feature.control.statement_ui")
    pkg_tree_tags = importlib.import_module("a07_feature.control.tree_tags")
    pkg_ui_bindings = importlib.import_module("a07_feature.ui.bindings")
    pkg_ui_page = importlib.import_module("a07_feature.ui.page")
    pkg_ui_canonical = importlib.import_module("a07_feature.ui.canonical_layout")
    pkg_ui_helpers = importlib.import_module("a07_feature.ui.helpers")
    pkg_ui_selection = importlib.import_module("a07_feature.ui.selection")
    pkg_ui_tree_render = importlib.import_module("a07_feature.ui.tree_render")
    pkg_ui_tree_ui = importlib.import_module("a07_feature.ui.tree_ui")
    pkg_ui_support_render = importlib.import_module("a07_feature.ui.support_render")
    pkg_ui_render = importlib.import_module("a07_feature.ui.render")
    pkg_context_menu = importlib.import_module("a07_feature.page_a07_context_menu")
    pkg_context_menu_base = importlib.import_module("a07_feature.page_a07_context_menu_base")
    pkg_context_menu_control = importlib.import_module("a07_feature.page_a07_context_menu_control")
    pkg_context_menu_codes = importlib.import_module("a07_feature.page_a07_context_menu_codes")

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
    assert pkg_classification.suggest_a07_code is pkg_classification_a07_engine.suggest_a07_code
    assert pkg_classification.classify_payroll_account is pkg_classification_engine.classify_payroll_account
    assert pkg_classification.suspicious_saved_payroll_profile_issue is (
        pkg_classification_audit.suspicious_saved_payroll_profile_issue
    )
    assert pkg_classification.detect_rf1022_exclude_blocks is (
        pkg_classification_catalog.detect_rf1022_exclude_blocks
    )
    assert root_classification._has_payroll_profile_state is pkg_classification._has_payroll_profile_state
    assert pkg_classification._has_payroll_profile_state is (
        pkg_classification_guardrails._has_payroll_profile_state
    )
    assert pkg_classification._normalized_phrase_match is pkg_classification_shared._normalized_phrase_match
    assert pkg_classification._suggest_control_group_from_catalog is (
        pkg_classification_catalog._suggest_control_group_from_catalog
    )
    assert root_feedback.append_feedback_events is pkg_feedback.append_feedback_events
    assert root_bridge.is_payroll_mode is pkg_bridge.is_payroll_mode
    assert compat_rf1022.A07PageRf1022Mixin is pkg_rf1022.A07PageRf1022Mixin
    assert callable(pkg_profile_state._load_code_profile_state)
    assert callable(compat_runtime_helpers._load_code_profile_state)
    assert pkg_queue_shared is not None
    assert compat_control_data.build_control_queue_df is pkg_control_data.build_control_queue_df
    assert compat_control_data.build_control_queue_df is pkg_control_queue_data.build_control_queue_df
    assert compat_control_data.build_control_queue_df is pkg_queue_data.build_control_queue_df
    assert compat_control_data.build_a07_overview_df is pkg_overview_data.build_a07_overview_df
    assert compat_control_data.build_history_comparison_df is pkg_history_data.build_history_comparison_df
    assert compat_control_data.build_mapping_history_details is pkg_history_data.build_mapping_history_details
    assert compat_control_data.filter_control_gl_df is pkg_control_filters.filter_control_gl_df
    assert compat_control_data.filter_control_gl_df is pkg_queue_data.filter_control_gl_df
    assert compat_control_data.build_control_gl_df is pkg_control_gl_data.build_control_gl_df
    assert compat_control_data.select_batch_suggestion_rows is (
        pkg_control_suggestion_selection.select_batch_suggestion_rows
    )
    assert compat_control_data.build_global_auto_mapping_plan is pkg_global_auto.build_global_auto_mapping_plan
    assert compat_control_data.build_rf1022_candidate_df is pkg_rf1022_candidates.build_rf1022_candidate_df
    assert compat_control_data.build_rf1022_candidate_df_for_groups is pkg_rf1022_candidates.build_rf1022_candidate_df_for_groups
    assert compat_control_data.build_control_statement_export_df is pkg_statement_data.build_control_statement_export_df
    assert compat_control_data.build_mapping_audit_df is pkg_mapping_audit.build_mapping_audit_df
    assert compat_control_data.apply_mapping_audit_to_control_gl_df is pkg_mapping_audit.apply_mapping_audit_to_control_gl_df
    assert callable(pkg_mapping_audit_rules.build_mapping_audit_df)
    assert callable(pkg_mapping_audit_status.sort_mapping_rows_by_audit_status)
    assert callable(pkg_mapping_review.build_mapping_review_df)
    assert callable(pkg_mapping_audit_projection.apply_mapping_audit_to_control_gl_df)
    assert compat_control_data.control_queue_tree_tag is pkg_tree_tags.control_queue_tree_tag
    assert compat_control_data.reconcile_tree_tag is pkg_tree_tags.reconcile_tree_tag
    assert compat_control_matching.best_suggestion_row_for_code is pkg_control_matching.best_suggestion_row_for_code
    assert compat_control_status.control_intro_text is pkg_control_status.control_intro_text
    assert compat_control_presenter.build_control_panel_state is pkg_control_presenter.build_control_panel_state
    assert compat_statement_model.normalize_control_statement_view is pkg_statement_model.normalize_control_statement_view
    assert compat_statement_source.build_current_control_statement_rows is pkg_statement_source.build_current_control_statement_rows
    assert compat_statement_ui.A07PageControlStatementMixin is pkg_statement_ui.A07PageControlStatementMixin
    assert hasattr(pkg_ui_bindings, "A07PageBindingsMixin")
    assert compat_ui_page.A07PageUiMixin is pkg_ui_page.A07PageUiMixin
    assert compat_ui_canonical.A07PageCanonicalUiMixin is pkg_ui_canonical.A07PageCanonicalUiMixin
    assert compat_ui_helpers.A07PageUiHelpersMixin is pkg_ui_helpers.A07PageUiHelpersMixin
    assert compat_ui_selection.A07PageSelectionMixin is pkg_ui_selection.A07PageSelectionMixin
    assert compat_ui_tree_render.A07PageTreeRenderMixin is pkg_ui_tree_render.A07PageTreeRenderMixin
    assert compat_ui_tree_ui.A07PageTreeUiMixin is pkg_ui_tree_ui.A07PageTreeUiMixin
    assert issubclass(pkg_ui_tree_ui.A07PageTreeUiMixin, pkg_ui_helpers.A07PageUiHelpersMixin)
    assert compat_ui_support_render.A07PageSupportRenderMixin is pkg_ui_support_render.A07PageSupportRenderMixin
    assert compat_ui_render.A07PageRenderMixin is pkg_ui_render.A07PageRenderMixin
    assert issubclass(pkg_context_menu.A07PageContextMenuMixin, pkg_context_menu_base.A07PageContextMenuBaseMixin)
    assert issubclass(pkg_context_menu.A07PageContextMenuMixin, pkg_context_menu_control.A07PageControlContextMenuMixin)
    assert issubclass(pkg_context_menu.A07PageContextMenuMixin, pkg_context_menu_codes.A07PageCodeAndGroupContextMenuMixin)
def test_path_modules_and_page_paths_facade_are_importable() -> None:
    pkg_page_paths = importlib.import_module("a07_feature.page_paths")
    pkg_path_shared = importlib.import_module("a07_feature.path_shared")
    pkg_path_context = importlib.import_module("a07_feature.path_context")
    pkg_path_rulebook = importlib.import_module("a07_feature.path_rulebook")
    pkg_path_snapshots = importlib.import_module("a07_feature.path_snapshots")
    pkg_path_trial_balance = importlib.import_module("a07_feature.path_trial_balance")
    pkg_path_history = importlib.import_module("a07_feature.path_history")
    assert pkg_page_paths.MATCHER_SETTINGS_DEFAULTS is pkg_path_rulebook.MATCHER_SETTINGS_DEFAULTS
    assert pkg_page_paths._path_signature is pkg_path_shared._path_signature
    assert pkg_page_paths.get_a07_workspace_dir is pkg_path_context.get_a07_workspace_dir
    assert pkg_page_paths.resolve_rulebook_path is pkg_path_rulebook.resolve_rulebook_path
    assert pkg_page_paths.get_context_snapshot is pkg_path_snapshots.get_context_snapshot
    assert pkg_page_paths.get_active_trial_balance_path_for_context is (
        pkg_path_trial_balance.get_active_trial_balance_path_for_context
    )
    assert pkg_page_paths.load_previous_year_mapping_for_context is (
        pkg_path_history.load_previous_year_mapping_for_context
    )
def test_page_a07_facade_points_to_canonical_moved_modules() -> None:
    facade = importlib.import_module("page_a07")
    pkg_src_a07 = importlib.import_module("src.pages.a07")
    pkg_src_a07_page = importlib.import_module("src.pages.a07.page_a07")
    pkg_global_auto = importlib.import_module("a07_feature.control.global_auto")
    pkg_rf1022_candidates = importlib.import_module("a07_feature.control.rf1022_candidates")
    pkg_rf1022 = importlib.import_module("a07_feature.payroll.rf1022")
    pkg_statement_ui = importlib.import_module("a07_feature.control.statement_ui")
    pkg_ui_page = importlib.import_module("a07_feature.ui.page")
    pkg_ui_canonical = importlib.import_module("a07_feature.ui.canonical_layout")
    pkg_ui_helpers = importlib.import_module("a07_feature.ui.helpers")
    pkg_ui_render = importlib.import_module("a07_feature.ui.render")
    pkg_ui_selection = importlib.import_module("a07_feature.ui.selection")
    pkg_ui_support_render = importlib.import_module("a07_feature.ui.support_render")
    pkg_ui_tree_render = importlib.import_module("a07_feature.ui.tree_render")
    assert facade is pkg_src_a07_page
    assert pkg_src_a07.A07Page is facade.A07Page
    assert facade._rf1022 is pkg_rf1022
    assert facade._SHARED_ORIGINALS["build_global_auto_mapping_plan"] is pkg_global_auto.build_global_auto_mapping_plan
    assert facade._SHARED_ORIGINALS["build_rf1022_candidate_df"] is pkg_rf1022_candidates.build_rf1022_candidate_df
    assert facade._control_statement is pkg_statement_ui
    assert facade._ui is pkg_ui_page
    assert facade._ui_canonical is pkg_ui_canonical
    assert facade._ui_helpers is pkg_ui_helpers
    assert facade._render is pkg_ui_render
    assert facade._selection is pkg_ui_selection
    assert facade._support_render is pkg_ui_support_render
    assert facade._tree_render is pkg_ui_tree_render
