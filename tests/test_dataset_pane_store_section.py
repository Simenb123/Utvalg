"""Tests for Fase B — preview-fallback i _on_select_sb."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

import dataset_pane_store_section as dpss


class _FakeSection:
    """Minimal stand-in som eksponerer alt `_on_select_sb` trenger."""

    def __init__(self, *, client: str, year: str, path: str) -> None:
        self._client_name = client
        self._year_name = year
        self._path = path
        self.frame = object()  # bare en parent-placeholder
        self._on_tb_selected_cb = MagicMock()
        self._tb_set_called_with = None
        self._bus_events: list[tuple[str, object]] = []

    def _client(self) -> str:
        return self._client_name

    def _year(self) -> str:
        return self._year_name


@pytest.fixture
def fake_session(monkeypatch):
    session = SimpleNamespace(client=None, year=None, _tb=None)

    def set_tb(df):
        session._tb = df

    session.set_tb = set_tb
    monkeypatch.setitem(__import__("sys").modules, "session", session)
    return session


@pytest.fixture
def fake_bus(monkeypatch):
    captured: list[tuple[str, object]] = []

    class _Bus:
        def emit(self, name, payload):
            captured.append((name, payload))

    monkeypatch.setitem(__import__("sys").modules, "bus", _Bus())
    return captured


@pytest.fixture
def section_with_store(monkeypatch, tmp_path: Path):
    """Fake client_store som returnerer én SB-versjon."""
    sb_path = tmp_path / "sb.xlsx"
    sb_path.write_bytes(b"")

    store = SimpleNamespace()
    store.get_version = MagicMock(return_value=SimpleNamespace(path=str(sb_path)))

    monkeypatch.setattr(dpss, "_HAS_CLIENT_STORE", True, raising=False)
    monkeypatch.setattr(dpss, "client_store", store, raising=False)
    monkeypatch.setattr(dpss, "messagebox", MagicMock(), raising=False)

    section = _FakeSection(client="Demo AS", year="2024", path=str(sb_path))
    return section, store, sb_path


def _sample_tb_df() -> pd.DataFrame:
    return pd.DataFrame({
        "konto": ["3000"],
        "kontonavn": ["Salg"],
        "ib": [0.0],
        "ub": [-100.0],
        "netto": [-100.0],
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_on_select_sb_uses_auto_reader_first(monkeypatch, fake_session, fake_bus, section_with_store):
    section, store, sb_path = section_with_store

    auto_df = _sample_tb_df()
    read_mock = MagicMock(return_value=auto_df)
    preview_mock = MagicMock()  # skal ikke kalles
    monkeypatch.setitem(__import__("sys").modules, "trial_balance_reader",
                        SimpleNamespace(read_trial_balance=read_mock))
    monkeypatch.setitem(__import__("sys").modules, "tb_preview_dialog",
                        SimpleNamespace(open_tb_preview=preview_mock))

    dpss.ClientStoreSection._on_select_sb(section, "v1")

    read_mock.assert_called_once_with(str(sb_path))
    preview_mock.assert_not_called()
    assert fake_session._tb is auto_df
    assert fake_session.client == "Demo AS"
    assert fake_session.year == "2024"
    assert any(name == "TB_LOADED" for name, _ in fake_bus)
    section._on_tb_selected_cb.assert_called_once_with(str(sb_path))


def test_on_select_sb_opens_preview_on_read_error(monkeypatch, fake_session, fake_bus, section_with_store):
    section, _store, sb_path = section_with_store

    preview_df = _sample_tb_df()

    def _raise(*_a, **_kw):
        raise ValueError("tullete kolonner")

    read_mock = MagicMock(side_effect=_raise)
    preview_mock = MagicMock(return_value=(preview_df, "Demo AS"))
    monkeypatch.setitem(__import__("sys").modules, "trial_balance_reader",
                        SimpleNamespace(read_trial_balance=read_mock))
    monkeypatch.setitem(__import__("sys").modules, "tb_preview_dialog",
                        SimpleNamespace(open_tb_preview=preview_mock))

    dpss.ClientStoreSection._on_select_sb(section, "v1")

    preview_mock.assert_called_once()
    assert fake_session._tb is preview_df
    assert any(name == "TB_LOADED" for name, _ in fake_bus)


def test_on_select_sb_cancelled_preview_does_not_mutate_session(
    monkeypatch, fake_session, fake_bus, section_with_store,
):
    section, _store, _sb_path = section_with_store

    read_mock = MagicMock(side_effect=RuntimeError("les-feil"))
    preview_mock = MagicMock(return_value=None)  # bruker avbrøt
    monkeypatch.setitem(__import__("sys").modules, "trial_balance_reader",
                        SimpleNamespace(read_trial_balance=read_mock))
    monkeypatch.setitem(__import__("sys").modules, "tb_preview_dialog",
                        SimpleNamespace(open_tb_preview=preview_mock))

    dpss.ClientStoreSection._on_select_sb(section, "v1")

    preview_mock.assert_called_once()
    assert fake_session._tb is None
    assert fake_session.client is None
    assert fake_session.year is None
    assert fake_bus == []
    section._on_tb_selected_cb.assert_not_called()


def test_on_select_sb_confirmed_preview_triggers_tb_loaded(
    monkeypatch, fake_session, fake_bus, section_with_store,
):
    section, _store, sb_path = section_with_store

    preview_df = _sample_tb_df()
    read_mock = MagicMock(side_effect=ValueError("rå read feilet"))
    preview_mock = MagicMock(return_value=(preview_df, "Ignoreres"))
    monkeypatch.setitem(__import__("sys").modules, "trial_balance_reader",
                        SimpleNamespace(read_trial_balance=read_mock))
    monkeypatch.setitem(__import__("sys").modules, "tb_preview_dialog",
                        SimpleNamespace(open_tb_preview=preview_mock))

    dpss.ClientStoreSection._on_select_sb(section, "v1")

    events = [name for name, _ in fake_bus]
    assert "TB_LOADED" in events
    section._on_tb_selected_cb.assert_called_once_with(str(sb_path))
