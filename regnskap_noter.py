"""regnskap_noter.py -- Noter-system for RegnskapPage.

Ekstrahert fra page_regnskap.py.  Bygger, laster, lagrer og eksporterer noter.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import preferences
from regnskap_data import (
    PRINSIPP_DEFAULT,
    PRINSIPP_DEFAULTS,
    fmt_amount,
    get_notes_for_framework,
    build_note_numbers,
    save_note_template,
    list_note_templates,
    load_note_template,
    delete_note_template,
)

log = logging.getLogger(__name__)

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore
    messagebox = None  # type: ignore


# ---------------------------------------------------------------------------
# Scrollable / form helpers (were module-level in page_regnskap.py)
# ---------------------------------------------------------------------------

def make_scrollable(parent: Any) -> tuple[Any, Any]:
    """Returns (canvas, inner_frame) for a scrollable note form."""
    if tk is None:
        return None, None

    canvas = tk.Canvas(parent, bg="#FAFAFA", highlightthickness=0)
    vsb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=vsb.set)

    inner = ttk.Frame(canvas, padding=(12, 8, 12, 12))
    win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

    def _on_inner_configure(_e: Any) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _on_canvas_configure(e: Any) -> None:
        canvas.itemconfig(win_id, width=e.width)

    inner.bind("<Configure>", _on_inner_configure)
    canvas.bind("<Configure>", _on_canvas_configure)

    def _scroll(event: Any) -> None:
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _scroll))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))

    vsb.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    return canvas, inner


def build_note_form(
    parent: Any,
    spec: list[dict],
) -> tuple[Any, dict[str, Any]]:
    """
    Build a structured note form in parent.
    Returns (canvas, entry_widgets_by_key).
    """
    if tk is None:
        return None, {}

    canvas, inner = make_scrollable(parent)
    if inner is None:
        return None, {}

    inner.columnconfigure(0, weight=1, minsize=260)
    inner.columnconfigure(1, weight=0, minsize=160)

    entry_widgets: dict[str, tk.StringVar] = {}

    HDR_BG    = "#E3EAF4"
    AUTO_FG   = "#1A56A0"
    FIELD_BG  = "#FFFFFF"

    row_idx = 0

    for spec_row in spec:
        rtype = spec_row["type"]

        if rtype == "header":
            lbl = ttk.Label(
                inner,
                text=spec_row["label"],
                font=("TkDefaultFont", 9, "bold"),
                foreground="#1A2E5A",
                background=HDR_BG,
                anchor="w",
                padding=(6, 4),
            )
            lbl.grid(row=row_idx, column=0, columnspan=2, sticky="ew",
                     pady=(10, 2))
            row_idx += 1

        elif rtype == "sep":
            sep = ttk.Separator(inner, orient="horizontal")
            sep.grid(row=row_idx, column=0, columnspan=2, sticky="ew",
                     pady=6)
            row_idx += 1

        elif rtype == "auto":
            lbl = ttk.Label(inner, text="  " + spec_row["label"],
                             anchor="w", font=("TkDefaultFont", 10))
            lbl.grid(row=row_idx, column=0, sticky="ew", pady=1)

            svar = tk.StringVar(value="\u2013")
            entry = ttk.Entry(inner, textvariable=svar, width=22,
                               state="readonly", justify="right",
                               font=("TkDefaultFont", 10))
            try:
                style_name = "Auto.TEntry"
                entry.configure(style=style_name)
            except Exception:
                pass
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(6, 0), pady=1)

            key = f"__auto__{spec_row.get('regnr', '')}_{spec_row.get('period', 'current')}"
            entry_widgets[key] = svar
            row_idx += 1

        elif rtype == "field":
            lbl = ttk.Label(inner, text="  " + spec_row["label"],
                             anchor="w", font=("TkDefaultFont", 10))
            lbl.grid(row=row_idx, column=0, sticky="ew", pady=1)

            key = spec_row.get("key", f"_field_{row_idx}")
            svar = tk.StringVar(value=spec_row.get("default", ""))
            entry = ttk.Entry(inner, textvariable=svar, width=22,
                               justify="right", font=("TkDefaultFont", 10))
            entry.grid(row=row_idx, column=1, sticky="ew", padx=(6, 0), pady=1)

            entry_widgets[key] = svar
            row_idx += 1

    return canvas, entry_widgets


# ---------------------------------------------------------------------------
# Tab building
# ---------------------------------------------------------------------------

def build_noter_tab(page: Any, parent: Any) -> None:
    parent.rowconfigure(1, weight=1)
    parent.columnconfigure(0, weight=1)

    note_toolbar = ttk.Frame(parent)
    note_toolbar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))

    ttk.Button(note_toolbar, text="Ny egendefinert note",
               command=page._add_custom_note, width=20).pack(side="left", padx=2)

    ttk.Separator(note_toolbar, orient="vertical").pack(
        side="left", fill="y", padx=6, pady=2)

    ttk.Button(note_toolbar, text="Lagre som mal",
               command=page._save_as_template, width=14).pack(side="left", padx=2)
    ttk.Button(note_toolbar, text="Last inn mal",
               command=page._load_from_template, width=14).pack(side="left", padx=2)

    noter_nb = ttk.Notebook(parent)
    noter_nb.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
    page._noter_nb = noter_nb

    rebuild_noter_tabs(page)


def rebuild_noter_tabs(page: Any) -> None:
    """Rebuild all note tabs based on framework + custom notes."""
    old_data = collect_notes_data(page)

    nb = page._noter_nb
    for child in nb.tabs():
        nb.forget(child)
    page._note_vars.clear()
    page._note_text_widgets.clear()

    fw_notes = get_notes_for_framework(page._framework)
    custom = [(nid, lbl, None) for nid, lbl in page._custom_notes]
    all_notes = fw_notes + custom

    page._active_notes = all_notes
    page._active_note_numbers, page._active_note_refs = build_note_numbers(all_notes)

    for note_id, note_label, spec in all_notes:
        is_custom = any(nid == note_id for nid, _ in page._custom_notes)
        build_single_note_tab(page, nb, note_id, note_label, spec, is_custom)

    apply_notes_data(page, old_data)
    update_note_auto_values(page)


def build_single_note_tab(
    page: Any, nb: Any, note_id: str, note_label: str,
    spec: list | None, is_custom: bool = False,
) -> None:
    tab = ttk.Frame(nb)
    nb.add(tab, text=note_label)
    tab.rowconfigure(1, weight=1)
    tab.columnconfigure(0, weight=1)

    btn_bar = ttk.Frame(tab)
    btn_bar.grid(row=0, column=0, sticky="ew", padx=4, pady=(4, 0))
    ttk.Button(btn_bar, text="Lagre note",
               command=lambda nid=note_id: save_note(page, nid),
               width=12).pack(side="left")
    ttk.Label(btn_bar,
              text="  Lagres per klient. Auto-verdier hentes fra regnskapet.",
              foreground="#888888").pack(side="left")
    if is_custom:
        ttk.Button(
            btn_bar, text="Fjern note",
            command=lambda nid=note_id: remove_custom_note(page, nid),
            width=10,
        ).pack(side="right", padx=2)

    content_frame = ttk.Frame(tab)
    content_frame.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
    content_frame.rowconfigure(0, weight=1)
    content_frame.columnconfigure(0, weight=1)

    if spec is None:
        default_text = ""
        if note_id == "regnskapsprinsipper":
            default_text = PRINSIPP_DEFAULTS.get(page._framework, PRINSIPP_DEFAULT)
        txt = tk.Text(content_frame, wrap="word",
                      font=("TkDefaultFont", 10),
                      relief="flat", bg="#FAFAFA", padx=10, pady=8,
                      undo=True)
        vsb = ttk.Scrollbar(content_frame, orient="vertical",
                            command=txt.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=vsb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        if default_text:
            txt.insert("1.0", default_text)
        txt.bind("<Control-s>",
                 lambda _e, nid=note_id: save_note(page, nid) or "break")
        page._note_text_widgets[note_id] = txt
    else:
        canvas, entry_vars = build_note_form(content_frame, spec)
        page._note_vars[note_id] = entry_vars


# ---------------------------------------------------------------------------
# Framework change
# ---------------------------------------------------------------------------

def on_framework_change(page: Any, *_args: Any) -> None:
    new_fw = page._framework_var.get()
    if new_fw == page._framework:
        return
    page._framework = new_fw
    preferences.set(
        page._pref_key("__meta__", "framework"),
        new_fw,
    )
    rebuild_noter_tabs(page)
    load_all_notes(page)


# ---------------------------------------------------------------------------
# Custom notes
# ---------------------------------------------------------------------------

def add_custom_note(page: Any) -> None:
    """Dialog for a legge til en egendefinert fritekst-note."""
    dlg = tk.Toplevel(page)
    dlg.title("Ny egendefinert note")
    dlg.geometry("340x120")
    dlg.transient(page)
    dlg.grab_set()

    ttk.Label(dlg, text="Notetittel:").pack(padx=12, pady=(12, 2), anchor="w")
    var = tk.StringVar()
    entry = ttk.Entry(dlg, textvariable=var, width=40)
    entry.pack(padx=12, pady=2)
    entry.focus_set()

    def _ok(*_: Any) -> None:
        name = var.get().strip()
        if not name:
            return
        nid = "custom_" + "".join(
            c if c.isalnum() else "_" for c in name.lower()
        )
        if any(n == nid for n, _ in page._custom_notes):
            messagebox.showwarning("Duplikat", f"Noten \u00ab{name}\u00bb finnes allerede.", parent=dlg)
            return
        page._custom_notes.append((nid, name))
        save_custom_notes_list(page)
        rebuild_noter_tabs(page)
        load_all_notes(page)
        try:
            page._noter_nb.select(len(page._noter_nb.tabs()) - 1)
        except Exception:
            pass
        dlg.destroy()

    entry.bind("<Return>", _ok)
    ttk.Button(dlg, text="Opprett", command=_ok, width=10).pack(pady=8)


def remove_custom_note(page: Any, note_id: str) -> None:
    if messagebox and not messagebox.askyesno(
            "Fjern note", "Fjerne denne noten?", parent=page):
        return
    page._custom_notes = [(n, l) for n, l in page._custom_notes if n != note_id]
    save_custom_notes_list(page)
    rebuild_noter_tabs(page)
    load_all_notes(page)


def save_custom_notes_list(page: Any) -> None:
    """Persist the list of custom note IDs for this client."""
    data = [{"id": nid, "label": lbl} for nid, lbl in page._custom_notes]
    preferences.set(
        page._pref_key("__meta__", "custom_notes"),
        json.dumps(data, ensure_ascii=False),
    )


def load_custom_notes_list(page: Any) -> None:
    """Load custom notes list from preferences."""
    raw = preferences.get(page._pref_key("__meta__", "custom_notes"))
    if not raw:
        page._custom_notes = []
        return
    try:
        data = json.loads(raw)
        page._custom_notes = [(d["id"], d["label"]) for d in data]
    except Exception:
        page._custom_notes = []


# ---------------------------------------------------------------------------
# Note template library
# ---------------------------------------------------------------------------

def save_as_template(page: Any) -> None:
    """Lagre navarende noteverdier som en gjenbrukbar mal."""
    dlg = tk.Toplevel(page)
    dlg.title("Lagre notemal")
    dlg.geometry("380x120")
    dlg.transient(page)
    dlg.grab_set()

    ttk.Label(dlg, text="Malnavn:").pack(padx=12, pady=(12, 2), anchor="w")
    var = tk.StringVar()
    entry = ttk.Entry(dlg, textvariable=var, width=44)
    entry.pack(padx=12, pady=2)
    entry.focus_set()

    def _ok(*_: Any) -> None:
        name = var.get().strip()
        if not name:
            return
        notes_data = collect_notes_data(page)
        save_note_template(name, notes_data)
        messagebox.showinfo(
            "Mal lagret",
            f"Notemalen \u00ab{name}\u00bb er lagret.\n\nKan gjenbrukes p\u00e5 andre klienter.",
            parent=dlg,
        )
        dlg.destroy()

    entry.bind("<Return>", _ok)
    ttk.Button(dlg, text="Lagre", command=_ok, width=10).pack(pady=8)


def load_from_template(page: Any) -> None:
    """Last inn en notemal fra biblioteket."""
    templates = list_note_templates()
    if not templates:
        messagebox.showinfo(
            "Ingen maler",
            "Det er ingen lagrede notemaler enn\u00e5.\n"
            "Bruk \u00abLagre som mal\u00bb for \u00e5 opprette en.",
            parent=page,
        )
        return

    dlg = tk.Toplevel(page)
    dlg.title("Last inn notemal")
    dlg.geometry("400x300")
    dlg.transient(page)
    dlg.grab_set()

    ttk.Label(dlg, text="Velg mal:").pack(padx=12, pady=(12, 2), anchor="w")

    listbox = tk.Listbox(dlg, height=8)
    for t in templates:
        listbox.insert("end", t)
    listbox.pack(padx=12, pady=4, fill="both", expand=True)
    if templates:
        listbox.selection_set(0)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=8)

    def _load() -> None:
        sel = listbox.curselection()
        if not sel:
            return
        name = templates[sel[0]]
        data = load_note_template(name)
        if data is None:
            messagebox.showerror("Feil", f"Kunne ikke laste malen \u00ab{name}\u00bb.", parent=dlg)
            return
        apply_notes_data(page, data)
        messagebox.showinfo("Mal lastet", f"Malen \u00ab{name}\u00bb er lastet inn.", parent=dlg)
        dlg.destroy()

    def _delete() -> None:
        sel = listbox.curselection()
        if not sel:
            return
        name = templates[sel[0]]
        if not messagebox.askyesno("Slett mal", f"Slette malen \u00ab{name}\u00bb?", parent=dlg):
            return
        delete_note_template(name)
        listbox.delete(sel[0])
        templates.pop(sel[0])

    ttk.Button(btn_frame, text="Last inn", command=_load, width=12).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="Slett", command=_delete, width=8).pack(side="left", padx=4)
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy, width=8).pack(side="left", padx=4)


def apply_notes_data(page: Any, data: dict[str, dict[str, str]]) -> None:
    """Apply note data dict to current widgets."""
    if not data:
        return
    for note_id, vals in data.items():
        vars_dict = page._note_vars.get(note_id)
        if vars_dict:
            for key, value in vals.items():
                if key.startswith("__auto__"):
                    continue
                svar = vars_dict.get(key)
                if svar is not None:
                    try:
                        svar.set(str(value))
                    except Exception:
                        pass
        txt = page._note_text_widgets.get(note_id)
        if txt is not None and "tekst" in vals:
            try:
                txt.delete("1.0", "end")
                txt.insert("1.0", vals["tekst"])
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Auto-values
# ---------------------------------------------------------------------------

def update_note_auto_values(page: Any) -> None:
    """Fill in all __auto__ StringVars from ub/ub_prev."""
    for note_id, vars_dict in page._note_vars.items():
        for key, svar in vars_dict.items():
            if not key.startswith("__auto__"):
                continue
            parts = key.split("__auto__", 1)[-1].split("_", 1)
            if len(parts) != 2:
                continue
            try:
                regnr  = int(parts[0])
                period = parts[1]
            except ValueError:
                continue
            lookup = page._ub_prev if (period == "prev" and page._ub_prev) else page._ub
            val = lookup.get(regnr)
            try:
                svar.set(fmt_amount(val) if val is not None else "\u2013")
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_all_notes(page: Any) -> None:
    for note_id, vars_dict in page._note_vars.items():
        for key, svar in vars_dict.items():
            if key.startswith("__auto__"):
                continue
            saved = preferences.get(page._pref_key(note_id, key))
            if saved is not None:
                try:
                    svar.set(str(saved))
                except Exception:
                    pass
    for note_id, txt in page._note_text_widgets.items():
        saved = preferences.get(page._pref_key(note_id, "tekst"))
        if saved and isinstance(saved, str):
            try:
                txt.delete("1.0", "end")
                txt.insert("1.0", saved)
            except Exception:
                pass


def autofill_dm_note(page: Any) -> None:
    """Auto-fyll driftsmidler-notefelt fra DriftsmidlerPage hvis tomme."""
    dm_page = page._driftsmidler_page
    if dm_page is None or not hasattr(dm_page, "get_note_data"):
        return
    try:
        dm_data = dm_page.get_note_data()
    except Exception:
        return
    if not dm_data:
        return
    vars_dict = page._note_vars.get("driftsmidlernote")
    if not vars_dict:
        return
    for key, value in dm_data.items():
        svar = vars_dict.get(key)
        if svar is None:
            continue
        try:
            current = svar.get()
        except Exception:
            current = ""
        if not current or not str(current).strip():
            try:
                svar.set(str(value))
            except Exception:
                pass


def save_note(page: Any, note_id: str) -> None:
    vars_dict = page._note_vars.get(note_id) or {}
    for key, svar in vars_dict.items():
        if key.startswith("__auto__"):
            continue
        try:
            preferences.set(page._pref_key(note_id, key), svar.get())
        except Exception:
            pass
    txt = page._note_text_widgets.get(note_id)
    if txt is not None:
        try:
            content = txt.get("1.0", "end-1c")
            preferences.set(page._pref_key(note_id, "tekst"), content)
        except Exception:
            pass


def collect_notes_data(page: Any) -> dict[str, dict[str, str]]:
    """Gather all note field values for export."""
    out: dict[str, dict[str, str]] = {}
    for note_id, vars_dict in page._note_vars.items():
        nd: dict[str, str] = {}
        for key, svar in vars_dict.items():
            if key.startswith("__auto__"):
                continue
            try:
                nd[key] = svar.get()
            except Exception:
                nd[key] = ""
        out[note_id] = nd
    for note_id, txt in page._note_text_widgets.items():
        try:
            out.setdefault(note_id, {})["tekst"] = txt.get("1.0", "end-1c")
        except Exception:
            pass
    return out
