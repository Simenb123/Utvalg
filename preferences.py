from __future__ import annotations
from dataclasses import dataclass, asdict
import json
import os
from typing import Any

@dataclass
class Preferences:
    default_direction: str = "Alle"  # "Alle" | "Debet" | "Kredit"
    decimal_comma: bool = True       # reserve – brukes senere hvis vi vil gjøre dette endringsbart i UI

_PREF_PATH = os.path.join(os.path.expanduser("~"), ".utvalg_prefs.json")

def load_preferences() -> Preferences:
    try:
        with open(_PREF_PATH, "r", encoding="utf-8") as f:
            raw: dict[str, Any] = json.load(f)
        return Preferences(**{k: raw.get(k, v) for k, v in asdict(Preferences()).items()})
    except Exception:
        return Preferences()

def save_preferences(p: Preferences) -> None:
    try:
        with open(_PREF_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(p), f, ensure_ascii=False, indent=2)
    except Exception:
        pass
