from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, Optional, List
import json, tempfile, os

_FILE = Path(__file__).resolve().parent / "ab_presets.json"

def _read_all() -> Dict[str, Any]:
    if not _FILE.exists():
        return {}
    try:
        with open(_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _write_all(data: Dict[str, Any]) -> None:
    tmp = Path(tempfile.gettempdir()) / ("ab_presets.tmp.json")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _FILE)

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