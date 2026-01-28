"""analyse_viewdata.py

Ren (UI-fri) hjelpe-logikk for Analyse-fanen.

Mål:
- Flytte pandas-logikk ut av store Tkinter-filer (f.eks. page_analyse.py)
  slik at UI kan bli tynnere og vi kan teste logikk uavhengig av GUI.

Prinsipper:
- Best-effort: Manglende felt => tomme verdier/0, ikke crash.
- Robust dato: dayfirst=True (norsk dd.mm.yyyy), men støtter også ISO.
- Ingen Tkinter-importer her.

Kontrakt/kolonnenavn (kanoniske):
- Bilag, Beløp, Tekst, Konto, Kontonavn, Dato

Eksport/clipboard:
- Treeview-kopiering til clipboard håndteres i ui_hotkeys.py.
- Denne modulen fokuserer på å bygge DataFrames i riktig kolonnerekkefølge.

"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from analyse_model import build_pivot_by_account
from konto_utils import konto_to_str
from logger import get_logger

log = get_logger()


# -----------------------------------------------------------------------------
# Konstanter
# -----------------------------------------------------------------------------

DEFAULT_TX_COLS: tuple[str, ...] = (
    "Bilag",
    "Beløp",
    "Tekst",
    "Kunder",
    "Konto",
    "Kontonavn",
    "Dato",
)

# Kandidatkolonner for "kunde/motpart" (varierer mellom datasett)
DEFAULT_CUSTOMER_COLS: tuple[str, ...] = (
    "Kunder",
    "Kundenavn",
    "Kunde",
    "Motpart",
    "Leverandør",
    "Leverandørnavn",
    "Customer",
    "CustomerName",
)

SHEET_PIVOT: str = "Pivot pr konto"
SHEET_TX: str = "Transaksjoner"
SHEET_TX_SHOWN: str = "Transaksjoner (viste)"
SHEET_TX_ALL: str = "Transaksjoner (alle valgte)"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def _empty_series(index: pd.Index) -> pd.Series:
    return pd.Series(["" for _ in range(len(index))], index=index, dtype="object")


def _safe_str_series(s: pd.Series) -> pd.Series:
    """Returner en "sikker" strengserie uten NaN/'nan' som tekst."""
    if s is None:
        return pd.Series(dtype="object")
    try:
        # Pandas StringDtype gir best kontroll på <NA>
        out = s.astype("string")
        out = out.fillna("")
        return out.astype(str)
    except Exception:
        return s.fillna("").astype(str)


def _format_date_ddmmyyyy(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series(dtype="object")
    if s.empty:
        return pd.Series([], dtype="object")

    # Robust parsing for norske/internasjonale varianter.
    # Pandas kan ellers forsøke å inferere én felles format-streng og feile på "blandede" kolonner.
    try:
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True, format="mixed")  # pandas >= 2.0
    except TypeError:  # pragma: no cover (eldre pandas)
        # Fallback (to-pass) uten format='mixed'
        dt = pd.to_datetime(s, errors="coerce", dayfirst=True)
        if dt.isna().any():
            dt2 = pd.to_datetime(s, errors="coerce")
            dt = dt.fillna(dt2)

    out = dt.dt.strftime("%d.%m.%Y")
    return out.fillna("").astype(str)


# -----------------------------------------------------------------------------
# Offentlig API
# -----------------------------------------------------------------------------

def first_nonempty_series(
    df: pd.DataFrame,
    cols: Sequence[str],
    *,
    na_strings: Sequence[str] = ("nan", "none"),
    strip: bool = True,
) -> pd.Series:
    """Returner første ikke-tomme verdi per rad fra en prioritert kolonneliste.

    Typisk bruk: finne "kunde"/"motpart" når datasett kan ha ulike kolonnenavn.

    - Tom streng (""), None, NaN og strengverdier som 'nan'/'None' behandles som tomt.
    - Resultatet er alltid en strengserie (object) uten NaN.
    """

    if df is None:
        return pd.Series(dtype="object")

    if df.empty:
        return pd.Series([], dtype="object")

    existing = [c for c in cols if c in df.columns]
    if not existing:
        return _empty_series(df.index)

    # Konverter til pandas string dtype for stabil håndtering av <NA>
    tmp = df[existing].copy()
    try:
        tmp = tmp.astype("string")
    except Exception:
        # Fallback: behold som object
        tmp = tmp.astype("object")

    if strip:
        # Stripping på få kolonner er OK.
        for c in existing:
            try:
                tmp[c] = tmp[c].str.strip()
            except Exception:
                tmp[c] = tmp[c].astype("string").str.strip()

    # Normaliser tokens vi skal behandle som "tomt"
    token_set = {t.strip().lower() for t in na_strings if isinstance(t, str) and t.strip()}

    for c in existing:
        s = tmp[c]

        # Tom streng => NA
        try:
            s = s.mask(s == "", pd.NA)
        except Exception:
            # object fallback
            s = s.replace("", pd.NA)

        # Token-matching case-insensitive
        if token_set:
            try:
                lower = s.astype("string").str.lower()
                s = s.mask(lower.isin(token_set), pd.NA)
            except Exception:
                lower = s.astype(str).str.lower()
                s = s.mask(lower.isin(token_set), pd.NA)

        tmp[c] = s

    # Finn første ikke-NA på tvers av kolonner
    try:
        first = tmp.bfill(axis=1).iloc[:, 0]
    except Exception:
        # Svært defensiv fallback
        first = tmp.iloc[:, 0]
        for c in existing[1:]:
            first = first.fillna(tmp[c])

    # Returner som vanlige strenger uten NaN
    try:
        return first.astype("string").fillna("").astype(str)
    except Exception:
        return first.fillna("").astype(str)


def build_transactions_view_df(
    df: pd.DataFrame,
    *,
    tx_cols: Sequence[str] = DEFAULT_TX_COLS,
    customer_cols: Sequence[str] = DEFAULT_CUSTOMER_COLS,
) -> pd.DataFrame:
    """Bygg en transaksjons-DataFrame med fast kolonnerekkefølge (for UI/eksport).

    Returnerer DataFrame med kolonnene i `tx_cols`.

    - Beløp beholdes som numerisk (float) hvis mulig.
    - Dato formateres som dd.mm.yyyy (streng) for konsistent UI.
    """

    if df is None or df.empty:
        return pd.DataFrame(columns=list(tx_cols))

    out = pd.DataFrame(index=df.index)

    # Bilag
    if "Bilag" in df.columns:
        out["Bilag"] = df["Bilag"].map(konto_to_str)
    else:
        out["Bilag"] = ""

    # Beløp
    if "Beløp" in df.columns:
        out["Beløp"] = pd.to_numeric(df["Beløp"], errors="coerce").fillna(0.0)
    else:
        out["Beløp"] = 0.0

    # Tekst
    if "Tekst" in df.columns:
        out["Tekst"] = _safe_str_series(df["Tekst"])
    else:
        out["Tekst"] = ""

    # Kunder/motpart
    out["Kunder"] = first_nonempty_series(df, customer_cols)

    # Konto
    if "Konto" in df.columns:
        out["Konto"] = df["Konto"].map(konto_to_str)
    else:
        out["Konto"] = ""

    # Kontonavn
    if "Kontonavn" in df.columns:
        out["Kontonavn"] = _safe_str_series(df["Kontonavn"])
    else:
        out["Kontonavn"] = ""

    # Dato
    if "Dato" in df.columns:
        out["Dato"] = _format_date_ddmmyyyy(df["Dato"])
    else:
        out["Dato"] = ""

    # Sikre kolonner i riktig rekkefølge
    for c in tx_cols:
        if c not in out.columns:
            out[c] = ""

    return out[list(tx_cols)].reset_index(drop=True)


def compute_selected_transactions(
    df_filtered: pd.DataFrame,
    selected_accounts: Iterable[Any],
    *,
    max_rows: int = 200,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Filtrer transaksjoner på valgte kontoer.

    Returnerer (df_all_selected, df_shown), der df_shown er begrenset til max_rows.

    Funksjonen er UI-uavhengig og tar imot en allerede filtrert df (fra analysefilter).
    """

    if df_filtered is None or df_filtered.empty or "Konto" not in df_filtered.columns:
        empty = pd.DataFrame(columns=df_filtered.columns if isinstance(df_filtered, pd.DataFrame) else None)
        return empty, empty

    wanted = [konto_to_str(a) for a in (selected_accounts or [])]
    wanted = [w for w in wanted if w]
    if not wanted:
        empty = pd.DataFrame(columns=df_filtered.columns)
        return empty, empty

    if not isinstance(max_rows, int) or max_rows <= 0:
        max_rows = 200

    konto_norm = df_filtered["Konto"].map(konto_to_str)
    mask = konto_norm.isin(set(wanted))

    df_all = df_filtered.loc[mask].copy()
    df_show = df_all.head(max_rows).copy()

    return df_all, df_show


