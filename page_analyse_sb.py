"""page_analyse_sb.py

Saldobalansevisning for Analyse-fanen.

Egen Treeview (_sb_tree) med egne kolonner, vist som alternativ til
transaksjonslisten (_tx_tree). Toggling skjer via show_sb_tree / show_tx_tree.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import formatting


# Egne kolonner for SB-visning (ingen gjenbruk av TX-kolonner)
SB_COLS = ("Konto", "Kontonavn", "IB", "Endring", "UB", "Antall")

_SB_COL_WIDTHS = {
    "Konto":     70,
    "Kontonavn": 220,
    "IB":        110,
    "Endring":   110,
    "UB":        110,
    "Antall":    70,
}


# =====================================================================
# Oppretting og toggling av SB-treeview
# =====================================================================

def create_sb_tree(parent_frame: Any) -> Any:
    """Opprett en SB-treeview i parent_frame, returnerer (frame, tree).

    Lager en egen Frame med tree + scrollbars, plassert i samme grid-celle
    som TX-treet. Skjult som standard.
    """
    try:
        from tkinter import ttk
        import tkinter as tk
    except Exception:
        return None

    frame = ttk.Frame(parent_frame)

    tree = ttk.Treeview(frame, columns=SB_COLS, show="headings", selectmode="extended")
    tree.grid(row=0, column=0, sticky="nsew")

    for col in SB_COLS:
        tree.heading(col, text=col)
        anchor = "e" if col in ("IB", "Endring", "UB", "Antall") else "w"
        stretch = col == "Kontonavn"
        tree.column(col, width=_SB_COL_WIDTHS.get(col, 100), anchor=anchor, stretch=stretch)

    try:
        tree.tag_configure("neg", foreground="red")
    except Exception:
        pass

    v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    h_scroll.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    # Lagre tree-referanse på frame for enkel tilgang
    frame._sb_tree = tree  # type: ignore[attr-defined]

    return frame


def show_sb_tree(*, page: Any) -> None:
    """Vis SB-treet og skjul TX-treet."""
    sb_frame = getattr(page, "_sb_frame", None)
    tx_frame = getattr(page, "_tx_frame", None)
    if sb_frame is None:
        return
    try:
        if tx_frame is not None:
            tx_frame.grid_remove()
        sb_frame.grid()
    except Exception:
        pass


def show_tx_tree(*, page: Any) -> None:
    """Vis TX-treet og skjul SB-treet."""
    sb_frame = getattr(page, "_sb_frame", None)
    tx_frame = getattr(page, "_tx_frame", None)
    try:
        if sb_frame is not None:
            sb_frame.grid_remove()
        if tx_frame is not None:
            tx_frame.grid()
    except Exception:
        pass


# =====================================================================
# SB-data refresh
# =====================================================================

def _clear_tree(tree: Any) -> None:
    if tree is None:
        return
    try:
        items = tree.get_children("")
    except Exception:
        items = ()
    for item in items:
        try:
            tree.delete(item)
        except Exception:
            continue


def _resolve_sb_columns(sb_df: pd.DataFrame) -> dict[str, str]:
    """Map logiske SB-feltnavn til faktiske kolonnenavn i DataFrame."""
    col_map: dict[str, str] = {}
    for c in sb_df.columns:
        cl = c.lower()
        if cl == "konto":
            col_map["konto"] = c
        elif cl == "kontonavn":
            col_map["kontonavn"] = c
        elif cl == "ib":
            col_map["ib"] = c
        elif cl in ("netto", "endring"):
            col_map["endring"] = c
        elif cl == "ub":
            col_map["ub"] = c
        elif cl == "antall":
            col_map["antall"] = c
    return col_map


def _get_selected_rl_name(*, page: Any) -> str:
    """Hent navnet på valgt regnskapslinje (for visning i summary-label)."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return ""
    try:
        selected = tree.selection()
        if not selected:
            return ""
        if len(selected) == 1:
            vals = tree.item(selected[0], "values")
            if vals and len(vals) > 1:
                nr = str(vals[0]).strip()
                name = str(vals[1]).strip()
                return f"{nr} {name}"
        return f"{len(selected)} regnskapslinjer"
    except Exception:
        return ""


def _get_selected_regnr(*, page: Any) -> list[int]:
    """Hent valgte regnskapslinje-nummer direkte fra pivot-tree.

    Skipper Σ-sumrader. Returnerer tom liste hvis ingenting er valgt
    (ingen fallback til alle rader).
    """
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []
    regnr_list: list[int] = []
    try:
        selected = tree.selection()
        if not selected:
            return []
        for item in selected:
            try:
                name_val = str(tree.set(item, "Kontonavn") or "")
                if name_val.startswith("\u03a3"):  # Σ sum-rad
                    continue
                regnr_list.append(int(tree.set(item, "Konto")))
            except (ValueError, TypeError):
                pass
    except Exception:
        pass
    return regnr_list


