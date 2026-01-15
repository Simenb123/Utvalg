"""utvalg_excel_report.py

Bygger en mer informativ Excel-rapport for Utvalg-fanen.

Dette er bevisst lagt i egen modul for å holde controller_export.py
slankere (<400 linjer) i tråd med prosjektets leveranseprinsipper.

Rapporten er best-effort:
  - Manglende felter => vi hopper over det vi ikke kan beregne.
  - Manglende full-dataset (df_all) => vi hopper over bilagtransaksjoner.

Bruk:
  sheets = augment_utvalg_export(sheets, meta=..., df_all=...)
"""

from __future__ import annotations

import datetime as _dt
import inspect
import logging
from typing import Any, Dict, Mapping, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Call-stack context (best effort)
# ---------------------------------------------------------------------------
def _tk_get(var: Any) -> Any:
    """Trygg avlesning av tkinter-variabler.

    Vi importerer ikke tkinter direkte (tester kjører ofte med stub).
    """

    if var is None:
        return None
    try:
        if hasattr(var, "get") and callable(var.get):
            return var.get()
    except Exception:
        return None
    return var


def try_collect_selectionstudio_context_from_stack() -> Tuple[Dict[str, Any], Optional[pd.DataFrame]]:
    """Prøver å hente meta + df_all fra SelectionStudio via call-stack.

    Dette gjør at vi kan forbedre eksporten uten å måtte endre store GUI-filer.
    Returnerer (meta, df_all). Tom dict / None hvis vi ikke finner.
    """

    meta: Dict[str, Any] = {}
    df_all: Optional[pd.DataFrame] = None

    frame = inspect.currentframe()
    if frame is None:
        return meta, df_all

    try:
        frame = frame.f_back  # kalleren
        while frame is not None:
            loc = frame.f_locals
            self_obj = loc.get("self")

            if self_obj is not None and hasattr(self_obj, "var_risk") and hasattr(self_obj, "_df_all"):
                # Vi antar at dette er SelectionStudio eller en kompatibel klasse
                meta = {
                    "risk": _tk_get(getattr(self_obj, "var_risk", None)),
                    "confidence": _tk_get(getattr(self_obj, "var_confidence", None)),
                    "tolerable_error": _tk_get(getattr(self_obj, "var_tolerable_error", None)),
                    "method": _tk_get(getattr(self_obj, "var_method", None)),
                    "k": _tk_get(getattr(self_obj, "var_k", None)),
                    "sample_n": _tk_get(getattr(self_obj, "var_sample_n", None)),
                    "direction": _tk_get(getattr(self_obj, "var_direction", None)),
                    "use_abs": _tk_get(getattr(self_obj, "var_use_abs", None)),
                    "min_amount": _tk_get(getattr(self_obj, "var_min_amount", None)),
                    "max_amount": _tk_get(getattr(self_obj, "var_max_amount", None)),
                }

                maybe_df_all = getattr(self_obj, "_df_all", None)
                if isinstance(maybe_df_all, pd.DataFrame):
                    df_all = maybe_df_all

                # Rydd bort None-verdier
                meta = {k: v for k, v in meta.items() if v is not None and v != ""}
                break

            frame = frame.f_back
    finally:
        # Unngå referansesyklus
        del frame

    return meta, df_all


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def _normalize_id_series(s: pd.Series) -> pd.Series:
    """Normaliserer Bilag (og andre id-er) til str for robust matching."""

    s2 = s.astype(str).str.strip()
    # typisk Excel-lesing gir '123.0'
    s2 = s2.str.replace(r"\.0$", "", regex=True)
    return s2


