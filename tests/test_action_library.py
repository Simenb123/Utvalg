"""Tester for lokalt handlingsbibliotek (action_library.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import action_library
from action_library import DEFAULT_ACTION_TYPES, LocalAction


@pytest.fixture
def tmp_lib(tmp_path: Path) -> Path:
    return tmp_path / "action_library.json"


def test_load_missing_returns_empty(tmp_lib: Path) -> None:
    assert action_library.load_library(tmp_lib) == []


def test_load_invalid_json_returns_empty(tmp_lib: Path) -> None:
    tmp_lib.write_text("not json", encoding="utf-8")
    assert action_library.load_library(tmp_lib) == []


def test_upsert_roundtrip(tmp_lib: Path) -> None:
    a = LocalAction.new("Kontroll av eierskap", type="kontroll", omraade="Innledende")
    action_library.upsert_action(a, tmp_lib)
    items = action_library.load_library(tmp_lib)
    assert len(items) == 1
    assert items[0].navn == "Kontroll av eierskap"
    assert items[0].type == "kontroll"
    assert items[0].omraade == "Innledende"
    assert items[0].opprettet and items[0].endret


def test_upsert_updates_existing(tmp_lib: Path) -> None:
    a = LocalAction.new("Første navn")
    action_library.upsert_action(a, tmp_lib)
    a.navn = "Oppdatert navn"
    a.beskrivelse = "ny"
    action_library.upsert_action(a, tmp_lib)
    items = action_library.load_library(tmp_lib)
    assert len(items) == 1
    assert items[0].navn == "Oppdatert navn"
    assert items[0].beskrivelse == "ny"


def test_delete_removes(tmp_lib: Path) -> None:
    a = LocalAction.new("X")
    b = LocalAction.new("Y")
    action_library.upsert_action(a, tmp_lib)
    action_library.upsert_action(b, tmp_lib)
    action_library.delete_action(a.id, tmp_lib)
    items = action_library.load_library(tmp_lib)
    assert {i.navn for i in items} == {"Y"}


def test_custom_type_preserved(tmp_lib: Path) -> None:
    payload = {"actions": [{"id": "x", "navn": "Egendefinert", "type": "min-egen-type"}]}
    tmp_lib.write_text(json.dumps(payload), encoding="utf-8")
    items = action_library.load_library(tmp_lib)
    assert len(items) == 1
    assert items[0].type == "min-egen-type"


def test_types_default_when_missing(tmp_lib: Path) -> None:
    assert action_library.load_types(tmp_lib) == list(DEFAULT_ACTION_TYPES)


def test_save_and_load_custom_types(tmp_lib: Path) -> None:
    action_library.save_types(["detaljkontroll", "analyse", "samtale"], tmp_lib)
    assert action_library.load_types(tmp_lib) == ["detaljkontroll", "analyse", "samtale"]


def test_save_types_preserves_actions(tmp_lib: Path) -> None:
    a = LocalAction.new("Behold meg")
    action_library.upsert_action(a, tmp_lib)
    action_library.save_types(["x", "y"], tmp_lib)
    items = action_library.load_library(tmp_lib)
    assert len(items) == 1 and items[0].navn == "Behold meg"
    assert action_library.load_types(tmp_lib) == ["x", "y"]


def test_save_types_dedupes_and_strips(tmp_lib: Path) -> None:
    result = action_library.save_types(["  a ", "b", "a", "", "c"], tmp_lib)
    assert result == ["a", "b", "c"]


def test_empty_navn_dropped(tmp_lib: Path) -> None:
    payload = {"actions": [{"id": "x", "navn": "", "type": "kontroll"}]}
    tmp_lib.write_text(json.dumps(payload), encoding="utf-8")
    assert action_library.load_library(tmp_lib) == []


def test_default_action_types_contains_expected() -> None:
    assert "substansiv" in DEFAULT_ACTION_TYPES
    assert "kontroll" in DEFAULT_ACTION_TYPES
