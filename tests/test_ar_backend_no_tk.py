"""Lint-test: ar/backend/ får ikke importere tkinter.

Pilot 7 av frontend/backend-mønsteret. AR = aksjonærer (ikke
anleggsregister). Backend må kunne kjøres hodeløst.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_DIR = (
    Path(__file__).resolve().parent.parent
    / "src" / "pages" / "ar" / "backend"
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
    from src.pages.ar.backend import (  # noqa: F401
        formatters,
        ownership_chain,
        pdf_parser,
        store,
    )
    assert hasattr(store, "normalize_orgnr")
    assert hasattr(formatters, "_safe_text")
    assert hasattr(pdf_parser, "ParseResult")


def test_toplevel_shims_aliasser_same_module_object() -> None:
    """Toppnivå-shims (11 totalt) skal være SAMME modul-objekt som ny lokasjon."""
    import ar_ownership_chain
    import ar_registry_pdf_parser
    import ar_registry_pdf_review_dialog
    import ar_store
    import page_ar
    import page_ar_brreg
    import page_ar_chart
    import page_ar_compare
    import page_ar_drilldown
    import page_ar_formatters
    import page_ar_import_detail_dialog

    from src.pages.ar.backend import (
        formatters,
        ownership_chain,
        pdf_parser,
        store,
    )
    from src.pages.ar.frontend import (
        brreg,
        chart,
        compare,
        drilldown,
        import_detail_dialog,
        page,
        pdf_review_dialog,
    )

    assert ar_store is store
    assert ar_ownership_chain is ownership_chain
    assert ar_registry_pdf_parser is pdf_parser
    assert page_ar_formatters is formatters
    assert page_ar is page
    assert page_ar_brreg is brreg
    assert page_ar_chart is chart
    assert page_ar_compare is compare
    assert page_ar_drilldown is drilldown
    assert page_ar_import_detail_dialog is import_detail_dialog
    assert ar_registry_pdf_review_dialog is pdf_review_dialog
