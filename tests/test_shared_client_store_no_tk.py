"""Lint-test: src/shared/client_store/ får ikke importere tkinter.

Pilot 22. Klient-store er cross-cutting backend som må kunne kjøres
hodeløst (REST-eksponering senere).

Tk-koblede dialoger ligger separat:
- client_picker_dialog.py (toppnivå)
- client_store_enrich_ui.py (toppnivå)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_DIR = Path(__file__).resolve().parent.parent / "src" / "shared" / "client_store"

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
    from src.shared.client_store import enrich, importer, meta_index, store, versions  # noqa: F401
    assert hasattr(store, "read_client_meta")
    assert hasattr(meta_index, "get_index")
    assert hasattr(enrich, "plan_enrichment")
