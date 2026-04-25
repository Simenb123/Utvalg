from __future__ import annotations

import tkinter as tk
from tkinter import ttk


def build_source_overview_rows(
    *,
    a07_text: str,
    tb_text: str,
    mapping_text: str,
    rulebook_text: str,
    history_text: str,
) -> list[tuple[str, str]]:
    return [
        ("A07-kilde", a07_text),
        ("Saldobalanse", tb_text),
        ("Mapping", mapping_text),
        ("Rulebook", rulebook_text),
        ("Historikk", history_text),
    ]


def open_source_overview(page) -> None:
    existing = page._source_overview_window
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return
        except Exception:
            pass

    win = tk.Toplevel(page)
    win.title("A07-kilder")
    win.geometry("760x320")
    page._source_overview_window = win

    body = ttk.Frame(win, padding=10)
    body.pack(fill="both", expand=True)

    ttk.Label(
        body,
        text="Kildeinfo for valgt klient/aar. Dette er bare referanseinfo, ikke en egen arbeidsflate.",
        style="Muted.TLabel",
        wraplength=700,
        justify="left",
    ).pack(anchor="w")

    grid = ttk.Frame(body)
    grid.pack(fill="both", expand=True, pady=(12, 0))
    grid.columnconfigure(1, weight=1)

    for row_idx, (label_text, value_text) in enumerate(
        build_source_overview_rows(
            a07_text=page.a07_path_var.get(),
            tb_text=page.tb_path_var.get(),
            mapping_text=page.mapping_path_var.get(),
            rulebook_text=page.rulebook_path_var.get(),
            history_text=page.history_path_var.get(),
        )
    ):
        ttk.Label(grid, text=f"{label_text}:", style="Section.TLabel").grid(
            row=row_idx,
            column=0,
            sticky="nw",
            padx=(0, 10),
            pady=(0, 8),
        )
        ttk.Label(
            grid,
            text=value_text,
            style="Muted.TLabel",
            wraplength=540,
            justify="left",
        ).grid(row=row_idx, column=1, sticky="nw", pady=(0, 8))

    actions = ttk.Frame(body)
    actions.pack(fill="x", pady=(8, 0))
    ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

    def _on_close() -> None:
        try:
            win.destroy()
        finally:
            page._source_overview_window = None

    win.protocol("WM_DELETE_WINDOW", _on_close)
