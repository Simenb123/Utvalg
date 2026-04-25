"""Lint-test: saldobalanse/backend/ får ikke importere tkinter.

Pilot 4 av frontend/backend-mønsteret. Samme prinsipp som pilotene for
driftsmidler og statistikk — backend må kunne kjøres hodeløst og
senere eksponeres som REST-endepunkt.

Status etter pilot 4: kun ``payload.py`` er flyttet til backend
(den eneste rene fila uten page-coupling). ``saldobalanse_columns.py``
og ``saldobalanse_payroll_mode.py`` ligger fortsatt på toppnivå —
columns leser ``page._tree`` osv. og er reelt frontend, payroll_mode
er en compat shim.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "saldobalanse" / "backend"
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
    from src.pages.saldobalanse.backend import payload  # noqa: F401
    from src.pages.saldobalanse import backend  # noqa: F401

    # Public API skal være på plass
    assert hasattr(payload, "ALL_COLUMNS")
    assert hasattr(payload, "SaldobalansePayload")


def test_toplevel_shim_aliasses_same_module_object() -> None:
    """``saldobalanse_payload`` (toppnivå) skal være SAMME modul-objekt
    som ``src.pages.saldobalanse.backend.payload``.

    Dette sikrer at eksisterende ``monkeypatch.setattr(saldobalanse_payload, ...)``
    i tester treffer samme objekt som det frontend/admin-koden importerer.
    """
    import saldobalanse_payload as legacy
    from src.pages.saldobalanse.backend import payload as new

    assert legacy is new, (
        "sys.modules-alias virker ikke — toppnivå-shim peker til en annen modul "
        "enn den nye lokasjonen. Tester som monkeypatcher kommer til å bli "
        "inkonsistente."
    )
