from __future__ import annotations

import json
from pathlib import Path


def load_mapping(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mapping file does not exist: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mapping JSON must be an object with account->code pairs")

    out: dict[str, str] = {}
    for k, v in data.items():
        kk = str(k).strip()
        if not kk:
            continue
        vv = "" if v is None else str(v).strip()
        out[kk] = vv
    return out


def save_mapping(path: str | Path, mapping: dict[str, str]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        str(k): ("" if v is None else str(v))
        for k, v in sorted(mapping.items(), key=lambda kv: str(kv[0]))
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
