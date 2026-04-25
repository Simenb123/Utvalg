"""Architecture guard: A07 backend code must stay headless.

The A07 page is being migrated toward the same split as driftsmidler:
frontend owns Tk, backend owns data/motor logic. This test protects that
boundary while old a07_feature import paths remain as compatibility shims.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
CANONICAL_BACKEND_DIR = ROOT / "src" / "pages" / "a07" / "backend"

TK_PATTERNS = [
    re.compile(r"^\s*import\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*from\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*import\s+(tk|ttk)\b", re.MULTILINE),
]

CANONICAL_BACKEND_FORBIDDEN = [
    *TK_PATTERNS,
    re.compile(r"^\s*from\s+src\.pages\.a07\.frontend\b", re.MULTILINE),
    re.compile(r"^\s*import\s+src\.pages\.a07\.frontend\b", re.MULTILINE),
    re.compile(r"^\s*from\s+src\.pages\.a07\.controller\b", re.MULTILINE),
    re.compile(r"^\s*from\s+a07_feature\.ui\b", re.MULTILINE),
    re.compile(r"^\s*from\s+a07_feature\.page_a07_env\b", re.MULTILINE),
]

KNOWN_NON_BACKEND = {
    ROOT / "a07_feature" / "control" / "statement_ui.py",
    ROOT / "a07_feature" / "control" / "statement_window_ui.py",
    ROOT / "a07_feature" / "control" / "statement_panel_ui.py",
    ROOT / "a07_feature" / "control" / "statement_view_state.py",
    ROOT / "a07_feature" / "payroll" / "rf1022.py",
}


def _canonical_backend_files() -> list[Path]:
    if not CANONICAL_BACKEND_DIR.is_dir():
        pytest.fail(f"Forventer at {CANONICAL_BACKEND_DIR} eksisterer.")
    return sorted(CANONICAL_BACKEND_DIR.rglob("*.py"))


def _legacy_backend_candidate_files() -> list[Path]:
    files: set[Path] = set()
    for pattern in (
        "a07_feature/control/*.py",
        "a07_feature/suggest/*.py",
        "a07_feature/payroll/classification*.py",
        "a07_feature/payroll/feedback.py",
        "a07_feature/payroll/profile_state.py",
        "a07_feature/payroll/saldobalanse_bridge.py",
        "a07_feature/path_*.py",
    ):
        files.update(ROOT.glob(pattern))
    for rel in (
        "a07_feature/groups.py",
        "a07_feature/mapping_source.py",
        "a07_feature/parser.py",
        "a07_feature/reconcile.py",
        "a07_feature/rule_learning.py",
        "a07_feature/storage.py",
        "a07_feature/workspace.py",
    ):
        path = ROOT / rel
        if path.exists():
            files.add(path)
    return sorted(path for path in files if path.exists() and path not in KNOWN_NON_BACKEND)


@pytest.mark.parametrize("py_file", _canonical_backend_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_canonical_a07_backend_has_no_frontend_or_tk_imports(py_file: Path) -> None:
    source = py_file.read_text(encoding="utf-8")
    for pattern in CANONICAL_BACKEND_FORBIDDEN:
        match = pattern.search(source)
        assert match is None, (
            f"{py_file.relative_to(ROOT).as_posix()} bryter backend-grensen med "
            f"{match.group().strip()!r}."
        )


@pytest.mark.parametrize("py_file", _legacy_backend_candidate_files(), ids=lambda p: p.relative_to(ROOT).as_posix())
def test_legacy_a07_backend_candidates_have_no_tk_imports(py_file: Path) -> None:
    source = py_file.read_text(encoding="utf-8")
    for pattern in TK_PATTERNS:
        match = pattern.search(source)
        assert match is None, (
            f"{py_file.relative_to(ROOT).as_posix()} importerer Tk direkte. "
            "Flytt GUI-bruk til src/pages/a07/frontend."
        )


def test_a07_backend_imports_headless() -> None:
    from src.pages.a07 import backend
    from src.pages.a07.backend import (
        candidate_actions,
        control,
        control_actions,
        mapping_apply,
        payroll,
        project_io,
        rf1022,
        suggest,
    )

    assert set(backend.__all__) == {
        "candidate_actions",
        "control",
        "control_actions",
        "mapping_apply",
        "payroll",
        "project_io",
        "rf1022",
        "suggest",
    }
    assert hasattr(candidate_actions, "global_auto_plan_action_counts")
    assert hasattr(control, "build_control_statement_export_df")
    assert hasattr(control_actions, "plan_selected_control_gl_action")
    assert hasattr(mapping_apply, "apply_residual_changes_to_mapping")
    assert hasattr(payroll, "classify_payroll_account")
    assert hasattr(project_io, "mapping_load_path_decision")
    assert hasattr(rf1022, "build_rf1022_source_df")
    assert hasattr(suggest, "analyze_a07_residuals")


def test_a07_frontend_modules_have_legacy_compat_shims() -> None:
    import a07_feature.control.statement_ui as statement_compat
    import a07_feature.payroll.rf1022 as rf1022_compat
    from src.pages.a07.frontend import control_statement_ui, rf1022

    assert statement_compat.A07PageControlStatementMixin is control_statement_ui.A07PageControlStatementMixin
    assert rf1022_compat.A07PageRf1022Mixin is rf1022.A07PageRf1022Mixin
