from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional, List
import json, tempfile, os

import app_paths

_BASE_DIR = Path(__file__).resolve().parent


def _file_path() -> Path:
    """Hvor ab_presets.json lagres.

    I frozen-modus lagrer vi i AppData (eller UTVALG_DATA_DIR) slik at filen
    ikke havner i en midlertidig utpakkingsmappe.
    """

    if app_paths.is_frozen():
        return app_paths.data_file("ab_presets.json")
    return _BASE_DIR / "ab_presets.json"

def _read_all() -> Dict[str, Any]:
    file_path = _file_path()

    # Best effort migrering (frozen): hvis vi ikke har filen i data-mappen,
    # prøv å lese fra gamle plasseringer og skriv til ny sti.
    if app_paths.is_frozen() and not file_path.exists():
        legacy = app_paths.best_effort_legacy_paths(
            app_paths.executable_dir() / "ab_presets.json",
            Path.cwd() / "ab_presets.json",
            _BASE_DIR / "ab_presets.json",
        )
        for lp in legacy:
            try:
                with open(lp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    _write_all(data)
                    break
            except Exception:
                continue

    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _write_all(data: Dict[str, Any]) -> None:
    file_path = _file_path()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.gettempdir()) / ("ab_presets.tmp.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, file_path)

def list_presets() -> List[str]:
    return sorted(_read_all().keys())

def get_preset(name: str) -> Optional[Dict[str, Any]]:
    data = _read_all()
    return data.get(name)

def save_preset(name: str, cfg: Dict[str, Any]) -> None:
    data = _read_all()
    data[name] = cfg
    _write_all(data)

def delete_preset(name: str) -> None:
    data = _read_all()
    if name in data:
        del data[name]
        _write_all(data)

# ---------- import/eksport ----------
def export_all(path: Path) -> Path:
    """Eksporter alle presets til gitt sti (JSON)."""
    path = Path(path)
    data = _read_all()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path

def import_merge(path: Path, replace: bool = False) -> int:
    """Importer fra JSON. replace=True erstatter hele filen, ellers merges (overskriver ved navnekollisjon).
    Returnerer antall nøkler som ble importert/oppdatert."""
    path = Path(path)
    if not path.exists():
        return 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            incoming = json.load(f)
        if not isinstance(incoming, dict):
            return 0
    except Exception:
        return 0
    if replace:
        _write_all(incoming)
        return len(incoming)
    current = _read_all()
    current.update(incoming)
    _write_all(current)
    return len(incoming)
