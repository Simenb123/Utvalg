# ml_map.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, List

_STORE = Path(".ml_map.json")

def _load() -> dict:
    if _STORE.exists():
        try:
            return json.loads(_STORE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def _save(obj: dict) -> None:
    _STORE.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

def _make_key(headers: List[str]) -> str:
    # Nøkkel basert på sett av col-names (rekkefølge-uavhengig)
    return "|".join(sorted([str(h).strip().lower() for h in headers]))

def suggest(headers: List[str]) -> Dict[str, str] | None:
    db = _load()
    return db.get(_make_key(headers))

def learn(headers: List[str], mapping: Dict[str, str]) -> None:
    db = _load()
    db[_make_key(headers)] = mapping
    _save(db)
