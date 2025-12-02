# -*- coding: utf-8 -*-
"""
analyse_model.py

Denne modulen inneholder ren datalogi for analysefanen. Ved å trekke
ut pivot- og filtreringsfunksjonene fra GUI-koden kan vi teste dem
uavhengig av Tkinter. Funksjonene tar inn en pandas DataFrame og
returnerer DataFrames eller dictionaries med aggregerte resultater.

Funksjonene her er en forenklet versjon av logikken som finnes i
originalprosjektet Utvalg. Vi håndterer bare pivot per konto og en
enkel oppsummering av kolonne "Beløp" og "Bilag". Flere felt kan
legges til etter behov.
"""

from __future__ import annotations

from typing import Dict, Any, List, Iterable

import pandas as pd

def build_pivot_by_account(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bygg en enkel pivot per konto og kontonavn.

    - Grupperer alltid på "Konto".
    - Hvis "Kontonavn" finnes, grupperer også på den.
    - Aggregerer sum av "Beløp" hvis kolonnen finnes, og teller antall
      "Bilag" hvis kolonnen finnes.

    Parametre:
        df: DataFrame med transaksjoner. Forventes at kolonnene er mappet
            til kanoniske navn (Konto, Kontonavn, Beløp, Bilag, osv.).

    Returnerer:
        Et DataFrame med gruppenøkler og aggregerte kolonner.
    """
    if df is None or df.empty or "Konto" not in df.columns:
        # Ingenting å pivotere på
        return pd.DataFrame()

    group_cols: List[str] = ["Konto"]
    if "Kontonavn" in df.columns:
        group_cols.append("Kontonavn")

    agg: Dict[str, str] = {}
    if "Beløp" in df.columns:
        agg["Beløp"] = "sum"
    if "Bilag" in df.columns:
        agg["Bilag"] = "count"

    if not agg:
        # Ingen aggregasjon å gjøre; returner unike kombinasjoner
        return df[group_cols].drop_duplicates().reset_index(drop=True)

    pivot = (
        df.groupby(group_cols, dropna=False)
        .agg(agg)
        .reset_index()
    )

    # Gi hyggeligere kolonnenavn
    rename_map: Dict[str, str] = {}
    if "Beløp" in pivot.columns:
        rename_map["Beløp"] = "Sum beløp"
    if "Bilag" in pivot.columns:
        rename_map["Bilag"] = "Antall bilag"
    if rename_map:
        pivot = pivot.rename(columns=rename_map)
    return pivot

def build_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Lag en enkel oppsummering av datasettet.

    Nøkler i resultatet:
      - rows: antall rader i datasettet
      - sum_amount: sum av kolonnen "Beløp" (hvis finnes)
      - min_date / max_date: min og max av kolonnen "Dato" som pandas
        Timestamp (hvis finnes)
    """
    summary: Dict[str, Any] = {
        "rows": int(df.shape[0] if df is not None else 0),
        "sum_amount": None,
        "min_date": None,
        "max_date": None,
    }
    if df is None or df.empty:
        return summary
    # Sum beløp
    if "Beløp" in df.columns:
        summary["sum_amount"] = float(
            pd.to_numeric(df["Beløp"], errors="coerce").fillna(0).sum()
        )
    # Dato-statistikk
    if "Dato" in df.columns:
        dates = pd.to_datetime(df["Dato"], errors="coerce", dayfirst=True)
        dates = dates.dropna()
        if not dates.empty:
            summary["min_date"] = dates.min()
            summary["max_date"] = dates.max()
    return summary

def filter_by_accounts(df: pd.DataFrame, accounts: Iterable[Any]) -> pd.DataFrame:
    """
    Filtrer datarammen på en liste av kontoer. Hvis "Konto" ikke finnes,
    returneres df uendret.
    """
    if df is None or "Konto" not in df.columns:
        return df
    acc_list = [str(a) for a in accounts]
    if not acc_list:
        return df
    mask = df["Konto"].astype(str).isin(acc_list)
    return df[mask].copy()