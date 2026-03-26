from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .apply import apply_suggestion_to_mapping
from .engine import suggest_mappings
from .helpers import (
    _auto_basis_for_code,
    _get_series,
    _is_a07_relevant_account,
    _konto_in_ranges,
    _konto_int,
    _safe_float,
    _score_account,
    _tokenize,
    available_basis,
)
from .models import (
    BASIS_ALIASES,
    BASIS_DEBET,
    BASIS_ENDRING,
    BASIS_IB,
    BASIS_KREDIT,
    BASIS_UB,
    EXCLUDED_A07_CODES,
    PAYROLL_TOKENS,
    SUGGEST_OUT_COLUMNS,
    SuggestConfig,
    SuggestionRow,
)
from .rulebook import Rulebook, RulebookRule, load_rulebook


def suggest_mapping_candidates(
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    mapping_existing: Optional[Dict[str, str]] = None,
    config: Optional[SuggestConfig] = None,
    mapping: Optional[Dict[str, str]] = None,
    **kwargs: Any,
) -> pd.DataFrame:
    if mapping_existing is None and mapping is not None:
        mapping_existing = mapping

    if "mapping" in kwargs:
        kw_map = kwargs.pop("mapping")
        if mapping_existing is None:
            mapping_existing = kw_map

    mapping_existing = mapping_existing or {}
    mapping_effective = {
        str(k): str(v)
        for k, v in mapping_existing.items()
        if str(v).strip()
    }

    return suggest_mappings(
        a07_codes_df=a07_df,
        gl_df=gl_df,
        mapping=mapping_effective,
        config=config,
        **kwargs,
    )


__all__ = [
    "SuggestConfig",
    "SuggestionRow",
    "suggest_mappings",
    "suggest_mapping_candidates",
    "apply_suggestion_to_mapping",
    "EXCLUDED_A07_CODES",
    "PAYROLL_TOKENS",
    "BASIS_UB",
    "BASIS_IB",
    "BASIS_ENDRING",
    "BASIS_DEBET",
    "BASIS_KREDIT",
    "BASIS_ALIASES",
    "SUGGEST_OUT_COLUMNS",
    "available_basis",
    "Rulebook",
    "RulebookRule",
    "load_rulebook",
    "_auto_basis_for_code",
    "_get_series",
    "_is_a07_relevant_account",
    "_konto_in_ranges",
    "_konto_int",
    "_safe_float",
    "_score_account",
    "_tokenize",
]
