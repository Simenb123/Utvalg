"""ui_treeview_sort.py

Klikk-for-sortering for ``ttk.Treeview``.

Tkinter har ikke innebygd sortering av Treeview-rader. Denne modulen
installerer en heading-handler per kolonne som sorterer radene når
brukeren klikker på kolonneoverskriften.

Heuristikk:
- Tall sorteres som tall (støtter norsk formatering: tusenskiller mellomrom,
  desimal komma, parentes-negativ osv.).
- Dato sorteres som dato (best effort) for vanlige norske og ISO-formater,
  f.eks. "29.09.2025" og "2025-09-29" (og varianter med tid).
- Alt annet sorteres som case-insensitiv tekst.

Modulen er laget for å være robust og liten. Den bruker kun informasjonen
som allerede ligger i Treeview-cellene (strings), og forsøker å gjøre en
fornuftig type-tolkning før den sorterer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Sequence

import tkinter as tk
from tkinter import ttk


_NBSP_RE = re.compile(r"[\u00a0\u202f]")

# Dato-støtte: dd.mm.yyyy (evt. tid) og ISO yyyy-mm-dd (evt. tid)
_DATE_RE_DMY = re.compile(
    r"^(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{2,4})(?:\s+(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?$"
)
_DATE_RE_DMY_SLASH = re.compile(
    r"^(?P<d>\d{1,2})/(?P<m>\d{1,2})/(?P<y>\d{2,4})(?:\s+(?P<h>\d{1,2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?$"
)
_DATE_RE_ISO = re.compile(
    r"^(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})(?:[ T](?P<h>\d{2}):(?P<mi>\d{2})(?::(?P<s>\d{2}))?)?$"
)


def _clean_cell(value: Any) -> str:
    """Return a safe string representation for parsing/sorting."""

    if value is None:
        return ""
    try:
        s = str(value)
    except Exception:
        return ""
    return s.strip()


def _looks_like_number(s: str) -> bool:
    """Heuristic: decide whether a string is probably a number.

    Be conservative: some cells contain lists like "1500, 2700".
    """

    if not s:
        return False

    # Combination strings typically have ", " between account numbers.
    if re.search(r",\s+\d", s):
        return False

    # Allow optional currency/percent suffix.
    s2 = s.lower().replace("nok", "").replace("kr", "").strip()

    # Basic allowed chars.
    if not re.fullmatch(r"[()\-+0-9\s.,%]+", s2):
        return False

    # More than one percent sign or more than one decimal comma is suspicious.
    if s2.count("%") > 1:
        return False
    if s2.count(",") > 1:
        return False

    return True


def _parse_number(s: str) -> float | None:
    """Parse a number from a cell string.

    Supports:
    - Norwegian: "1 234,56" (space thousands, comma decimals)
    - "1.234,56" (dot thousands, comma decimals)
    - plain ints/floats
    - percentages: "12,7%" -> 12.7
    """

    s = _clean_cell(s)
    if not s:
        return None
    if s.lower() in {"nan", "none"}:
        return None

    if not _looks_like_number(s):
        return None

    # Remove currency markers
    s = s.replace("kr", "").replace("KR", "").replace("NOK", "").replace("nok", "")

    # Replace NBSP / narrow NBSP
    s = _NBSP_RE.sub(" ", s)
    s = s.strip()

    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()

    if s.endswith("%"):
        s = s[:-1].strip()

    # Remove spaces (thousands separators)
    s = s.replace(" ", "")

    # If both '.' and ',' are present -> assume '.' thousands + ',' decimals
    if "," in s and "." in s:
        s = s.replace(".", "")
        s = s.replace(",", ".")
    elif "," in s:
        # Only comma -> comma decimals
        s = s.replace(",", ".")

    try:
        v = float(s)
    except Exception:
        return None

    if neg:
        v = -v

    # Note: we sort percentage values as their numeric percent (12.7), not 0.127
    return v


def _year_2_to_4(year: int) -> int:
    """Convert 2-digit year to 4-digit.

    Heuristic: 00-69 => 2000-2069, 70-99 => 1970-1999.
    """

    if year >= 100:
        return year
    return 2000 + year if year <= 69 else 1900 + year


def _dt_to_sort_key(dt: datetime) -> int:
    """Stable numeric sort key for datetime without timezones."""

    return dt.toordinal() * 86400 + dt.hour * 3600 + dt.minute * 60 + dt.second


def _parse_date(s: str) -> int | None:
    """Parse common date formats used in the UI.

    Supports (best effort):
      - dd.mm.yyyy
      - dd.mm.yyyy HH:MM[:SS]
      - dd/mm/yyyy
      - yyyy-mm-dd
      - yyyy-mm-dd HH:MM[:SS]

    Returns an integer sort-key or None.
    """

    s = _clean_cell(s)
    if not s:
        return None

    # Fast reject: avoid treating plain numbers as dates.
    if len(s) < 8:
        return None

    for rx in (_DATE_RE_DMY, _DATE_RE_DMY_SLASH, _DATE_RE_ISO):
        m = rx.fullmatch(s)
        if not m:
            continue

        try:
            d = int(m.group("d"))
            mo = int(m.group("m"))
            y_raw = int(m.group("y"))
            y = _year_2_to_4(y_raw)

            h = int(m.group("h") or 0)
            mi = int(m.group("mi") or 0)
            sec = int(m.group("s") or 0)

            dt = datetime(y, mo, d, h, mi, sec)
            return _dt_to_sort_key(dt)
        except Exception:
            return None

    return None


@dataclass
class _SortState:
    last_col: str | None = None
    descending: bool = False


def enable_treeview_sorting(
    tree: ttk.Treeview,
    *,
    columns: Sequence[str] | None = None,
    text_key: Callable[[str], Any] | None = None,
) -> None:
    """Enable click-to-sort on a Treeview."""

    # Store state on widget instance.
    if not hasattr(tree, "_sort_state"):
        tree._sort_state = _SortState()  # type: ignore[attr-defined]

    cols = list(columns) if columns is not None else list(tree["columns"])
    if not cols:
        return

    if text_key is None:
        text_key = lambda s: s.casefold()

    def _on_click(col: str) -> None:
        if getattr(tree, "_suppress_next_heading_sort", False):
            try:
                tree._suppress_next_heading_sort = False  # type: ignore[attr-defined]
            except Exception:
                pass
            return

        state: _SortState = tree._sort_state  # type: ignore[attr-defined]
        if state.last_col == col:
            state.descending = not state.descending
        else:
            state.last_col = col
            state.descending = False

        _sort_treeview(tree, col, descending=state.descending, text_key=text_key)

    # Attach command to each column header.
    for col in cols:
        try:
            tree.heading(col, command=lambda c=col: _on_click(c))
        except tk.TclError:
            # Some Treeviews may not have the column configured yet.
            continue


def _sort_treeview(
    tree: ttk.Treeview,
    col: str,
    *,
    descending: bool,
    text_key: Callable[[str], Any],
) -> None:
    """Sort Treeview items by a given column."""

    # Preserve selection/focus.
    selection = tree.selection()
    focus = tree.focus()

    children = list(tree.get_children(""))
    if not children:
        return

    parsed: dict[str, tuple[str, Any]] = {}
    non_empty = 0
    numeric_votes = 0
    date_votes = 0

    for iid in children:
        raw = _clean_cell(tree.set(iid, col))
        if raw:
            non_empty += 1

        if not raw:
            parsed[iid] = ("blank", 0)
            continue

        dt_key = _parse_date(raw)
        if dt_key is not None:
            date_votes += 1
            parsed[iid] = ("date", dt_key)
            continue

        num = _parse_number(raw)
        if num is not None:
            numeric_votes += 1
            parsed[iid] = ("num", num)
            continue

        parsed[iid] = ("text", text_key(raw))

    date_mode = bool(non_empty) and (date_votes / non_empty >= 0.8)
    numeric_mode = bool(non_empty) and (numeric_votes / non_empty >= 0.8)

    def _key_date(iid: str) -> tuple[int, Any]:
        t, v = parsed.get(iid, ("blank", 0))
        if t == "date":
            return (0, v)
        if t == "num":
            return (1, v)
        if t == "text":
            return (2, v)
        return (3, 0)

    def _key_numeric(iid: str) -> tuple[int, Any]:
        t, v = parsed.get(iid, ("blank", 0))
        if t == "num":
            return (0, v)
        if t == "text":
            return (1, v)
        if t == "date":
            # Ikke forventet i en "nesten alltid numerisk" kolonne,
            # men vi legger det etter tekst for å unngå type-miks.
            return (2, v)
        return (3, 0)

    def _key_mixed(iid: str) -> tuple[int, Any]:
        t, v = parsed.get(iid, ("blank", 0))
        if t == "date":
            return (0, v)
        if t == "num":
            return (1, v)
        if t == "text":
            return (2, v)
        return (3, 0)

    if date_mode:
        key_fn = _key_date
    elif numeric_mode:
        key_fn = _key_numeric
    else:
        key_fn = _key_mixed

    ordered = sorted(children, key=key_fn, reverse=descending)

    for index, iid in enumerate(ordered):
        tree.move(iid, "", index)

    # Restore selection/focus.
    if selection:
        tree.selection_set(selection)
    if focus:
        try:
            tree.focus(focus)
        except tk.TclError:
            pass