def prepare_transactions_export_sheets(
    df_filtered: pd.DataFrame,
    selected_accounts: Iterable[Any],
    *,
    max_rows: int = 200,
    tx_cols: Sequence[str] = DEFAULT_TX_COLS,
    customer_cols: Sequence[str] = DEFAULT_CUSTOMER_COLS,
) -> dict[str, pd.DataFrame]:
    """Bygg ark-mapping for eksport av transaksjoner.

    Hvis transaksjonslisten er begrenset (Vis: N), så eksporteres to ark:
    - "Transaksjoner (viste)"
    - "Transaksjoner (alle valgte)"

    Hvis alt vises, eksporteres kun "Transaksjoner".
    """

    df_all, df_show = compute_selected_transactions(df_filtered, selected_accounts, max_rows=max_rows)

    if df_all.empty:
        return {}

    df_all_view = build_transactions_view_df(df_all, tx_cols=tx_cols, customer_cols=customer_cols)
    df_show_view = build_transactions_view_df(df_show, tx_cols=tx_cols, customer_cols=customer_cols)

    if len(df_all_view) == len(df_show_view):
        return {SHEET_TX: df_all_view}

    return {
        SHEET_TX_SHOWN: df_show_view,
        SHEET_TX_ALL: df_all_view,
    }


