from __future__ import annotations

import copy
from pathlib import Path

import pandas as pd

from a07_feature import A07Group
from a07_feature import (
    apply_groups_to_mapping,
    build_grouped_a07_df,
    load_a07_groups,
    load_locks,
    load_mapping,
    load_project_state,
    mapping_to_assigned_df,
    reconcile_a07_vs_gl,
    suggest_mapping_candidates,
    unmapped_accounts_df,
)
from a07_feature.control.data import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    build_a07_overview_df,
    build_control_gl_df,
    build_control_queue_df,
    build_control_statement_export_df,
    build_history_comparison_df,
    build_rf1022_statement_df,
    filter_control_statement_df,
)
from a07_feature.control.matching import decorate_suggestions_for_display
from a07_feature.page_paths import (
    build_groups_df,
    build_suggest_config,
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    load_matcher_settings,
    resolve_context_mapping_path,
    resolve_context_source_path,
)

from .page_a07_constants import _BASIS_LABELS
from .page_a07_frames import (
    _empty_a07_df,
    _empty_control_statement_df,
    _empty_mapping_df,
    _empty_reconcile_df,
    _empty_suggestions_df,
    _empty_unmapped_df,
)
from .page_a07_runtime_helpers import _build_usage_features_for_a07


def build_context_restore_payload(
    *,
    client: str | None,
    year: str | None,
    load_active_trial_balance_cached,
    load_a07_source_cached,
    load_mapping_file_cached,
    load_previous_year_mapping_cached,
    resolve_rulebook_path_cached,
) -> dict[str, object]:
    gl_df, tb_path = load_active_trial_balance_cached(client, year)
    source_a07_df = _empty_a07_df()
    a07_df = _empty_a07_df()
    a07_path: Path | None = None
    source_path = resolve_context_source_path(client, year)
    if source_path is not None:
        try:
            source_a07_df = load_a07_source_cached(source_path)
            a07_df = source_a07_df.copy()
            a07_path = source_path
        except Exception:
            source_a07_df = _empty_a07_df()
            a07_df = _empty_a07_df()
            a07_path = None

    mapping: dict[str, str] = {}
    mapping_path: Path | None = None
    mapping_candidate = resolve_context_mapping_path(a07_path, client=client, year=year)
    if mapping_candidate is not None:
        try:
            mapping = load_mapping_file_cached(
                mapping_candidate,
                client=client,
                year=year,
            )
            try:
                mapping_exists = mapping_candidate.exists()
            except Exception:
                mapping_exists = False
            if mapping_exists:
                mapping_path = mapping_candidate
        except Exception:
            mapping = {}
            mapping_path = None

    groups: dict[str, A07Group] = {}
    groups_path: Path | None = None
    locks: set[str] = set()
    locks_path: Path | None = None
    project_meta: dict[str, object] = {}
    project_path: Path | None = None
    if client and year:
        try:
            groups_path = default_a07_groups_path(client, year)
            groups = load_a07_groups(groups_path)
        except Exception:
            groups = {}
            groups_path = None
        try:
            locks_path = default_a07_locks_path(client, year)
            locks = load_locks(locks_path)
        except Exception:
            locks = set()
            locks_path = None
        try:
            project_path = default_a07_project_path(client, year)
            project_meta = load_project_state(project_path)
        except Exception:
            project_meta = {}
            project_path = None

    basis_col = str(project_meta.get("basis_col") or "Endring").strip()
    if basis_col not in _BASIS_LABELS:
        basis_col = "Endring"

    (
        previous_mapping,
        previous_mapping_path,
        previous_mapping_year,
    ) = load_previous_year_mapping_cached(client, year)

    return {
        "gl_df": gl_df,
        "tb_path": tb_path,
        "source_a07_df": source_a07_df,
        "a07_df": a07_df,
        "a07_path": a07_path,
        "mapping": mapping,
        "mapping_path": mapping_path,
        "groups": groups,
        "groups_path": groups_path,
        "locks": locks,
        "locks_path": locks_path,
        "project_meta": project_meta,
        "project_path": project_path,
        "basis_col": basis_col,
        "previous_mapping": previous_mapping,
        "previous_mapping_path": previous_mapping_path,
        "previous_mapping_year": previous_mapping_year,
        "rulebook_path": resolve_rulebook_path_cached(client, year),
        "pending_focus_code": str(project_meta.get("selected_code") or "").strip() or None,
    }


