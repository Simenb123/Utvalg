from __future__ import annotations
import tkinter as tk
from tkinter import ttk
def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try: style.theme_use("clam")
    except Exception: pass
    accent = "#2D7FF9"; bg = "#F5F7FB"; fg = "#1F2430"
    style.configure(".", background=bg, foreground=fg)
    style.configure("TFrame", background=bg); style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TButton", padding=6); style.map("TButton", foreground=[("active", fg)], background=[("active", "#E6EEF9")])
    style.configure("Treeview", rowheight=22, font=("Segoe UI", 10)); style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
    style.configure("TNotebook", background=bg); style.configure("TNotebook.Tab", padding=(12, 6, 12, 6))
    style.map("TNotebook.Tab", background=[("selected", "#FFFFFF")], foreground=[("selected", "#000000")])
