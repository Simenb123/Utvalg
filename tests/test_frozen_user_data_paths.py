from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _set_frozen(monkeypatch: pytest.MonkeyPatch, data_dir: Path) -> None:
    """Simuler PyInstaller/frozen og sett en deterministisk data-mappe."""

    monkeypatch.setenv("UTVALG_DATA_DIR", str(data_dir))
    # app_paths.is_frozen() sjekker sys.frozen eller sys._MEIPASS
    monkeypatch.setattr(sys, "frozen", True, raising=False)


def test_preferences_writes_to_data_dir_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_frozen(monkeypatch, tmp_path)

    import preferences

    importlib.reload(preferences)

    preferences.set("ui.test", 123)

    prefs_file = tmp_path / ".session" / "preferences.json"
    assert prefs_file.exists()
    obj = json.loads(prefs_file.read_text(encoding="utf-8"))
    assert obj["global"]["ui"]["test"] == 123


def test_column_memory_writes_to_data_dir_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_frozen(monkeypatch, tmp_path)

    import column_memory

    importlib.reload(column_memory)

    column_memory.set_learning_enabled(False)

    mem_file = tmp_path / "column_memory.json"
    assert mem_file.exists()
    obj = json.loads(mem_file.read_text(encoding="utf-8"))
    assert obj["flags"]["learning_enabled"] is False


def test_ab_prefs_writes_to_data_dir_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_frozen(monkeypatch, tmp_path)

    import ab_prefs

    importlib.reload(ab_prefs)

    ab_prefs.save_preset("demo", {"a": 1})

    preset_file = tmp_path / "ab_presets.json"
    assert preset_file.exists()
    obj = json.loads(preset_file.read_text(encoding="utf-8"))
    assert obj["demo"]["a"] == 1


def test_ml_map_utils_writes_to_data_dir_when_frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _set_frozen(monkeypatch, tmp_path)

    import ml_map_utils

    importlib.reload(ml_map_utils)

    headers = ["Kontonr", "Bilagsnr", "Bokført beløp", "Bilagsdato"]
    mapping = {"Beløp": "Bokført beløp", "Dato": "Bilagsdato"}
    ml_map_utils.update_ml_map(headers, mapping)

    ml_file = tmp_path / ".ml_map.json"
    assert ml_file.exists()
    obj = json.loads(ml_file.read_text(encoding="utf-8"))
    assert isinstance(obj, dict)
    # vi forventer at strukturen inneholder signatures etter update
    assert "signatures" in obj


def test_column_memory_invalid_json_falls_back_to_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Typisk feiltilfelle: korrupt JSON på disk skal ikke krasje."""

    _set_frozen(monkeypatch, tmp_path)

    # Skriv en ugyldig JSON-fil der modulene forventer den.
    bad_file = tmp_path / "column_memory.json"
    bad_file.write_text("{not valid json", encoding="utf-8")

    import column_memory

    importlib.reload(column_memory)

    # Skal ikke kaste; default er learning_enabled=True
    assert column_memory.is_learning_enabled() is True
