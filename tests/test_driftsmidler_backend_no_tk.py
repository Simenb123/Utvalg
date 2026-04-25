"""Lint-test: driftsmidler/backend/ får ikke importere tkinter.

Dette er den arkitektoniske garantien for at backend kan kjøres hodeløst
(uten Tk) og senere eksponeres som REST-endepunkt for en evt. React-
frontend. Brudd fanges her — i CI, ikke ved kjøretid.

Mønsteret er ment å brukes på alle ``src/pages/<feature>/backend/``-pakker
etter hvert som flere pages migreres.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "driftsmidler" / "backend"
)

_FORBIDDEN_PATTERNS = [
    re.compile(r"^\s*import\s+tkinter\b", re.MULTILINE),
    re.compile(r"^\s*from\s+tkinter\b", re.MULTILINE),
    # Pakke-navn alene (f.eks. "import tk") — sjeldent brukt, men dekk det.
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
    """Backend-pakken skal kunne importeres uten at tkinter er tilgjengelig
    (smoke-test som verifiserer at lint-regelen er meningsfull)."""
    # Bare importer modulen — hvis noen tkinter-import fantes ville den
    # mislykkes på systemer uten Tk.
    from src.pages.driftsmidler.backend import compute  # noqa: F401
    from src.pages.driftsmidler import backend  # noqa: F401

    # Alle public symboler skal være på plass
    expected = {
        "build_dm_reconciliation",
        "classify_dm_transactions",
        "get_konto_ranges",
        "safe_float",
    }
    actual = set(backend.__all__)
    assert expected == actual, (
        f"Public API har endret seg. Forventet {expected}, fikk {actual}."
    )
