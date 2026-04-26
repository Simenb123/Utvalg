from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import src.pages.dataset.frontend.pane_store as dataset_pane_store


def test_get_active_version_path_none_when_store_missing(monkeypatch) -> None:
    monkeypatch.setattr(dataset_pane_store, "_HAS_CLIENT_STORE", False, raising=False)
    monkeypatch.setattr(dataset_pane_store, "client_store", None, raising=False)
    assert dataset_pane_store.get_active_version_path("Demo AS", "2024") is None


def test_get_active_version_path_returns_existing_file(tmp_path: Path, monkeypatch) -> None:
    f = tmp_path / "hb.xlsx"
    f.write_text("dummy", encoding="utf-8")

    def _get_active_version(_client: str, *, year: str, dtype: str):
        assert year == "2024"
        assert dtype == "hb"
        return SimpleNamespace(path=str(f))

    stub = SimpleNamespace(get_active_version=_get_active_version)

    monkeypatch.setattr(dataset_pane_store, "_HAS_CLIENT_STORE", True, raising=False)
    monkeypatch.setattr(dataset_pane_store, "client_store", stub, raising=False)

    out = dataset_pane_store.get_active_version_path("Demo AS", "2024", "hb")
    assert out == str(f)


def test_get_active_version_path_none_when_file_missing(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "missing.xlsx"

    stub = SimpleNamespace(get_active_version=lambda _c, *, year, dtype: SimpleNamespace(path=str(missing)))
    monkeypatch.setattr(dataset_pane_store, "_HAS_CLIENT_STORE", True, raising=False)
    monkeypatch.setattr(dataset_pane_store, "client_store", stub, raising=False)

    assert dataset_pane_store.get_active_version_path("Demo AS", "2024", "hb") is None
