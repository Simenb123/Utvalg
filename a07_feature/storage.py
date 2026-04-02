from __future__ import annotations

import json
from pathlib import Path


def _read_json_object(path: str | Path) -> dict[str, object]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_json_object(path: str | Path, payload: dict[str, object]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


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


def load_locks(path: str | Path) -> set[str]:
    raw = _read_json_object(path)
    values = raw.get("codes")
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def save_locks(path: str | Path, locks: set[str]) -> Path:
    payload = {
        "codes": sorted({str(code).strip() for code in (locks or set()) if str(code).strip()}),
    }
    return _write_json_object(path, payload)


def load_project_state(path: str | Path) -> dict[str, object]:
    raw = _read_json_object(path)
    basis_col = str(raw.get("basis_col") or "").strip() or "Endring"
    selected_code = str(raw.get("selected_code") or "").strip() or None
    selected_group = str(raw.get("selected_group") or "").strip() or None
    return {
        "basis_col": basis_col,
        "selected_code": selected_code,
        "selected_group": selected_group,
    }


def save_project_state(path: str | Path, payload: dict[str, object]) -> Path:
    basis_col = str(payload.get("basis_col") or "").strip() or "Endring"
    selected_code = str(payload.get("selected_code") or "").strip()
    selected_group = str(payload.get("selected_group") or "").strip()
    out = {
        "basis_col": basis_col,
        "selected_code": selected_code or None,
        "selected_group": selected_group or None,
    }
    return _write_json_object(path, out)
