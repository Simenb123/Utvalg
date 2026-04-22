"""page_analyse_export.py

Eksport-hjelpere for Analyse-fanen.

Flyttet ut av page_analyse.py for å holde GUI-filen kort.

Inneholder:
- bygging av ark-map for eksport av transaksjoner
- bygging av ark-map for eksport av pivot pr. konto

NB: Denne modulen bygger kun data (DataFrame). Selve skrivingen til Excel
ligger i andre moduler (f.eks. controller_export / dataset_export).
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import pandas as pd

import analyse_viewdata
from analyse_model import build_pivot_by_account

log = logging.getLogger(__name__)


def prepare_transactions_export_sheets(*, page: Any) -> Dict[str, pd.DataFrame]:
    """Bygger ark-map for eksport av transaksjoner.

    - Valgfritt: begrenser til valgte kontoer
    - Slår sammen kunde-kolonner til en felles kolonne: "Kunder"
    - Parser dato robust for blandede formater (norsk + ISO) uten FutureWarning
    """
    df = getattr(page, "_df_filtered", None)
    if df is None or getattr(df, "empty", True):
        return {"Hovedbok": pd.DataFrame()}

    out = df.copy()

    # Begrens til valgte kontoer (dersom metoden finnes)
    try:
        selected_accounts = list(page._get_selected_accounts())
    except Exception:
        selected_accounts = []

    if selected_accounts and "Konto" in out.columns:
        selected_accounts_s = {str(x) for x in selected_accounts}
        out = out[out["Konto"].astype(str).isin(selected_accounts_s)].copy()

    # Kunder: slå sammen "Kundenavn" og "Kunde" -> "Kunder"
    def _clean_customer(s: pd.Series) -> pd.Series:
        s = s.fillna("").astype("string").str.strip()
        return s.replace({"nan": ""})

    if any(c in out.columns for c in ("Kunder", "Kunde", "Kundenavn")):
        if "Kunder" in out.columns:
            kunder = _clean_customer(out["Kunder"])
        else:
            s_name = (
                _clean_customer(out["Kundenavn"])
                if "Kundenavn" in out.columns
                else pd.Series([""] * len(out), index=out.index, dtype="string")
            )
            s_kunde = (
                _clean_customer(out["Kunde"])
                if "Kunde" in out.columns
                else pd.Series([""] * len(out), index=out.index, dtype="string")
            )
            # Preferer kundenavn hvis tilgjengelig, ellers kunde
            kunder = s_name.where(s_name != "", s_kunde)
        out["Kunder"] = kunder

        drop_cols = [c for c in ("Kundenavn", "Kunde") if c in out.columns]
        if drop_cols:
            out = out.drop(columns=drop_cols)

    # Dato: robust parsing for blandede formater (dd.mm.yyyy + yyyy-mm-dd)
    if "Dato" in out.columns:
        ser = out["Dato"]
        ser_str = ser.astype("string").fillna("").str.strip()

        # Pre-alloker strengkolonne
        out_dato = pd.Series([""] * len(out), index=out.index, dtype="object")

        mask_no = ser_str.str.match(r"^\d{2}\.\d{2}\.\d{4}$")
        if mask_no.any():
            dt_no = pd.to_datetime(ser_str[mask_no], format="%d.%m.%Y", errors="coerce")
            out_dato.loc[mask_no] = dt_no.dt.strftime("%d.%m.%Y").fillna("")

        mask_iso = ser_str.str.match(r"^\d{4}-\d{2}-\d{2}$")
        if mask_iso.any():
            dt_iso = pd.to_datetime(ser_str[mask_iso], format="%Y-%m-%d", errors="coerce")
            out_dato.loc[mask_iso] = dt_iso.dt.strftime("%d.%m.%Y").fillna("")

        # Fallback for andre formater: forsøk pandas-parser, men unngå FutureWarning
        mask_rest = (~mask_no) & (~mask_iso) & (ser_str != "")
        if mask_rest.any():
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", category=FutureWarning)
                dt_rest = pd.to_datetime(ser_str[mask_rest], errors="coerce", dayfirst=True)

            formatted = dt_rest.dt.strftime("%d.%m.%Y")
            # Behold original hvis vi ikke klarer å parse
            out_dato.loc[mask_rest] = formatted.fillna(ser_str[mask_rest])

        out["Dato"] = out_dato

    # Max rader
    try:
        max_rows = int(getattr(page, "_var_max_rows").get())
    except Exception:
        max_rows = 200

    if max_rows > 0 and len(out) > max_rows:
        out = out.head(max_rows).copy()

    return {"Hovedbok": out}


def prepare_pivot_export_sheets(*, page: Any) -> Dict[str, pd.DataFrame]:
    """Bygger ark-map for eksport av pivot-tabellen.

    Dersom siste pivot allerede er beregnet (_pivot_df_last), brukes den.
    Ellers bygges den fra _df_filtered.
    """
    pivot_df = getattr(page, "_pivot_df_last", None)

    if pivot_df is None or getattr(pivot_df, "empty", True):
        df_filtered = getattr(page, "_df_filtered", pd.DataFrame())
        if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty:
            pivot_df = build_pivot_by_account(df_filtered)
        else:
            pivot_df = pd.DataFrame()

    sheet_name = getattr(analyse_viewdata, "SHEET_PIVOT", "Pivot pr konto")
    return {sheet_name: pivot_df}


def prepare_regnskapsoppstilling_export_data(*, page: Any) -> dict[str, Any]:
    """Bygg eksportgrunnlag for RL-regnskapsoppstilling.

    Returnerer både RL-pivoten og et transaksjonsgrunnlag som kan legges i
    eget ark i Excel-eksporten.
    """

    try:
        import session
    except Exception:  # pragma: no cover
        session = None  # type: ignore

    try:
        import page_analyse_rl
    except Exception:
        return {
            "rl_df": pd.DataFrame(),
            "regnskapslinjer": None,
            "transactions_df": pd.DataFrame(),
            "sb_df": pd.DataFrame(),
            "intervals": None,
            "account_overrides": None,
            "client": getattr(session, "client", None) if session is not None else None,
            "year": getattr(session, "year", None) if session is not None else None,
        }

    df_filtered = getattr(page, "_df_filtered", None)
    intervals = getattr(page, "_rl_intervals", None)
    regnskapslinjer = getattr(page, "_rl_regnskapslinjer", None)

    # Bruk samme SB-visning som UI-en (respekterer "Inkluder ÅO"-toggle).
    # NB: _resolve_analysis_sb_views er keyword-only (def f(*, page)),
    # så dette må kalles med page=page — ikke positional.
    try:
        _, _, sb_df = page_analyse_rl._resolve_analysis_sb_views(page=page)
    except Exception as exc:
        log.warning(
            "prepare_regnskapsoppstilling_export_data: _resolve_analysis_sb_views feilet, "
            "faller tilbake til base SB uten ÅO-justering: %s", exc, exc_info=True,
        )
        sb_df = getattr(page, "_rl_sb_df", None)

    try:
        account_overrides = page_analyse_rl._load_current_client_account_overrides()
    except Exception:
        account_overrides = None

    # Last fjorårs-SB hvis tilgjengelig — sendes til build_rl_pivot så rl_df
    # alltid får UB_fjor/Endring_fjor uavhengig av om Analyse-fanen står i
    # Regnskapslinje-modus. Tidligere ble fjor merget inn fra _pivot_df_last
    # i page_regnskap.py, men det feilet stille når brukeren stod i HB-/SB-
    # konto-modus (da har _pivot_df_last "Konto", ikke "regnr").
    sb_prev_df = None
    try:
        sb_prev_df = page_analyse_rl.ensure_sb_prev_loaded(page=page)
    except Exception as exc:
        log.debug("prepare_regnskapsoppstilling_export_data: ensure_sb_prev_loaded feilet: %s", exc)

    prior_year_overrides = None
    try:
        import regnskap_client_overrides as _rco
        client_name = getattr(session, "client", None) if session is not None else None
        active_year = getattr(session, "year", None) if session is not None else None
        if client_name and active_year is not None:
            prior_year_overrides = _rco.load_prior_year_overrides(client_name, str(active_year))
    except Exception as exc:
        log.debug("prepare_regnskapsoppstilling_export_data: prior_year_overrides feilet: %s", exc)

    if not isinstance(df_filtered, pd.DataFrame) or df_filtered.empty or intervals is None or regnskapslinjer is None:
        rl_df = pd.DataFrame()
    else:
        try:
            rl_df = page_analyse_rl.build_rl_pivot(
                df_filtered,
                intervals,
                regnskapslinjer,
                sb_df=sb_df,
                sb_prev_df=sb_prev_df,
                account_overrides=account_overrides,
                prior_year_overrides=prior_year_overrides,
            )
        except Exception:
            rl_df = pd.DataFrame()

    tx_df = pd.DataFrame()
    if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty:
        tx_cols = tuple(getattr(page, "TX_COLS", analyse_viewdata.DEFAULT_TX_COLS))
        try:
            selected_accounts = list(page._get_selected_accounts())
        except Exception:
            selected_accounts = []

        if selected_accounts:
            tx_sheets = analyse_viewdata.prepare_transactions_export_sheets(
                df_filtered,
                selected_accounts,
                max_rows=max(len(df_filtered.index), 1),
                tx_cols=tx_cols,
            )
            tx_df = tx_sheets.get(analyse_viewdata.SHEET_TX_ALL)
            if tx_df is None or getattr(tx_df, "empty", True):
                tx_df = tx_sheets.get(analyse_viewdata.SHEET_TX)
            if tx_df is None or getattr(tx_df, "empty", True):
                tx_df = tx_sheets.get(analyse_viewdata.SHEET_TX_SHOWN)
            if tx_df is None:
                tx_df = pd.DataFrame()
        else:
            tx_df = analyse_viewdata.build_transactions_view_df(df_filtered, tx_cols=tx_cols)

    reskontro_df = (df_filtered
                    if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty
                    else pd.DataFrame())

    df_hb_full = (df_filtered
                  if isinstance(df_filtered, pd.DataFrame) and not df_filtered.empty
                  else pd.DataFrame())

    return {
        "rl_df": rl_df if isinstance(rl_df, pd.DataFrame) else pd.DataFrame(),
        "regnskapslinjer": regnskapslinjer,
        "transactions_df": tx_df if isinstance(tx_df, pd.DataFrame) else pd.DataFrame(),
        "df_hb": df_hb_full,
        "reskontro_df": reskontro_df,
        "sb_df": sb_df if isinstance(sb_df, pd.DataFrame) else pd.DataFrame(),
        "intervals": intervals,
        "account_overrides": account_overrides,
        "client": getattr(session, "client", None) if session is not None else None,
        "year": getattr(session, "year", None) if session is not None else None,
    }
