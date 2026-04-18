"""dataset_pane_ui.py

UI-bygger for DatasetPane.

Holdes separat for å holde dataset_pane.py under kontroll og gjøre det enklere å
vedlikeholde. GUI testes ikke i headless CI.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

import tkinter as tk
from tkinter import ttk

# Vanlige valgfrie felt som vises alltid (brukes aktivt av revisor)
_COMMON_OPTIONAL = {"Kontonavn", "Dato", "Tekst", "Referanse"}


def build_ui(
    pane,
    *,
    title: str,
    canon_fields: List[str],
) -> Tuple[ttk.Combobox, ttk.Label, Dict[str, tk.StringVar], Dict[str, ttk.Combobox]]:
    """Bygg UI og returner (sheet_combo, status_lbl, combo_vars, combo_widgets)."""

    required_fields = ["Konto", "Bilag", "Beløp"]
    common_optional = [f for f in canon_fields if f not in required_fields and f in _COMMON_OPTIONAL]
    advanced_optional = [f for f in canon_fields if f not in required_fields and f not in _COMMON_OPTIONAL]

    top = ttk.LabelFrame(pane, text="Fil", padding=10)
    top.pack(fill="x", padx=8, pady=(8, 6))
    top.columnconfigure(1, weight=1)

    ttk.Label(top, text=f"{title}:").grid(row=0, column=0, sticky="w")
    ttk.Entry(top, textvariable=pane.path_var).grid(row=0, column=1, sticky="ew", padx=4)
    ttk.Button(top, text="Velg fil...", style="Secondary.TButton", command=pane._choose_file).grid(
        row=0, column=2, padx=2
    )
    ttk.Button(top, text="Forhåndsvis", style="Secondary.TButton", command=pane._preview).grid(
        row=0, column=3, padx=2
    )

    sheet_label = ttk.Label(top, text="Ark:")
    sheet_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
    sheet_combo = ttk.Combobox(top, textvariable=pane.sheet_var, state="disabled")
    sheet_combo.grid(row=1, column=1, sticky="ew", padx=4, pady=(8, 0))
    sheet_combo.bind("<<ComboboxSelected>>", pane._on_sheet_selected)

    header_label = ttk.Label(top, text="Header-rad:")
    header_label.grid(row=1, column=2, sticky="e", pady=(8, 0))
    ent_hdr = ttk.Entry(top, textvariable=pane.header_row_var, width=6)
    ent_hdr.grid(row=1, column=3, sticky="w", padx=2, pady=(8, 0))
    ent_hdr.bind("<Return>", lambda _e: pane._load_headers())
    ent_hdr.bind("<FocusOut>", lambda _e: pane._load_headers())

    btn_find_header = ttk.Button(
        top,
        text="Finn header",
        style="Secondary.TButton",
        command=lambda: pane._load_headers(auto_detect=True),
    )
    btn_find_header.grid(row=1, column=4, padx=2, pady=(8, 0))

    mapf = ttk.LabelFrame(pane, text="Kolonnekart", padding=10)
    mapf.pack(fill="x", padx=8, pady=(0, 6))
    mapf.columnconfigure(0, weight=1)

    # Samlet grid for påkrevde + vanlige valgfrie felt — etikettene skiller
    # kategoriene godt nok (Konto/Bilag/Beløp er åpenbart påkrevde).
    fields_frame = ttk.Frame(mapf)
    fields_frame.grid(row=0, column=0, sticky="ew")
    fields_frame.columnconfigure(1, weight=1)
    fields_frame.columnconfigure(3, weight=1)

    required_frame = fields_frame
    common_frame = fields_frame

    # --- Avanserte valgfrie felt (skjult som standard) ---
    advanced_container = ttk.Frame(mapf)
    advanced_container.grid(row=1, column=0, sticky="ew", pady=(6, 0))
    advanced_container.columnconfigure(0, weight=1)

    _advanced_visible = tk.BooleanVar(value=False)

    def _toggle_advanced():
        if _advanced_visible.get():
            advanced_frame.grid(row=1, column=0, sticky="ew")
            btn_toggle.configure(text="Skjul flere felt")
        else:
            advanced_frame.grid_remove()
            btn_toggle.configure(text="Vis flere felt ({})".format(len(advanced_optional)))

    btn_toggle = ttk.Checkbutton(
        advanced_container,
        text="Vis flere felt ({})".format(len(advanced_optional)),
        variable=_advanced_visible,
        command=_toggle_advanced,
        style="Toolbutton.TCheckbutton",
    )
    btn_toggle.grid(row=0, column=0, sticky="w")

    advanced_frame = ttk.LabelFrame(advanced_container, text="Kunde / Leverandør / MVA / Valuta", padding=10)
    advanced_frame.columnconfigure(1, weight=1)
    advanced_frame.columnconfigure(3, weight=1)
    # Start skjult
    advanced_frame.grid(row=1, column=0, sticky="ew")
    advanced_frame.grid_remove()

    combo_vars: Dict[str, tk.StringVar] = {}
    combo_widgets: Dict[str, ttk.Combobox] = {}

    for row_index, canon in enumerate(required_fields):
        ttk.Label(required_frame, text=f"{canon}:").grid(row=row_index, column=0, sticky="w", pady=2)
        var = tk.StringVar(value="")
        cb = ttk.Combobox(required_frame, textvariable=var, state="readonly", values=("",), height=18)
        cb.grid(row=row_index, column=1, sticky="ew", padx=(8, 0), pady=2)
        cb.bind("<<ComboboxSelected>>", lambda _e: pane._update_build_readiness())
        combo_vars[canon] = var
        combo_widgets[canon] = cb

    # Vanlige valgfrie felt starter på raden etter siste påkrevde.
    common_base_row = len(required_fields)
    for index, canon in enumerate(common_optional):
        row_index = common_base_row + index // 2
        column_offset = (index % 2) * 2
        ttk.Label(common_frame, text=f"{canon}:").grid(row=row_index, column=column_offset, sticky="w", pady=2)
        var = tk.StringVar(value="")
        cb = ttk.Combobox(common_frame, textvariable=var, state="readonly", values=("",), height=18)
        cb.grid(row=row_index, column=column_offset + 1, sticky="ew", padx=(8, 12), pady=2)
        cb.bind("<<ComboboxSelected>>", lambda _e: pane._update_build_readiness())
        combo_vars[canon] = var
        combo_widgets[canon] = cb

    for index, canon in enumerate(advanced_optional):
        row_index = index // 2
        column_offset = (index % 2) * 2
        ttk.Label(advanced_frame, text=f"{canon}:").grid(row=row_index, column=column_offset, sticky="w", pady=2)
        var = tk.StringVar(value="")
        cb = ttk.Combobox(advanced_frame, textvariable=var, state="readonly", values=("",), height=18)
        cb.grid(row=row_index, column=column_offset + 1, sticky="ew", padx=(8, 12), pady=2)
        cb.bind("<<ComboboxSelected>>", lambda _e: pane._update_build_readiness())
        combo_vars[canon] = var
        combo_widgets[canon] = cb

    # Lagre referanser for SAF-T-modus (kan kollapse hele seksjonen)
    pane._optional_section_frame = common_frame
    pane._advanced_container = advanced_container
    pane._advanced_frame = advanced_frame
    pane._advanced_visible_var = _advanced_visible
    pane._btn_toggle_advanced = btn_toggle

    actions = ttk.Frame(pane)
    actions.pack(fill="x", padx=8, pady=(0, 8))
    actions.columnconfigure(0, weight=1)

    readiness_lbl = ttk.Label(
        actions,
        text="",
        style="Warning.TLabel",
        justify="left",
    )
    readiness_lbl.grid(row=0, column=0, sticky="w")

    btn_edit_map = ttk.Button(
        actions,
        text="Endre kolonnekart",
        style="Secondary.TButton",
        command=lambda: pane._set_kolonnekart_collapsed(False, user=True),
    )
    btn_edit_map.grid(row=0, column=1, padx=(8, 0))
    btn_edit_map.grid_remove()  # starter skjult

    btn_guess = ttk.Button(actions, text="Oppdater forslag", style="Secondary.TButton", command=pane._guess_mapping)
    btn_guess.grid(row=0, column=2, padx=(8, 0))

    btn_build = ttk.Button(actions, text="Bygg datasett", style="Primary.TButton", command=pane._build_dataset_clicked)
    btn_build.grid(row=0, column=3, padx=(6, 0))

    status_lbl = ttk.Label(
        pane,
        text="",
        justify="left",
        style="Status.TLabel",
        wraplength=980,
    )
    status_lbl.pack(fill="x", padx=8, pady=(0, 8))

    pane._sheet_label = sheet_label
    pane._header_label = header_label
    pane._header_entry = ent_hdr
    pane._header_button = btn_find_header
    pane._structure_hint_label = None
    pane._structure_hint_default_text = ""
    pane._structure_hint_saft_text = ""
    pane._readiness_lbl = readiness_lbl
    pane._btn_guess = btn_guess
    pane._btn_build = btn_build
    pane._mapf = mapf
    pane._btn_edit_map = btn_edit_map
    pane._actions_frame = actions

    return sheet_combo, status_lbl, combo_vars, combo_widgets
