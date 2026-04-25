"""Lint-test: statistikk/backend/ får ikke importere tkinter.

Pilot 2/3 av frontend/backend-mønsteret. Samme prinsipp som
``test_driftsmidler_backend_no_tk.py`` — backend må kunne kjøres
hodeløst og senere eksponeres som REST-endepunkt.

Status etter pilot 3: pure-data-API er på plass
(``get_konto_set_for_regnr``, ``compute_kontoer``, ``compute_motpost_rl``,
``write_workbook`` med ``pivot_df_rl``/``sb_df``/``sb_prev_df``/``context``).
Underscore-prefiksede shims tar fortsatt ``page`` for bakoverkompat med
tester, men ingen av dem importerer tkinter.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "statistikk" / "backend"
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
    from src.pages.statistikk.backend import compute, excel  # noqa: F401
    from src.pages.statistikk import backend  # noqa: F401

    # Public API skal være på plass
    assert hasattr(compute, "get_konto_ranges")
    assert hasattr(excel, "write_workbook")
