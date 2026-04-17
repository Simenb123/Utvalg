"""storage.py — JSON-lagring og -lasting av Diagram."""

from __future__ import annotations

import json
from pathlib import Path

from .model import Diagram


def save_diagram(diagram: Diagram, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(diagram.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def load_diagram(path: str | Path) -> Diagram:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    return Diagram.from_dict(data)
