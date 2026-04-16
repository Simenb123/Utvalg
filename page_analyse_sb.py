"""page_analyse_sb.py

Saldobalansevisning for Analyse-fanen.

Egen Treeview (_sb_tree) med egne kolonner, vist som alternativ til
transaksjonslisten (_tx_tree). Toggling skjer via show_sb_tree / show_tx_tree.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import formatting


# Egne kolonner for SB-visning (ingen gjenbruk av TX-kolonner).
# "Endring_fjor" (UB - UB_fjor) og "Endring_pct" er beregnede kolonner som
# matcher samme labels som i venstre pivot ("Endring" og "Endring %"). Den
# opprinnelige "Endring"-kolonnen er fortsatt periode-bevegelsen (UB - IB)
# og vises som "Bevegelse i år" via den felles label-mapperen.
SB_COLS = (
    "Konto", "Kontonavn", "OK", "Vedlegg", "Gruppe",
    "IB", "Endring", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)

# Kanonisk standardvisning — matcher venstre pivot:
# Konto | Kontonavn | UB <år> | UB <år-1> | Endring | Endring % | Antall
SB_DEFAULT_VISIBLE = (
    "Konto", "Kontonavn", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)

# Overskrifter hentes nå fra analysis_heading (page_analyse_columns). Kartet
# beholdes tomt av bakoverkomp — configure_sb_tree_columns bruker mapperen.
_SB_COL_HEADINGS: dict[str, str] = {}

_SB_COL_WIDTHS = {
    "Konto":        70,
    "Kontonavn":    220,
    "OK":           40,
    "Vedlegg":      60,
    "Gruppe":       150,
    "IB":           110,
    "Endring":      110,
    "UB":           110,
    "UB_fjor":      110,
    "Endring_fjor": 110,
    "Endring_pct":  90,
    "Antall":       70,
}

_SB_NUMERIC_COLS = (
    "IB", "Endring", "UB", "UB_fjor", "Endring_fjor", "Endring_pct", "Antall",
)
_SB_CENTER_COLS = ("OK", "Vedlegg")


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

    try:
        import page_analyse_columns as _cols
        year = _cols._active_year()
        _heading_fn = lambda c: _cols.analysis_heading(c, year=year)
    except Exception:
        _heading_fn = lambda c: _SB_COL_HEADINGS.get(c, c)

    for col in SB_COLS:
        tree.heading(col, text=_heading_fn(col))
        if col in _SB_NUMERIC_COLS:
            anchor = "e"
        elif col in _SB_CENTER_COLS:
            anchor = "center"
        else:
            anchor = "w"
        stretch = col == "Kontonavn"
        tree.column(col, width=_SB_COL_WIDTHS.get(col, 100), anchor=anchor, stretch=stretch)

    try:
        tree.tag_configure("gruppe", foreground="#1A56A0")
    except Exception:
        pass

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


def _hide_all_views(*, page: Any, except_frame: Any = None) -> None:
    """Skjul alle visningsrammer bortsett fra except_frame."""
    for attr in ("_tx_frame", "_sb_frame", "_nk_frame", "_mp_frame", "_mp_acct_frame"):
        f = getattr(page, attr, None)
        if f is not None and f is not except_frame:
            try:
                f.grid_remove()
            except Exception:
                pass


def show_sb_tree(*, page: Any) -> None:
    """Vis SB-treet og skjul andre visninger."""
    sb_frame = getattr(page, "_sb_frame", None)
    if sb_frame is None:
        return
    _hide_all_views(page=page, except_frame=sb_frame)
    try:
        sb_frame.grid()
    except Exception:
        pass
    try:
        import page_analyse_columns as _cols
        _cols.configure_sb_tree_columns(page=page)
    except Exception:
        pass


def show_tx_tree(*, page: Any) -> None:
    """Vis TX-treet og skjul andre visninger."""
    tx_frame = getattr(page, "_tx_frame", None)
    _hide_all_views(page=page, except_frame=tx_frame)
    try:
        if tx_frame is not None:
            tx_frame.grid()
    except Exception:
        pass


def show_nk_view(*, page: Any) -> None:
    """Vis nøkkeltall-rammen og skjul andre visninger."""
    nk_frame = getattr(page, "_nk_frame", None)
    if nk_frame is None:
        return
    _hide_all_views(page=page, except_frame=nk_frame)
    try:
        nk_frame.grid()
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


def _capture_sb_selection(tree: Any) -> tuple[list[str], str]:
    selected_accounts: list[str] = []
    focused_account = ""

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    for item in selected:
        try:
            values = list(tree.item(item, "values") or [])
        except Exception:
            values = []
        konto = str(values[0]).strip() if values else ""
        if konto:
            selected_accounts.append(konto)

    try:
        focus_item = tree.focus()
    except Exception:
        focus_item = ""

    if focus_item:
        try:
            values = list(tree.item(focus_item, "values") or [])
        except Exception:
            values = []
        focused_account = str(values[0]).strip() if values else ""

    return selected_accounts, focused_account


def _restore_sb_selection(tree: Any, *, selected_accounts: list[str], focused_account: str) -> None:
    wanted = {str(v or "").strip() for v in selected_accounts if str(v or "").strip()}
    focus_wanted = str(focused_account or "").strip()
    if not wanted and not focus_wanted:
        return

    items_to_select: list[str] = []
    focus_item = ""

    try:
        items = tree.get_children("")
    except Exception:
        items = ()

    for item in items:
        try:
            values = list(tree.item(item, "values") or [])
        except Exception:
            values = []
        konto = str(values[0]).strip() if values else ""
        if not konto:
            continue
        if konto in wanted:
            items_to_select.append(item)
        if focus_wanted and konto == focus_wanted and not focus_item:
            focus_item = item

    if items_to_select:
        try:
            tree.selection_set(items_to_select)
        except Exception:
            pass
        if not focus_item:
            focus_item = items_to_select[0]

    if focus_item:
        try:
            tree.focus(focus_item)
        except Exception:
            pass
        try:
            tree.see(focus_item)
        except Exception:
            pass


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

    selected_regnr = _get_selected_regnr(page=page)
    if not selected_regnr:
        return set()
    regnr_set = {int(r) for r in selected_regnr}

    import regnskapslinje_mapping_service as _rl_svc

    context = _rl_svc.context_from_page(page)
    if context.is_empty and not context.account_overrides:
        return set()

    sb_konto_str = sb_df[konto_src].astype(str).str.strip()
    accounts = sb_konto_str.unique().tolist()
    resolved = _rl_svc.resolve_accounts_to_rl(accounts, context=context)
    if resolved.empty:
        return set()
    return set(
        resolved.loc[resolved["regnr"].isin(regnr_set), "konto"].astype(str).tolist()
    )


def refresh_sb_view(*, page: Any) -> None:
    """Fyll SB-treet med saldobalansekontoer for valgt(e) regnskapslinjer.

    Filtrerer bort kontoer der IB, Endring og UB alle er 0.
    """
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return

    selected_accounts, focused_account = _capture_sb_selection(tree)

    _clear_tree(tree)

    # Hent SB-data
    sb_df = getattr(page, "_rl_sb_df", None)
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return

    try:
        sb_df = page._get_effective_sb_df()
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
                lbl.configure(text="Velg en regnskapslinje for å se saldobalanse")
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

    # Bygg UB-i-fjor-map per konto fra _rl_sb_prev_df
    prev_map: dict[str, float] = {}
    try:
        sb_prev_df = getattr(page, "_rl_sb_prev_df", None)
        if isinstance(sb_prev_df, pd.DataFrame) and not sb_prev_df.empty:
            prev_cols = _resolve_sb_columns(sb_prev_df)
            prev_konto = prev_cols.get("konto")
            prev_ub = prev_cols.get("ub")
            if prev_konto and prev_ub:
                wp = sb_prev_df[[prev_konto, prev_ub]].copy()
                wp[prev_konto] = wp[prev_konto].astype(str)
                wp[prev_ub] = pd.to_numeric(wp[prev_ub], errors="coerce")
                wp = wp.dropna(subset=[prev_ub])
                # Ved duplikater: ta siste verdi
                prev_map = dict(zip(wp[prev_konto].tolist(), wp[prev_ub].astype(float).tolist()))
    except Exception:
        prev_map = {}

    # Koble UB-fjor til aktive rader per konto
    ub_fjor_by_konto: dict[str, float] = {}
    if prev_map:
        for konto in active[konto_src].astype(str).tolist():
            if konto in prev_map:
                ub_fjor_by_konto[konto] = prev_map[konto]
    has_prev = bool(ub_fjor_by_konto)

    # Bruk sentral kolonnekonfigurasjon (displaycolumns + dynamisk UB_fjor)
    try:
        import page_analyse_columns as _cols
        _cols.configure_sb_tree_columns(page=page)
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
            text = (
                f"{prefix}{len(active)} kontoer | "
                f"Sum UB: {formatting.fmt_amount(total_ub)}"
            )
            if has_prev:
                total_ub_prev = sum(ub_fjor_by_konto.values())
                text += f" | Sum UB i fjor: {formatting.fmt_amount(total_ub_prev)}"
            lbl.configure(text=text)
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

    # Last kontogjennomgang (OK + vedlegg) per år
    account_review: dict[str, dict] = {}
    try:
        import regnskap_client_overrides as _rco
        import session as _session  # type: ignore[import]
        _client = getattr(_session, "client", None) or ""
        _year = getattr(_session, "year", None) or ""
        if _client and _year:
            account_review = _rco.load_account_review(_client, str(_year))
    except Exception:
        account_review = {}

    # Last konto-klassifisering (gruppe per konto)
    gruppe_mapping: dict[str, str] = {}
    try:
        import konto_klassifisering as _kk
        import session as _session  # type: ignore[import]
        _client = getattr(_session, "client", None) or ""
        if _client:
            gruppe_mapping = _kk.load(_client)
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

    # Sjekk desimaltoggle
    use_dec = True
    try:
        _vd = getattr(page, "_var_decimals", None)
        if _vd is not None:
            use_dec = bool(_vd.get())
    except Exception:
        pass

    def _fmt(v: float) -> str:
        if not use_dec:
            return formatting.fmt_amount(round(v))
        return formatting.fmt_amount(v)

    for tup in active.itertuples(index=False):
        try:
            konto = str(tup[konto_idx]) if konto_idx >= 0 else ""
            navn = str(tup[navn_idx] or "") if navn_idx >= 0 else ""
            ib_val = tup[ib_idx] if ib_idx >= 0 else 0.0
            endring_val = tup[endr_idx] if endr_idx >= 0 else 0.0
            ub_val = tup[ub_idx] if ub_idx >= 0 else 0.0
            antall_val = tup[antall_idx] if antall_idx >= 0 else 0

            comment = account_comments.get(konto, "")
            gruppe = gruppe_mapping.get(konto, "")
            tags: tuple
            if comment and gruppe:
                tags = ("commented", "gruppe")
            elif comment:
                tags = ("commented",)
            elif gruppe:
                tags = ("gruppe",)
            else:
                tags = ()
            # Kommentar signaliseres via 'commented'-tag (farge), ikke via
            # \u00e5 lime inn tekst i Kontonavn.
            display_name = navn

            ub_fjor_raw = ub_fjor_by_konto.get(konto)
            ub_fjor_cell = _fmt(ub_fjor_raw) if ub_fjor_raw is not None else ""

            # År-over-år: Endring_fjor = UB - UB_fjor, Endring_pct = delta / |UB_fjor|
            if ub_fjor_raw is not None:
                try:
                    ub_num = float(ub_val or 0.0)
                    uf_num = float(ub_fjor_raw)
                except (TypeError, ValueError):
                    ub_num = 0.0
                    uf_num = 0.0
                delta = ub_num - uf_num
                endring_fjor_cell = _fmt(delta)
                if abs(uf_num) > 1e-9:
                    pct = delta / abs(uf_num) * 100.0
                    endring_pct_cell = f"{pct:+.1f} %".replace(".", ",")
                else:
                    endring_pct_cell = ""
            else:
                endring_fjor_cell = ""
                endring_pct_cell = ""

            review_entry = account_review.get(konto, {})
            ok_cell = "OK" if review_entry.get("ok") else ""
            n_atts = len(review_entry.get("attachments") or [])
            vedlegg_cell = str(n_atts) if n_atts > 0 else ""

            tree.insert("", "end", values=(
                konto,
                display_name,
                ok_cell,
                vedlegg_cell,
                gruppe,
                _fmt(ib_val),
                _fmt(endring_val),
                _fmt(ub_val),
                ub_fjor_cell,
                endring_fjor_cell,
                endring_pct_cell,
                formatting.format_int_no(antall_val) if antall_val else "",
            ), tags=tags)
        except Exception:
            continue

    # Bind høyreklikk + drag-n-drop (én gang)
    _bind_sb_once(page=page, tree=tree)
    _restore_sb_selection(
        tree,
        selected_accounts=selected_accounts,
        focused_account=focused_account,
    )


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
# Kontogjennomgang: OK-markering + vedlegg
# =====================================================================

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
        import regnskap_client_overrides as _rco
        _rco.set_accounts_ok(client, year, kontoer, ok)
    except Exception:
        return
    _refresh_sb_after_review_change(page)


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
        import regnskap_client_overrides as _rco
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
            import regnskap_client_overrides as _rco
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
            import regnskap_client_overrides as _rco
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
            import regnskap_client_overrides as _rco
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
        import regnskap_client_overrides
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


# =====================================================================
# Kontodetaljer — primær flate for oppfølging av én konto
# =====================================================================

def _parse_norwegian_number(text: str | float | int | None) -> float | None:
    """Tolk en tallstreng i norsk format (tusenskilletegn + komma)."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        try:
            if text != text:  # NaN
                return None
            return float(text)
        except Exception:
            return None
    s = str(text).strip()
    if not s or s == "—":
        return None
    neg = False
    if s.startswith("(") and s.endswith(")"):
        neg = True
        s = s[1:-1].strip()
    s = s.replace("\xa0", "").replace(" ", "")
    s = s.replace("−", "-")  # unicode minus
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    else:
        pass
    try:
        val = float(s)
    except Exception:
        return None
    return -val if neg else val


