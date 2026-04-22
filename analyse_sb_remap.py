"""analyse_sb_remap.py — bindinger og remap for SB-tree.

Utskilt fra page_analyse_sb.py. Innholder:
- Høyreklikk og header-meny (_bind_sb_*)
- Remap av SB-konto mot regnskapslinje (remap_sb_account,
  _remap_multiple_sb_accounts)
- Drag-n-drop fra SB-tree til pivot-tree (_bind_sb_drag_drop,
  _execute_drag_remap, _check_rl_has_active_kontoer)

Kryss-seksjon-referanser (review-seksjonen + kontodetaljer) hentes lazily
via page_analyse_sb for å unngå sirkulære importer.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


# Kryss-seksjon-referanser (review + kontodetaljer) eksponeres som tynne
# proxy-funksjoner som slår opp live verdi fra page_analyse_sb ved hvert
# kall. Dette holder call-site-koden uendret (f.eks. i lambdas) og lar
# tester monkeypatche page_analyse_sb-symbolene og fortsatt se effekten
# her inne.
def _action_link_menu_label(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._action_link_menu_label(**kw)


def _add_attachments_to_kontoer(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._add_attachments_to_kontoer(**kw)


def _edit_comment(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._edit_comment(**kw)


def _open_action_link_dialog(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._open_action_link_dialog(**kw)


def _open_path(path: str) -> Any:
    import page_analyse_sb as _ps
    return _ps._open_path(path)


def _refresh_sb_after_review_change(page: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._refresh_sb_after_review_change(page)


def _resolve_regnr_by_konto(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._resolve_regnr_by_konto(**kw)


def _resolve_sb_columns(sb_df: pd.DataFrame) -> dict[str, str]:
    import page_analyse_sb as _ps
    return _ps._resolve_sb_columns(sb_df)


def _session_client_year() -> tuple[str, str]:
    import page_analyse_sb as _ps
    return _ps._session_client_year()


def _set_accounts_ok(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._set_accounts_ok(**kw)


def _show_attachments_dialog(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps._show_attachments_dialog(**kw)


def show_kontodetaljer_dialog(**kw: Any) -> Any:
    import page_analyse_sb as _ps
    return _ps.show_kontodetaljer_dialog(**kw)


# =====================================================================
# Binding: høyreklikk + drag-n-drop (bindes kun én gang)
# =====================================================================

def _bind_sb_once(*, page: Any, tree: Any) -> None:
    """Bind høyreklikk, dobbeltklikk og drag-n-drop på SB-tree — kalles kun én gang."""
    if getattr(tree, "_sb_events_bound", False):
        return
    tree._sb_events_bound = True  # type: ignore[attr-defined]

    _bind_sb_rightclick(page=page, tree=tree)
    _bind_sb_header_rightclick(page=page, tree=tree)
    _bind_sb_drag_drop(page=page, tree=tree)
    _bind_sb_header_sort(page=page, tree=tree)


# Numeriske kolonner som sorteres som tall (bruker SB_COLS-IDs).
_SB_NUMERIC_SORT_COLS = {
    "regnr",
    "IB", "Endring", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
}


def _bind_sb_header_sort(*, page: Any, tree: Any) -> None:
    """Bind venstreklikk på SB-kolonneoverskrift til sortering.

    Klikk veksler mellom stigende og synkende. Numeriske kolonner sorteres
    som tall (parser norsk format med mellomrom som tusen-skille og komma
    som desimal); øvrige kolonner sorteres alfabetisk.
    """
    state: dict[str, object] = {"col": None, "desc": False}

    def _parse_no_number(s: str) -> float:
        if s is None:
            return 0.0
        txt = str(s).strip().replace(" ", " ")
        if not txt:
            return 0.0
        # Strip prosent og non-numeric tegn (behold minus, komma, punktum, siffer)
        clean = "".join(ch for ch in txt if ch.isdigit() or ch in "-,.")
        # Norsk format: " " = tusen-skille (ikke i clean), "," = desimal
        clean = clean.replace(",", ".")
        try:
            return float(clean) if clean not in ("", "-", ".", "-.") else 0.0
        except ValueError:
            return 0.0

    def _on_header_click(col: str) -> None:
        try:
            children = list(tree.get_children(""))
        except Exception:
            return
        if not children:
            return
        desc = state["desc"] if state["col"] == col else False
        desc = not desc

        is_num = col in _SB_NUMERIC_SORT_COLS

        def _key(iid: str):
            try:
                v = tree.set(iid, col)
            except Exception:
                v = ""
            if is_num:
                num = _parse_no_number(v)
                # Tomme felt sist uansett retning
                empty = not str(v).strip()
                return (1 if empty else 0, -num if desc else num)
            txt = str(v or "").lower()
            return (1 if not txt else 0, txt)

        try:
            ordered = sorted(children, key=_key, reverse=False)
        except Exception:
            return

        if not is_num and desc:
            ordered = list(reversed(ordered))

        for i, iid in enumerate(ordered):
            try:
                tree.move(iid, "", i)
            except Exception:
                pass

        state["col"] = col
        state["desc"] = desc

    # Bind hver kolonneoverskrift til sin egen handler
    try:
        cols = list(tree["columns"])  # type: ignore[index]
    except Exception:
        cols = []
    for col in cols:
        try:
            tree.heading(col, command=lambda c=col: _on_header_click(c))
        except Exception:
            pass

    def _on_sb_header_release(event: Any) -> None:
        try:
            region = str(tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region in {"separator", "heading"}:
            try:
                import page_analyse_columns as _cols
                _cols.remember_sb_column_widths(page=page)
            except Exception:
                pass

    tree.bind("<ButtonRelease-1>", _on_sb_header_release, add=True)

    def _on_sb_dblclick(event: Any) -> None:
        """Dobbeltklikk på SB-konto → åpne Kontodetaljer."""
        iid = tree.identify_row(event.y)
        if not iid:
            return
        try:
            values = tree.item(iid, "values")
            konto = str(values[0]).strip() if values else ""
            kontonavn = str(values[1]).strip() if len(values) > 1 else ""
        except Exception:
            return
        if not konto or konto.startswith("\u03a3"):  # Skip sum-rader
            return
        show_kontodetaljer_dialog(page=page, konto=konto, kontonavn=kontonavn)

    tree.bind("<Double-1>", _on_sb_dblclick, add=True)


def _bind_sb_header_rightclick(*, page: Any, tree: Any) -> None:
    """Bind h\u00f8yreklikk p\u00e5 SB-header til kolonnemeny (vis/skjul)."""
    try:
        import tkinter as tk
    except Exception:
        return

    def _on_header_rightclick(event: Any) -> None:
        try:
            region = tree.identify_region(event.x, event.y)
        except Exception:
            region = ""
        if region not in ("heading", "separator"):
            return
        _show_sb_header_menu(page=page, tree=tree, event=event)

    tree.bind("<Button-3>", _on_header_rightclick, add=True)


def _show_sb_header_menu(*, page: Any, tree: Any, event: Any) -> None:
    """Vis kolonnemeny p\u00e5 SB-header med checkbuttons + Tilpass/Nullstill."""
    try:
        import tkinter as tk
    except Exception:
        return
    try:
        import page_analyse_columns as _cols
    except Exception:
        return

    default_order = list(SB_COLS)
    current_order = list(getattr(page, "_sb_cols_order", default_order))
    current_visible = list(getattr(page, "_sb_cols_visible", default_order))
    pinned = set(_cols.SB_PINNED_COLS)

    # Hent brukervennlige labels via felles vokabular slik at menyen
    # viser "UB 2025" / "Δ UB 25/24" istedenfor interne IDs.
    year = _cols._active_year()

    menu = tk.Menu(tree, tearoff=0)

    def _toggle(col: str) -> None:
        if col in pinned:
            return
        new_visible = list(current_visible)
        if col in new_visible:
            new_visible.remove(col)
        else:
            new_visible.append(col)
        _cols.apply_sb_column_config(
            page=page, order=current_order, visible=new_visible)

    for col in current_order:
        try:
            heading = _cols.analysis_heading(col, year=year)
        except Exception:
            heading = _SB_COL_HEADINGS.get(col, col)
        is_visible = col in current_visible
        is_pinned = col in pinned
        label = f"\u2713 {heading}" if is_visible else f"   {heading}"
        if is_pinned:
            menu.add_command(label=label + "  (l\u00e5st)", state="disabled")
        else:
            menu.add_command(label=label, command=lambda c=col: _toggle(c))

    menu.add_separator()
    menu.add_command(
        label="Tilpass kolonner\u2026",
        command=lambda: _cols.open_sb_column_chooser(page=page),
    )
    menu.add_command(
        label="Nullstill kolonner",
        command=lambda: _cols.reset_sb_columns_to_default(page=page),
    )

    try:
        menu.tk_popup(event.x_root, event.y_root)
    except Exception:
        pass


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
        # Skip header/separator — håndteres av _bind_sb_header_rightclick
        try:
            region = tree.identify_region(event.x, event.y)
        except Exception:
            region = ""
        if region in ("heading", "separator"):
            return
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
                label="Kontodetaljer\u2026",
                command=lambda: show_kontodetaljer_dialog(
                    page=page, konto=konto, kontonavn=kontonavn),
            )
            menu.add_separator()
            menu.add_command(
                label="Merk som OK",
                command=lambda: _set_accounts_ok(page=page, kontoer=[konto], ok=True),
            )
            menu.add_command(
                label="Fjern OK",
                command=lambda: _set_accounts_ok(page=page, kontoer=[konto], ok=False),
            )
            menu.add_separator()
            menu.add_command(
                label="Legg til vedlegg\u2026",
                command=lambda: _add_attachments_to_kontoer(page=page, kontoer=[konto]),
            )
            menu.add_command(
                label="Vis vedlegg\u2026",
                command=lambda: _show_attachments_dialog(page=page, konto=konto, kontonavn=kontonavn),
            )
            menu.add_separator()
            link_label = _action_link_menu_label(
                kind="account", entity_key=konto, base="Koble til handling"
            )
            menu.add_command(
                label=f"{link_label}\u2026",
                command=lambda: _open_action_link_dialog(
                    page=page, kind="account",
                    entity_key=konto, entity_label=f"{konto} {kontonavn}",
                ),
            )
            menu.add_separator()
            menu.add_command(
                label=f"Endre regnskapslinje for {konto}\u2026",
                command=lambda: remap_sb_account(page=page, konto=konto, kontonavn=kontonavn),
            )
            menu.add_command(
                label="Vis hovedbok\u2026",
                command=lambda: show_sb_account_transactions(page=page, konto=konto),
            )
            menu.add_command(
                label="Kommentar\u2026",
                command=lambda: _edit_comment(page=page, kind="accounts",
                                              key=konto, label=f"{konto} {kontonavn}"),
            )
        else:
            kontoer_only = [k for k, _ in selected]
            menu.add_command(
                label=f"Merk {len(selected)} valgte som OK",
                command=lambda: _set_accounts_ok(page=page, kontoer=kontoer_only, ok=True),
            )
            menu.add_command(
                label=f"Fjern OK på {len(selected)} valgte",
                command=lambda: _set_accounts_ok(page=page, kontoer=kontoer_only, ok=False),
            )
            menu.add_command(
                label=f"Legg til vedlegg på {len(selected)} kontoer\u2026",
                command=lambda: _add_attachments_to_kontoer(page=page, kontoer=kontoer_only),
            )
            menu.add_separator()
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
    mapping_issue = next(
        (
            issue
            for issue in (getattr(page, "_mapping_issues", []) or [])
            if str(getattr(issue, "konto", "") or "").strip() == str(konto or "").strip()
        ),
        None,
    )

    # Finn nåværende regnr/regnskapslinje via den kanoniske RL-servicen
    current_regnr = None
    current_rl_name = ""
    try:
        import regnskapslinje_mapping_service as _rl_svc

        context = _rl_svc.context_from_page(page)
        resolved = _rl_svc.resolve_accounts_to_rl([str(konto or "").strip()], context=context)
        if not resolved.empty:
            row = resolved.iloc[0]
            regnr_val = row.get("regnr")
            if pd.notna(regnr_val):
                current_regnr = int(regnr_val)
                current_rl_name = str(row.get("regnskapslinje", "") or "")
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
        suggested_regnr=getattr(mapping_issue, "suggested_regnr", None),
        suggested_regnskapslinje=str(getattr(mapping_issue, "suggested_regnskapslinje", "") or ""),
        suggestion_reason=str(getattr(mapping_issue, "suggestion_reason", "") or ""),
        suggestion_source=str(getattr(mapping_issue, "suggestion_source", "") or ""),
        confidence_bucket=str(getattr(mapping_issue, "confidence_bucket", "") or ""),
        sign_note=str(getattr(mapping_issue, "sign_note", "") or ""),
        regnskapslinjer=regnskapslinjer,
        on_saved=_on_saved,
        on_removed=_on_saved,
    )


def show_sb_account_transactions(*, page: Any, konto: str) -> None:
    """Bytt til transaksjonsvisning (Hovedbok) filtrert på en spesifikk konto."""
    try:
        page._var_tx_view_mode.set("Hovedbok")
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
    dlg.resizable(True, True)
    dlg.minsize(520, 520)

    # Kontoer-info
    konto_text = ", ".join(k for k, _n in kontoer[:5])
    if len(kontoer) > 5:
        konto_text += f" (+{len(kontoer) - 5} til)"
    ttk.Label(dlg, text=f"Kontoer: {konto_text}").pack(padx=12, pady=(10, 4), anchor="w")

    # Listbox med regnskapslinjer
    ttk.Label(dlg, text="Velg mål-regnskapslinje:").pack(padx=12, pady=(6, 2), anchor="w")

    lb_frame = ttk.Frame(dlg)
    lb_frame.pack(padx=12, pady=2, fill="both", expand=True)

    lb = tk.Listbox(lb_frame, width=60, height=28, exportselection=False)
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
                    has_kontoer = _check_rl_has_active_kontoer(
                        regnr=source_regnr,
                        sb_df=sb_df,
                        konto_src=konto_src,
                        page=page,
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
                                   page: Any) -> bool:
    """Sjekk om en regnskapslinje fremdeles har SB-kontoer med aktivitet.

    Bruker den kanoniske RL-servicen for konto -> regnr-oppslag, slik
    at samme klient-overrides og baseline-intervaller brukes som i RL-pivoten.
    """
    try:
        import regnskapslinje_mapping_service as _rl_svc

        context = _rl_svc.context_from_page(page)
        sb_konto = sb_df[konto_src].astype(str).str.strip()
        accounts = sb_konto.unique().tolist()
        resolved = _rl_svc.resolve_accounts_to_rl(accounts, context=context)
        if resolved.empty:
            return False
        target_kontoer = set(
            resolved.loc[resolved["regnr"] == int(regnr), "konto"].astype(str).tolist()
        )
        if not target_kontoer:
            return False
        matched = sb_df[sb_konto.isin(target_kontoer)]
        for c in matched.columns:
            if c.lower() in ("ib", "netto", "endring", "ub"):
                vals = pd.to_numeric(matched[c], errors="coerce").fillna(0).abs()
                if (vals > 0.005).any():
                    return True
        return False
    except Exception:
        return True  # Fallback: anta den har kontoer


