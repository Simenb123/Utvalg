# -*- coding: utf-8 -*-
"""
analyse_model.py

Dette modul innholder ren datalogi for analysefanen. Ved å trekke
ut pivot‑ og filtreringsfunksjonene fra GUI‑koden kan vi teste dem
uavhengig av Tkinter. Funksjonene tar inn en pandas DataFrame og
returnerer DataFrames eller dictionaries med aggregerte resultater.

Funksjonene her er en forenklet versjon av logikken som finnes i
originalprosjektet Utvalg. Vi håndterer bare pivot per konto og en
enkel oppsummering av kolonne "Beløp" og telling av "Bilag". Flere felt
kan legges til etter behov.

NB: build_pivot_by_account sørger for at gruppenøkler (Konto og
Kontonavn) alltid er kolonner i resultatet, ikke indeks. Dette gjør
det enklere å iterere over rader i testene.
"""

from __future__ import annotations

from typing import Dict, Any, Iterable, List

import pandas as pd


def build_pivot_by_account(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bygg en enkel pivot per konto og kontonavn.

    - Grupper alltid på kolonnen "Konto" dersom den finnes.
    - Hvis kolonnen "Kontonavn" finnes, grupper også på denne.
    - Summér kolonnen "Beløp" (om den finnes) og tell antall oppføringer
      av kolonnen "Bilag" (om den finnes).

    Parametre:
        df: DataFrame med transaksjoner. Forventes at kolonnene er mappet
            til kanoniske navn (Konto, Kontonavn, Beløp, Bilag, osv.).

    Returnerer:
        Et DataFrame med gruppenøkler og aggregerte kolonner.
    """
    if df is None or df.empty or "Konto" not in df.columns:
        # Ingen konto å gruppere på
        return pd.DataFrame()

    # Definer gruppekriterier
    group_cols: List[str] = ["Konto"]
    if "Kontonavn" in df.columns:
        group_cols.append("Kontonavn")

    # Definer aggregasjoner
    agg: Dict[str, str] = {}
    if "Beløp" in df.columns:
        agg["Beløp"] = "sum"
    if "Bilag" in df.columns:
        agg["Bilag"] = "count"

    if not agg:
        # Ingen numeriske kolonner å aggregere, returner unike kombinasjoner
        return df[group_cols].drop_duplicates().reset_index(drop=True)

    # Utfør gruppering og aggregering. dropna=False gjør at NaN ikke
    # filtreres bort i gruppekriteriene
    pivot = (
        df.groupby(group_cols, dropna=False)
        .agg(agg)
        .reset_index()
    )

    # Gi mer beskrivende navn på aggregerte kolonner
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

    Hvis datasettet er tomt eller None, returneres nullverdier.
    """
    summary: Dict[str, Any] = {
        "rows": int(df.shape[0] if df is not None else 0),
        "sum_amount": None,
        "min_date": None,
        "max_date": None,
    }
    if df is None or df.empty:
        return summary

    # Summer beløp hvis kolonnen finnes
    if "Beløp" in df.columns:
        # Bruk to_numeric for å håndtere strenger med tall og ignorer ikke‑numeriske verdier
        summary["sum_amount"] = float(
            pd.to_numeric(df["Beløp"], errors="coerce").fillna(0).sum()
        )

    # Hent dato-statistikk
    if "Dato" in df.columns:
        # Konverter strenger til datetime; dayfirst=True håndterer norsk datoformat dd.mm.yyyy
        dates = pd.to_datetime(df["Dato"], errors="coerce", dayfirst=True)
        dates = dates.dropna()
        if not dates.empty:
            summary["min_date"] = dates.min()
            summary["max_date"] = dates.max()

    return summary


def filter_by_accounts(df: pd.DataFrame, accounts: Iterable[Any]) -> pd.DataFrame:
    """
    Filtrer datarammen på en liste av kontoer.

    Hvis df er None eller ikke inneholder kolonnen "Konto", returneres den
    opprinnelige datarammen uendret.

    Parametre:
        df: DataFrame med transaksjoner.
        accounts: En iterable av kontonumre (kan være tall eller strenger).

    Returnerer:
        En kopi av df som bare inneholder rader der "Konto" stemmer med
        en av verdiene i accounts. Hvis accounts er tom, returneres df.
    """
    if df is None or "Konto" not in df.columns:
        return df
    # Normaliser kontonumre til strenger for sammenligning
    acc_list = [str(a) for a in accounts]
    if not acc_list:
        return df
    mask = df["Konto"].astype(str).isin(acc_list)
    return df[mask].copy()
