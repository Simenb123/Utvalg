"""Utvalg.views_selection_studio

SelectionStudio is a reusable widget used by both the legacy Utvalg page
(`page_utvalg.py`) and the newer strata-based page (`page_utvalg_strata.py`).

This module intentionally keeps backward compatible entrypoints:

* The `SelectionStudio` constructor accepts multiple legacy signatures.
* Helper functions are re-exported from `selection_studio_helpers`.
* Legacy formatting helper names are kept as aliases.

Business rules
--------------
* **Tolererbar feil** is treated as the already calculated threshold
  (arbeidsvesentlighet - forventet feil).
* All bilag with ``abs(SumBeløp) >= tolererbar feil`` are always selected as
  **spesifikk utvelgelse**.
* The recommended sample size is computed on the *remaining* population after
  removing the specific selection (so the recommendation is reduced by the
  automatic picks).
"""

from __future__ import annotations

import math
import re
import inspect
import os
from datetime import datetime

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import random

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controller_export import export_to_excel
from selectionstudio_filters import filter_selectionstudio_dataframe
try:
    # Nyere stratifiering.py eksponerer en 'Series-first' API (brukt av testene).
    from stratifiering import stratify_values as _stratify_values
except Exception:  # pragma: no cover
    # Fallback: implementer en enkel variant lokalt (for eldre stratifiering.py).
    def _stratify_values(
        values: pd.Series,
        *,
        method: str = "quantile",
        k: int = 3,
    ) -> tuple[list[tuple[str, pd.Series]], dict[str, str], pd.DataFrame]:
        """Stratifiser en Series og returner (groups, interval_map, stats_df).

        groups: liste av (group_label, mask) der mask er boolsk Series med samme index.
        interval_map: mapping group_label -> tekstlig intervall.
        stats_df: DataFrame med kolonnene Gruppe, Antall, Sum, Min, Max.
        """
        s = pd.to_numeric(values, errors="coerce").fillna(0.0)
        kk = max(int(k), 1)
        m = (method or "quantile").strip().lower()

        if s.empty:
            empty_stats = pd.DataFrame(columns=["Gruppe", "Antall", "Sum", "Min", "Max"])
            return [], {}, empty_stats

        # Dersom alle verdier er like (eller kk==1) gir flere strata ingen mening.
        if kk <= 1 or s.nunique(dropna=False) <= 1:
            label = "Gruppe 1"
            mask = pd.Series([True] * len(s), index=s.index)
            vmin = float(s.min())
            vmax = float(s.max())
            interval_map = {label: f"[{vmin}; {vmax}]"}
            stats_df = pd.DataFrame(
                [{"Gruppe": label, "Antall": int(mask.sum()), "Sum": float(s.sum()), "Min": vmin, "Max": vmax}]
            )
            return [(label, mask)], interval_map, stats_df

        # Lag bins
        bins = None
        if m in {"quantile", "kvantil"}:
            try:
                bins = pd.qcut(s, q=kk, duplicates="drop")
            except Exception:
                bins = None
        elif m in {"equal_width", "lik_bredde", "equal"}:
            try:
                bins = pd.cut(s, bins=kk)
            except Exception:
                bins = None
        else:
            # Default
            try:
                bins = pd.qcut(s, q=kk, duplicates="drop")
            except Exception:
                bins = None

        if bins is None or not hasattr(bins, "cat"):
            # Fallback: én gruppe
            label = "Gruppe 1"
            mask = pd.Series([True] * len(s), index=s.index)
            vmin = float(s.min())
            vmax = float(s.max())
            interval_map = {label: f"[{vmin}; {vmax}]"}
            stats_df = pd.DataFrame(
                [{"Gruppe": label, "Antall": int(mask.sum()), "Sum": float(s.sum()), "Min": vmin, "Max": vmax}]
            )
            return [(label, mask)], interval_map, stats_df

        cats = list(bins.cat.categories)
        # pd.qcut med duplicates="drop" kan returnere < kk kategorier.
        if len(cats) <= 1:
            label = "Gruppe 1"
            mask = pd.Series([True] * len(s), index=s.index)
            vmin = float(s.min())
            vmax = float(s.max())
            interval_map = {label: f"[{vmin}; {vmax}]"}
            stats_df = pd.DataFrame(
                [{"Gruppe": label, "Antall": int(mask.sum()), "Sum": float(s.sum()), "Min": vmin, "Max": vmax}]
            )
            return [(label, mask)], interval_map, stats_df

        groups: list[tuple[str, pd.Series]] = []
        interval_map: dict[str, str] = {}
        stats_rows: list[dict[str, float | int | str]] = []

        for idx, interval in enumerate(cats, start=1):
            label = f"Gruppe {idx}"
            mask = bins == interval
            vals = s.loc[mask]
            vmin = float(vals.min()) if not vals.empty else float("nan")
            vmax = float(vals.max()) if not vals.empty else float("nan")
            groups.append((label, mask))
            # Bruk samme [min; max]-format som ellers i appen
            interval_map[label] = f"[{vmin}; {vmax}]"
            stats_rows.append(
                {
                    "Gruppe": label,
                    "Antall": int(mask.sum()),
                    "Sum": float(vals.sum()),
                    "Min": vmin,
                    "Max": vmax,
                }
            )

        stats_df = pd.DataFrame(stats_rows)
        return groups, interval_map, stats_df

# Pure helper functions (kept out of GUI logic)
from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    compute_bilag_split_summary,
    build_sample_summary_text,
    build_source_text,
    confidence_factor,
    compute_population_metrics,
    fmt_amount_no,
    fmt_int_no,
    format_interval_no,
    parse_amount,
    suggest_sample_size,
)

try:
    # Preferred drilldown dialog for bilag
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None


# ---------------------------------------------------------------------------
# Backwards compatible formatting aliases
# ---------------------------------------------------------------------------


def format_amount_input_no(value: Any) -> str:
    """Format an amount as the user typically types it (no decimals).

    Legacy alias kept for tests and older code.
    """

    try:
        n = parse_amount(value)
    except Exception:
        return ""
    return fmt_amount_no(n, decimals=0)




# ---------------------------------------------------------------------------
# UI helpers: unngå linjeskift i tusenskiller
# ---------------------------------------------------------------------------

_NO_BREAK_SPACE = "\u00A0"
_RE_SPACE_BETWEEN_DIGITS = re.compile(r"(?<=\d) (?=\d)")


def no_break_spaces_in_numbers(text: str) -> str:
    """Erstatt vanlige mellomrom *mellom siffer* med non‑breaking space.

    Hvorfor:
      - I UI (Label med wraplength) kan Tk bryte linjen på vanlige mellomrom.
      - Norske tusenskiller er mellomrom, så tall som "13 851 272" kan bli delt i to linjer.
      - Ved å bruke NBSP mellom sifre holdes tallet samlet, men øvrige ord kan fortsatt wrappe.

    NB: Dette brukes **kun** for visningstekst (ikke for lagring/Excel).
    """
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return ""
    return _RE_SPACE_BETWEEN_DIGITS.sub(_NO_BREAK_SPACE, text)

# --- custom strata boundaries (manual) -----------------------------------------

_CUSTOM_SPLIT_RE = re.compile(r"[;\n]+")


def parse_custom_strata_bounds(text: str) -> list[float]:
    """Parse en liste med strata-grenser fra tekst.

    Bruker semikolon og/eller linjeskift som skilletegn, f.eks.:
        "100 000; 500 000; 1 000 000"

    Returnerer sortert, unike, positive grenser (float). Ugyldige tokens ignoreres.
    """
    raw = (text or "").strip()
    if not raw:
        return []

    parts = [p.strip() for p in _CUSTOM_SPLIT_RE.split(raw) if p.strip()]
    bounds: list[float] = []
    for p in parts:
        f = parse_amount(p)
        if f is None:
            continue
        try:
            bounds.append(float(abs(f)))
        except Exception:
            continue

    # Sorter og fjern duplikater
    bounds_sorted = sorted({b for b in bounds if math.isfinite(b)})
    return bounds_sorted


def format_custom_strata_bounds(bounds: list[float]) -> str:
    """Formater en liste med strata-grenser til et lesbart input-format."""
    if not bounds:
        return ""
    return "; ".join(fmt_amount_no(b, decimals=0) for b in bounds)


