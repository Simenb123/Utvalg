"""ui_hotkeys.py

Globale hotkeys + kopiering til clipboard + (valgfritt) selection-summary.

Hotkeys:
  - Ctrl+A: marker alle rader i aktiv Treeview/Listbox
  - Ctrl+C: kopier markerte rader til clipboard (Treeview -> TSV, Listbox -> linjer)

Selection summary:
  - Valgfritt, men default ON.
  - Bruker `ui_selection_summary` for å vise antall + sum av relevante beløpskolonner.

Design:
- Duck typing: fungerer i pytest uten Tk-vindu.
- Idempotent install: kan kalles flere ganger.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import ui_selection_summary


# --------------------------------------------------------------------------------------
# Widget deteksjon (duck typing)
# --------------------------------------------------------------------------------------

def _tree_is_treeview(widget: Any) -> bool:
    return all(hasattr(widget, attr) for attr in ("selection", "set", "get_children"))


def _listbox_is_listbox(widget: Any) -> bool:
    return all(hasattr(widget, attr) for attr in ("curselection", "get", "size", "selection_set"))


def _tree_get_columns(tree: Any) -> list[str]:
    try:
        return [str(c) for c in list(tree["columns"])]  # type: ignore[index]
    except Exception:
        return []


def _tree_get_heading_text(tree: Any, col_id: str) -> str:
    try:
        txt = tree.heading(col_id, option="text")
        return str(txt) if txt else str(col_id)
    except Exception:
        return str(col_id)


# --------------------------------------------------------------------------------------
# Select all
# --------------------------------------------------------------------------------------

def treeview_select_all(tree: Any) -> int:
    """Marker alle rader i en Treeview. Returnerer antall rader som ble markert."""
    if not _tree_is_treeview(tree):
        return 0
    try:
        items = list(tree.get_children())
        if items:
            tree.selection_set(items)
        return len(items)
    except Exception:
        return 0


def listbox_select_all(listbox: Any) -> int:
    """Marker alle elementer i en Listbox. Returnerer antall som ble markert."""
    if not _listbox_is_listbox(listbox):
        return 0
    try:
        n = int(listbox.size())
        if n <= 0:
            return 0
        # Bruk ints (ikke "end") for kompatibilitet med dummy-lister i tester.
        listbox.selection_set(0, n - 1)
        return n
    except Exception:
        return 0


# --------------------------------------------------------------------------------------
# Clipboard copy
# --------------------------------------------------------------------------------------

def treeview_selection_to_tsv(tree: Any, *, include_headers: bool = True) -> str:
    """Kopier markerte rader i Treeview som TSV (Excel-vennlig)."""
    if not _tree_is_treeview(tree):
        return ""

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    cols = _tree_get_columns(tree)
    if not cols:
        return ""

    lines: list[str] = []
    if include_headers:
        headers = [_tree_get_heading_text(tree, c) for c in cols]
        lines.append("\t".join(headers))

    for iid in selected:
        row = []
        for c in cols:
            try:
                v = tree.set(iid, c)
            except Exception:
                v = ""
            row.append("" if v is None else str(v))
        lines.append("\t".join(row))

    return "\n".join(lines)


def listbox_selection_to_lines(listbox: Any) -> str:
    """Kopier markerte elementer i Listbox som linjer."""
    if not _listbox_is_listbox(listbox):
        return ""

    try:
        idxs = list(listbox.curselection())
    except Exception:
        idxs = []

    lines: list[str] = []
    for i in idxs:
        try:
            lines.append(str(listbox.get(i)))
        except Exception:
            continue
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Global install
# --------------------------------------------------------------------------------------

@dataclass
class GlobalHotkeyHandler:
    root: Any

    def on_ctrl_a(self, _event: Any) -> str:
        target = getattr(self.root, "focus_get", lambda: None)()
        if _tree_is_treeview(target):
            treeview_select_all(target)
        elif _listbox_is_listbox(target):
            listbox_select_all(target)
        return "break"

    def on_ctrl_c(self, _event: Any) -> str:
        target = getattr(self.root, "focus_get", lambda: None)()

        if _tree_is_treeview(target):
            txt = treeview_selection_to_tsv(target)
        elif _listbox_is_listbox(target):
            txt = listbox_selection_to_lines(target)
        else:
            txt = ""

        if txt:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(txt)
            except Exception:
                pass
        return "break"


@dataclass
class _Installed:
    handler: Optional[GlobalHotkeyHandler] = None


def _get_install_state(root: Any) -> _Installed:
    st = getattr(root, "_ui_hotkeys_installed", None)
    if isinstance(st, _Installed):
        return st
    st = _Installed()
    try:
        setattr(root, "_ui_hotkeys_installed", st)
    except Exception:
        pass
    return st


def install_global_hotkeys(
    root: Any,
    *,
    enable_ctrl_a: bool = True,
    enable_ctrl_c: bool = True,
    enable_selection_summary: bool = True,
    status_setter: Optional[Callable[[str], None]] = None,
    **_ignored: Any,
) -> Optional[GlobalHotkeyHandler]:
    """Installer globale hotkeys (idempotent).

    `status_setter` er nytt og brukes av selection-summary for å skrive tekst et sted.
    Vi aksepterer også **_ignored for å være robust mot gamle parametre i kall.

    Returnerer handler (for testing), eller eksisterende handler hvis allerede installert.
    """
    if not callable(getattr(root, "bind_all", None)):
        return None

    st = _get_install_state(root)
    if st.handler is None:
        st.handler = GlobalHotkeyHandler(root=root)

        if enable_ctrl_a:
            try:
                root.bind_all("<Control-a>", st.handler.on_ctrl_a, add="+")
                root.bind_all("<Control-A>", st.handler.on_ctrl_a, add="+")
            except Exception:
                pass

        if enable_ctrl_c:
            try:
                root.bind_all("<Control-c>", st.handler.on_ctrl_c, add="+")
                root.bind_all("<Control-C>", st.handler.on_ctrl_c, add="+")
            except Exception:
                pass

    if enable_selection_summary:
        ui_selection_summary.install_global_selection_summary(root, status_setter=status_setter)

    return st.handler


# Re-export summerings-helpers (kjekt å gjenbruke i andre moduler / tester)
guess_sum_columns = ui_selection_summary.guess_sum_columns
treeview_selection_sums = ui_selection_summary.treeview_selection_sums
build_selection_summary_text = ui_selection_summary.build_selection_summary_text


__all__ = [
    "install_global_hotkeys",
    "GlobalHotkeyHandler",
    "treeview_select_all",
    "listbox_select_all",
    "treeview_selection_to_tsv",
    "listbox_selection_to_lines",
    "guess_sum_columns",
    "treeview_selection_sums",
    "build_selection_summary_text",
]