def _try_parse_float_no(value: Any) -> Optional[float]:
    """Forsøk å parse et norsk tallformat til float.

    Eksempler: "1 300 000" -> 1300000.0, "12,5" -> 12.5.
    """

    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except Exception:
            return None

    s = str(value).strip()
    if not s:
        return None

    s = s.replace("\xa0", " ").replace(" ", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def _format_bool_no(value: Any) -> Any:
    """Format boolsk verdi til norsk Ja/Nei (best effort)."""

    if value is None:
        return None
    if isinstance(value, bool):
        return "Ja" if value else "Nei"
    if isinstance(value, (int, float)):
        if value == 1:
            return "Ja"
        if value == 0:
            return "Nei"
    s = str(value).strip().lower()
    if s in {"1", "true", "ja", "yes", "y"}:
        return "Ja"
    if s in {"0", "false", "nei", "no", "n"}:
        return "Nei"
    return value


def _safe_sum(df: pd.DataFrame, col: str, abs_sum: bool = False) -> Optional[float]:
    if col not in df.columns:
        return None
    try:
        series = pd.to_numeric(df[col], errors="coerce")
        if abs_sum:
            series = series.abs()
        v = float(series.sum(skipna=True))
        return v
    except Exception:
        return None


def is_utvalg_export_case(sheets: Mapping[str, pd.DataFrame]) -> bool:
    """Heuristikk: Utvalg-fanen sender alltid minst Utvalg + Grunnlag."""

    keys = {str(k).strip().lower() for k in sheets.keys()}
    return "utvalg" in keys and "grunnlag" in keys


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------
def _add_utvalg_nummerering(df_utvalg: pd.DataFrame) -> pd.DataFrame:
    df = df_utvalg.copy().reset_index(drop=True)
    if "UtvalgNr" not in df.columns:
        df.insert(0, "UtvalgNr", range(1, len(df) + 1))
    return df


def _build_forutsetninger_sheet(meta: Mapping[str, Any]) -> pd.DataFrame:
    rows = []
    # Fast rekkefølge
    mapping = [
        ("Risiko", meta.get("risk")),
        ("Sikkerhet", meta.get("confidence")),
        ("Tolererbar feil", meta.get("tolerable_error")),
        ("Metode", meta.get("method")),
        ("Antall grupper (k)", meta.get("k")),
        ("Utvalgsstørrelse", meta.get("sample_n")),
        ("Retning", meta.get("direction")),
        ("Beløp fra", meta.get("min_amount")),
        ("Beløp til", meta.get("max_amount")),
        ("Bruk absolutt beløp", meta.get("use_abs")),
    ]
    for k, v in mapping:
        if v is None or v == "":
            continue

        # Litt "smart" formatting for Excel
        if k in {"Tolererbar feil", "Beløp fra", "Beløp til"}:
            parsed = _try_parse_float_no(v)
            v = parsed if parsed is not None else v
        if k in {"Antall grupper (k)", "Utvalgsstørrelse"}:
            try:
                v_int = int(float(str(v).strip().replace(" ", "").replace(",", ".")))
                v = v_int
            except Exception:
                pass
        if k == "Bruk absolutt beløp":
            v = _format_bool_no(v)

        rows.append({"Parameter": k, "Verdi": v})

    if not rows:
        rows.append({"Parameter": "(ingen)", "Verdi": ""})

    return pd.DataFrame(rows)


def _build_oppsummering_sheet(df_utvalg: pd.DataFrame, df_grunnlag: pd.DataFrame, meta: Mapping[str, Any]) -> pd.DataFrame:
    now = _dt.datetime.now().strftime("%d.%m.%Y %H:%M")

    grunnlag_rows = len(df_grunnlag)
    grunnlag_bilag = int(df_grunnlag["Bilag"].nunique()) if "Bilag" in df_grunnlag.columns else None

    grunnlag_sum = _safe_sum(df_grunnlag, "Beløp", abs_sum=False)
    grunnlag_abs_sum = _safe_sum(df_grunnlag, "Beløp", abs_sum=True)

    utvalg_bilag = len(df_utvalg)
    utvalg_sum = _safe_sum(df_utvalg, "SumBeløp", abs_sum=False) or _safe_sum(df_utvalg, "SumBelop", abs_sum=False)
    utvalg_abs_sum = None
    if utvalg_sum is not None:
        try:
            utvalg_abs_sum = float(pd.to_numeric(df_utvalg.get("SumBeløp", df_utvalg.get("SumBelop")), errors="coerce").abs().sum())
        except Exception:
            utvalg_abs_sum = None

    andel = None
    if grunnlag_bilag and grunnlag_bilag > 0:
        andel = utvalg_bilag / grunnlag_bilag

    rows = [
        {"Felt": "Eksportert", "Verdi": now},
        {"Felt": "Antall rader i grunnlag", "Verdi": grunnlag_rows},
    ]

    if grunnlag_bilag is not None:
        rows.append({"Felt": "Antall bilag i grunnlag", "Verdi": grunnlag_bilag})
    if grunnlag_sum is not None:
        rows.append({"Felt": "Sum beløp i grunnlag", "Verdi": grunnlag_sum})
    if grunnlag_abs_sum is not None:
        rows.append({"Felt": "Sum absolutt beløp i grunnlag", "Verdi": grunnlag_abs_sum})

    rows.append({"Felt": "Antall bilag i utvalg", "Verdi": utvalg_bilag})
    if utvalg_sum is not None:
        rows.append({"Felt": "Sum beløp i utvalg", "Verdi": utvalg_sum})
    if utvalg_abs_sum is not None:
        rows.append({"Felt": "Sum absolutt beløp i utvalg", "Verdi": utvalg_abs_sum})
    if andel is not None:
        rows.append({"Felt": "Utvalgsandel (bilag)", "Verdi": andel})

    # Noen nøkkelparametre (for rask oversikt)
    if meta.get("risk") is not None:
        rows.append({"Felt": "Risiko", "Verdi": meta.get("risk")})
    if meta.get("confidence") is not None:
        rows.append({"Felt": "Sikkerhet", "Verdi": meta.get("confidence")})
    if meta.get("tolerable_error") is not None:
        tol = meta.get("tolerable_error")
        rows.append({"Felt": "Tolererbar feil", "Verdi": _try_parse_float_no(tol) or tol})
    if meta.get("method") is not None:
        rows.append({"Felt": "Metode", "Verdi": meta.get("method")})
    if meta.get("k") is not None:
        rows.append({"Felt": "Antall grupper (k)", "Verdi": meta.get("k")})
    if meta.get("sample_n") is not None:
        rows.append({"Felt": "Utvalgsstørrelse", "Verdi": meta.get("sample_n")})
    if meta.get("direction") is not None:
        rows.append({"Felt": "Retning", "Verdi": meta.get("direction")})
    if meta.get("use_abs") is not None:
        rows.append({"Felt": "Bruk absolutt beløp", "Verdi": _format_bool_no(meta.get("use_abs"))})

    return pd.DataFrame(rows)


def _build_bilagtransaksjoner_sheet(df_all: pd.DataFrame, df_utvalg_numbered: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df_all is None or df_utvalg_numbered is None:
        return None
    if "Bilag" not in df_all.columns or "Bilag" not in df_utvalg_numbered.columns:
        return None

    bilag_map = df_utvalg_numbered[["UtvalgNr", "Bilag"]].copy()
    bilag_map["_bilag_norm"] = _normalize_id_series(bilag_map["Bilag"])

    df_tx = df_all.copy()
    df_tx["_bilag_norm"] = _normalize_id_series(df_tx["Bilag"])
    wanted = set(bilag_map["_bilag_norm"].dropna().astype(str).tolist())
    df_tx = df_tx[df_tx["_bilag_norm"].isin(wanted)].copy()
    if df_tx.empty:
        return None

    df_tx = df_tx.merge(bilag_map[["UtvalgNr", "_bilag_norm"]], on="_bilag_norm", how="left")
    df_tx.drop(columns=["_bilag_norm"], inplace=True, errors="ignore")

    # Kolonnerekkefølge: UtvalgNr, Bilag, Dato, Konto, Kontonavn, Tekst, Beløp, ...rest
    preferred = ["UtvalgNr", "Bilag", "Dato", "Konto", "Kontonavn", "Tekst", "Beløp"]
    cols = []
    for c in preferred:
        if c in df_tx.columns and c not in cols:
            cols.append(c)
    for c in df_tx.columns:
        if c not in cols:
            cols.append(c)
    df_tx = df_tx[cols]

    # Sortering
    sort_cols = [c for c in ["UtvalgNr", "Bilag", "Konto"] if c in df_tx.columns]
    if sort_cols:
        try:
            df_tx = df_tx.sort_values(sort_cols, kind="mergesort")
        except Exception:
            pass

    return df_tx


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def augment_utvalg_export(
    sheets: Dict[str, pd.DataFrame],
    *,
    meta: Optional[Mapping[str, Any]] = None,
    df_all: Optional[pd.DataFrame] = None,
) -> Dict[str, pd.DataFrame]:
    """Legger til ekstra ark og forbedringer for utvalg-eksport.

    Forventer at sheets inneholder minst:
      - "Utvalg": bilag-sample (1 rad per bilag)
      - "Grunnlag": filtrert populasjon (transaksjonsnivå)

    Returnerer ny dict med definert rekkefølge på ark.
    """

    meta = dict(meta or {})

    df_utvalg = sheets.get("Utvalg")
    df_grunnlag = sheets.get("Grunnlag")
    if not isinstance(df_utvalg, pd.DataFrame) or not isinstance(df_grunnlag, pd.DataFrame):
        return sheets

    df_utvalg_numbered = _add_utvalg_nummerering(df_utvalg)

    # Bygg ekstraark
    df_forut = _build_forutsetninger_sheet(meta)
    df_opp = _build_oppsummering_sheet(df_utvalg_numbered, df_grunnlag, meta)
    df_tx = _build_bilagtransaksjoner_sheet(df_all, df_utvalg_numbered) if isinstance(df_all, pd.DataFrame) else None

    # Sett opp i ønsket rekkefølge
    ordered: Dict[str, pd.DataFrame] = {}
    ordered["Oppsummering"] = df_opp
    ordered["Forutsetninger"] = df_forut
    ordered["Utvalg"] = df_utvalg_numbered
    if df_tx is not None:
        ordered["Bilagtransaksjoner"] = df_tx
    ordered["Grunnlag"] = df_grunnlag

    # Ta med eventuelle andre ark som caller sendte inn
    for k, v in sheets.items():
        if k in ordered:
            continue
        if isinstance(v, pd.DataFrame):
            ordered[k] = v

    return ordered
