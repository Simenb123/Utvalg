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
    """Bygg pivot per konto og fyll treeview."""
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
            tree.insert("", "end", values=(konto, navn, sum_txt, cnt_txt))
        except Exception:
            # Defensive: one bad row should not break UI
            continue


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


def get_selected_accounts(*, page: Any) -> List[str]:
    """Hent valgte kontoer fra pivot-tree.

    Dersom ingen rader er eksplisitt markert, returneres alle synlige kontoer
    (for effektivt workflow, spesielt før "Til utvalg").
    """
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
