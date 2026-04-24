"""views_column_chooser.py — Kolonnevelger-dialog.

Lar brukeren velge hvilke kolonner som skal være synlige og i hvilken
rekkefølge. Støtter:
- klikk hvor som helst på raden for å veksle synlighet
- dra rader for å endre rekkefølge (erstatter separate opp/ned-knapper)
- pinned-kolonner vises som låst (ikon + disabled text)
- brukervennlige overskriftstekster via ``headings``-parameter
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import List, Mapping, Sequence, Tuple


def _clean_columns(items: Sequence[str] | None) -> List[str]:
    return [str(c) for c in (items or []) if str(c).strip() and not str(c).startswith("_")]


def open_column_chooser(
    master,
    all_cols: Sequence[str],
    visible_cols: Sequence[str],
    initial_order: Sequence[str],
    *,
    default_visible_cols: Sequence[str] | None = None,
    default_order: Sequence[str] | None = None,
    headings: Mapping[str, str] | None = None,
    pinned: Sequence[str] | None = None,
) -> Tuple[List[str], List[str]] | None:
    """Dialog for valg av synlighet og rekkefølge.

    Returnerer ``(order, visible)`` eller ``None`` om brukeren avbryter.
    """

    dialog = tk.Toplevel(master)
    dialog.title("Kolonner")
    dialog.transient(master)
    dialog.grab_set()
    dialog.minsize(620, 480)
    try:
        dialog.configure(background="#FAFAF7")
    except Exception:
        pass

    info = ttk.Label(
        dialog,
        text=(
            "Klikk for å vise eller skjule. Dra for å endre rekkefølge.\n"
            "Visningsnavn er det som vises i tabellen; Variabel er interne kolonne-IDen."
        ),
        justify="left",
        padding=(0, 0, 0, 4),
    )
    info.pack(side="top", anchor="w", padx=12, pady=(12, 2))

    cols = _clean_columns(initial_order)
    for c in _clean_columns(all_cols):
        if c not in cols:
            cols.append(c)

    visible = [c for c in _clean_columns(visible_cols) if c in cols]

    default_cols = [c for c in _clean_columns(default_order) if c in cols]
    for c in cols:
        if c not in default_cols:
            default_cols.append(c)

    default_visible = [
        c for c in _clean_columns(default_visible_cols or visible_cols)
        if c in default_cols
    ]

    heading_map: dict[str, str] = {str(k): str(v) for k, v in (headings or {}).items()}
    pinned_set = {str(p) for p in (pinned or ())}

    # Visningslinje per kolonne — bruker heading hvis gitt, ellers ID.
    def _display_for(col: str) -> str:
        text = heading_map.get(col, "").strip()
        return text or col

    # --- Hovedliste ---
    body = ttk.Frame(dialog)
    body.pack(fill="both", expand=True, padx=12, pady=6)
    body.columnconfigure(0, weight=1)
    body.rowconfigure(0, weight=1)

    tree = ttk.Treeview(
        body,
        columns=("vis", "kol", "var", "laas"),
        show="headings",
        selectmode="browse",
        height=14,
    )
    tree.grid(row=0, column=0, sticky="nsew")
    vsb = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=vsb.set)
    vsb.grid(row=0, column=1, sticky="ns")

    tree.heading("vis", text="Vis")
    tree.column("vis", width=44, anchor="center", stretch=False)
    tree.heading("kol", text="Visningsnavn")
    tree.column("kol", width=240, anchor="w", stretch=True)
    tree.heading("var", text="Variabel")
    tree.column("var", width=150, anchor="w", stretch=False)
    tree.heading("laas", text="")
    tree.column("laas", width=34, anchor="center", stretch=False)

    try:
        tree.tag_configure("pinned", foreground="#9A9A90")
        tree.tag_configure("hidden", foreground="#6B6B66")
    except Exception:
        pass

    def refresh_tree(focus_col: str | None = None) -> None:
        tree.delete(*tree.get_children(""))
        for c in cols:
            is_pinned = c in pinned_set
            is_vis = c in visible or is_pinned
            check = "☑" if is_vis else "☐"
            lock = "🔒" if is_pinned else ""
            display = _display_for(c)
            # Skjul variabelkolonnen når den er identisk med visningsnavnet
            # — da tilfører den ingen informasjon.
            variable = c if c != display else ""
            tags: tuple[str, ...] = ()
            if is_pinned:
                tags = ("pinned",)
            elif not is_vis:
                tags = ("hidden",)
            tree.insert(
                "",
                "end",
                iid=c,
                values=(check, display, variable, lock),
                tags=tags,
            )
        if focus_col and focus_col in cols:
            try:
                tree.focus(focus_col)
                tree.selection_set(focus_col)
                tree.see(focus_col)
            except Exception:
                pass

    refresh_tree()

    # --- Interaksjon: klikk veksler synlighet ---
    def _toggle_at(iid: str) -> None:
        if not iid or iid in pinned_set:
            return
        if iid in visible:
            visible.remove(iid)
        else:
            # Sett inn på posisjon som matcher kolonnerekkefølgen
            pos = 0
            for c in cols:
                if c == iid:
                    break
                if c in visible or c in pinned_set:
                    pos += 1
            visible.insert(pos, iid)
        refresh_tree(focus_col=iid)

    def _on_click(event) -> None:
        try:
            region = str(tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region == "heading":
            return
        iid = tree.identify_row(event.y)
        if not iid:
            return
        # Registrer drag-start for mulig reorder. Toggling skjer bare
        # ved release hvis ingen drag oppstod.
        drag_state["start_iid"] = iid
        drag_state["start_y"] = event.y
        drag_state["active"] = False

    def _on_motion(event) -> None:
        start_iid = drag_state.get("start_iid") or ""
        if not start_iid:
            return
        if start_iid in pinned_set:
            return
        dy = event.y - int(drag_state.get("start_y", 0) or 0)
        if not drag_state.get("active") and abs(dy) < 6:
            return
        drag_state["active"] = True
        target_iid = tree.identify_row(event.y)
        if not target_iid or target_iid == start_iid:
            return
        if target_iid in pinned_set:
            return
        # Flytt start_iid til target-posisjonen i cols
        try:
            src_idx = cols.index(start_iid)
            dst_idx = cols.index(target_iid)
        except ValueError:
            return
        if src_idx == dst_idx:
            return
        cols.pop(src_idx)
        cols.insert(dst_idx, start_iid)
        refresh_tree(focus_col=start_iid)

    def _on_release(event) -> None:
        start_iid = drag_state.get("start_iid") or ""
        was_drag = bool(drag_state.get("active"))
        drag_state["start_iid"] = ""
        drag_state["active"] = False
        if not start_iid or was_drag:
            return
        # Ren klikk uten drag → toggle
        iid = tree.identify_row(event.y)
        if iid == start_iid:
            _toggle_at(iid)

    drag_state: dict = {"start_iid": "", "start_y": 0, "active": False}
    tree.bind("<ButtonPress-1>", _on_click)
    tree.bind("<B1-Motion>", _on_motion)
    tree.bind("<ButtonRelease-1>", _on_release)

    # Tastatur-snarveier
    def _on_space(_event=None) -> str:
        iid = tree.focus()
        if iid:
            _toggle_at(iid)
        return "break"

    def _on_alt_up(_event=None) -> str:
        iid = tree.focus()
        if not iid or iid in pinned_set:
            return "break"
        try:
            i = cols.index(iid)
        except ValueError:
            return "break"
        if i <= 0:
            return "break"
        if cols[i - 1] in pinned_set:
            return "break"
        cols[i - 1], cols[i] = cols[i], cols[i - 1]
        refresh_tree(focus_col=iid)
        return "break"

    def _on_alt_down(_event=None) -> str:
        iid = tree.focus()
        if not iid or iid in pinned_set:
            return "break"
        try:
            i = cols.index(iid)
        except ValueError:
            return "break"
        if i >= len(cols) - 1:
            return "break"
        cols[i + 1], cols[i] = cols[i], cols[i + 1]
        refresh_tree(focus_col=iid)
        return "break"

    tree.bind("<space>", _on_space)
    tree.bind("<Alt-Up>", _on_alt_up)
    tree.bind("<Alt-Down>", _on_alt_down)

    # --- Footer-knapper ---
    footer = ttk.Frame(dialog)
    footer.pack(fill="x", padx=12, pady=(4, 12))

    def set_standard() -> None:
        nonlocal cols, visible
        cols = list(default_cols)
        visible = list(default_visible)
        refresh_tree()

    ttk.Button(footer, text="Standard", command=set_standard).pack(side="left")

    def ok() -> None:
        dialog.result = (cols, visible)
        dialog.destroy()

    def cancel() -> None:
        dialog.result = None
        dialog.destroy()

    # Lagre = primær handling (høyrestilt), Avbryt rett ved siden av.
    save_btn = ttk.Button(footer, text="Lagre", command=ok)
    save_btn.pack(side="right")
    ttk.Button(footer, text="Avbryt", command=cancel).pack(side="right", padx=(0, 8))

    try:
        save_btn.focus_set()
    except Exception:
        pass

    dialog.bind("<Return>", lambda _e=None: ok())
    dialog.bind("<Escape>", lambda _e=None: cancel())

    dialog.wait_window()
    return getattr(dialog, "result", None)
