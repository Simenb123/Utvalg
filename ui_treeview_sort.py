"""Tiny helper for clickable column sorting in ttk.Treeview.

This project has many multi-column "listbox"-style views built with
``ttk.Treeview``. Tkinter does not provide built-in sorting, so we attach a
click handler to each heading.

Usage
-----

```python
from ui_treeview_sort import enable_treeview_sorting

# after you have created the tree + set headings
enable_treeview_sorting(tree)
```

The helper tries to sort numbers as numbers (including Norwegian formatting)
and everything else as case-insensitive text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

import tkinter as tk
from tkinter import ttk


_NBSP_RE = re.compile(r"[\u00a0\u202f]")


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

    We need to be conservative because some cells contain lists like
    "1500, 2700" (motkonto combinations). Those must be treated as text.
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

    pct = False
    if s.endswith("%"):
        pct = True
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
    """Enable click-to-sort on a Treeview.

    Parameters
    ----------
    tree:
        The Treeview to attach sorting to.
    columns:
        Optional list of column ids to make sortable. Defaults to all columns
        in ``tree['columns']``.
    text_key:
        Optional custom key for text sorting. Default is case-insensitive.
    """

    # Store state on widget instance.
    if not hasattr(tree, "_sort_state"):
        tree._sort_state = _SortState()  # type: ignore[attr-defined]

    cols = list(columns) if columns is not None else list(tree["columns"])
    if not cols:
        return

    if text_key is None:
        text_key = lambda s: s.casefold()

    def _on_click(col: str) -> None:
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

    values: list[tuple[Any, str]] = []
    numeric_votes = 0
    non_empty = 0

    for iid in children:
        raw = _clean_cell(tree.set(iid, col))
        if raw:
            non_empty += 1

        num = _parse_number(raw)
        if num is not None:
            numeric_votes += 1
            key: Any = (0, num)  # numbers first
        elif not raw:
            key = (2, 0)  # blanks last
        else:
            key = (1, text_key(raw))
        values.append((key, iid))

    # If almost everything looks numeric -> treat the whole column as numeric.
    # This avoids mixed ordering for columns like "Konto"/"Bilag".
    if non_empty and numeric_votes / non_empty >= 0.8:
        values = []
        for iid in children:
            raw = _clean_cell(tree.set(iid, col))
            num = _parse_number(raw)
            if num is None:
                # Put non-numeric/blanks at the end
                key = (1, float("inf"))
            else:
                key = (0, num)
            values.append((key, iid))

    values.sort(key=lambda t: t[0], reverse=descending)

    for index, (_, iid) in enumerate(values):
        tree.move(iid, "", index)

    # Restore selection/focus.
    if selection:
        tree.selection_set(selection)
    if focus:
        try:
            tree.focus(focus)
        except tk.TclError:
            pass
