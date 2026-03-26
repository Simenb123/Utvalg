from __future__ import annotations

from typing import Sequence

import pandas as pd

from .extract import (
    AUTO_FIELD_KEY,
    BILAG_FIELD_KEY,
    DOCUMENT_NO_FIELD_KEY,
    REFERENCE_FIELD_KEY,
    TEXT_INVOICE_FIELD_KEY,
    build_series_rows,
    custom_column_field_key,
    list_series_field_options,
)
from .models import SeriesAnalysisResult, SeriesCandidate

_AUTO_CANDIDATE_KEYS = {
    REFERENCE_FIELD_KEY,
    DOCUMENT_NO_FIELD_KEY,
    BILAG_FIELD_KEY,
    TEXT_INVOICE_FIELD_KEY,
}


def _family_label(prefix: str, width: int | None, min_number: int | None, max_number: int | None) -> str:
    prefix_txt = str(prefix or "")
    if min_number is None or max_number is None:
        return prefix_txt or "Serie"
    start = str(int(min_number)).zfill(int(width)) if width else str(int(min_number))
    end = str(int(max_number)).zfill(int(width)) if width else str(int(max_number))
    return f"{prefix_txt}{start}-{prefix_txt}{end}" if prefix_txt else f"{start}-{end}"


def summarise_series_runs(rows_df: pd.DataFrame) -> pd.DataFrame:
    if rows_df is None or rows_df.empty:
        return pd.DataFrame(
            columns=[
                "field_key",
                "field_label",
                "source_column",
                "family_key",
                "label",
                "prefix",
                "width",
                "count_rows",
                "count_distinct",
                "min_number",
                "max_number",
                "duplicate_count",
                "gap_count",
                "coverage",
                "score",
            ]
        )

    out_rows: list[dict[str, object]] = []
    grouped = rows_df.groupby(["field_key", "field_label", "source_column", "family_key"], dropna=False)
    for (field_key, field_label, source_column, family_key), group in grouped:
        numbers = sorted({int(v) for v in group["number"].dropna().tolist()})
        if not numbers:
            continue
        min_number = numbers[0]
        max_number = numbers[-1]
        span = max_number - min_number + 1
        distinct_count = len(numbers)
        duplicate_count = int(len(group.index) - distinct_count)
        gap_count = max(0, span - distinct_count)
        coverage = (distinct_count / span) if span > 0 else 0.0
        prefix = str(group["prefix"].iloc[0] or "")
        width = group["width"].dropna().astype(int).iloc[0] if group["width"].notna().any() else None
        structured_bonus = (
            100.0
            if field_key == REFERENCE_FIELD_KEY
            else 80.0
            if field_key == DOCUMENT_NO_FIELD_KEY
            else 60.0
            if field_key == BILAG_FIELD_KEY
            else 0.0
        )
        score = structured_bonus + (coverage * 25.0) + float(distinct_count) - (duplicate_count * 0.5)
        out_rows.append(
            {
                "field_key": field_key,
                "field_label": field_label,
                "source_column": source_column,
                "family_key": family_key,
                "label": _family_label(prefix, width, min_number, max_number),
                "prefix": prefix,
                "width": width,
                "count_rows": int(len(group.index)),
                "count_distinct": int(distinct_count),
                "min_number": int(min_number),
                "max_number": int(max_number),
                "duplicate_count": int(duplicate_count),
                "gap_count": int(gap_count),
                "coverage": float(coverage),
                "score": float(score),
            }
        )

    return pd.DataFrame(out_rows).sort_values(["score", "count_distinct"], ascending=[False, False], ignore_index=True)


def _empty_result(
    *,
    options,
    selected_field_key: str,
    selected_field_label: str,
    selected_source_column: str,
    selected_family_key: str = "",
) -> SeriesAnalysisResult:
    empty_families = summarise_series_runs(pd.DataFrame())
    return SeriesAnalysisResult(
        field_options=tuple(options),
        selected_field_key=str(selected_field_key or ""),
        selected_field_label=str(selected_field_label or ""),
        selected_source_column=str(selected_source_column or ""),
        selected_family_key=str(selected_family_key or ""),
        families_df=empty_families,
        scope_rows_df=pd.DataFrame(),
        gaps_df=pd.DataFrame(columns=["family_key", "number"]),
        hits_df=pd.DataFrame(columns=["gap_number", "field_key", "source_column", "Bilag", "Dato", "Konto", "Tekst"]),
    )


def pick_default_series_field(df: pd.DataFrame) -> SeriesCandidate | None:
    best: SeriesCandidate | None = None
    for option in list_series_field_options(df):
        if option.key == AUTO_FIELD_KEY or option.key not in _AUTO_CANDIDATE_KEYS:
            continue
        try:
            _option, rows_df = build_series_rows(df, option.key)
        except Exception:
            continue
        families = summarise_series_runs(rows_df)
        if families.empty:
            continue
        top = families.iloc[0]
        candidate = SeriesCandidate(
            field_key=str(top["field_key"]),
            field_label=str(top["field_label"]),
            source_column=str(top["source_column"]),
            family_key=str(top["family_key"]),
            label=str(top["label"]),
            score=float(top["score"]),
            structured=bool(option.structured),
        )
        if best is None or candidate.score > best.score:
            best = candidate
    return best


