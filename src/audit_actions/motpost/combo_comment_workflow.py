from __future__ import annotations

"""Arbeidsflyt for kommentarer på kombinasjoner.

Ligger i egen modul for å holde `motpost/combinations_popup.py` under 1000 linjer.
"""

from typing import Dict

import tkinter as tk
from tkinter import ttk

from .combo_comment_dialog import edit_combo_comment
from .combinations_popup_helpers import truncate_text


def _combo_from_tree_item(tree: ttk.Treeview, item: str) -> str:
    try:
        values = tree.item(item, "values")
    except Exception:
        return ""
    try:
        cols = list(tree["columns"])
    except Exception:
        cols = []
    row = {c: v for c, v in zip(cols, values)}
    return str(row.get("Kombinasjon", "") or "").strip()


def apply_comment_to_tree_item(tree: ttk.Treeview, item: str, *, combo: str, comment_map: Dict[str, str]) -> None:
    """Oppdaterer 'Kommentar'-kolonnen på én rad basert på comment_map."""
    comment_full = str(comment_map.get(combo, "") or "").strip()
    comment_disp = truncate_text(comment_full, max_len=80) if comment_full else ""

    try:
        values = list(tree.item(item, "values"))
        cols = list(tree["columns"])
        idx = cols.index("Kommentar")
        if idx < len(values):
            values[idx] = comment_disp
        tree.item(item, values=values)
    except Exception:
        # Best effort
        pass


def edit_comment_for_tree_item(
    parent: tk.Misc,
    tree: ttk.Treeview,
    item: str,
    *,
    comment_map: Dict[str, str],
) -> None:
    """Åpner kommentar-dialog for aktuell tree-item og oppdaterer map + UI."""
    combo = _combo_from_tree_item(tree, item)
    if not combo:
        return

    existing = str(comment_map.get(combo, "") or "")
    new_comment = edit_combo_comment(parent, combo=combo, initial_comment=existing)
    if new_comment is None:
        return

    new_str = str(new_comment).strip()
    if new_str:
        comment_map[combo] = new_str
    else:
        comment_map.pop(combo, None)

    apply_comment_to_tree_item(tree, item, combo=combo, comment_map=comment_map)


def edit_comment_for_focus(parent: tk.Misc, tree: ttk.Treeview, *, comment_map: Dict[str, str]) -> None:
    """Åpner kommentar-dialog for fokusert rad (evt. første markerte)."""
    item = ""
    try:
        item = tree.focus() or ""
    except Exception:
        item = ""

    if not item:
        try:
            sel = tree.selection()
            if sel:
                item = sel[0]
        except Exception:
            item = ""

    if not item:
        return

    edit_comment_for_tree_item(parent, tree, item, comment_map=comment_map)
