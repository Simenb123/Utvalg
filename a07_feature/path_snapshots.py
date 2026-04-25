from __future__ import annotations

from pathlib import Path

from .path_context import (
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    resolve_context_mapping_path,
    resolve_context_source_path,
)
from .path_shared import _clean_context_value, _path_signature, _safe_exists
from .path_trial_balance import get_active_trial_balance_path_for_context


def get_context_snapshot_with_paths(
    client: str | None,
    year: str | int | None,
    *,
    tb_path: str | Path | None = None,
    source_path: str | Path | None = None,
    mapping_path: str | Path | None = None,
    groups_path: str | Path | None = None,
    locks_path: str | Path | None = None,
    project_path: str | Path | None = None,
) -> tuple[tuple[str | None, int | None, int | None], ...]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    source_candidate: Path | None = Path(source_path) if source_path else None
    mapping_candidate: Path | None = Path(mapping_path) if mapping_path else None
    groups_candidate: Path | None = Path(groups_path) if groups_path else None
    locks_candidate: Path | None = Path(locks_path) if locks_path else None
    project_candidate: Path | None = Path(project_path) if project_path else None
    tb_candidate: Path | None = Path(tb_path) if tb_path else None

    if client_s and year_s:
        if source_candidate is None:
            source_candidate = resolve_context_source_path(client_s, year_s)
        if mapping_candidate is None:
            mapping_candidate = resolve_context_mapping_path(
                source_candidate,
                client=client_s,
                year=year_s,
            )
        if groups_candidate is None:
            groups_guess = default_a07_groups_path(client_s, year_s)
            if _safe_exists(groups_guess):
                groups_candidate = groups_guess
        if locks_candidate is None:
            locks_guess = default_a07_locks_path(client_s, year_s)
            if _safe_exists(locks_guess):
                locks_candidate = locks_guess
        if project_candidate is None:
            project_guess = default_a07_project_path(client_s, year_s)
            if _safe_exists(project_guess):
                project_candidate = project_guess

    return (
        _path_signature(tb_candidate),
        _path_signature(source_candidate),
        _path_signature(mapping_candidate),
        _path_signature(groups_candidate),
        _path_signature(locks_candidate),
        _path_signature(project_candidate),
    )


def get_context_snapshot(
    client: str | None,
    year: str | int | None,
) -> tuple[tuple[str | None, int | None, int | None], ...]:
    tb_path = get_active_trial_balance_path_for_context(client, year)
    return get_context_snapshot_with_paths(client, year, tb_path=tb_path)
