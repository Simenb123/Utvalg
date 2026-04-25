"""Lint-test: materiality/backend/ får ikke importere tkinter.

Pilot 6 av frontend/backend-mønsteret. Backend må kunne kjøres
hodeløst og senere eksponeres som REST-endepunkt.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "materiality" / "backend"
)

_FORBIDDEN_PATTERNS = [
    re.compile(r"^\s*import\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*from\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*import\s+(tk|ttk)\b", re.MULTILINE),
]


def _backend_python_files() -> list[Path]:
    if not _BACKEND_DIR.is_dir():
        pytest.fail(
            f"Forventer at {_BACKEND_DIR} eksisterer — har strukturen blitt endret?"
        )
    return sorted(_BACKEND_DIR.rglob("*.py"))


@pytest.mark.parametrize("py_file", _backend_python_files(), ids=lambda p: p.name)
def test_backend_file_does_not_import_tkinter(py_file: Path) -> None:
    """Hver enkelt fil i backend/ skal være fri for tkinter-imports."""
    src = py_file.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        match = pattern.search(src)
        assert match is None, (
            f"{py_file.relative_to(_BACKEND_DIR.parent)} importerer tkinter "
            f"({match.group().strip() if match else ''!r}). "
            f"Backend må være ren Python — flytt Tk-bruk til frontend/."
        )


def test_backend_can_be_imported_headless() -> None:
    """Backend-pakken skal kunne importeres uten at tkinter er tilgjengelig."""
    from src.pages.materiality.backend import (  # noqa: F401
        crmsystem,
        engine,
        store,
        workpaper_excel,
    )

    # Public API skal være på plass
    assert hasattr(engine, "calculate_materiality")
    assert hasattr(store, "load_state")
    assert hasattr(workpaper_excel, "export_materiality_workpaper")
    assert hasattr(crmsystem, "load_materiality_from_crm")


def test_toplevel_shims_aliasser_same_module_object() -> None:
    """Toppnivå-shims skal være SAMME modul-objekt som backend-modulen."""
    import crmsystem_materiality as legacy_crm
    import materiality_engine as legacy_engine
    import materiality_store as legacy_store
    import materiality_workpaper_excel as legacy_excel

    from src.pages.materiality.backend import crmsystem, engine, store, workpaper_excel

    assert legacy_crm is crmsystem
    assert legacy_engine is engine
    assert legacy_store is store
    assert legacy_excel is workpaper_excel