def _resolve_target_kontoer(*, page: Any, sb_df: pd.DataFrame,
                             konto_src: str) -> set[str]:
    """Finn SB-kontoer som tilhører valgte regnskapslinjer/kontoer.

    Bruker vektorisert pandas-logikk istedenfor triple-nested loops.
    Overrides erstatter (ikke supplerer) intervall-mapping.
    """
    agg_mode = ""
    try:
        agg_mode = str(page._var_aggregering.get()) if page._var_aggregering else ""
    except Exception:
        pass

    if agg_mode != "Regnskapslinje":
        selected_accounts = page._get_selected_accounts()
        return set(selected_accounts)

    intervals = getattr(page, "_rl_intervals", None)
    if intervals is None or not isinstance(intervals, pd.DataFrame) or intervals.empty:
        return set()

    selected_regnr = _get_selected_regnr(page=page)
    if not selected_regnr:
        return set()

    regnr_set = set(selected_regnr)

    # Last overrides
    overrides: dict[str, int] = {}
    try:
        import regnskap_client_overrides
        import session as _session
        client = getattr(_session, "client", None) or ""
        year = getattr(_session, "year", None) or ""
        if client:
            overrides = regnskap_client_overrides.load_account_overrides(
                client, year=str(year) if year else None)
    except Exception:
        pass

    # Konverter SB-kontoer til numerisk for vektorisert range-sjekk
    sb_konto_num = pd.to_numeric(sb_df[konto_src], errors="coerce")
    sb_konto_str = sb_df[konto_src].astype(str)

    # Finn intervaller for valgte regnr
    sel_intervals = intervals[intervals["regnr"].astype(int).isin(regnr_set)]

    # Vektorisert range-match: for hvert intervall, sjekk hvilke SB-kontoer som faller innenfor
    mask = pd.Series(False, index=sb_df.index)
    for _, irow in sel_intervals.iterrows():
        fra, til = int(irow["fra"]), int(irow["til"])
        mask |= (sb_konto_num >= fra) & (sb_konto_num <= til)

    result = set(sb_konto_str[mask])

    if overrides:
        # Fjern kontoer som er overridden BORT fra valgte regnr
        overridden_away = {k for k, rn in overrides.items() if rn not in regnr_set}
        result -= overridden_away

        # Legg til kontoer som er overridden INN til valgte regnr
        all_sb_set = set(sb_konto_str)
        overridden_in = {k for k, rn in overrides.items()
                         if rn in regnr_set and k in all_sb_set}
        result |= overridden_in

    return result


