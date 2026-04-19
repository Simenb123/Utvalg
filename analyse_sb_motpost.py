"""analyse_sb_motpost.py — motpost-visninger (inline og konto-nivå).

Utskilt fra page_analyse_sb.py. Funksjonene tar `page` som første argument
og page_analyse_sb re-eksporterer dem for bakoverkompatibilitet.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import formatting

from analyse_sb_refresh import _clear_tree


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
