"""UI: client/storage selector block shown at the top of the dataset pane."""

from __future__ import annotations

from dataclasses import dataclass

import tkinter as tk
from tkinter import ttk


@dataclass
class _StoreWidgets:
    frame: ttk.Frame
    client_var: tk.StringVar
    year_var: tk.StringVar
    hb_var: tk.StringVar

    cb_client: ttk.Combobox
    btn_pick_client: ttk.Button
    btn_settings: ttk.Button
    btn_my_clients: ttk.Button
    my_clients_var: tk.BooleanVar

    cb_year: ttk.Combobox

    cb_hb: ttk.Combobox
    btn_versions: ttk.Button

    lbl_storage: ttk.Label
    info_labels: dict[str, ttk.Label]


def build_client_store_widgets(parent: tk.Widget, *, init_client: str = "", init_year: str = "2025") -> _StoreWidgets:
    frame = ttk.LabelFrame(parent, text="Datakilde", padding=10)
    frame.columnconfigure(1, weight=1)

    client_var = tk.StringVar(value=init_client)
    year_var = tk.StringVar(value=str(init_year))
    hb_var = tk.StringVar(value="")

    ttk.Label(frame, text="Klient:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    cb_client = ttk.Combobox(frame, textvariable=client_var, state="readonly")
    cb_client.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

    btn_pick_client = ttk.Button(frame, text="Finn…", width=8, style="Secondary.TButton")
    btn_pick_client.grid(row=0, column=2, sticky="w", padx=4, pady=4)

    my_clients_var = tk.BooleanVar(value=False)
    btn_my_clients = ttk.Checkbutton(
        frame, text="Mine klienter", variable=my_clients_var,
        style="Toolbutton.TCheckbutton",
    )
    btn_my_clients.grid(row=0, column=3, sticky="w", padx=4, pady=4)

    btn_settings = ttk.Button(frame, text="Oppsett…", width=12, style="Secondary.TButton")
    btn_settings.grid(row=0, column=4, sticky="w", padx=4, pady=4)

    import datetime as _dt
    _current_year = _dt.date.today().year
    _year_values = [str(y) for y in range(_current_year - 7, _current_year + 3)]
    ttk.Label(frame, text="År:").grid(row=0, column=5, sticky="e", padx=6, pady=4)
    cb_year = ttk.Combobox(frame, textvariable=year_var, values=_year_values, width=6, state="readonly")
    cb_year.grid(row=0, column=6, sticky="w", padx=6, pady=4)

    ttk.Label(frame, text="Kildeversjon:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
    cb_hb = ttk.Combobox(frame, textvariable=hb_var, state="readonly")
    cb_hb.grid(row=1, column=1, columnspan=4, sticky="ew", padx=6, pady=4)

    # Keep the Dataset pane clean: version management is handled in a dedicated dialog.
    btn_versions = ttk.Button(frame, text="Versjoner…", style="Secondary.TButton")
    btn_versions.grid(row=1, column=5, columnspan=2, sticky="ew", padx=4, pady=4)

    lbl_storage = ttk.Label(frame, text="Datamappe: (ukjent)", style="Muted.TLabel")
    lbl_storage.grid(row=2, column=0, columnspan=7, sticky="w", padx=6, pady=(2, 2))

    # --- Klient-infopanel (rad 3) ---
    info_frame = ttk.Frame(frame)
    info_frame.grid(row=3, column=0, columnspan=7, sticky="ew", padx=6, pady=(0, 6))
    info_labels: dict[str, ttk.Label] = {}
    for i, (key, label_text) in enumerate([
        ("orgnr", "Org.nr:"),
        ("knr", "Knr:"),
        ("ansvarlig", "Ansvarlig:"),
        ("manager", "Manager:"),
    ]):
        ttk.Label(info_frame, text=label_text, style="Muted.TLabel").grid(
            row=0, column=i * 2, sticky="w", padx=(0 if i == 0 else 12, 2))
        lbl = ttk.Label(info_frame, text="\u2013")
        lbl.grid(row=0, column=i * 2 + 1, sticky="w")
        info_labels[key] = lbl

    return _StoreWidgets(
        frame=frame,
        client_var=client_var,
        year_var=year_var,
        hb_var=hb_var,
        cb_client=cb_client,
        btn_pick_client=btn_pick_client,
        btn_settings=btn_settings,
        btn_my_clients=btn_my_clients,
        my_clients_var=my_clients_var,
        cb_year=cb_year,
        cb_hb=cb_hb,
        btn_versions=btn_versions,
        lbl_storage=lbl_storage,
        info_labels=info_labels,
    )
