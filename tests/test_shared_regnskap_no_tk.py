"""Lint-test: src/shared/regnskap/ får ikke importere tkinter.

Pilot 21. Cross-cutting regnskap-utility må kunne kjøres hodeløst.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_DIR = Path(__file__).resolve().parent.parent / "src" / "shared" / "regnskap"

_FORBIDDEN_PATTERNS = [
    re.compile(r"^\s*import\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*from\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*import\s+(tk|ttk)\b", re.MULTILINE),
]


def _files() -> list[Path]:
    if not _DIR.is_dir():
        pytest.fail(f"Forventer at {_DIR} eksisterer")
    return sorted(_DIR.rglob("*.py"))


@pytest.mark.parametrize("py_file", _files(), ids=lambda p: p.name)
def test_no_tkinter(py_file: Path) -> None:
    src = py_file.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(src)
        assert match is None, (
            f"{py_file.relative_to(_DIR.parent)} importerer tkinter "
            f"({match.group().strip() if match else ''!r})."
        )


def test_can_be_imported_headless() -> None:
    from src.shared.regnskap import (  # noqa: F401
        client_overrides, config, data, intelligence, mapping, report,
    )
    assert hasattr(config, "load_regnskapslinjer")
    assert hasattr(client_overrides, "load_accounting_system")
