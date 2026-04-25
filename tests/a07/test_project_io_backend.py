from __future__ import annotations

from pathlib import Path

from src.pages.a07.backend.project_io import (
    autosave_mapping_file,
    build_project_state,
    mapping_load_path_decision,
    mapping_save_path_decision,
    save_workspace_state_files,
)


def test_build_project_state_normalizes_empty_values() -> None:
    assert build_project_state(basis_col="", selected_code=" fastloenn ", selected_group=None) == {
        "basis_col": "Endring",
        "selected_code": "fastloenn",
        "selected_group": None,
    }


def test_mapping_load_path_decision_uses_context_path_without_dialog(tmp_path) -> None:
    default_path = tmp_path / "a07_mapping.json"

    decision = mapping_load_path_decision(
        a07_path=None,
        client="Air AS",
        year="2025",
        suggest_path=lambda _a07_path, *, client=None, year=None: default_path,
    )

    assert decision.path == default_path
    assert decision.needs_dialog is False


def test_mapping_save_path_decision_requires_dialog_without_context(tmp_path) -> None:
    default_path = tmp_path / "manual_mapping.json"

    decision = mapping_save_path_decision(
        a07_path=tmp_path / "a07.json",
        client=None,
        year=None,
        suggest_path=lambda _a07_path, *, client=None, year=None: default_path,
    )

    assert decision.path == default_path
    assert decision.needs_dialog is True


def test_autosave_mapping_file_returns_none_when_no_path_can_be_resolved() -> None:
    saved = autosave_mapping_file(
        explicit_mapping_path=None,
        a07_path=None,
        client=None,
        year=None,
        mapping={"5000": "fastloenn"},
        resolve_path=lambda *_args, **_kwargs: None,
    )

    assert saved is None


def test_save_workspace_state_files_writes_all_three_state_files(tmp_path) -> None:
    calls: list[tuple[str, object, Path]] = []

    result = save_workspace_state_files(
        client="Air AS",
        year="2025",
        groups={"g": object()},
        locks={"fastloenn"},
        project_state={"basis_col": "UB"},
        default_groups_path=lambda client, year: tmp_path / f"{client}_{year}_groups.json",
        default_locks_path=lambda client, year: tmp_path / f"{client}_{year}_locks.json",
        default_project_path=lambda client, year: tmp_path / f"{client}_{year}_project.json",
        save_groups=lambda groups, path: calls.append(("groups", groups, Path(path))),
        save_locks_fn=lambda path, locks: calls.append(("locks", locks, Path(path))) or Path(path),
        save_project_state_fn=lambda path, state: calls.append(("project", state, Path(path))) or Path(path),
    )

    assert result is not None
    assert result.groups_path.name == "Air AS_2025_groups.json"
    assert [call[0] for call in calls] == ["groups", "locks", "project"]