def stratify_values_custom_bounds(
    values: pd.Series,
    *,
    bounds: list[float],
) -> tuple[list[tuple[int, pd.Series]], dict[str, str], pd.DataFrame]:
    """Stratifiserer en numerisk serie basert på manuelle grenser.

    - values forventes å være et beløpsmål som allerede er valgt (typisk |SumBeløp|).
    - bounds er sortert, unike grenser (positiv verdi), f.eks. [100_000, 500_000].

    Returnerer (grupper, intervall_map, stats_df) kompatibelt med eksisterende UI:
      - grupper: [(1, mask_series), (2, mask_series), ...]
      - intervall_map: {"1": "0 – 100 000", "2": "100 000 – 500 000", "3": ">= 500 000"}
      - stats_df: kolonner [Gruppe, Antall, Sum, Min, Max]
    """
    stats_cols = ["Gruppe", "Antall", "Sum", "Min", "Max"]

    if values is None or len(values) == 0:
        return [], {}, pd.DataFrame(columns=stats_cols)

    s = pd.to_numeric(values, errors="coerce").fillna(0.0)

    b = sorted({float(abs(x)) for x in (bounds or []) if x is not None and math.isfinite(float(x))})

    # 1 gruppe hvis ingen grenser
    if not b:
        antall = int(len(s))
        sum_ = float(s.sum()) if antall else 0.0
        min_ = float(s.min()) if antall else float("nan")
        max_ = float(s.max()) if antall else float("nan")
        interval = f"{fmt_amount_no(min_, decimals=0)} – {fmt_amount_no(max_, decimals=0)}" if antall else ""
        groups = [(1, pd.Series([True] * len(s), index=s.index))]
        interval_map = {"1": interval}
        stats_df = pd.DataFrame(
            [{"Gruppe": 1, "Antall": antall, "Sum": sum_, "Min": min_, "Max": max_}],
            columns=stats_cols,
        )
        return groups, interval_map, stats_df

    bins = [float("-inf"), *b, float("inf")]
    cut = pd.cut(s, bins=bins, include_lowest=True, right=True)

    groups: list[tuple[int, pd.Series]] = []
    interval_map: dict[str, str] = {}
    rows: list[dict[str, Any]] = []

    num_groups = len(b) + 1
    for i in range(1, num_groups + 1):
        mask = cut.cat.codes == (i - 1)
        mask = pd.Series(mask, index=s.index)

        gvals = s.loc[mask]
        antall = int(mask.sum())
        sum_ = float(gvals.sum()) if antall else 0.0
        min_ = float(gvals.min()) if antall else float("nan")
        max_ = float(gvals.max()) if antall else float("nan")

        groups.append((i, mask))
        rows.append({"Gruppe": i, "Antall": antall, "Sum": sum_, "Min": min_, "Max": max_})

        if i == 1:
            interval_txt = f"0 – {fmt_amount_no(b[0], decimals=0)}"
        elif i == num_groups:
            interval_txt = f">= {fmt_amount_no(b[-1], decimals=0)}"
        else:
            lo = b[i - 2]
            hi = b[i - 1]
            interval_txt = f"{fmt_amount_no(lo, decimals=0)} – {fmt_amount_no(hi, decimals=0)}"

        interval_map[str(i)] = interval_txt

    stats_df = pd.DataFrame(rows, columns=stats_cols)
    return groups, interval_map, stats_df


# ---------------------------------------------------------------------------
# Specific selection helpers (pure logic, unit-testable)
# ---------------------------------------------------------------------------


