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

    lbl_client: ttk.Label
    btn_switch_client: ttk.Button

    cb_year: ttk.Combobox

    btn_versions: ttk.Button

    status_pills: dict[str, tk.Label]
    company_labels: dict[str, ttk.Label]
    company_key_labels: dict[str, ttk.Label]
    role_labels: dict[str, ttk.Label]
    team_labels: dict[str, ttk.Label]


def _add_kv_row(parent: tk.Widget, row: int, label_text: str,
                wraplength: int = 240) -> tuple[ttk.Label, ttk.Label]:
    """Bygg en label-verdi-rad i en info-boks. Returnerer (value, key)."""
    key_lbl = ttk.Label(parent, text=label_text, style="Muted.TLabel")
    key_lbl.grid(row=row, column=0, sticky="nw", padx=(0, 6), pady=1)
    val_lbl = ttk.Label(parent, text="\u2013", anchor="w", justify="left",
                        wraplength=wraplength)
    val_lbl.grid(row=row, column=1, sticky="ew", pady=1)
    return val_lbl, key_lbl


def build_client_store_widgets(parent: tk.Widget, *, init_client: str = "", init_year: str = "2025") -> _StoreWidgets:
    frame = ttk.LabelFrame(parent, text="Datakilde", padding=10)
    frame.columnconfigure(1, weight=1)

    client_var = tk.StringVar(value=init_client)
    year_var = tk.StringVar(value=str(init_year))
    hb_var = tk.StringVar(value="")

    _client_font = ("Segoe UI", 11, "bold")
    _year_font = ("Segoe UI", 12, "bold")
    try:
        _style = ttk.Style(frame)
        _style.configure("Client.TLabel", font=_client_font)
        _style.configure("Year.TCombobox", padding=(4, 2), font=_year_font)
        frame.option_add("*TCombobox*Listbox.font", _year_font)
    except Exception:
        pass

    ttk.Label(frame, text="Klient:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
    lbl_client = ttk.Label(frame, textvariable=client_var, style="Client.TLabel", anchor="w")
    lbl_client.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

    ttk.Label(frame, text="År:", font=_year_font).grid(row=0, column=2, sticky="e", padx=6, pady=4)
    cb_year = ttk.Combobox(frame, textvariable=year_var, values=[], width=6,
                           state="readonly", style="Year.TCombobox")
    try:
        cb_year.configure(font=_year_font)
    except tk.TclError:
        pass

    import datetime as _dt
    _current_year = _dt.date.today().year
    cb_year["values"] = [str(y) for y in range(_current_year - 7, _current_year + 3)]
    cb_year.grid(row=0, column=3, sticky="w", padx=6, pady=4)

    btn_switch_client = ttk.Button(frame, text="Bytt klient…", style="Secondary.TButton")
    btn_switch_client.grid(row=0, column=4, sticky="e", padx=4, pady=4)

    btn_versions = ttk.Button(frame, text="Versjoner…", style="Secondary.TButton")
    btn_versions.grid(row=0, column=5, sticky="e", padx=4, pady=4)

    # --- Datakilde-status (rad 1): 4 pills for HB/SB/KR/LR ---
    status_frame = ttk.Frame(frame)
    status_frame.grid(row=1, column=0, columnspan=6, sticky="w", padx=6, pady=(4, 6))
    status_pills: dict[str, tk.Label] = {}
    _pill_font = ("Segoe UI", 9, "bold")
    for i, (dtype, short) in enumerate([("hb", "HB"), ("sb", "SB"), ("kr", "KR"), ("lr", "LR")]):
        pill = tk.Label(
            status_frame, text=f"  {short}  ",
            bg="#e0e0e0", fg="#9e9e9e",
            font=_pill_font, padx=10, pady=3,
            borderwidth=0, cursor="hand2",
        )
        pill.grid(row=0, column=i, padx=(0 if i == 0 else 6, 0))
        status_pills[dtype] = pill

    # --- Rad 2: 3 parallelle info-bokser (Selskap / Roller / Team) ---
    info_container = ttk.Frame(frame)
    info_container.grid(row=2, column=0, columnspan=6, sticky="ew", padx=6, pady=(0, 4))
    for col in (0, 1, 2):
        info_container.columnconfigure(col, weight=1, uniform="info")

    # Selskap
    company_frame = ttk.LabelFrame(info_container, text="Selskap", padding=8)
    company_frame.grid(row=0, column=0, sticky="new", padx=(0, 4))
    company_frame.columnconfigure(1, weight=1)
    company_labels: dict[str, ttk.Label] = {}
    company_key_labels: dict[str, ttk.Label] = {}
    for row_idx, (key, text) in enumerate([
        ("orgnr", "Org.nr:"),
        ("knr", "Knr:"),
        ("orgform", "Org.form:"),
        ("naering", "N\u00e6ring:"),
        ("mva", "MVA-reg:"),
        ("address", "Adresse:"),
        ("stiftelsesdato", "Stiftelsesdato:"),
        ("ansatte", "Ansatte:"),
        ("hjemmeside", "Hjemmeside:"),
        ("kapital", "Kapital:"),
        ("antall_aksjer", "Antall aksjer:"),
        ("status", "Status:"),  # skjules når ingen rødt flagg
    ]):
        v, k = _add_kv_row(company_frame, row_idx, text)
        company_labels[key] = v
        company_key_labels[key] = k

    # Roller
    roles_frame = ttk.LabelFrame(info_container, text="Roller", padding=8)
    roles_frame.grid(row=0, column=1, sticky="new", padx=4)
    roles_frame.columnconfigure(1, weight=1)
    role_labels: dict[str, ttk.Label] = {}
    for row_idx, (key, text) in enumerate([
        ("daglig_leder", "Daglig leder:"),
        ("styreleder", "Styreleder:"),
        ("nestleder", "Nestleder:"),
        ("styremedlemmer", "Styremedlem:"),
        ("varamedlemmer", "Varamedlem:"),
        ("revisor", "Revisor:"),
        ("regnskapsforer", "Regnskapsf\u00f8rer:"),
    ]):
        role_labels[key], _ = _add_kv_row(roles_frame, row_idx, text)

    # Team
    team_frame = ttk.LabelFrame(info_container, text="Team", padding=8)
    team_frame.grid(row=0, column=2, sticky="new", padx=(4, 0))
    team_frame.columnconfigure(1, weight=1)
    team_labels: dict[str, ttk.Label] = {}
    for row_idx, (key, text) in enumerate([
        ("partner", "Partner:"),
        ("manager", "Manager:"),
        ("medarbeidere", "Medarbeidere:"),
    ]):
        team_labels[key], _ = _add_kv_row(team_frame, row_idx, text)

    return _StoreWidgets(
        frame=frame,
        client_var=client_var,
        year_var=year_var,
        hb_var=hb_var,
        lbl_client=lbl_client,
        btn_switch_client=btn_switch_client,
        cb_year=cb_year,
        btn_versions=btn_versions,
        status_pills=status_pills,
        company_labels=company_labels,
        company_key_labels=company_key_labels,
        role_labels=role_labels,
        team_labels=team_labels,
    )
