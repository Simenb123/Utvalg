"""dataset_pane_ui.py

UI-bygger for DatasetPane.

Holdes separat for å holde dataset_pane.py under kontroll og gjøre det enklere å
vedlikeholde. GUI testes ikke i headless CI.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import tkinter as tk
from tkinter import ttk


def build_ui(
    pane,
    *,
    title: str,
    canon_fields: List[str],
) -> Tuple[ttk.Combobox, ttk.Label, Dict[str, tk.StringVar], Dict[str, ttk.Combobox]]:
    """Bygg UI og returner (sheet_combo, status_lbl, combo_vars, combo_widgets)."""

    top = ttk.Frame(pane)
    top.pack(fill="x", padx=8, pady=(8, 4))
    top.columnconfigure(1, weight=1)

    ttk.Label(top, text=f"{title}:").grid(row=0, column=0, sticky="w")
    ttk.Entry(top, textvariable=pane.path_var).grid(row=0, column=1, sticky="ew", padx=4)
    ttk.Button(top, text="Bla…", command=pane._choose_file).grid(row=0, column=2, padx=2)
    ttk.Button(top, text="Forhåndsvis", command=pane._preview).grid(row=0, column=3, padx=2)

    ttk.Label(top, text="Ark:").grid(row=1, column=0, sticky="w", pady=(6, 0))
    sheet_combo = ttk.Combobox(top, textvariable=pane.sheet_var, state="disabled")
    sheet_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
    sheet_combo.bind("<<ComboboxSelected>>", pane._on_sheet_selected)

    ttk.Label(top, text="Header-rad:").grid(row=1, column=2, sticky="e", pady=(6, 0))
    ent_hdr = ttk.Entry(top, textvariable=pane.header_row_var, width=6)
    ent_hdr.grid(row=1, column=3, sticky="w", padx=2, pady=(6, 0))
    ent_hdr.bind("<Return>", lambda _e: pane._load_headers())
    ent_hdr.bind("<FocusOut>", lambda _e: pane._load_headers())
    ttk.Button(top, text="Gjett header", command=lambda: pane._load_headers(auto_detect=True)).grid(
        row=1, column=4, padx=2, pady=(6, 0)
    )

    mapf = ttk.LabelFrame(pane, text="Kolonnekart (mapping)", padding=8)
    mapf.pack(fill="x", padx=8, pady=(4, 4))
    mapf.columnconfigure(1, weight=1)

    combo_vars: Dict[str, tk.StringVar] = {}
    combo_widgets: Dict[str, ttk.Combobox] = {}
    for r, canon in enumerate(canon_fields):
        ttk.Label(mapf, text=f"{canon}:").grid(row=r, column=0, sticky="w", pady=1)
        var = tk.StringVar(value="")
        # height=... styrer hvor mange rader som vises i rullgardinen.
        # Litt høyere gir bedre oversikt når det er mange kolonner.
        cb = ttk.Combobox(mapf, textvariable=var, state="readonly", values=("",), height=24)
        cb.grid(row=r, column=1, sticky="ew", padx=(4, 0), pady=1)
        combo_vars[canon] = var
        combo_widgets[canon] = cb

    btn = ttk.Frame(pane)
    btn.pack(fill="x", padx=8, pady=(0, 8))
    ttk.Button(btn, text="Gjett mapping", command=pane._guess_mapping).pack(side="left")
    ttk.Button(btn, text="Bygg datasett", command=pane._build_dataset_clicked).pack(side="left", padx=(6, 0))

    status_lbl = ttk.Label(
        pane,
        text="Velg fil. Header/mapping lastes automatisk. Kontroller mapping. Bygg datasett.",
    )
    status_lbl.pack(fill="x", padx=8, pady=(0, 8))

    return sheet_combo, status_lbl, combo_vars, combo_widgets
