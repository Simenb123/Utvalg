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
    *,
    client_meta: dict[str, dict] | None = None,
    initial_query: str = "",
    initial_selection: str | None = None,
    title: str = "Velg klient",
    show_mine_filter: bool = True,
    mine_by_default: bool = False,
) -> Optional[str]:
    """Åpne en søkbar dialog for å velge klient.

    Viser multi-kolonne Treeview med Klient, Org.nr, Knr, Ansvarlig, Manager.
    Søk matcher på tvers av navn, orgnr og Knr.

    Returnerer valgt klient (display-navn) eller None ved avbryt.
    """

    if initial_selection is None:
        sel = str(initial_query or "").strip()
        initial_selection = sel or None

    meta = client_meta or {}

    # Sortér case-insensitivt
    all_clients = sorted([c for c in clients if c], key=lambda s: s.lower())

    # Bygg søkbar strengliste for rask filtrering
    search_index: dict[str, str] = {}
    for c in all_clients:
        m = meta.get(c, {})
        search_index[c] = " ".join([
            c.lower(),
            (m.get("org_number") or "").lower(),
            (m.get("client_number") or "").lower(),
        ])

    # "Mine klienter"-filter
    my_clients_set: set[str] | None = None
    if show_mine_filter:
        try:
            import team_config
            from src.shared.client_store.enrich import is_my_client
            user = team_config.current_user()
            if user:
                my_clients_set = set()
                for c in all_clients:
                    m = meta.get(c, {})
                    if is_my_client(m, user.visena_initials, user.full_name):
                        my_clients_set.add(c)
        except Exception:
            my_clients_set = None

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("860x520")

    st = _PickerState(result=None)

    frm = ttk.Frame(win, padding=10)
    frm.pack(fill="both", expand=True)

    # --- Søkerad ---
    search_row = ttk.Frame(frm)
    search_row.pack(fill="x")

    ttk.Label(search_row, text="Søk (navn / orgnr / Knr):").pack(side="left")

    query_var = tk.StringVar(value="")
    ent = ttk.Entry(search_row, textvariable=query_var)
    ent.pack(side="left", fill="x", expand=True, padx=(6, 0))

    # Default på "Mine klienter" kun hvis vi faktisk fant noen — ellers ville
    # dialogen åpnet med tom liste.
    mine_default = bool(
        mine_by_default and show_mine_filter and my_clients_set
    )
    mine_var = tk.BooleanVar(value=mine_default)
    if show_mine_filter and my_clients_set is not None:
        ttk.Checkbutton(search_row, text="Mine klienter", variable=mine_var).pack(
            side="right", padx=(8, 0))

    # --- Treeview ---
    tree_frame = ttk.Frame(frm)
    tree_frame.pack(fill="both", expand=True, pady=(8, 0))

    cols = ("klient", "orgnr", "knr", "ansvarlig", "manager")
    tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="browse")

    tree.heading("klient", text="Klient")
    tree.heading("orgnr", text="Org.nr")
    tree.heading("knr", text="Knr")
    tree.heading("ansvarlig", text="Ansvarlig")
    tree.heading("manager", text="Manager")

    tree.column("klient", width=300, stretch=True)
    tree.column("orgnr", width=100, stretch=False)
    tree.column("knr", width=70, stretch=False)
    tree.column("ansvarlig", width=80, stretch=False)
    tree.column("manager", width=160, stretch=True)

    yscroll = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=yscroll.set)

    tree.pack(side="left", fill="both", expand=True)
    yscroll.pack(side="right", fill="y")

    # Sortering
    try:
        from ui_treeview_sort import enable_treeview_sorting
        enable_treeview_sorting(tree)
    except Exception:
        pass

    # --- Statuslinje ---
    lbl_count = ttk.Label(frm, text="")
    lbl_count.pack(anchor="w", pady=(6, 0))

    # --- Hjelpefunksjoner ---

    def get_selected() -> str:
        sel = tree.selection()
        if not sel:
            return ""
        try:
            return str(tree.item(sel[0], "values")[0])
        except Exception:
            return ""

    def fill_tree(items: list[str], select_value: str | None = None) -> None:
        tree.delete(*tree.get_children())

        for c in items:
            m = meta.get(c, {})
            tree.insert("", "end", iid=c, values=(
                c,
                m.get("org_number", ""),
                m.get("client_number", ""),
                m.get("responsible", ""),
                m.get("manager", ""),
            ))

        lbl_count.configure(text=f"Viser {len(items)} av {len(all_clients)} klienter")

        if not items:
            return

        # Forhåndsvelg
        target = select_value or (items[0] if items else None)
        if target and tree.exists(target):
            tree.selection_set(target)
            tree.focus(target)
            tree.see(target)

    def apply_filter() -> None:
        q = str(query_var.get() or "").strip().lower()
        only_mine = mine_var.get()

        filtered = []
        for c in all_clients:
            if only_mine and my_clients_set is not None and c not in my_clients_set:
                continue
            if q and q not in search_index.get(c, c.lower()):
                continue
            filtered.append(c)

        cur = get_selected() or initial_selection
        fill_tree(filtered, select_value=cur)

    # --- Callbacks ---

    def on_ok() -> None:
        sel = get_selected()
        if sel:
            st.result = sel
        win.destroy()

    def on_cancel() -> None:
        st.result = None
        win.destroy()

    def on_double_click(event: tk.Event) -> None:
        on_ok()

    def on_delete_client() -> None:
        sel = get_selected()
        if not sel:
            return

        msg = (
            f"Vil du slette klienten '{sel}'?\n\n"
            "Dette vil *arkivere* klientmappen (inkl. versjoner) ved å flytte den til\n"
            "'_deleted_clients' under datamappen. Dette kan angres ved å flytte mappen tilbake."
        )
        if not messagebox.askyesno("Slett klient", msg, parent=win):
            return

        try:
            import src.shared.client_store.store as client_store
            deleted_to = client_store.delete_client(sel)
        except Exception as e:
            messagebox.showerror("Slett klient", f"Kunne ikke slette '{sel}'.\n\n{e}", parent=win)
            return

        try:
            all_clients.remove(sel)
        except ValueError:
            pass

        query_var.set("")
        fill_tree(all_clients)

        messagebox.showinfo("Slett klient", f"'{sel}' ble arkivert til:\n{deleted_to}", parent=win)

    def on_search_down(event: tk.Event) -> str:
        """↓ i søkefeltet → flytt fokus til Treeview."""
        children = tree.get_children()
        if children:
            cur = tree.selection()
            if cur:
                idx = list(children).index(cur[0])
                next_idx = min(idx + 1, len(children) - 1)
            else:
                next_idx = 0
            target = children[next_idx]
            tree.selection_set(target)
            tree.focus(target)
            tree.see(target)
            tree.focus_set()
        return "break"

    def on_tree_up(event: tk.Event) -> str | None:
        """↑ øverst i Treeview → flytt fokus til søkefeltet."""
        children = tree.get_children()
        cur = tree.selection()
        if not cur or (children and cur[0] == children[0]):
            ent.focus_set()
            ent.icursor(tk.END)
            return "break"
        return None

    # --- Bindings ---
    query_var.trace_add("write", lambda *_: apply_filter())
    mine_var.trace_add("write", lambda *_: apply_filter())
    ent.bind("<Down>", on_search_down)
    tree.bind("<Up>", on_tree_up)
    tree.bind("<Double-Button-1>", on_double_click)
    win.bind("<Return>", lambda *_: on_ok())
    win.bind("<Escape>", lambda *_: on_cancel())
    win.bind("<Delete>", lambda *_: on_delete_client())

    # --- Knapper ---
    bottom = ttk.Frame(frm)
    bottom.pack(fill="x", pady=(10, 0))

    btn_delete = ttk.Button(bottom, text="Slett klient", command=on_delete_client)
    btn_delete.pack(side="left")

    btn_ok = ttk.Button(bottom, text="OK", command=on_ok)
    btn_ok.pack(side="right", padx=(6, 0))

    btn_cancel = ttk.Button(bottom, text="Avbryt", command=on_cancel)
    btn_cancel.pack(side="right")

    # --- Initial fyll ---
    if mine_default:
        apply_filter()
    else:
        fill_tree(all_clients, select_value=initial_selection)

    ent.focus_set()
    win.wait_window()
    return st.result
