from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import src.pages.dataset.frontend.pane_store as dataset_pane_store


def test_get_active_version_path_returns_none_when_store_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dataset_pane_store, "_HAS_CLIENT_STORE", False, raising=False)
    monkeypatch.setattr(dataset_pane_store, "client_store", None, raising=False)
    assert dataset_pane_store.get_active_version_path("Demo AS", "2025") is None


def test_get_active_version_path_returns_path_when_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    f = tmp_path / "hb.xlsx"
    f.write_text("dummy", encoding="utf-8")

    def _get_active_version(_client: str, *, year: str, dtype: str):
        assert year == "2025"
        assert dtype == "hb"
        return SimpleNamespace(path=str(f))

    stub = SimpleNamespace(get_active_version=_get_active_version)
    monkeypatch.setattr(dataset_pane_store, "_HAS_CLIENT_STORE", True, raising=False)
    monkeypatch.setattr(dataset_pane_store, "client_store", stub, raising=False)

    assert dataset_pane_store.get_active_version_path("Demo AS", "2025", "hb") == str(f)
