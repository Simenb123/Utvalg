"""Motpostanalyse (GUI) - Treeview helpers.

Dette er *UI-hjelpefunksjoner* (duck typing) som kan testes uten Tkinter.

Begrunnelse for egen modul:
    - :mod:`views_motpost_konto` ble stor
    - disse funksjonene er ren "lim" mellom Treeview og callbacks
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.audit_actions.motpost.konto_core import _konto_str


def treeview_value_from_iid(
    tree: Any,
    iid: Any,
    *,
    col_index: int = 0,
    value_transform: Callable[[Any], str] | None = None,
) -> Optional[str]:
    """Hent en verdi fra Treeview.item(iid, 'values')[col_index]."""
    if iid is None:
        return None
    try:
        values = tree.item(iid, "values")
    except Exception:
        return None
    if not values or len(values) <= col_index:
        return None
    raw = values[col_index]
    try:
        return value_transform(raw) if value_transform else str(raw)
    except Exception:
        return str(raw)


def treeview_first_selected_value(
    tree: Any,
    *,
    col_index: int = 0,
    value_transform: Callable[[Any], str] | None = None,
) -> Optional[str]:
    """Hent verdi fra første markerte rad i Treeview."""
    try:
        sel = list(tree.selection())
    except Exception:
        return None
    if not sel:
        return None
    return treeview_value_from_iid(tree, sel[0], col_index=col_index, value_transform=value_transform)


def _on_tree_double_click_open_value(
    event: Any,
    tree: Any,
    open_value_callback: Callable[[str], None],
    *,
    col_index: int = 0,
) -> str:
    """Dobbelklikk: identifiser raden under mus og åpne drilldown."""
    try:
        iid = tree.identify_row(event.y)
    except Exception:
        iid = None
    if iid:
        try:
            tree.selection_set(iid)
        except Exception:
            pass
        value = treeview_value_from_iid(tree, iid, col_index=col_index, value_transform=_konto_str)
        if value:
            open_value_callback(value)
    return "break"


def _on_tree_enter_open_first_selected(
    _event: Any,
    tree: Any,
    open_value_callback: Callable[[str], None],
    *,
    col_index: int = 0,
) -> str:
    value = treeview_first_selected_value(tree, col_index=col_index, value_transform=_konto_str)
    if value:
        open_value_callback(value)
    return "break"


def configure_bilag_details_tree(tree: Any, *, open_bilag_callback: Callable[[str], None]) -> None:
    """Fellesoppsett for bilag-listen i motpostanalyse:

    - Multiselect (extended)
    - Dobbelklikk åpner drilldown for bilaget
    - Enter åpner drilldown for første markerte bilag

    (Duck typing slik at dette kan testes uten Tk.)
    """

    try:
        tree.configure(selectmode="extended")
    except Exception:
        pass

    # Bind både med og uten 'add' for å støtte dummy-trær i tester.
    try:
        tree.bind(
            "<Double-1>",
            lambda e: _on_tree_double_click_open_value(e, tree, open_bilag_callback, col_index=0),
            add="+",
        )
        tree.bind(
            "<Return>",
            lambda e: _on_tree_enter_open_first_selected(e, tree, open_bilag_callback, col_index=0),
            add="+",
        )
        return
    except Exception:
        pass

    try:
        tree.bind(
            "<Double-1>",
            lambda e: _on_tree_double_click_open_value(e, tree, open_bilag_callback, col_index=0),
        )
        tree.bind(
            "<Return>",
            lambda e: _on_tree_enter_open_first_selected(e, tree, open_bilag_callback, col_index=0),
        )
    except Exception:
        pass
