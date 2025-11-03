from __future__ import annotations
import json
import os
from typing import Dict, List

_PATH = os.path.join(os.path.expanduser("~"), ".utvalg_colmap.json")

def _load() -> dict:
    try:
        with open(_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _save(d: dict) -> None:
    try:
        with open(_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def _key(headers: List[str]) -> str:
    """Grov nøkkel av kolonnenavn (små bokstaver, sortert)."""
    return "|".join(sorted([h.strip().lower() for h in headers if h]))

def learn(headers: List[str], mapping: Dict[str, str]) -> None:
    db = _load()
    db[_key(headers)] = {k: v for k, v in mapping.items() if v}
    _save(db)

def suggest(headers: List[str]) -> Dict[str, str]:
    db = _load()
    return db.get(_key(headers), {})
