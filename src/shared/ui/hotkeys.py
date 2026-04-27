"""ui_hotkeys.py

Globale hotkeys + kopiering til clipboard + (valgfritt) selection-summary.

Hotkeys:
  - Ctrl+A: marker alle rader i aktiv Treeview/Listbox
  - Ctrl+C: kopier markerte rader til clipboard
      - Treeview: TSV *med* header (Excel-vennlig ved liming til tomt område)
      - Listbox: én linje per element
  - Ctrl+Shift+C: kopier markerte rader til clipboard (samme som Ctrl+C)

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
import math
from typing import Any, Callable, Optional

from . import selection_summary as ui_selection_summary


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


def _tree_get_visible_columns(tree: Any) -> list[str]:
    """Returner kun kolonner som faktisk er synlige i treet.

    Tk Treeview lagrer alle kolonner i tree["columns"], men kan begrense
    hvilke som vises via tree["displaycolumns"]. Returverdien respekterer
    rekkefølgen i displaycolumns slik at copy-paste matcher GUI.

    Faller tilbake til alle kolonner hvis displaycolumns mangler eller er
    satt til "#all".
    """
    all_cols = _tree_get_columns(tree)
    if not all_cols:
        return []
    try:
        disp = tree["displaycolumns"]  # type: ignore[index]
    except Exception:
        return all_cols
    try:
        disp_list = list(disp)
    except TypeError:
        disp_list = [disp]
    disp_strs = [str(c) for c in disp_list if str(c).strip()]
    if not disp_strs or "#all" in disp_strs:
        return all_cols
    # Filtrer til IDs som faktisk finnes (defensivt mot stale displaycolumns)
    visible = [c for c in disp_strs if c in all_cols]
    return visible if visible else all_cols


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

    # Treat NaN/NA-like as empty (common when Treeview is populated from pandas)
    try:
        if isinstance(v, float) and math.isnan(v):
            return ""
    except Exception:
        pass

    s = str(v)
    if s.strip().lower() in {"nan", "none", "null", "na", "nat"}:
        return ""
    # Standardiser NBSP og fjern tab/linjeskift
    s = s.replace("\u00A0", " ")
    s = s.replace("\t", " ")
    s = s.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    return s.strip()


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

def treeview_selection_to_tsv(tree: Any) -> str:
    """Kopier markerte rader i Treeview som TSV (Excel-vennlig), alltid med header.

    Tar kun med kolonner som faktisk er synlige i GUI (respekterer
    displaycolumns). Skjulte kolonner ekskluderes — det brukeren ser i
    GUI er det som havner på utklippstavlen.
    """
    if not _tree_is_treeview(tree):
        return ""

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    cols = _tree_get_visible_columns(tree)
    if not cols or not selected:
        return ""

    lines: list[str] = []

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

    # Viktig: Bruk kun LF (\n) i tekst vi legger på Tk-clipboard.
    # På Windows kan Tk gjøre egen CRLF-normalisering. Hvis vi allerede har CRLF kan
    # det i praksis ende opp som CRCRLF og gi "tomme rader" ved liming i Excel.
    return "\n".join(lines)


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

    return "\n".join(lines)


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

        # Normaliser linjeskift for å unngå blanklinjer ved liming i Excel (Windows)
        txt = str(txt).replace("\r\n", "\n").replace("\r", "\n")

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(txt)
        except Exception:
            # Clipboard kan feile i enkelte test-/CI-miljøer.
            pass

    def on_ctrl_c(self, _event: Any) -> str | None:
        """Ctrl+C (og Ctrl+Shift+C): kopier med header (Treeview)."""
        target = getattr(self.root, "focus_get", lambda: None)()

        if _tree_is_treeview(target):
            txt = treeview_selection_to_tsv(target)
        elif _listbox_is_listbox(target):
            txt = listbox_selection_to_lines(target)
        else:
            # Ikke en liste-widget: la standard Ctrl+C (kopier tekst i Entry/Text) fungere.
            return None

        self._copy_to_clipboard(txt)
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
    selection_summary_require_opt_in: bool = False,
    **_ignored: Any,
) -> Optional[GlobalHotkeyHandler]:
    """Installer globale hotkeys (idempotent).

    `status_setter` brukes av selection-summary for å skrive tekst et sted.
    `selection_summary_require_opt_in` sendes videre til selection-summary slik
    at bare eksplisitt registrerte Treeviews bidrar til footeren.

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
                # Ctrl+C / Ctrl+Shift+C -> kopier med header
                root.bind_all("<Control-c>", st.handler.on_ctrl_c, add="+")
                root.bind_all("<Control-C>", st.handler.on_ctrl_c, add="+")
            except Exception:
                pass

    if enable_selection_summary:
        ui_selection_summary.install_global_selection_summary(
            root,
            status_setter=status_setter,
            require_opt_in=selection_summary_require_opt_in,
        )

    return st.handler