def build_core_refresh_payload(
    *,
    client: str | None,
    year: str | None,
    source_a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    groups: dict[str, A07Group],
    mapping: dict[str, str],
    basis_col: str,
    locks: set[str],
    previous_mapping: dict[str, str],
    usage_df: pd.DataFrame | None,
    previous_mapping_path: Path | None,
    previous_mapping_year: str | None,
    rulebook_path: Path | None,
    load_code_profile_state,
) -> dict[str, object]:
    matcher_settings = load_matcher_settings()
    grouped_a07_df, membership = build_grouped_a07_df(source_a07_df, groups)
    effective_mapping = apply_groups_to_mapping(mapping, membership)
    effective_previous_mapping = apply_groups_to_mapping(previous_mapping, membership)
    usage_features = _build_usage_features_for_a07(usage_df)

    suggestions = _empty_suggestions_df()
    reconcile_df = _empty_reconcile_df()
    mapping_df = mapping_to_assigned_df(
        mapping=effective_mapping,
        gl_df=gl_df,
        include_empty=False,
        basis_col=basis_col,
    ).reset_index(drop=True)
    unmapped_df = _empty_unmapped_df()
    if not grouped_a07_df.empty and not gl_df.empty:
        suggestions = suggest_mapping_candidates(
            a07_df=grouped_a07_df,
            gl_df=gl_df,
            mapping_existing=effective_mapping,
            config=build_suggest_config(
                rulebook_path,
                matcher_settings,
                basis_col=basis_col,
            ),
            mapping_prior=effective_previous_mapping,
            usage_features=usage_features,
        ).reset_index(drop=True)
        suggestions = decorate_suggestions_for_display(suggestions, gl_df).reset_index(drop=True)
        reconcile_df = reconcile_a07_vs_gl(
            a07_df=grouped_a07_df,
            gl_df=gl_df,
            mapping=effective_mapping,
            basis_col=basis_col,
        ).reset_index(drop=True)
        unmapped_df = unmapped_accounts_df(
            gl_df=gl_df,
            mapping=effective_mapping,
            basis_col=basis_col,
        ).reset_index(drop=True)
    code_profile_state = load_code_profile_state(client, year, effective_mapping, gl_df=gl_df)

    control_gl_df = build_control_gl_df(
        gl_df,
        effective_mapping,
        basis_col=basis_col,
    ).reset_index(drop=True)
    a07_overview_df = build_a07_overview_df(grouped_a07_df, reconcile_df)
    control_df = build_control_queue_df(
        a07_overview_df,
        suggestions,
        mapping_current=effective_mapping,
        mapping_previous=effective_previous_mapping,
        gl_df=gl_df,
        code_profile_state=code_profile_state,
        locked_codes=locks,
    ).reset_index(drop=True)
    groups_df = build_groups_df(groups, locked_codes=locks).reset_index(drop=True)
    control_statement_base_df = build_control_statement_export_df(
        client=client,
        year=year,
        gl_df=gl_df,
        reconcile_df=reconcile_df,
        mapping_current=effective_mapping,
    )
    control_statement_df = filter_control_statement_df(
        control_statement_base_df,
        view=CONTROL_STATEMENT_VIEW_PAYROLL,
    )
    rf1022_overview_df = build_rf1022_statement_df(
        control_statement_df,
        basis_col=basis_col,
    )

    return {
        "rulebook_path": rulebook_path,
        "matcher_settings": matcher_settings,
        "previous_mapping": previous_mapping,
        "previous_mapping_path": previous_mapping_path,
        "previous_mapping_year": previous_mapping_year,
        "effective_mapping": effective_mapping,
        "effective_previous_mapping": effective_previous_mapping,
        "grouped_a07_df": grouped_a07_df.reset_index(drop=True),
        "membership": membership,
        "suggestions": suggestions,
        "reconcile_df": reconcile_df,
        "mapping_df": mapping_df,
        "unmapped_df": unmapped_df,
        "control_gl_df": control_gl_df,
        "a07_overview_df": a07_overview_df,
        "control_df": control_df,
        "groups_df": groups_df,
        "control_statement_base_df": control_statement_base_df,
        "control_statement_df": control_statement_df,
        "rf1022_overview_df": rf1022_overview_df,
    }


def build_support_refresh_payload(
    *,
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    effective_mapping: dict[str, str],
    effective_previous_mapping: dict[str, str],
) -> dict[str, object]:
    history_compare_df = build_history_comparison_df(
        a07_df,
        gl_df,
        mapping_current=effective_mapping,
        mapping_previous=effective_previous_mapping,
    ).reset_index(drop=True)
    return {
        "history_compare_df": history_compare_df,
    }


__all__ = [
    "build_context_restore_payload",
    "build_core_refresh_payload",
    "build_support_refresh_payload",
]
