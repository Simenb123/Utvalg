from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class SeriesFieldOption:
    key: str
    label: str
    source_column: Optional[str] = None
    structured: bool = False


@dataclass(frozen=True)
class SeriesRun:
    field_key: str
    family_key: str
    label: str
    source_column: str
    prefix: str
    width: Optional[int]
    count_rows: int
    count_distinct: int
    min_number: Optional[int]
    max_number: Optional[int]
    duplicate_count: int
    gap_count: int
    coverage: float
    score: float


@dataclass(frozen=True)
class SeriesCandidate:
    field_key: str
    field_label: str
    source_column: str
    family_key: str
    label: str
    score: float
    structured: bool


@dataclass(frozen=True)
class SeriesGapHit:
    gap_number: int
    source_column: str
    field_key: str
    row_count: int
    distinct_bilag: int


@dataclass(frozen=True)
class SeriesAnalysisResult:
    field_options: tuple[SeriesFieldOption, ...]
    selected_field_key: str
    selected_field_label: str
    selected_source_column: str
    selected_family_key: str
    families_df: pd.DataFrame
    scope_rows_df: pd.DataFrame
    gaps_df: pd.DataFrame
    hits_df: pd.DataFrame
