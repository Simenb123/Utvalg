"""analyse_sb_refresh.py — bygger SB-treet for valgt(e) regnskapslinjer.

Utskilt fra page_analyse_sb.py. refresh_sb_view og private hjelpere
(_clear_tree, _resolve_sb_columns, _capture_sb_selection,
_restore_sb_selection, _get_selected_rl_name, _get_selected_regnr,
_resolve_target_kontoer).
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import formatting


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
    accounts = set(sb_konto_str.unique().tolist())

    # Inkluder også kontoer som kun finnes i fjor-SB, slik at RL med kun
    # fjorårsdata kan resolveres og vises i hoyre-panelet.
    sb_prev_df = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev_df, pd.DataFrame) and not sb_prev_df.empty:
        prev_cols = _resolve_sb_columns(sb_prev_df)
        prev_konto_src = prev_cols.get("konto")
        if prev_konto_src:
            try:
                prev_accounts = (
                    sb_prev_df[prev_konto_src].astype(str).str.strip().unique().tolist()
                )
                accounts.update(prev_accounts)
            except Exception:
                pass

    resolved = _rl_svc.resolve_accounts_to_rl(list(accounts), context=context)
    if resolved.empty:
        return set()
    return set(
        resolved.loc[resolved["regnr"].isin(regnr_set), "konto"].astype(str).tolist()
    )


def refresh_sb_view(*, page: Any) -> None:
    """Fyll SB-treet med saldobalansekontoer for valgt(e) regnskapslinjer.

    Filtrerer bort kontoer der IB, Endring og UB alle er 0.
    """
    # Alle hjelpefunksjoner slås opp via page_analyse_sb slik at tester
    # kan monkeypatche dem der (historisk kontrakt bevart etter splittingen).
    import page_analyse_sb as _ps  # lazy for å unngå sirkulær import
    _bind_sb_once = _ps._bind_sb_once
    _clear_tree_fn = _ps._clear_tree
    _capture_fn = _ps._capture_sb_selection
    _restore_fn = _ps._restore_sb_selection
    _resolve_cols = _ps._resolve_sb_columns
    _resolve_targets = _ps._resolve_target_kontoer
    _get_rl_name = _ps._get_selected_rl_name

    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return

    selected_accounts, focused_account = _capture_fn(tree)

    _clear_tree_fn(tree)

    # Hent SB-data
    sb_df = getattr(page, "_rl_sb_df", None)
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return

    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        pass

    col_map = _resolve_cols(sb_df)
    konto_src = col_map.get("konto")
    if not konto_src:
        return

    target_konto = _resolve_targets(
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

    # Bygg UB-i-fjor-map per konto fra _rl_sb_prev_df (lastet idempotent)
    # NB: Gjoeres foer filtrering slik at kontoer med kun fjor-data overlever.
    prev_map: dict[str, float] = {}
    prev_name_map: dict[str, str] = {}
    try:
        import page_analyse_rl as _rl_mod
        _rl_mod.ensure_sb_prev_loaded(page=page)
    except Exception:
        pass
    try:
        sb_prev_df = getattr(page, "_rl_sb_prev_df", None)
        if isinstance(sb_prev_df, pd.DataFrame) and not sb_prev_df.empty:
            prev_cols = _resolve_cols(sb_prev_df)
            prev_konto = prev_cols.get("konto")
            prev_ub = prev_cols.get("ub")
            prev_navn = prev_cols.get("kontonavn")
            if prev_konto and prev_ub:
                wp = sb_prev_df[[prev_konto, prev_ub]].copy()
                wp[prev_konto] = wp[prev_konto].astype(str)
                wp[prev_ub] = pd.to_numeric(wp[prev_ub], errors="coerce")
                wp = wp.dropna(subset=[prev_ub])
                # Ved duplikater: ta siste verdi
                prev_map = dict(zip(wp[prev_konto].tolist(), wp[prev_ub].astype(float).tolist()))
            if prev_konto and prev_navn:
                try:
                    wn = sb_prev_df[[prev_konto, prev_navn]].copy()
                    wn[prev_konto] = wn[prev_konto].astype(str)
                    prev_name_map = dict(
                        zip(wn[prev_konto].tolist(), wn[prev_navn].astype(str).tolist())
                    )
                except Exception:
                    prev_name_map = {}
    except Exception:
        prev_map = {}

    # Legg til syntetiske rader for target-kontoer som kun finnes i sb_prev.
    present_in_matched: set[str] = set()
    try:
        present_in_matched = set(matched[konto_src].astype(str).str.strip().tolist())
    except Exception:
        present_in_matched = set()
    only_prev = [
        k for k in target_konto
        if str(k).strip() in prev_map and str(k).strip() not in present_in_matched
    ]
    if only_prev:
        extra_rows = []
        for k in only_prev:
            row: dict[str, Any] = {c: 0 for c in matched.columns}
            if konto_src in matched.columns:
                row[konto_src] = str(k).strip()
            navn_src = col_map.get("kontonavn")
            if navn_src and navn_src in matched.columns:
                row[navn_src] = prev_name_map.get(str(k).strip(), "")
            for nk in ("ib", "endring", "ub"):
                col = col_map.get(nk)
                if col and col in matched.columns:
                    row[col] = 0.0
            antall_col = col_map.get("antall")
            if antall_col and antall_col in matched.columns:
                row[antall_col] = 0
            extra_rows.append(row)
        if extra_rows:
            matched = pd.concat(
                [matched, pd.DataFrame(extra_rows, columns=matched.columns)],
                ignore_index=True,
            )

    # Filtrer bort rader der IB, Endring, UB *og* UB_fjor alle er 0.
    num_keys = ["ib", "endring", "ub"]
    num_cols = [col_map[k] for k in num_keys if k in col_map]
    if num_cols:
        for c in num_cols:
            matched[c] = pd.to_numeric(matched[c], errors="coerce").fillna(0.0)
        has_activity = matched[num_cols].abs().sum(axis=1) > 0.005
        if prev_map:
            prev_series = (
                matched[konto_src].astype(str).str.strip()
                .map(lambda k: abs(float(prev_map.get(k, 0.0) or 0.0)))
            )
            has_prev_activity = prev_series > 0.005
            keep = has_activity | has_prev_activity
        else:
            keep = has_activity
        active = matched[keep]
    else:
        active = matched

    # Sorter etter konto-nummer
    try:
        active = active.sort_values(konto_src, key=lambda s: pd.to_numeric(s, errors="coerce"))
    except Exception:
        pass

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
            rl_name = _get_rl_name(page=page)
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

    # Bygg konto→regnr- og regnr→regnskapslinje-mapping for valgfrie
    # SB-kolonner ("regnr", "regnskapslinje"). Disse er ikke i default
    # visible men kan slås på via kolonnemenyen.
    konto_to_regnr: dict[str, int] = {}
    regnr_to_navn: dict[int, str] = {}
    try:
        intervals = getattr(page, "_rl_intervals", None)
        regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
        if intervals is not None and regnskapslinjer is not None:
            try:
                from page_analyse_rl_data import (
                    _load_current_client_account_overrides,
                    _resolve_regnr_for_accounts,
                )
                ao = None
                try:
                    ao = _load_current_client_account_overrides()
                except Exception:
                    ao = None
                kontoer_iter = (
                    str(tup[konto_idx]) for tup in active.itertuples(index=False)
                    if konto_idx >= 0
                )
                kontoer_unique = list({k for k in kontoer_iter if k})
                if kontoer_unique:
                    lookup = _resolve_regnr_for_accounts(
                        kontoer_unique,
                        intervals=intervals,
                        regnskapslinjer=regnskapslinjer,
                        account_overrides=ao,
                    )
                    if isinstance(lookup, pd.DataFrame) and not lookup.empty:
                        for _, r in lookup.iterrows():
                            try:
                                konto_to_regnr[str(r["konto"])] = int(r["regnr"])
                            except (KeyError, TypeError, ValueError):
                                continue
            except Exception:
                pass
            # Bygg regnr→navn
            try:
                from regnskap_mapping import normalize_regnskapslinjer
                regn = normalize_regnskapslinjer(regnskapslinjer)
                for _, r in regn.iterrows():
                    try:
                        regnr_to_navn[int(r["regnr"])] = str(r["regnskapslinje"])
                    except (KeyError, TypeError, ValueError):
                        continue
            except Exception:
                pass
    except Exception:
        pass

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
            is_ok = bool(account_review.get(konto, {}).get("ok"))
            _tag_list: list[str] = []
            if comment:
                _tag_list.append("commented")
            if gruppe:
                _tag_list.append("gruppe")
            if is_ok:
                _tag_list.append("ok_row")
            tags = tuple(_tag_list)
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
            is_review_ok = bool(review_entry.get("ok"))
            ok_cell = "OK" if is_review_ok else ""
            if is_review_ok:
                ok_av_cell = str(review_entry.get("ok_by", "") or "")
                ok_at_raw = str(review_entry.get("ok_at", "") or "")
                ok_dato_cell = ok_at_raw.split("T", 1)[0] if ok_at_raw else ""
            else:
                ok_av_cell = ""
                ok_dato_cell = ""
            n_atts = len(review_entry.get("attachments") or [])
            vedlegg_cell = str(n_atts) if n_atts > 0 else ""

            # Valgfrie kolonner: regnr og regnskapslinje (lookup pr konto)
            _regnr_int = konto_to_regnr.get(konto)
            regnr_cell = str(_regnr_int) if _regnr_int is not None else ""
            regnsl_cell = regnr_to_navn.get(_regnr_int, "") if _regnr_int is not None else ""

            tree.insert("", "end", values=(
                konto,
                display_name,
                ok_cell,
                ok_av_cell,
                ok_dato_cell,
                vedlegg_cell,
                gruppe,
                regnr_cell,
                regnsl_cell,
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
    _restore_fn(
        tree,
        selected_accounts=selected_accounts,
        focused_account=focused_account,
    )
