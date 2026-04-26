"""page_analyse_pivot.py

Pivot-logikk for Analyse-fanen (venstre panel).

Flyttet ut av page_analyse.py for bedre struktur og vedlikehold.

Denne modulen er GUI-uavhengig i den forstand at den kun bruker Treeview-API
via et "duck-typed" page-objekt.
"""

from __future__ import annotations

from typing import Any, List

import pandas as pd

import formatting
from analyse_model import build_pivot_by_account
from konto_utils import konto_to_str


def _capture_account_pivot_selection(*, tree: Any) -> tuple[list[str], str]:
    selected_accounts: list[str] = []
    focused_account = ""

    try:
        selected_items = list(tree.selection())
    except Exception:
        selected_items = []

    for item in selected_items:
        try:
            konto = konto_to_str(tree.set(item, "Konto"))
        except Exception:
            konto = ""
        if konto:
            selected_accounts.append(konto)

    try:
        focused_item = tree.focus()
    except Exception:
        focused_item = ""

    if focused_item:
        try:
            focused_account = konto_to_str(tree.set(focused_item, "Konto"))
        except Exception:
            focused_account = ""

    return selected_accounts, focused_account


def _restore_account_pivot_selection(*, tree: Any, selected_accounts: list[str], focused_account: str) -> None:
    if tree is None:
        return

    wanted = {str(k or "").strip() for k in selected_accounts if str(k or "").strip()}
    focus_wanted = str(focused_account or "").strip()

    items_to_select: list[str] = []
    focus_item = ""
    try:
        items = tree.get_children("")
    except Exception:
        items = ()

    for item in items:
        try:
            konto = konto_to_str(tree.set(item, "Konto"))
        except Exception:
            konto = ""
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


def _resolve_agg_mode(page: Any) -> str:
    """Les aggregeringsmodus med legacy-migrering ('Konto' → 'SB-konto')."""
    try:
        from page_analyse_columns import normalize_aggregation_mode
    except Exception:
        def normalize_aggregation_mode(v: object) -> str:  # type: ignore[no-redef]
            s = str(v or "").strip()
            return "SB-konto" if s == "Konto" else s
    agg_var = getattr(page, "_var_aggregering", None)
    try:
        raw = agg_var.get() if agg_var is not None else ""
    except Exception:
        raw = ""
    return normalize_aggregation_mode(raw)


