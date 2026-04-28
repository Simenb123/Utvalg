"""selection_studio_specific.py

Ren (UI-uavhengig) logikk for utvalg:

- Aggregering av transaksjoner til bilagsnivå
- Spesifikk utvelgelse basert på tolererbar feil
- Anbefalinger/metadata som brukes av SelectionStudio

Holdes separat fra Tkinter-koden i views_selection_studio_ui.py slik at det er lett å teste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import pandas as pd

__all__ = [
    "SpecificSelectionRecommendation",
    "build_bilag_dataframe",
    "split_specific_selection_by_tolerable_error",
    "compute_specific_selection_recommendation",
]


def _find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    """Finn kolonnenavn i `df` basert på kandidater (case/whitespace-insensitive)."""
    if df is None or df.empty:
        return None
    norm_map = {str(c).strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = str(cand).strip().lower()
        if key in norm_map:
            return norm_map[key]
    return None


def build_bilag_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Aggreger transaksjoner til bilagsnivå.

    Returnerer alltid en DataFrame med stabile kolonner:
    ``['Bilag', 'Dato', 'Tekst', 'SumBeløp']``.

    Robust mot vanlige variasjoner i kolonnenavn, f.eks.:
    - ``Beløp`` / ``Belop`` / ``Amount`` / ``SumBeløp``
    - ``Dato`` / ``Date``
    - ``Tekst`` / ``Text``
    """

    if df is None or df.empty:
        return pd.DataFrame(columns=["Bilag", "Dato", "Tekst", "SumBeløp"])

    bilag_col = _find_column(df, ["Bilag", "bilag", "Voucher", "voucher", "Bilagsnr", "bilagsnr", "BilagsNr"])
    amount_col = _find_column(
        df,
        [
            "Beløp",
            "Belop",
            "Belop.",
            "Amount",
            "amount",
            "SumBeløp",
            "SumBelop",
            "Sumbeløp",
            "Sumbelop",
        ],
    )
    date_col = _find_column(df, ["Dato", "dato", "Date", "date"])
    text_col = _find_column(
        df,
        ["Tekst", "tekst", "Text", "text", "Beskrivelse", "beskrivelse", "Description", "description"],
    )

    if bilag_col is None:
        raise KeyError("Mangler bilagskolonne. Forventet f.eks. 'Bilag'.")
    if amount_col is None:
        raise KeyError("Mangler beløpskolonne. Forventet f.eks. 'Beløp'/'Belop'/'Amount'.")

    agg: dict[str, str] = {amount_col: "sum"}
    if date_col is not None:
        agg[date_col] = "first"
    if text_col is not None:
        agg[text_col] = "first"

    bilag_df = df.groupby(bilag_col, as_index=False).agg(agg)

    rename_map: dict[str, str] = {bilag_col: "Bilag", amount_col: "SumBeløp"}
    if date_col is not None:
        rename_map[date_col] = "Dato"
    if text_col is not None:
        rename_map[text_col] = "Tekst"
    bilag_df = bilag_df.rename(columns=rename_map)

    if "Dato" not in bilag_df.columns:
        bilag_df["Dato"] = ""
    if "Tekst" not in bilag_df.columns:
        bilag_df["Tekst"] = ""

    return bilag_df[["Bilag", "Dato", "Tekst", "SumBeløp"]]


