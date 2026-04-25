from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Sequence

from .page_a07_dialogs_shared import _PickerOption, _filter_picker_options


def open_manual_mapping_dialog(
    parent: tk.Misc,
    *,
    account_options: Sequence[_PickerOption],
    code_options: Sequence[_PickerOption],
    initial_account: str | None = None,
    initial_code: str | None = None,
    title: str = "Ny eller rediger mapping",
) -> tuple[str, str] | None:
    if not account_options or not code_options:
        return None
    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("1100x560")
    result: dict[str, tuple[str, str] | None] = {"value": None}
    selected_account = str(initial_account or "").strip() or None
    selected_code = str(initial_code or "").strip() or None
    filtered_accounts = list(account_options)
    filtered_codes = list(code_options)
    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)
    ttk.Label(
        outer,
        text="Velg konto og A07-kode. Skriv i søkefeltene for å filtrere listene.",
    ).pack(anchor="w")
    columns = ttk.Frame(outer)
    columns.pack(fill="both", expand=True, pady=(8, 0))
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    columns.rowconfigure(0, weight=1)
    status_var = tk.StringVar(value="")
    account_query = tk.StringVar(value="")
    code_query = tk.StringVar(value="")

    def _build_picker_column(parent_frame: ttk.Frame, title_text: str) -> tuple[ttk.Entry, tk.Listbox, ttk.Label]:
        ttk.Label(parent_frame, text=title_text).pack(anchor="w")
        entry = ttk.Entry(parent_frame)
        entry.pack(fill="x", pady=(4, 6))
        list_frame = ttk.Frame(parent_frame)
        list_frame.pack(fill="both", expand=True)
        ybar = ttk.Scrollbar(list_frame, orient="vertical")
        ybar.pack(side="right", fill="y")
        listbox = tk.Listbox(list_frame, activestyle="dotbox", exportselection=False, yscrollcommand=ybar.set)
        listbox.pack(side="left", fill="both", expand=True)
        ybar.config(command=listbox.yview)
        count_label = ttk.Label(parent_frame, text="")
        count_label.pack(anchor="w", pady=(6, 0))
        return entry, listbox, count_label

    def _selected_option(listbox: tk.Listbox, options: Sequence[_PickerOption]) -> _PickerOption | None:
        try:
            idx = int(listbox.curselection()[0])
        except Exception:
            return None
        if idx < 0 or idx >= len(options):
            return None
        return options[idx]

    def _fill_list(
        listbox: tk.Listbox,
        options: Sequence[_PickerOption],
        count_label: ttk.Label,
        total_count: int,
        selected_key: str | None,
    ) -> None:
        listbox.delete(0, tk.END)
        for option in options:
            listbox.insert(tk.END, option.label)
        count_label.configure(text=f"Viser {len(options)} av {total_count}")
        if not options:
            return
        idx = 0
        if selected_key:
            for pos, option in enumerate(options):
                if option.key == selected_key:
                    idx = pos
                    break
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)

    def _update_status() -> None:
        account_text = selected_account or "-"
        code_text = selected_code or "-"
        status_var.set(f"Valg: {account_text} -> {code_text}")

    def _refresh_account_list() -> None:
        nonlocal filtered_accounts, selected_account
        filtered_accounts = _filter_picker_options(account_options, account_query.get())
        _fill_list(
            account_listbox,
            filtered_accounts,
            account_count,
            len(account_options),
            selected_account,
        )
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _refresh_code_list() -> None:
        nonlocal filtered_codes, selected_code
        filtered_codes = _filter_picker_options(code_options, code_query.get())
        _fill_list(
            code_listbox,
            filtered_codes,
            code_count,
            len(code_options),
            selected_code,
        )
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_account_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_account
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _on_code_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_code
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_ok() -> None:
        if not selected_account or not selected_code:
            messagebox.showinfo("A07", "Velg både konto og A07-kode.", parent=win)
            return
        result["value"] = (selected_account, selected_code)
        win.destroy()

    def _on_cancel() -> None:
        result["value"] = None
        win.destroy()

    account_frame = ttk.Frame(columns)
    account_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    code_frame = ttk.Frame(columns)
    code_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
    account_entry, account_listbox, account_count = _build_picker_column(account_frame, "Konto")
    code_entry, code_listbox, code_count = _build_picker_column(code_frame, "A07-kode")
    account_entry.configure(textvariable=account_query)
    code_entry.configure(textvariable=code_query)
    account_query.trace_add("write", lambda *_args: _refresh_account_list())
    code_query.trace_add("write", lambda *_args: _refresh_code_list())
    account_listbox.bind("<<ListboxSelect>>", _on_account_select)
    code_listbox.bind("<<ListboxSelect>>", _on_code_select)
    account_listbox.bind("<Double-Button-1>", lambda _event: code_entry.focus_set())
    code_listbox.bind("<Double-Button-1>", lambda _event: _on_ok())
    win.bind("<Return>", lambda *_args: _on_ok())
    win.bind("<Escape>", lambda *_args: _on_cancel())
    ttk.Label(outer, textvariable=status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="Avbryt", command=_on_cancel).pack(side="right")
    ttk.Button(buttons, text="Bruk mapping", command=_on_ok).pack(side="right", padx=(0, 6))
    _refresh_account_list()
    _refresh_code_list()
    account_entry.focus_set()
    win.wait_window()
    return result["value"]
