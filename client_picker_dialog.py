from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import tkinter as tk
from tkinter import messagebox, ttk


@dataclass
class _PickerState:
    result: Optional[str] = None


def open_client_picker(
    parent: tk.Misc,
    clients: list[str],
    initial_query: str = "",
    initial_selection: str | None = None,
    title: str = "Velg klient",
) -> Optional[str]:
    """Åpne en liten dialog for å søke/velge klient.

    - Dialogen starter alltid med tomt søkefelt (for å unngå "låst" søk på valgt klient).
    - Hvis initial_selection er satt, forhåndsmarkeres den i lista.

    Returnerer valgt klient (display-navn) eller None ved avbryt.
    """

    # Bakoverkompatibilitet: hvis noen fortsatt sender initial_query med forventning om
    # "start på denne klienten", bruk den som initial_selection.
    if initial_selection is None:
        sel = str(initial_query or "").strip()
        initial_selection = sel or None

    # Kopi + sortér én gang (case-insensitivt)
    all_clients = sorted([c for c in clients if c], key=lambda s: s.lower())

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("720x480")

    st = _PickerState(result=None)

    frm = ttk.Frame(win, padding=10)
    frm.pack(fill="both", expand=True)

    ttk.Label(frm, text="Søk (klientnr / navn):").pack(anchor="w")

    # Viktig: Start alltid blankt søkefelt.
    query_var = tk.StringVar(value="")
    ent = ttk.Entry(frm, textvariable=query_var)
    ent.pack(fill="x", pady=(0, 8))

    # Liste + scrollbar
    list_frame = ttk.Frame(frm)
    list_frame.pack(fill="both", expand=True)

    yscroll = ttk.Scrollbar(list_frame, orient="vertical")
    yscroll.pack(side="right", fill="y")

    listbox = tk.Listbox(
        list_frame,
        activestyle="dotbox",
        selectmode="browse",
        yscrollcommand=yscroll.set,
    )
    listbox.pack(side="left", fill="both", expand=True)
    yscroll.config(command=listbox.yview)

    lbl_count = ttk.Label(frm, text="")
    lbl_count.pack(anchor="w", pady=(6, 0))

    def get_selected() -> str:
        try:
            idx = int(listbox.curselection()[0])
        except Exception:
            return ""
        try:
            return str(listbox.get(idx))
        except Exception:
            return ""

    def fill_list(items: list[str], select_value: str | None = None) -> None:
        listbox.delete(0, tk.END)
        for c in items:
            listbox.insert(tk.END, c)

        lbl_count.configure(text=f"Viser {len(items)} av {len(all_clients)} klienter")

        if not items:
            return

        # Finn index for ønsket forhåndsvalg (hvis det finnes i filtrert liste)
        idx = 0
        if select_value:
            try:
                idx = items.index(select_value)
            except ValueError:
                idx = 0

        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)

    def apply_filter() -> None:
        q = str(query_var.get() or "").strip().lower()
        if not q:
            filtered = all_clients
        else:
            filtered = [c for c in all_clients if q in c.lower()]
        # Ved filtering: behold valgt klient hvis den fortsatt er synlig
        cur = get_selected() or initial_selection
        fill_list(filtered, select_value=cur)

    def on_ok() -> None:
        sel = get_selected()
        if sel:
            st.result = sel
        win.destroy()

    def on_cancel() -> None:
        st.result = None
        win.destroy()

    def on_double_click(event: tk.Event) -> None:  # noqa: ARG001
        on_ok()

    def on_delete_client() -> None:
        sel = get_selected()
        if not sel:
            return

        # Sikker "soft delete": arkiver til _deleted_clients
        msg = (
            f"Vil du slette klienten '{sel}'?\n\n"
            "Dette vil *arkivere* klientmappen (inkl. versjoner) ved å flytte den til\n"
            "'_deleted_clients' under datamappen. Dette kan angres ved å flytte mappen tilbake."
        )
        if not messagebox.askyesno("Slett klient", msg, parent=win):
            return

        try:
            import client_store

            deleted_to = client_store.delete_client(sel)
        except Exception as e:
            messagebox.showerror(
                "Slett klient",
                f"Kunne ikke slette klienten '{sel}'.\n\n{e}",
                parent=win,
            )
            return

        # Oppdater intern liste og UI
        try:
            all_clients.remove(sel)
        except ValueError:
            pass

        # Etter sletting: blankt søk og oppdatert liste
        query_var.set("")
        fill_list(all_clients)

        messagebox.showinfo(
            "Slett klient",
            f"Klienten '{sel}' ble arkivert til:\n{deleted_to}",
            parent=win,
        )

    def on_search_down(event: tk.Event) -> str:  # noqa: ARG001
        """↓ i søkefeltet → flytt fokus til listbox."""
        if listbox.size() > 0:
            cur = listbox.curselection()
            idx = (cur[0] + 1) if cur and cur[0] + 1 < listbox.size() else (cur[0] if cur else 0)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(idx)
            listbox.activate(idx)
            listbox.see(idx)
            listbox.focus_set()
        return "break"

    def on_listbox_up(event: tk.Event) -> str | None:  # noqa: ARG001
        """↑ øverst i listbox → flytt fokus tilbake til søkefeltet."""
        cur = listbox.curselection()
        if not cur or cur[0] == 0:
            ent.focus_set()
            ent.icursor(tk.END)
            return "break"
        return None

    # Bindinger
    query_var.trace_add("write", lambda *_: apply_filter())
    ent.bind("<Down>", on_search_down)
    listbox.bind("<Up>", on_listbox_up)
    listbox.bind("<Double-Button-1>", on_double_click)
    win.bind("<Return>", lambda *_: on_ok())
    win.bind("<Escape>", lambda *_: on_cancel())
    win.bind("<Delete>", lambda *_: on_delete_client())

    # Knapper
    bottom = ttk.Frame(frm)
    bottom.pack(fill="x", pady=(10, 0))

    btn_delete = ttk.Button(bottom, text="Slett klient", command=on_delete_client)
    btn_delete.pack(side="left")

    btn_ok = ttk.Button(bottom, text="OK", command=on_ok)
    btn_ok.pack(side="right", padx=(6, 0))

    btn_cancel = ttk.Button(bottom, text="Avbryt", command=on_cancel)
    btn_cancel.pack(side="right")

    # Initial fyll + initial selection
    fill_list(all_clients, select_value=initial_selection)

    ent.focus_set()

    # Vent til lukket
    win.wait_window()
    return st.result
