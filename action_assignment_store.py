"""Action assignment store — persistens for direkte handling-ansvar.

Lagrer hvem på teamet som er ansvarlig for *selve* revisjonshandlingen,
uavhengig av konto-/RL-koblinger. Lever ved siden av aggregert
``assigned_to`` fra ``regnskap_client_overrides`` (se
``doc/architecture/ansvar_tilordning.md``).

Filformat: ``years/<YYYY>/handlinger/assignments.json`` med
``{action_key: initials}``. ``action_key`` er strengen som brukes som
``iid`` i tabellen — ``str(action_id)`` for CRM-handlinger eller
``"L:<id>"`` for lokale handlinger, slik at samme lager dekker begge.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import client_store


def _handlinger_dir(client: str, year: str) -> Path:
    base = client_store.years_dir(client, year=year)
    target = base / "handlinger"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _assignments_path(client: str, year: str) -> Path:
    return _handlinger_dir(client, year) / "assignments.json"


def load_assignments(client: str | None, year: str | None) -> dict[str, str]:
    """Returner ``{action_key: initials}``. Tom dict ved manglende fil."""
    if not client or not year:
        return {}
    path = _assignments_path(client, year)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        v = str(value or "").strip().upper()
        if k and v:
            out[k] = v
    return out


def _save_all(client: str, year: str, assignments: Mapping[str, str]) -> Path:
    path = _assignments_path(client, year)
    payload = {
        str(k).strip(): str(v).strip().upper()
        for k, v in assignments.items()
        if str(k).strip() and str(v).strip()
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def set_assignment(
    client: str, year: str, action_key: str, initials: str
) -> dict[str, str]:
    """Sett (eller fjern) ansvarlig for én handling. Returner full mapping."""
    if not client or not year:
        raise ValueError("client og year må være satt")
    key = str(action_key or "").strip()
    if not key:
        raise ValueError("action_key kan ikke være tom")
    assignments = load_assignments(client, year)
    value = str(initials or "").strip().upper()
    if value:
        assignments[key] = value
    else:
        assignments.pop(key, None)
    _save_all(client, year, assignments)
    return assignments


def set_many(
    client: str, year: str, action_keys: list[str], initials: str
) -> dict[str, str]:
    """Sett samme ansvarlig for flere handlinger på én gang."""
    if not client or not year:
        raise ValueError("client og year må være satt")
    assignments = load_assignments(client, year)
    value = str(initials or "").strip().upper()
    for raw_key in action_keys or []:
        key = str(raw_key or "").strip()
        if not key:
            continue
        if value:
            assignments[key] = value
        else:
            assignments.pop(key, None)
    _save_all(client, year, assignments)
    return assignments


def clear_assignment(client: str, year: str, action_key: str) -> bool:
    """Fjern ansvarlig for én handling. Returner True hvis noe ble fjernet."""
    if not client or not year:
        return False
    key = str(action_key or "").strip()
    assignments = load_assignments(client, year)
    if key not in assignments:
        return False
    del assignments[key]
    _save_all(client, year, assignments)
    return True
