"""Lint-test: src/shared/saft/ får ikke importere tkinter.

Pilot 24. SAF-T-pakka er ren backend (cross-cutting utility).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_DIR = Path(__file__).resolve().parent.parent / "src" / "shared" / "saft"

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
    from src.shared.saft import reader, tax_table, trial_balance  # noqa: F401
    assert hasattr(reader, "read_saft_ledger")
    assert hasattr(reader, "READER_VERSION")
    assert hasattr(tax_table, "extract_tax_table")
    assert hasattr(trial_balance, "extract_trial_balance_df_from_saft")
    assert hasattr(trial_balance, "make_trial_balance_xlsx_from_saft")
