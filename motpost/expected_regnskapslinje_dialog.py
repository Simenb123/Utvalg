from __future__ import annotations

from typing import Sequence

import tkinter as tk
from tkinter import ttk


def _sort_label_key(value: str) -> tuple[int, int | str, str]:
    text = str(value or "").strip()
    if not text:
        return (2, "", "")
    head = text.split(" ", 1)[0].strip()
    try:
        return (0, int(head), text.lower())
    except Exception:
        return (1, text.lower(), text.lower())


def choose_expected_regnskapslinjer(
    parent: tk.Misc,
    *,
    options: Sequence[str],
    selected: Sequence[str] = (),
    title: str = "Forventede regnskapslinjer",
) -> list[str] | None:
    labels = sorted({str(v).strip() for v in options if str(v).strip()}, key=_sort_label_key)
    if not labels:
        return []

    initial = {str(v).strip() for v in selected if str(v).strip()}
    result: dict[str, list[str] | None] = {"value": None}

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.geometry("520x420")
    win.minsize(420, 320)

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill=tk.BOTH, expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(1, weight=1)

    ttk.Label(
        outer,
        text="Velg regnskapslinjer som skal regnes som forventede motposter.",
        justify="left",
    ).grid(row=0, column=0, sticky="w", pady=(0, 8))

    list_frame = ttk.Frame(outer)
    list_frame.grid(row=1, column=0, sticky="nsew")
    list_frame.columnconfigure(0, weight=1)
    list_frame.rowconfigure(0, weight=1)

    listbox = tk.Listbox(list_frame, selectmode=tk.MULTIPLE, exportselection=False)
    listbox.grid(row=0, column=0, sticky="nsew")
    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=listbox.yview)
    scrollbar.grid(row=0, column=1, sticky="ns")
    listbox.configure(yscrollcommand=scrollbar.set)

    for idx, label in enumerate(labels):
        listbox.insert(tk.END, label)
        if label in initial:
            listbox.selection_set(idx)

    button_bar = ttk.Frame(outer)
    button_bar.grid(row=2, column=0, sticky="e", pady=(10, 0))

    def _selected_values() -> list[str]:
        return [str(listbox.get(i)).strip() for i in listbox.curselection()]

    def _save() -> None:
        result["value"] = _selected_values()
        win.destroy()

    def _clear() -> None:
        result["value"] = []
        win.destroy()

    ttk.Button(button_bar, text="Bruk", command=_save).pack(side=tk.RIGHT)
    ttk.Button(button_bar, text="Avbryt", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 6))
    ttk.Button(button_bar, text="Tøm", command=_clear).pack(side=tk.RIGHT, padx=(0, 6))

    try:
        listbox.focus_set()
    except Exception:
        pass

    win.wait_window()
    return result["value"]
