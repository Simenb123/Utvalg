"""analyse_sb_konto_review.py — konto-review (OK, vedlegg, kommentarer, handlingskoblinger).

Utskilt fra page_analyse_sb.py. Funksjonene tar `page` som første argument
og page_analyse_sb re-eksporterer dem for bakoverkompatibilitet.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from analyse_sb_refresh import refresh_sb_view


def _session_client_year() -> tuple[str, str]:
    try:
        import session as _session
        client = str(getattr(_session, "client", "") or "").strip()
        year = str(getattr(_session, "year", "") or "").strip()
        return client, year
    except Exception:
        return "", ""


def _refresh_sb_after_review_change(page: Any) -> None:
    try:
        refresh_sb_view(page=page)
    except Exception:
        pass


def _set_accounts_ok(*, page: Any, kontoer: list[str], ok: bool) -> None:
    client, year = _session_client_year()
    if not client or not year or not kontoer:
        return
    try:
        import src.shared.regnskap.client_overrides as _rco
        _rco.set_accounts_ok(client, year, kontoer, ok)
    except Exception:
        return
    _refresh_sb_after_review_change(page)


def _action_link_menu_label(*, kind: str, entity_key: str, base: str) -> str:
    """Returner menu-label med antall eksisterende koblinger, hvis noen."""
    client, year = _session_client_year()
    if not client or not year or not entity_key:
        return base
    try:
        import src.shared.regnskap.client_overrides as _rco
        if kind == "account":
            links_map = _rco.load_account_action_links(client, year)
        else:
            links_map = _rco.load_rl_action_links(client, year)
        n = len(links_map.get(str(entity_key), []))
    except Exception:
        return base
    if n <= 0:
        return base
    if n == 1:
        return f"{base} (1 koblet)"
    return f"{base} ({n} koblet)"


def _open_action_link_dialog(
    *, page: Any, kind: str, entity_key: str, entity_label: str
) -> None:
    """Åpne handlingskobling-dialog og oppfrisk visning etter lagring."""
    client, year = _session_client_year()
    if not client or not year or not entity_key:
        return
    try:
        from action_link_dialog import open_action_link_dialog as _open
    except Exception:
        return
    _open(
        parent=page,
        client=client,
        year=year,
        kind=kind,
        entity_key=str(entity_key),
        entity_label=entity_label,
        on_saved=lambda: _refresh_sb_after_review_change(page),
    )


def _resolve_regnr_by_konto(*, page: Any, kontoer: list[str]) -> dict[str, tuple[int, str]]:
    """Slå opp (regnr, regnskapslinje) for hver konto via den kanoniske RL-servicen."""
    out: dict[str, tuple[int, str]] = {}
    if not kontoer:
        return out

    import regnskapslinje_mapping_service as _rl_svc

    context = _rl_svc.context_from_page(page)
    cleaned = [str(k or "").strip() for k in kontoer if str(k or "").strip()]
    if not cleaned:
        return out
    resolved = _rl_svc.resolve_accounts_to_rl(cleaned, context=context)
    if resolved.empty:
        return out
    for _, row in resolved.iterrows():
        regnr_val = row.get("regnr")
        if pd.isna(regnr_val):
            continue
        konto = str(row.get("konto", "") or "").strip()
        if not konto:
            continue
        out[konto] = (int(regnr_val), str(row.get("regnskapslinje", "") or ""))
    return out


def _add_attachments_to_kontoer(*, page: Any, kontoer: list[str]) -> None:
    if not kontoer:
        return
    try:
        from tkinter import filedialog
    except Exception:
        return

    client, year = _session_client_year()
    if not client or not year:
        return

    paths = filedialog.askopenfilenames(
        parent=page,
        title=f"Velg vedlegg for {len(kontoer)} konto(er)",
    )
    if not paths:
        return

    regnr_by_konto = _resolve_regnr_by_konto(page=page, kontoer=kontoer)

    try:
        import src.shared.regnskap.client_overrides as _rco
        _rco.add_account_attachments(
            client, year, kontoer, list(paths),
            regnr_by_konto=regnr_by_konto,
        )
    except Exception:
        return
    _refresh_sb_after_review_change(page)


def _open_path(path: str) -> None:
    """Åpne fil eller mappe i systemstandard program."""
    import os
    import subprocess
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif os.uname().sysname == "Darwin":  # type: ignore[attr-defined]
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def _show_attachments_dialog(*, page: Any, konto: str, kontonavn: str) -> None:
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return

    client, year = _session_client_year()
    if not client or not year:
        return

    def _load_rows() -> list[dict]:
        try:
            import src.shared.regnskap.client_overrides as _rco
            return _rco.list_account_attachments(client, year, konto)
        except Exception:
            return []

    dlg = tk.Toplevel(page)
    dlg.title(f"Vedlegg — {konto} {kontonavn}".strip())
    dlg.resizable(True, True)
    dlg.minsize(720, 360)

    ttk.Label(
        dlg,
        text=f"Vedlegg for konto {konto} {kontonavn}".strip(),
    ).pack(padx=12, pady=(10, 6), anchor="w")

    cols = ("label", "path", "storage", "added_at", "status")
    tree = ttk.Treeview(dlg, columns=cols, show="headings", height=8, selectmode="browse")
    tree.heading("label", text="Navn")
    tree.heading("path", text="Sti")
    tree.heading("storage", text="Lagring")
    tree.heading("added_at", text="Lagt til")
    tree.heading("status", text="Status")
    tree.column("label", width=180, anchor="w")
    tree.column("path", width=320, anchor="w")
    tree.column("storage", width=110, anchor="center")
    tree.column("added_at", width=120, anchor="w")
    tree.column("status", width=70, anchor="center")
    tree.pack(padx=12, pady=4, fill="both", expand=True)

    from pathlib import Path as _Path

    def _storage_label(row: dict) -> str:
        s = str(row.get("storage", "external") or "external").lower()
        return "Utvalg-lager" if s == "managed" else "Ekstern"

    def _fill() -> None:
        for iid in tree.get_children(""):
            tree.delete(iid)
        for row in _load_rows():
            p = row.get("path", "")
            exists = False
            try:
                exists = _Path(p).exists()
            except Exception:
                exists = False
            tree.insert("", "end", values=(
                row.get("label", "") or _Path(p).name,
                p,
                _storage_label(row),
                row.get("added_at", ""),
                "" if exists else "Mangler",
            ))

    def _selected_path() -> str:
        sel = tree.selection()
        if not sel:
            return ""
        vals = tree.item(sel[0], "values")
        return str(vals[1]) if vals and len(vals) > 1 else ""

    def _selected_row() -> dict | None:
        p = _selected_path()
        if not p:
            return None
        for row in _load_rows():
            if str(row.get("path", "")) == p:
                return row
        return None

    def _do_open() -> None:
        p = _selected_path()
        if not p:
            return
        if not _Path(p).exists():
            messagebox.showinfo("Vedlegg", f"Filen finnes ikke lenger:\n{p}", parent=dlg)
            return
        _open_path(p)

    def _do_open_folder() -> None:
        p = _selected_path()
        if not p:
            return
        folder = str(_Path(p).parent)
        if not _Path(folder).exists():
            messagebox.showinfo("Vedlegg", f"Mappen finnes ikke:\n{folder}", parent=dlg)
            return
        _open_path(folder)

    def _do_remove() -> None:
        p = _selected_path()
        if not p:
            return
        if not messagebox.askyesno("Fjern kobling", f"Fjerne koblingen til:\n{p}?", parent=dlg):
            return
        try:
            import src.shared.regnskap.client_overrides as _rco
            _rco.remove_account_attachment(client, year, konto, p)
        except Exception:
            return
        _fill()
        _refresh_sb_after_review_change(page)

    def _do_migrate() -> None:
        row = _selected_row()
        if not row:
            return
        if str(row.get("storage", "external")).lower() == "managed":
            messagebox.showinfo("Utvalg-lager",
                                "Vedlegget er allerede lagret i Utvalg-lager.",
                                parent=dlg)
            return
        src = str(row.get("path", ""))
        if not src or not _Path(src).exists():
            messagebox.showinfo("Utvalg-lager",
                                f"Kan ikke migrere — kildefilen finnes ikke:\n{src}",
                                parent=dlg)
            return
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[konto])
        rl_info = rbk.get(konto)
        if not rl_info:
            messagebox.showinfo("Utvalg-lager",
                                f"Fant ikke regnskapslinje for konto {konto}.",
                                parent=dlg)
            return
        try:
            import src.shared.regnskap.client_overrides as _rco
            _rco.migrate_attachment_to_managed(
                client, year, konto, src,
                regnr=rl_info[0], regnskapslinje=rl_info[1],
            )
        except Exception as exc:
            messagebox.showerror("Utvalg-lager", f"Migrering feilet:\n{exc}", parent=dlg)
            return
        _fill()
        _refresh_sb_after_review_change(page)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(padx=12, pady=(4, 10), fill="x")
    ttk.Button(btn_frame, text="Åpne", command=_do_open).pack(side="left")
    ttk.Button(btn_frame, text="Åpne mappe", command=_do_open_folder).pack(side="left", padx=(6, 0))
    ttk.Button(btn_frame, text="Kopier inn i Utvalg-lager", command=_do_migrate).pack(side="left", padx=(6, 0))
    ttk.Button(btn_frame, text="Fjern kobling", command=_do_remove).pack(side="left", padx=(6, 0))
    ttk.Button(btn_frame, text="Lukk", command=dlg.destroy).pack(side="right")

    _fill()

    # Tastatur + dobbeltklikk: Enter/dblclick åpner, Delete fjerner, Escape lukker
    tree.bind("<Double-1>", lambda _e: _do_open())
    tree.bind("<Return>", lambda _e: _do_open())
    tree.bind("<Delete>", lambda _e: _do_remove())
    dlg.bind("<Escape>", lambda _e: dlg.destroy())

    dlg.update_idletasks()
    w = max(dlg.winfo_width(), 1000)
    h = max(dlg.winfo_height(), 520)
    try:
        x = page.winfo_rootx() + max(0, (page.winfo_width() - w) // 2)
        y = page.winfo_rooty() + max(0, (page.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass
    tree.focus_set()


# =====================================================================
# Drag-n-drop: SB-konto → Regnskapslinje (remap)
# =====================================================================
# Kommentarer
# =====================================================================

def _edit_comment(*, page: Any, kind: str, key: str, label: str) -> None:
    """Åpne en dialog for å legge til/redigere en kommentar.

    Vanlig resizable Toplevel-vindu med standard min/maks-knapper.
    Ctrl+Enter lagrer, Escape lukker uten å lagre.
    """
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return

    try:
        import session as _session
        import src.shared.regnskap.client_overrides as regnskap_client_overrides
        client = getattr(_session, "client", None) or ""
    except Exception:
        return
    if not client:
        return

    comments = regnskap_client_overrides.load_comments(client)
    current = comments.get(kind, {}).get(str(key), "")

    dlg = tk.Toplevel(page)
    dlg.title(f"Kommentar — {label}".strip())
    dlg.resizable(True, True)
    dlg.minsize(560, 320)

    header = ttk.Frame(dlg)
    header.pack(padx=14, pady=(12, 4), fill="x")
    ttk.Label(header, text=label, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
    ttk.Label(header, text="Ctrl+Enter lagrer · Escape lukker",
              foreground="#666").pack(anchor="w", pady=(2, 0))

    text_wrap = ttk.Frame(dlg)
    text_wrap.pack(padx=14, pady=(4, 8), fill="both", expand=True)
    txt = tk.Text(text_wrap, height=12, wrap="word",
                  padx=8, pady=6, undo=True)
    scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=txt.yview)
    txt.configure(yscrollcommand=scroll.set)
    txt.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    txt.insert("1.0", current)
    txt.focus_set()

    def _refresh_analysis() -> None:
        try:
            refresh_views = getattr(page, "_refresh_analysis_views_after_adjustment_change", None)
            if callable(refresh_views):
                refresh_views()
            else:
                page._refresh_pivot()
                page._refresh_transactions_view()
        except Exception:
            pass

    def _save(_event: Any = None) -> str:
        new_text = txt.get("1.0", "end").strip()
        regnskap_client_overrides.save_comment(client, kind=kind, key=str(key), text=new_text)
        dlg.destroy()
        _refresh_analysis()
        return "break"

    def _remove(_event: Any = None) -> str:
        regnskap_client_overrides.save_comment(client, kind=kind, key=str(key), text="")
        dlg.destroy()
        _refresh_analysis()
        return "break"

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(padx=14, pady=(0, 12), fill="x")
    ttk.Button(btn_frame, text="Lagre", command=_save).pack(side="right", padx=(6, 0))
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy).pack(side="right")
    if current:
        ttk.Button(btn_frame, text="Fjern", command=_remove).pack(side="left")

    dlg.bind("<Control-Return>", _save)
    dlg.bind("<Escape>", lambda _e: dlg.destroy())

    dlg.update_idletasks()
    try:
        w, h = 640, 420
        x = page.winfo_rootx() + max(0, (page.winfo_width() - w) // 2)
        y = page.winfo_rooty() + max(0, (page.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass

