"""page_analyse_rl_drilldown.py

Drilldown-data for valgte regnskapslinjer: fra RL-seleksjon i pivot_tree
til konto-drilldown, transaksjoner og detaljkontekst.

Utskilt fra page_analyse_rl.py. Re-eksportert via page_analyse_rl som
fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

import pandas as pd

import formatting

from page_analyse_rl_data import (
    _load_current_client_account_overrides,
    _resolve_analysis_sb_views,
    _resolve_regnr_for_accounts,
)

log = logging.getLogger("app")


def _expand_selected_regnskapslinjer(
    regnskapslinjer: Optional[pd.DataFrame],
    regnr_values: List[int],
) -> List[int]:
    if not regnr_values:
        return []
    if regnskapslinjer is None or regnskapslinjer.empty:
        return regnr_values

    try:
        from regnskap_mapping import expand_regnskapslinje_selection
        return expand_regnskapslinje_selection(
            regnskapslinjer=regnskapslinjer,
            selected_regnr=regnr_values,
        )
    except Exception as exc:
        log.warning("Kunne ikke utvide regnskapslinjevalg: %s", exc)
        return regnr_values


def get_selected_rl_rows(*, page: Any) -> List[tuple[int, str]]:
    """Returner valgte regnskapslinjer fra pivoten som (regnr, navn)."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

    try:
        selected = list(tree.selection())
    except Exception:
        selected = []

    if not selected:
        try:
            focused = tree.focus()
        except Exception:
            focused = ""
        if focused:
            selected = [focused]

    rows: List[tuple[int, str]] = []
    for item in selected:
        try:
            regnr = int(str(tree.set(item, "Konto") or "").strip())
        except Exception:
            continue
        try:
            navn = str(tree.set(item, "Kontonavn") or "").strip()
        except Exception:
            navn = ""
        rows.append((regnr, navn))
    return rows


