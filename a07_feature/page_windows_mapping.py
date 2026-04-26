from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


def open_mapping_overview(page, mapping_columns) -> None:
    existing = getattr(page, "_mapping_window", None)
    if existing is not None:
        try:
            if existing.winfo_exists():
                existing.focus_force()
                return
        except Exception:
            pass

    win = tk.Toplevel(page)
    win.title("A07-mappinger")
    win.geometry("760x520")
    page._mapping_window = win

    header = ttk.Frame(win, padding=10)
    header.pack(fill="x")
    ttk.Label(
        header,
        text="Lagrede mappinger for valgt klient/aar. Bruk dette vinduet ved behov, ikke som hovedarbeidsflate.",
        style="Muted.TLabel",
        wraplength=700,
        justify="left",
    ).pack(anchor="w")

    summary_var = tk.StringVar(value="")
    ttk.Label(header, textvariable=summary_var, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

    body = ttk.Frame(win, padding=(10, 0, 10, 10))
    body.pack(fill="both", expand=True)
    tree = page._build_tree_tab(body, mapping_columns)

    def _refresh_window_tree() -> None:
        page._fill_tree(tree, page.mapping_df, mapping_columns, iid_column="Konto")
        summary_var.set(f"Antall mappinger: {len(page.mapping_df)}")

    def _selected_account() -> str | None:
        selection = tree.selection()
        if not selection:
            return None
        return str(selection[0]).strip() or None

    def _selected_account_or_notify() -> str | None:
        account = _selected_account()
        if not account:
            messagebox.showinfo("A07", "Velg en mappingrad først.", parent=win)
            return None
        return account

    def _edit_selected() -> None:
        account = _selected_account_or_notify()
        if not account:
            return
        page._open_manual_mapping_clicked(initial_account=account)
        _refresh_window_tree()

    def _remove_selected() -> None:
        account = _selected_account_or_notify()
        if not account:
            return
        page._remove_mapping_accounts_checked(
            [account],
            focus_widget=tree,
            refresh="core",
            source_label="Fjernet mapping fra",
        )
        _refresh_window_tree()

    actions = ttk.Frame(win, padding=(10, 0, 10, 10))
    actions.pack(fill="x")
    ttk.Button(
        actions,
        text="Rediger valgt",
        command=_edit_selected,
    ).pack(side="left")
    ttk.Button(
        actions,
        text="Fjern valgt",
        command=_remove_selected,
    ).pack(side="left", padx=(6, 0))
    ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

    def _on_close() -> None:
        try:
            win.destroy()
        finally:
            page._mapping_window = None

    win.protocol("WM_DELETE_WINDOW", _on_close)
    _refresh_window_tree()
