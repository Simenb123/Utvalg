from __future__ import annotations
import tkinter as tk
from tkinter import ttk

def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    bg = "#F5F4EF"
    surface = "#FFFDF8"
    border = "#D7D1C7"
    fg = "#1F2430"
    muted = "#667085"
    accent = "#2F6D62"
    accent_hover = "#24564D"
    accent_soft = "#E5F1EE"
    warning = "#9F5B2E"
    warning_soft = "#FCEBD9"
    success = "#256D5A"
    success_soft = "#E2F1EB"

    try:
        root.configure(background=bg)
    except Exception:
        pass

    style.configure(".", background=bg, foreground=fg, font=("Segoe UI", 10))
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=surface)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Muted.TLabel", background=bg, foreground=muted)
    style.configure("Section.TLabel", background=bg, foreground=fg, font=("Segoe UI", 10, "bold"))
    style.configure("Status.TLabel", background=bg, foreground=muted)
    style.configure("Ready.TLabel", background=success_soft, foreground=success, padding=(8, 4))
    style.configure("Warning.TLabel", background=warning_soft, foreground=warning, padding=(8, 4))

    style.configure("TLabelframe", background=bg, bordercolor=border, relief="solid")
    style.configure("TLabelframe.Label", background=bg, foreground=fg, font=("Segoe UI", 10, "bold"))

    style.configure(
        "TButton",
        padding=(10, 6),
        background=surface,
        foreground=fg,
        bordercolor=border,
    )
    style.map(
        "TButton",
        background=[("active", "#F0ECE3"), ("pressed", "#E7E1D5")],
        bordercolor=[("focus", accent)],
    )
    style.configure(
        "Primary.TButton",
        padding=(12, 7),
        background=accent,
        foreground="#FFFFFF",
        bordercolor=accent,
    )
    style.map(
        "Primary.TButton",
        background=[("active", accent_hover), ("pressed", accent_hover), ("disabled", "#B8C9C5")],
        foreground=[("disabled", "#F7FAF9")],
    )
    style.configure(
        "Secondary.TButton",
        padding=(10, 6),
        background=accent_soft,
        foreground=accent,
        bordercolor=accent_soft,
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#D8EAE4"), ("pressed", "#CDE3DB")],
    )

    style.configure(
        "TEntry",
        fieldbackground="#FFFFFF",
        background="#FFFFFF",
        foreground=fg,
        bordercolor=border,
        insertcolor=fg,
    )
    style.configure(
        "TCombobox",
        fieldbackground="#FFFFFF",
        background="#FFFFFF",
        foreground=fg,
        bordercolor=border,
        arrowsize=14,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", "#FFFFFF"), ("disabled", "#F3F0E8")],
        foreground=[("disabled", muted)],
    )

    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background="#ECE7DD",
        foreground=fg,
        padding=(12, 7),
        font=("Segoe UI", 10),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", surface), ("active", "#F3EFE7")],
    )

    style.configure("Treeview", rowheight=24, font=("Segoe UI", 10), background="#FFFFFF", fieldbackground="#FFFFFF")
    style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
