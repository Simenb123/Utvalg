from __future__ import annotations
from dataclasses import dataclass
@dataclass
class Preferences:
    default_direction: str = "Alle"
def load_preferences() -> Preferences:
    return Preferences()