def build_rl_account_drilldown(
    df_hb: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    sb_df: Optional[pd.DataFrame] = None,
    regnr_filter: Optional[List[int]] = None,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Bygg kontooversikt under valgt(e) regnskapslinjer."""
    from regnskap_mapping import normalize_regnskapslinjer

    if df_hb is None or df_hb.empty or "Konto" not in df_hb.columns:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    work = pd.DataFrame()
    work["konto"] = df_hb["Konto"].astype(str)
    if "Kontonavn" in df_hb.columns:
        work["kontonavn"] = df_hb["Kontonavn"].fillna("").astype(str)
    else:
        work["kontonavn"] = ""
    work["_cnt"] = 1
    if "Beløp" in df_hb.columns:
        work["_hb_sum"] = pd.to_numeric(df_hb["Beløp"], errors="coerce").fillna(0.0)
    else:
        work["_hb_sum"] = 0.0

    konto_agg = (
        work.groupby(["konto", "kontonavn"], as_index=False)
        .agg(Antall=("_cnt", "sum"), HB_sum=("_hb_sum", "sum"))
    )

    try:
        regnr_lookup = _resolve_regnr_for_accounts(
            konto_agg["konto"].astype(str).tolist(),
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
        mapped = konto_agg.merge(regnr_lookup, on="konto", how="left")
        regn = normalize_regnskapslinjer(regnskapslinjer)
    except Exception as exc:
        log.warning("build_rl_account_drilldown: %s", exc)
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    expanded_regnr = _expand_selected_regnskapslinjer(regnskapslinjer, regnr_filter or [])

    if expanded_regnr:
        mapped = mapped.loc[mapped["regnr"].isin(expanded_regnr)].copy()
    else:
        mapped = mapped.loc[mapped["regnr"].notna()].copy()

    if mapped.empty:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    rl_names = regn[["regnr", "regnskapslinje"]].copy()
    rl_names["regnr"] = rl_names["regnr"].astype(int)
    mapped["regnr"] = mapped["regnr"].astype(int)
    mapped = mapped.merge(rl_names, how="left", on="regnr")

    if sb_df is not None and not sb_df.empty and "konto" in sb_df.columns:
        sb_work = sb_df.copy()
        sb_work["konto"] = sb_work["konto"].astype(str)
        if "kontonavn" not in sb_work.columns:
            sb_work["kontonavn"] = ""
        sb_work["kontonavn"] = sb_work["kontonavn"].fillna("").astype(str)
        sb_work["ib"] = pd.to_numeric(sb_work.get("ib"), errors="coerce").fillna(0.0)
        sb_work["ub"] = pd.to_numeric(sb_work.get("ub"), errors="coerce").fillna(0.0)
        sb_acc = (
            sb_work.groupby("konto", as_index=False)
            .agg(
                kontonavn_sb=("kontonavn", "first"),
                IB=("ib", "sum"),
                UB=("ub", "sum"),
            )
        )
        out = mapped.merge(sb_acc, how="left", on="konto")
        out["IB"] = out["IB"].fillna(0.0)
        out["UB"] = out["UB"].fillna(0.0)
        out["Endring"] = out["UB"] - out["IB"]
        out["Kontonavn"] = out["kontonavn"].where(out["kontonavn"].astype(str).str.strip() != "", out["kontonavn_sb"])
    else:
        out = mapped.copy()
        out["IB"] = 0.0
        out["UB"] = pd.to_numeric(out["HB_sum"], errors="coerce").fillna(0.0)
        out["Endring"] = out["UB"]
        out["Kontonavn"] = out["kontonavn"]

    out["Kontonavn"] = out["Kontonavn"].fillna("").astype(str)
    out["Antall"] = pd.to_numeric(out["Antall"], errors="coerce").fillna(0).astype(int)
    out["Nr"] = out["regnr"].astype(int)
    out["Regnskapslinje"] = out["regnskapslinje"].fillna("").astype(str)
    out["Konto"] = out["konto"].astype(str)

    out = out.sort_values(["Nr", "Konto"]).reset_index(drop=True)
    return out[["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]]


def build_selected_rl_account_drilldown(*, page: Any) -> tuple[pd.DataFrame, List[tuple[int, str]]]:
    """Bygg drilldown-data for valgte regnskapslinjer i Analyse."""
    selected_rows = get_selected_rl_rows(page=page)
    regnr_filter = [regnr for regnr, _ in selected_rows]

    df_filtered = getattr(page, "_df_filtered", None)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)
    _, _, sb_df = _resolve_analysis_sb_views(page=page)
    account_overrides = _load_current_client_account_overrides()

    if not isinstance(df_filtered, pd.DataFrame) or intervals is None or regnskapslinjer is None:
        return pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"]), selected_rows

    return (
        build_rl_account_drilldown(
            df_filtered,
            intervals,
            regnskapslinjer,
            sb_df=sb_df,
            regnr_filter=regnr_filter,
            account_overrides=account_overrides,
        ),
        selected_rows,
    )


def build_selected_rl_detail_context(*, page: Any) -> dict[str, Any]:
    """Bygg rikere detaljkontekst for valgte regnskapslinjer i Analyse."""
    drill_df, selected_rows = build_selected_rl_account_drilldown(page=page)
    if drill_df is None or not isinstance(drill_df, pd.DataFrame):
        drill_df = pd.DataFrame(columns=["Nr", "Regnskapslinje", "Konto", "Kontonavn", "IB", "Endring", "UB", "Antall"])

    df_filtered = getattr(page, "_df_filtered", None)
    if not isinstance(df_filtered, pd.DataFrame):
        df_filtered = pd.DataFrame()

    selected_accounts = [str(value).strip() for value in drill_df.get("Konto", pd.Series(dtype=str)).astype(str).tolist() if str(value).strip()]
    selected_set = set(selected_accounts)
    if not df_filtered.empty and "Konto" in df_filtered.columns and selected_set:
        tx_df = df_filtered.loc[df_filtered["Konto"].astype(str).str.strip().isin(selected_set)].copy()
    else:
        tx_df = pd.DataFrame(columns=df_filtered.columns if isinstance(df_filtered, pd.DataFrame) else [])

    scope_parts = [f"{int(regnr)} {str(name or '').strip()}".strip() for regnr, name in selected_rows]
    scope_text = ", ".join(scope_parts) if scope_parts else "Ingen regnskapslinje valgt"

    ib_sum = float(pd.to_numeric(drill_df.get("IB", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0
    endring_sum = float(pd.to_numeric(drill_df.get("Endring", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0
    ub_sum = float(pd.to_numeric(drill_df.get("UB", pd.Series(dtype=float)), errors="coerce").fillna(0.0).sum()) if not drill_df.empty else 0.0

    summary = (
        f"Regnskapslinjer: {scope_text} | "
        f"Kontoer: {len(selected_accounts)} | "
        f"Transaksjoner: {len(tx_df.index)} | "
        f"IB: {formatting.fmt_amount(ib_sum)} | "
        f"Endring: {formatting.fmt_amount(endring_sum)} | "
        f"UB: {formatting.fmt_amount(ub_sum)}"
    )

    return {
        "accounts_df": drill_df,
        "summary": summary,
        "selected_rows": selected_rows,
        "selected_accounts": selected_accounts,
        "transactions_df": tx_df,
        "mapping_warning": str(getattr(page, "_rl_mapping_warning", "") or "").strip(),
    }


def get_selected_rl_accounts(*, page: Any) -> List[str]:
    """Returner kontoer (str) tilhørende valgte regnskapslinjer i pivot_tree."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return []

    selected_regnr: List[int] = []
    try:
        selected = tree.selection()
        if not selected:
            selected = tree.get_children()
        for item in selected:
            try:
                regnr_str = tree.set(item, "Konto")
                selected_regnr.append(int(regnr_str))
            except (ValueError, TypeError, Exception):
                pass
    except Exception:
        return []

    if not selected_regnr:
        return []

    intervals = getattr(page, "_rl_intervals", None)
    df_filtered = getattr(page, "_df_filtered", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    if intervals is None or df_filtered is None or not isinstance(df_filtered, pd.DataFrame):
        return []

    if "Konto" not in df_filtered.columns:
        return []

    kontos_in_hb = df_filtered["Konto"].dropna().astype(str).unique().tolist()
    if not kontos_in_hb:
        return []

    expanded_regnr = _expand_selected_regnskapslinjer(regnskapslinjer, selected_regnr)
    if not expanded_regnr:
        return []

    try:
        account_overrides = _load_current_client_account_overrides()
        regnr_lookup = _resolve_regnr_for_accounts(
            kontos_in_hb,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )
        matching = (
            regnr_lookup
            .loc[regnr_lookup["regnr"].isin(expanded_regnr), "konto"]
            .tolist()
        )
        deduped: List[str] = []
        seen: set[str] = set()
        for konto in matching:
            konto_s = str(konto or "").strip()
            if not konto_s or konto_s in seen:
                continue
            deduped.append(konto_s)
            seen.add(konto_s)
        return deduped
    except Exception as exc:
        log.warning("get_selected_rl_accounts: feil ved konto-oppslag: %s", exc)
        return []
