from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any

def enable_treeview_sort(tree: ttk.Treeview, types: Dict[str, str]) -> None:
    sort_state = {}
    def key_for(col: str, v: str) -> Any:
        t = types.get(col, "text")
        s = (v or "").strip()
        if t == "int":
            try: return int(s.replace(" ", ""))
            except Exception: return 0
        if t == "amount":
            try: return float(s.replace(" ", "").replace(".", "").replace(",", "."))
            except Exception: return 0.0
        return s.lower()
    def on_click(col: str):
        items = [(iid, tree.set(iid, col)) for iid in tree.get_children("")]
        items.sort(key=lambda pair: key_for(col, pair[1]), reverse=sort_state.get(col, False))
        for idx, (iid, _v) in enumerate(items):
            tree.move(iid, "", idx)
        sort_state[col] = not sort_state.get(col, False)
    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: on_click(c))