"""Tester for brreg_mapping_config."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import brreg_mapping_config as bmc
import classification_config


@pytest.fixture(autouse=True)
def _tmp_repo_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Rut alle lese/skrive-operasjoner til tmp_path."""
    monkeypatch.setattr(classification_config, "repo_dir", lambda: tmp_path)
    yield


def test_load_returns_empty_when_file_missing() -> None:
    assert bmc.load_brreg_rl_mapping() == {}


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    mapping = {"salgsinntekt": 10, "sum_eiendeler": 665}
    path = bmc.save_brreg_rl_mapping(mapping)
    assert path.exists()
    loaded = bmc.load_brreg_rl_mapping()
    assert loaded == mapping


def test_save_coerces_types(tmp_path: Path) -> None:
    bmc.save_brreg_rl_mapping({"salgsinntekt": "10", 123: 5, "  ": 1, "x": "bad"})
    loaded = bmc.load_brreg_rl_mapping()
    assert loaded == {"salgsinntekt": 10}


def test_load_returns_empty_for_invalid_json(tmp_path: Path) -> None:
    path = bmc.resolve_brreg_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not valid json", encoding="utf-8")
    assert bmc.load_brreg_rl_mapping() == {}


def test_load_returns_empty_when_mappings_key_missing(tmp_path: Path) -> None:
    path = bmc.resolve_brreg_mapping_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"version": 1}), encoding="utf-8")
    assert bmc.load_brreg_rl_mapping() == {}


def test_null_value_preserved_as_disabled(tmp_path: Path) -> None:
    """``null`` i JSON = deaktiver alias-fallback for denne BRREG-nøkkelen."""
    mapping = {"salgsinntekt": 10, "finansinntekter": None}
    bmc.save_brreg_rl_mapping(mapping)
    loaded = bmc.load_brreg_rl_mapping()
    assert loaded == {"salgsinntekt": 10, "finansinntekter": None}


def test_list_brreg_keys_matches_brreg_keys_module() -> None:
    import brreg_rl_comparison as brc

    result = bmc.list_brreg_keys()
    assert len(result) == len(brc._BRREG_KEYS)
    keys = {pair[0] for pair in result}
    assert keys == set(brc._BRREG_KEYS.keys())
    # Alle labels er ikke-tomme
    for _key, label in result:
        assert label
