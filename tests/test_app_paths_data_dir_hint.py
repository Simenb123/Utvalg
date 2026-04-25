from __future__ import annotations

from pathlib import Path

import pytest

import app_paths


def test_data_dir_uses_env_override_even_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    hint_target = tmp_path / "hint_target"
    app_paths.write_data_dir_hint(str(hint_target))

    env_target = tmp_path / "env_target"
    monkeypatch.setenv("UTVALG_DATA_DIR", str(env_target))

    assert app_paths.data_dir() == env_target.expanduser().resolve()


def test_data_dir_uses_hint_file_when_env_not_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("UTVALG_DATA_DIR", raising=False)
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)

    target = tmp_path / "shared"
    app_paths.write_data_dir_hint(str(target))

    assert app_paths.data_dir() == target.expanduser().resolve()


def test_read_data_dir_hint_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    monkeypatch.delenv("UTVALG_DATA_DIR", raising=False)
    assert app_paths.read_data_dir_hint() is None


def test_sources_dir_uses_env_override_even_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    hint_target = tmp_path / "shared_sources"
    hint_target.mkdir(parents=True)
    app_paths.write_sources_dir_hint(str(hint_target))

    env_target = tmp_path / "env_sources"
    env_target.mkdir(parents=True)
    monkeypatch.setenv("UTVALG_SOURCES_DIR", str(env_target))

    assert app_paths.sources_dir() == env_target.expanduser().resolve()


def test_sources_dir_uses_hint_file_when_env_not_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    monkeypatch.delenv("UTVALG_SOURCES_DIR", raising=False)

    target = tmp_path / "configured_sources"
    target.mkdir(parents=True)
    app_paths.write_sources_dir_hint(str(target))

    assert app_paths.sources_dir() == target.expanduser().resolve()


def test_clear_sources_dir_hint_removes_hint_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    target = tmp_path / "sources"
    target.mkdir(parents=True)
    hint_file = app_paths.write_sources_dir_hint(str(target))

    assert hint_file.exists()
    app_paths.clear_sources_dir_hint()
    assert not hint_file.exists()
    assert app_paths.read_sources_dir_hint() is None
