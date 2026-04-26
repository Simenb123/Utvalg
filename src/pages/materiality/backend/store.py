from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import src.shared.client_store.store as client_store


SCHEMA_VERSION = 1
STATE_FILE = "materiality.json"
_CLIENT_NO_PREFIX_RE = re.compile(r"^\s*(\d{2,12})\s+")

SELECTION_THRESHOLD_KEYS = (
    "performance_materiality",
    "overall_materiality",
    "clearly_trivial",
    "manual",
)
DEFAULT_SELECTION_THRESHOLD_KEY = "performance_materiality"
SELECTION_THRESHOLD_LABELS: dict[str, str] = {
    "performance_materiality": "Arbeidsvesentlighet (PM)",
    "overall_materiality": "Total vesentlighet (OM)",
    "clearly_trivial": "Grense ubetydelig feil",
    "manual": "Manuell",
}
_SELECTION_THRESHOLD_ALIASES = {
    "pm": "performance_materiality",
    "performance": "performance_materiality",
    "performance_materiality": "performance_materiality",
    "om": "overall_materiality",
    "overall": "overall_materiality",
    "overall_materiality": "overall_materiality",
    "trivial": "clearly_trivial",
    "clearlytriv": "clearly_trivial",
    "clearly_triv": "clearly_trivial",
    "clearly_trivial": "clearly_trivial",
    "manual": "manual",
}


def utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def materiality_dir(client: str, year: str) -> Path:
    base = client_store.years_dir(client, year=year)
    target = base / "materiality"
    target.mkdir(parents=True, exist_ok=True)
    return target


def materiality_path(client: str, year: str) -> Path:
    return materiality_dir(client, year) / STATE_FILE


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_state(client: str, year: str) -> dict[str, Any]:
    path = materiality_path(client, year)
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "client": client,
            "year": year,
            "crm_client_number": "",
            "active_materiality": None,
            "last_local_calculation": None,
            "selection_threshold_key": DEFAULT_SELECTION_THRESHOLD_KEY,
            "updated_at_utc": "",
        }
    data = _read_json(path)
    if not isinstance(data, dict):
        data = {}
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("client", client)
    data.setdefault("year", year)
    data.setdefault("crm_client_number", "")
    data.setdefault("active_materiality", None)
    data.setdefault("last_local_calculation", None)
    data.setdefault("selection_threshold_key", DEFAULT_SELECTION_THRESHOLD_KEY)
    data.setdefault("updated_at_utc", "")
    return data


def save_state(client: str, year: str, payload: Mapping[str, Any]) -> Path:
    body = dict(payload)
    body["schema_version"] = SCHEMA_VERSION
    body["client"] = client
    body["year"] = year
    body["updated_at_utc"] = utc_now_z()
    path = materiality_path(client, year)
    _write_json_atomic(path, body)
    return path


def merge_state(client: str, year: str, updates: Mapping[str, Any]) -> dict[str, Any]:
    current = load_state(client, year)
    current.update(dict(updates))
    save_state(client, year, current)
    return current


def extract_prefixed_client_number(display_name: str) -> str:
    match = _CLIENT_NO_PREFIX_RE.match(display_name or "")
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def to_descartes_client_number(client_number: str) -> str:
    digits = "".join(ch for ch in str(client_number or "").strip() if ch.isdigit())
    if len(digits) >= 3 and digits[:2] in {"14", "15"} and digits[2:].isdigit():
        return digits[2:]
    return digits


def build_candidate_client_numbers(display_name: str, override: str = "") -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        v = "".join(ch for ch in str(value or "").strip() if ch.isdigit())
        if not v or v in seen:
            return
        seen.add(v)
        candidates.append(v)

    override_digits = "".join(ch for ch in str(override or "").strip() if ch.isdigit())
    prefixed = extract_prefixed_client_number(display_name)
    derived = to_descartes_client_number(override_digits or prefixed)

    _push(override_digits)
    _push(derived)
    _push(prefixed)

    derived_from_prefixed = to_descartes_client_number(prefixed)
    if derived_from_prefixed != derived:
        _push(derived_from_prefixed)

    return candidates


def normalize_selection_threshold_key(value: object) -> str:
    raw = str(value or "").strip().lower()
    key = _SELECTION_THRESHOLD_ALIASES.get(raw, raw)
    if key in SELECTION_THRESHOLD_KEYS:
        return key
    return DEFAULT_SELECTION_THRESHOLD_KEY


def get_selection_threshold_label(value: object) -> str:
    key = normalize_selection_threshold_key(value)
    return SELECTION_THRESHOLD_LABELS.get(key, SELECTION_THRESHOLD_LABELS[DEFAULT_SELECTION_THRESHOLD_KEY])


def resolve_selection_threshold(active_materiality: object, preferred_key: object = None) -> tuple[str, float | None]:
    key = normalize_selection_threshold_key(preferred_key)
    if key == "manual":
        return key, None
    if not isinstance(active_materiality, Mapping):
        return key, None

    def _amount_for(field_name: str) -> float | None:
        raw = active_materiality.get(field_name)
        try:
            amount = float(raw)
        except Exception:
            return None
        amount = abs(amount)
        if amount <= 0.0:
            return None
        return amount

    amount = _amount_for(key)
    if amount is not None:
        return key, amount

    for fallback_key in (
        "performance_materiality",
        "overall_materiality",
        "clearly_trivial",
    ):
        amount = _amount_for(fallback_key)
        if amount is not None:
            return fallback_key, amount

    return key, None