def _fmt_nok(value: float | None) -> str:
    if value is None:
        return "—"
    try:
        text = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    except Exception:
        return str(value)
    return text


def _resolve_raw_kontonavn(*, page: Any, konto: str) -> str:
    """Finn rått kontonavn fra `_rl_sb_df` — aldri det pyntede displaynavnet.

    Brukes av dialoger og eksport slik at kommentar/ikon fra SB-listens
    visningstekst (se `display_name` i SB-oppbyggingen) ikke lekker inn
    i formell dokumentasjon.
    """
    try:
        sb_df = getattr(page, "_rl_sb_df", None)
        if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
            return ""
        cols = _resolve_sb_columns(sb_df)
        kc, nc = cols.get("konto"), cols.get("kontonavn")
        if not kc or not nc:
            return ""
        m = sb_df[sb_df[kc].astype(str) == str(konto)]
        if m.empty:
            return ""
        return str(m.iloc[0].get(nc, "") or "").strip()
    except Exception:
        return ""


def _collect_konto_details(*, page: Any, konto: str) -> dict[str, str]:
    """Hent ut infosammendrag for en konto fra SB-treets rad + oppslag.

    Returnerer et dict med strenger slik de vises i GUI-en (allerede formatert).
    `kontonavn` er alltid rått navn fra datasettet — ikke pyntet display.
    """
    details: dict[str, str] = {
        "konto": str(konto), "kontonavn": "", "gruppe": "",
        "ib": "", "endring": "", "ub": "", "ub_fjor": "", "antall": "",
    }

    tree = getattr(page, "_sb_tree", None)
    if tree is not None:
        try:
            for iid in tree.get_children(""):
                vals = tree.item(iid, "values")
                if not vals:
                    continue
                if str(vals[0]).strip() != str(konto).strip():
                    continue
                # Rekkefølge: Konto, Kontonavn(display), OK, Vedlegg, Gruppe, IB, Endring, UB, UB_fjor, Antall
                # Merk: vals[1] er pyntet displaytekst — kontonavn hentes rått fra SB-df under.
                details["gruppe"]    = str(vals[4]) if len(vals) > 4 else ""
                details["ib"]        = str(vals[5]) if len(vals) > 5 else ""
                details["endring"]   = str(vals[6]) if len(vals) > 6 else ""
                details["ub"]        = str(vals[7]) if len(vals) > 7 else ""
                details["ub_fjor"]   = str(vals[8]) if len(vals) > 8 else ""
                details["antall"]    = str(vals[9]) if len(vals) > 9 else ""
                break
        except Exception:
            pass

    details["kontonavn"] = _resolve_raw_kontonavn(page=page, konto=konto)

    # Regnskapslinje (regnr + navn)
    try:
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[str(konto)])
        info = rbk.get(str(konto))
        if info:
            details["regnr"] = str(int(info[0]))
            details["regnskapslinje"] = str(info[1])
    except Exception:
        pass
    details.setdefault("regnr", "")
    details.setdefault("regnskapslinje", "")

    return details