def refresh_sb_view(*, page: Any) -> None:
    """Fyll SB-treet med saldobalansekontoer for valgt(e) regnskapslinjer.

    Filtrerer bort kontoer der IB, Endring og UB alle er 0.
    """
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return

    _clear_tree(tree)

    # Hent SB-data
    sb_df = getattr(page, "_rl_sb_df", None)
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return

    # Tilleggsposteringer: juster SB hvis aktivert
    try:
        _ao_var = getattr(page, "_var_include_ao", None)
        if _ao_var is not None and bool(_ao_var.get()):
            import tilleggsposteringer
            import regnskap_client_overrides
            import session as _session
            _cl = getattr(_session, "client", None) or ""
            _yr = getattr(_session, "year", None) or ""
            if _cl and _yr:
                ao_entries = regnskap_client_overrides.load_supplementary_entries(_cl, _yr)
                if ao_entries:
                    sb_df = tilleggsposteringer.apply_to_sb(sb_df, ao_entries)
    except Exception:
        pass

    col_map = _resolve_sb_columns(sb_df)
    konto_src = col_map.get("konto")
    if not konto_src:
        return

    target_konto = _resolve_target_kontoer(
        page=page, sb_df=sb_df, konto_src=konto_src,
    )

    # Oppdater summary-label (inkl. valgt RL-navn)
    lbl = getattr(page, "_lbl_tx_summary", None)

    if not target_konto:
        if lbl is not None:
            try:
                lbl.configure(text="Velg en regnskapslinje for å se saldobalansekontoer")
            except Exception:
                pass
        _bind_sb_once(page=page, tree=tree)
        return

    matched = sb_df[sb_df[konto_src].astype(str).isin(target_konto)].copy()

    # Filtrer bort rader der IB, Endring og UB alle er 0
    num_keys = ["ib", "endring", "ub"]
    num_cols = [col_map[k] for k in num_keys if k in col_map]
    if num_cols:
        for c in num_cols:
            matched[c] = pd.to_numeric(matched[c], errors="coerce").fillna(0.0)
        has_activity = matched[num_cols].abs().sum(axis=1) > 0.005
        active = matched[has_activity]
    else:
        active = matched

    # Sorter etter konto-nummer
    try:
        active = active.sort_values(konto_src, key=lambda s: pd.to_numeric(s, errors="coerce"))
    except Exception:
        pass

    # Oppdater summary-label med RL-navn
    if lbl is not None:
        try:
            ub_src = col_map.get("ub")
            total_ub = 0.0
            if ub_src:
                total_ub = active[ub_src].sum()
            # Hent valgt RL-navn
            rl_name = _get_selected_rl_name(page=page)
            prefix = f"{rl_name}: " if rl_name else ""
            lbl.configure(
                text=f"{prefix}{len(active)} kontoer | Sum UB: {formatting.fmt_amount(total_ub)}"
            )
        except Exception:
            pass

    # Last kommentarer
    account_comments: dict[str, str] = {}
    try:
        import regnskap_client_overrides
        import session as _session
        client = getattr(_session, "client", None) or ""
        if client:
            all_comments = regnskap_client_overrides.load_comments(client)
            account_comments = all_comments.get("accounts", {})
    except Exception:
        pass

    # Sett opp tag for kommenterte rader
    try:
        tree.tag_configure("commented", foreground="#1565C0")
    except Exception:
        pass

    # Fyll treet — bruk .itertuples() for bedre ytelse enn .iterrows()
    konto_col = col_map.get("konto", "")
    navn_col = col_map.get("kontonavn", "")
    ib_col = col_map.get("ib", "")
    endr_col = col_map.get("endring", "")
    ub_col = col_map.get("ub", "")
    antall_col = col_map.get("antall", "")

    cols = list(active.columns)
    konto_idx = cols.index(konto_col) if konto_col in cols else -1
    navn_idx = cols.index(navn_col) if navn_col in cols else -1
    ib_idx = cols.index(ib_col) if ib_col in cols else -1
    endr_idx = cols.index(endr_col) if endr_col in cols else -1
    ub_idx = cols.index(ub_col) if ub_col in cols else -1
    antall_idx = cols.index(antall_col) if antall_col in cols else -1

    for tup in active.itertuples(index=False):
        try:
            konto = str(tup[konto_idx]) if konto_idx >= 0 else ""
            navn = str(tup[navn_idx] or "") if navn_idx >= 0 else ""
            ib_val = tup[ib_idx] if ib_idx >= 0 else 0.0
            endring_val = tup[endr_idx] if endr_idx >= 0 else 0.0
            ub_val = tup[ub_idx] if ub_idx >= 0 else 0.0
            antall_val = tup[antall_idx] if antall_idx >= 0 else 0

            comment = account_comments.get(konto, "")
            tags = ("commented",) if comment else ()
            display_name = f"\u270e {navn}  \u2014 {comment}" if comment else navn

            tree.insert("", "end", values=(
                konto,
                display_name,
                formatting.fmt_amount(ib_val),
                formatting.fmt_amount(endring_val),
                formatting.fmt_amount(ub_val),
                formatting.format_int_no(antall_val) if antall_val else "",
            ), tags=tags)
        except Exception:
            continue

    # Bind høyreklikk + drag-n-drop (én gang)
    _bind_sb_once(page=page, tree=tree)


# =====================================================================
# Binding: høyreklikk + drag-n-drop (bindes kun én gang)
# =====================================================================

def _bind_sb_once(*, page: Any, tree: Any) -> None:
    """Bind høyreklikk og drag-n-drop på SB-tree — kalles kun én gang."""
    if getattr(tree, "_sb_events_bound", False):
        return
    tree._sb_events_bound = True  # type: ignore[attr-defined]

    _bind_sb_rightclick(page=page, tree=tree)
    _bind_sb_drag_drop(page=page, tree=tree)