def _resolve_active_year() -> int | None:
    try:
        import session as _session
        raw = getattr(_session, "year", None)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _build_sb_konto_pivot(*, page: Any) -> pd.DataFrame:
    """Bygg SB-konto pivot fra effektiv SB + fjorårs SB + HB-antall.

    Kolonner i resultatet: Konto, Kontonavn, Sum beløp (UB aktivt år),
    UB_fjor (UB forrige år), Endring_fjor (UB - UB_fjor), Endring_pct,
    Endring (fallback = netto eller ub - ib ved manglende fjorsdata),
    Antall bilag (fra HB-pivot nunique(Bilag) under aktive filtre).
    """
    # --- Effektiv SB (AO-justert hvis aktivert) ---
    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = None

    cols = ["Konto", "Kontonavn", "Sum beløp", "UB_fjor", "Endring_fjor",
            "Endring_pct", "Endring", "Antall bilag"]

    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return pd.DataFrame(columns=cols)

    konto_col = next((c for c in sb_df.columns if str(c).strip().lower() == "konto"), None)
    if not konto_col:
        return pd.DataFrame(columns=cols)

    name_col = next((c for c in sb_df.columns if str(c).strip().lower() == "kontonavn"), None)
    ub_col = next((c for c in sb_df.columns if str(c).strip().lower() == "ub"), None)
    ib_col = next((c for c in sb_df.columns if str(c).strip().lower() == "ib"), None)
    netto_col = next((c for c in sb_df.columns if str(c).strip().lower() == "netto"), None)

    work = sb_df.copy()
    work[konto_col] = work[konto_col].astype(str).str.strip()
    if ub_col:
        work[ub_col] = pd.to_numeric(work[ub_col], errors="coerce").fillna(0.0)
    if ib_col:
        work[ib_col] = pd.to_numeric(work[ib_col], errors="coerce").fillna(0.0)
    if netto_col:
        work[netto_col] = pd.to_numeric(work[netto_col], errors="coerce").fillna(0.0)
    if name_col:
        work[name_col] = work[name_col].fillna("").astype(str)

    agg_map: dict[str, str] = {}
    if ub_col:
        agg_map[ub_col] = "sum"
    if ib_col:
        agg_map[ib_col] = "sum"
    if netto_col:
        agg_map[netto_col] = "sum"
    if name_col:
        agg_map[name_col] = "first"

    if not agg_map:
        return pd.DataFrame(columns=cols)

    grouped = work.groupby(konto_col, as_index=False).agg(agg_map)
    rename = {konto_col: "Konto"}
    if name_col:
        rename[name_col] = "Kontonavn"
    if ub_col:
        rename[ub_col] = "_ub"
    if ib_col:
        rename[ib_col] = "_ib"
    if netto_col:
        rename[netto_col] = "_netto"
    grouped = grouped.rename(columns=rename)

    if "Kontonavn" not in grouped.columns:
        grouped["Kontonavn"] = ""

    grouped["Sum beløp"] = grouped.get("_ub", 0.0)

    # Fallback-bevegelse når fjorårsdata mangler: netto, ellers ub - ib
    if "_netto" in grouped.columns:
        grouped["Endring"] = grouped["_netto"]
    elif "_ib" in grouped.columns and "_ub" in grouped.columns:
        grouped["Endring"] = grouped["_ub"] - grouped["_ib"]
    else:
        grouped["Endring"] = 0.0

    # --- Forrige års SB ---
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    has_prev = (
        isinstance(sb_prev, pd.DataFrame)
        and not sb_prev.empty
    )
    if has_prev:
        pk_col = next((c for c in sb_prev.columns if str(c).strip().lower() == "konto"), None)
        pu_col = next((c for c in sb_prev.columns if str(c).strip().lower() == "ub"), None)
        if pk_col and pu_col:
            prev = sb_prev[[pk_col, pu_col]].copy()
            prev[pk_col] = prev[pk_col].astype(str).str.strip()
            prev[pu_col] = pd.to_numeric(prev[pu_col], errors="coerce").fillna(0.0)
            prev = prev.groupby(pk_col, as_index=False).agg({pu_col: "sum"})
            prev = prev.rename(columns={pk_col: "Konto", pu_col: "UB_fjor"})
            grouped = grouped.merge(prev, how="left", on="Konto")
        else:
            has_prev = False
    if "UB_fjor" in grouped.columns:
        grouped["Endring_fjor"] = grouped["Sum beløp"] - grouped["UB_fjor"].fillna(0.0)
        denom = grouped["UB_fjor"].abs()
        grouped["Endring_pct"] = (grouped["Endring_fjor"] / denom.where(denom > 1e-9)) * 100.0
    else:
        grouped["UB_fjor"] = pd.NA
        grouped["Endring_fjor"] = pd.NA
        grouped["Endring_pct"] = pd.NA

    # --- Antall bilag fra HB-pivot (filtrert) ---
    df_filtered = getattr(page, "_df_filtered", None)
    if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty:
        try:
            hb_pivot = build_pivot_by_account(df_filtered)
        except Exception:
            hb_pivot = pd.DataFrame()
        if isinstance(hb_pivot, pd.DataFrame) and not hb_pivot.empty and "Konto" in hb_pivot.columns:
            cnt_col = next((c for c in hb_pivot.columns if str(c).startswith("Antall")), None)
            if cnt_col:
                hb_small = hb_pivot[["Konto", cnt_col]].copy()
                hb_small["Konto"] = hb_small["Konto"].astype(str).str.strip()
                hb_small = hb_small.rename(columns={cnt_col: "Antall bilag"})
                grouped = grouped.merge(hb_small, how="left", on="Konto")
    if "Antall bilag" not in grouped.columns:
        grouped["Antall bilag"] = 0
    grouped["Antall bilag"] = pd.to_numeric(grouped["Antall bilag"], errors="coerce").fillna(0).astype(int)

    grouped = grouped.drop(columns=["_ub", "_ib", "_netto"], errors="ignore")
    grouped = grouped.sort_values(["Konto", "Kontonavn"], kind="mergesort", ignore_index=True)
    for c in cols:
        if c not in grouped.columns:
            grouped[c] = 0.0 if c == "Sum beløp" else pd.NA
    return grouped[cols]


