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

    try:
        page._clear_tree(tree)
    except Exception:
        # Tree cleanup should never crash GUI
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        return

    pivot_df = build_pivot_by_account(df_filtered)

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

        sum_txt = formatting.fmt_amount(sum_val)
        cnt_txt = formatting.format_int_no(cnt_val)

        try:
            tree.insert("", "end", values=(konto, navn, "", "", sum_txt, cnt_txt))
        except Exception:
            # Defensive: one bad row should not break UI
            continue

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_pivot_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
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