def _bind_sb_rightclick(*, page: Any, tree: Any) -> None:
    """Bind høyreklikkmeny for SB-kontoer (endre regnskapslinje).

    Bevarer multi-selection: hvis høyreklikk treffer et allerede-valgt
    item, beholdes hele seleksjonen. Ellers velges kun det nye itemet.
    """
    try:
        import tkinter as tk
    except Exception:
        return

    def _on_sb_rightclick(event: Any) -> None:
        item = tree.identify_row(event.y)
        if not item:
            return

        # Bevar multi-selection hvis høyreklikk treffer allerede-valgt
        current_sel = tree.selection()
        if item not in current_sel:
            tree.selection_set(item)
            current_sel = (item,)

        # Samle alle valgte kontoer
        selected: list[tuple[str, str]] = []
        for sel_item in current_sel:
            vals = tree.item(sel_item, "values")
            if vals:
                k = str(vals[0]).strip()
                n = str(vals[1]).strip() if len(vals) > 1 else ""
                if k:
                    selected.append((k, n))

        if not selected:
            return

        menu = tk.Menu(tree, tearoff=0)

        if len(selected) == 1:
            konto, kontonavn = selected[0]
            menu.add_command(
                label=f"Endre regnskapslinje for {konto}\u2026",
                command=lambda: remap_sb_account(page=page, konto=konto, kontonavn=kontonavn),
            )
            menu.add_command(
                label="Vis transaksjoner\u2026",
                command=lambda: show_sb_account_transactions(page=page, konto=konto),
            )
            menu.add_separator()
            menu.add_command(
                label="Kommentar\u2026",
                command=lambda: _edit_comment(page=page, kind="accounts",
                                              key=konto, label=f"{konto} {kontonavn}"),
            )
        else:
            menu.add_command(
                label=f"Flytt {len(selected)} kontoer til regnskapslinje\u2026",
                command=lambda: _remap_multiple_sb_accounts(page=page, kontoer=list(selected)),
            )

        try:
            menu.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass

    tree.bind("<Button-3>", _on_sb_rightclick)


def remap_sb_account(*, page: Any, konto: str, kontonavn: str) -> None:
    """Åpne remapping-dialog for en SB-konto."""
    try:
        from tkinter import messagebox
    except Exception:
        return

    try:
        import session as _session
        client = getattr(_session, "client", None) or ""
    except Exception:
        client = ""

    if not client:
        messagebox.showerror("Remap", "Ingen aktiv klient.", parent=page)
        return

    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    intervals = getattr(page, "_rl_intervals", None)

    # Finn nåværende regnr for kontoen
    current_regnr = None
    current_rl_name = ""
    if intervals is not None and isinstance(intervals, pd.DataFrame):
        try:
            knum = int(konto)
            for _, irow in intervals.iterrows():
                fra = int(irow["fra"])
                til = int(irow["til"])
                if fra <= knum <= til:
                    current_regnr = int(irow["regnr"])
                    break
        except Exception:
            pass

    # Sjekk override
    try:
        import regnskap_client_overrides
        year = getattr(_session, "year", None) or ""
        overrides = regnskap_client_overrides.load_account_overrides(
            client, year=str(year) if year else None)
        if konto in overrides:
            current_regnr = overrides[konto]
    except Exception:
        pass

    # Finn regnskapslinje-navn
    if current_regnr is not None and regnskapslinjer is not None:
        try:
            match = regnskapslinjer[regnskapslinjer["nr"] == current_regnr]
            if not match.empty:
                current_rl_name = str(match.iloc[0].get("regnskapslinje", ""))
        except Exception:
            pass

    from views_rl_account_drill import open_account_mapping_dialog

    def _on_saved() -> None:
        page._reload_rl_config()
        page._apply_filters_and_refresh()

    open_account_mapping_dialog(
        page,
        client=client,
        konto=konto,
        kontonavn=kontonavn,
        current_regnr=current_regnr,
        current_regnskapslinje=current_rl_name,
        regnskapslinjer=regnskapslinjer,
        on_saved=_on_saved,
        on_removed=_on_saved,
    )


def show_sb_account_transactions(*, page: Any, konto: str) -> None:
    """Bytt til transaksjonsvisning filtrert på en spesifikk konto."""
    try:
        page._var_tx_view_mode.set("Transaksjoner")
    except Exception:
        pass
    try:
        page._var_search.set(konto)
        page._apply_filters_and_refresh()
    except Exception:
        pass


