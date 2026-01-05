"""selection_studio_helpers

Ren (Tk-fri) hjelpe-/domene-logikk for "Utvalg" (Selection Studio).

Designmål:
  * Testbar uten Tkinter.
  * Robust parsing/formattering av norske tall ("1 234,56").
  * **Bakoverkompatibilitet**: Repoet har historisk hatt flere varianter
    av samme funksjoner/signaturer. Testene i ``tests/`` forventer at vi
    støtter disse variantene uten at importer knekker.

Domenet er norsk revisjon / regnskap (NGAAP):
  * Populasjon = transaksjoner (rader)
  * Bilag = unike bilagsnummer
  * Konto = kontonummer
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Union

import math
import re

import pandas as pd

# --- Konfidensfaktorer (Elifsen et al. 2014, tabell 17.1) ---
# Vi forenkler risiko og sikkerhet til lav/middels/høy.
# Sikkerhet/konfidensnivå: lav=80%, middels=90%, høy=95%
CONFIDENCE_FACTORS: dict[str, dict[str, float]] = {
    "høy": {"høy": 3.0, "middels": 2.3, "lav": 2.0},
    "middels": {"høy": 2.3, "middels": 1.6, "lav": 1.2},
    "lav": {"høy": 2.0, "middels": 1.2, "lav": 1.0},
}

_CONF_LABELS = {
    "80": "lav",
    "80%": "lav",
    "0.8": "lav",
    "90": "middels",
    "90%": "middels",
    "0.9": "middels",
    "95": "høy",
    "95%": "høy",
    "0.95": "høy",
}


# ---------------------------
# Parsing / formatering (NO)
# ---------------------------

def _is_nan(x: Any) -> bool:
    try:
        return bool(pd.isna(x))
    except Exception:
        return False


def parse_amount(value: Any) -> Optional[float]:
    """
    Parse tall fra norsk/vanlig tekst til float.

    Støtter bl.a.:
    - "1 234,50" -> 1234.5
    - "1.234,50" -> 1234.5
    - "1,234.50" -> 1234.5
    - "(1 234,50)" -> -1234.5
    - 10 -> 10.0

    Returnerer None ved tom/ugyldig input.
    """
    if value is None or _is_nan(value):
        return None

    if isinstance(value, (int, float)):
        return float(value)

    s = str(value).strip()
    if not s:
        return None

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()

    # Fjern mellomrom (inkl NBSP)
    s = s.replace("\u00A0", " ").replace(" ", "")

    # Fjern valutategn osv. men behold -, . og ,
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if s in {"", "-", ".", ",", "-.", "-,"}:
        return None

    # Hvis både komma og punktum: anta den siste er desimalskilletegnet
    if "," in s and "." in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            # "1.234,56" => '.' tusen, ',' desimal
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # "1,234.56" => ',' tusen, '.' desimal
            s = s.replace(",", "")
    elif "," in s:
        # Kun komma => desimal (typisk norsk)
        s = s.replace(",", ".")

    try:
        val = float(s)
    except ValueError:
        return None

    if negative:
        val = -val
    return val


def parse_int(value: Any) -> Optional[int]:
    """Parse int fra tekst. Returnerer None ved tom/ugyldig input."""
    f = parse_amount(value)
    if f is None:
        return None
    try:
        return int(round(f))
    except Exception:
        return None


def format_amount_no(value: Any, decimals: int = 2) -> str:
    """
    Formatér tall til norsk format: tusenskille = mellomrom, desimal = komma.
    1234.5 -> "1 234,50"
    """
    f = parse_amount(value)
    if f is None:
        return ""
    # Python: 1,234.56 -> vi vil ha 1 234,56
    s = f"{f:,.{decimals}f}"
    s = s.replace(",", " ").replace(".", ",")
    return s


def format_int_no(value: Any) -> str:
    """Formatér heltall til norsk format: 1234567 -> '1 234 567'."""
    i = parse_int(value)
    if i is None:
        return ""
    return f"{i:,}".replace(",", " ")


def format_interval_no(interval: Any, decimals: int = 2) -> str:
    """
    Konverter pandas-interval-string til norsk format.

    Eksempel:
    "(0.259, 255.998]" -> "(0,26 – 256,00]"
    """
    if interval is None or _is_nan(interval):
        return ""

    s = str(interval).strip()
    if not s:
        return ""

    m = re.match(r"^([\(\[])\s*([^,]+)\s*,\s*([^\]\)]+)\s*([\]\)])$", s)
    if not m:
        # Ukjent format – returner som det er
        return s

    left_br, left_raw, right_raw, right_br = m.groups()
    left_val = parse_amount(left_raw)
    right_val = parse_amount(right_raw)

    left_txt = format_amount_no(left_val, decimals=decimals) if left_val is not None else left_raw.strip()
    right_txt = format_amount_no(right_val, decimals=decimals) if right_val is not None else right_raw.strip()

    return f"{left_br}{left_txt} – {right_txt}{right_br}"


# ---------------------------
# Populasjons-/utvalgs-metrikk
# ---------------------------

@dataclass(frozen=True)
class PopulationMetrics:
    """Små oppsummeringsmetrikker for en populasjon.

    Bakoverkompatibilitet:
      * Nye navn: rows, bilag, konto
      * Legacy navn brukt i noen tester/eldre kode: n_rows, n_bilag, n_accounts
    """

    rows: int
    bilag: int
    konto: int
    sum_net: float
    sum_abs: float

    # Egen __init__ for å støtte legacy keyword-argumenter.
    def __init__(
        self,
        rows: int | None = None,
        bilag: int | None = None,
        konto: int | None = None,
        *,
        sum_net: float = 0.0,
        sum_abs: float = 0.0,
        n_rows: int | None = None,
        n_bilag: int | None = None,
        n_accounts: int | None = None,
        **_: Any,
    ) -> None:
        if rows is None:
            rows = n_rows
        if bilag is None:
            bilag = n_bilag
        if konto is None:
            konto = n_accounts

        object.__setattr__(self, "rows", int(rows or 0))
        object.__setattr__(self, "bilag", int(bilag or 0))
        object.__setattr__(self, "konto", int(konto or 0))
        object.__setattr__(self, "sum_net", float(sum_net or 0.0))
        object.__setattr__(self, "sum_abs", float(sum_abs or 0.0))


def _find_col(df: pd.DataFrame, candidates: list[str]) -> Optional[str]:
    if df is None or df.empty:
        return None
    # eksakt
    for c in candidates:
        if c in df.columns:
            return c
    # case-insensitive
    lower_map = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def compute_population_metrics(df: Optional[pd.DataFrame]) -> PopulationMetrics:
    """
    Beregn grunnleggende metrikker for en populasjon (DataFrame).

    Forventer typisk kolonner:
    - Bilag
    - Konto
    - Beløp / Belop
    """
    if df is None or df.empty:
        return PopulationMetrics(rows=0, bilag=0, konto=0, sum_net=0.0, sum_abs=0.0)

    bilag_col = _find_col(df, ["Bilag", "bilag", "Voucher"])
    konto_col = _find_col(df, ["Konto", "konto", "Account"])
    amount_col = _find_col(df, ["Beløp", "Belop", "Beløp", "Amount", "amount"])

    rows = int(len(df))
    bilag = int(df[bilag_col].nunique(dropna=True)) if bilag_col else 0
    konto = int(df[konto_col].nunique(dropna=True)) if konto_col else 0

    if amount_col:
        amt = pd.to_numeric(df[amount_col], errors="coerce")
        sum_net = float(amt.sum(skipna=True))
        sum_abs = float(amt.abs().sum(skipna=True))
    else:
        sum_net = 0.0
        sum_abs = 0.0

    return PopulationMetrics(rows=rows, bilag=bilag, konto=konto, sum_net=sum_net, sum_abs=sum_abs)


def build_source_text(df_base: Optional[pd.DataFrame], df_all: Optional[pd.DataFrame] = None) -> str:
    """Lag en kort "kilde"-tekst.

    Funksjonen støtter to historiske kallmønstre:

    1) ``build_source_text(df_base, df_all)``
       Brukes av SelectionStudio for å vise om vi jobber på hele datasettet
       eller en delmengde.

    2) ``build_source_text(df_accounts)``
       Brukes av eldre GUI/tester for å vise hvilke kontoer som er valgt.
       Forventer at DataFrame har en "Konto"-kolonne.
    """
    if df_base is None:
        return "Kilde: (ingen data)"

    # Variant 2: kun ett argument => beskriv kontoer
    if df_all is None:
        konto_col = _find_col(df_base, ["Konto", "konto", "Account"])
        if not konto_col:
            return "Kilde: (ukjent kontoutvalg)"

        konto_series = df_base[konto_col].dropna().astype(str).str.strip().str.replace(r"\.0$", "", regex=True)
        unique = sorted({k for k in konto_series.tolist() if k != ""})
        if not unique:
            return "Kilde: Kontoer: 0"

        # Finn min/max som tall hvis mulig, ellers leksikografisk
        def _to_int_safe(x: str) -> Optional[int]:
            try:
                return int(x)
            except Exception:
                return None

        ints = [i for i in (_to_int_safe(x) for x in unique) if i is not None]
        if ints:
            lo = min(ints)
            hi = max(ints)
            span = f"({lo}-{hi})"
        else:
            span = f"({unique[0]}-{unique[-1]})"

        return f"Kilde: Kontoer: {len(unique)} {span}"

    # Variant 1: df_base + df_all
    same = False
    try:
        same = df_base.reset_index(drop=True).equals(df_all.reset_index(drop=True))
    except Exception:
        same = False

    if same:
        return "Kilde: hele datasettet"
    return "Kilde: kontoutvalg (delmengde av datasett)"


def build_population_summary_text(
    metrics: PopulationMetrics,
    *args: Any,
    **kwargs: Any,
) -> str:
    """Bygg en kort oppsummeringstekst for populasjon.

    Repoet har hatt flere signaturer i omløp. Vi støtter:

    * ``build_population_summary_text(metrics)``
    * ``build_population_summary_text(metrics, removed_rows, removed_bilag)``
    * ``build_population_summary_text(metrics, removed_rows=..., removed_bilag=...)``
    * ``build_population_summary_text(base_metrics, work_metrics, abs_basis=True/False)``
      (for UI som viser både grunnlag og "etter filter").
    """

    # --- parse kwargs -------------------------------------------------
    abs_basis = bool(kwargs.pop("abs_basis", True))
    removed_rows_kw = kwargs.pop("removed_rows", 0)
    removed_bilag_kw = kwargs.pop("removed_bilag", 0)

    # --- parse positional legacy --------------------------------------
    work_metrics: Optional[PopulationMetrics] = None
    removed_rows = int(removed_rows_kw or 0)
    removed_bilag = int(removed_bilag_kw or 0)

    if len(args) >= 1:
        if isinstance(args[0], PopulationMetrics):
            work_metrics = args[0]
        else:
            # legacy: (metrics, removed_rows, removed_bilag)
            try:
                removed_rows = int(args[0] or 0)
            except Exception:
                removed_rows = int(removed_rows_kw or 0)

    if len(args) >= 2:
        if work_metrics is None:
            try:
                removed_bilag = int(args[1] or 0)
            except Exception:
                removed_bilag = int(removed_bilag_kw or 0)
        else:
            # If someone passes 3 args as (base, work, abs_basis?) we ignore; use kw.
            pass

    # --- helper formatting --------------------------------------------
    def _line(m: PopulationMetrics) -> str:
        return (
            f"{format_int_no(m.rows)} rader | "
            f"{format_int_no(m.bilag)} bilag | "
            f"{format_int_no(m.konto)} kontoer"
        )

    def _sums(m: PopulationMetrics) -> str:
        if abs_basis:
            return f"Sum (abs): {format_amount_no(m.sum_abs)} | Netto: {format_amount_no(m.sum_net)}"
        return f"Sum (netto): {format_amount_no(m.sum_net)} | Abs: {format_amount_no(m.sum_abs)}"

    # --- build output --------------------------------------------------
    if work_metrics is not None:
        return (
            f"Grunnlag: {_line(metrics)}\n"
            f"Etter filter: {_line(work_metrics)}\n"
            f"{_sums(work_metrics)}"
        )

    txt = f"Grunnlag: {_line(metrics)} | {_sums(metrics)}"
    if removed_rows or removed_bilag:
        txt += f" | Fjernet: {format_int_no(removed_rows)} rader, {format_int_no(removed_bilag)} bilag"
    return txt


def build_sample_summary_text(sample_df: Optional[pd.DataFrame]) -> str:
    """Oppsummering for trukket utvalg (sample).

    Testene forventer at teksten:
      * alltid starter med "Utvalg:"
      * bruker unike bilag-tellinger
      * kan inkludere sum per bilag hvis kolonnene finnes
      * ikke kaster exceptions ved manglende kolonner
    """
    if sample_df is None or sample_df.empty:
        return "Utvalg: (ingen bilag trukket)"

    bilag_col = _find_col(sample_df, ["Bilag", "bilag", "Voucher"])
    amount_col = _find_col(sample_df, ["Beløp", "Belop", "Amount", "amount"])

    rows = int(len(sample_df))
    bilag = int(sample_df[bilag_col].nunique(dropna=True)) if bilag_col else 0

    txt = f"Utvalg: {format_int_no(bilag)} bilag | {format_int_no(rows)} rader"

    # Unngå dobbelttelling: summer "per bilag" basert på første forekomst per bilag
    dedup = sample_df
    if bilag_col and bilag_col in sample_df.columns:
        dedup = sample_df.drop_duplicates(subset=[bilag_col])

    col_ground = _find_col(sample_df, ["Sum bilag (grunnlag)"])
    col_interval = _find_col(sample_df, ["Sum bilag (kontointervallet)"])

    if col_ground or col_interval:
        if col_ground:
            s1 = float(pd.to_numeric(dedup[col_ground], errors="coerce").fillna(0.0).sum())
            txt += f" | Sum (filtrert grunnlag): {format_amount_no(s1)} (Sum bilag (grunnlag))"
        if col_interval:
            s2 = float(pd.to_numeric(dedup[col_interval], errors="coerce").fillna(0.0).sum())
            txt += f" | Sum (valgte kontoer): {format_amount_no(s2)} (Sum bilag (kontointervallet))"
        return txt

    # Fallback: summer Beløp (netto/abs)
    if amount_col:
        amt = pd.to_numeric(sample_df[amount_col], errors="coerce").fillna(0.0)
        txt += f" | Sum (abs): {format_amount_no(float(amt.abs().sum()))} | Netto: {format_amount_no(float(amt.sum()))}"

    return txt


# ---------------------------
# Risiko/sikkerhet -> forslag utvalg
# ---------------------------

def _risk_to_label(risk: Union[str, int, float, None]) -> str:
    """Normaliser risiko til "lav"/"middels"/"høy".

    Støtter:
      * "lav"/"middels"/"høy"
      * legacy skala 1-5 (int eller tekst)
    """
    if risk is None:
        return "middels"
    if isinstance(risk, (int, float)):
        r = int(round(float(risk)))
        if r >= 4:
            return "høy"
        if r <= 2:
            return "lav"
        return "middels"
    s = str(risk).strip().lower()
    if s.isdigit():
        return _risk_to_label(int(s))
    if s in {"lav", "middels", "høy"}:
        return s
    return "middels"


def confidence_factor(
    risk_level: Union[str, int, float, None] = "middels",
    confidence_level: Union[str, int, float, None] = "middels",
) -> float:
    """
    Slår opp konfidensfaktor basert på (risiko, sikkerhet).
    - risk_level: "lav" | "middels" | "høy"
    - confidence_level: "lav" | "middels" | "høy" eller 80/90/95 eller "80%"/"90%"/"95%"
    """
    r = _risk_to_label(risk_level)

    c_raw = str(confidence_level).strip().lower()
    c = _CONF_LABELS.get(c_raw, c_raw)
    if c not in {"lav", "middels", "høy"}:
        c = "middels"
    return float(CONFIDENCE_FACTORS[r][c])


def suggest_sample_size(
    population: int | float,
    tolerable_error: float | None = None,
    expected_error: float | None = None,
    *,
    # --- legacy/GUI keywords ------------------------------------------
    risk_factor: int | None = None,
    assurance: str | int | float | None = None,
    population_value: float | None = None,
    # --- new/explicit keywords ----------------------------------------
    risk_level: str | None = None,
    confidence_level: str | int | float | None = None,
    min_size: int = 1,
    max_size: int | None = None,
) -> int:
    """Foreslå utvalgsstørrelse.

    Repoet har to hovedbruk:

    **A) Revisorformel (bokført verdi):**
        ``sample ≈ (pop_value / (tolerable - expected)) * konfidensfaktor``

      Brukes enten direkte som:
        ``suggest_sample_size(pop_value, tolerable_error, expected_error=..., risk_level=..., confidence_level=...)``

      ...eller via GUI (SelectionStudio) som:
        ``suggest_sample_size(population_n, population_value=..., tolerable_error=..., expected_error=..., risk_factor=..., assurance=...)``

    **B) Tommelfingerregel (når tolerable/expected ikke er satt):**
        Returner en andel av populasjonen basert på konfidensfaktor, clampet
        til [min_size, max_size] og aldri > population_n.

    Funksjonen er bevisst robust og "best effort" for å støtte flere gamle
    kallmønstre uten å knekke tester/UI.
    """

    # Normaliser min/max
    min_n = int(max(min_size, 0))
    max_n = int(max_size) if max_size is not None else None

    # Konverter assurance/confidence
    conf_in = confidence_level
    if conf_in is None:
        conf_in = assurance

    risk_in: str | int | float | None
    if risk_level is not None:
        risk_in = risk_level
    elif risk_factor is not None:
        risk_in = risk_factor
    else:
        risk_in = "middels"

    factor = confidence_factor(risk_level=risk_in, confidence_level=conf_in or "middels")

    # ---------------------------------------------------------------
    # Formel-mode
    # ---------------------------------------------------------------
    def _safe_float(x: Any) -> Optional[float]:
        try:
            if x is None:
                return None
            return float(x)
        except Exception:
            return None

    tol = _safe_float(tolerable_error)
    exp = _safe_float(expected_error) or 0.0

    # Direct formula call pattern: population is pop_value and tolerable_error provided positionally.
    direct_formula = tol is not None and risk_level is not None and population_value is None
    if direct_formula:
        pop_val = float(population or 0.0)
        denom = float(tol) - float(exp)
        if pop_val > 0 and denom > 0:
            raw = (pop_val / denom) * factor
            n = int(math.ceil(raw))
            if n < min_n:
                n = min_n
            if max_n is not None:
                n = min(n, max_n)
            return int(n)
        return int(min_n)

    # GUI formula pattern: population is count (bilag), and population_value gives book value.
    if population_value is not None and tol is not None:
        pop_val = float(population_value or 0.0)
        denom = float(tol) - float(exp)
        if pop_val > 0 and denom > 0:
            raw = (pop_val / denom) * factor
            n = int(math.ceil(raw))
        else:
            n = min_n

        # Clamp to population count if population looks like a count
        try:
            pop_n = int(round(float(population)))
        except Exception:
            pop_n = 0

        if pop_n > 0:
            n = max(min_n, min(n, pop_n))
        if max_n is not None:
            n = min(n, max_n)
        return int(n)

    # ---------------------------------------------------------------
    # Tommelfingerregel: 10% * konfidensfaktor (clampet)
    # ---------------------------------------------------------------
    try:
        pop_n2 = int(round(float(population)))
    except Exception:
        pop_n2 = 0

    if pop_n2 <= 0:
        return int(min_n)

    raw2 = float(pop_n2) * 0.10 * float(factor)
    n2 = int(math.ceil(raw2))
    n2 = max(min_n, n2)
    n2 = min(n2, pop_n2)
    if max_n is not None:
        n2 = min(n2, max_n)
    return int(n2)


# -------------------------------------------------------------------------
# Kompatibilitet / aliaser (så importer ikke knekker når vi rydder i navn)
# -------------------------------------------------------------------------

# gamle/alternative navn brukt av GUI/tester
fmt_amount_no = format_amount_no
fmt_int_no = format_int_no

# noen steder brukes disse navnene
parse_float = parse_amount
parse_number = parse_amount
