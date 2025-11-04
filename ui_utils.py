from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any
from formatting import parse_amount

def enable_treeview_sort(tree: ttk.Treeview, types: Dict[str, str]) -> None:
    sort_state = {}
    def sort_by(col: str):
        items = [(iid, tree.set(iid, col)) for iid in tree.get_children("")]
        t = types.get(col, "text")
        def keyfun(v: str) -> Any:
            if t == "int":
                try: return int(str(v).replace(" ", ""))
                except Exception: return 0
            if t == "amount":
                try:
                    s = (v or "").replace(" ", "").replace("kr","").replace("\u00A0","").replace(".", "").replace(",", ".")
                    return float(s)
                except Exception:
                    return 0.0
            if t == "date":
                return v
            return str(v).lower()
        items.sort(key=lambda pair: keyfun(pair[1]), reverse=sort_state.get(col, False))
        for idx, (iid, _v) in enumerate(items):
            tree.move(iid, "", idx)
        sort_state[col] = not sort_state.get(col, False)
    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: sort_by(c))
