"""Tests for action_workpaper_store — Handlinger 2.0 slice 1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import action_workpaper_store as store
from action_workpaper_store import ActionWorkpaper


@pytest.fixture
def _mock_years_dir(tmp_path, monkeypatch):
    def fake_years_dir(display_name: str, *, year: str) -> Path:
        p = tmp_path / display_name / "years" / year
        p.mkdir(parents=True, exist_ok=True)
        return p

    monkeypatch.setattr(store.client_store, "years_dir", fake_years_dir)
    return tmp_path


class TestLoadEmpty:
    def test_load_nonexistent_returns_empty(self, _mock_years_dir):
        assert store.load_workpapers("Acme AS", "2025") == {}

    def test_load_missing_client_returns_empty(self, _mock_years_dir):
        assert store.load_workpapers(None, "2025") == {}
        assert store.load_workpapers("Acme AS", None) == {}

    def test_load_corrupt_json_returns_empty(self, _mock_years_dir, tmp_path):
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger"
        path.mkdir(parents=True, exist_ok=True)
        (path / "workpapers.json").write_text("{not valid json", encoding="utf-8")
        assert store.load_workpapers("Acme AS", "2025") == {}


class TestConfirmRegnr:
    def test_confirm_creates_file_and_returns_workpaper(self, _mock_years_dir):
        wp = store.confirm_regnr(
            "Acme AS", "2025", 42,
            regnr="70",
            regnskapslinje="Annen driftskostnad",
            confirmed_by="revisor@firma.no",
            note="ADK-sjekk",
        )
        assert wp.action_id == 42
        assert wp.confirmed_regnr == "70"
        assert wp.confirmed_regnskapslinje == "Annen driftskostnad"
        assert wp.confirmed_by == "revisor@firma.no"
        assert wp.confirmed_at  # timestamp stamped

        loaded = store.load_workpapers("Acme AS", "2025")
        assert 42 in loaded
        assert loaded[42].confirmed_regnr == "70"

    def test_confirm_roundtrip_preserves_fields(self, _mock_years_dir):
        store.confirm_regnr(
            "Acme AS", "2025", 7,
            regnr="605",
            regnskapslinje="Varelager",
            confirmed_by="abc",
            note="bekreftet etter gjennomgang",
            confirmed_at="2026-04-17T12:00:00+00:00",
        )
        loaded = store.load_workpapers("Acme AS", "2025")
        wp = loaded[7]
        assert wp.confirmed_regnr == "605"
        assert wp.confirmed_regnskapslinje == "Varelager"
        assert wp.confirmed_by == "abc"
        assert wp.note == "bekreftet etter gjennomgang"
        assert wp.confirmed_at == "2026-04-17T12:00:00+00:00"

    def test_confirm_overwrites_previous_confirmation(self, _mock_years_dir):
        store.confirm_regnr("Acme AS", "2025", 1, regnr="10", regnskapslinje="Salg")
        store.confirm_regnr("Acme AS", "2025", 1, regnr="20", regnskapslinje="Varekost")
        loaded = store.load_workpapers("Acme AS", "2025")
        assert loaded[1].confirmed_regnr == "20"
        assert loaded[1].confirmed_regnskapslinje == "Varekost"

    def test_confirm_rejects_invalid_action_id(self, _mock_years_dir):
        with pytest.raises(ValueError):
            store.confirm_regnr("Acme AS", "2025", 0, regnr="10")

    def test_confirm_rejects_empty_regnr(self, _mock_years_dir):
        with pytest.raises(ValueError):
            store.confirm_regnr("Acme AS", "2025", 1, regnr="   ")


class TestClearConfirmation:
    def test_clear_removes_entry(self, _mock_years_dir):
        store.confirm_regnr("Acme AS", "2025", 1, regnr="10")
        store.confirm_regnr("Acme AS", "2025", 2, regnr="20")
        assert store.clear_confirmation("Acme AS", "2025", 1) is True
        loaded = store.load_workpapers("Acme AS", "2025")
        assert 1 not in loaded
        assert 2 in loaded

    def test_clear_nonexistent_returns_false(self, _mock_years_dir):
        assert store.clear_confirmation("Acme AS", "2025", 999) is False


class TestPersistenceFormat:
    def test_json_is_keyed_by_action_id_as_string(self, _mock_years_dir, tmp_path):
        store.confirm_regnr("Acme AS", "2025", 42, regnr="70", regnskapslinje="ADK")
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger" / "workpapers.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "42" in data
        assert data["42"]["confirmed_regnr"] == "70"

    def test_empty_regnr_entries_pruned_on_save(self, _mock_years_dir, tmp_path):
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger"
        path.mkdir(parents=True, exist_ok=True)
        raw = {
            "1": {"action_id": 1, "confirmed_regnr": "10"},
            "2": {"action_id": 2, "confirmed_regnr": ""},
        }
        (path / "workpapers.json").write_text(json.dumps(raw), encoding="utf-8")
        loaded = store.load_workpapers("Acme AS", "2025")
        assert 1 in loaded
        assert 2 not in loaded


class TestResolveEffectiveRegnr:
    def test_confirmed_overrides_auto_match(self):
        wps = {
            42: ActionWorkpaper(
                action_id=42, confirmed_regnr="70",
                confirmed_regnskapslinje="ADK",
            )
        }
        regnr, rl, source = store.resolve_effective_regnr(42, "10", "Salg", wps)
        assert regnr == "70"
        assert rl == "ADK"
        assert source == "confirmed"

    def test_falls_back_to_auto_when_no_confirmation(self):
        regnr, rl, source = store.resolve_effective_regnr(42, "10", "Salg", {})
        assert regnr == "10"
        assert rl == "Salg"
        assert source == "auto"

    def test_returns_empty_when_no_match_at_all(self):
        regnr, rl, source = store.resolve_effective_regnr(42, "", "", {})
        assert regnr == ""
        assert rl == ""
        assert source == ""

    def test_none_workpapers_uses_auto(self):
        regnr, _, source = store.resolve_effective_regnr(42, "10", "Salg", None)
        assert regnr == "10"
        assert source == "auto"

    def test_other_action_id_confirmed_does_not_bleed(self):
        wps = {99: ActionWorkpaper(action_id=99, confirmed_regnr="70")}
        regnr, _, source = store.resolve_effective_regnr(42, "10", "Salg", wps)
        assert regnr == "10"
        assert source == "auto"


class TestActionWorkpaperSerialization:
    def test_to_dict_includes_all_fields(self):
        wp = ActionWorkpaper(
            action_id=1, confirmed_regnr="10",
            confirmed_regnskapslinje="Salg",
            confirmed_at="2026-04-17T00:00:00+00:00",
            confirmed_by="rev", note="note",
        )
        d = wp.to_dict()
        assert d["action_id"] == 1
        assert d["confirmed_regnr"] == "10"
        assert d["note"] == "note"

    def test_from_dict_handles_missing_keys(self):
        wp = ActionWorkpaper.from_dict({"action_id": 5, "confirmed_regnr": "70"})
        assert wp.action_id == 5
        assert wp.confirmed_regnr == "70"
        assert wp.note == ""

    def test_from_dict_coerces_action_id_from_string(self):
        wp = ActionWorkpaper.from_dict({"action_id": "42", "confirmed_regnr": "70"})
        assert wp.action_id == 42
