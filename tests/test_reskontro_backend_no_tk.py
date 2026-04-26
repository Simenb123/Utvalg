"""Lint-test: reskontro/backend/ får ikke importere tkinter.

Pilot 20 av frontend/backend-mønsteret.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "reskontro" / "backend"
)

_FORBIDDEN_PATTERNS = [
    re.compile(r"^\s*import\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*from\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*import\s+(tk|ttk)\b", re.MULTILINE),
]


def _backend_python_files() -> list[Path]:
    if not _BACKEND_DIR.is_dir():
        pytest.fail(f"Forventer at {_BACKEND_DIR} eksisterer")
    return sorted(_BACKEND_DIR.rglob("*.py"))


@pytest.mark.parametrize("py_file", _backend_python_files(), ids=lambda p: p.name)
def test_backend_file_does_not_import_tkinter(py_file: Path) -> None:
    src = py_file.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(src)
        assert match is None, (
            f"{py_file.relative_to(_BACKEND_DIR.parent)} importerer tkinter "
            f"({match.group().strip() if match else ''!r})."
        )


def test_backend_can_be_imported_headless() -> None:
    from src.pages.reskontro.backend import (  # noqa: F401
        brreg_helpers, open_items, report_engine, report_html,
    )
    assert hasattr(open_items, "__name__")
    assert hasattr(report_engine, "__name__")
