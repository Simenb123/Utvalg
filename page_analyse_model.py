"""
page_analyse_model.py

Ren logikk for analysefanen (ingen Tkinter her).

Ansvar:
- Hente gjeldende dataset fra analysis_pkg (der set_dataset() har blitt kalt).
- Bygge enkle summeringer (antall rader, sum beløp, min/max dato).
- Lage en pivot per konto.
- Enkle filterfunksjoner (tekst og konto).

Denne modulen kan testes uavhengig av GUI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


@dataclass
class AnalyseState:
    """Samlet state for analysefanen."""

    df: pd.DataFrame


def _extract_df_from_analysis_pkg() -> pd.DataFrame:
    """
    Hent DataFrame fra analysis_pkg.

    Vi vet fra testene at noen før oss har kalt:
        set_dataset(df, cols)

    Det er ikke 100 % sikkert hva API-et ellers heter, så vi gjør følgende:

    1) Hvis analysis_pkg har en funksjon get_dataset(), prøver vi den først.
       - Hvis den returnerer (df, cols), bruker vi df.
       - Hvis den returnerer df direkte, bruker vi det.

    2) Hvis ikke get_dataset finnes eller gir noe fornuftig, scanner vi
       attributtene i modulen og tar den første verdien som er en DataFrame.
    """
    try:
        import analysis_pkg as ap  # type: ignore[import]
    except Exception:
        # Hvis analysis_pkg ikke kan importeres, har vi uansett ikke noe dataset.
        return pd.DataFrame()

    # 1) Forsøk via get_dataset()
    get_dataset = getattr(ap, "get_dataset", None)
    if callable(get_dataset):
        try:
            result = get_dataset()
        except TypeError:
            # Signaturen stemte ikke – da går vi videre til fallback
            result = None

        if isinstance(result, tuple) and result:
            df_candidate = result[0]
        else:
            df_candidate = result

        if isinstance(df_candidate, pd.DataFrame):
            return df_candidate.copy()

    # 2) Fallback – finn første DataFrame-attributt i modulen
    for _name, value in vars(ap).items():
        if isinstance(value, pd.DataFrame):
            return value.copy()

    # Ingenting funnet
    return pd.DataFrame()


def load_state_from_analysis_pkg() -> AnalyseState:
    """
    Bygg en AnalyseState basert på det som til enhver tid ligger i analysis_pkg.

    Brukes typisk fra GUI-laget (AnalysePage.refresh_from_session()).
    """
    df = _extract_df_from_analysis_pkg()
    return AnalyseState(df=df)


def build_summary(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Lag en enkel oppsummering av populasjonen.

    Nøkler:
      - rows: antall rader
      - sum_amount: sum av kolonnen "Beløp" hvis den finnes
      - min_date / max_date: min/max av kolonnen "Dato" (tolket som dato, dd.mm.yyyy)
    """
    summary: Dict[str, Any] = {
        "rows": int(df.shape[0]),
        "sum_amount": None,
        "min_date": None,
        "max_date": None,
    }

    if "Beløp" in df.columns:
        # Robust mot None/NaN
        summary["sum_amount"] = float(pd.to_numeric(df["Beløp"], errors="coerce").fillna(0).sum())

    if "Dato" in df.columns and not df.empty:
        dates = pd.to_datetime(df["Dato"], errors="coerce", dayfirst=True)
        dates = dates.dropna()
        if not dates.empty:
            summary["min_date"] = dates.min()
            summary["max_date"] = dates.max()

    return summary


def build_pivot_by_account(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lag en enkel pivot per konto (og kontonavn hvis den finnes).

    - Grupperer minst på "Konto".
    - Hvis "Kontonavn" finnes, grupperer vi på den også.
    - Aggregerer:
        * Sum "Beløp" (hvis finnes)
        * Antall "Bilag" (hvis finnes)
    """
    if df.empty or "Konto" not in df.columns:
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
        # Ingenting å aggregere på – returner bare unike kontoer
        return df[group_cols].drop_duplicates().reset_index(drop=True)

    pivot = (
        df.groupby(group_cols, dropna=False)
        .agg(agg)
        .reset_index()
    )

    # Gi litt hyggeligere kolonnenavn
    rename_map: Dict[str, str] = {}
    if "Beløp" in pivot.columns:
        rename_map["Beløp"] = "Sum beløp"
    if "Bilag" in pivot.columns:
        rename_map["Bilag"] = "Antall bilag"

    if rename_map:
        pivot = pivot.rename(columns=rename_map)

    return pivot


def filter_by_search_text(df: pd.DataFrame, text: str) -> pd.DataFrame:
    """
    Fritekstsøk i noen sentrale kolonner.

    Søker (hvis kolonnene finnes):
      - "Tekst"
      - "Kontonavn"
      - "Bilag"
      - "Konto"
    """
    text = (text or "").strip().lower()
    if not text or df.empty:
        return df

    candidates = [c for c in ["Tekst", "Kontonavn", "Bilag", "Konto"] if c in df.columns]
    if not candidates:
        return df

    mask = pd.Series(False, index=df.index)
    for col in candidates:
        mask |= df[col].astype(str).str.lower().str.contains(text, na=False)

    return df[mask].copy()


def filter_by_accounts(df: pd.DataFrame, accounts: Iterable[Any]) -> pd.DataFrame:
    """
    Filtrer på et sett med kontonumre (som str eller tall).

    Hvis "Konto"-kolonnen ikke finnes, returneres df uendret.
    """
    if "Konto" not in df.columns:
        return df

    acc_list = [str(a) for a in accounts]
    if not acc_list:
        return df

    mask = df["Konto"].astype(str).isin(acc_list)
    return df[mask].copy()
