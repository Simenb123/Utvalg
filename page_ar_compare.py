"""page_ar_compare.py — compare/changes-fanene for ARPage.

Utskilt fra page_ar.py. Modulfunksjoner tar page som første argument.
ARPage beholder tynne delegatorer for bakoverkompatibilitet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tkinter as tk
from tkinter import messagebox, ttk

from ar_store import accept_pending_ownership_changes, accept_pending_owner_changes

from page_ar_formatters import (
    _compare_change_label,
    _fmt_currency,
    _fmt_pct,
    _fmt_signed_thousand,
    _fmt_thousand,
    _safe_text,
)


def build_changes_tab(page, parent: ttk.Frame) -> None:
    sh_frame = ttk.LabelFrame(parent, text="Aksjonærendringer i klienten", padding=4)
    sh_frame.grid(row=0, column=0, sticky="nsew")
    sh_frame.columnconfigure(0, weight=1)
    sh_frame.rowconfigure(1, weight=1)

    page.var_sh_changes_empty = tk.StringVar(value="")
    page._lbl_sh_changes_empty = ttk.Label(
        sh_frame,
        textvariable=page.var_sh_changes_empty,
        foreground="#98A2B3",
        wraplength=700,
        justify="left",
    )

    sh_cols = ("owner", "change", "shares_base", "shares_current", "delta", "pct_current", "has_trace")
    sh_tree = ttk.Treeview(sh_frame, columns=sh_cols, show="headings", selectmode="browse")
    sh_tree.heading("owner", text="Aksjonær")
    sh_tree.heading("change", text="Endring")
    sh_tree.heading("shares_base", text="Aksjer (base)")
    sh_tree.heading("shares_current", text="Aksjer (nå)")
    sh_tree.heading("delta", text="\u0394 aksjer")
    sh_tree.heading("pct_current", text="Eierandel (nå)")
    sh_tree.heading("has_trace", text="RF-1086")
    sh_tree.column("owner", width=240, stretch=True)
    sh_tree.column("change", width=100)
    sh_tree.column("shares_base", width=110, anchor="e")
    sh_tree.column("shares_current", width=110, anchor="e")
    sh_tree.column("delta", width=90, anchor="e")
    sh_tree.column("pct_current", width=110, anchor="e")
    sh_tree.column("has_trace", width=110, anchor="center")
    sh_ysb = ttk.Scrollbar(sh_frame, orient="vertical", command=sh_tree.yview)
    sh_tree.configure(yscrollcommand=sh_ysb.set)
    sh_tree.grid(row=1, column=0, sticky="nsew")
    sh_ysb.grid(row=1, column=1, sticky="ns")
    sh_tree.bind("<Double-1>", page._on_shareholder_change_open)
    sh_tree.bind("<Return>", page._on_shareholder_change_open)
    page._tree_shareholder_changes = sh_tree
    page._shareholder_change_rows_by_iid = {}

    pending_frame = ttk.LabelFrame(
        parent, text="Ventende registerendringer i eide selskaper", padding=4,
    )
    pending_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
    pending_frame.columnconfigure(0, weight=1)
    pending_frame.rowconfigure(2, weight=1)
    page._pending_frame = pending_frame

    bar = ttk.Frame(pending_frame)
    bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
    page._btn_accept_selected = ttk.Button(
        bar, text="Godta valgte", command=page._on_accept_selected_changes, state="disabled",
    )
    page._btn_accept_selected.pack(side="left")
    page._btn_accept_all = ttk.Button(
        bar, text="Godta alle", command=page._on_accept_all_changes, state="disabled",
    )
    page._btn_accept_all.pack(side="left", padx=(4, 0))

    page.var_changes_empty = tk.StringVar(value="")
    page._lbl_changes_empty = ttk.Label(
        pending_frame,
        textvariable=page.var_changes_empty,
        foreground="#98A2B3",
        wraplength=700,
        justify="left",
    )

    tree = ttk.Treeview(
        pending_frame,
        columns=("company", "orgnr", "change", "current", "candidate", "source"),
        show="headings",
        selectmode="extended",
    )
    tree.heading("company", text="Selskap")
    tree.heading("orgnr", text="Org.nr")
    tree.heading("change", text="Endring")
    tree.heading("current", text="Gjeldende")
    tree.heading("candidate", text="Nytt register")
    tree.heading("source", text="Kilde")
    tree.column("company", width=260, stretch=True)
    tree.column("orgnr", width=95)
    tree.column("change", width=110)
    tree.column("current", width=180, stretch=True)
    tree.column("candidate", width=180, stretch=True)
    tree.column("source", width=130)
    tree.grid(row=2, column=0, sticky="nsew")
    tree.bind("<<TreeviewSelect>>", page._on_changes_selection_changed)
    page._tree_changes = tree

    hist_frame = ttk.LabelFrame(parent, text="Importhistorikk", padding=4)
    hist_frame.grid(row=2, column=0, sticky="nsew", pady=(6, 0))
    hist_frame.columnconfigure(0, weight=1)
    hist_frame.rowconfigure(1, weight=1)

    page.var_history_empty = tk.StringVar(value="")
    page._lbl_history_empty = ttk.Label(
        hist_frame,
        textvariable=page.var_history_empty,
        foreground="#98A2B3",
        wraplength=700,
        justify="left",
    )

    hist_cols = ("register_year", "imported_at", "source_file", "shareholders", "status")
    hist_tree = ttk.Treeview(hist_frame, columns=hist_cols, show="headings", selectmode="browse")
    for cid, text, width, anchor in [
        ("register_year", "Registerår", 90, "center"),
        ("imported_at", "Importert", 150, "w"),
        ("source_file", "Kildefil", 340, "w"),
        ("shareholders", "Aksjonærer", 110, "e"),
        ("status", "Status", 120, "w"),
    ]:
        hist_tree.heading(cid, text=text)
        hist_tree.column(cid, width=width, anchor=anchor, stretch=(cid == "source_file"))

    hist_ysb = ttk.Scrollbar(hist_frame, orient="vertical", command=hist_tree.yview)
    hist_tree.configure(yscrollcommand=hist_ysb.set)
    hist_tree.grid(row=1, column=0, sticky="nsew")
    hist_ysb.grid(row=1, column=1, sticky="ns")

    hist_tree.bind("<Double-1>", page._on_history_open_detail)
    hist_tree.bind("<Return>", page._on_history_open_detail)

    page._tree_history = hist_tree
    page._history_rows_by_iid = {}


def on_changes_selection_changed(page, _event=None) -> None:
    try:
        sel = page._tree_changes.selection()
        page._btn_accept_selected.configure(state="normal" if sel else "disabled")
    except Exception:
        pass


def on_shareholder_change_open(page, _event=None) -> None:
    tree = getattr(page, "_tree_shareholder_changes", None)
    if tree is None:
        return
    sel = tree.selection()
    if not sel:
        return
    row = page._shareholder_change_rows_by_iid.get(sel[0]) or {}
    orgnr = _safe_text(row.get("shareholder_orgnr"))
    name = _safe_text(row.get("shareholder_name"))
    target_iid = None
    for iid, cmp_row in page._compare_rows_by_iid.items():
        if orgnr and _safe_text(cmp_row.get("shareholder_orgnr")) == orgnr:
            target_iid = iid
            break
        if not orgnr and name and _safe_text(cmp_row.get("shareholder_name")) == name:
            target_iid = iid
            break
    try:
        page._nb.select(page._frm_owners)
    except Exception:
        pass
    if target_iid is None:
        return
    try:
        page._tree_owners.selection_set((target_iid,))
        page._tree_owners.focus(target_iid)
        page._tree_owners.see(target_iid)
        page._on_compare_selected()
    except Exception:
        pass


def on_history_open_detail(page, _event=None) -> None:
    tree = getattr(page, "_tree_history", None)
    if tree is None:
        return
    sel = tree.selection()
    if not sel:
        return
    row = page._history_rows_by_iid.get(sel[0]) or {}
    import_id = _safe_text(row.get("import_id"))
    if not import_id:
        return
    page._show_persisted_import_detail(import_id)


def populate_compare_tree(page) -> None:
    tree = page._tree_owners
    page._compare_rows_by_iid = {}
    page._owners_rows_by_iid = {}
    tree.delete(*tree.get_children())

    ov = page._overview or {}
    compare_rows = ov.get("owners_compare") or []
    raw_base_year = _safe_text(ov.get("owners_base_year_used"))
    source_year = _safe_text(ov.get("owners_current_year_used"))
    view_year = _safe_text(ov.get("year")) or _safe_text(page._year) or source_year or "nå"
    has_import = page._has_current_import()
    has_base = bool(raw_base_year) and raw_base_year != source_year
    try:
        if has_base:
            tree.heading("shares_base", text=f"Aksjer {raw_base_year}")
        else:
            tree.heading("shares_base", text="Aksjer (ingen sammenligning)")
        if source_year and source_year != view_year:
            tree.heading("shares_current", text=f"Aksjer {view_year} (fra {source_year})")
            tree.heading("pct_current", text=f"Eierandel {view_year} (fra {source_year})")
        else:
            tree.heading("shares_current", text=f"Aksjer {view_year}")
            tree.heading("pct_current", text=f"Eierandel {view_year}")
    except Exception:
        pass

    try:
        if has_import and has_base:
            tree.configure(displaycolumns="#all")
        elif has_base:
            tree.configure(displaycolumns=(
                "owner", "orgnr", "kind",
                "shares_base", "shares_current", "shares_delta",
                "pct_current",
            ))
        elif has_import:
            tree.configure(displaycolumns=(
                "owner", "orgnr", "kind",
                "shares_current",
                "bought", "sold", "tx_value",
                "pct_current",
            ))
        else:
            tree.configure(displaycolumns=(
                "owner", "orgnr", "kind",
                "shares_current",
                "pct_current",
            ))
    except Exception:
        pass

    base_label = raw_base_year if has_base else None
    if not compare_rows:
        page.var_owners_caption.set(
            "Ingen aksjonærdata importert ennå — bruk «Importer RF-1086 (PDF)» for å fylle oversikten.",
        )
    else:
        if base_label:
            timeline = f"{base_label} → {view_year}"
        else:
            timeline = view_year
        suffix = " (RF-1086)" if has_import else ""
        source_note = (
            f" — videreført fra {source_year}"
            if source_year and source_year != view_year
            else ""
        )
        page.var_owners_caption.set(
            f"Aksjonærer i klienten — {timeline}{suffix}{source_note}"
        )

    for idx, row in enumerate(compare_rows, start=1):
        iid = f"compare-{idx}"
        page._compare_rows_by_iid[iid] = dict(row)
        change_type = _safe_text(row.get("change_type"))
        source = _safe_text(row.get("source"))
        tags: tuple[str, ...] = ()
        if change_type in {"new", "removed", "changed", "hidden"}:
            tags = (change_type,)
        elif source in {"manual", "manual_override"}:
            tags = (source,)
        shares_base = int(row.get("shares_base") or 0)
        shares_current = int(row.get("shares_current") or 0)
        delta = int(row.get("shares_delta") or 0)
        bought = int(row.get("shares_bought") or 0)
        sold = int(row.get("shares_sold") or 0)
        tx_val = float(row.get("transaction_value_total") or 0.0)
        tree.insert(
            "", "end", iid=iid,
            values=(
                _safe_text(row.get("shareholder_name")),
                _safe_text(row.get("shareholder_orgnr")),
                _safe_text(row.get("shareholder_kind")) or "unknown",
                _fmt_thousand(shares_base),
                _fmt_thousand(shares_current),
                _fmt_signed_thousand(delta),
                _fmt_thousand(bought) if bought else "",
                _fmt_thousand(sold) if sold else "",
                _fmt_currency(tx_val) if tx_val else "",
                _fmt_pct(row.get("ownership_pct_current")),
            ),
            tags=tags,
        )

    page._clear_compare_detail()


def _update_owner_buttons(page, row: dict[str, Any] | None) -> None:
    updater = getattr(page, "_update_manual_owner_action_state", None)
    if callable(updater):
        try:
            updater(row)
        except Exception:
            pass


def clear_compare_detail(page) -> None:
    page.var_compare_header.set("")
    page.var_detail_shares_base.set("–")
    page.var_detail_shares_current.set("–")
    page.var_detail_shares_delta.set("–")
    page.var_detail_pct_base.set("–")
    page.var_detail_pct_current.set("–")
    page.var_detail_change_type.set("–")
    page.var_compare_imported_at.set("–")
    page.var_compare_source_file.set("–")
    page.var_compare_source_year.set("–")
    has_import = page._has_current_import()
    accepted = (page._overview or {}).get("accepted_meta") or {}
    basis_kind = _safe_text(accepted.get("source_kind"))
    basis_label = {
        "carry_forward": "Videreført",
        "register_baseline": "Register",
        "accepted_update": "Godkjent",
    }.get(basis_kind, "Videreført")
    page.var_compare_data_basis.set(basis_label if not has_import else "RF-1086")
    page.var_compare_rf_status.set("importert" if has_import else "ikke importert")
    page.var_compare_tx_empty.set("")
    page.var_compare_no_import.set("")
    try:
        page._lbl_compare_tx_empty.grid_remove()
        page._lbl_compare_no_import.grid_remove()
        page._tree_compare_tx.delete(*page._tree_compare_tx.get_children())
        page._btn_compare_open_pdf.grid_remove()
        page._btn_compare_import_detail.grid_remove()
    except Exception:
        pass


def on_compare_selected(page, _event=None) -> None:
    sel = page._tree_owners.selection()
    if not sel:
        page._clear_compare_detail()
        _update_owner_buttons(page, None)
        return
    row = page._compare_rows_by_iid.get(sel[0])
    if not row:
        page._clear_compare_detail()
        _update_owner_buttons(page, None)
        return
    _update_owner_buttons(page, row)

    name = _safe_text(row.get("shareholder_name"))
    orgnr = _safe_text(row.get("shareholder_orgnr"))
    header = f"{name}" + (f"  ({orgnr})" if orgnr else "")
    page.var_compare_header.set(header)

    base_year = _safe_text(row.get("base_year")) or "base"
    cur_year = _safe_text(row.get("current_year")) or "nå"
    sb = int(row.get("shares_base") or 0)
    sc = int(row.get("shares_current") or 0)
    pb = float(row.get("ownership_pct_base") or 0.0)
    pc = float(row.get("ownership_pct_current") or 0.0)
    change = _compare_change_label(row.get("change_type"))
    page._lbl_detail_shares_base_title.configure(text=f"Aksjer {base_year}:")
    page._lbl_detail_shares_current_title.configure(text=f"Aksjer {cur_year}:")
    page._lbl_detail_pct_base_title.configure(text=f"Eierandel {base_year}:")
    page._lbl_detail_pct_current_title.configure(text=f"Eierandel {cur_year}:")
    page.var_detail_shares_base.set(_fmt_thousand(sb))
    page.var_detail_shares_current.set(_fmt_thousand(sc))
    page.var_detail_shares_delta.set(_fmt_signed_thousand(sc - sb))
    page.var_detail_pct_base.set(f"{_fmt_pct(pb)} %")
    page.var_detail_pct_current.set(f"{_fmt_pct(pc)} %")
    page.var_detail_change_type.set(change)

    key = ""
    if orgnr:
        key = f"org:{orgnr}"
    elif name:
        key = f"name:{name.casefold()}"

    trace: dict[str, Any] = {}
    try:
        from ar_store import get_shareholder_trace_detail
        trace = get_shareholder_trace_detail(page._client, page._year, key) or {}
    except Exception:
        trace = {}

    has_import = page._has_current_import()
    year_for_msg = _safe_text(page._year) or "valgt år"

    page._tree_compare_tx.delete(*page._tree_compare_tx.get_children())
    if not has_import:
        page.var_compare_no_import.set(
            f"RF-1086 for {year_for_msg} er ikke importert."
        )
        try:
            page._lbl_compare_no_import.grid(row=0, column=0, sticky="ew", pady=(0, 4))
            page._lbl_compare_tx_empty.grid_remove()
            page._tree_compare_tx.grid_remove()
        except Exception:
            pass
    else:
        page.var_compare_no_import.set("")
        try:
            page._lbl_compare_no_import.grid_remove()
            page._tree_compare_tx.grid(row=1, column=0, sticky="nsew")
        except Exception:
            pass
        tx_rows = trace.get("transactions") or []
        for tx in tx_rows:
            direction = _safe_text(tx.get("direction"))
            retning = "Tilgang" if direction == "tilgang" else "Avgang" if direction == "avgang" else direction
            page._tree_compare_tx.insert(
                "", "end",
                values=(
                    _safe_text(tx.get("date")),
                    retning,
                    _safe_text(tx.get("trans_type")),
                    _fmt_thousand(int(tx.get("shares") or 0)),
                    _fmt_currency(float(tx.get("amount") or 0.0)),
                ),
            )
        if tx_rows:
            page.var_compare_tx_empty.set("")
            try:
                page._lbl_compare_tx_empty.grid_remove()
            except Exception:
                pass
        else:
            page.var_compare_tx_empty.set("Ingen registrerte kjøp/salg.")
            try:
                page._lbl_compare_tx_empty.grid(row=0, column=0, sticky="w", pady=(0, 4))
            except Exception:
                pass

    current_import = trace.get("current_import") or {}
    accepted = (page._overview or {}).get("accepted_meta") or {}
    basis_kind = _safe_text(accepted.get("source_kind"))
    basis_label = {
        "carry_forward": "Videreført",
        "register_baseline": "Register",
        "accepted_update": "Godkjent",
    }.get(basis_kind, "Videreført")
    if has_import:
        page.var_compare_data_basis.set("RF-1086")
        page.var_compare_rf_status.set("importert")
        page.var_compare_source_year.set(
            _safe_text(current_import.get("register_year"))
            or _safe_text(current_import.get("target_year")) or "–"
        )
        page.var_compare_imported_at.set(
            _safe_text(current_import.get("imported_at_utc"))[:16] or "–"
        )
        page.var_compare_source_file.set(
            _safe_text(current_import.get("source_file")) or "–"
        )
    else:
        page.var_compare_data_basis.set(basis_label)
        page.var_compare_rf_status.set("ikke importert")
        page.var_compare_source_year.set("–")
        page.var_compare_imported_at.set("–")
        page.var_compare_source_file.set("–")

    stored = _safe_text(trace.get("stored_file_path"))
    page._current_compare_pdf = stored
    page._current_compare_import_id = _safe_text(current_import.get("import_id"))
    try:
        if has_import:
            pdf_state = "normal" if stored and Path(stored).exists() else "disabled"
            page._btn_compare_open_pdf.configure(state=pdf_state)
            page._btn_compare_open_pdf.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 2))
            detail_state = "normal" if page._current_compare_import_id else "disabled"
            page._btn_compare_import_detail.configure(state=detail_state)
            page._btn_compare_import_detail.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(2, 2))
        else:
            page._btn_compare_open_pdf.grid_remove()
            page._btn_compare_import_detail.grid_remove()
    except Exception:
        pass


def on_compare_open_pdf(page) -> None:
    page._open_pdf_path(getattr(page, "_current_compare_pdf", ""))


def on_compare_show_import_detail(page) -> None:
    import_id = getattr(page, "_current_compare_import_id", "")
    if not import_id:
        messagebox.showinfo("AR", "Ingen import knyttet til denne aksjonæren.")
        return
    page._show_persisted_import_detail(import_id)


def show_persisted_import_detail(page, import_id: str) -> None:
    try:
        from ar_store import _load_import_detail
    except Exception as exc:
        messagebox.showerror("AR", f"Kunne ikke laste importdetaljer:\n{exc}")
        return
    detail = _load_import_detail(import_id) or {}
    if not detail:
        messagebox.showinfo("AR", "Fant ingen lagrede importdetaljer.")
        return
    from page_ar_import_detail_dialog import _ImportDetailDialog
    _ImportDetailDialog(page, detail=detail).show()


def selected_change_keys(page) -> list[str]:
    keys: list[str] = []
    for iid in page._tree_changes.selection():
        row = page._change_rows_by_iid.get(iid)
        if row is None:
            continue
        key = _safe_text(row.get("change_key"))
        if key:
            keys.append(key)
    return keys


def _partition_selected_changes(page) -> tuple[list[str], list[str]]:
    """Return (owned_change_keys, owner_manual_ids) for the current selection."""
    owned_keys: list[str] = []
    owner_ids: list[str] = []
    for iid in page._tree_changes.selection():
        row = page._change_rows_by_iid.get(iid)
        if row is None:
            continue
        if _safe_text(row.get("kind")) == "owner":
            mid = _safe_text(row.get("manual_change_id"))
            if mid:
                owner_ids.append(mid)
        else:
            key = _safe_text(row.get("change_key"))
            if key:
                owned_keys.append(key)
    return owned_keys, owner_ids


def on_accept_selected_changes(page) -> None:
    if not page._client or not page._year:
        return
    owned_keys, owner_ids = _partition_selected_changes(page)
    if not owned_keys and not owner_ids:
        messagebox.showinfo("AR", "Velg minst én registerendring å godta.")
        return
    if owned_keys:
        accept_pending_ownership_changes(page._client, page._year, owned_keys)
    if owner_ids:
        accept_pending_owner_changes(page._client, page._year, owner_ids)
    page._refresh_current_overview()
    total = len(owned_keys) + len(owner_ids)
    page.var_status.set(f"Godkjente {total} registerendringer.")


def on_accept_all_changes(page) -> None:
    if not page._client or not page._year:
        return
    pending = page._overview.get("pending_changes") or []
    if not pending:
        messagebox.showinfo("AR", "Det finnes ingen ventende registerendringer.")
        return
    if not messagebox.askyesno("AR", f"Godta alle {len(pending)} registerendringer for {page._year}?"):
        return
    has_owner = any(_safe_text(r.get("kind")) == "owner" for r in pending)
    has_owned = any(_safe_text(r.get("kind")) != "owner" for r in pending)
    if has_owned:
        accept_pending_ownership_changes(page._client, page._year)
    if has_owner:
        accept_pending_owner_changes(page._client, page._year)
    page._refresh_current_overview()
    page.var_status.set(f"Godkjente alle registerendringer for {page._year}.")


def select_changes_tab_if_pending(page) -> None:
    pending = page._overview.get("pending_changes") or []
    if not pending:
        return
    try:
        page._nb.select(page._frm_changes)
    except Exception:
        return
