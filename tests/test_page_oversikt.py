"""Tests for OversiktPage."""
from __future__ import annotations

import pytest


def test_oversikt_page_imports() -> None:
    """OversiktPage should be importable."""
    from src.pages.oversikt import page_oversikt
    assert hasattr(page_oversikt, "OversiktPage")


def test_get_recent_clients_returns_list() -> None:
    """preferences.get_recent_clients should return a list."""
    import preferences
    result = preferences.get_recent_clients()
    assert isinstance(result, list)


def test_add_recent_client_stores_entry(monkeypatch, tmp_path) -> None:
    """add_recent_client should store client in memory."""
    import preferences

    prefs_file = str(tmp_path / "prefs.json")
    monkeypatch.setattr(preferences, "_PREFS_PATH", prefs_file)
    monkeypatch.setattr(preferences, "_DATA", {})

    preferences.add_recent_client("TestKlient AS")
    clients = preferences.get_recent_clients()
    assert len(clients) >= 1
    assert clients[0]["name"] == "TestKlient AS"


def test_add_recent_client_deduplicates(monkeypatch, tmp_path) -> None:
    """Adding same client twice should not create duplicates."""
    import preferences

    prefs_file = str(tmp_path / "prefs.json")
    monkeypatch.setattr(preferences, "_PREFS_PATH", prefs_file)
    monkeypatch.setattr(preferences, "_DATA", {})

    preferences.add_recent_client("Firma A")
    preferences.add_recent_client("Firma B")
    preferences.add_recent_client("Firma A")  # duplicate

    clients = preferences.get_recent_clients()
    names = [c["name"] for c in clients]
    assert names.count("Firma A") == 1
    assert names[0] == "Firma A"  # most recent first