def split_specific_selection_by_tolerable_error(
    bilag_df: pd.DataFrame,
    tolerable_error: float | int | None,
    *,
    amount_col: str | None = None,
    amount_column: str = "SumBeløp",
    use_abs: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split bilag i "spesifikt utvalg" vs resten.

    Regler:
    - Et bilag havner i spesifikt utvalg hvis |SumBeløp| >= tolerable_error (eller SumBeløp >= tolerable_error når use_abs=False).
    - Hvis tolerable_error er tom/0/negativ: ingen bilag tas automatisk ut (dvs. alt blir "resten").

    Parametre:
        bilag_df: DataFrame med minst kolonnen SumBeløp (default) og gjerne Bilag.
        tolerable_error: Tolererbar feil (positivt tall).
        amount_col / amount_column: Kolonnenavn for beløpet (default "SumBeløp").
        use_abs: Bruk absoluttverdi når vi sammenligner mot tolerable_error.

    Returnerer:
        (df_specific, df_remaining)
    """

    if bilag_df is None or bilag_df.empty:
        empty = bilag_df.copy() if isinstance(bilag_df, pd.DataFrame) else pd.DataFrame()
        return empty, empty

    col = amount_col or amount_column
    if col not in bilag_df.columns:
        raise KeyError(col)

    tol = float(tolerable_error or 0.0)
    tol_abs = abs(tol)

    # 0 eller negativ toleranse betyr at vi ikke kjører spesifikt utvalg automatisk.
    if tol_abs <= 0.0:
        df_specific = bilag_df.iloc[0:0].copy()
        df_remaining = bilag_df.copy()
        return df_specific, df_remaining

    amounts = pd.to_numeric(bilag_df[col], errors="coerce").fillna(0.0)
    metric = amounts.abs() if use_abs else amounts

    mask_specific = metric >= tol_abs
    df_specific = bilag_df.loc[mask_specific].copy()
    df_remaining = bilag_df.loc[~mask_specific].copy()
    return df_specific, df_remaining
@dataclass(frozen=True)
class SpecificSelectionRecommendation:
    """Resultat fra beregning av spesifikt utvalg.

    Denne klassen er bevisst laget for å fungere både med attribute-access
    (f.eks. `reco.specific_bilag`) og som en dict-lignende struktur
    (f.eks. `reco["n_specific"]`) for bakoverkompatibilitet.
    """

    tolerable_error: float
    confidence_factor: float | None
    use_abs: bool

    specific_bilag: list[Any] = field(default_factory=list)
    specific_count: int = 0
    remaining_count: int = 0

    specific_value: float = 0.0
    remaining_value: float = 0.0
    total_value: float = 0.0

    additional_n: int = 0
    total_n: int = 0

    # Kun tilgjengelig når input var bilag_df
    specific_df: pd.DataFrame | None = None
    remaining_df: pd.DataFrame | None = None

    def as_dict(self) -> dict[str, Any]:
        # NOTE: The selection studio historically returned a dict with a simple
        # success flag. Some tests and UI call-sites still expect this.
        return {
            "ok": True,
            # Core
            "tolerable_error": self.tolerable_error,
            "threshold": self.tolerable_error,  # alias
            "confidence_factor": self.confidence_factor,
            "use_abs": self.use_abs,
            # Counts
            "n_specific": self.specific_count,
            "n_remaining": self.remaining_count,
            "n_total": int(self.specific_count + self.remaining_count),
            # Values
            "specific_book_value": self.specific_value,
            "remaining_book_value": self.remaining_value,
            "total_book_value": self.total_value,
            "specific_value": self.specific_value,
            "remaining_value": self.remaining_value,
            "total_value": self.total_value,
            # Recommended sample sizes
            "recommended_remaining": self.additional_n,
            "recommended_total": self.total_n,
            # DataFrames (optional)
            "specific_df": self.specific_df,
            "remaining_df": self.remaining_df,
            # Legacy names (used by some tester/GUI)
            "specific_bilag": self.specific_bilag,
            "specific_count": self.specific_count,
            "remaining_count": self.remaining_count,
            "additional_n": self.additional_n,
            "total_n": self.total_n,
            "n_total_recommended": self.total_n,
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def keys(self):
        return self.as_dict().keys()

    def items(self):
        return self.as_dict().items()


def compute_specific_selection_recommendation(
    bilag_df: pd.DataFrame | None = None,
    tolerable_error: float | int | None = None,
    *,
    bilag_values: Optional[Iterable[float]] = None,
    amount_col: str | None = None,
    amount_column: str = "SumBeløp",
    bilag_col: str = "Bilag",
    threshold: float | int | None = None,
    use_abs: bool = True,
    confidence_factor: float | None = None,
    sample_size: int | None = None,
) -> SpecificSelectionRecommendation:
    """Beregn spesifikt utvalg og anbefalt tilleggstrekk.

    Logikk (testet):
    - Bilag med |beløp| >= tolerable_error tas alltid med i spesifikt utvalg.
    - additional_n = ceil((remaining_value / tolerable_error) * confidence_factor)
      der remaining_value er bokført verdi *etter* at spesifikt utvalg er tatt ut.

    Parametre:
        bilag_df: DataFrame på bilag-nivå (kolonne "SumBeløp" som default)
        bilag_values: Alternativt en Series/itererbar med bilag-summer.
                     Hvis Series brukes index som bilag-id.
        tolerable_error / threshold: Tolererbar feil (positivt tall)
        confidence_factor: Numerisk faktor (f.eks. 1.6) brukt i formelen over.
        sample_size: Valgfritt. Hvis satt, tolkes som ønsket total_n (minst specific_count).

    Returnerer:
        SpecificSelectionRecommendation
    """

    # Backwards compat: noen kaller "threshold"
    if tolerable_error is None and threshold is not None:
        tolerable_error = threshold

    tol_abs = abs(float(tolerable_error or 0.0))

    # Normaliser til en Series med beløp og en Series med bilag-id'er
    specific_df = None
    remaining_df = None

    if bilag_values is not None:
        if isinstance(bilag_values, pd.Series):
            amounts = pd.to_numeric(bilag_values, errors="coerce").fillna(0.0)
        else:
            seq = list(bilag_values)
            amounts = pd.to_numeric(pd.Series(seq, index=list(range(len(seq)))), errors="coerce").fillna(0.0)

        metric = amounts.abs() if use_abs else amounts
        if tol_abs > 0.0:
            mask_specific = metric >= tol_abs
        else:
            mask_specific = pd.Series([False] * len(metric), index=metric.index)

        specific_bilag = list(mask_specific[mask_specific].index)
        specific_count = int(mask_specific.sum())
        remaining_count = int(len(metric) - specific_count)

        specific_value = float(metric.loc[mask_specific].sum()) if len(metric) else 0.0
        remaining_value = float(metric.loc[~mask_specific].sum()) if len(metric) else 0.0
        total_value = float(metric.sum()) if len(metric) else 0.0

    else:
        df_in = bilag_df if isinstance(bilag_df, pd.DataFrame) else pd.DataFrame()
        if df_in.empty:
            return SpecificSelectionRecommendation(
                tolerable_error=tol_abs,
                confidence_factor=confidence_factor,
                use_abs=use_abs,
                specific_bilag=[],
                specific_count=0,
                remaining_count=0,
                specific_value=0.0,
                remaining_value=0.0,
                total_value=0.0,
                additional_n=0,
                total_n=0,
                specific_df=df_in.copy(),
                remaining_df=df_in.copy(),
            )

        col = amount_col or amount_column
        if col not in df_in.columns:
            raise KeyError(col)

        amounts = pd.to_numeric(df_in[col], errors="coerce").fillna(0.0)
        metric = amounts.abs() if use_abs else amounts

        if tol_abs > 0.0:
            mask_specific = metric >= tol_abs
        else:
            mask_specific = pd.Series([False] * len(metric), index=df_in.index)

        # Hent bilag-id fra kolonne hvis mulig, ellers index
        if bilag_col in df_in.columns:
            specific_bilag = df_in.loc[mask_specific, bilag_col].tolist()
        else:
            specific_bilag = df_in.index[mask_specific].tolist()

        specific_count = int(mask_specific.sum())
        remaining_count = int(len(metric) - specific_count)

        specific_value = float(metric.loc[mask_specific].sum())
        remaining_value = float(metric.loc[~mask_specific].sum())
        total_value = float(metric.sum())

        specific_df, remaining_df = split_specific_selection_by_tolerable_error(
            df_in,
            tol_abs,
            amount_col=amount_col,
            amount_column=amount_column,
            use_abs=use_abs,
        )

    # additional_n: enten fra sample_size (overstyring) eller beregning
    additional_n = 0
    if sample_size is not None:
        desired_total = max(int(sample_size), int(specific_count))
        additional_n = max(desired_total - int(specific_count), 0)
        total_n = desired_total
    else:
        # I nettobeløp-modus (use_abs=False) kan rest-populasjonen ha negativt
        # fortegn (f.eks. kreditposter). Utvalgsstørrelse bør fortsatt beregnes
        # ut fra størrelsen |beløp|.
        remaining_value_for_n = abs(float(remaining_value))

        if confidence_factor is not None and tol_abs > 0.0 and remaining_value_for_n > 0.0:
            cf = float(confidence_factor)
            additional_n = int(math.ceil((remaining_value_for_n / tol_abs) * cf))
        else:
            additional_n = 0
        # Ikke trekk mer enn det som finnes igjen
        additional_n = min(additional_n, int(remaining_count))
        total_n = int(specific_count + additional_n)

    return SpecificSelectionRecommendation(
        tolerable_error=tol_abs,
        confidence_factor=confidence_factor,
        use_abs=use_abs,
        specific_bilag=list(specific_bilag),
        specific_count=int(specific_count),
        remaining_count=int(remaining_count),
        specific_value=float(specific_value),
        remaining_value=float(remaining_value),
        total_value=float(total_value),
        additional_n=int(additional_n),
        total_n=int(total_n),
        specific_df=specific_df,
        remaining_df=remaining_df,
    )

def recommend_random_sample_size_net_basis(
    population_value_net: float,
    population_count: int,
    *,
    tolerable_error: float,
    confidence_factor: float,
) -> int:
    """Anbefal størrelse på tilfeldig trekk basert på netto (signert) populasjonsverdi.

    Dette er logikken som brukes i SelectionStudio når vi har tatt ut "spesifikk utvalg"
    (bilag der |beløp| >= tolererbar feil) og skal anbefale antall bilag i tilfeldig trekk.

    Prinsipp:
      - Populasjonsverdi = netto sum (signert). Kreditposter (f.eks. salgsinntekter) er ofte negative.
      - Formelen bruker |netto| for å få positiv størrelse i beregningen.
      - Returnerer 0 når grunnlaget ikke gir mening (tom populasjon, tolererbar feil <= 0, eller netto = 0).
      - Resultatet clamps til [1, population_count] når beregningen gir > 0.

    Parametre:
        population_value_net: netto (signert) bokført verdi
        population_count: antall bilag i populasjonen (rest etter spesifikk)
        tolerable_error: tolererbar feil (>0)
        confidence_factor: konfidensfaktor (f.eks. 1.6)

    """
    try:
        n = int(population_count or 0)
    except Exception:
        n = 0
    if n <= 0:
        return 0

    tol = abs(float(tolerable_error or 0.0))
    if tol <= 0.0:
        return 0

    basis_value = abs(float(population_value_net or 0.0))
    if basis_value <= 0.0:
        return 0

    try:
        cf = float(confidence_factor)
    except Exception:
        cf = 1.0

    suggested = int(math.ceil((basis_value / tol) * cf))
    return min(max(suggested, 1), n)


def compute_net_basis_recommendation(
    bilag_df: pd.DataFrame,
    *,
    tolerable_error: float,
    confidence_factor: float,
    amount_col: str = "SumBeløp",
) -> dict[str, Any]:
    """Pure helper: beregn anbefaling (spesifikk + tilfeldig) uten GUI-avhengigheter.

    - Spesifikk: |beløp| >= tolererbar feil
    - Restverdi: netto (signert) sum av beløp i restpopulasjonen
    - Tilfeldig n: basert på |netto rest| og konfidensfaktor

    Returnerer dict med:
      n_specific, n_random, n_total, remaining_net, remaining_df
    """
    if bilag_df is None or bilag_df.empty:
        return {
            "n_specific": 0,
            "n_random": 0,
            "n_total": 0,
            "remaining_net": 0.0,
            "remaining_df": pd.DataFrame(),
        }

    # Spesifikk utvelgelse basert på absolutt verdi (uavhengig av fortegn)
    spec_info = compute_specific_selection_recommendation(
        bilag_df,
        tolerable_error,
        use_abs=True,
        amount_column=amount_col,
    )
    n_specific = int(spec_info["n_specific"] or 0)
    remaining_df = spec_info.get("remaining_df", None)
    if remaining_df is None:
        remaining_df = pd.DataFrame()

    if remaining_df.empty or amount_col not in remaining_df.columns:
        remaining_net = 0.0
    else:
        remaining_net = float(pd.to_numeric(remaining_df[amount_col], errors="coerce").fillna(0.0).sum())

    n_random = recommend_random_sample_size_net_basis(
        remaining_net,
        int(len(remaining_df)),
        tolerable_error=tolerable_error,
        confidence_factor=confidence_factor,
    )
    n_total = int(n_specific + n_random)

    return {
        "n_specific": n_specific,
        "n_random": int(n_random),
        "n_total": int(n_total),
        "remaining_net": float(remaining_net),
        "remaining_df": remaining_df,
    }

def build_bilag_dataframe(
    df: pd.DataFrame,
    *,
    bilag_col: str = "Bilag",
    amount_col: str = "Beløp",
    date_col: str = "Dato",
    text_col: str = "Tekst",
) -> pd.DataFrame:
    """Bygg et bilag-nivå DataFrame fra transaksjonslinjer.

    Forventer minst kolonnene:
      - bilag_col (default: "Bilag")
      - amount_col (default: "Beløp")

    Returnerer et DataFrame med (minst) kolonnene:
      - Bilag
      - SumBeløp

    Hvis Dato/Tekst finnes, tas første forekomst pr bilag for visning.
    """
    if df is None or df.empty:
        cols = [bilag_col, "SumBeløp"]
        # Bevar disse hvis de er standardkolonner
        if date_col:
            cols.insert(1, date_col)
        if text_col:
            cols.insert(2, text_col)
        return pd.DataFrame(columns=cols)

    # Litt robusthet for "Belop" uten norsk tegn (noen Excel-kilder)
    amt_col = amount_col
    if amt_col not in df.columns and amt_col == "Beløp" and "Belop" in df.columns:
        amt_col = "Belop"

    if bilag_col not in df.columns:
        raise KeyError(bilag_col)
    if amt_col not in df.columns:
        raise KeyError(amount_col)

    work = df.copy()
    work[amt_col] = pd.to_numeric(work[amt_col], errors="coerce").fillna(0.0)

    agg: dict[str, str] = {amt_col: "sum"}
    if date_col and date_col in work.columns:
        agg[date_col] = "first"
    if text_col and text_col in work.columns:
        agg[text_col] = "first"

    out = (
        work.groupby(bilag_col, dropna=False, as_index=False)
        .agg(agg)
        .rename(columns={amt_col: "SumBeløp"})
    )

    # Sett en stabil kolonnerekkefølge
    ordered_cols = [bilag_col]
    if date_col and date_col in out.columns:
        ordered_cols.append(date_col)
    if text_col and text_col in out.columns:
        ordered_cols.append(text_col)
    ordered_cols.append("SumBeløp")
    out = out[ordered_cols]
    return out


def stratify_bilag_sums(
    values: pd.Series | pd.DataFrame,
    *,
    method: str = "quantile",
    k: int = 3,
    use_abs: bool = True,
    amount_col: str = "SumBeløp",
) -> tuple[Any, Any, Any]:
    """Stratifiser bilag-summer.

    - Hvis `values` er en Series: returnerer (groups, interval_map, stats_df)
      i samme format som `stratifiering.stratify_values`.

    - Hvis `values` er en DataFrame med `amount_col`: returnerer
      (summary_df, bilag_out_df, interval_map) der bilag_out_df får kolonnene
      "Gruppe" og "Intervall".

    Dette er en adapter for å gjøre GUI/testene robuste mot at stratifiering
    opererer på en kolonne som heter "Beløp" i transaksjonsdata, mens GUI-et
    ofte jobber med summer på bilag-nivå ("SumBeløp").
    """
    kk = max(int(k), 1)

    if isinstance(values, pd.Series):
        s = pd.to_numeric(values, errors="coerce").fillna(0.0)
        metric = s.abs() if use_abs else s
        groups, interval_map, stats_df = _stratify_values(metric, method=method, k=kk)
        return groups, interval_map, stats_df

    if isinstance(values, pd.DataFrame):
        if amount_col not in values.columns:
            raise KeyError(amount_col)
        s = pd.to_numeric(values[amount_col], errors="coerce").fillna(0.0)
        metric = s.abs() if use_abs else s
        groups, interval_map, stats_df = _stratify_values(metric, method=method, k=kk)

        out = values.copy()
        grp_series = pd.Series(index=out.index, dtype=object)
        for grp_label, mask in groups:
            idxs = mask[mask].index
            grp_series.loc[idxs] = grp_label
        out["Gruppe"] = grp_series
        out["Intervall"] = out["Gruppe"].map(interval_map).fillna("")

        summary = stats_df.copy()
        if "Gruppe" in summary.columns:
            summary["Intervall"] = summary["Gruppe"].map(interval_map).fillna("")
        return summary, out, interval_map

    raise TypeError(f"values må være pd.Series eller pd.DataFrame, fikk {type(values)!r}")

@dataclass
class _Recommendation:
    conf_factor: float
    n_specific: int
    n_random_recommended: int
    n_total_recommended: int
    population_value_remaining: float


class SelectionStudio(ttk.Frame):
    """GUI for stratified voucher selection.

    Backward compatible constructor
    ------------------------------
    The project has historically called SelectionStudio in a few different ways.
    This class accepts all of the following:

    * ``SelectionStudio(master, df_base, on_commit, df_all)`` (legacy)
    * ``SelectionStudio(master, df_base, on_commit=..., df_all=...)``
    * ``SelectionStudio(master, df_base=pd.DataFrame(), on_commit_selection=...)``
    * ``SelectionStudio(master, on_commit_selection=...)`` (data loaded later)
    """

    # --- constructor / public API -------------------------------------------------

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        # Parse legacy positional arguments
        df_base: Optional[pd.DataFrame] = None
        df_all: Optional[pd.DataFrame] = None
        on_commit: Optional[Callable[[pd.DataFrame], None]] = None

        if len(args) >= 1 and isinstance(args[0], pd.DataFrame):
            df_base = args[0]
        if len(args) >= 2 and callable(args[1]):
            on_commit = args[1]
        if len(args) >= 3 and isinstance(args[2], pd.DataFrame):
            df_all = args[2]

        # Keyword overrides / aliases
        df_base = kwargs.pop("df_base", df_base)
        df_all = kwargs.pop("df_all", df_all)

        # Callback aliases (også for gamle navn brukt i ui_main)
        on_commit_kw = kwargs.pop("on_commit", None)
        on_commit_selection_kw = kwargs.pop("on_commit_selection", None)
        on_commit_sample_kw = kwargs.pop("on_commit_sample", None)
        on_commit_selection_kw2 = kwargs.pop("on_commitSample", None)  # defensive
        cb = (
            on_commit_selection_kw
            or on_commit_sample_kw
            or on_commit_kw
            or on_commit_selection_kw2
            or on_commit
        )

        super().__init__(master, **kwargs)

        self._on_commit_selection: Optional[Callable[[pd.DataFrame], None]] = cb

        # Data
        self._df_base: pd.DataFrame = pd.DataFrame()
        self._df_all: pd.DataFrame = pd.DataFrame()
        self._df_filtered: pd.DataFrame = pd.DataFrame()
        self._bilag_df: pd.DataFrame = pd.DataFrame()
        self._df_sample: pd.DataFrame = pd.DataFrame()

        # Internal state
        self._last_suggested_n: Optional[int] = None
        self._rng = random.Random(42)  # deterministic for repeatability

        # UI vars
        # Retning: i revisjon er "Alle" (netto) default. Vi tilbyr to enkle
        # av/på-filter i stedet for en rullgardin, for å redusere risiko for feilvalg.
        self.var_only_debit = tk.BooleanVar(value=False)
        self.var_only_credit = tk.BooleanVar(value=False)

        # Backwards compatible: behold var_direction for eldre kode/tester som leser den.
        self.var_direction = tk.StringVar(value="Alle")

        self.var_min_amount = tk.StringVar(value="")
        self.var_max_amount = tk.StringVar(value="")

        # Bruk absolutt beløp var tidligere en bruker-toggle. I revisjon er netto
        # standard, og vi skjuler derfor denne fra UI. Den beholdes kun for
        # bakoverkompatibilitet, men brukes ikke i filter-/beregningslogikk.
        self.var_use_abs = tk.BooleanVar(value=False)  # Kandidat til fjerning – ubrukt i UI

        # Intern guard for å unngå rekursjon når vi synkroniserer checkbokser -> var_direction
        self._dir_sync_guard = False
        self.var_only_debit.trace_add("write", lambda *_: self._on_direction_checkbox_changed("debit"))
        self.var_only_credit.trace_add("write", lambda *_: self._on_direction_checkbox_changed("credit"))

        self.var_risk = tk.StringVar(value="Middels")
        self.var_confidence = tk.StringVar(value="90%")
        self.var_tolerable_error = tk.StringVar(value="")
        self.var_method = tk.StringVar(value="quantile")
        self.var_k = tk.IntVar(value=3)

        # Manuelle strata-grenser (brukes kun når metode = 'custom')
        self.var_custom_bounds = tk.StringVar(value="")
        self.var_custom_bounds_hint = tk.StringVar(value="")
        self._custom_bounds_sync_guard = False

        self.var_sample_n = tk.IntVar(value=0)  # 0 = auto

        self.var_recommendation = tk.StringVar(value="")
        self.var_base_summary = tk.StringVar(value="Ingen data lastet.")

        self._build_ui()

        # Vis/skjul kontroller for manuelle strata-grenser
        self.var_method.trace_add("write", lambda *_: self._update_method_controls())
        self.var_custom_bounds.trace_add("write", lambda *_: self._update_method_controls())
        self._update_method_controls()

        # Bindings to keep recommendation up to date
        for v in (
            self.var_direction,
            self.var_min_amount,
            self.var_max_amount,
            self.var_risk,
            self.var_confidence,
            self.var_tolerable_error,
            self.var_method,
            self.var_k,
            self.var_custom_bounds,
        ):
            v.trace_add("write", lambda *_: self._schedule_refresh())

        # Load initial data if provided
        if df_base is not None and not df_base.empty:
            self.load_data(df_base=df_base, df_all=df_all)
        elif df_all is not None and not df_all.empty:
            # Some callers provide only df_all
            self.load_data(df_base=df_all, df_all=df_all)

    def load_data(self, *args: Any, **kwargs: Any) -> None:
        """Load/replace the dataset used for selection.

        Backwards compatible with multiple call styles:

        * ``load_data(df_base, df_all=df_all)``
        * ``load_data(df_all, df_base=df_base)``
        * ``load_data(df_base, df_all)`` or ``load_data(df_all, df_base)``
        """

        df_base = kwargs.pop("df_base", None)
        df_all = kwargs.pop("df_all", None)

        # Positional fallbacks
        if len(args) == 1 and isinstance(args[0], pd.DataFrame):
            if df_base is None and df_all is None:
                df_base = args[0]
        elif len(args) == 2 and all(isinstance(a, pd.DataFrame) for a in args):
            a0, a1 = args
            # Infer which is the "all" dataframe by size (rows)
            if df_base is None and df_all is None:
                if len(a0) >= len(a1):
                    df_all = a0
                    df_base = a1
                else:
                    df_all = a1
                    df_base = a0
            else:
                df_base = df_base or a0
                df_all = df_all or a1

        if df_base is None:
            df_base = pd.DataFrame()
        if df_all is None:
            df_all = df_base

        self._df_base = df_base.copy()
        self._df_all = df_all.copy()
        self._df_sample = pd.DataFrame()

        # Sensible default tolerable error if empty: 5% of population book value (rounded).
        # I praksis er tolererbar feil en input fra revisjonsplanleggingen, men dette gir
        # et "ikke-null" forslag når brukeren ikke har fylt inn noe.
        if not (self.var_tolerable_error.get() or "").strip() and not self._df_base.empty:
            try:
                metrics = compute_population_metrics(self._df_base)

                # Netto er standard i revisjon, men dersom netto summerer til ~0 (f.eks. clearing),
                # faller vi tilbake til absolutt-sum for å unngå et tomt forslag.
                base_value = abs(float(getattr(metrics, "sum_net", 0.0) or 0.0))
                if base_value <= 0.0:
                    base_value = float(getattr(metrics, "sum_abs", 0.0) or 0.0)

                default_tol = max(int(round(base_value * 0.05)), 0)
                if default_tol > 0:
                    self.var_tolerable_error.set(format_amount_input_no(default_tol))
            except Exception:
                pass

        self._schedule_refresh(immediate=True)

    # --- UI ----------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)

        # Top summary
        lbl = ttk.Label(self, textvariable=self.var_base_summary)
        lbl.grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 4))

        # Left panel
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="nsw", padx=(8, 4), pady=(0, 8))
        left.columnconfigure(0, weight=1)

        # --- Filters section
        lf_filters = ttk.LabelFrame(left, text="Filtre")
        lf_filters.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        lf_filters.columnconfigure(1, weight=1)

        ttk.Label(lf_filters, text="Retning").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        frm_dir = ttk.Frame(lf_filters)
        frm_dir.grid(row=0, column=1, sticky="w", padx=6, pady=(6, 2))
        ttk.Checkbutton(frm_dir, text="Kun debet", variable=self.var_only_debit).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(frm_dir, text="Kun kredit", variable=self.var_only_credit).grid(
            row=0, column=1, sticky="w", padx=(12, 0)
        )

        ttk.Label(lf_filters, text="Beløp (netto) fra/til").grid(row=1, column=0, sticky="w", padx=6, pady=(6, 2))
        frm_amt = ttk.Frame(lf_filters)
        frm_amt.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 2))
        frm_amt.columnconfigure(0, weight=1)
        frm_amt.columnconfigure(2, weight=1)
        ttk.Entry(frm_amt, textvariable=self.var_min_amount, width=10).grid(row=0, column=0, sticky="ew")
        ttk.Label(frm_amt, text="til").grid(row=0, column=1, padx=4)
        ttk.Entry(frm_amt, textvariable=self.var_max_amount, width=10).grid(row=0, column=2, sticky="ew")

        # --- Selection section
        lf_sel = ttk.LabelFrame(left, text="Utvalg")
        lf_sel.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        lf_sel.columnconfigure(1, weight=1)

        ttk.Label(lf_sel, text="Risiko").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        cmb_risk = ttk.Combobox(
            lf_sel,
            textvariable=self.var_risk,
            values=["Lav", "Middels", "Høy"],
            width=12,
            state="readonly",
        )
        cmb_risk.grid(row=0, column=1, sticky="ew", padx=6, pady=(6, 2))

        ttk.Label(lf_sel, text="Sikkerhet").grid(row=1, column=0, sticky="w", padx=6, pady=(6, 2))
        cmb_conf = ttk.Combobox(
            lf_sel,
            textvariable=self.var_confidence,
            values=["80%", "90%", "95%"],
            width=12,
            state="readonly",
        )
        cmb_conf.grid(row=1, column=1, sticky="ew", padx=6, pady=(6, 2))

        ttk.Label(lf_sel, text="Tolererbar feil").grid(row=2, column=0, sticky="w", padx=6, pady=(6, 2))
        ent_tol = ttk.Entry(lf_sel, textvariable=self.var_tolerable_error)
        ent_tol.grid(row=2, column=1, sticky="ew", padx=6, pady=(6, 2))
        ent_tol.bind("<FocusOut>", lambda _e: self._format_tolerable_error_entry())

        ttk.Label(lf_sel, text="Metode").grid(row=3, column=0, sticky="w", padx=6, pady=(6, 2))
        cmb_method = ttk.Combobox(
            lf_sel,
            textvariable=self.var_method,
            values=["quantile", "equal_width", "custom"],
            state="readonly",
            width=12,
        )
        cmb_method.grid(row=3, column=1, sticky="ew", padx=6, pady=(6, 2))

        ttk.Label(lf_sel, text="Antall grupper (k)").grid(row=4, column=0, sticky="w", padx=6, pady=2)
        spn_k = ttk.Spinbox(lf_sel, from_=1, to=12, textvariable=self.var_k, width=6)
        spn_k.grid(row=4, column=1, sticky="w", padx=6, pady=2)
        self._spn_k = spn_k

        # Manuelle strata-grenser (kun når metode = 'custom')
        self.frm_custom_bounds = ttk.Frame(lf_sel)
        self.frm_custom_bounds.grid(row=5, column=0, columnspan=2, sticky="ew", padx=6, pady=(6, 2))
        self.frm_custom_bounds.columnconfigure(1, weight=1)

        ttk.Label(self.frm_custom_bounds, text="Strata-grenser").grid(row=0, column=0, sticky="w")
        self.ent_custom_bounds = ttk.Entry(self.frm_custom_bounds, textvariable=self.var_custom_bounds)
        self.ent_custom_bounds.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        self.ent_custom_bounds.bind("<FocusOut>", lambda _e: self._format_custom_bounds_entry())

        self.lbl_custom_bounds_hint = ttk.Label(
            self.frm_custom_bounds,
            textvariable=self.var_custom_bounds_hint,
            wraplength=260,
        )
        self.lbl_custom_bounds_hint.grid(row=1, column=0, columnspan=2, sticky="w", pady=(2, 0))

        ttk.Label(lf_sel, text="Utvalgsstørrelse").grid(row=6, column=0, sticky="w", padx=6, pady=2)
        spn_n = ttk.Spinbox(
            lf_sel, from_=0, to=9999, textvariable=self.var_sample_n, width=6, command=self._sample_size_touched
        )
        spn_n.grid(row=6, column=1, sticky="w", padx=6, pady=2)
        spn_n.bind("<KeyRelease>", lambda _e: self._sample_size_touched())
        spn_n.bind("<FocusOut>", lambda _e: self._sample_size_touched())

        lbl_rec = ttk.Label(lf_sel, textvariable=self.var_recommendation, wraplength=260, justify="left")
        lbl_rec.grid(row=7, column=0, columnspan=2, sticky="w", padx=6, pady=(6, 6))

        # Buttons
        frm_btn = ttk.Frame(left)
        frm_btn.grid(row=2, column=0, sticky="ew")
        frm_btn.columnconfigure(0, weight=1)
        frm_btn.columnconfigure(1, weight=1)

        ttk.Button(frm_btn, text="Kjør utvalg", command=self._run_selection).grid(
            row=0, column=0, sticky="ew", padx=(0, 4), pady=(0, 4)
        )
        ttk.Button(frm_btn, text="Legg i utvalg", command=self._commit_selection).grid(
            row=0, column=1, sticky="ew", padx=(4, 0), pady=(0, 4)
        )
        ttk.Button(frm_btn, text="Eksporter Excel", command=self._export_excel).grid(
            row=1, column=0, columnspan=2, sticky="ew"
        )

        # Right panel (tabs)
        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew", padx=(4, 8), pady=(0, 8))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.nb = ttk.Notebook(right)
        self.nb.grid(row=0, column=0, sticky="nsew")

        # Tab: Utvalg
        tab_utvalg = ttk.Frame(self.nb)
        tab_utvalg.columnconfigure(0, weight=1)
        tab_utvalg.rowconfigure(1, weight=1)
        self.nb.add(tab_utvalg, text="Utvalg")

        frm_top = ttk.Frame(tab_utvalg)
        frm_top.grid(row=0, column=0, sticky="ew", pady=(4, 0))
        frm_top.columnconfigure(0, weight=1)
        ttk.Button(frm_top, text="Vis kontorer", command=self._show_accounts).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(frm_top, text="Drilldown", command=self._open_drilldown).grid(row=0, column=2, padx=(6, 0))

        columns = ("Bilag", "Dato", "Tekst", "SumBeløp", "Gruppe", "Intervall")
        self.tree = ttk.Treeview(tab_utvalg, columns=columns, show="headings", height=18)
        # Vis negative beløp (kredit) tydeligere
        try:
            self.tree.tag_configure("neg", foreground="red")
        except Exception:
            pass
        for c in columns:
            self.tree.heading(c, text=c)
            self.tree.column(c, anchor="w", width=120)
        self.tree.column("Bilag", width=80, anchor="e")
        self.tree.column("SumBeløp", width=120, anchor="e")
        self.tree.column("Dato", width=100, anchor="w")

        vsb = ttk.Scrollbar(tab_utvalg, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")

        # Double-click opens drilldown for the selected bilag
        self.tree.bind("<Double-1>", lambda _evt: self._open_drilldown())

        # Tab: Grupper
        tab_grp = ttk.Frame(self.nb)
        tab_grp.columnconfigure(0, weight=1)
        tab_grp.rowconfigure(0, weight=1)
        self.nb.add(tab_grp, text="Grupper")

        grp_cols = ("Gruppe", "Intervall", "Antall", "SumBeløp")
        self.tree_groups = ttk.Treeview(tab_grp, columns=grp_cols, show="headings", height=10)
        for c in grp_cols:
            self.tree_groups.heading(c, text=c)
            self.tree_groups.column(c, anchor="w", width=160)
        self.tree_groups.column("Antall", anchor="e", width=80)
        self.tree_groups.column("SumBeløp", anchor="e", width=120)
        vsb2 = ttk.Scrollbar(tab_grp, orient="vertical", command=self.tree_groups.yview)
        self.tree_groups.configure(yscrollcommand=vsb2.set)
        self.tree_groups.grid(row=0, column=0, sticky="nsew")
        vsb2.grid(row=0, column=1, sticky="ns")

    def _on_direction_checkbox_changed(self, changed: str) -> None:
        """Synkroniser checkbokser (Kun debet/kun kredit) til var_direction.

        * Ingen valgt  -> "Alle"
        * Kun debet    -> "Debet"
        * Kun kredit   -> "Kredit"

        Boksene er gjensidig utelukkende for å unngå tvetydig filtrering.
        """

        if getattr(self, "_dir_sync_guard", False):
            return

        self._dir_sync_guard = True
        try:
            only_debit = bool(self.var_only_debit.get())
            only_credit = bool(self.var_only_credit.get())

            # Hvis bruker slår på én, slår vi av den andre
            if changed == "debit" and only_debit:
                if only_credit:
                    self.var_only_credit.set(False)
                self.var_direction.set("Debet")
                return

            if changed == "credit" and only_credit:
                if only_debit:
                    self.var_only_debit.set(False)
                self.var_direction.set("Kredit")
                return

            # Hvis en boks ble slått av: sett retning basert på gjeldende state
            only_debit = bool(self.var_only_debit.get())
            only_credit = bool(self.var_only_credit.get())

            if only_debit:
                self.var_direction.set("Debet")
            elif only_credit:
                self.var_direction.set("Kredit")
            else:
                self.var_direction.set("Alle")
        finally:
            self._dir_sync_guard = False

    # --- custom strata (manuelle grenser) --------------------------------------

    def _update_method_controls(self) -> None:
        """Vis/skjul felt for manuelle strata-grenser og aktiver/deaktiver k."""
        method = (self.var_method.get() or "quantile").strip().lower()
        is_custom = method == "custom"

        # Vis/skjul frame
        if hasattr(self, "frm_custom_bounds"):
            try:
                if is_custom:
                    self.frm_custom_bounds.grid()
                else:
                    self.frm_custom_bounds.grid_remove()
            except Exception:
                pass

        # Aktiver/deaktiver k
        if hasattr(self, "_spn_k") and self._spn_k is not None:
            try:
                self._spn_k.configure(state="disabled" if is_custom else "normal")
            except Exception:
                pass

        # Oppdater hint
        if not hasattr(self, "var_custom_bounds_hint"):
            return

        if not is_custom:
            self.var_custom_bounds_hint.set("")
            return

        raw = (self.var_custom_bounds.get() or "").strip()
        if not raw:
            self.var_custom_bounds_hint.set("Bruk ';' mellom grenser, f.eks. 100 000; 500 000")
            return

        bounds = parse_custom_strata_bounds(raw)
        if not bounds:
            self.var_custom_bounds_hint.set("Kunne ikke tolke grenser. Bruk ';' mellom tall, f.eks. 100 000; 500 000")
            return

        self.var_custom_bounds_hint.set(
            no_break_spaces_in_numbers(f"{len(bounds)} grenser → {len(bounds) + 1} grupper")
        )

    def _format_custom_bounds_entry(self) -> None:
        """Normaliser input (sorter, fjern duplikater) når feltet mister fokus."""
        if getattr(self, "_custom_bounds_sync_guard", False):
            return

        raw = (self.var_custom_bounds.get() or "").strip()
        if not raw:
            return

        bounds = parse_custom_strata_bounds(raw)
        if not bounds:
            return

        normalized = format_custom_strata_bounds(bounds)
        if normalized and normalized != raw:
            try:
                self._custom_bounds_sync_guard = True
                self.var_custom_bounds.set(normalized)
            finally:
                self._custom_bounds_sync_guard = False

    def _get_custom_bounds(self) -> list[float]:
        """Hent manuelle strata-grenser fra UI."""
        bounds = parse_custom_strata_bounds(self.var_custom_bounds.get())
        return bounds

    def _stratify_remaining_values(self, values: pd.Series) -> tuple[list[tuple[Any, pd.Series]], dict[str, str], pd.DataFrame]:
        """Stratifiserer restpopulasjonen basert på valgt metode."""
        method = (self.var_method.get() or "quantile").strip().lower()
        if method == "custom":
            bounds = self._get_custom_bounds()
            return stratify_values_custom_bounds(values, bounds=bounds)

        k = int(self.var_k.get() or 3)
        return stratify_bilag_sums(values, method=method, k=k, use_abs=False)


    # --- refresh / recommendation -------------------------------------------------

    def _schedule_refresh(self, immediate: bool = False) -> None:
        if immediate:
            self._refresh_all()
            return

        # debounce
        if hasattr(self, "_refresh_after_id") and self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
        self._refresh_after_id = self.after(200, self._refresh_all)

    def _refresh_all(self) -> None:
        # Apply filters and update base summary + recommendation
        self._df_filtered = self._apply_filters(self._df_base)

        try:
            base_metrics = compute_population_metrics(self._df_base)
            work_metrics = compute_population_metrics(self._df_filtered)
            text = build_population_summary_text(base_metrics, work_metrics, abs_basis=False)
        except Exception:
            text = "Ingen data lastet."
        self.var_base_summary.set(text)

        rec = self._compute_recommendation()
        self._update_recommendation_text(rec)
        # Vis en liten "spesifikk/rest" oppsummering under anbefalingen.
        # Viktig: Spesifikk utvelgelse baseres på |SumBeløp| >= tolererbar feil,
        # mens nettobeløp brukes som standard for populasjonsverdi.
        try:
            tol_abs = self._get_tolerable_error_value()
            if getattr(self, "_bilag_df", None) is not None and not self._bilag_df.empty:
                split_text = self._build_bilag_split_text(self._bilag_df, tolerable_error=tol_abs)
                if split_text:
                    current = self.var_recommendation.get()
                    self.var_recommendation.set(no_break_spaces_in_numbers((current + "\n\n" + split_text).strip()))
        except Exception:
            pass

        self._refresh_groups_table()

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bruk filter-parametre fra UI og returner filtrert DataFrame."""
        if df is None or df.empty:
            return pd.DataFrame()

        direction = (self.var_direction.get() or "Alle").strip()
        min_value = self.var_min_amount.get()
        max_value = self.var_max_amount.get()

        # Beløp fra/til skal filtrere på netto (signert) – ikke absolutt.
        df_filtered, _summary = filter_selectionstudio_dataframe(
            df,
            direction=direction,
            min_value=min_value,
            max_value=max_value,
            use_abs=False,
        )
        return df_filtered

    def _build_bilag_split_text(self, bilag_df: pd.DataFrame, *, tolerable_error: float) -> str:
        """Bygg en kompakt tekst som viser populasjon/spesifikk/rest på bilag-nivå.

        Viktige prinsipper:
        - Spesifikk utvelgelse: |SumBeløp| >= tolererbar feil (alltid absolutt for terskel).
        - Populasjonsverdi: netto (signert) er standard i revisjon.
        - Utvalgsberegningen for tilfeldig trekk bruker |netto restpopulasjon|.
        """

        if bilag_df is None or bilag_df.empty or "SumBeløp" not in bilag_df.columns:
            return ""

        tol = abs(float(tolerable_error or 0.0))
        amounts = pd.to_numeric(bilag_df["SumBeløp"], errors="coerce").fillna(0.0)

        n_total = int(len(bilag_df))
        net_total = float(amounts.sum())
        abs_total = float(amounts.abs().sum())

        if tol > 0.0:
            mask_spec = amounts.abs() >= tol
        else:
            mask_spec = pd.Series([False] * len(bilag_df), index=bilag_df.index)

        amounts_spec = amounts.loc[mask_spec]
        amounts_rem = amounts.loc[~mask_spec]

        n_spec = int(mask_spec.sum())
        n_rem = int(n_total - n_spec)

        net_spec = float(amounts_spec.sum()) if n_spec else 0.0
        abs_spec = float(amounts_spec.abs().sum()) if n_spec else 0.0

        net_rem = float(amounts_rem.sum()) if n_rem else 0.0
        abs_rem = float(amounts_rem.abs().sum()) if n_rem else 0.0

        tol_txt = fmt_amount_no(tol, decimals=0) if tol > 0 else "0"

        return (
            f"Populasjon (bilag): {fmt_int_no(n_total)} | Netto: {fmt_amount_no(net_total, decimals=0)} | Abs: {fmt_amount_no(abs_total, decimals=0)}\n"
            f"Spesifikk (|beløp| >= {tol_txt}): {fmt_int_no(n_spec)} | Netto: {fmt_amount_no(net_spec, decimals=0)} | Abs: {fmt_amount_no(abs_spec, decimals=0)}\n"
            f"Restpopulasjon: {fmt_int_no(n_rem)} | Netto: {fmt_amount_no(net_rem, decimals=0)} | Abs: {fmt_amount_no(abs_rem, decimals=0)}\n"
            f"Beregning tilfeldig trekk bruker |netto rest|: {fmt_amount_no(abs(net_rem), decimals=0)}"
        )

    def _compute_recommendation(self) -> _Recommendation:
        # Compute bilag-level df
        self._bilag_df = self._build_bilag_df(self._df_filtered)

        tol = self._get_tolerable_error_value()

        # Confidence factor (risk + confidence)
        risk_level = (self.var_risk.get() or "Middels").strip().lower()
        conf_level = self._parse_confidence_percent(self.var_confidence.get())
        conf_factor = confidence_factor(risk_level=risk_level, confidence_level=conf_level)

        rec_dict = compute_net_basis_recommendation(
            self._bilag_df,
            tolerable_error=tol,
            confidence_factor=float(conf_factor),
            amount_col="SumBeløp",
        )
        n_specific = int(rec_dict["n_specific"])
        n_random = int(rec_dict["n_random"])
        n_total = int(rec_dict["n_total"])
        remaining_net = float(rec_dict["remaining_net"])

        # Update the sample size spinbox default behavior
        current_n = int(self.var_sample_n.get() or 0)
        if current_n == 0 or (self._last_suggested_n is not None and current_n == self._last_suggested_n):
            self.var_sample_n.set(n_total)
        self._last_suggested_n = n_total

        return _Recommendation(
            conf_factor=float(conf_factor),
            n_specific=n_specific,
            n_random_recommended=int(n_random),
            n_total_recommended=int(n_total),
            population_value_remaining=float(remaining_net),
        )

    def _update_recommendation_text(self, rec: _Recommendation) -> None:
        tol = self._get_tolerable_error_value()
        parts: list[str] = []
        if tol > 0:
            parts.append(f"Tolererbar feil: {fmt_amount_no(tol, decimals=0)}")
        if rec.conf_factor:
            parts.append(f"Konfidensfaktor: {str(rec.conf_factor).replace('.', ',')}")
        parts.append(
            f"Forslag utvalg: {fmt_int_no(rec.n_total_recommended)} bilag"
            + (f" (inkl. {fmt_int_no(rec.n_specific)} spesifikk)" if rec.n_specific else "")
        )
        self.var_recommendation.set(no_break_spaces_in_numbers("\n".join(parts)))

    def _refresh_groups_table(self) -> None:
        # Groups are shown for the remaining bilag (excluding specific)
        for i in self.tree_groups.get_children():
            self.tree_groups.delete(i)

        if self._bilag_df is None or self._bilag_df.empty:
            return

        tol = self._get_tolerable_error_value()
        # Spesifikk utvelgelse baseres alltid på |SumBeløp| >= tolererbar feil.
        spec, remaining = split_specific_selection_by_tolerable_error(self._bilag_df, tol, use_abs=True)
        if remaining.empty:
            # Only specific
            if not spec.empty:
                sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
                self.tree_groups.insert("", "end", values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)))
            return

        # Stratifisering gjøres på absolutt beløp (gir pene, positive intervaller)
        values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
        try:
            groups, interval_map, stats_df = self._stratify_remaining_values(values)
        except Exception:
            return

        # Insert optional specific group first
        if not spec.empty:
            sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
            self.tree_groups.insert(
                "",
                "end",
                values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)),
            )

        # Stats per group
        # stats_df columns: Gruppe, Antall, Sum, Min, Max
        for _, row in stats_df.iterrows():
            grp = row.get("Gruppe")
            interval = interval_map.get(str(grp), "")
            self.tree_groups.insert(
                "",
                "end",
                values=(
                    str(grp),
                    interval,
                    int(row.get("Antall", 0)),
                    fmt_amount_no(float(row.get("Sum", 0.0))),
                ),
            )

    # --- selection ----------------------------------------------------------------

    def _run_selection(self) -> None:
        try:
            if self._df_filtered is None or self._df_filtered.empty:
                messagebox.showinfo("Utvalg", "Ingen data i grunnlaget. Velg konti/filtre først.")
                return

            bilag_df = self._bilag_df
            if bilag_df is None or bilag_df.empty:
                messagebox.showinfo("Utvalg", "Ingen bilag i grunnlaget.")
                return

            tol = self._get_tolerable_error_value()
            # Spesifikk utvelgelse baseres alltid på |SumBeløp| >= tolererbar feil.
            spec, remaining = split_specific_selection_by_tolerable_error(bilag_df, tol, use_abs=True)

            # Determine desired total sample size
            desired_total = int(self.var_sample_n.get() or 0)
            if desired_total <= 0:
                rec = self._compute_recommendation()
                desired_total = rec.n_total_recommended

            # Always include specific
            specific_ids = list(spec["Bilag"].tolist()) if not spec.empty else []
            desired_total = max(desired_total, len(specific_ids))

            n_random = desired_total - len(specific_ids)
            random_ids: list[Any] = []

            if n_random > 0 and not remaining.empty:
                random_ids = self._draw_stratified_sample(remaining, n_random)

            sample_ids_set = set(specific_ids) | set(random_ids)
            sample_df = bilag_df[bilag_df["Bilag"].isin(sample_ids_set)].copy()

            # Annotate sample with group/interval
            sample_df["Gruppe"] = ""
            sample_df["Intervall"] = ""
            if tol > 0 and not spec.empty:
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Gruppe"] = "Spesifikk"
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Intervall"] = f">= {fmt_amount_no(tol, 0)}"

            # Fill for random using stratification intervals
            if random_ids:
                # Stratifisering gjøres på absolutt beløp (pene, positive intervaller)
                rem_values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
                groups, interval_map, _stats = self._stratify_remaining_values(rem_values)
                # Map bilag -> group
                group_by_idx = pd.Series(index=remaining.index, dtype=object)
                for grp_label, mask in groups:
                    group_by_idx.loc[mask[mask].index] = grp_label
                # Apply to sample
                for idx, grp_label in group_by_idx.items():
                    bilag_id = remaining.loc[idx, "Bilag"]
                    if bilag_id in sample_ids_set and bilag_id not in specific_ids:
                        sample_df.loc[sample_df["Bilag"] == bilag_id, "Gruppe"] = str(grp_label)
                        sample_df.loc[sample_df["Bilag"] == bilag_id, "Intervall"] = interval_map.get(str(grp_label), "")

            # Sort by abs sum amount desc
            amounts_sort = pd.to_numeric(sample_df["SumBeløp"], errors="coerce").fillna(0.0)
            sample_df = sample_df.assign(_abs_sort=amounts_sort.abs()).sort_values("_abs_sort", ascending=False).drop(
                columns=["_abs_sort"]
            )

            self._df_sample = sample_df
            self._populate_tree(sample_df)
            self.nb.select(0)

        except Exception as e:
            messagebox.showerror("Utvalg", f"Kunne ikke kjøre utvalg.\n\n{e}")

    def _draw_stratified_sample(self, remaining_bilag_df: pd.DataFrame, n: int) -> list[Any]:
        """Draw a stratified sample of bilag IDs from remaining_bilag_df."""

        if n <= 0 or remaining_bilag_df.empty:
            return []

        n = min(n, len(remaining_bilag_df))

        # Stratifisering gjøres på absolutt beløp (pene, positive intervaller)
        values = pd.to_numeric(remaining_bilag_df["SumBeløp"], errors="coerce").fillna(0.0).abs()

        groups, _interval_map, _stats = self._stratify_remaining_values(values)

        # Allocate n proportionally by stratum size
        sizes = [int(mask.sum()) for _g, mask in groups]
        total = sum(sizes) or 1
        raw_alloc = [n * s / total for s in sizes]
        alloc = [int(round(x)) for x in raw_alloc]

        # Fix rounding drift
        diff = n - sum(alloc)
        while diff != 0:
            # Adjust the largest strata first
            idx = max(range(len(alloc)), key=lambda i: sizes[i])
            if diff > 0:
                alloc[idx] += 1
                diff -= 1
            else:
                if alloc[idx] > 0:
                    alloc[idx] -= 1
                    diff += 1
                else:
                    break

        chosen: list[Any] = []
        for (grp_label, mask), take in zip(groups, alloc):
            if take <= 0:
                continue
            idxs = list(mask[mask].index)
            self._rng.shuffle(idxs)
            chosen.extend(remaining_bilag_df.loc[idxs[:take], "Bilag"].tolist())
        # If we still have too few due to empty strata, fill randomly
        if len(chosen) < n:
            remaining_ids = [x for x in remaining_bilag_df["Bilag"].tolist() if x not in set(chosen)]
            self._rng.shuffle(remaining_ids)
            chosen.extend(remaining_ids[: n - len(chosen)])
        return chosen[:n]

    def _populate_tree(self, df: pd.DataFrame) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

        if df is None or df.empty:
            return

        for _, row in df.iterrows():
            bilag = row.get("Bilag", "")
            dato = row.get("Dato", "")
            tekst = row.get("Tekst", "")
            sum_belop = row.get("SumBeløp", 0.0)
            gruppe = row.get("Gruppe", "")
            intervall = row.get("Intervall", "")

            # Robust numerisk verdi + tag for negative beløp (kredit)
            try:
                sum_val = float(pd.to_numeric(sum_belop, errors="coerce"))
            except Exception:
                sum_val = 0.0
            if pd.isna(sum_val):
                sum_val = 0.0

            tags: tuple[str, ...] = ()
            if sum_val < 0:
                tags = ("neg",)

            self.tree.insert(
                "",
                "end",
                values=(
                    bilag,
                    str(dato)[:10] if pd.notna(dato) else "",
                    tekst,
                    fmt_amount_no(sum_val),
                    gruppe,
                    intervall,
                ),
                tags=tags,
            )

    def _commit_selection(self) -> None:
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showinfo("Utvalg", "Ingen utvalg å legge til.")
            return

        if self._on_commit_selection is None:
            messagebox.showinfo("Utvalg", "Ingen mottaker for utvalg (on_commit).")
            return

        try:
            self._on_commit_selection(self._df_sample.copy())
        except Exception as e:
            messagebox.showerror("Utvalg", f"Kunne ikke legge utvalg til.\n\n{e}")

    def _export_excel(self) -> None:
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showinfo("Eksporter", "Ingen utvalg å eksportere.")
            return

        # Fyll inn et fornuftig standard filnavn så brukeren slipper å skrive det selv.
        default_name = f"Utvalg_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
        initialdir = getattr(self, "_last_export_dir", "") or ""

        path = filedialog.asksaveasfilename(
            title="Lagre Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=default_name,
            initialdir=initialdir,
        )
        if not path:
            return

        # Husk sist brukte mappe (for neste eksport).
        try:
            self._last_export_dir = os.path.dirname(path)
        except Exception:
            pass

        try:
            export_to_excel(
                path,
                Utvalg=self._df_sample,
                Grunnlag=self._df_filtered,
            )
            messagebox.showinfo("Eksporter", "Eksportert.")
        except Exception as e:
            messagebox.showerror("Eksporter", f"Kunne ikke eksportere.\n\n{e}")

    def _show_accounts(self) -> None:
        """Vis en enkel kontosummering for nåværende (filtrerte) grunnlag."""

        df = self._df_filtered
        if df is None or df.empty:
            messagebox.showinfo("Kontorer", "Ingen data å vise.")
            return

        if "Konto" not in df.columns:
            messagebox.showinfo("Kontorer", "Datasettet mangler kolonnen 'Konto'.")
            return

        konto_col = "Konto"
        navn_col = "Kontonavn" if "Kontonavn" in df.columns else None

        gcols = [konto_col] + ([navn_col] if navn_col else [])
        agg = {
            "Rader": (konto_col, "size"),
            "Bilag": ("Bilag", "nunique") if "Bilag" in df.columns else (konto_col, "size"),
            "Sum": ("Beløp", "sum") if "Beløp" in df.columns else (konto_col, "size"),
        }

        try:
            summary = df.groupby(gcols, dropna=False).agg(**agg).reset_index()
        except Exception:
            # Fallback for older pandas versions
            summary = df.groupby(gcols, dropna=False).agg({
                konto_col: "size",
                "Bilag": "nunique" if "Bilag" in df.columns else "size",
                "Beløp": "sum" if "Beløp" in df.columns else "size",
            }).reset_index()
            # Normalize column names
            if konto_col in summary.columns:
                summary = summary.rename(columns={konto_col: "Rader"})
            if "Bilag" in df.columns and "Bilag" in summary.columns:
                summary = summary.rename(columns={"Bilag": "Bilag"})
            if "Beløp" in summary.columns:
                summary = summary.rename(columns={"Beløp": "Sum"})

        if "Sum" in summary.columns:
            summary = summary.reindex(summary["Sum"].abs().sort_values(ascending=False).index)

        win = tk.Toplevel(self)
        win.title("Kontosummering")
        win.geometry("700x400")

        cols = ["Konto"]
        if navn_col:
            cols.append("Kontonavn")
        cols += ["Rader", "Bilag", "Sum"]

        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120, anchor=("w" if c in ("Konto", "Kontonavn") else "e"))
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ys = ttk.Scrollbar(win, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side=tk.RIGHT, fill=tk.Y)

        for _, row in summary.iterrows():
            konto = row.get(konto_col, "")
            navn = row.get(navn_col, "") if navn_col else ""
            rader = int(row.get("Rader", 0) or 0)
            bilag = int(row.get("Bilag", 0) or 0)
            s = float(row.get("Sum", 0.0) or 0.0)

            values: List[Any] = [konto]
            if navn_col:
                values.append(navn)
            values += [fmt_int_no(rader), fmt_int_no(bilag), fmt_amount_no(s, decimals=2)]
            tree.insert("", tk.END, values=values)

    def _open_drilldown(self) -> None:
        if _open_bilag_drill_dialog is None:
            messagebox.showinfo("Drilldown", "Drilldown er ikke tilgjengelig.")
            return
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Drilldown", "Velg et bilag i tabellen først.")
            return

        values = self.tree.item(selection[0], "values")
        if not values:
            return
        bilag = values[0]

        # Bakoverkompatibilitet: vi prøver å sende med et "forhåndsvalg" hvis API-et støtter det,
        # men faller tilbake uten ekstra kwargs hvis signaturen ikke matcher.
        try:
            kwargs: dict[str, Any] = {
                "df_all": self._df_all,
                "bilag_col": "Bilag",
            }

            try:
                params = inspect.signature(_open_bilag_drill_dialog).parameters
                if "preset_bilag" in params:
                    kwargs["preset_bilag"] = bilag
                elif "bilag" in params:
                    kwargs["bilag"] = bilag
                elif "bilag_id" in params:
                    kwargs["bilag_id"] = bilag
                elif "selected_bilag" in params:
                    kwargs["selected_bilag"] = bilag
            except Exception:
                # Klarte ikke å inspisere signaturen; kjør uten forhåndsvalg.
                pass

            _open_bilag_drill_dialog(self, **kwargs)
        except TypeError:
            # Typisk: "unexpected keyword argument ..." – prøv uten forhåndsvalg.
            try:
                _open_bilag_drill_dialog(self, df_all=self._df_all, bilag_col="Bilag")
            except Exception as e:
                messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")
        except Exception as e:
            messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")

    def _build_bilag_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggreger transaksjoner til bilag-nivå.

        Dette er et tynt wrapper rundt `build_bilag_dataframe`, men gjør det enklere
        å teste logikken separat.
        """
        return build_bilag_dataframe(df)
    def _parse_confidence_percent(self, s: str) -> float:
        s = (s or "90%").strip().replace("%", "")
        try:
            return float(s) / 100.0
        except Exception:
            return 0.90

    def _get_tolerable_error_value(self) -> float:
        """Return tolerable error as a number.

        parse_amount(...) kan returnere None (f.eks. tom streng). GUI-logikken
        forventer likevel et tall slik at vi kan sammenligne (>, <) uten å
        kræsje.
        """

        try:
            v = parse_amount(self.var_tolerable_error.get())
        except Exception:
            return 0.0
        return float(v) if v is not None else 0.0

    def _format_tolerable_error_entry(self) -> None:
        raw = self.var_tolerable_error.get()
        if not (raw or "").strip():
            return
        try:
            n = parse_amount(raw)
        except Exception:
            return
        # Keep it as integer-like
        self.var_tolerable_error.set(format_amount_input_no(n))

    def _sample_size_touched(self) -> None:
        # If user manually sets an explicit number, stop auto-updating
        try:
            current = int(self.var_sample_n.get() or 0)
        except Exception:
            return
        if self._last_suggested_n is not None and current != 0 and current != self._last_suggested_n:
            # Keep user's choice; do not overwrite on refresh
            pass


__all__ = [
    # widget
    "SelectionStudio",
    # helper re-exports
    "compute_population_metrics",
    "PopulationMetrics",
    "build_sample_summary_text",
    "build_source_text",
    "build_population_summary_text",
    "suggest_sample_size",
    "confidence_factor",
    "fmt_amount_no",
    "fmt_int_no",
    "format_interval_no",
    "parse_amount",
    "no_break_spaces_in_numbers",
    # manual strata helpers
    "parse_custom_strata_bounds",
    "format_custom_strata_bounds",
    "stratify_values_custom_bounds",
    # legacy formatting aliases
    "format_amount_input_no",
    # new specific selection helpers
    "split_specific_selection_by_tolerable_error",
    "compute_specific_selection_recommendation",
    "recommend_random_sample_size_net_basis",
    "compute_net_basis_recommendation",
    "build_bilag_dataframe",
    "stratify_bilag_sums",
]


# --- extracted logic overrides (keep at end of module) ---
from selection_studio_bilag import build_bilag_dataframe, stratify_bilag_sums  # noqa: E402,F401
