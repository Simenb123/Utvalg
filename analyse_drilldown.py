"""analyse_drilldown.py -- RL-drilldown og bilagsdrilldown for Analyse.

Ekstrahert fra page_analyse.py.
Alle funksjoner tar ``page`` som første parameter (AnalysePage-instansen).
"""
from __future__ import annotations

from typing import Any, List, Optional

import pandas as pd


def restore_rl_pivot_selection(page: Any, regnr_values: List[int]) -> None:
    """Velg rader i pivot-treet som matcher gitte regnr-verdier."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    wanted: set[int] = set()
    for value in regnr_values:
        try:
            wanted.add(int(value))
        except Exception:
            continue
    if not wanted:
        return

    items_to_select = []
    try:
        items = tree.get_children("")
    except Exception:
        items = ()

    for item in items:
        try:
            regnr = int(str(tree.set(item, "Konto") or "").strip())
        except Exception:
            continue
        if regnr in wanted:
            items_to_select.append(item)

    if not items_to_select:
        return

    try:
        tree.selection_set(items_to_select)
    except Exception:
        pass

    first = items_to_select[0]
    try:
        tree.focus(first)
    except Exception:
        pass
    try:
        tree.see(first)
    except Exception:
        pass


def reload_rl_drilldown_df(page: Any, regnr_filter: List[int]) -> pd.DataFrame:
    """Last på nytt RL-drilldown DataFrame for gitte regnr-filter."""
    cols = ["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]

    try:
        import page_analyse_rl
    except Exception:
        return pd.DataFrame(columns=cols)

    try:
        page._refresh_pivot()
    except Exception:
        pass
    restore_rl_pivot_selection(page, regnr_filter)
    try:
        page._refresh_transactions_view()
    except Exception:
        pass

    df_filtered = getattr(page, "_df_filtered", None)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    try:
        sb_df = page._get_effective_sb_df()
    except Exception:
        sb_df = getattr(page, "_rl_sb_df", None)

    if not isinstance(df_filtered, pd.DataFrame) or intervals is None or regnskapslinjer is None:
        return pd.DataFrame(columns=cols)

    try:
        account_overrides = page_analyse_rl._load_current_client_account_overrides()
    except Exception:
        account_overrides = None

    try:
        return page_analyse_rl.build_rl_account_drilldown(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=sb_df,
            regnr_filter=regnr_filter,
            account_overrides=account_overrides,
        )
    except Exception:
        return pd.DataFrame(columns=cols)


def open_rl_drilldown_from_pivot_selection(
    page: Any,
    *,
    messagebox: Any = None,
    session: Any = None,
    _open_rl_account_drilldown: Any = None,
) -> None:
    """Åpne RL-drilldown popup basert på valg i pivot-treet."""
    agg_mode = ""
    try:
        agg_mode = str(page._var_aggregering.get()) if page._var_aggregering is not None else ""
    except Exception:
        agg_mode = ""

    if agg_mode != "Regnskapslinje":
        return

    if getattr(page, "_detail_accounts_tree", None) is not None:
        try:
            if page._focus_detail_panel():
                return
        except Exception:
            pass

    try:
        import page_analyse_rl
        drill_df, selected_rows = page_analyse_rl.build_selected_rl_account_drilldown(page=page)
    except Exception:
        drill_df = None
        selected_rows = []

    if drill_df is None or drill_df.empty:
        if messagebox is not None:
            try:
                messagebox.showinfo("RL-drilldown", "Velg minst én regnskapslinje med kontoer i scope.")
            except Exception:
                pass
        return

    if _open_rl_account_drilldown is None:
        if messagebox is not None:
            try:
                messagebox.showerror("RL-drilldown", "RL-drilldown er ikke tilgjengelig (mangler GUI-støtte).")
            except Exception:
                pass
        return

    if len(selected_rows) == 1:
        regnr, navn = selected_rows[0]
        title = f"RL-drilldown: {regnr} {navn}".strip()
    else:
        title = f"RL-drilldown: {len(selected_rows)} regnskapslinjer"

    regnr_filter = [regnr for regnr, _ in selected_rows]

    def _reload_callback() -> pd.DataFrame:
        return page._reload_rl_drilldown_df(regnr_filter)

    try:
        _open_rl_account_drilldown(
            page,
            drill_df,
            title=title,
            client=getattr(session, "client", None),
            regnskapslinjer=getattr(page, "_rl_regnskapslinjer", None),
            reload_callback=_reload_callback,
        )
    except Exception as exc:
        if messagebox is not None:
            try:
                messagebox.showerror("RL-drilldown", f"Kunne ikke åpne RL-drilldown.\n\n{exc}")
            except Exception:
                pass


def refresh_nokkeltall_view(page: Any) -> None:
    """Beregn og vis nøkkeltall inline i _nk_text-widgeten."""
    nk_text = getattr(page, "_nk_text", None)
    if nk_text is None:
        return

    try:
        import nokkeltall_engine
    except Exception:
        return

    try:
        import page_analyse_export
    except Exception:
        return

    # Hent rl_df via eksisterende eksport-logikk
    try:
        payload = page_analyse_export.prepare_regnskapsoppstilling_export_data(page=page)
    except Exception:
        payload = {}
    rl_df = payload.get("rl_df")
    if not isinstance(rl_df, pd.DataFrame) or rl_df.empty:
        try:
            from page_analyse import _nk_write
            _nk_write(nk_text, "Ingen regnskapsdata tilgjengelig.\n\nLast inn HB-data og velg klient.")
        except Exception:
            pass
        return

    # Legg til fjorårskolonner hvis tilgjengelig
    pivot_df = getattr(page, "_pivot_df_last", None)
    if isinstance(pivot_df, pd.DataFrame) and "UB_fjor" in pivot_df.columns:
        rl_df = rl_df.copy()
        for col in ("UB_fjor", "Endring_fjor", "Endring_pct"):
            if col in pivot_df.columns and col not in rl_df.columns:
                merged = pivot_df[["regnr", col]].drop_duplicates(subset=["regnr"])
                rl_df = rl_df.merge(merged, on="regnr", how="left")

    client = str(payload.get("client") or "").strip()
    year = str(payload.get("year") or "").strip()

    try:
        result = nokkeltall_engine.compute_nokkeltall(rl_df, client=client, year=year)
    except Exception as exc:
        try:
            from page_analyse import _nk_write
            _nk_write(nk_text, f"Feil ved beregning av nøkkeltall:\n{exc}")
        except Exception:
            pass
        return

    brreg = getattr(page, "_nk_brreg_data", None)
    try:
        from page_analyse import _nk_render
        _nk_render(nk_text, result, brreg_data=brreg)
    except Exception:
        pass
