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


def _merge_effective_sb_into_account_pivot(*, page: Any, pivot_df: pd.DataFrame) -> pd.DataFrame:
    """La konto-pivot vise AO-justert effektiv saldo der det er relevant."""
    try:
        include_ao = bool(page._include_ao_enabled())
    except Exception:
        include_ao = False
    if not include_ao:
        return pivot_df

    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = None
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return pivot_df

    konto_col = next((c for c in sb_df.columns if str(c).strip().lower() == "konto"), None)
    if not konto_col:
        return pivot_df

    sum_source = next((c for c in sb_df.columns if str(c).strip().lower() in {"ub", "endring", "netto"}), None)
    if not sum_source:
        return pivot_df

    name_source = next((c for c in sb_df.columns if str(c).strip().lower() == "kontonavn"), None)

    sum_col = next((c for c in pivot_df.columns if str(c).startswith("Sum")), None)
    count_col = next((c for c in pivot_df.columns if str(c).startswith("Antall")), None)
    if sum_col is None:
        return pivot_df

    sb_work = sb_df.copy()
    sb_work[konto_col] = sb_work[konto_col].astype(str).str.strip()
    sb_work[sum_source] = pd.to_numeric(sb_work[sum_source], errors="coerce").fillna(0.0)
    if name_source and name_source in sb_work.columns:
        sb_work[name_source] = sb_work[name_source].fillna("").astype(str)

    group_map: dict[str, str] = {sum_source: "sum"}
    if name_source and name_source in sb_work.columns:
        group_map[name_source] = "first"
    sb_grouped = sb_work.groupby(konto_col, as_index=False).agg(group_map)
    sb_grouped = sb_grouped.rename(columns={konto_col: "Konto", sum_source: "_effective_sum", name_source: "_effective_name"})

    out = pivot_df.copy()
    out["Konto"] = out["Konto"].astype(str).str.strip()
    out = out.merge(sb_grouped, how="outer", on="Konto")

    if "Kontonavn" in out.columns and "_effective_name" in out.columns:
        out["Kontonavn"] = out["Kontonavn"].fillna("").astype(str)
        out["_effective_name"] = out["_effective_name"].fillna("").astype(str)
        out["Kontonavn"] = out["Kontonavn"].where(out["Kontonavn"].str.strip() != "", out["_effective_name"])
    elif "_effective_name" in out.columns:
        out["Kontonavn"] = out["_effective_name"].fillna("").astype(str)

    out[sum_col] = pd.to_numeric(out.get(sum_col), errors="coerce")
    out["_effective_sum"] = pd.to_numeric(out.get("_effective_sum"), errors="coerce")
    out[sum_col] = out["_effective_sum"].where(out["_effective_sum"].notna(), out[sum_col]).fillna(0.0)
    if count_col is not None:
        out[count_col] = pd.to_numeric(out.get(count_col), errors="coerce").fillna(0).astype(int)

    out = out.drop(columns=["_effective_sum", "_effective_name"], errors="ignore")
    out = out.sort_values(["Konto", "Kontonavn"], kind="mergesort", ignore_index=True)
    return out


def refresh_pivot(*, page: Any) -> None:
    """Bygg pivot og fyll treeview – dispatcher på aggregering-modus."""
    # RL-modus: deleger til page_analyse_rl
    agg_var = getattr(page, "_var_aggregering", None)
    agg_mode = ""
    try:
        agg_mode = str(agg_var.get()) if agg_var is not None else ""
    except Exception:
        pass

    if agg_mode == "Regnskapslinje":
        try:
            import page_analyse_rl
            page_analyse_rl.refresh_rl_pivot(page=page)
        except Exception as exc:
            import logging
            logging.getLogger("app").warning("refresh_pivot (RL): %s", exc)
        return

    if agg_mode == "MVA-kode":
        try:
            import page_analyse_mva
            page_analyse_mva.refresh_mva_pivot(page=page)
        except Exception as exc:
            import logging
            logging.getLogger("app").warning("refresh_pivot (MVA): %s", exc)
        return

    # --- standard konto-modus – tilbakestill headings ---
    try:
        page._rl_mapping_warning = ""
    except Exception:
        pass
    try:
        import page_analyse_rl
        page_analyse_rl.update_pivot_headings(page=page, mode="Konto")
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
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        return

    pivot_df = build_pivot_by_account(df_filtered)
    pivot_df = _merge_effective_sb_into_account_pivot(page=page, pivot_df=pivot_df)

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
    try:
        import regnskap_client_overrides as _rco
        import session as _sess
        _cl = getattr(_sess, "client", None) or ""
        if _cl:
            account_comments = _rco.load_comments(_cl).get("accounts", {})
    except Exception:
        pass

    try:
        tree.tag_configure("commented", foreground="#1565C0")
    except Exception:
        pass

    # Cache siste pivot for eksport
    try:
        page._pivot_df_last = pivot_df.copy()
    except Exception:
        pass

    # Expect columns: Konto, Kontonavn, Sum beløp, Antall bilag
    for _, row in pivot_df.iterrows():
        konto = konto_to_str(row.get("Konto", ""))
        navn = str(row.get("Kontonavn", "") or "")
        sum_val = row.get("Sum beløp", 0.0)
        cnt_val = row.get("Antall bilag", 0)

        if hide_zero and abs(float(sum_val or 0)) < 0.005:
            continue

        comment = account_comments.get(konto, "")
        tags = ("commented",) if comment else ()
        if comment:
            navn = f"\u270e {navn}  \u2014 {comment}"

        sum_txt = formatting.fmt_amount(sum_val)
        cnt_txt = formatting.format_int_no(cnt_val)

        try:
            tree.insert("", "end", values=(konto, navn, "", "", sum_txt, cnt_txt), tags=tags)
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
    I konto-modus: returnerer valgte kontoer direkte (eksisterende logikk).

    Dersom ingen rader er eksplisitt markert, returneres alle synlige kontoer.
    """
    # RL-modus: deleger til page_analyse_rl
    agg_var = getattr(page, "_var_aggregering", None)
    agg_mode = ""
    try:
        agg_mode = str(agg_var.get()) if agg_var is not None else ""
    except Exception:
        pass

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

    # --- standard konto-modus ---
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