def refresh_pivot(*, page: Any) -> None:
    """Bygg pivot og fyll treeview – dispatcher på aggregering-modus."""
    agg_mode = _resolve_agg_mode(page)

    # Timing-event sendes til src.monitoring.perf. Sett UTVALG_PROFILE=analyse
    # (eller bakoverkompat UTVALG_PROFILE_REFRESH=1) for stderr-print i tillegg.
    import time as _time
    import logging
    _log = logging.getLogger("app")
    _t0 = _time.perf_counter()

    try:
        if agg_mode == "Regnskapslinje":
            try:
                import page_analyse_rl
                page_analyse_rl.refresh_rl_pivot(page=page)
            except Exception as exc:
                _log.warning("refresh_pivot (RL): %s", exc)
            return

        if agg_mode == "MVA-kode":
            try:
                import page_analyse_mva
                page_analyse_mva.refresh_mva_pivot(page=page)
            except Exception as exc:
                _log.warning("refresh_pivot (MVA): %s", exc)
            return

        if agg_mode == "SB-konto":
            refresh_sb_konto_pivot(page=page)
            return

        # Default + legacy: HB-konto
        refresh_hb_konto_pivot(page=page)
    finally:
        try:
            from src.monitoring.perf import record_event as _record_event
            _record_event(
                "analyse.pivot.dispatch",
                (_time.perf_counter() - _t0) * 1000.0,
                meta={"mode": agg_mode},
            )
        except Exception:
            pass