def split_specific_selection_by_tolerable_error(
    bilag_df: pd.DataFrame,
    tolerable_error: float | int,
    *,
    amount_col: str = "SumBeløp",
    use_abs: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split bilag_df into:
      - specific_df: all bilag where abs(amount) >= tolerable_error (or amount >= if use_abs=False)
      - remaining_df: everything else
    """
    if bilag_df is None or bilag_df.empty:
        return (
            pd.DataFrame(columns=list(bilag_df.columns) if bilag_df is not None else []),
            pd.DataFrame(columns=list(bilag_df.columns) if bilag_df is not None else []),
        )

    if amount_col not in bilag_df.columns:
        raise KeyError(f"Mangler kolonne '{amount_col}' i bilag_df")

    tol = float(abs(tolerable_error))
    amounts = pd.to_numeric(bilag_df[amount_col], errors="coerce").fillna(0.0)

    metric = amounts.abs() if use_abs else amounts
    mask_specific = metric >= tol

    specific_df = bilag_df.loc[mask_specific].copy()
    remaining_df = bilag_df.loc[~mask_specific].copy()
    return specific_df, remaining_df


@dataclass
class SpecificSelectionRecommendation:
    """Resultat fra spesifikk utvelgelse basert på tolererbar feil.

    Klassen er bevisst kompatibel med både:
    - dict-style tilgang (``rec['n_specific']``), brukt i noen tester/kallsteder
    - attribute-style tilgang (``rec.n_specific``), brukt i andre
    """

    tolerable_error: float
    threshold: float
    n_specific: int
    n_remaining: int
    n_total: int
    specific_book_value: float
    remaining_book_value: float
    total_book_value: float

    specific_df: Optional[pd.DataFrame] = None
    remaining_df: Optional[pd.DataFrame] = None

    # For legacy/test use-cases (bilag_values -> bilag-id liste)
    specific_bilag: list[Any] = field(default_factory=list)

    confidence_factor: Optional[float] = None
    additional_n: Optional[int] = None
    total_n: Optional[int] = None

    sample_size_before: Optional[int] = None
    sample_size_after: Optional[int] = None

    use_abs: bool = True
    amount_column: str = "SumBeløp"

    @property
    def specific_count(self) -> int:
        return int(self.n_specific)

    @property
    def remaining_count(self) -> int:
        return int(self.n_remaining)

    @property
    def remaining_value_abs(self) -> float:
        if self.use_abs:
            return float(self.remaining_book_value)
        return float(abs(self.remaining_book_value))

    def __getitem__(self, key: str) -> Any:
        mapping = {
            # Primary keys
            "tolerable_error": self.tolerable_error,
            "threshold": self.threshold,
            "n_specific": self.n_specific,
            "n_remaining": self.n_remaining,
            "n_total": self.n_total,
            "specific_book_value": self.specific_book_value,
            "remaining_book_value": self.remaining_book_value,
            "total_book_value": self.total_book_value,
            # Legacy names (some older code/tests used these)
            "specific_value": self.specific_book_value,
            "remaining_value": self.remaining_book_value,
            "specific_df": self.specific_df,
            "remaining_df": self.remaining_df,
            "specific_bilag": self.specific_bilag,
            "specific_count": self.specific_count,
            "remaining_count": self.remaining_count,
            "remaining_value_abs": self.remaining_value_abs,
            # Sample size extras
            "confidence_factor": self.confidence_factor,
            "additional_n": self.additional_n,
            "total_n": self.total_n,
            "sample_size_before": self.sample_size_before,
            "sample_size_after": self.sample_size_after,
        }
        if key in mapping:
            return mapping[key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default


def compute_specific_selection_recommendation(
    bilag_df: pd.DataFrame | None = None,
    tolerable_error: float | int | None = None,
    *,
    bilag_values: Optional[Iterable[float]] = None,
    amount_column: str = "SumBeløp",
    amount_col: str | None = None,
    threshold: float | int | None = None,
    use_abs: bool = True,
    sample_size: Optional[int] = None,
    confidence_factor: Optional[float] = None,
) -> SpecificSelectionRecommendation:
    """Compute recommendation impact of specific selection.

    The function supports two call patterns for backward compatibility:

    1) DataFrame mode (SelectionStudio & specific-selection tests)
       - ``bilag_df``: DataFrame with one row per bilag and an amount column
       - returns ``SpecificSelectionRecommendation`` with ``specific_df`` / ``remaining_df``

    2) Series/iterable mode (legacy unit test)
       - ``bilag_values``: iterable/Series of bilag totals (index used as bilag-id if Series)
       - returns ``SpecificSelectionRecommendation`` with ``specific_bilag`` list

    Parameters
    ----------
    tolerable_error / threshold:
        Threshold for specific selection. Threshold wins if both are provided.

    confidence_factor:
        Optional factor used to estimate how many additional random picks are needed
        from the remaining population:
            additional_n = ceil((remaining_value_abs / tolerable_error) * confidence_factor)

    Returns
    -------
    SpecificSelectionRecommendation
    """

    if amount_col is not None:
        amount_column = amount_col

    # Resolve threshold
    if threshold is None:
        threshold = tolerable_error
    tol = float(threshold or 0.0)
    tol_abs = float(abs(tol))

    if bilag_df is not None and bilag_values is not None:
        raise ValueError("Bruk enten bilag_df eller bilag_values, ikke begge.")

    # --- values mode (legacy) -------------------------------------------------
    if bilag_values is not None:
        if isinstance(bilag_values, pd.Series):
            series = pd.to_numeric(bilag_values, errors="coerce").fillna(0.0)
        else:
            series = pd.to_numeric(pd.Series(list(bilag_values)), errors="coerce").fillna(0.0)

        metric = series.abs() if use_abs else series
        mask = metric >= tol_abs if tol_abs > 0 else metric >= 0  # tol==0 => everything is specific
        n_specific = int(mask.sum())
        n_total = int(len(metric))
        n_remaining = int(n_total - n_specific)

        specific_value = float(metric[mask].sum())
        remaining_value = float(metric[~mask].sum())
        total_value = float(specific_value + remaining_value)

        specific_bilag = list(metric.index[mask])

        # Optional additional sample size from remaining population
        additional_n: Optional[int] = None
        total_n: Optional[int] = None
        if confidence_factor is not None:
            if tol_abs <= 0:
                additional_n = 0
            else:
                rem_abs = float(remaining_value if use_abs else abs(remaining_value))
                additional_n = int(math.ceil((rem_abs / tol_abs) * float(confidence_factor))) if rem_abs > 0 else 0
                additional_n = max(additional_n, 0)
                additional_n = min(additional_n, n_remaining)
            total_n = int(n_specific + (additional_n or 0))

        sample_size_before = int(sample_size) if sample_size is not None else None
        sample_size_after = max(int(sample_size_before - n_specific), 0) if sample_size_before is not None else None

        return SpecificSelectionRecommendation(
            tolerable_error=tol_abs,
            threshold=tol_abs,
            n_specific=n_specific,
            n_remaining=n_remaining,
            n_total=n_total,
            specific_book_value=specific_value,
            remaining_book_value=remaining_value,
            total_book_value=total_value,
            specific_df=None,
            remaining_df=None,
            specific_bilag=specific_bilag,
            confidence_factor=float(confidence_factor) if confidence_factor is not None else None,
            additional_n=additional_n,
            total_n=total_n,
            sample_size_before=sample_size_before,
            sample_size_after=sample_size_after,
            use_abs=use_abs,
            amount_column=amount_column,
        )

    # --- dataframe mode -------------------------------------------------------
    df = bilag_df
    if df is None or df.empty:
        empty_df = pd.DataFrame(columns=["Bilag", "Dato", "Tekst", amount_column])
        sample_size_before = int(sample_size) if sample_size is not None else None
        sample_size_after = sample_size_before
        return SpecificSelectionRecommendation(
            tolerable_error=tol_abs,
            threshold=tol_abs,
            n_specific=0,
            n_remaining=0,
            n_total=0,
            specific_book_value=0.0,
            remaining_book_value=0.0,
            total_book_value=0.0,
            specific_df=empty_df,
            remaining_df=empty_df,
            specific_bilag=[],
            confidence_factor=float(confidence_factor) if confidence_factor is not None else None,
            additional_n=0 if confidence_factor is not None else None,
            total_n=0 if confidence_factor is not None else None,
            sample_size_before=sample_size_before,
            sample_size_after=sample_size_after,
            use_abs=use_abs,
            amount_column=amount_column,
        )

    # Resolve amount column in df (fallback to common variants)
    amount_col_used = amount_column
    if amount_col_used not in df.columns:
        alt = _find_column(df, [amount_column, "SumBeløp", "SumBelop", "Beløp", "Belop", "Amount"])
        if alt is not None:
            amount_col_used = alt
        else:
            raise KeyError(f"Mangler beløpskolonne '{amount_column}'.")

    amounts = pd.to_numeric(df[amount_col_used], errors="coerce").fillna(0.0)
    metric = amounts.abs() if use_abs else amounts

    mask = metric >= tol_abs if tol_abs > 0 else metric >= 0
    specific_df = df.loc[mask].copy()
    remaining_df = df.loc[~mask].copy()

    n_specific = int(len(specific_df))
    n_remaining = int(len(remaining_df))
    n_total = int(len(df))

    specific_value = float(metric.loc[specific_df.index].sum())
    remaining_value = float(metric.loc[remaining_df.index].sum())
    total_value = float(specific_value + remaining_value)

    if "Bilag" in specific_df.columns:
        specific_bilag = list(specific_df["Bilag"].tolist())
    else:
        specific_bilag = list(specific_df.index.tolist())

    additional_n: Optional[int] = None
    total_n: Optional[int] = None
    if confidence_factor is not None:
        if tol_abs <= 0:
            additional_n = 0
        else:
            rem_abs = float(remaining_value if use_abs else abs(remaining_value))
            additional_n = int(math.ceil((rem_abs / tol_abs) * float(confidence_factor))) if rem_abs > 0 else 0
            additional_n = max(additional_n, 0)
            additional_n = min(additional_n, n_remaining)
        total_n = int(n_specific + (additional_n or 0))

    sample_size_before = int(sample_size) if sample_size is not None else None
    sample_size_after = max(int(sample_size_before - n_specific), 0) if sample_size_before is not None else None

    return SpecificSelectionRecommendation(
        tolerable_error=tol_abs,
        threshold=tol_abs,
        n_specific=n_specific,
        n_remaining=n_remaining,
        n_total=n_total,
        specific_book_value=specific_value,
        remaining_book_value=remaining_value,
        total_book_value=total_value,
        specific_df=specific_df,
        remaining_df=remaining_df,
        specific_bilag=specific_bilag,
        confidence_factor=float(confidence_factor) if confidence_factor is not None else None,
        additional_n=additional_n,
        total_n=total_n,
        sample_size_before=sample_size_before,
        sample_size_after=sample_size_after,
        use_abs=use_abs,
        amount_column=amount_col_used,
    )