# --------------------------------------------------------------------------------------
# Column autofit (dobbeltklikk på header-separator)
# --------------------------------------------------------------------------------------

def _autofit_column(tree: Any, col_id: str) -> None:
    """Autofit en Treeview-kolonne basert på synlig innhold."""
    try:
        heading_text = _tree_get_heading_text(tree, col_id)
        max_len = len(heading_text)

        for idx, iid in enumerate(tree.get_children("")):
            if idx >= 200:
                break
            try:
                val = str(tree.set(iid, col_id)).strip()
                if val and val.lower() not in ("nan", "none"):
                    max_len = max(max_len, min(len(val), 60))
            except Exception:
                continue
            # Sjekk barn (for hierarkiske trær)
            for child_iid in tree.get_children(iid):
                if idx >= 200:
                    break
                try:
                    val = str(tree.set(child_iid, col_id)).strip()
                    if val and val.lower() not in ("nan", "none"):
                        max_len = max(max_len, min(len(val), 60))
                except Exception:
                    continue

        # ~8px per tegn + padding
        new_width = max(30, min(500, (max_len * 8) + 24))
        tree.column(col_id, width=new_width)
    except Exception:
        pass


def _install_autofit_on_tree(tree: Any) -> None:
    """Bind dobbeltklikk på header-separator til autofit."""
    if not _tree_is_treeview(tree):
        return
    if getattr(tree, "_autofit_installed", False):
        return

    def _on_header_double(event: Any) -> None:
        region = ""
        try:
            region = tree.identify_region(event.x, event.y)
        except Exception:
            return
        if region == "separator":
            try:
                col_id = tree.identify_column(event.x)
                # col_id er f.eks. "#1" — oversett til kolonne-id
                if col_id and col_id.startswith("#"):
                    col_num = int(col_id[1:])
                    cols = _tree_get_columns(tree)
                    if 0 < col_num <= len(cols):
                        _autofit_column(tree, cols[col_num - 1])
            except Exception:
                pass

    try:
        tree.bind("<Double-1>", _on_header_double, add="+")
        tree._autofit_installed = True  # type: ignore[attr-defined]
    except Exception:
        pass


def install_autofit_all(root: Any) -> None:
    """Installer autofit på alle eksisterende og fremtidige Treeview-widgets.

    Bruker after() for å periodisk sjekke nye treeviews (enkel tilnærming
    uten å hookte widget-opprettelse).
    """
    _seen: set[int] = set()

    def _scan() -> None:
        try:
            _scan_children(root)
        except Exception:
            pass
        try:
            root.after(3000, _scan)
        except Exception:
            pass

    def _scan_children(widget: Any) -> None:
        try:
            for child in widget.winfo_children():
                wid = id(child)
                if wid not in _seen and _tree_is_treeview(child):
                    _seen.add(wid)
                    _install_autofit_on_tree(child)
                _scan_children(child)
        except Exception:
            pass

    # Kjør første scan etter at GUI er bygget opp
    try:
        root.after(500, _scan)
    except Exception:
        pass


# Re-export summerings-helpers (kjekt å gjenbruke i andre moduler / tester)
guess_sum_columns = ui_selection_summary.guess_sum_columns
treeview_selection_sums = ui_selection_summary.treeview_selection_sums
build_selection_summary_text = ui_selection_summary.build_selection_summary_text
register_treeview_selection_summary = ui_selection_summary.register_treeview_selection_summary


__all__ = [
    "install_global_hotkeys",
    "install_autofit_all",
    "GlobalHotkeyHandler",
    "treeview_select_all",
    "listbox_select_all",
    "treeview_selection_to_tsv",
    "listbox_selection_to_lines",
    "guess_sum_columns",
    "treeview_selection_sums",
    "build_selection_summary_text",
    "register_treeview_selection_summary",
]
