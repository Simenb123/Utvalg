from __future__ import annotations
import pandas as pd
import tkinter as tk
from tkinter import ttk

from formatting import parse_amount, fmt_date

def enable_treeview_sort(tree: ttk.Treeview, col_types: dict[str, str]) -> None:
    """
    col_types: {"kolnavn": "int"|"amount"|"date"|"text", ...}
    """
    def sorter(col: str, reverse: bool) -> None:
        items = [(tree.set(k, col), k) for k in tree.get_children("")]
        typ = (col_types or {}).get(col, "text")

        def key_func(val: tuple[str, str]):
            s = val[0]
            if typ == "int":
                try:
                    return int(str(s).replace(" ", "").replace("\xa0", ""))
                except Exception:
                    return 0
            if typ == "amount":
                v = parse_amount(s)
                return v if v is not None else 0.0
            if typ == "date":
                try:
                    d = pd.to_datetime(s, dayfirst=True, errors="coerce")
                    return d.to_datetime64()
                except Exception:
                    return pd.NaT
            return str(s).lower()

        items.sort(key=key_func, reverse=reverse)
        for idx, (_, k) in enumerate(items):
            tree.move(k, "", idx)
        # toggle next
        tree.heading(col, command=lambda: sorter(col, not reverse))

    for col in tree["columns"]:
        tree.heading(col, command=lambda c=col: sorter(c, False))