def _remap_multiple_sb_accounts(*, page: Any,
                                 kontoer: list[tuple[str, str]]) -> None:
    """Åpne en dialog for å velge mål-RL og remappe flere kontoer."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return

    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    if regnskapslinjer is None or not isinstance(regnskapslinjer, pd.DataFrame):
        return

    # Bygg liste av regnskapslinjer (kun ikke-sumposter)
    try:
        from regnskap_mapping import normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
        rl_rows = regn.loc[~regn["sumpost"], ["regnr", "regnskapslinje"]].copy()
    except Exception:
        rl_rows = regnskapslinjer[["nr", "regnskapslinje"]].copy()
        rl_rows = rl_rows.rename(columns={"nr": "regnr"})

    choices: list[tuple[int, str]] = []
    for _, r in rl_rows.iterrows():
        try:
            choices.append((int(r["regnr"]), str(r["regnskapslinje"])))
        except Exception:
            pass
    if not choices:
        return

    # Hent kilde-regnr
    source_regnr = 0
    try:
        pivot_tree = getattr(page, "_pivot_tree", None)
        if pivot_tree:
            psel = pivot_tree.selection()
            if psel:
                pv = pivot_tree.item(psel[0], "values")
                if pv:
                    source_regnr = int(str(pv[0]).strip())
    except Exception:
        pass

    # Bygg dialog
    dlg = tk.Toplevel(page)
    dlg.title(f"Flytt {len(kontoer)} kontoer til regnskapslinje")
    dlg.transient(page)
    dlg.grab_set()
    dlg.resizable(False, False)

    # Kontoer-info
    konto_text = ", ".join(k for k, _n in kontoer[:5])
    if len(kontoer) > 5:
        konto_text += f" (+{len(kontoer) - 5} til)"
    ttk.Label(dlg, text=f"Kontoer: {konto_text}").pack(padx=12, pady=(10, 4), anchor="w")

    # Listbox med regnskapslinjer
    ttk.Label(dlg, text="Velg mål-regnskapslinje:").pack(padx=12, pady=(6, 2), anchor="w")

    lb_frame = ttk.Frame(dlg)
    lb_frame.pack(padx=12, pady=2, fill="both", expand=True)

    lb = tk.Listbox(lb_frame, width=50, height=15, exportselection=False)
    lb_scroll = ttk.Scrollbar(lb_frame, orient="vertical", command=lb.yview)
    lb.configure(yscrollcommand=lb_scroll.set)
    lb.pack(side="left", fill="both", expand=True)
    lb_scroll.pack(side="right", fill="y")

    for regnr, name in choices:
        lb.insert("end", f"{regnr}  {name}")

    def _do_remap() -> None:
        sel = lb.curselection()
        if not sel:
            return
        target_regnr = choices[sel[0]][0]
        dlg.destroy()
        _execute_drag_remap(
            page=page,
            kontoer=[k for k, _n in kontoer],
            target_regnr=target_regnr,
            source_regnr=source_regnr,
        )

    def _on_dblclick(_event: Any) -> None:
        _do_remap()

    lb.bind("<Double-1>", _on_dblclick)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(padx=12, pady=(6, 10), fill="x")
    ttk.Button(btn_frame, text="Flytt", command=_do_remap).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy).pack(side="right")

    # Senter dialogen
    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = page.winfo_rootx() + (page.winfo_width() - w) // 2
    y = page.winfo_rooty() + (page.winfo_height() - h) // 2
    dlg.geometry(f"+{x}+{y}")


# =====================================================================
# Drag-n-drop: SB-konto → Regnskapslinje (remap)
# =====================================================================
# Kommentarer
# =====================================================================

def _edit_comment(*, page: Any, kind: str, key: str, label: str) -> None:
    """Åpne en enkel dialog for å legge til/redigere en kommentar."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return

    try:
        import session as _session
        import regnskap_client_overrides
        client = getattr(_session, "client", None) or ""
    except Exception:
        return
    if not client:
        return

    comments = regnskap_client_overrides.load_comments(client)
    current = comments.get(kind, {}).get(str(key), "")

    dlg = tk.Toplevel(page)
    dlg.title("Kommentar")
    dlg.transient(page)
    dlg.grab_set()
    dlg.resizable(False, False)

    ttk.Label(dlg, text=label).pack(padx=12, pady=(10, 4), anchor="w")
    txt = tk.Text(dlg, width=50, height=4, wrap="word")
    txt.pack(padx=12, pady=4)
    txt.insert("1.0", current)
    txt.focus_set()

    def _save() -> None:
        new_text = txt.get("1.0", "end").strip()
        regnskap_client_overrides.save_comment(client, kind=kind, key=str(key), text=new_text)
        dlg.destroy()
        # Refresh SB view for å vise kommentaren
        try:
            page._refresh_pivot()
            page._refresh_transactions_view()
        except Exception:
            pass

    def _on_key(event: Any) -> str | None:
        if event.keysym == "Return" and not (event.state & 0x1):  # Enter uten Shift
            _save()
            return "break"
        return None

    txt.bind("<Key>", _on_key)

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(padx=12, pady=(4, 10), fill="x")
    ttk.Button(btn_frame, text="Lagre", command=_save).pack(side="right", padx=(4, 0))
    ttk.Button(btn_frame, text="Avbryt", command=dlg.destroy).pack(side="right")
    if current:
        ttk.Button(btn_frame, text="Fjern", command=lambda: (
            regnskap_client_overrides.save_comment(client, kind=kind, key=str(key), text=""),
            dlg.destroy(),
            page._refresh_pivot(),
            page._refresh_transactions_view(),
        )).pack(side="left")

    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = page.winfo_rootx() + (page.winfo_width() - w) // 2
    y = page.winfo_rooty() + (page.winfo_height() - h) // 2
    dlg.geometry(f"+{x}+{y}")


