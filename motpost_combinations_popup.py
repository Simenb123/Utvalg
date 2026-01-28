"""Popup for visning av motkonto-kombinasjoner.

Denne modulen gir en enkel Toplevel-window med en tabell (Treeview) som viser
motkonto-kombinasjoner.

Den støtter to visninger:
- Samlet for alle valgte kontoer
- Per valgt konto (valgfritt)

Bevisst enkel, slik at den er robust og lett å videreutvikle.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

import tkinter as tk
from tkinter import ttk


def _format_cell(val, col_name: str) -> str:
    """Formatterer verdier til en lesbar streng."""

    if pd.isna(val):
        return ""

    if isinstance(val, float):
        # Percent/andel
        if "andel" in col_name.lower() or col_name.strip().startswith("%"):
            return f"{val:.1f}%"

        # Money-ish
        return f"{val:,.2f}".replace(",", " ").replace(".", ",")

    return str(val)


def _build_tree(parent: tk.Widget, df: pd.DataFrame) -> ttk.Treeview:
    """Bygger en Treeview med alle rader i df."""

    cols = list(df.columns)

    tree = ttk.Treeview(parent, columns=cols, show="headings", height=18)
    for c in cols:
        tree.heading(c, text=c)
        tree.column(c, width=140, anchor="w", stretch=True)

    for _, row in df.iterrows():
        values = [_format_cell(row[c], c) for c in cols]
        tree.insert("", "end", values=values)

    return tree


def _render_df(container: tk.Widget, df: Optional[pd.DataFrame], *, empty_text: str) -> None:
    """Renderer df i container (eller en tekst hvis df er tom)."""

    for w in container.winfo_children():
        w.destroy()

    if df is None or df.empty:
        ttk.Label(container, text=empty_text).pack(anchor="w", padx=8, pady=8)
        return

    tree = _build_tree(container, df)

    vsb = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(container, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

    tree.grid(row=0, column=0, sticky="nsew")
    vsb.grid(row=0, column=1, sticky="ns")
    hsb.grid(row=1, column=0, sticky="ew")

    container.grid_rowconfigure(0, weight=1)
    container.grid_columnconfigure(0, weight=1)


def show_motkonto_combinations_popup(
    parent: tk.Widget,
    *,
    df_combos: pd.DataFrame,
    df_combo_per_selected: Optional[pd.DataFrame] = None,
    title: str = "Motkonto-kombinasjoner",
    summary: Optional[str] = None,
) -> None:
    """Åpner popup med kombinasjoner."""

    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry("1100x600")
    win.transient(parent)
    win.grab_set()

    outer = ttk.Frame(win, padding=8)
    outer.pack(fill=tk.BOTH, expand=True)

    if summary:
        ttk.Label(outer, text=summary).pack(anchor="w", pady=(0, 8))

    nb = ttk.Notebook(outer)
    nb.pack(fill=tk.BOTH, expand=True)

    tab_all = ttk.Frame(nb)
    nb.add(tab_all, text="Alle valgte kontoer")
    _render_df(tab_all, df_combos, empty_text="Ingen kombinasjoner i grunnlaget.")

    tab_per = ttk.Frame(nb)
    nb.add(tab_per, text="Per valgt konto")
    _render_df(tab_per, df_combo_per_selected, empty_text="Ingen data per valgt konto.")

    btn_row = ttk.Frame(outer)
    btn_row.pack(fill=tk.X, pady=(8, 0))

    ttk.Button(btn_row, text="Lukk", command=win.destroy).pack(side=tk.RIGHT)
