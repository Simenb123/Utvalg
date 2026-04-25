from __future__ import annotations

import tkinter as tk
from tkinter import ttk


_CARD_TITLES = {
    "opplysning": "Opplysningspliktig",
    "aga": "AGA-pliktig",
    "uavklart": "Uavklart RF-1022",
    "status": "Status",
}


def build_control_statement_summary_card_strip(parent: tk.Misc) -> tuple[ttk.Frame, dict[str, dict[str, tk.StringVar]]]:
    frame = ttk.Frame(parent, padding=(10, 0, 10, 8))
    card_vars: dict[str, dict[str, tk.StringVar]] = {}
    for key, title in _CARD_TITLES.items():
        card = ttk.LabelFrame(frame, text=title, padding=(8, 5))
        card.pack(side="left", fill="x", expand=True, padx=(0, 6))
        value_var = tk.StringVar(value="-")
        detail_var = tk.StringVar(value="")
        ttk.Label(card, textvariable=value_var).pack(anchor="w")
        ttk.Label(card, textvariable=detail_var, style="Muted.TLabel").pack(anchor="w")
        card_vars[key] = {
            "value": value_var,
            "detail": detail_var,
        }
    return frame, card_vars


def update_control_statement_summary_cards(
    card_vars: dict[str, dict[str, tk.StringVar]] | None,
    cards: list[dict[str, str]] | None,
) -> None:
    if not card_vars:
        return
    card_by_key = {str(card.get("key") or "").strip(): card for card in cards or []}
    for key, vars_by_name in card_vars.items():
        card = card_by_key.get(key, {})
        for field in ("value", "detail"):
            var = vars_by_name.get(field)
            if var is not None:
                var.set(str(card.get(field) or ("-" if field == "value" else "")))


__all__ = [
    "build_control_statement_summary_card_strip",
    "update_control_statement_summary_cards",
]
