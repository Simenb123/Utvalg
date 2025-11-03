from __future__ import annotations
import tkinter as tk
from tkinter import ttk

def _parse_numeric(txt: str) -> float:
    if txt is None: return 0.0
    s = str(txt).strip().replace("\u00A0", " ")
    s = s.replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return 0.0

def attach_sorting(tree: ttk.Treeview, col_types: dict[str, str]):
    """
    Legg på klikkbar sortering per kolonne.
    col_types: {"sum": "amount"/"float", "ant": "int", "navn": "str", ...}
    """
    directions = {}

    def sort_by(col: str):
        data = []
        for iid in tree.get_children(""):
            vals = tree.item(iid, "values")
            # Finn index for col
            idx = list(tree["columns"]).index(col)
            v = vals[idx] if idx < len(vals) else ""
            if col_types.get(col) in ("amount", "float", "int"):
                key = _parse_numeric(v)
            else:
                key = str(v).lower()
            data.append((key, iid))
        reverse = directions.get(col, False)
        data.sort(reverse=not reverse)
        directions[col] = not reverse
        for i, (_k, iid) in enumerate(data):
            tree.move(iid, "", i)

    for col in tree["columns"]:
        def handler(c=col):
            sort_by(c)
        tree.heading(col, command=handler)
