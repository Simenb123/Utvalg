from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

CODE_DEFAULT_BUDGET = 400
TEST_DEFAULT_BUDGET = 1000
TEST_HELPER_DEFAULT_BUDGET = 400

CODE_BUDGETS: dict[Path, int] = {
    Path("page_a07.py"): 200,
    Path("src/pages/a07/page_a07.py"): 200,
    Path("src/pages/a07/frontend/page.py"): 700,
    Path("a07_feature/control/data.py"): 400,
    Path("a07_feature/control/mapping_audit.py"): 250,
    Path("a07_feature/control/matching.py"): 250,
    Path("a07_feature/control/queue_data.py"): 250,
    Path("a07_feature/control/statement_data.py"): 450,
    Path("a07_feature/control/statement_ui.py"): 250,
    Path("a07_feature/page_a07_constants.py"): 500,
    Path("a07_feature/page_a07_context_menu.py"): 250,
    Path("a07_feature/page_a07_dialogs.py"): 250,
    Path("a07_feature/page_a07_project_actions.py"): 250,
    Path("a07_feature/page_a07_refresh.py"): 500,
    Path("a07_feature/page_a07_refresh_apply.py"): 600,
    Path("a07_feature/page_a07_refresh_services.py"): 450,
    Path("a07_feature/page_a07_refresh_state.py"): 550,
    Path("a07_feature/page_paths.py"): 250,
    Path("a07_feature/page_windows.py"): 250,
    Path("a07_feature/parser.py"): 450,
    Path("a07_feature/payroll/classification.py"): 250,
    Path("a07_feature/payroll/rf1022.py"): 600,
    Path("a07_feature/suggest/engine.py"): 250,
    Path("a07_feature/ui/canonical_layout.py"): 250,
    Path("a07_feature/ui/helpers.py"): 250,
    Path("a07_feature/ui/render.py"): 500,
}

TEST_BUDGETS: dict[Path, int] = {
    Path("tests/a07/test_paths_and_storage.py"): 250,
    Path("tests/a07/test_path_context.py"): 200,
    Path("tests/a07/test_path_rulebook.py"): 150,
    Path("tests/a07/test_path_history.py"): 200,
    Path("tests/a07/test_path_trial_balance.py"): 150,
    Path("tests/a07/test_control_queue_engine.py"): 200,
    Path("tests/a07/test_mapping_audit_review.py"): 300,
    Path("tests/a07/test_global_auto_plan.py"): 250,
    Path("tests/a07/test_control_queue_data.py"): 350,
    Path("tests/a07/test_control_gl_data.py"): 150,
    Path("tests/a07/test_control_filters.py"): 150,
    Path("tests/a07/test_mapping_action_guardrails.py"): 150,
    Path("tests/test_page_a07.py"): 200,
    Path("tests/test_page_a07_payroll.py"): 450,
    Path("tests/test_a07_namespace_smoke.py"): 200,
    Path("tests/test_a07_ui_helpers_namespace_smoke.py"): 150,
    Path("tests/test_a07_refactor_round1.py"): 250,
    Path("tests/test_a07_control_matching.py"): 500,
    Path("tests/test_a07_control_matching_namespace_smoke.py"): 100,
    Path("tests/test_a07_mapping_audit_namespace_smoke.py"): 100,
    Path("tests/test_a07_context_menu_namespace_smoke.py"): 100,
    Path("tests/test_a07_dialogs_namespace_smoke.py"): 100,
    Path("tests/test_a07_control_data_namespace_smoke.py"): 100,
    Path("tests/test_a07_control_statement_source.py"): 350,
    Path("tests/test_a07_control_statement_ui_namespace_smoke.py"): 100,
    Path("tests/test_a07_feature_adapters_and_select.py"): 250,
    Path("tests/test_a07_feature_suggest.py"): 650,
    Path("tests/test_a07_feature_suggest_namespace_smoke.py"): 100,
    Path("tests/test_a07_mapping_source.py"): 350,
    Path("tests/test_a07_project_actions_namespace_smoke.py"): 100,
    Path("tests/test_a07_page_windows_namespace_smoke.py"): 100,
    Path("tests/test_a07_suggest_usage.py"): 350,
    Path("tests/test_a07_ui_canonical_namespace_smoke.py"): 100,
    Path("tests/test_payroll_classification.py"): 100,
    Path("tests/test_payroll_classification_suggest.py"): 250,
    Path("tests/test_payroll_classification_classify.py"): 350,
    Path("tests/test_payroll_classification_catalog.py"): 250,
    Path("tests/test_payroll_classification_audit.py"): 300,
}


def _iter_code_files() -> list[Path]:
    files = sorted((ROOT / "a07_feature").rglob("*.py"))
    files.extend(sorted((ROOT / "src" / "pages" / "a07").rglob("*.py")))
    files.append(ROOT / "page_a07.py")
    return [path for path in files if path.exists()]


def _iter_test_files() -> list[Path]:
    files = sorted((ROOT / "tests" / "a07").glob("*.py"))
    files.extend(sorted((ROOT / "tests").glob("test_a07*.py")))
    files.extend(sorted((ROOT / "tests").glob("test_page_a07*.py")))
    files.extend(sorted((ROOT / "tests").glob("test_payroll_classification*.py")))
    return [path for path in files if path.exists()]


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open("r", encoding="utf-8-sig"))


def _budget_for(path: Path) -> int:
    rel = path.relative_to(ROOT)
    if rel in CODE_BUDGETS:
        return CODE_BUDGETS[rel]
    if rel in TEST_BUDGETS:
        return TEST_BUDGETS[rel]
    if rel.parts[:2] == ("tests", "a07"):
        return TEST_DEFAULT_BUDGET if rel.name.startswith("test_") else TEST_HELPER_DEFAULT_BUDGET
    if rel.parts and rel.parts[0] == "tests":
        return TEST_DEFAULT_BUDGET
    return CODE_DEFAULT_BUDGET


def test_a07_code_and_test_modules_stay_within_budget() -> None:
    offenders: list[str] = []
    for path in [*_iter_code_files(), *_iter_test_files()]:
        rel = path.relative_to(ROOT)
        lines = _line_count(path)
        budget = _budget_for(path)
        if lines > budget:
            offenders.append(f"{rel.as_posix()}: {lines} > {budget}")

    assert not offenders, "A07 module budgets exceeded:\n" + "\n".join(offenders)
