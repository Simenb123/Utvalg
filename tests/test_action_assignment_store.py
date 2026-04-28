"""Tests for action_assignment_store — direkte handling-ansvar."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import src.audit_actions.assignment_store as store


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
        assert store.load_assignments("Acme AS", "2025") == {}

    def test_load_missing_client_returns_empty(self, _mock_years_dir):
        assert store.load_assignments(None, "2025") == {}
        assert store.load_assignments("Acme AS", None) == {}

    def test_load_corrupt_json_returns_empty(self, _mock_years_dir, tmp_path):
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger"
        path.mkdir(parents=True, exist_ok=True)
        (path / "assignments.json").write_text("{not valid", encoding="utf-8")
        assert store.load_assignments("Acme AS", "2025") == {}

    def test_load_strips_blank_entries(self, _mock_years_dir, tmp_path):
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger"
        path.mkdir(parents=True, exist_ok=True)
        raw = {"42": "sb", "  ": "tn", "99": "  "}
        (path / "assignments.json").write_text(json.dumps(raw), encoding="utf-8")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"42": "SB"}


class TestSetAssignment:
    def test_set_persists_uppercase(self, _mock_years_dir):
        store.set_assignment("Acme AS", "2025", "42", "sb")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"42": "SB"}

    def test_set_supports_local_action_keys(self, _mock_years_dir):
        store.set_assignment("Acme AS", "2025", "L:abc-123", "tn")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"L:abc-123": "TN"}

    def test_set_overwrites_previous_value(self, _mock_years_dir):
        store.set_assignment("Acme AS", "2025", "42", "sb")
        store.set_assignment("Acme AS", "2025", "42", "tn")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"42": "TN"}

    def test_set_blank_initials_removes_entry(self, _mock_years_dir):
        store.set_assignment("Acme AS", "2025", "42", "sb")
        store.set_assignment("Acme AS", "2025", "42", "")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {}

    def test_set_rejects_empty_action_key(self, _mock_years_dir):
        with pytest.raises(ValueError):
            store.set_assignment("Acme AS", "2025", "  ", "sb")

    def test_set_rejects_missing_client_or_year(self, _mock_years_dir):
        with pytest.raises(ValueError):
            store.set_assignment("", "2025", "42", "sb")
        with pytest.raises(ValueError):
            store.set_assignment("Acme AS", "", "42", "sb")


class TestSetMany:
    def test_set_many_assigns_same_initials(self, _mock_years_dir):
        store.set_many("Acme AS", "2025", ["1", "2", "L:abc"], "sb")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"1": "SB", "2": "SB", "L:abc": "SB"}

    def test_set_many_blank_clears_all(self, _mock_years_dir):
        store.set_many("Acme AS", "2025", ["1", "2"], "sb")
        store.set_many("Acme AS", "2025", ["1", "2"], "")
        assert store.load_assignments("Acme AS", "2025") == {}

    def test_set_many_skips_blank_keys(self, _mock_years_dir):
        store.set_many("Acme AS", "2025", ["1", "  ", "2"], "tn")
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"1": "TN", "2": "TN"}


class TestClearAssignment:
    def test_clear_removes_entry(self, _mock_years_dir):
        store.set_assignment("Acme AS", "2025", "1", "sb")
        store.set_assignment("Acme AS", "2025", "2", "tn")
        assert store.clear_assignment("Acme AS", "2025", "1") is True
        loaded = store.load_assignments("Acme AS", "2025")
        assert loaded == {"2": "TN"}

    def test_clear_unknown_returns_false(self, _mock_years_dir):
        assert store.clear_assignment("Acme AS", "2025", "999") is False


class TestPersistenceFormat:
    def test_json_keyed_by_action_key(self, _mock_years_dir, tmp_path):
        store.set_assignment("Acme AS", "2025", "42", "sb")
        path = tmp_path / "Acme AS" / "years" / "2025" / "handlinger" / "assignments.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == {"42": "SB"}
