from __future__ import annotations

import inspect
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Callable, Mapping, Optional


def _coerce_number(v: str) -> float:
    s = (v or "").strip()
    if not s:
        return 0.0
    # Norsk: "1 234,56" -> 1234.56
    s = s.replace("\u00a0", " ").replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0


def enable_treeview_sort(
    tree: ttk.Treeview,
    types: Optional[Mapping[str, type]] = None,
    *,
    sort_value_fn: Optional[Callable[..., Any]] = None,
) -> None:
    """
    Slår på klikk-sortering på Treeview-headere.

    Bakoverkompatibilitet:
    - Eldre bruk: enable_treeview_sort(tree, {"Sum": float, "Antall": int})
    - Nyere bruk: enable_treeview_sort(tree, sort_value_fn=my_fn)

    sort_value_fn:
      Støtter signatur:
        - fn(value) -> key
        - fn(col, value) -> key
        - fn(col, value, item_id) -> key
    """
    types_map = dict(types or {})
    sort_state: dict[str, bool] = {}  # True=asc, False=desc

    # Finn hvor mange argumenter sort_value_fn forventer (hvis gitt)
    fn_arity = 0
    if sort_value_fn is not None:
        try:
            fn_arity = len(inspect.signature(sort_value_fn).parameters)
        except Exception:
            fn_arity = 2  # safe default

    def key_for(col: str, item_id: str) -> Any:
        raw = tree.set(item_id, col)

        if sort_value_fn is not None:
            try:
                if fn_arity <= 1:
                    return sort_value_fn(raw)  # type: ignore[misc]
                if fn_arity == 2:
                    return sort_value_fn(col, raw)  # type: ignore[misc]
                return sort_value_fn(col, raw, item_id)  # type: ignore[misc]
            except Exception:
                # fall back under
                pass

        t = types_map.get(col)
        if t is int:
            try:
                return int(_coerce_number(raw))
            except Exception:
                return 0
        if t is float:
            return _coerce_number(raw)

        # Default: case-insensitiv tekst
        return (raw or "").lower()

    def on_heading_click(col: str) -> None:
        ascending = sort_state.get(col, True)
        items = list(tree.get_children(""))
        items.sort(key=lambda iid: key_for(col, iid), reverse=not ascending)

        for idx, iid in enumerate(items):
            tree.move(iid, "", idx)

        sort_state[col] = not ascending

    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: on_heading_click(c))


def show_error(title: str, msg: str) -> None:
    messagebox.showerror(title, msg)
