"""Lint-test: src/shared/workpapers/ får ikke importere tkinter.

Pilot 25. Workpaper-pakka samler ren backend (forside, generators,
klientinfo, library). De 5 ``workpaper_export_*.py``-filene som
orkestrerer file-dialog/messagebox er IKKE flyttet hit — de hører
i ``src/audit_actions/`` (planlagt egen pilot).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_DIR = Path(__file__).resolve().parent.parent / "src" / "shared" / "workpapers"

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
    from src.shared.workpapers import forside, generators, klientinfo, library  # noqa: F401
    assert hasattr(library, "Workpaper")
    assert hasattr(library, "DEFAULT_KATEGORIER")
    assert hasattr(forside, "build_forside_sheet")
    assert hasattr(generators, "BUILTIN_GENERATORS")
    assert hasattr(klientinfo, "build_cross_matches")
