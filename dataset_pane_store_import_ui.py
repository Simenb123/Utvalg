# -*- coding: utf-8 -*-
"""dataset_pane_store_import_ui.py

UI-hjelper for import av klientliste (Excel/CSV) uten at Tkinter-GUI henger.

Vi kjører selve importen i en bakgrunnstråd, og oppdaterer en progress-dialog
via en kø + polling med ``after``.
"""

from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk


def import_client_list_with_progress(parent: tk.Misc, file_path: str, *, on_done=None) -> None:  # noqa: ANN001
    """Start import av klientliste i bakgrunnstråd.

    Args:
        parent: Tk parent (typisk en Frame).
        file_path: Sti til Excel/CSV.
        on_done: Callback(stats: dict) som kalles i UI-tråd når importen er ferdig.
    """

    try:
        import client_store_import
    except Exception:
        messagebox.showwarning("Importer", "Import-modul er ikke tilgjengelig.")
        return

    p = str(file_path or "").strip()
    if not p:
        return

    root = parent.winfo_toplevel()
    progress = tk.Toplevel(root)
    progress.title("Importer")
    progress.transient(root)
    progress.resizable(False, False)

    # Modal: hindrer brukeren i å trykke import flere ganger
    try:
        progress.grab_set()
    except Exception:
        pass

    txt_var = tk.StringVar(value="Importer klientliste…")
    ttk.Label(progress, textvariable=txt_var, padding=12).pack(anchor="center")

    pb = ttk.Progressbar(progress, mode="indeterminate", length=340)
    pb.pack(fill="x", padx=16, pady=(0, 16))
    pb.start(10)

    # Sentrer på parent
    try:
        root.update_idletasks()
        w, h = 420, 140
        rx, ry = root.winfo_rootx(), root.winfo_rooty()
        rw, rh = root.winfo_width(), root.winfo_height()
        x = rx + (rw - w) // 2
        y = ry + (rh - h) // 2
        progress.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

    q: "queue.Queue[tuple]" = queue.Queue()

    def _progress_cb(i: int, total: int, name: str) -> None:
        q.put(("progress", i, total, name))

    def _worker() -> None:
        try:
            stats = client_store_import.import_clients_from_file(Path(p), progress_cb=_progress_cb)
            q.put(("done", stats))
        except Exception as e:
            q.put(("error", e))

    threading.Thread(target=_worker, daemon=True).start()

    def _poll() -> None:
        if not progress.winfo_exists():
            return

        got_done = False
        done_stats = None
        err = None

        # Tøm køen (kan komme mange progress-meldinger)
        while True:
            try:
                item = q.get_nowait()
            except queue.Empty:
                break

            if not item:
                continue
            kind = item[0]
            if kind == "progress":
                _k, i, total, name = item
                try:
                    if isinstance(total, int) and total > 0:
                        if pb["mode"] != "determinate":
                            pb.stop()
                            pb.configure(mode="determinate", maximum=max(total, 1))
                        pb["value"] = int(i)
                        pretty = str(name or "").strip()
                        txt_var.set(
                            f"Oppretter {i}/{total}: {pretty}" if pretty else f"Oppretter {i}/{total}…"
                        )
                    else:
                        txt_var.set("Ingen nye klienter. Sjekker…")
                except Exception:
                    pass
            elif kind == "done":
                got_done = True
                done_stats = item[1] if len(item) > 1 else {}
            elif kind == "error":
                err = item[1] if len(item) > 1 else Exception("Ukjent feil")

        if err is not None:
            try:
                pb.stop()
            except Exception:
                pass
            try:
                progress.destroy()
            except Exception:
                pass
            messagebox.showerror("Importer", f"Kunne ikke importere klientliste: {err}")
            return

        if got_done:
            try:
                pb.stop()
            except Exception:
                pass
            try:
                progress.destroy()
            except Exception:
                pass
            if on_done is not None:
                try:
                    on_done(done_stats)
                except Exception:
                    # Best effort: callback skal ikke knekke GUI
                    pass
            return

        progress.after(80, _poll)

    _poll()
