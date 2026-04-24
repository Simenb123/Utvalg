"""page_analyse_transactions.py

Transaksjonslisten (høyre panel) for Analyse-fanen.

Inneholder:
- oppdatering av transaksjons-treeview basert på valgt(e) konto(er)
- bygging av oppsummeringstekst (viste rader vs total scope)
- uthenting av valgt bilag fra listen

Flyttet ut av page_analyse.py for bedre moduldeling.
"""

from __future__ import annotations

from typing import Any

import math

import pandas as pd

import analyse_viewdata
import formatting


def _set_summary_text(*, page: Any, lbl: Any, base_text: str) -> None:
    text = base_text

    agg_mode = ""
    try:
        agg_var = getattr(page, "_var_aggregering", None)
        agg_mode = str(agg_var.get()) if agg_var is not None else ""
    except Exception:
        agg_mode = ""

    try:
        warning = str(getattr(page, "_rl_mapping_warning", "") or "").strip()
    except Exception:
        warning = ""

    if agg_mode == "Regnskapslinje" and warning:
        text = f"{text} | {warning}"

    try:
        lbl.config(text=text)
    except Exception:
        pass


def refresh_transactions_view(*, page: Any) -> None:
    """Oppdater transaksjonslisten basert på valgte kontoer i pivot."""
    tx_tree = getattr(page, "_tx_tree", None)
    lbl = getattr(page, "_lbl_tx_summary", None)

    if tx_tree is None or lbl is None:
        return

    try:
        page._clear_tree(tx_tree)
    except Exception:
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    if df_filtered is None or not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty:
        _set_summary_text(page=page, lbl=lbl, base_text="Oppsummering: (ingen rader)")
        return

    # Hent valgte kontoer
    try:
        sel_accounts = page._get_selected_accounts()
    except Exception:
        sel_accounts = []

    try:
        import page_analyse_detail_panel

        sel_accounts = page_analyse_detail_panel.selected_transaction_accounts(page, list(sel_accounts))
    except Exception:
        sel_accounts = list(sel_accounts)

    if not sel_accounts:
        _set_summary_text(page=page, lbl=lbl, base_text="Oppsummering: (ingen rader)")
        return

    if "Konto" not in df_filtered.columns:
        _set_summary_text(page=page, lbl=lbl, base_text="Oppsummering: (mangler Konto-kolonne)")
        return

    # Display subset
    try:
        max_rows = int(getattr(page, "_var_max_rows").get() or 200)
    except Exception:
        max_rows = 200
    if max_rows <= 0:
        max_rows = 200

    df_sel_all, df_show = analyse_viewdata.compute_selected_transactions(
        df_filtered, sel_accounts, max_rows=max_rows
    )

    # Totals for full selection
    bel_all = pd.to_numeric(df_sel_all.get("Beløp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    total_rows = len(df_sel_all)
    total_sum = float(bel_all.sum())

    shown_rows = len(df_show)
    bel_show = pd.to_numeric(df_show.get("Beløp", pd.Series(dtype=float)), errors="coerce").fillna(0.0)
    shown_sum = float(bel_show.sum())

    if total_rows == shown_rows:
        _set_summary_text(
            page=page,
            lbl=lbl,
            base_text=f"Oppsummering: {total_rows} rader | Sum: {formatting.fmt_amount(total_sum)}",
        )
    else:
        _set_summary_text(
            page=page,
            lbl=lbl,
            base_text=(
                f"Oppsummering: {shown_rows} av {total_rows} rader | "
                f"Sum: {formatting.fmt_amount(shown_sum)} (totalt {formatting.fmt_amount(total_sum)})"
            ),
        )

    tx_cols = list(getattr(page, "TX_COLS", analyse_viewdata.DEFAULT_TX_COLS))

    # Bygg visnings-DF med kanoniske kolonner + ryddige strenger
    df_show_view = analyse_viewdata.build_transactions_view_df(df_show, tx_cols=tx_cols)

    amount_cols = {"Beløp", "MVA-beløp", "Valutabeløp", "MVA-belop", "Valutabelop", "Debet", "Kredit"}
    percent_cols = {"MVA-prosent"}

    # Desimal-toggle: deler state med pivot og SB-visningen (_var_decimals).
    # Når av → avrundete heltall; når på → 2 desimaler som fmt_amount default.
    _use_decimals = True
    try:
        _vd = getattr(page, "_var_decimals", None)
        if _vd is not None:
            _use_decimals = bool(_vd.get())
    except Exception:
        pass
    _amount_decimals = 2 if _use_decimals else 0

    def _fmt_cell(col: str, val: object) -> str:
        """Formatter én celle basert på kolonnenavn.

        - Beløpskolonner: norsk tallformat (tusenskille + komma); desimal-
          visning styres av ``page._var_decimals``.
        - Prosentkolonner: vis 0.25 som 25, og bruk 0 desimaler hvis heltall
        - Ellers: str(val) med None -> ""
        """
        if val is None:
            return ""
        if col in amount_cols:
            return formatting.fmt_amount(val, decimals=_amount_decimals)
        if col in percent_cols:
            try:
                v = float(val)
            except Exception:
                return str(val)
            if not math.isfinite(v):
                return ""
            if 0 < v <= 1:
                v = v * 100.0
            dec = 0 if abs(v - round(v)) < 1e-9 else 2
            return formatting.format_number_no(v, decimals=dec)
        return str(val)

    # Bruk itertuples(name=None) for å unngå problemer med kolonnenavn som ikke er gyldige Python-identifikatorer
    cols = list(df_show_view.columns)
    idx_belop = cols.index("Beløp") if "Beløp" in cols else None

    for row in df_show_view.itertuples(index=False, name=None):
        belop_val = row[idx_belop] if idx_belop is not None else 0.0

        tags = ()
        try:
            if float(belop_val) < 0:
                tags = ("neg",)
        except Exception:
            pass

        try:
            values = tuple(_fmt_cell(c, v) for c, v in zip(cols, row))
            tx_tree.insert("", "end", values=values, tags=tags)
        except Exception:
            continue

    maybe_auto_fit = getattr(page, "_maybe_auto_fit_tx_tree", None)
    if callable(maybe_auto_fit):
        try:
            maybe_auto_fit()
        except Exception:
            pass



def get_selected_bilag_from_tx_tree(*, page: Any) -> str:
    """Hent valgt bilag fra transaksjonslisten (TX tree)."""
    tx_tree = getattr(page, "_tx_tree", None)
    if tx_tree is None:
        return ""

    try:
        sel = tx_tree.selection()
    except Exception:
        sel = ()

    if not sel:
        return ""

    item = sel[0]

    bilag = ""
    # Prefer Treeview-set på kolonnenavn
    try:
        bilag = str(tx_tree.set(item, "Bilag") or "")
    except Exception:
        bilag = ""

    if not bilag:
        try:
            values = list(tx_tree.item(item).get("values") or [])
            if values:
                cols = list(getattr(page, "TX_COLS", ()) or ())
                try:
                    idx = cols.index("Bilag")
                except ValueError:
                    idx = 0
                if 0 <= idx < len(values):
                    bilag = str(values[idx])
                else:
                    bilag = str(values[0])
        except Exception:
            bilag = ""

    return str(bilag).strip()
