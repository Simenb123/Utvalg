from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from a07_feature.page_a07_runtime_helpers import _clean_context_value
from a07_feature.page_paths import (
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    resolve_autosave_mapping_path,
    suggest_default_mapping_path,
)
from a07_feature.storage import save_locks, save_mapping, save_project_state
from a07_feature.groups import save_a07_groups


@dataclass(frozen=True)
class WorkspaceStateSaveResult:
    groups_path: Path
    locks_path: Path
    project_path: Path


@dataclass(frozen=True)
class MappingPathDecision:
    path: Path
    needs_dialog: bool


def build_project_state(
    *,
    basis_col: object,
    selected_code: object,
    selected_group: object,
) -> dict[str, object]:
    return {
        "basis_col": str(basis_col or "").strip() or "Endring",
        "selected_code": str(selected_code or "").strip() or None,
        "selected_group": str(selected_group or "").strip() or None,
    }


def save_workspace_state_files(
    *,
    client: object,
    year: object,
    groups: Mapping[str, Any] | None,
    locks: set[str] | None,
    project_state: dict[str, object],
    default_groups_path: Callable[[str, str], Path] = default_a07_groups_path,
    default_locks_path: Callable[[str, str], Path] = default_a07_locks_path,
    default_project_path: Callable[[str, str], Path] = default_a07_project_path,
    save_groups: Callable[[Mapping[str, Any] | None, str | Path], object] = save_a07_groups,
    save_locks_fn: Callable[[str | Path, set[str] | None], Path] = save_locks,
    save_project_state_fn: Callable[[str | Path, dict[str, object]], Path] = save_project_state,
) -> WorkspaceStateSaveResult | None:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if not client_s or not year_s:
        return None

    groups_path = default_groups_path(client_s, year_s)
    locks_path = default_locks_path(client_s, year_s)
    project_path = default_project_path(client_s, year_s)
    save_groups(groups or {}, groups_path)
    save_locks_fn(locks_path, locks or set())
    save_project_state_fn(project_path, project_state)
    return WorkspaceStateSaveResult(groups_path=Path(groups_path), locks_path=Path(locks_path), project_path=Path(project_path))


def autosave_mapping_file(
    *,
    explicit_mapping_path: object,
    a07_path: object,
    client: object,
    year: object,
    mapping: dict[str, str],
    source: str = "manual",
    confidence: float | None = 1.0,
    resolve_path: Callable[..., Path | None] = resolve_autosave_mapping_path,
    save_mapping_fn: Callable[..., Path] = save_mapping,
) -> Path | None:
    save_path = resolve_path(explicit_mapping_path, a07_path=a07_path, client=client, year=year)
    if save_path is None:
        return None
    return Path(
        save_mapping_fn(
            save_path,
            mapping,
            client=client,
            year=year,
            source=source,
            confidence=confidence,
            shadow_to_profiles=True,
        )
    )


def mapping_load_path_decision(
    *,
    a07_path: object,
    client: object,
    year: object,
    suggest_path: Callable[..., Path] = suggest_default_mapping_path,
) -> MappingPathDecision:
    default_path = suggest_path(a07_path, client=client, year=year)
    has_context = bool(_clean_context_value(client) and _clean_context_value(year))
    return MappingPathDecision(path=Path(default_path), needs_dialog=not (Path(default_path).exists() or has_context))


def mapping_save_path_decision(
    *,
    a07_path: object,
    client: object,
    year: object,
    suggest_path: Callable[..., Path] = suggest_default_mapping_path,
) -> MappingPathDecision:
    default_path = suggest_path(a07_path, client=client, year=year)
    has_context = bool(_clean_context_value(client) and _clean_context_value(year))
    return MappingPathDecision(path=Path(default_path), needs_dialog=not has_context)


def save_mapping_file(
    *,
    path: object,
    mapping: dict[str, str],
    client: object,
    year: object,
    save_mapping_fn: Callable[..., Path] = save_mapping,
) -> Path:
    return Path(save_mapping_fn(path, mapping, client=client, year=year, shadow_to_profiles=True))


__all__ = [
    "MappingPathDecision",
    "WorkspaceStateSaveResult",
    "autosave_mapping_file",
    "build_project_state",
    "mapping_load_path_decision",
    "mapping_save_path_decision",
    "save_mapping_file",
    "save_workspace_state_files",
]
