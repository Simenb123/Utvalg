# -*- coding: utf-8 -*-
"""client_store_enrich_ui.py – Preview- og progress-dialoger for klientberikelse."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import client_store
import client_store_enrich as enrich


# ---------------------------------------------------------------------------
# Preview-dialog
# ---------------------------------------------------------------------------

def _show_enrichment_preview(
    parent: tk.Widget,
    plan: enrich.EnrichmentPlan,
) -> bool:
    """Vis preview-dialog. Returnerer True hvis bruker godkjenner."""

    root = parent.winfo_toplevel()
    win = tk.Toplevel(root)
    win.title("Berik klientdata – forhåndsvisning")
    win.transient(root)
    win.grab_set()

    try:
        win.geometry("960x580")
    except Exception:
        pass

    # Oppsummering
    summary = (
        f"Matchet: {len(plan.matched)}   |   "
        f"Allerede beriket: {len(plan.already_enriched)}   |   "
        f"Utvalg uten match: {len(plan.unmatched_utvalg)}   |   "
        f"Visena uten match: {len(plan.unmatched_visena)}"
    )
    ttk.Label(win, text=summary, font=("", 10, "bold")).pack(
        fill="x", padx=12, pady=(12, 4)
    )
    ttk.Label(
        win,
        text="Berikelsen legger til org.nr og klientnr – eksisterende data overskrives ikke.",
    ).pack(fill="x", padx=12, pady=(0, 8))

    nb = ttk.Notebook(win)
    nb.pack(fill="both", expand=True, padx=12, pady=4)

    # --- Tab 1: Matchet ---
    frm_match = ttk.Frame(nb)
    nb.add(frm_match, text=f"Matchet ({len(plan.matched)})")
    frm_match.rowconfigure(0, weight=1)
    frm_match.columnconfigure(0, weight=1)

    cols_match = ("klient", "orgnr", "knr", "ansvarlig", "match")
    tv_match = ttk.Treeview(frm_match, columns=cols_match, show="headings", height=16)
    tv_match.heading("klient", text="Klient")
    tv_match.heading("orgnr", text="Org.nr")
    tv_match.heading("knr", text="Knr")
    tv_match.heading("ansvarlig", text="Ansvarlig")
    tv_match.heading("match", text="Match-type")
    tv_match.column("klient", width=300)
    tv_match.column("orgnr", width=120)
    tv_match.column("knr", width=80)
    tv_match.column("ansvarlig", width=80)
    tv_match.column("match", width=120)

    sb_match = ttk.Scrollbar(frm_match, orient="vertical", command=tv_match.yview)
    tv_match.configure(yscrollcommand=sb_match.set)
    tv_match.grid(row=0, column=0, sticky="nsew")
    sb_match.grid(row=0, column=1, sticky="ns")

    _MATCH_LABELS = {
        "exact_knr": "Eksakt Knr",
        "exact_name": "Eksakt navn",
        "fuzzy_name": "Fuzzy navn",
    }
    for m in plan.matched:
        label = _MATCH_LABELS.get(m.match_type, m.match_type)
        if m.match_type == "fuzzy_name":
            label += f" ({m.match_score:.0%})"
        tv_match.insert("", "end", values=(
            m.display_name,
            m.visena_row.org_number,
            m.visena_row.client_number,
            m.visena_row.responsible,
            label,
        ))

    # --- Tab 2: Allerede beriket ---
    frm_already = ttk.Frame(nb)
    nb.add(frm_already, text=f"Allerede beriket ({len(plan.already_enriched)})")
    frm_already.rowconfigure(0, weight=1)
    frm_already.columnconfigure(0, weight=1)

    lb_already = tk.Listbox(frm_already)
    sb_already = ttk.Scrollbar(frm_already, orient="vertical", command=lb_already.yview)
    lb_already.configure(yscrollcommand=sb_already.set)
    lb_already.grid(row=0, column=0, sticky="nsew")
    sb_already.grid(row=0, column=1, sticky="ns")
    for dn in plan.already_enriched:
        lb_already.insert("end", dn)

    # --- Tab 3: Utvalg uten match ---
    frm_no_visena = ttk.Frame(nb)
    nb.add(frm_no_visena, text=f"Uten Visena-match ({len(plan.unmatched_utvalg)})")
    frm_no_visena.rowconfigure(0, weight=1)
    frm_no_visena.columnconfigure(0, weight=1)

    lb_no_visena = tk.Listbox(frm_no_visena)
    sb_no_visena = ttk.Scrollbar(frm_no_visena, orient="vertical", command=lb_no_visena.yview)
    lb_no_visena.configure(yscrollcommand=sb_no_visena.set)
    lb_no_visena.grid(row=0, column=0, sticky="nsew")
    sb_no_visena.grid(row=0, column=1, sticky="ns")
    for dn in plan.unmatched_utvalg:
        lb_no_visena.insert("end", dn)

    # --- Tab 4: Visena uten match ---
    frm_no_utvalg = ttk.Frame(nb)
    nb.add(frm_no_utvalg, text=f"Visena uten match ({len(plan.unmatched_visena)})")
    frm_no_utvalg.rowconfigure(0, weight=1)
    frm_no_utvalg.columnconfigure(0, weight=1)

    cols_vis = ("firma", "orgnr", "knr", "ansvarlig")
    tv_vis = ttk.Treeview(frm_no_utvalg, columns=cols_vis, show="headings", height=16)
    tv_vis.heading("firma", text="Firma")
    tv_vis.heading("orgnr", text="Org.nr")
    tv_vis.heading("knr", text="Knr")
    tv_vis.heading("ansvarlig", text="Ansvarlig")
    tv_vis.column("firma", width=300)
    tv_vis.column("orgnr", width=120)
    tv_vis.column("knr", width=80)
    tv_vis.column("ansvarlig", width=80)

    sb_vis = ttk.Scrollbar(frm_no_utvalg, orient="vertical", command=tv_vis.yview)
    tv_vis.configure(yscrollcommand=sb_vis.set)
    tv_vis.grid(row=0, column=0, sticky="nsew")
    sb_vis.grid(row=0, column=1, sticky="ns")

    for vr in plan.unmatched_visena:
        tv_vis.insert("", "end", values=(vr.firma, vr.org_number, vr.client_number, vr.responsible))

    # --- Knapper ---
    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(4, 12))

    ok_state = {"ok": False}

    def on_ok():
        ok_state["ok"] = True
        win.destroy()

    def on_cancel():
        win.destroy()

    ok_btn = ttk.Button(btns, text="Start berikelse", command=on_ok)
    cancel_btn = ttk.Button(btns, text="Avbryt", command=on_cancel)
    cancel_btn.pack(side="right")
    ok_btn.pack(side="right", padx=(0, 8))

    if not plan.matched:
        ok_btn.state(["disabled"])

    win.wait_window()
    return ok_state["ok"]


# ---------------------------------------------------------------------------
# Progress-dialog + bakgrunnstråd
# ---------------------------------------------------------------------------

def _run_enrichment_with_progress(
    parent: tk.Widget,
    matches: list[enrich.EnrichmentMatch],
    on_done: Optional[callable] = None,
) -> None:
    """Kjør berikelse i bakgrunnstråd med progresjonsvindu."""

    win = tk.Toplevel(parent)
    win.title("Beriker klientdata")
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    status = ttk.Label(win, text="Starter berikelse…")
    status.pack(padx=12, pady=(12, 6))

    pb = ttk.Progressbar(win, length=420, mode="determinate", maximum=len(matches))
    pb.pack(padx=12, pady=(0, 12))

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=12, pady=(0, 12))

    cancel_event = threading.Event()

    def _on_cancel():
        cancel_event.set()
        try:
            cancel_btn.state(["disabled"])
        except Exception:
            pass
        status.config(text="Avbryter…")

    cancel_btn = ttk.Button(btns, text="Avbryt", command=_on_cancel)
    cancel_btn.pack(side="right")

    win.protocol("WM_DELETE_WINDOW", _on_cancel)

    q: Queue[tuple] = Queue()

    def progress_cb(done: int, total: int, name: str) -> None:
        q.put(("progress", done, total, name))

    def worker():
        try:
            stats = enrich.apply_enrichment(
                matches, progress_cb=progress_cb, cancel_event=cancel_event
            )
            q.put(("done", stats))
        except Exception as e:
            q.put(("error", str(e)))

    threading.Thread(target=worker, daemon=True).start()

    def poll():
        try:
            while True:
                msg = q.get_nowait()
                if not msg:
                    continue
                kind = msg[0]
                if kind == "progress":
                    _, done, total, name = msg
                    pb.configure(value=done)
                    status.config(text=f"Beriker {done}/{total}: {name}")
                elif kind == "done":
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    stats = msg[1]
                    if stats.get("cancelled"):
                        messagebox.showinfo(
                            "Berik klientdata",
                            f"Avbrutt. {stats.get('enriched', 0)} klienter beriket.",
                            parent=parent,
                        )
                    else:
                        messagebox.showinfo(
                            "Berik klientdata",
                            f"{stats.get('enriched', 0)} klienter beriket.",
                            parent=parent,
                        )
                    if on_done:
                        on_done(stats)
                    return
                elif kind == "error":
                    try:
                        win.destroy()
                    except Exception:
                        pass
                    messagebox.showerror("Berik klientdata", msg[1], parent=parent)
                    return
        except Empty:
            pass
        win.after(60, poll)

    poll()


# ---------------------------------------------------------------------------
# Offentlig API — knyttes til knapp i page_regnskap.py
# ---------------------------------------------------------------------------

def start_enrichment_flow(parent: tk.Widget, on_done: Optional[callable] = None) -> None:
    """Åpne fildialog, planlegg berikelse, vis preview, kjør.

    Kall denne fra 'Berik klientdata…'-knappen.
    """

    file_path = filedialog.askopenfilename(
        parent=parent,
        title="Velg Visena prosessliste (XLSX)",
        filetypes=[("Excel-filer", "*.xlsx *.xls"), ("Alle filer", "*.*")],
    )
    if not file_path:
        return

    path = Path(file_path)

    # Les Visena-data
    try:
        visena_rows = enrich.read_enrichment_data_xlsx(path)
    except Exception as e:
        messagebox.showerror(
            "Berik klientdata",
            f"Kunne ikke lese filen:\n\n{e}",
            parent=parent,
        )
        return

    if not visena_rows:
        messagebox.showinfo(
            "Berik klientdata",
            "Fant ingen rader i filen.",
            parent=parent,
        )
        return

    # Hent eksisterende klienter
    existing = client_store.list_clients()

    # Planlegg berikelse
    try:
        plan = enrich.plan_enrichment(visena_rows, existing)
    except Exception as e:
        messagebox.showerror(
            "Berik klientdata",
            f"Feil under planlegging:\n\n{e}",
            parent=parent,
        )
        return

    if not plan.matched:
        messagebox.showinfo(
            "Berik klientdata",
            f"Ingen klienter matchet.\n\n"
            f"Allerede beriket: {len(plan.already_enriched)}\n"
            f"Utvalg uten match: {len(plan.unmatched_utvalg)}\n"
            f"Visena uten match: {len(plan.unmatched_visena)}",
            parent=parent,
        )
        return

    # Vis preview
    ok = _show_enrichment_preview(parent, plan)
    if not ok:
        return

    # Kjør berikelse
    _run_enrichment_with_progress(parent, plan.matched, on_done=on_done)
