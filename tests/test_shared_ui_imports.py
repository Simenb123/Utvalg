"""Lint-test: src/shared/ui/ — pakke-integritet og public-API.

Pilot 26. I motsetning til andre src/shared/-pakker SKAL denne pakka
kunne importere ``tkinter`` (det er en GUI-utility-pakke). Denne testen
sjekker bare at modulene kan importeres + at forventede public-symboler
finnes.
"""
from __future__ import annotations


def test_can_be_imported() -> None:
    from src.shared.ui import (  # noqa: F401
        dialog,
        excel_theme,
        hotkeys,
        loading,
        managed_treeview,
        selection_summary,
        tokens,
        treeview_sort,
        utils,
    )


def test_public_symbols_exist() -> None:
    from src.shared.ui import dialog, managed_treeview, tokens, treeview_sort

    assert hasattr(dialog, "make_dialog")
    assert hasattr(managed_treeview, "ManagedTreeview")
    assert hasattr(managed_treeview, "ColumnSpec")
    assert hasattr(treeview_sort, "enable_treeview_sorting")
    # Tokens er fargevariabler — sjekk noen av de mest brukte
    assert hasattr(tokens, "SAGE")
    assert hasattr(tokens, "FONT_FAMILY_BODY")


def test_relative_imports_within_package() -> None:
    """Pakka skal bruke relative imports internt — verifiser at ingen
    fil refererer til de gamle ui_*/vaak_*-flatnavnene."""
    import re
    from pathlib import Path

    pkg_dir = Path(__file__).resolve().parent.parent / "src" / "shared" / "ui"
    forbidden = re.compile(
        r"^\s*(import|from)\s+(ui_dialog|ui_hotkeys|ui_loading|"
        r"ui_managed_treeview|ui_selection_summary|ui_treeview_sort|"
        r"ui_utils|vaak_excel_theme|vaak_tokens)\b",
        re.MULTILINE,
    )
    for py in sorted(pkg_dir.rglob("*.py")):
        src = py.read_text(encoding="utf-8")
        m = forbidden.search(src)
        assert m is None, (
            f"{py.name} bruker fortsatt flatnavn-import: {m.group().strip()!r}"
        )