def refresh_sb_konto_pivot(*, page: Any) -> None:
    """Fyll pivot_tree i SB-konto-modus (UB aktivt år + komparativ)."""
    try:
        page._rl_mapping_warning = ""
    except Exception:
        pass
    try:
        import page_analyse_rl
        page_analyse_rl.ensure_sb_prev_loaded(page=page)
        page_analyse_rl.update_pivot_headings(page=page, mode="SB-konto")
    except Exception:
        pass

    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    selected_accounts, focused_account = _capture_account_pivot_selection(tree=tree)

    try:
        page._clear_tree(tree)
    except Exception:
        pass

    pivot_df = _build_sb_konto_pivot(page=page)

    show_only_unmapped = False
    try:
        var = getattr(page, "_var_show_only_unmapped", None)
        if var is not None:
            show_only_unmapped = bool(var.get())
    except Exception:
        show_only_unmapped = False

    if show_only_unmapped:
        wanted = {
            str(v).strip()
            for v in getattr(page, "_mapping_problem_accounts", []) or []
            if str(v).strip()
        }
        if wanted:
            pivot_df = pivot_df.loc[
                pivot_df["Konto"].astype(str).str.strip().isin(wanted)
            ].copy()
        else:
            pivot_df = pivot_df.iloc[0:0].copy()

    hide_zero = False
    try:
        var = getattr(page, "_var_hide_zero", None)
        if var is not None:
            hide_zero = bool(var.get())
    except Exception:
        pass

    account_comments: dict[str, str] = {}
    account_review: dict[str, dict] = {}
    try:
        import src.shared.regnskap.client_overrides as _rco
        import session as _sess
        _cl = getattr(_sess, "client", None) or ""
        _yr = getattr(_sess, "year", None)
        if _cl:
            account_comments = _rco.load_comments(_cl).get("accounts", {})
            if _yr is not None:
                try:
                    account_review = _rco.load_account_review(_cl, str(_yr))
                except Exception:
                    account_review = {}
    except Exception:
        pass

    try:
        tree.tag_configure("commented", foreground="#1565C0")
    except Exception:
        pass

    # Lys grønn bakgrunn for konti markert som OK (ferdigrevidert)
    try:
        tree.tag_configure("ok_row", background="#E3F5E1")
    except Exception:
        pass

    try:
        snap = pivot_df.copy()
        page._pivot_df_last = snap
        page._pivot_df_sb_konto = snap
    except Exception:
        pass

    _dec = 2
    try:
        _var_dec = getattr(page, "_var_decimals", None)
        if _var_dec is not None and not bool(_var_dec.get()):
            _dec = 0
    except Exception:
        pass

    has_prev = bool(pivot_df["UB_fjor"].notna().any()) if "UB_fjor" in pivot_df.columns else False

    for _, row in pivot_df.iterrows():
        konto = konto_to_str(row.get("Konto", ""))
        navn = str(row.get("Kontonavn", "") or "")
        sum_val = row.get("Sum beløp", 0.0)
        cnt_val = row.get("Antall bilag", 0)

        if hide_zero:
            # Skjul kun kontoer som er 0 b\u00e5de i aktuelt \u00e5r og i fjor.
            try:
                cur_zero = abs(float(sum_val or 0)) < 0.005
            except Exception:
                cur_zero = False
            ub_fjor_val = row.get("UB_fjor")
            try:
                prev_zero = (
                    ub_fjor_val is None
                    or (isinstance(ub_fjor_val, float) and ub_fjor_val != ub_fjor_val)
                    or abs(float(ub_fjor_val or 0)) < 0.005
                )
            except Exception:
                prev_zero = True
            if cur_zero and prev_zero:
                continue

        comment = account_comments.get(konto, "")
        is_ok = bool(account_review.get(konto, {}).get("ok"))
        _pt: list[str] = []
        if comment:
            _pt.append("commented")
        if is_ok:
            _pt.append("ok_row")
        tags = tuple(_pt)

        sum_txt = formatting.fmt_amount(sum_val, decimals=_dec)
        cnt_txt = formatting.format_int_no(cnt_val)

        ub_fjor_val = row.get("UB_fjor")
        endring_fjor_val = row.get("Endring_fjor")
        endring_pct_val = row.get("Endring_pct")
        endring_fallback = row.get("Endring")

        def _fmt_opt(v: Any) -> str:
            if v is None:
                return ""
            try:
                if v != v:  # NaN
                    return ""
            except Exception:
                pass
            try:
                return formatting.fmt_amount(float(v), decimals=_dec)
            except Exception:
                return ""

        def _fmt_pct(v: Any) -> str:
            if v is None:
                return ""
            try:
                if v != v:
                    return ""
            except Exception:
                pass
            try:
                return f"{float(v):.1f} %"
            except Exception:
                return ""

        if has_prev:
            endring_txt = ""  # intern Endring skjules i komparativ modus
            ub_fjor_txt = _fmt_opt(ub_fjor_val)
            endring_fjor_txt = _fmt_opt(endring_fjor_val)
            endring_pct_txt = _fmt_pct(endring_pct_val)
        else:
            endring_txt = _fmt_opt(endring_fallback)
            ub_fjor_txt = ""
            endring_fjor_txt = ""
            endring_pct_txt = ""

        ok_txt = "OK" if is_ok else ""
        try:
            tree.insert(
                "",
                "end",
                values=(
                    konto,            # Konto
                    navn,             # Kontonavn
                    ok_txt,           # OK
                    "",               # IB
                    endring_txt,      # Endring (fallback uten fjorsdata)
                    sum_txt,          # Sum (UB aktivt år)
                    "",               # AO_belop
                    "",               # UB_for_ao
                    "",               # UB_etter_ao
                    cnt_txt,          # Antall
                    ub_fjor_txt,      # UB_fjor
                    endring_fjor_txt, # Endring_fjor
                    endring_pct_txt,  # Endring_pct
                ),
                tags=tags,
            )
        except Exception:
            continue

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
        except Exception:
            pass

    _restore_account_pivot_selection(
        tree=tree,
        selected_accounts=selected_accounts,
        focused_account=focused_account,
    )

    if show_only_unmapped:
        try:
            current_sel = list(tree.selection())
        except Exception:
            current_sel = []
        if not current_sel:
            try:
                first = next(iter(tree.get_children("")), "")
            except Exception:
                first = ""
            if first:
                try:
                    tree.selection_set((first,))
                    tree.focus(first)
                    tree.see(first)
                except Exception:
                    pass


