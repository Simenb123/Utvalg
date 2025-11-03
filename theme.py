from __future__ import annotations
import tkinter as tk
from tkinter import ttk

def setup_theme(root: tk.Tk) -> None:
    """
    Lett 'Azure'-inspirert ttk-stil uten eksterne temaer.
    Gir ryddig blå aksent, tydelige tabeller og polstring.
    """
    style = ttk.Style(root)
    # Bruk 'clam' for god Treeview-støtte
    try:
        style.theme_use("clam")
    except Exception:
        pass

    # Farger
    ACCENT = "#2962FF"   # blå aksent
    BG     = "#F5F6FA"
    FG     = "#222"
    ALTBG  = "#E9ECF5"

    root.configure(background=BG)
    style.configure(".", background=BG, foreground=FG, font=("Segoe UI", 10))
    style.configure("TLabel", background=BG)
    style.configure("TFrame", background=BG)
    style.configure("TLabelframe", background=BG)
    style.configure("TLabelframe.Label", background=BG, font=("Segoe UI Semibold", 10))

    style.configure("TButton", padding=6)
    style.map("TButton",
              background=[("active", "#3D74FF")],
              foreground=[("active", "white")])

    # Notebook
    style.configure("TNotebook", background=BG, tabmargins=[10, 4, 10, 0])
    style.configure("TNotebook.Tab", padding=[16, 8], background=ALTBG)
    style.map("TNotebook.Tab",
              background=[("selected", "white")],
              expand=[("selected", [1, 1, 1, 0])])

    # Treeview
    style.configure("Treeview",
                    background="white", fieldbackground="white",
                    rowheight=24, bordercolor="#D0D4E0", borderwidth=1)
    style.configure("Treeview.Heading", font=("Segoe UI Semibold", 10))
    style.map("Treeview",
              background=[("selected", "#DDE7FF")],
              foreground=[("selected", "black")])
