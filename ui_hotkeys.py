"""ui_hotkeys.py

Globale hotkeys + kopiering til clipboard + (valgfritt) selection-summary.

Hotkeys:
  - Ctrl+A: marker alle rader i aktiv Treeview/Listbox
  - Ctrl+C: kopier markerte rader til clipboard
      - Treeview: TSV *uten* header (Excel-vennlig ved liming i forhåndsmarkert område)
      - Listbox: én linje per element
  - Ctrl+Shift+C: kopier Treeview *med* header (kolonnenavn)

Selection summary:
  - Valgfritt, men default ON.
  - Bruker `ui_selection_summary` for å vise antall + sum av relevante beløpskolonner.

Design:
- Duck typing: fungerer i pytest uten Tk-vindu.
- Idempotent install: kan kalles flere ganger.
- Ikke “stjel” Ctrl+A/C i tekstfelt: vi returnerer kun "break" når vi faktisk håndterer
  Treeview/Listbox, ellers lar vi default oppførsel fungere (Entry/Text).
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


def _sanitize_cell_text(v: Any) -> str:
    """Saniter celler slik at TSV blir rektangulær og Excel-vennlig.

    - Tabulatorer og linjeskift i celler vil ellers gi ekstra kolonner/rader.
    """
    if v is None:
        return ""
    s = str(v)
    # Standardiser NBSP og fjern tab/linjeskift
    s = s.replace("\u00A0", " ")
    s = s.replace("\t", " ")
    s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return s


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

def treeview_selection_to_tsv(tree: Any, *, include_headers: bool = False) -> str:
    """Kopier markerte rader i Treeview som TSV (Excel-vennlig)."""
    if not _tree_is_treeview(tree):
        return ""

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    cols = _tree_get_columns(tree)
    if not cols or not selected:
        return ""

    lines: list[str] = []
    if include_headers:
        headers = [_sanitize_cell_text(_tree_get_heading_text(tree, c)) for c in cols]
        lines.append("\t".join(headers))

    for iid in selected:
        row = []
        for c in cols:
            try:
                v = tree.set(iid, c)
            except Exception:
                v = ""
            row.append(_sanitize_cell_text(v))
        lines.append("\t".join(row))

    # Excel på Windows liker CRLF best, men splitlines() håndterer begge i tester.
    return "\r\n".join(lines)


def listbox_selection_to_lines(listbox: Any) -> str:
    """Kopier markerte elementer i Listbox som linjer."""
    if not _listbox_is_listbox(listbox):
        return ""

    try:
        idxs = list(listbox.curselection())
    except Exception:
        idxs = []

    if not idxs:
        return ""

    lines: list[str] = []
    for i in idxs:
        try:
            lines.append(_sanitize_cell_text(listbox.get(i)))
        except Exception:
            continue

    return "\r\n".join(lines)


# --------------------------------------------------------------------------------------
# Global install
# --------------------------------------------------------------------------------------

@dataclass
class GlobalHotkeyHandler:
    root: Any

    def on_ctrl_a(self, _event: Any) -> str | None:
        target = getattr(self.root, "focus_get", lambda: None)()
        if _tree_is_treeview(target):
            treeview_select_all(target)
            return "break"
        if _listbox_is_listbox(target):
            listbox_select_all(target)
            return "break"
        # Ikke en liste-widget: la standard Ctrl+A oppførsel (f.eks. Entry) fungere.
        return None

    def _copy_to_clipboard(self, txt: str) -> None:
        if not txt:
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
        except Exception:
            # Clipboard kan feile i enkelte test-/CI-miljøer.
            pass

    def on_ctrl_c(self, _event: Any) -> str | None:
        """Ctrl+C: kopier uten header."""
        target = getattr(self.root, "focus_get", lambda: None)()

        if _tree_is_treeview(target):
            txt = treeview_selection_to_tsv(target, include_headers=False)
        elif _listbox_is_listbox(target):
            txt = listbox_selection_to_lines(target)
        else:
            # Ikke en liste-widget: la standard Ctrl+C (kopier tekst i Entry/Text) fungere.
            return None

        self._copy_to_clipboard(txt)
        return "break"

    def on_ctrl_shift_c(self, _event: Any) -> str | None:
        """Ctrl+Shift+C: kopier med header (Treeview)."""
        target = getattr(self.root, "focus_get", lambda: None)()
        if _tree_is_treeview(target):
            txt = treeview_selection_to_tsv(target, include_headers=True)
            self._copy_to_clipboard(txt)
            return "break"
        return None


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

    `status_setter` brukes av selection-summary for å skrive tekst et sted.
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
                # Ctrl+C (uten shift) -> uten header
                root.bind_all("<Control-c>", st.handler.on_ctrl_c, add="+")
                # Ctrl+Shift+C -> med header
                root.bind_all("<Control-C>", st.handler.on_ctrl_shift_c, add="+")
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
