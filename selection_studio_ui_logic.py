"""Selection Studio helper logic.

Denne modulen inneholder beregnings- og formatteringsfunksjoner som brukes av
Selection Studio (GUI) og testene.

De er flyttet ut fra `views_selection_studio_ui.py` for å gjøre UI-filen mindre,
mer lesbar og enklere å videreutvikle.
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, Tuple

import pandas as pd

from selection_studio_helpers import (
    fmt_amount_no,
    parse_amount,
)
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