def find_series_gaps(rows_df: pd.DataFrame, *, family_key: str) -> pd.DataFrame:
    if rows_df is None or rows_df.empty or not family_key:
        return pd.DataFrame(columns=["family_key", "number"])

    subset = rows_df.loc[rows_df["family_key"] == family_key].copy()
    if subset.empty:
        return pd.DataFrame(columns=["family_key", "number"])

    numbers = sorted({int(v) for v in subset["number"].dropna().tolist()})
    if not numbers:
        return pd.DataFrame(columns=["family_key", "number"])

    full = set(range(numbers[0], numbers[-1] + 1))
    missing = sorted(full - set(numbers))
    return pd.DataFrame({"family_key": [family_key] * len(missing), "number": missing})


def search_gap_hits_in_full_ledger(
    all_df: pd.DataFrame,
    gap_values: Sequence[int],
    *,
    field_key: str,
    family_key: str,
    include_text_fallback: bool = False,
) -> pd.DataFrame:
    if all_df is None or all_df.empty or not gap_values:
        return pd.DataFrame(columns=["gap_number", "field_key", "source_column", "Bilag", "Dato", "Konto", "Tekst"])

    _option, rows_df = build_series_rows(all_df, field_key)
    hits = rows_df.loc[rows_df["family_key"] == family_key].copy()
    hits = hits.loc[hits["number"].isin([int(v) for v in gap_values])].copy()

    if hits.empty and include_text_fallback and field_key != TEXT_INVOICE_FIELD_KEY:
        _text_option, text_rows_df = build_series_rows(all_df, TEXT_INVOICE_FIELD_KEY)
        hits = text_rows_df.loc[text_rows_df["number"].isin([int(v) for v in gap_values])].copy()

    if hits.empty:
        return pd.DataFrame(columns=["gap_number", "field_key", "source_column", "Bilag", "Dato", "Konto", "Tekst"])

    merged = hits.merge(
        all_df.reset_index().rename(columns={"index": "row_index"}),
        on="row_index",
        how="left",
        suffixes=("", "_src"),
    )
    merged = merged.rename(columns={"number": "gap_number"})
    keep = [c for c in ["gap_number", "field_key", "source_column", "Bilag", "Dato", "Konto", "Tekst", "raw_value"] if c in merged.columns]
    return merged[keep].sort_values(["gap_number", "Dato", "Bilag"], kind="mergesort", ignore_index=True)


def analyze_series(
    scope_df: pd.DataFrame,
    all_df: pd.DataFrame | None = None,
    *,
    field_key: str = AUTO_FIELD_KEY,
    family_key: str | None = None,
    include_text_fallback: bool = False,
) -> SeriesAnalysisResult:
    if scope_df is None:
        scope_df = pd.DataFrame()
    if all_df is None:
        all_df = scope_df

    options = tuple(list_series_field_options(scope_df))
    selected = pick_default_series_field(scope_df) if field_key == AUTO_FIELD_KEY else None
    resolved_field_key = selected.field_key if selected is not None else field_key

    if resolved_field_key == AUTO_FIELD_KEY:
        fallback = next((opt for opt in options if opt.key != AUTO_FIELD_KEY and opt.source_column), None)
        if fallback is None:
            return _empty_result(
                options=options,
                selected_field_key="",
                selected_field_label="",
                selected_source_column="",
            )
        resolved_field_key = fallback.key

    try:
        option, scope_rows_df = build_series_rows(scope_df, resolved_field_key)
    except Exception:
        option = next((opt for opt in options if opt.key == resolved_field_key), None)
        return _empty_result(
            options=options,
            selected_field_key=resolved_field_key,
            selected_field_label=str(getattr(option, "label", "") or ""),
            selected_source_column=str(getattr(option, "source_column", "") or ""),
        )

    families_df = summarise_series_runs(scope_rows_df)

    selected_family_key = str(family_key or "")
    if not selected_family_key:
        if selected is not None and selected.field_key == resolved_field_key:
            selected_family_key = selected.family_key
        elif not families_df.empty:
            selected_family_key = str(families_df.iloc[0]["family_key"])

    gaps_df = find_series_gaps(scope_rows_df, family_key=selected_family_key)
    hits_df = search_gap_hits_in_full_ledger(
        all_df,
        gaps_df["number"].astype(int).tolist() if not gaps_df.empty else [],
        field_key=resolved_field_key,
        family_key=selected_family_key,
        include_text_fallback=include_text_fallback,
    )

    return SeriesAnalysisResult(
        field_options=options,
        selected_field_key=option.key,
        selected_field_label=option.label,
        selected_source_column=str(option.source_column or ""),
        selected_family_key=selected_family_key,
        families_df=families_df,
        scope_rows_df=scope_rows_df,
        gaps_df=gaps_df,
        hits_df=hits_df,
    )


__all__ = [
    "AUTO_FIELD_KEY",
    "REFERENCE_FIELD_KEY",
    "DOCUMENT_NO_FIELD_KEY",
    "BILAG_FIELD_KEY",
    "TEXT_INVOICE_FIELD_KEY",
    "analyze_series",
    "custom_column_field_key",
    "find_series_gaps",
    "list_series_field_options",
    "pick_default_series_field",
    "search_gap_hits_in_full_ledger",
]
