"""Tester for workpaper_library.py og handling ↔ arbeidspapir-kobling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import action_library
import workpaper_library
from action_library import LocalAction
from workpaper_library import Workpaper


@pytest.fixture
def tmp_wp(tmp_path: Path) -> Path:
    return tmp_path / "workpapers.json"


@pytest.fixture
def tmp_actions(tmp_path: Path) -> Path:
    return tmp_path / "actions.json"


def test_load_missing_returns_empty(tmp_wp: Path) -> None:
    assert workpaper_library.load_library(tmp_wp) == []


def test_upsert_roundtrip(tmp_wp: Path) -> None:
    w = Workpaper.new("Regnskapsoppstilling (Excel)", kategori="generert",
                      generator_id="export_regnskap_excel")
    workpaper_library.upsert_workpaper(w, tmp_wp)
    items = workpaper_library.load_library(tmp_wp)
    assert len(items) == 1
    assert items[0].kategori == "generert"
    assert items[0].generator_id == "export_regnskap_excel"


def test_delete_removes(tmp_wp: Path) -> None:
    a = Workpaper.new("A")
    b = Workpaper.new("B")
    workpaper_library.upsert_workpaper(a, tmp_wp)
    workpaper_library.upsert_workpaper(b, tmp_wp)
    workpaper_library.delete_workpaper(a.id, tmp_wp)
    items = workpaper_library.load_library(tmp_wp)
    assert {w.navn for w in items} == {"B"}


def test_empty_navn_dropped(tmp_wp: Path) -> None:
    payload = {"workpapers": [{"id": "x", "navn": ""}]}
    tmp_wp.write_text(json.dumps(payload), encoding="utf-8")
    assert workpaper_library.load_library(tmp_wp) == []


def test_action_stores_workpaper_ids(tmp_actions: Path) -> None:
    a = LocalAction.new("Innledende analyse", workpaper_ids=["wp-1", "wp-2"])
    action_library.upsert_action(a, tmp_actions)
    loaded = action_library.load_library(tmp_actions)
    assert len(loaded) == 1
    assert loaded[0].workpaper_ids == ["wp-1", "wp-2"]


def test_action_workpaper_ids_default_empty(tmp_actions: Path) -> None:
    a = LocalAction.new("X")
    action_library.upsert_action(a, tmp_actions)
    loaded = action_library.load_library(tmp_actions)
    assert loaded[0].workpaper_ids == []


def test_action_normalizes_non_list_workpaper_ids(tmp_actions: Path) -> None:
    payload = {
        "actions": [
            {"id": "a", "navn": "Test", "workpaper_ids": "not-a-list"},
        ]
    }
    tmp_actions.write_text(json.dumps(payload), encoding="utf-8")
    loaded = action_library.load_library(tmp_actions)
    assert loaded[0].workpaper_ids == []


def test_action_strips_empty_workpaper_ids(tmp_actions: Path) -> None:
    payload = {
        "actions": [
            {"id": "a", "navn": "Test", "workpaper_ids": ["wp-1", "", "  ", "wp-2"]},
        ]
    }
    tmp_actions.write_text(json.dumps(payload), encoding="utf-8")
    loaded = action_library.load_library(tmp_actions)
    assert loaded[0].workpaper_ids == ["wp-1", "wp-2"]


def test_by_id_index() -> None:
    a = Workpaper.new("A")
    b = Workpaper.new("B")
    idx = workpaper_library.by_id([a, b])
    assert idx[a.id].navn == "A"
    assert idx[b.id].navn == "B"


def test_list_builtins_non_empty_and_locked() -> None:
    import workpaper_generators

    builtins = workpaper_library.list_builtins()
    assert len(builtins) == len(workpaper_generators.BUILTIN_GENERATORS)
    ids = {w.id for w in builtins}
    assert all(i.startswith("wp:") for i in ids)
    assert all(w.kategori == "generert" for w in builtins)
    # Alle generator_id peker på en metode som navngis av registeret
    expected_methods = {g.method_name for g in workpaper_generators.BUILTIN_GENERATORS}
    assert {w.generator_id for w in builtins} == expected_methods


def test_is_builtin_distinguishes_prefix() -> None:
    assert workpaper_library.is_builtin("wp:nokkeltall_html") is True
    assert workpaper_library.is_builtin("abc-def-123") is False
    assert workpaper_library.is_builtin("") is False


def test_list_all_merges_builtins_then_manual(tmp_wp: Path) -> None:
    manual = Workpaper.new("Eget notat", kategori="manuell")
    workpaper_library.upsert_workpaper(manual, tmp_wp)
    merged = workpaper_library.list_all(tmp_wp)
    assert len(merged) == len(workpaper_library.list_builtins()) + 1
    # Innebygde kommer først
    assert merged[0].id.startswith("wp:")
    # Manuelle til slutt
    assert merged[-1].id == manual.id


def test_builtin_ids_stable_for_known_generators() -> None:
    import workpaper_generators

    ids = {g.id for g in workpaper_generators.BUILTIN_GENERATORS}
    # Bakoverkompat — disse id-ene kan referanses i action_library.workpaper_ids
    assert "wp:regnskap_excel" in ids
    assert "wp:nokkeltall_pdf" in ids
    assert "wp:ib_ub_kontinuitet" in ids
    assert "wp:sb_hb_avstemming" in ids


def test_builtin_methods_exist_on_analyse_page() -> None:
    """Sanity: method_name peker på en attributt som faktisk finnes.

    Vi importerer ikke AnalysePage her (Tk-avhengig), men bekrefter at
    navnene minst har _export-prefiks slik at retning stemmer.
    """
    import workpaper_generators

    for g in workpaper_generators.BUILTIN_GENERATORS:
        assert g.method_name.startswith("_export_"), g.method_name
