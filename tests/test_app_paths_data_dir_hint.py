from __future__ import annotations

from pathlib import Path

import pytest

import app_paths


def test_data_dir_uses_env_override_even_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Hint file
    monkeypatch.setattr(app_paths, "executable_dir", lambda: tmp_path)
    hint_target = tmp_path / "hint_target"
    app_paths.write_data_dir_hint(str(hint_target))

    # Env override must win
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