# =====================================================================

_DRAG_THRESHOLD_PX = 8  # piksler bevegelse før drag starter


def _bind_sb_drag_drop(*, page: Any, tree: Any) -> None:
    """Bind drag-n-drop fra SB-tree til pivot-tree for hurtig remapping.

    Bruker kan markere en eller flere SB-kontoer, dra dem over til en
    regnskapslinje i pivot-treet, og slippe for å remappe.

    Tilnærming:
    - Avstandsterskel (8px) istedenfor tidsforsinket start
    - Tooltip opprettes én gang ved drag-start, tekst oppdateres via configure()
    - Bindings legges til kun én gang (guard i _bind_sb_once)
    """
    pivot_tree = getattr(page, "_pivot_tree", None)
    if pivot_tree is None:
        return

    try:
        import tkinter as tk
    except Exception:
        return

    # Delt state mellom event-handlers
    drag: dict[str, Any] = {
        "pressing": False,      # Museknapp er nede
        "active": False,        # Drag er startet (passert terskel)
        "origin_x": 0,          # Trykk-posisjon
        "origin_y": 0,
        "kontoer": [],          # [(konto, kontonavn), ...]
        "tip_window": None,     # Toplevel tooltip
        "tip_label": None,      # Label inni tooltip
        "highlighted": None,    # Sist highlightet item i pivot
        "saved_sel": (),        # Pivot selection før drag
        "source_regnr": 0,      # Kilde-RL for remap
        "click_on_selected": False,  # Trykk på allerede-valgt item
        "pressed_item": "",     # Item som ble trykket på
    }

    # ------------------------------------------------------------------
    # Hjelpere
    # ------------------------------------------------------------------

    def _get_selected_kontoer() -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        try:
            for item in tree.selection():
                vals = tree.item(item, "values")
                if vals:
                    konto = str(vals[0]).strip()
                    navn = str(vals[1]).strip() if len(vals) > 1 else ""
                    if konto:
                        result.append((konto, navn))
        except Exception:
            pass
        return result

    def _is_rl_mode() -> bool:
        try:
            return str(page._var_aggregering.get()) == "Regnskapslinje"
        except Exception:
            return False

    def _make_tooltip_text(kontoer: list, rl_nr: str | None = None,
                           rl_name: str = "") -> str:
        if rl_nr:
            if len(kontoer) == 1:
                return f"{kontoer[0][0]} \u2794 {rl_nr} {rl_name}"
            return f"{len(kontoer)} kontoer \u2794 {rl_nr} {rl_name}"
        if len(kontoer) == 1:
            return f"\u2794 {kontoer[0][0]} {kontoer[0][1]}"
        return f"\u2794 {len(kontoer)} kontoer"

    def _create_tooltip(x_root: int, y_root: int, text: str) -> None:
        tip = tk.Toplevel(tree)
        tip.wm_overrideredirect(True)
        tip.wm_attributes("-topmost", True)
        lbl = tk.Label(
            tip, text=text,
            background="#FFFDE7", foreground="#333333",
            relief="solid", borderwidth=1,
            font=("Segoe UI", 9),
            padx=6, pady=3,
        )
        lbl.pack()
        tip.wm_geometry(f"+{x_root + 16}+{y_root + 8}")
        drag["tip_window"] = tip
        drag["tip_label"] = lbl

    def _destroy_tooltip() -> None:
        tip = drag.get("tip_window")
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
        drag["tip_window"] = None
        drag["tip_label"] = None

    def _pivot_item_at(event: Any) -> str | None:
        """Returnerer pivot-tree item-id under skjermkoordinatene, eller None."""
        try:
            px = pivot_tree.winfo_rootx()
            py = pivot_tree.winfo_rooty()
            pw = pivot_tree.winfo_width()
            ph = pivot_tree.winfo_height()
            rx = event.x_root - px
            ry = event.y_root - py
            if 0 <= rx <= pw and 0 <= ry <= ph:
                return pivot_tree.identify_row(ry) or None
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------
    # Start drag (kalles når terskel er passert)
    # ------------------------------------------------------------------

    def _start_drag(event: Any) -> None:
        kontoer = _get_selected_kontoer()
        if not kontoer:
            drag["pressing"] = False
            return

        drag["active"] = True
        drag["kontoer"] = kontoer
        drag["highlighted"] = None

        # Lagre nåværende pivot selection slik at vi kan gjenopprette
        try:
            drag["saved_sel"] = pivot_tree.selection()
        except Exception:
            drag["saved_sel"] = ()

        _create_tooltip(event.x_root, event.y_root,
                        _make_tooltip_text(kontoer))
        try:
            tree.configure(cursor="hand2")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_press(event: Any) -> None:
        if not _is_rl_mode():
            drag["click_on_selected"] = False
            return

        # Sjekk om brukeren klikker på et allerede-valgt item
        # (for multi-select drag uten å miste seleksjon)
        item = tree.identify_row(event.y)
        current_sel = tree.selection()
        drag["pressed_item"] = item or ""

        if item and item in current_sel and len(current_sel) > 1:
            # Klikket på allerede-valgt: bevar multi-selection
            drag["click_on_selected"] = True
            # Gjenopprett seleksjonen etter at default handler har endret den
            tree.after_idle(lambda: tree.selection_set(*current_sel))
        else:
            drag["click_on_selected"] = False

        drag["pressing"] = True
        drag["active"] = False
        drag["origin_x"] = event.x
        drag["origin_y"] = event.y

        # Lagre kilde-regnr fra pivot (nåværende visning)
        try:
            pivot_sel = pivot_tree.selection()
            if pivot_sel:
                pv = pivot_tree.item(pivot_sel[0], "values")
                if pv:
                    drag["source_regnr"] = int(str(pv[0]).strip())
        except Exception:
            drag["source_regnr"] = 0

    def _on_motion(event: Any) -> None:
        if not drag["pressing"]:
            return

        # Sjekk terskel før drag-start
        if not drag["active"]:
            dx = abs(event.x - drag["origin_x"])
            dy = abs(event.y - drag["origin_y"])
            if dx < _DRAG_THRESHOLD_PX and dy < _DRAG_THRESHOLD_PX:
                return
            _start_drag(event)
            if not drag["active"]:
                return

        # Flytt tooltip
        tip = drag["tip_window"]
        if tip is not None:
            try:
                tip.wm_geometry(f"+{event.x_root + 16}+{event.y_root + 8}")
            except Exception:
                pass

        # Highlight mål-RL i pivot-tree
        item = _pivot_item_at(event)
        if item != drag["highlighted"]:
            drag["highlighted"] = item
            if item:
                try:
                    pivot_tree.selection_set(item)
                    pivot_tree.focus(item)
                except Exception:
                    pass
                # Oppdater tooltip-tekst
                try:
                    rl_vals = pivot_tree.item(item, "values")
                    if rl_vals:
                        txt = _make_tooltip_text(
                            drag["kontoer"],
                            str(rl_vals[0]).strip(),
                            str(rl_vals[1]).strip() if len(rl_vals) > 1 else "",
                        )
                        lbl = drag["tip_label"]
                        if lbl is not None:
                            lbl.configure(text=txt)
                except Exception:
                    pass
            else:
                # Utenfor pivot → gjenopprett
                try:
                    pivot_tree.selection_remove(pivot_tree.selection())
                except Exception:
                    pass
                lbl = drag["tip_label"]
                if lbl is not None:
                    try:
                        lbl.configure(text=_make_tooltip_text(drag["kontoer"]))
                    except Exception:
                        pass

    def _on_release(event: Any) -> None:
        was_active = drag["active"]
        drag["pressing"] = False
        drag["active"] = False

        if not was_active:
            # Vanlig klikk (ingen drag): hvis det var klikk på allerede-valgt
            # item, velg kun det itemet nå (standard click-to-deselect)
            if drag["click_on_selected"] and drag["pressed_item"]:
                try:
                    tree.selection_set(drag["pressed_item"])
                except Exception:
                    pass
            drag["click_on_selected"] = False
            return

        drag["click_on_selected"] = False
        _destroy_tooltip()
        try:
            tree.configure(cursor="")
        except Exception:
            pass

        kontoer = drag["kontoer"]
        source_regnr = drag.get("source_regnr", 0)
        drag["kontoer"] = []
        drag["highlighted"] = None

        if not kontoer:
            return

        # Finn mål-RL
        item = _pivot_item_at(event)
        if not item:
            # Sluppet utenfor → gjenopprett pivot selection
            try:
                saved = drag.get("saved_sel", ())
                if saved:
                    pivot_tree.selection_set(*saved)
            except Exception:
                pass
            return

        try:
            rl_vals = pivot_tree.item(item, "values")
            if not rl_vals:
                return
            target_regnr = int(str(rl_vals[0]).strip())
        except Exception:
            return

        _execute_drag_remap(
            page=page,
            kontoer=[k for k, _n in kontoer],
            target_regnr=target_regnr,
            source_regnr=source_regnr,
        )

    # Bind events — alle med add=True for å bevare normal oppførsel
    tree.bind("<ButtonPress-1>", _on_press, add=True)
    tree.bind("<B1-Motion>", _on_motion, add=True)
    tree.bind("<ButtonRelease-1>", _on_release, add=True)