def refresh_hb_konto_pivot(*, page: Any) -> None:
    """Fyll pivot_tree i HB-konto-modus (ren HB-pivot, ingen SB-overstyring)."""
    try:
        page._rl_mapping_warning = ""
    except Exception:
        pass
    try:
        import page_analyse_rl
        page_analyse_rl.ensure_sb_prev_loaded(page=page)
        page_analyse_rl.update_pivot_headings(page=page, mode="HB-konto")
    except Exception:
        pass

    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    selected_accounts, focused_account = _capture_account_pivot_selection(tree=tree)

    try:
        page._clear_tree(tree)
    except Exception:
        # Tree cleanup should never crash GUI
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    has_hb = df_filtered is not None and isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty

    show_only_unmapped = False
    try:
        var = getattr(page, "_var_show_only_unmapped", None)
        if var is not None:
            show_only_unmapped = bool(var.get())
    except Exception:
        show_only_unmapped = False

    if not has_hb and not show_only_unmapped:
        return

    if has_hb:
        pivot_df = build_pivot_by_account(df_filtered)
    else:
        pivot_df = pd.DataFrame(columns=["Konto", "Kontonavn", "Sum beløp", "Antall bilag"])

    # Berik med UB_fjor slik at "Vis nullsaldo" kan sjekke år+fjor. Gjør ingen
    # visningsendring — UB_fjor vises ikke i HB-konto-modus — men filteret
    # skal ikke skjule kontoer som har fjorårssaldo.
    sb_prev = getattr(page, "_rl_sb_prev_df", None)
    if isinstance(sb_prev, pd.DataFrame) and not sb_prev.empty and not pivot_df.empty:
        pk_col = next((c for c in sb_prev.columns if str(c).strip().lower() == "konto"), None)
        pu_col = next((c for c in sb_prev.columns if str(c).strip().lower() == "ub"), None)
        if pk_col and pu_col:
            prev = sb_prev[[pk_col, pu_col]].copy()
            prev[pk_col] = prev[pk_col].astype(str).str.strip()
            prev[pu_col] = pd.to_numeric(prev[pu_col], errors="coerce").fillna(0.0)
            prev = prev.groupby(pk_col, as_index=False).agg({pu_col: "sum"})
            prev = prev.rename(columns={pk_col: "Konto", pu_col: "UB_fjor"})
            pivot_df = pivot_df.copy()
            pivot_df["Konto"] = pivot_df["Konto"].astype(str).str.strip()
            pivot_df = pivot_df.merge(prev, how="left", on="Konto")

    if show_only_unmapped:
        wanted = {
            str(v).strip()
            for v in getattr(page, "_mapping_problem_accounts", []) or []
            if str(v).strip()
        }
        if wanted:
            pivot_df = pivot_df.loc[
                pivot_df["Konto"].astype(str).str.strip().isin(wanted)
            ].copy()
            # Legg til problemkontoer fra SB som ikke finnes i HB-pivoten
            existing = set(pivot_df["Konto"].astype(str).str.strip())
            missing = wanted - existing
            if missing:
                issues = getattr(page, "_mapping_issues", []) or []
                new_rows = []
                for issue in issues:
                    k = str(issue.konto).strip()
                    if k in missing:
                        new_rows.append({
                            "Konto": k,
                            "Kontonavn": str(getattr(issue, "kontonavn", "") or ""),
                            "Sum beløp": float(getattr(issue, "belop", 0.0) or 0.0),
                            "Antall bilag": 0,
                        })
                if new_rows:
                    pivot_df = pd.concat(
                        [pivot_df, pd.DataFrame(new_rows)],
                        ignore_index=True,
                    )
        else:
            pivot_df = pivot_df.iloc[0:0].copy()

    # Skjul nullsaldo-kontoer om brukeren har valgt det
    hide_zero = False
    try:
        var = getattr(page, "_var_hide_zero", None)
        if var is not None:
            hide_zero = bool(var.get())
    except Exception:
        pass

    # Last konto-kommentarer
    account_comments: dict[str, str] = {}
    account_review: dict[str, dict] = {}
    try:
        import src.shared.regnskap.client_overrides as _rco
        import session as _sess
        _cl = getattr(_sess, "client", None) or ""
        _yr = getattr(_sess, "year", None)
        if _cl:
            account_comments = _rco.load_comments(_cl).get("accounts", {})
            if _yr is not None:
                try:
                    account_review = _rco.load_account_review(_cl, str(_yr))
                except Exception:
                    account_review = {}
    except Exception:
        pass

    try:
        tree.tag_configure("commented", foreground="#1565C0")
    except Exception:
        pass

    # Lys grønn bakgrunn for konti markert som OK (ferdigrevidert)
    try:
        tree.tag_configure("ok_row", background="#E3F5E1")
    except Exception:
        pass

    # Cache siste pivot for eksport
    try:
        snap = pivot_df.copy()
        page._pivot_df_last = snap
        page._pivot_df_hb_konto = snap
    except Exception:
        pass

    _dec = 2
    try:
        _var_dec = getattr(page, "_var_decimals", None)
        if _var_dec is not None and not bool(_var_dec.get()):
            _dec = 0
    except Exception:
        pass

    # Expect columns: Konto, Kontonavn, Sum beløp, Antall bilag
    for _, row in pivot_df.iterrows():
        konto = konto_to_str(row.get("Konto", ""))
        navn = str(row.get("Kontonavn", "") or "")
        sum_val = row.get("Sum beløp", 0.0)
        cnt_val = row.get("Antall bilag", 0)

        if hide_zero:
            # Skjul kun kontoer som er 0 både i aktuelt år og i fjor.
            try:
                cur_zero = abs(float(sum_val or 0)) < 0.005
            except Exception:
                cur_zero = False
            ub_fjor_val = row.get("UB_fjor") if "UB_fjor" in pivot_df.columns else None
            try:
                prev_zero = (
                    ub_fjor_val is None
                    or (isinstance(ub_fjor_val, float) and ub_fjor_val != ub_fjor_val)
                    or abs(float(ub_fjor_val or 0)) < 0.005
                )
            except Exception:
                prev_zero = True
            if cur_zero and prev_zero:
                continue

        comment = account_comments.get(konto, "")
        is_ok = bool(account_review.get(konto, {}).get("ok"))
        _pt: list[str] = []
        if comment:
            _pt.append("commented")
        if is_ok:
            _pt.append("ok_row")
        tags = tuple(_pt)

        sum_txt = formatting.fmt_amount(sum_val, decimals=_dec)
        cnt_txt = formatting.format_int_no(cnt_val)

        ok_txt = "OK" if is_ok else ""
        try:
            tree.insert(
                "",
                "end",
                values=(
                    konto,
                    navn,
                    ok_txt,
                    "",
                    "",
                    sum_txt,
                    "",
                    "",
                    "",
                    cnt_txt,
                    "",
                    "",
                    "",
                ),
                tags=tags,
            )
        except Exception:
            # Defensive: one bad row should not break UI
            continue

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
        except Exception:
            pass

    _restore_account_pivot_selection(
        tree=tree,
        selected_accounts=selected_accounts,
        focused_account=focused_account,
    )

    if show_only_unmapped:
        try:
            current_sel = list(tree.selection())
        except Exception:
            current_sel = []
        if not current_sel:
            try:
                first = next(iter(tree.get_children("")), "")
            except Exception:
                first = ""
            if first:
                try:
                    tree.selection_set((first,))
                except Exception:
                    pass
                try:
                    tree.focus(first)
                except Exception:
                    pass
                try:
                    tree.see(first)
                except Exception:
                    pass


