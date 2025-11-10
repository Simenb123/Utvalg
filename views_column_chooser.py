
from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from typing import List, Sequence, Tuple

def open_column_chooser(master, all_cols: Sequence[str], visible_cols: Sequence[str], initial_order: Sequence[str]) -> Tuple[List[str], List[str]] | None:
    """Dialog for valg av synlighet og rekkefølge. Returnerer (order, visible) eller None."""
    dialog = tk.Toplevel(master)
    dialog.title("Kolonner"); dialog.transient(master); dialog.grab_set()
    dialog.minsize(540, 360)

    info = ttk.Label(dialog, text=("Velg kolonner og rekkefølge.\n"
                                   "Tips: Pinned-kolonner vises alltid først."),
                     justify="left")
    info.pack(side="top", anchor="w", padx=8, pady=(8,4))

    # filtrer bort interne kolonner (starter med '_')
    cols = [c for c in initial_order if not str(c).startswith("_")]
    for c in all_cols:
        if not str(c).startswith("_") and c not in cols:
            cols.append(c)

    visible = [c for c in visible_cols if not str(c).startswith("_")]

    frame = ttk.Frame(dialog); frame.pack(fill="both", expand=True, padx=8, pady=6)
    frame.columnconfigure(0, weight=1); frame.rowconfigure(0, weight=1)

    tree = ttk.Treeview(frame, columns=("vis","kol"), show="headings", selectmode="browse")
    tree.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview); tree.configure(yscrollcommand=vsb.set)
    vsb.grid(row=0, column=1, sticky="ns")

    tree.heading("vis", text="Vis"); tree.column("vis", width=60, anchor="center")
    tree.heading("kol", text="Kolonne"); tree.column("kol", width=360, anchor="w")

    def refresh_tree():
        tree.delete(*tree.get_children(""))
        for c in cols:
            check = "✓" if c in visible else ""
            tree.insert("", "end", values=(check, c))

    refresh_tree()

    btns = ttk.Frame(dialog); btns.pack(fill="x", padx=8, pady=(6,8))
    def toggle_vis():
        sel = tree.focus()
        if not sel: return
        c = tree.item(sel, "values")[1]
        if c in visible: visible.remove(c)
        else: visible.append(c)
        refresh_tree(); 
        for iid in tree.get_children(""):
            if tree.item(iid, "values")[1]==c: tree.focus(iid); tree.selection_set(iid); break

    def move_up():
        sel = tree.focus()
        if not sel: return
        c = tree.item(sel, "values")[1]
        i = cols.index(c)
        if i>0: cols[i-1], cols[i] = cols[i], cols[i-1]
        refresh_tree()
        for iid in tree.get_children(""):
            if tree.item(iid, "values")[1]==c: tree.focus(iid); tree.selection_set(iid); break

    def move_down():
        sel = tree.focus()
        if not sel: return
        c = tree.item(sel, "values")[1]
        i = cols.index(c)
        if i < len(cols)-1: cols[i+1], cols[i] = cols[i], cols[i+1]
        refresh_tree()
        for iid in tree.get_children(""):
            if tree.item(iid, "values")[1]==c: tree.focus(iid); tree.selection_set(iid); break

    def set_standard():
        nonlocal visible
        visible = list(cols); refresh_tree()

    ttk.Button(btns, text="Vis/Skjul", command=toggle_vis).pack(side="left")
    ttk.Button(btns, text="Opp", command=move_up).pack(side="left", padx=(6,0))
    ttk.Button(btns, text="Ned", command=move_down).pack(side="left", padx=(6,0))
    ttk.Button(btns, text="Standard", command=set_standard).pack(side="left", padx=(12,0))

    def ok():
        dialog.result = (cols, visible); dialog.destroy()
    def cancel():
        dialog.result = None; dialog.destroy()

    ttk.Button(btns, text="Lagre", command=ok).pack(side="right")
    ttk.Button(btns, text="Avbryt", command=cancel).pack(side="right", padx=(0,8))

    dialog.wait_window()
    return getattr(dialog, "result", None)