def prepare_pivot_export_sheets(
    df_filtered: pd.DataFrame,
    *,
    pivot_df: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    """Bygg ark-mapping for eksport av pivot pr konto.

    pivot_df kan gis inn hvis GUI allerede har bygget pivot og vil eksportere
    akkurat det som vises.

    Hvis pivot_df ikke er gitt, bygger vi pivot på df_filtered.
    """

    df_out: pd.DataFrame

    if pivot_df is not None and isinstance(pivot_df, pd.DataFrame) and not pivot_df.empty:
        df_out = pivot_df.copy()
    else:
        if df_filtered is None or df_filtered.empty:
            return {}
        df_out = build_pivot_by_account(df_filtered)

    if df_out is None or df_out.empty:
        return {}

    return {SHEET_PIVOT: df_out.reset_index(drop=True)}


def merge_sheet_maps(*maps: Mapping[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Slå sammen flere {arknavn: df}-mappinger.

    Hvis samme arknavn finnes flere steder, suffixes det automatisk.
    """

    out: dict[str, pd.DataFrame] = {}
    used: set[str] = set()

    for m in maps:
        for name, df in (m or {}).items():
            base = str(name)
            final = base
            if final in used:
                i = 2
                while f"{base} ({i})" in used:
                    i += 1
                final = f"{base} ({i})"
            used.add(final)
            out[final] = df

    return out