def select_all_accounts(*, page: Any) -> None:
    """Marker alle kontoer i pivot og refresh transaksjoner."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    try:
        items = tree.get_children("")
        tree.selection_set(items)
    except Exception:
        return

    try:
        page._refresh_transactions_view()
    except Exception:
        pass


def get_selected_accounts(*, page: Any) -> List[str]:  # noqa: C901
    """Hent valgte kontoer fra pivot-tree.

    I RL-modus: mapper valgte regnskapslinjer til underliggende kontoer.
    I SB-konto / HB-konto-modus: returnerer valgte kontoer direkte.

    Dersom ingen rader er eksplisitt markert, returneres alle synlige kontoer.
    """
    agg_mode = _resolve_agg_mode(page)

    if agg_mode == "Regnskapslinje":
        try:
            import page_analyse_rl
            return page_analyse_rl.get_selected_rl_accounts(page=page)
        except Exception:
            return []

    if agg_mode == "MVA-kode":
        try:
            import page_analyse_mva
            return page_analyse_mva.get_selected_mva_accounts(page=page)
        except Exception:
            return []

    # --- SB-konto / HB-konto ---
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

    accounts: List[str] = []

    try:
        selected = tree.selection()
    except Exception:
        selected = ()

    if not selected:
        try:
            selected = tree.get_children()
        except Exception:
            selected = ()

    for item in selected:
        try:
            konto = konto_to_str(tree.set(item, "Konto"))
        except Exception:
            konto = ""
        if konto:
            accounts.append(konto)

    # de-dupe while preserving order
    seen = set()
    unique: List[str] = []
    for a in accounts:
        if a not in seen:
            unique.append(a)
            seen.add(a)

    return unique
