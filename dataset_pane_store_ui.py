# -*- coding: utf-8 -*-
"""dataset_pane_store_ui.py

Bygger Tkinter-widgets for klient/versjon-seksjonen.

Denne modulen er kun UI-konstruksjon. Logikk/handlinger ligger i
``dataset_pane_store_section.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk


@dataclass
class ClientStoreWidgets:
    frame: tk.Frame
    client_var: tk.StringVar
    year_var: tk.StringVar
    hb_var: tk.StringVar
    lbl_storage: ttk.Label
    cb_client: ttk.Combobox
    cb_hb: ttk.Combobox
    ent_year: ttk.Entry
    btn_create: ttk.Button
    btn_import_list: ttk.Button
    btn_refresh: ttk.Button
    btn_delete: ttk.Button
    btn_pick: ttk.Button


def build_client_store_widgets(parent: tk.Frame, *, init_client: str, init_year: str) -> ClientStoreWidgets:
    section = ttk.LabelFrame(parent, text="Klient og versjoner (HB)")
    section.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 4))
    section.columnconfigure(1, weight=1)

    client_var = tk.StringVar(value=init_client)
    year_var = tk.StringVar(value=init_year)
    hb_var = tk.StringVar(value="")

    ttk.Label(section, text="Klient:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    cb_client = ttk.Combobox(section, textvariable=client_var, state="normal")
    cb_client.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

    btn_create = ttk.Button(section, text="Opprett")
    btn_create.grid(row=0, column=2, sticky="e", padx=(0, 6), pady=4)

    btn_import_list = ttk.Button(section, text="Importer liste…")
    btn_import_list.grid(row=0, column=3, sticky="e", padx=(0, 6), pady=4)

    ttk.Label(section, text="År:").grid(row=0, column=4, sticky="e", padx=(12, 2), pady=4)
    ent_year = ttk.Entry(section, textvariable=year_var, width=6)
    ent_year.grid(row=0, column=5, sticky="e", padx=(0, 6), pady=4)

    ttk.Label(section, text="HB-versjon:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
    cb_hb = ttk.Combobox(section, textvariable=hb_var, state="readonly")
    cb_hb.grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=4)

    btn_refresh = ttk.Button(section, text="Oppdater")
    btn_refresh.grid(row=1, column=4, sticky="e", padx=(0, 6), pady=4)

    btn_delete = ttk.Button(section, text="Slett")
    btn_delete.grid(row=1, column=5, sticky="e", padx=(0, 6), pady=4)

    lbl_storage = ttk.Label(section, text="Datamappe: -")
    lbl_storage.grid(row=2, column=0, columnspan=5, sticky="w", padx=6, pady=(2, 6))

    btn_pick = ttk.Button(section, text="Velg datamappe…")
    btn_pick.grid(row=2, column=6, sticky="e", padx=(0, 6), pady=(2, 6))

    return ClientStoreWidgets(
        frame=section,
        client_var=client_var,
        year_var=year_var,
        hb_var=hb_var,
        lbl_storage=lbl_storage,
        cb_client=cb_client,
        cb_hb=cb_hb,
        ent_year=ent_year,
        btn_create=btn_create,
        btn_import_list=btn_import_list,
        btn_refresh=btn_refresh,
        btn_delete=btn_delete,
        btn_pick=btn_pick,
    )