def show_kontodetaljer_dialog(*, page: Any, konto: str, kontonavn: str = "") -> None:
    """Åpne samlet Kontodetaljer-dialog (primær flate for én konto).

    Kombinerer konto-info, OK-markering, kommentar og vedlegg i ett
    resizable vindu. Bygger på eksisterende lagringsmodeller — ingen
    ny datamodell introduseres.
    """
    try:
        import tkinter as tk
        from tkinter import ttk, messagebox
    except Exception:
        return

    client, year = _session_client_year()
    if not client or not year:
        return

    import regnskap_client_overrides as _rco
    from pathlib import Path as _Path

    konto = str(konto).strip()
    if not konto:
        return

    details = _collect_konto_details(page=page, konto=konto)
    # Alltid rått kontonavn — ikke stol på displaytekst fra treeview
    kontonavn = details.get("kontonavn", "") or kontonavn

    dlg = tk.Toplevel(page)
    dlg.title(f"Kontodetaljer — {konto} {kontonavn}".strip())
    dlg.resizable(True, True)
    dlg.minsize(900, 560)

    # ---------- Infosammendrag (rad 1) ----------
    info_frame = ttk.LabelFrame(dlg, text="Konto")
    info_frame.pack(padx=12, pady=(12, 4), fill="x")

    rl_label = f"{details.get('regnr', '')} {details.get('regnskapslinje', '')}".strip() or "—"
    info_rows = [
        ("Konto", f"{konto}  {kontonavn}"),
        ("Regnskapslinje", rl_label),
        ("Gruppe", details.get("gruppe") or "—"),
        ("IB", details.get("ib") or "—"),
        ("Endring", details.get("endring") or "—"),
        ("UB", details.get("ub") or "—"),
        ("UB i fjor", details.get("ub_fjor") or "—"),
        ("Antall", details.get("antall") or "—"),
    ]
    for i, (lbl, val) in enumerate(info_rows):
        r, c = i // 4, (i % 4) * 2
        ttk.Label(info_frame, text=f"{lbl}:", foreground="#666").grid(
            row=r, column=c, sticky="w", padx=(8, 4), pady=2)
        ttk.Label(info_frame, text=val).grid(
            row=r, column=c + 1, sticky="w", padx=(0, 12), pady=2)
    for c in range(8):
        info_frame.columnconfigure(c, weight=1 if c % 2 == 1 else 0)

    # OK-status + sekundær handlingsstripe
    ok_frame = ttk.Frame(dlg)
    ok_frame.pack(padx=12, pady=(0, 4), fill="x")
    ok_var = tk.StringVar()

    def _refresh_ok_label() -> None:
        review = _rco.load_account_review(client, year)
        is_ok = bool(review.get(konto, {}).get("ok"))
        ok_var.set("OK ✓" if is_ok else "Ikke markert OK")
        ok_btn.configure(text=("Fjern OK" if is_ok else "Merk som OK"))

    ttk.Label(ok_frame, text="Status:", foreground="#666").pack(side="left", padx=(8, 4))
    ttk.Label(ok_frame, textvariable=ok_var, font=("TkDefaultFont", 10, "bold")
              ).pack(side="left")

    def _toggle_ok() -> None:
        review = _rco.load_account_review(client, year)
        is_ok = bool(review.get(konto, {}).get("ok"))
        _rco.set_accounts_ok(client, year, [konto], not is_ok)
        _refresh_ok_label()
        _refresh_sb_after_review_change(page)

    ok_btn = ttk.Button(ok_frame, text="Merk som OK", command=_toggle_ok)
    ok_btn.pack(side="right", padx=(0, 8))

    def _do_export_workpaper() -> None:
        """Eksporter revisjonsunderlag: mappe med PDF + primær kildefil."""
        try:
            import account_workpaper_pdf as _awp
            import client_store as _cs
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Kunne ikke laste eksport-modul:\n{exc}", parent=dlg,
            )
            return
        review = {}
        try:
            review = _rco.load_account_review(client, year).get(konto, {}) or {}
        except Exception:
            pass
        payload = _awp.AccountWorkpaperData(
            client=client,
            year=str(year),
            konto=konto,
            kontonavn=kontonavn,
            regnr=str(details.get("regnr", "") or ""),
            regnskapslinje=str(details.get("regnskapslinje", "") or ""),
            ib=str(details.get("ib", "") or ""),
            endring=str(details.get("endring", "") or ""),
            ub=str(details.get("ub", "") or ""),
            ub_fjor=str(details.get("ub_fjor", "") or ""),
            antall=str(details.get("antall", "") or ""),
            ok=bool(review.get("ok")),
            comment=_rco.load_comments(client).get("accounts", {}).get(konto, "") or "",
            attachments=_load_atts(),
            ub_evidence=_load_evidence(),
        )
        try:
            dest_dir = _cs.exports_dir(client, year=str(year))
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Kunne ikke finne eksportmappe:\n{exc}", parent=dlg,
            )
            return
        try:
            result = _awp.export_account_workpaper_package(
                data=payload, dest_dir=dest_dir, year=str(year),
            )
        except Exception as exc:
            messagebox.showerror(
                "Eksport",
                f"Eksport feilet:\n{exc}", parent=dlg,
            )
            return
        if result.source_included:
            msg = (
                f"Revisjonsunderlag lagret:\n{result.folder}\n\n"
                f"- {result.pdf_path.name}\n"
                f"- {result.source_path.name}\n\n"
                "Åpne mappen nå?"
            )
        else:
            msg = (
                f"Revisjonsunderlag lagret:\n{result.folder}\n\n"
                f"- {result.pdf_path.name}\n"
                "(Kildefil var ikke tilgjengelig og ble ikke kopiert.)\n\n"
                "Åpne mappen nå?"
            )
        if messagebox.askyesno("Eksport", msg, parent=dlg):
            _open_path(str(result.folder))

    ttk.Button(
        ok_frame, text="Eksporter revisjonsunderlag…",
        command=_do_export_workpaper,
    ).pack(side="right", padx=(0, 6))

    # ---------- Delt visning: samlet venstreside ↔ preview (høyre) ----------
    try:
        from document_control_viewer import (
            DocumentPreviewFrame,
            preview_target_from_ub_evidence,
        )
    except Exception:
        DocumentPreviewFrame = None  # type: ignore[assignment]
        preview_target_from_ub_evidence = None  # type: ignore[assignment]

    paned = ttk.Panedwindow(dlg, orient="horizontal")
    paned.pack(padx=12, pady=(4, 6), fill="both", expand=True)

    # Venstre: vertikal PanedWindow med Kommentar (øverst), Vedlegg, UB-kontroll
    left_paned = ttk.Panedwindow(paned, orient="vertical")
    paned.add(left_paned, weight=1)

    # -- Preview-panel (høyre) --
    right_frame = ttk.Frame(paned)
    paned.add(right_frame, weight=1)

    preview: Any = None
    if DocumentPreviewFrame is not None:
        try:
            preview = DocumentPreviewFrame(right_frame)
            preview.pack(fill="both", expand=True)
        except Exception:
            preview = None
    if preview is None:
        ttk.Label(
            right_frame,
            text="Forhåndsvisning er ikke tilgjengelig i dette miljøet.",
            foreground="#888",
        ).pack(padx=8, pady=8)

    # ---------- Kommentar (øverst) ----------
    c_frame = ttk.LabelFrame(left_paned, text="Kommentar")
    left_paned.add(c_frame, weight=2)

    current_comment = _rco.load_comments(client).get("accounts", {}).get(konto, "")
    c_inner = ttk.Frame(c_frame)
    c_inner.pack(padx=8, pady=(8, 4), fill="both", expand=True)
    c_txt = tk.Text(c_inner, wrap="word", padx=6, pady=6, undo=True, height=6)
    c_scroll = ttk.Scrollbar(c_inner, orient="vertical", command=c_txt.yview)
    c_txt.configure(yscrollcommand=c_scroll.set)
    c_txt.pack(side="left", fill="both", expand=True)
    c_scroll.pack(side="right", fill="y")
    c_txt.insert("1.0", current_comment)

    c_btn_row = ttk.Frame(c_frame)
    c_btn_row.pack(padx=8, pady=(0, 8), fill="x")

    def _save_comment(_event: Any = None) -> str:
        text = c_txt.get("1.0", "end").strip()
        try:
            _rco.save_comment(client, kind="accounts", key=konto, text=text)
        except Exception as exc:
            messagebox.showerror("Kommentar",
                                 f"Kunne ikke lagre kommentar:\n{exc}", parent=dlg)
            return "break"
        try:
            refresh_views = getattr(page, "_refresh_analysis_views_after_adjustment_change", None)
            if callable(refresh_views):
                refresh_views()
        except Exception:
            pass
        return "break"

    ttk.Button(c_btn_row, text="Lagre kommentar", command=_save_comment).pack(side="right")

    # ---------- Vedlegg (midten) ----------
    v_frame = ttk.LabelFrame(left_paned, text="Vedlegg")
    left_paned.add(v_frame, weight=1)

    v_tree_frame = ttk.Frame(v_frame)
    v_tree_frame.pack(padx=8, pady=(8, 4), fill="both", expand=True)

    v_cols = ("label", "path", "storage", "added_at", "status")
    v_tree = ttk.Treeview(v_tree_frame, columns=v_cols, show="headings",
                          height=6, selectmode="browse")
    v_tree.heading("label", text="Navn")
    v_tree.heading("path", text="Sti")
    v_tree.heading("storage", text="Lagring")
    v_tree.heading("added_at", text="Lagt til")
    v_tree.heading("status", text="Status")
    v_tree.column("label", width=160, anchor="w")
    v_tree.column("path", width=240, anchor="w")
    v_tree.column("storage", width=100, anchor="center")
    v_tree.column("added_at", width=120, anchor="w")
    v_tree.column("status", width=70, anchor="center")
    v_scroll_att = ttk.Scrollbar(v_tree_frame, orient="vertical", command=v_tree.yview)
    v_tree.configure(yscrollcommand=v_scroll_att.set)
    v_tree.pack(side="left", fill="both", expand=True)
    v_scroll_att.pack(side="right", fill="y")

    empty_lbl = ttk.Label(v_frame, text="Ingen vedlegg — bruk 'Legg til vedlegg…' nederst.",
                          foreground="#888")

    def _storage_label(row: dict) -> str:
        s = str(row.get("storage", "external") or "external").lower()
        return "Utvalg-lager" if s == "managed" else "Ekstern"

    def _load_atts() -> list[dict]:
        try:
            return _rco.list_account_attachments(client, year, konto)
        except Exception:
            return []

    def _fill_atts() -> None:
        for iid in v_tree.get_children(""):
            v_tree.delete(iid)
        rows = _load_atts()
        for row in rows:
            p = row.get("path", "")
            exists = False
            try:
                exists = _Path(p).exists()
            except Exception:
                pass
            v_tree.insert("", "end", values=(
                row.get("label", "") or _Path(p).name,
                p, _storage_label(row),
                row.get("added_at", ""),
                "" if exists else "Mangler",
            ))
        if not rows:
            empty_lbl.pack(pady=(0, 8))
        else:
            empty_lbl.pack_forget()
        _refresh_ub_tab()

    def _selected_att_path() -> str:
        sel = v_tree.selection()
        if not sel:
            return ""
        vals = v_tree.item(sel[0], "values")
        return str(vals[1]) if vals and len(vals) > 1 else ""

    def _selected_att_row() -> dict | None:
        p = _selected_att_path()
        if not p:
            return None
        for row in _load_atts():
            if str(row.get("path", "")) == p:
                return row
        return None

    def _on_att_select(_event: Any = None) -> None:
        p = _selected_att_path()
        if not p or preview is None:
            return
        try:
            if not _Path(p).exists():
                return
            preview.load_file(p)
        except Exception:
            return
        # Forsøk automatisk UB-forslag som del av normalflyten.
        # Planlagt oppførsel: ikke overskriv manuelt bevis, ingen feildialog
        # ved manglende treff – bare rolig hint i UB-kontroll.
        _try_auto_on_attachment_select(p)

    def _do_att_open() -> None:
        p = _selected_att_path()
        if not p:
            return
        if not _Path(p).exists():
            messagebox.showinfo("Vedlegg", f"Filen finnes ikke lenger:\n{p}", parent=dlg)
            return
        _open_path(p)

    def _do_att_open_folder() -> None:
        p = _selected_att_path()
        if not p:
            return
        folder = str(_Path(p).parent)
        if not _Path(folder).exists():
            messagebox.showinfo("Vedlegg", f"Mappen finnes ikke:\n{folder}", parent=dlg)
            return
        _open_path(folder)

    def _do_att_add() -> None:
        try:
            from tkinter import filedialog
        except Exception:
            return
        paths = filedialog.askopenfilenames(
            parent=dlg, title=f"Velg vedlegg for {konto} {kontonavn}".strip())
        if not paths:
            return
        rbk = _resolve_regnr_by_konto(page=page, kontoer=[konto])
        try:
            _rco.add_account_attachments(client, year, [konto], list(paths),
                                         regnr_by_konto=rbk)
        except Exception as exc:
            messagebox.showerror("Vedlegg", f"Kunne ikke lagre vedlegg:\n{exc}", parent=dlg)
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    def _do_att_remove() -> None:
        p = _selected_att_path()
        if not p:
            return
        if not messagebox.askyesno("Fjern kobling",
                                   f"Fjerne koblingen til:\n{p}?", parent=dlg):
            return
        try:
            _rco.remove_account_attachment(client, year, konto, p)
        except Exception:
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    def _do_att_migrate() -> None:
        row = _selected_att_row()
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
            _rco.migrate_attachment_to_managed(client, year, konto, src,
                                               regnr=rl_info[0],
                                               regnskapslinje=rl_info[1])
        except Exception as exc:
            messagebox.showerror("Utvalg-lager",
                                 f"Migrering feilet:\n{exc}", parent=dlg)
            return
        _fill_atts()
        _refresh_sb_after_review_change(page)

    v_tree.bind("<<TreeviewSelect>>", _on_att_select)
    v_tree.bind("<Double-1>", lambda _e: _do_att_open())
    v_tree.bind("<Return>", lambda _e: _do_att_open())
    v_tree.bind("<Delete>", lambda _e: _do_att_remove())

    v_btn_row = ttk.Frame(v_frame)
    v_btn_row.pack(padx=8, pady=(0, 8), fill="x")
    ttk.Button(v_btn_row, text="Legg til vedlegg…", command=_do_att_add).pack(side="left")
    ttk.Button(v_btn_row, text="Åpne", command=_do_att_open).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Åpne mappe", command=_do_att_open_folder
               ).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Kopier inn i Utvalg-lager",
               command=_do_att_migrate).pack(side="left", padx=(6, 0))
    ttk.Button(v_btn_row, text="Fjern kobling", command=_do_att_remove
               ).pack(side="left", padx=(6, 0))

    # ---------- UB-kontroll (nederst) ----------
    ub_frame = ttk.LabelFrame(left_paned, text="UB-kontroll")
    left_paned.add(ub_frame, weight=2)

    expected_ub_value = _parse_norwegian_number(details.get("ub", ""))

    ub_info = ttk.Frame(ub_frame)
    ub_info.pack(padx=8, pady=(8, 4), fill="x")
    ub_info.columnconfigure(1, weight=1)

    var_expected = tk.StringVar(value=details.get("ub", "") or "—")
    var_evidence_label = tk.StringVar(value="—")
    var_evidence_page = tk.StringVar(value="—")
    var_raw = tk.StringVar(value="")
    var_doc_value = tk.StringVar(value="—")
    var_avvik = tk.StringVar(value="—")
    var_status = tk.StringVar(value="Ikke kontrollert")
    var_source = tk.StringVar(value="—")
    var_note = tk.StringVar(value="")

    def _row(r: int, label: str, var: tk.StringVar, *, bold: bool = False) -> None:
        ttk.Label(ub_info, text=label, foreground="#666").grid(
            row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        lbl = ttk.Label(ub_info, textvariable=var)
        if bold:
            try:
                lbl.configure(font=("TkDefaultFont", 10, "bold"))
            except Exception:
                pass
        lbl.grid(row=r, column=1, sticky="w", pady=2)

    _row(0, "Forventet UB (fra analyse):", var_expected, bold=True)
    _row(1, "Valgt bevis:", var_evidence_label)
    _row(2, "Side:", var_evidence_page)
    _row(3, "Kilde:", var_source)
    _row(4, "Avvik (dok − analyse):", var_avvik, bold=True)
    _row(5, "Status:", var_status, bold=True)

    raw_row = ttk.Frame(ub_frame)
    raw_row.pack(padx=8, pady=(4, 4), fill="x")
    ttk.Label(raw_row, text="Verdi fra dokument (rå):", foreground="#666"
              ).pack(side="left", padx=(0, 6))
    raw_entry = ttk.Entry(raw_row, textvariable=var_raw, width=24)
    raw_entry.pack(side="left")
    ttk.Label(raw_row, text="→ tolket:", foreground="#666"
              ).pack(side="left", padx=(8, 4))
    ttk.Label(raw_row, textvariable=var_doc_value).pack(side="left")

    note_row = ttk.Frame(ub_frame)
    note_row.pack(padx=8, pady=(4, 4), fill="x")
    ttk.Label(note_row, text="Notat:", foreground="#666"
              ).pack(side="left", padx=(0, 6))
    ttk.Entry(note_row, textvariable=var_note).pack(side="left", fill="x", expand=True)

    # Rolig fallback-hint: vises kun når auto-søk feilet uten å lagre noe
    var_hint = tk.StringVar(value="")
    hint_lbl = ttk.Label(ub_frame, textvariable=var_hint, foreground="#888")
    hint_lbl.pack(padx=8, pady=(0, 4), fill="x")

    ub_btn_row = ttk.Frame(ub_frame)
    ub_btn_row.pack(padx=8, pady=(4, 8), fill="x")

    def _set_hint(text: str = "") -> None:
        var_hint.set(text)

    def _load_evidence() -> dict | None:
        try:
            return _rco.load_ub_evidence(client, year, konto)
        except Exception:
            return None

    def _compute_status(
        doc_value: float | None, expected: float | None
    ) -> tuple[str, float | None]:
        if doc_value is None or expected is None:
            return "unchecked", None
        avvik = round(float(doc_value) - float(expected), 2)
        status = "match" if abs(avvik) < 0.5 else "mismatch"
        return status, avvik

    def _status_text(status: str) -> str:
        return {
            "match": "OK — verdi stemmer",
            "mismatch": "Avvik",
            "unchecked": "Ikke kontrollert",
        }.get(status, "Ikke kontrollert")

    def _source_text(source: str) -> str:
        return {
            "manual": "Manuell markering",
            "auto": "Automatisk forslag",
        }.get(str(source or "").strip().lower(), "—")

    def _refresh_ub_tab() -> None:
        ev = _load_evidence()
        if ev is None:
            var_evidence_label.set("—")
            var_evidence_page.set("—")
            var_raw.set("")
            var_doc_value.set("—")
            var_avvik.set("—")
            var_status.set("Ikke kontrollert")
            var_source.set("—")
            var_note.set("")
            return
        # Bevis finnes: nullstill eventuell auto-fallback-hint
        _set_hint("")
        var_evidence_label.set(str(ev.get("attachment_label") or _Path(str(ev.get("attachment_path", ""))).name))
        var_evidence_page.set(str(ev.get("page") or "—"))
        var_raw.set(str(ev.get("raw_value") or ""))
        nv = ev.get("normalized_value")
        if nv is None:
            parsed = _parse_norwegian_number(str(ev.get("raw_value") or ""))
        else:
            try:
                parsed = float(nv)
            except Exception:
                parsed = None
        var_doc_value.set(_fmt_nok(parsed) if parsed is not None else "—")
        status, avvik = _compute_status(parsed, expected_ub_value)
        var_avvik.set(_fmt_nok(avvik) if avvik is not None else "—")
        var_status.set(_status_text(status))
        var_source.set(_source_text(str(ev.get("source", ""))))
        var_note.set(str(ev.get("note") or ""))

    def _on_raw_changed(*_args: Any) -> None:
        parsed = _parse_norwegian_number(var_raw.get())
        var_doc_value.set(_fmt_nok(parsed) if parsed is not None else "—")
        status, avvik = _compute_status(parsed, expected_ub_value)
        var_avvik.set(_fmt_nok(avvik) if avvik is not None else "—")
        var_status.set(_status_text(status))

    var_raw.trace_add("write", _on_raw_changed)

    def _focus_ub_evidence() -> None:
        ev = _load_evidence()
        if not ev or preview is None:
            messagebox.showinfo(
                "UB-bevis",
                "Ingen lagret UB-bevis for denne kontoen enda.",
                parent=dlg,
            )
            return
        path = str(ev.get("attachment_path") or "")
        try:
            if path and _Path(path).exists():
                preview.load_file(path)
                if preview_target_from_ub_evidence is not None:
                    target = preview_target_from_ub_evidence(ev, label="UB")
                    if target is not None:
                        preview.set_highlight(target)
        except Exception:
            pass

    def _attempt_auto_find(path: str) -> dict | None:
        """Forsøk automatisk UB-deteksjon i PDF. Returnerer match-dict eller None.

        Returnerer kun noe når kildedokumentet er en PDF som appen allerede
        kan forhåndsvise. Bilder og andre filtyper støttes ikke i v1.
        """
        if preview is None or expected_ub_value is None:
            return None
        try:
            from document_control_viewer import preview_kind_for_path
            if preview_kind_for_path(path) != "pdf":
                return None
        except Exception:
            return None
        try:
            preview.load_file(path)
        except Exception:
            return None
        try:
            return preview.find_ub_match(expected_ub_value)
        except Exception:
            return None

    def _try_auto_on_attachment_select(path: str) -> None:
        """Kjør stille auto-UB-forslag når vedlegg velges.

        Regler:
        - Bare PDF. For bilder/uspesifisert: rolig hint, ingen dialog.
        - Overskriv aldri manuelt bevis på samme vedlegg.
        - Ved entydig treff: lagre evidence (source="auto") og highlight.
        - Ved tvetydig/manglende: rolig hint i UB-kontroll, ingen dialog.
        """
        if expected_ub_value is None or preview is None:
            return
        try:
            from document_control_viewer import preview_kind_for_path
            kind = preview_kind_for_path(path)
        except Exception:
            kind = "unsupported"
        if kind != "pdf":
            _set_hint("Automatisk UB-søk støttes foreløpig bare for PDF.")
            return

        prior = _load_evidence() or {}
        prior_source = str(prior.get("source") or "").lower()
        prior_path = str(prior.get("attachment_path") or "")
        same_attachment = prior_path == path
        if prior_source == "manual" and prior.get("bbox") and same_attachment:
            # Manuelt bevis på samme vedlegg — ikke rør, bare highlight.
            _focus_ub_evidence()
            return

        match = _attempt_auto_find(path)
        if match is None:
            _set_hint("Fant ikke sikkert treff — bruk 'Marker manuelt'.")
            return

        row = _selected_att_row() or {}
        normalized = match.get("normalized_value")
        status, _avvik = _compute_status(
            float(normalized) if normalized is not None else None,
            expected_ub_value,
        )
        new_ev = {
            "attachment_path": path,
            "attachment_label": row.get("label") or _Path(path).name,
            "page": int(match.get("page") or 1),
            "bbox": list(match.get("bbox") or []),
            "raw_value": str(match.get("raw_value") or ""),
            "normalized_value": normalized,
            "status": status,
            "source": "auto",
            "note": (prior.get("note") if same_attachment else "") or "",
        }
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception:
            _set_hint("Kunne ikke lagre automatisk UB-forslag.")
            return
        _set_hint("")
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _set_selected_as_primary() -> None:
        row = _selected_att_row()
        if not row:
            messagebox.showinfo(
                "Primært UB-bevis",
                "Velg et vedlegg i Vedlegg-fanen først.",
                parent=dlg,
            )
            return
        path = str(row.get("path") or "")
        if not path:
            return
        prior = _load_evidence() or {}
        prior_source = str(prior.get("source") or "").lower()
        prior_path = str(prior.get("attachment_path") or "")
        same_attachment = prior_path == path

        # Prøv automatisk forslag først hvis det er trygt (ingen manuell
        # markering skal overskrives uten eksplisitt handling).
        auto: dict | None = None
        may_auto = (
            not prior  # ingen eksisterende
            or prior_source == "auto"
            or (prior_source == "manual" and not same_attachment)  # nytt vedlegg
        ) and (not prior.get("bbox") or prior_source != "manual" or not same_attachment)
        if may_auto:
            auto = _attempt_auto_find(path)

        if auto is not None:
            raw_value = str(auto.get("raw_value") or "")
            normalized = auto.get("normalized_value")
            status, _avvik = _compute_status(
                float(normalized) if normalized is not None else None,
                expected_ub_value,
            )
            new_ev = {
                "attachment_path": path,
                "attachment_label": row.get("label") or _Path(path).name,
                "page": int(auto.get("page") or 1),
                "bbox": list(auto.get("bbox") or []),
                "raw_value": raw_value,
                "normalized_value": normalized,
                "status": status,
                "source": "auto",
                "note": var_note.get() or (prior.get("note") if same_attachment else ""),
            }
        else:
            # Fallback: gjenbruk eksisterende bevis for samme vedlegg, ellers tomt.
            keep = prior if same_attachment else {}
            new_ev = {
                "attachment_path": path,
                "attachment_label": row.get("label") or _Path(path).name,
                "page": keep.get("page") or 1,
                "bbox": keep.get("bbox"),
                "raw_value": keep.get("raw_value") or var_raw.get(),
                "normalized_value": keep.get("normalized_value"),
                "status": keep.get("status") or "unchecked",
                "source": keep.get("source") or "manual",
                "note": var_note.get() or keep.get("note") or "",
            }

        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _find_ub_auto_explicit() -> None:
        """Eksplisitt 'Finn UB automatisk' — overstyrer også manuelt bevis hvis bruker bekrefter."""
        ev = _load_evidence() or {}
        path = str(ev.get("attachment_path") or "")
        if not path:
            row = _selected_att_row()
            if row:
                path = str(row.get("path") or "")
        if not path:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Velg et vedlegg i Vedlegg-listen først.",
                parent=dlg,
            )
            return

        try:
            from document_control_viewer import preview_kind_for_path
            kind = preview_kind_for_path(path)
        except Exception:
            kind = "unsupported"
        if kind != "pdf":
            messagebox.showinfo(
                "Finn UB automatisk",
                "Automatisk søk støttes foreløpig bare for PDF.",
                parent=dlg,
            )
            return
        if expected_ub_value is None:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Forventet UB er ikke tilgjengelig fra analysen.",
                parent=dlg,
            )
            return

        existing_source = str(ev.get("source") or "").lower()
        if existing_source == "manual" and ev.get("bbox"):
            if not messagebox.askyesno(
                "Finn UB automatisk",
                "Det finnes allerede et manuelt markert bevis. Vil du la "
                "automatisk forslag overstyre dette?",
                parent=dlg,
            ):
                return

        match = _attempt_auto_find(path)
        if not match:
            messagebox.showinfo(
                "Finn UB automatisk",
                "Fant ikke et entydig treff. Bruk 'Marker manuelt' i stedet.",
                parent=dlg,
            )
            return

        normalized = match.get("normalized_value")
        status, _avvik = _compute_status(
            float(normalized) if normalized is not None else None,
            expected_ub_value,
        )
        new_ev = {
            "attachment_path": path,
            "attachment_label": ev.get("attachment_label") or _Path(path).name,
            "page": int(match.get("page") or 1),
            "bbox": list(match.get("bbox") or []),
            "raw_value": str(match.get("raw_value") or ""),
            "normalized_value": normalized,
            "status": status,
            "source": "auto",
            "note": var_note.get() or ev.get("note") or "",
        }
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        _focus_ub_evidence()

    def _start_marking() -> None:
        if preview is None:
            messagebox.showinfo(
                "Marker UB-felt",
                "Forhåndsvisning er ikke tilgjengelig.",
                parent=dlg,
            )
            return
        ev = _load_evidence()
        path = ""
        if ev:
            path = str(ev.get("attachment_path") or "")
        if not path:
            row = _selected_att_row()
            if row:
                path = str(row.get("path") or "")
        if not path or not _Path(path).exists():
            messagebox.showinfo(
                "Marker UB-felt",
                "Velg et vedlegg i Vedlegg-fanen eller sett et primært bevis først.",
                parent=dlg,
            )
            return
        try:
            preview.load_file(path)
        except Exception:
            pass

        def _on_marked(page_no: int, bbox: tuple[float, float, float, float]) -> None:
            ev_now = _load_evidence() or {}
            row = _selected_att_row()
            label = (
                ev_now.get("attachment_label")
                or (row.get("label") if row else None)
                or _Path(path).name
            )
            new_ev = {
                "attachment_path": path,
                "attachment_label": label,
                "page": int(page_no),
                "bbox": list(bbox),
                "raw_value": ev_now.get("raw_value") or var_raw.get(),
                "normalized_value": ev_now.get("normalized_value"),
                "status": "unchecked",
                "source": "manual",
                "note": var_note.get(),
            }
            try:
                _rco.save_ub_evidence(client, year, konto, new_ev)
            except Exception as exc:
                messagebox.showerror("UB-bevis",
                                     f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
                return
            _refresh_ub_tab()
            _refresh_sb_after_review_change(page)

        try:
            preview.start_marking(_on_marked, label="UB")
        except Exception:
            pass

    def _use_marked_value() -> None:
        parsed = _parse_norwegian_number(var_raw.get())
        ev = _load_evidence()
        if not ev:
            messagebox.showinfo(
                "Bruk markert verdi",
                "Lagre et UB-bevis (marker UB-felt) før du registrerer verdi.",
                parent=dlg,
            )
            return
        status, _avvik = _compute_status(parsed, expected_ub_value)
        new_ev = dict(ev)
        new_ev["raw_value"] = var_raw.get().strip()
        new_ev["normalized_value"] = parsed
        new_ev["status"] = status
        new_ev["note"] = var_note.get()
        try:
            _rco.save_ub_evidence(client, year, konto, new_ev)
        except Exception as exc:
            messagebox.showerror("UB-bevis",
                                 f"Kunne ikke lagre UB-bevis:\n{exc}", parent=dlg)
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)

    def _clear_evidence() -> None:
        if not messagebox.askyesno(
            "Fjern UB-bevis",
            "Vil du fjerne UB-bevis for denne kontoen?",
            parent=dlg,
        ):
            return
        try:
            _rco.clear_ub_evidence(client, year, konto)
        except Exception:
            return
        _refresh_ub_tab()
        _refresh_sb_after_review_change(page)
        if preview is not None:
            try:
                preview.set_highlight(None)
            except Exception:
                pass

    ttk.Button(ub_btn_row, text="Bruk som primært bevis",
               command=_set_selected_as_primary).pack(side="left")
    ttk.Button(ub_btn_row, text="Finn UB automatisk",
               command=_find_ub_auto_explicit).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Marker manuelt",
               command=_start_marking).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Bruk registrert verdi",
               command=_use_marked_value).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Gå til UB-bevis",
               command=_focus_ub_evidence).pack(side="left", padx=(6, 0))
    ttk.Button(ub_btn_row, text="Fjern markering",
               command=_clear_evidence).pack(side="left", padx=(6, 0))

    # Ingen `Lukk`-knapp i hovedvinduet — vindus-X og Escape lukker dialogen.

    # ---------- Tastatur ----------
    dlg.bind("<Escape>", lambda _e: dlg.destroy())
    dlg.bind("<Control-Return>", _save_comment)

    _refresh_ok_label()
    _fill_atts()
    _refresh_ub_tab()

    # Hvis bevis finnes ved åpning: last vedlegg i preview og fokuser bevis
    _focus_ub_evidence()

    def _apply_sash_ratio() -> None:
        """Sett sash slik at preview (høyre) får ~65% av bredden."""
        try:
            total = paned.winfo_width()
            if total > 200:
                paned.sashpos(0, int(total * 0.35))
        except Exception:
            pass

    dlg.update_idletasks()
    try:
        w, h = 1320, 780
        x = page.winfo_rootx() + max(0, (page.winfo_width() - w) // 2)
        y = page.winfo_rooty() + max(0, (page.winfo_height() - h) // 2)
        dlg.geometry(f"{w}x{h}+{x}+{y}")
    except Exception:
        pass
    # Kjør sash-justering etter geometry er satt (Tkinter trenger en runde
    # for at winfo_width() skal gjenspeile ny vindusstørrelse).
    dlg.after(50, _apply_sash_ratio)
    c_txt.focus_set()


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


# =====================================================================
# Motpost-visning (inline i høyre panel)
# =====================================================================

MP_COLS = ("Konto", "Kontonavn", "Bilag", "Dato", "Tekst", "Beløp")

_MP_COL_WIDTHS = {
    "Konto":     70,
    "Kontonavn": 180,
    "Bilag":     80,
    "Dato":      90,
    "Tekst":     240,
    "Beløp":     110,
}


def create_mp_tree(parent_frame: Any) -> Any:
    """Opprett en motpost-treeview i parent_frame."""
    try:
        from tkinter import ttk
        import tkinter as tk
    except Exception:
        return None

    frame = ttk.Frame(parent_frame)

    tree = ttk.Treeview(frame, columns=MP_COLS, show="headings", selectmode="extended")
    tree.grid(row=0, column=0, sticky="nsew")

    for col in MP_COLS:
        tree.heading(col, text=col)
        anchor = "e" if col == "Beløp" else "w"
        stretch = col == "Tekst"
        tree.column(col, width=_MP_COL_WIDTHS.get(col, 100), anchor=anchor, stretch=stretch)

    # Tag: valgt kontos linjer utheves
    try:
        tree.tag_configure("selected_account", background="#E5F1EE")
        tree.tag_configure("motpost", background="#FFFDF8")
        tree.tag_configure("neg", foreground="#C62828")
    except Exception:
        pass

    v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    h_scroll.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame._mp_tree = tree  # type: ignore[attr-defined]

    return frame


def show_mp_tree(*, page: Any) -> None:
    """Vis motpost-treet og skjul andre visninger."""
    mp_frame = getattr(page, "_mp_frame", None)
    if mp_frame is None:
        return
    _hide_all_views(page=page, except_frame=mp_frame)
    try:
        mp_frame.grid()
    except Exception:
        pass


def refresh_mp_view(*, page: Any) -> None:
    """Fyll motpost-treet med transaksjoner for valgte kontoer + motposter."""
    mp_frame = getattr(page, "_mp_frame", None)
    if mp_frame is None:
        return
    tree = getattr(mp_frame, "_mp_tree", None)
    if tree is None:
        return

    _clear_tree(tree)

    # Hent valgte kontoer
    accounts = []
    try:
        accounts = list(page._get_selected_accounts())
    except Exception:
        pass

    if not accounts:
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl:
            try:
                lbl.configure(text="Velg konto(er) i pivot-listen for å se motposter")
            except Exception:
                pass
        return

    # Hent datasett
    import session
    df_all = getattr(page, "dataset", None)
    if df_all is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
        df_all = getattr(session, "dataset", None)
    if df_all is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
        return

    required = {"Bilag", "Konto", "Beløp"}
    if not required.issubset(set(df_all.columns)):
        return

    # Bruk filtrert datasett for å finne bilag
    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        df_filtered = df_all

    accounts_set = {str(a).strip() for a in accounts}
    mask = df_filtered["Konto"].astype(str).str.strip().isin(accounts_set)
    bilag_list = df_filtered.loc[mask, "Bilag"].astype(str).str.strip().unique().tolist()
    bilag_list = [b for b in bilag_list if b]

    if not bilag_list:
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl:
            try:
                lbl.configure(text="Ingen bilag funnet for valgte kontoer")
            except Exception:
                pass
        return

    # Hent alle linjer for disse bilagene fra fullt datasett
    bilag_set = set(bilag_list)
    df_scope = df_all[df_all["Bilag"].astype(str).str.strip().isin(bilag_set)].copy()

    if df_scope.empty:
        return

    # Sorter: bilag → konto
    try:
        df_scope = df_scope.sort_values(["Bilag", "Konto"])
    except Exception:
        pass

    use_decimals = True
    try:
        use_decimals = bool(getattr(page, "_var_decimals", None) and page._var_decimals.get())
    except Exception:
        pass

    # Fyll treet
    for row in df_scope.itertuples(index=False):
        konto = str(getattr(row, "Konto", "")).strip()
        kontonavn = str(getattr(row, "Kontonavn", "")).strip() if hasattr(row, "Kontonavn") else ""
        bilag = str(getattr(row, "Bilag", "")).strip()
        dato = str(getattr(row, "Dato", "")).strip() if hasattr(row, "Dato") else ""
        tekst = str(getattr(row, "Tekst", "")).strip() if hasattr(row, "Tekst") else ""
        try:
            belop_raw = float(getattr(row, "Beløp", 0) or 0)
        except (ValueError, TypeError):
            belop_raw = 0.0

        if use_decimals:
            belop = formatting.fmt_amount(belop_raw)
        else:
            belop = formatting.fmt_amount(round(belop_raw))

        tags = ()
        if konto in accounts_set:
            tags = ("selected_account",)
        else:
            tags = ("motpost",)
        if belop_raw < 0:
            tags = (*tags, "neg")

        tree.insert("", "end", values=(konto, kontonavn, bilag, dato, tekst, belop), tags=tags)

    # Summary
    lbl = getattr(page, "_lbl_tx_summary", None)
    if lbl:
        try:
            n_bilag = len(bilag_set)
            n_lines = len(df_scope)
            lbl.configure(text=f"Motposter: {n_bilag} bilag, {n_lines} linjer")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Motposter (kontonivå) — aggregert motpost per konto
# ---------------------------------------------------------------------------

_MP_ACCT_COLS = ("Motkonto", "Kontonavn", "Antall bilag", "Sum")
_MP_ACCT_COL_WIDTHS = {
    "Motkonto":      90,
    "Kontonavn":     240,
    "Antall bilag":  100,
    "Sum":           120,
}


def create_mp_account_tree(parent_frame: Any) -> Any:
    """Opprett en motpost-kontonivå-treeview i parent_frame."""
    try:
        from tkinter import ttk
        import tkinter as tk
    except Exception:
        return None

    frame = ttk.Frame(parent_frame)

    tree = ttk.Treeview(frame, columns=_MP_ACCT_COLS, show="headings", selectmode="extended")
    tree.grid(row=0, column=0, sticky="nsew")

    for col in _MP_ACCT_COLS:
        tree.heading(col, text=col)
        anchor = "e" if col in ("Antall bilag", "Sum") else "w"
        stretch = col == "Kontonavn"
        tree.column(col, width=_MP_ACCT_COL_WIDTHS.get(col, 100), anchor=anchor, stretch=stretch)

    try:
        tree.tag_configure("selected_account", background="#E5F1EE")
        tree.tag_configure("motpost", background="#FFFDF8")
        tree.tag_configure("neg", foreground="#C62828")
    except Exception:
        pass

    v_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    v_scroll.grid(row=0, column=1, sticky="ns")
    h_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    h_scroll.grid(row=1, column=0, sticky="ew")
    tree.configure(yscrollcommand=v_scroll.set, xscrollcommand=h_scroll.set)

    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    frame._mp_acct_tree = tree  # type: ignore[attr-defined]

    return frame


def show_mp_account_tree(*, page: Any) -> None:
    """Vis motpost-kontonivå-treet og skjul andre visninger."""
    mp_acct_frame = getattr(page, "_mp_acct_frame", None)
    if mp_acct_frame is None:
        return
    _hide_all_views(page=page, except_frame=mp_acct_frame)
    try:
        mp_acct_frame.grid()
    except Exception:
        pass


def refresh_mp_account_view(*, page: Any) -> None:
    """Fyll motpost-kontonivå med aggregert motpost per konto for valgte kontoer."""
    mp_acct_frame = getattr(page, "_mp_acct_frame", None)
    if mp_acct_frame is None:
        return
    tree = getattr(mp_acct_frame, "_mp_acct_tree", None)
    if tree is None:
        return

    _clear_tree(tree)

    # Hent valgte kontoer
    accounts: list[str] = []
    try:
        accounts = list(page._get_selected_accounts())
    except Exception:
        pass

    if not accounts:
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl:
            try:
                lbl.configure(text="Velg konto(er) i pivot-listen for å se motposter (kontonivå)")
            except Exception:
                pass
        return

    # Hent datasett
    import session
    df_all = getattr(page, "dataset", None)
    if df_all is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
        df_all = getattr(session, "dataset", None)
    if df_all is None or not isinstance(df_all, pd.DataFrame) or df_all.empty:
        return

    required = {"Bilag", "Konto", "Beløp"}
    if not required.issubset(set(df_all.columns)):
        return

    # Bruk filtrert datasett for å finne bilag
    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        df_filtered = df_all

    accounts_set = {str(a).strip() for a in accounts}
    mask = df_filtered["Konto"].astype(str).str.strip().isin(accounts_set)
    bilag_list = df_filtered.loc[mask, "Bilag"].astype(str).str.strip().unique().tolist()
    bilag_list = [b for b in bilag_list if b]

    if not bilag_list:
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl:
            try:
                lbl.configure(text="Ingen bilag funnet for valgte kontoer")
            except Exception:
                pass
        return

    # Hent alle linjer for disse bilagene fra fullt datasett
    bilag_set = set(bilag_list)
    df_scope = df_all[df_all["Bilag"].astype(str).str.strip().isin(bilag_set)].copy()

    if df_scope.empty:
        return

    # Motposter = linjer som IKKE er valgt konto
    motpost_df = df_scope[~df_scope["Konto"].astype(str).str.strip().isin(accounts_set)].copy()

    if motpost_df.empty:
        lbl = getattr(page, "_lbl_tx_summary", None)
        if lbl:
            try:
                lbl.configure(text="Ingen motposter funnet")
            except Exception:
                pass
        return

    # Aggreger per motkonto
    motpost_df["MKonto"] = motpost_df["Konto"].astype(str).str.strip()
    motpost_df["MNavn"] = ""
    if "Kontonavn" in motpost_df.columns:
        motpost_df["MNavn"] = motpost_df["Kontonavn"].astype(str).str.strip()

    agg = motpost_df.groupby(["MKonto", "MNavn"]).agg(
        Sum=("Beløp", "sum"),
        Antall=("Bilag", "nunique"),
    ).reset_index()
    agg = agg.sort_values("Sum", key=abs, ascending=False)

    use_decimals = True
    try:
        use_decimals = bool(getattr(page, "_var_decimals", None) and page._var_decimals.get())
    except Exception:
        pass

    # Vis først valgte kontoer som oppsummering
    for acct in sorted(accounts_set):
        acct_mask = df_scope["Konto"].astype(str).str.strip() == acct
        acct_df = df_scope[acct_mask]
        acct_sum = acct_df["Beløp"].sum() if not acct_df.empty else 0.0
        acct_name = ""
        if "Kontonavn" in acct_df.columns and not acct_df.empty:
            acct_name = str(acct_df["Kontonavn"].iloc[0]).strip()
        n_bilag = acct_df["Bilag"].nunique() if not acct_df.empty else 0
        if use_decimals:
            sum_str = formatting.fmt_amount(acct_sum)
        else:
            sum_str = formatting.fmt_amount(round(acct_sum))
        tags = ("selected_account",)
        if acct_sum < 0:
            tags = (*tags, "neg")
        tree.insert("", "end", values=(acct, acct_name, n_bilag, sum_str), tags=tags)

    # Vis motkontoer
    for row in agg.itertuples(index=False):
        konto = row.MKonto
        kontonavn = row.MNavn
        antall = int(row.Antall)
        belop_raw = float(row.Sum)

        if use_decimals:
            belop = formatting.fmt_amount(belop_raw)
        else:
            belop = formatting.fmt_amount(round(belop_raw))

        tags = ("motpost",)
        if belop_raw < 0:
            tags = (*tags, "neg")

        tree.insert("", "end", values=(konto, kontonavn, antall, belop), tags=tags)

    # Summary
    lbl = getattr(page, "_lbl_tx_summary", None)
    if lbl:
        try:
            n_motkontoer = len(agg)
            n_bilag = len(bilag_set)
            lbl.configure(text=f"Motposter (kontonivå): {n_motkontoer} motkontoer, {n_bilag} bilag")
        except Exception:
            pass
