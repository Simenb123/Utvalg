from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import messagebox, ttk
from typing import Optional, Tuple

import src.shared.client_store.importer as client_store_import


def _show_import_preview(parent: tk.Widget, file_path: Path, plan: client_store_import.ImportPlan) -> Tuple[bool, bool]:
    """Viser en enkel forhåndsvisning før import.

    Returnerer (ok, update_names).
    """

    root = parent.winfo_toplevel()
    win = tk.Toplevel(root)
    win.title("Importer klientliste – forhåndsvisning")
    win.transient(root)
    win.grab_set()

    # Rimelig størrelse (kan endres av bruker)
    try:
        win.geometry("820x520")
    except Exception:
        pass

    info = (
        f"Fil: {file_path.name}\n"
        f"Fant {plan.found} unike rader/klienter i filen.\n\n"
        f"Nye klienter: {len(plan.new_clients)}\n"
        f"Eksisterende (match på klientnr/navn): {len(plan.existing_clients)}\n"
        f"Navneendringer (match på klientnr): {len(plan.rename_candidates)}\n"
        f"Duplikater i fil (samme klientnr/navn): {len(plan.duplicates_in_file)}\n\n"
        "Importen sletter ikke data. Den kan opprette nye klienter og (valgfritt) oppdatere visningsnavn."
    )
    lbl = ttk.Label(win, text=info, justify="left")
    lbl.pack(fill="x", padx=12, pady=(12, 8))

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=12, pady=8)

    def add_tab(title: str, items: list[str]) -> None:
        frm = ttk.Frame(nb)
        nb.add(frm, text=title)
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        lb = tk.Listbox(frm)
        sb = ttk.Scrollbar(frm, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=sb.set)

        lb.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        for it in items:
            lb.insert("end", it)

    add_tab(f"Nye klienter ({len(plan.new_clients)})", plan.new_clients)
    add_tab(
        f"Navneendringer ({len(plan.rename_candidates)})",
        [f"{old}  →  {new}" for (old, new) in plan.rename_candidates],
    )
    if plan.duplicates_in_file:
        add_tab(f"Duplikater i fil ({len(plan.duplicates_in_file)})", plan.duplicates_in_file)

    update_names_var = tk.BooleanVar(value=False)
    chk = ttk.Checkbutton(
        win,
        text="Oppdater navn på eksisterende klienter (samme klientnr)",
        variable=update_names_var,
    )
    if not plan.rename_candidates:
        chk.state(["disabled"])
    chk.pack(anchor="w", padx=12, pady=(0, 8))

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(0, 12))

    ok_state = {"ok": False}

    def can_run() -> bool:
        return bool(plan.new_clients) or (update_names_var.get() and bool(plan.rename_candidates))

    def on_ok() -> None:
        ok_state["ok"] = True
        win.destroy()

    def on_cancel() -> None:
        win.destroy()

    ok_btn = ttk.Button(btns, text="Start import", command=on_ok)
    cancel_btn = ttk.Button(btns, text="Avbryt", command=on_cancel)
    cancel_btn.pack(side="right")
    ok_btn.pack(side="right", padx=(0, 8))

    def refresh_ok_state(*_args: object) -> None:
        if can_run():
            ok_btn.state(["!disabled"])
        else:
            ok_btn.state(["disabled"])

    update_names_var.trace_add("write", refresh_ok_state)
    refresh_ok_state()

    win.wait_window()
    return ok_state["ok"], bool(update_names_var.get())


def import_client_list_with_progress(parent: tk.Widget, file_path: str, on_done: Optional[callable] = None) -> None:
    file_path_p = Path(file_path)

    # 1) Planlegg import (forhåndssjekk)
    try:
        plan = client_store_import.plan_import_clients(file_path_p)
    except Exception as e:
        messagebox.showerror("Importer klientliste", f"Kunne ikke lese filen:\n\n{e}", parent=parent)
        return

    if not plan.new_clients and not plan.rename_candidates:
        messagebox.showinfo(
            "Importer klientliste",
            "Ingen nye klienter (eller navneendringer) ble funnet i filen.",
            parent=parent,
        )
        if on_done:
            on_done({"found": plan.found, "created": 0, "skipped_existing": plan.found})
        return

    ok, update_names = _show_import_preview(parent, file_path_p, plan)
    if not ok:
        return

    if not plan.new_clients and not (update_names and plan.rename_candidates):
        messagebox.showinfo(
            "Importer klientliste",
            "Ingen oppgaver valgt. Kryss av for navneoppdatering eller avbryt.",
            parent=parent,
        )
        return

    # 2) Kjør import med progresjonsvindu
    win = tk.Toplevel(parent)
    win.title("Importerer klientliste")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    status = ttk.Label(win, text="Starter import…")
    status.pack(padx=12, pady=(12, 6))

    pb = ttk.Progressbar(win, length=420, mode="indeterminate")
    pb.pack(padx=12, pady=(0, 12))

    btns = ttk.Frame(win)
    btns.pack(fill='x', padx=12, pady=(0, 12))

    def _on_cancel() -> None:
        cancel_event.set()
        try:
            cancel_btn.state(['disabled'])
        except Exception:
            pass
        status.config(text='Avbryter… (venter på at importen stopper)')

    cancel_btn = ttk.Button(btns, text='Avbryt import', command=_on_cancel)
    cancel_btn.pack(side='right')

    def _on_close() -> None:
        _on_cancel()

    win.protocol('WM_DELETE_WINDOW', _on_close)


    q: Queue[tuple] = Queue()
    cancel_event = threading.Event()


    def progress_cb(done: int, total: int, name: str) -> None:
        q.put(("progress", done, total, name))

    def worker() -> None:
        try:
            stats = client_store_import.import_clients_from_file(
                file_path_p,
                progress_cb=progress_cb,
                update_names=update_names,
                plan=plan,
                cancel_event=cancel_event,
            )
            q.put(("done", stats))
        except Exception as e:
            q.put(("error", str(e)))

    threading.Thread(target=worker, daemon=True).start()

    pb.start(10)

    def poll() -> None:
        try:
            while True:
                msg = q.get_nowait()
                if not msg:
                    continue
                kind = msg[0]
                if kind == "progress":
                    _, done, total, name = msg
                    if total and total > 0:
                        pb.stop()
                        pb.configure(mode="determinate", maximum=total, value=done)
                        status.config(text=f"Importer {done}/{total}: {name}")
                    else:
                        pb.configure(mode="indeterminate")
                        pb.start(10)
                        status.config(text=f"Importer… {name}")
                elif kind == "done":
                    pb.stop()
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    stats = msg[1]
                    if stats.get('cancelled'):
                        messagebox.showinfo(
                            'Importer klientliste',
                            f"Import avbrutt. Opprettet {stats.get('created', 0)} klienter.",
                            parent=parent,
                        )
                    if on_done:
                        on_done(stats)
                    return
                elif kind == "error":
                    pb.stop()
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    messagebox.showerror("Import-feil", msg[1], parent=parent)
                    return
        except Empty:
            pass
        win.after(60, poll)

    poll()
