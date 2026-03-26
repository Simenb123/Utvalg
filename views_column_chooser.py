from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Sequence, Tuple


def _clean_columns(items: Sequence[str] | None) -> List[str]:
    return [str(c) for c in (items or []) if str(c).strip() and not str(c).startswith("_")]


def open_column_chooser(
    master,
    all_cols: Sequence[str],
    visible_cols: Sequence[str],
    initial_order: Sequence[str],
    *,
    default_visible_cols: Sequence[str] | None = None,
    default_order: Sequence[str] | None = None,
) -> Tuple[List[str], List[str]] | None:
    """Dialog for valg av synlighet og rekkefølge.

    Returnerer ``(order, visible)`` eller ``None``.
    """

    dialog = tk.Toplevel(master)
    dialog.title("Kolonner")
    dialog.transient(master)
    dialog.grab_set()
    dialog.minsize(540, 360)

    info = ttk.Label(
        dialog,
        text=(
            "Velg kolonner og rekkefølge.\n"
            "Tips: Pinned-kolonner vises alltid først."
        ),
        justify="left",
    )
    info.pack(side="top", anchor="w", padx=8, pady=(8, 4))

    cols = _clean_columns(initial_order)
    for c in _clean_columns(all_cols):
        if c not in cols:
            cols.append(c)

    visible = [c for c in _clean_columns(visible_cols) if c in cols]

    default_cols = [c for c in _clean_columns(default_order) if c in cols]
    for c in cols:
        if c not in default_cols:
            default_cols.append(c)

    default_visible = [c for c in _clean_columns(default_visible_cols or visible_cols) if c in default_cols]

    frame = ttk.Frame(dialog)
    frame.pack(fill="both", expand=True, padx=8, pady=6)
    frame.columnconfigure(0, weight=1)
    frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(frame, columns=("vis", "kol"), show="headings", selectmode="browse")
    tree.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    vsb.grid(row=0, column=1, sticky="ns")

    tree.heading("vis", text="Vis")
    tree.column("vis", width=60, anchor="center")
    tree.heading("kol", text="Kolonne")
    tree.column("kol", width=360, anchor="w")

    def refresh_tree() -> None:
        tree.delete(*tree.get_children(""))
        for c in cols:
            check = "✓" if c in visible else ""
            tree.insert("", "end", values=(check, c))

    refresh_tree()

    btns = ttk.Frame(dialog)
    btns.pack(fill="x", padx=8, pady=(6, 8))

    def _restore_focus(col_name: str) -> None:
        for iid in tree.get_children(""):
            if tree.item(iid, "values")[1] == col_name:
                tree.focus(iid)
                tree.selection_set(iid)
                break

    def toggle_vis() -> None:
        sel = tree.focus()
        if not sel:
            return
        c = tree.item(sel, "values")[1]
        if c in visible:
            visible.remove(c)
        else:
            visible.append(c)
        refresh_tree()
        _restore_focus(c)

    def move_up() -> None:
        sel = tree.focus()
        if not sel:
            return
        c = tree.item(sel, "values")[1]
        i = cols.index(c)
        if i > 0:
            cols[i - 1], cols[i] = cols[i], cols[i - 1]
        refresh_tree()
        _restore_focus(c)

    def move_down() -> None:
        sel = tree.focus()
        if not sel:
            return
        c = tree.item(sel, "values")[1]
        i = cols.index(c)
        if i < len(cols) - 1:
            cols[i + 1], cols[i] = cols[i], cols[i + 1]
        refresh_tree()
        _restore_focus(c)

    def set_standard() -> None:
        nonlocal cols, visible
        cols = list(default_cols)
        visible = list(default_visible)
        refresh_tree()

    ttk.Button(btns, text="Vis/Skjul", command=toggle_vis).pack(side="left")
    ttk.Button(btns, text="Opp", command=move_up).pack(side="left", padx=(6, 0))
    ttk.Button(btns, text="Ned", command=move_down).pack(side="left", padx=(6, 0))
    ttk.Button(btns, text="Standard", command=set_standard).pack(side="left", padx=(12, 0))

    def ok() -> None:
        dialog.result = (cols, visible)
        dialog.destroy()

    def cancel() -> None:
        dialog.result = None
        dialog.destroy()

    ttk.Button(btns, text="Lagre", command=ok).pack(side="right")
    ttk.Button(btns, text="Avbryt", command=cancel).pack(side="right", padx=(0, 8))

    dialog.wait_window()
    return getattr(dialog, "result", None)
