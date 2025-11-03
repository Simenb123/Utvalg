from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import datetime
from formatting import parse_amount

def enable_treeview_sort(tree: ttk.Treeview, types: dict[str, str]) -> None:
    """Klikk på kolonneoverskrift for å sortere. types: {"col": "int|amount|date|text"}"""
    def _sort(col, reverse):
        rows = [(tree.set(k, col), k) for k in tree.get_children("")]
        typ = types.get(col, "text")
        if typ == "int":
            conv = lambda x: int(str(x).replace(" ", "") or 0)
        elif typ == "amount":
            conv = lambda x: parse_amount(x) or 0.0
        elif typ == "date":
            conv = lambda x: datetime.strptime(str(x), "%d.%m.%Y") if x else datetime.min
        else:
            conv = lambda x: str(x)
        rows.sort(key=lambda t: conv(t[0]), reverse=reverse)
        for index, (_, k) in enumerate(rows):
            tree.move(k, "", index)
        tree.heading(col, command=lambda: _sort(col, not reverse))
    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: _sort(c, False))
