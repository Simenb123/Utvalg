"""Tynn fasade over ``regnskapslinje_mapping_service`` (RL-servicen).

Modulen ble tidligere eier av all RL-mappinglogikk for Analyse-fanen.
Fra runde 1 av RL-mapping-konsolideringen er logikken flyttet til
``regnskapslinje_mapping_service`` og denne modulen gjenstår kun som
en bakoverkompatibel fasade slik at eldre importveier (Analyse,
Saldobalanse og Admin) fortsetter å virke uendret.

Nye konsumenter bør importere direkte fra
``regnskapslinje_mapping_service``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import regnskapslinje_mapping_service as _svc
from regnskapslinje_mapping_service import (
    RLAdminRow,
    RLMappingContext,
    RLMappingIssue,
    RLMappingStatusSummary,
    build_admin_rl_rows,
    build_page_admin_rl_rows,
    build_page_rl_mapping_issues,
    build_rl_mapping_issues,
    clear_account_override,
    context_from_page,
    enrich_rl_mapping_issues_with_suggestions,
    get_problem_rl_accounts,
    load_rl_config_dataframes,
    load_rl_mapping_context,
    problem_rl_mapping_issues,
    resolve_accounts_to_rl,
    set_account_override,
    summarize_rl_mapping_issues,
    summarize_rl_status,
)


# ---------------------------------------------------------------------------
# Bakoverkompatible aliaser
# ---------------------------------------------------------------------------

# Eldre kode importerer ``UnmappedAccountIssue``. Aliaset er identisk med
# den kanoniske ``RLMappingIssue`` (felt-for-felt kompatibelt).
UnmappedAccountIssue = RLMappingIssue


# ---------------------------------------------------------------------------
# Tynne shims som mappar gamle signaturer til den nye RL-servicen
# ---------------------------------------------------------------------------


def build_mapping_issues(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
    include_ao: bool = False,
) -> list[RLMappingIssue]:
    """Bakoverkompatibelt entry point.

    Bygger en ad-hoc ``RLMappingContext`` fra de injiserte tabellene og
    delegerer videre til ``regnskapslinje_mapping_service``.
    """
    context = load_rl_mapping_context(
        intervals=intervals,
        regnskapslinjer=regnskapslinjer,
        account_overrides=account_overrides or {},
    )
    return build_rl_mapping_issues(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        context=context,
        include_ao=include_ao,
    )


def enrich_mapping_issues_with_suggestions(
    issues: list[RLMappingIssue],
    *,
    regnskapslinjer: pd.DataFrame | None,
    usage_features: dict[str, Any] | None = None,
    historical_overrides: dict[str, int] | None = None,
    rulebook_document: dict[str, Any] | None = None,
) -> list[RLMappingIssue]:
    return enrich_rl_mapping_issues_with_suggestions(
        issues,
        regnskapslinjer=regnskapslinjer,
        usage_features=usage_features,
        historical_overrides=historical_overrides,
        rulebook_document=rulebook_document,
    )


def problem_mapping_issues(
    issues: list[RLMappingIssue],
    *,
    include_zero: bool = False,
) -> list[RLMappingIssue]:
    return problem_rl_mapping_issues(issues, include_zero=include_zero)


def summarize_mapping_issues(
    issues: list[RLMappingIssue],
    *,
    include_zero: bool = False,
) -> str:
    return summarize_rl_mapping_issues(issues, include_zero=include_zero)


def get_problem_accounts(issues: list[RLMappingIssue]) -> list[str]:
    return get_problem_rl_accounts(issues)


def build_page_mapping_issues(page: Any, *, use_filtered_hb: bool = False) -> list[RLMappingIssue]:
    return build_page_rl_mapping_issues(page, use_filtered_hb=use_filtered_hb)


__all__ = [
    "RLAdminRow",
    "RLMappingContext",
    "RLMappingIssue",
    "RLMappingStatusSummary",
    "UnmappedAccountIssue",
    "build_admin_rl_rows",
    "build_mapping_issues",
    "build_page_admin_rl_rows",
    "build_page_mapping_issues",
    "build_page_rl_mapping_issues",
    "build_rl_mapping_issues",
    "clear_account_override",
    "context_from_page",
    "enrich_mapping_issues_with_suggestions",
    "enrich_rl_mapping_issues_with_suggestions",
    "get_problem_accounts",
    "get_problem_rl_accounts",
    "load_rl_config_dataframes",
    "load_rl_mapping_context",
    "problem_mapping_issues",
    "problem_rl_mapping_issues",
    "resolve_accounts_to_rl",
    "set_account_override",
    "summarize_mapping_issues",
    "summarize_rl_mapping_issues",
    "summarize_rl_status",
]
