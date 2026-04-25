from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .models import AccountUsageFeatures, SUGGEST_OUT_COLUMNS, SuggestConfig
from .solver_code import build_code_suggestion_rows
from .solver_prepare import build_engine_context


def suggest_mappings(
    a07_codes_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    mapping: Optional[Dict[str, str]] = None,
    *,
    max_combo: Optional[int] = None,
    candidates_per_code: Optional[int] = None,
    top_suggestions_per_code: Optional[int] = None,
    top_codes: Optional[int] = None,
    exclude_mapped_accounts: Optional[bool] = None,
    override_existing_mapping: Optional[bool] = None,
    filter_mode: Optional[str] = None,
    basis_strategy: Optional[str] = None,
    basis: Optional[str] = None,
    basis_by_code: Optional[Dict[str, str]] = None,
    tolerance_rel: Optional[float] = None,
    tolerance_abs: Optional[float] = None,
    rulebook_path: Optional[str] = None,
    use_residual: Optional[bool] = None,
    hide_solved_codes: Optional[bool] = None,
    basis_col: Optional[str] = None,
    max_candidates_per_code: Optional[int] = None,
    override_existing: Optional[bool] = None,
    top_per_code: Optional[int] = None,
    config: Optional[SuggestConfig] = None,
    cfg: Optional[SuggestConfig] = None,
    mapping_existing: Optional[Dict[str, str]] = None,
    mapping_prior: Optional[Dict[str, str]] = None,
    mapping_previous_year: Optional[Dict[str, str]] = None,
    usage_features: Optional[Dict[str, AccountUsageFeatures]] = None,
    monthly_df: Optional[pd.DataFrame] = None,
    **_ignored_kwargs: Any,
) -> pd.DataFrame:
    base_cfg = config or cfg or SuggestConfig()
    context = build_engine_context(
        a07_codes_df=a07_codes_df,
        gl_df=gl_df,
        base_cfg=base_cfg,
        mapping=mapping,
        mapping_existing=mapping_existing,
        mapping_prior=mapping_prior,
        mapping_previous_year=mapping_previous_year,
        usage_features=usage_features,
        monthly_df=monthly_df,
        max_combo=max_combo,
        candidates_per_code=candidates_per_code,
        top_suggestions_per_code=top_suggestions_per_code,
        top_codes=top_codes,
        exclude_mapped_accounts=exclude_mapped_accounts,
        override_existing_mapping=override_existing_mapping,
        filter_mode=filter_mode,
        basis_strategy=basis_strategy,
        basis=basis,
        basis_by_code=basis_by_code,
        tolerance_rel=tolerance_rel,
        tolerance_abs=tolerance_abs,
        rulebook_path=rulebook_path,
        use_residual=use_residual,
        hide_solved_codes=hide_solved_codes,
        basis_col=basis_col,
        max_candidates_per_code=max_candidates_per_code,
        override_existing=override_existing,
        top_per_code=top_per_code,
    )

    if context.a07_df.empty:
        return pd.DataFrame(columns=list(SUGGEST_OUT_COLUMNS))

    out_rows: list[dict[str, Any]] = []
    for _, row in context.a07_df.iterrows():
        out_rows.extend(build_code_suggestion_rows(row, context=context))

    if not out_rows:
        return pd.DataFrame(columns=list(SUGGEST_OUT_COLUMNS))

    df_out = pd.DataFrame(out_rows)
    return df_out.sort_values(
        by=["WithinTolerance", "Score", "Kode", "ComboSize"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


__all__ = ["suggest_mappings"]
