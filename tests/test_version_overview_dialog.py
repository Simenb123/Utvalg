from __future__ import annotations

from types import SimpleNamespace

from version_overview_dialog import _version_created_ts


def test_version_created_ts_prefers_created_at_for_current_model() -> None:
    version = SimpleNamespace(created_at=123.45)

    assert _version_created_ts(version) == 123.45


def test_version_created_ts_falls_back_to_legacy_created_ts() -> None:
    version = SimpleNamespace(created_ts=67.89)

    assert _version_created_ts(version) == 67.89
