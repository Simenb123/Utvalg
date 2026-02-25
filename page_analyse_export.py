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

from typing import Any, Dict

import pandas as pd

import analyse_viewdata
from analyse_model import build_pivot_by_account


def prepare_transactions_export_sheets(*, page: Any) -> Dict[str, pd.DataFrame]:
    """Bygger ark-map for eksport av transaksjoner.

    - Valgfritt: begrenser til valgte kontoer
    - Slår sammen kunde-kolonner til en felles kolonne: "Kunder"
    - Parser dato robust for blandede formater (norsk + ISO) uten FutureWarning
    """
    df = getattr(page, "_df_filtered", None)
    if df is None or getattr(df, "empty", True):
        return {"Transaksjoner": pd.DataFrame()}

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

    return {"Transaksjoner": out}


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