def _execute_drag_remap(*, page: Any, kontoer: list[str],
                        target_regnr: int, source_regnr: int = 0) -> None:
    """Remap en liste kontoer til en ny regnskapslinje.

    Etter remap velges kilde-RL i pivot automatisk slik at SB-visningen
    oppdateres. Hvis kilde-RL ikke lenger har kontoer, velges mål-RL.
    """
    try:
        import session as _session
        import regnskap_client_overrides

        client = getattr(_session, "client", None) or ""
        year = getattr(_session, "year", None) or ""
        if not client:
            return

        overrides = regnskap_client_overrides.load_account_overrides(
            client, year=str(year) if year else None)
        for konto in kontoer:
            overrides[konto] = target_regnr
        regnskap_client_overrides.save_account_overrides(
            client, overrides, year=str(year) if year else None)

        # Oppdater RL-config og pivot
        page._reload_rl_config()
        page._apply_filters_and_refresh()

        # Re-velg kilde-RL i pivot (så SB-visningen oppdateres)
        stay_regnr = source_regnr or target_regnr
        if source_regnr:
            # Sjekk om kilde-RL fremdeles har kontoer med aktivitet
            sb_df = getattr(page, "_rl_sb_df", None)
            if sb_df is not None and isinstance(sb_df, pd.DataFrame) and not sb_df.empty:
                col_map = _resolve_sb_columns(sb_df)
                konto_src = col_map.get("konto")
                if konto_src:
                    intervals = getattr(page, "_rl_intervals", None)
                    if intervals is not None and isinstance(intervals, pd.DataFrame):
                        has_kontoer = _check_rl_has_active_kontoer(
                            regnr=source_regnr, sb_df=sb_df,
                            konto_src=konto_src, intervals=intervals,
                        )
                        if not has_kontoer:
                            stay_regnr = target_regnr

        # Velg regnr i pivot-tree og trigger SB-refresh
        page._restore_rl_pivot_selection([stay_regnr])
        page._refresh_transactions_view()

        # Vis statusmelding
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl is not None:
            try:
                if len(kontoer) == 1:
                    msg = f"Konto {kontoer[0]} flyttet til RL {target_regnr}"
                else:
                    msg = f"{len(kontoer)} kontoer flyttet til RL {target_regnr}"
                lbl.configure(text=msg)
            except Exception:
                pass
    except Exception as exc:
        import logging
        logging.getLogger("app").warning("Drag remap failed: %s", exc)


def _check_rl_has_active_kontoer(*, regnr: int, sb_df: pd.DataFrame,
                                   konto_src: str,
                                   intervals: pd.DataFrame) -> bool:
    """Sjekk om en regnskapslinje fremdeles har SB-kontoer med aktivitet."""
    try:
        sb_nums = pd.to_numeric(sb_df[konto_src], errors="coerce")
        sel = intervals[intervals["regnr"].astype(int) == regnr]
        mask = pd.Series(False, index=sb_df.index)
        for _, irow in sel.iterrows():
            fra, til = int(irow["fra"]), int(irow["til"])
            mask |= (sb_nums >= fra) & (sb_nums <= til)

        if not mask.any():
            return False

        # Sjekk at minst én konto har non-zero balanse
        matched = sb_df[mask]
        for c in matched.columns:
            if c.lower() in ("ib", "netto", "endring", "ub"):
                vals = pd.to_numeric(matched[c], errors="coerce").fillna(0).abs()
                if (vals > 0.005).any():
                    return True
        return False
    except Exception:
        return True  # Fallback: anta den har kontoer
