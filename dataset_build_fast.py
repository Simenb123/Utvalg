# -*- coding: utf-8 -*-
"""
dataset_build_fast.py – R13 patch
Hurtig og robust innlesing + standardisering av datasett.
Denne versjonen utvider standard R12f ved å sikre at Konto og Bilag
behandles som tekstfelt, slik at de ikke formateres med tusenskiller eller
desimaler i GUI. I tillegg fjernes eventuelle ".0" som pandas legger til
ved automatisk konvertering av heltall til float.

- Bruker 'usecols' når mapping er kjent for å lese kun nødvendige kolonner.
- Robust norsk/internasjonal parsing av beløp og dato.
"""
from __future__ import annotations
from typing import Optional, List, Dict
import os
import pandas as pd
import numpy as np

from ml_map_utils import apply_mapping, canonical_fields

def _to_float_no(series: pd.Series) -> pd.Series:
    if series is None or len(series) == 0:
        return pd.Series([], dtype="float64")
    # Hvis kolonnen allerede er numerisk, konverter direkte til float
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    # Fjern non-breaking space og mellomrom
    s = series.astype(str).str.strip().str.replace("\u00a0", " ", regex=False)
    s = s.str.replace(" ", "", regex=False)
    # Hvis det er flere komma enn punktum, anta at komma er desimal
    comma_more = s.str.count(",") > s.str.count(".")
    s = s.where(~comma_more, s.str.replace(",", ".", regex=False))
    # Erstatt komma med punkt for å kunne parse
    s = s.str.replace(",", ".", regex=False)
    # Fjern andre tegn enn 0-9, punktum og minus
    s = s.str.replace(r"[^0-9\.\-]", "", regex=True)
    return pd.to_numeric(s, errors="coerce")

def _to_date_no(series: pd.Series) -> pd.Series:
    if series is None or len(series) == 0:
        return pd.to_datetime(pd.Series([], dtype="object"), errors="coerce")
    return pd.to_datetime(series, dayfirst=True, errors="coerce")

def _read_with_usecols(path: str, usecols: Optional[List[str]] = None) -> pd.DataFrame:
    ext = os.path.splitext(path)[1].lower()
    # SAF-T (.xml/.zip) -> extract to canonical CSV and reuse the normal CSV pipeline
    if ext in (".xml", ".zip"):
        from saft_importer import ensure_general_ledger_csv
        extracted = ensure_general_ledger_csv(path)
        return _read_with_usecols(str(extracted), usecols=usecols)
    if ext in (".xlsx", ".xlsm", ".xltx", ".xltm", ".xls"):
        try:
            return pd.read_excel(path, engine="openpyxl", usecols=usecols)
        except Exception:
            df = pd.read_excel(path, engine="openpyxl")
            return df.loc[:, [c for c in (usecols or []) if c in df.columns]]
    # CSV
    try:
        return pd.read_csv(path, sep=None, engine="python", usecols=usecols)
    except Exception:
        try:
            return pd.read_csv(path, sep=";", engine="python", usecols=usecols, encoding="utf-8")
        except Exception:
            df = pd.read_csv(path, sep=None, engine="python")
            return df.loc[:, [c for c in (usecols or []) if c in df.columns]]

def build_from_file(path: str, mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Leser filen raskt og returnerer et standardisert DataFrame med kanoniske
    kolonnenavn. mapping er et oppslag {Canon: SourceCol}. Hvis det er None
    leser vi alle kolonner, ellers bruker vi usecols for raskere innlesing.

    Denne funksjonen konverterer Beløp til numerisk og Dato til datetime
    (best-effort). Konto og Bilag konverteres til tekst og blanke rader fjernes.
    """
    usecols = list(mapping.values()) if isinstance(mapping, dict) else None
    df = _read_with_usecols(path, usecols=usecols)

    # Anvend mapping hvis kjent
    if isinstance(mapping, dict):
        df = apply_mapping(df, mapping)

    # Konverter felt (best-effort)
    if "Beløp" in df.columns:
        df["Beløp"] = _to_float_no(df["Beløp"])
    if "Dato" in df.columns:
        df["Dato"] = _to_date_no(df["Dato"])

    # Rydd opp og sørg for at Konto og Bilag behandles som tekst. Hvis de er
    # numeriske (f.eks. float), vil pandas vise dem med desimaler og
    # tusenskiller i GUI. Konverter derfor til str og fjern ".0" til slutt.
    if "Konto" in df.columns:
        try:
            df["Konto"] = df["Konto"].astype(str).str.replace(r"\.0$", "", regex=True)
        except Exception:
            df["Konto"] = df["Konto"].astype(str)
        df = df[df["Konto"].astype(str).str.strip().ne("")]
    if "Bilag" in df.columns:
        try:
            df["Bilag"] = df["Bilag"].astype(str).str.replace(r"\.0$", "", regex=True)
        except Exception:
            df["Bilag"] = df["Bilag"].astype(str)
        df = df[df["Bilag"].astype(str).str.strip().ne("")]

    # Sørg for definert kolonnerekkefølge: Kanoniske kolonner først, deretter resten
    CANON = canonical_fields()
    cols = [c for c in CANON if c in df.columns] + [c for c in df.columns if c not in CANON]
    return df.loc[:, cols]