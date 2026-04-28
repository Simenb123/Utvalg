"""Action workpaper store — persistens for bekreftede regnskapslinje-koblinger.

Slice 1 av Handlinger 2.0: revisor kan bekrefte eller overstyre den
auto-matchede regnskapslinjen for en CRM-handling. Bekreftede koblinger
lagres per klient/år i ``years/<YYYY>/handlinger/workpapers.json``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import src.shared.client_store.store as client_store


@dataclass
class ActionWorkpaper:
    action_id: int = 0
    confirmed_regnr: str = ""
    confirmed_regnskapslinje: str = ""
    confirmed_at: str = ""
    confirmed_by: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ActionWorkpaper":
        try:
            aid = int(data.get("action_id") or 0)
        except Exception:
            aid = 0
        return cls(
            action_id=aid,
            confirmed_regnr=str(data.get("confirmed_regnr") or "").strip(),
            confirmed_regnskapslinje=str(data.get("confirmed_regnskapslinje") or "").strip(),
            confirmed_at=str(data.get("confirmed_at") or "").strip(),
            confirmed_by=str(data.get("confirmed_by") or "").strip(),
            note=str(data.get("note") or ""),
        )


def _handlinger_dir(client: str, year: str) -> Path:
    base = client_store.years_dir(client, year=year)
    target = base / "handlinger"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _workpapers_path(client: str, year: str) -> Path:
    return _handlinger_dir(client, year) / "workpapers.json"


def load_workpapers(client: str | None, year: str | None) -> dict[int, ActionWorkpaper]:
    """Last alle bekreftede workpapers for klient/år, indeksert på action_id."""
    if not client or not year:
        return {}
    path = _workpapers_path(client, year)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}

    result: dict[int, ActionWorkpaper] = {}
    for key, value in raw.items():
        if not isinstance(value, Mapping):
            continue
        wp = ActionWorkpaper.from_dict(value)
        if wp.action_id <= 0:
            try:
                wp.action_id = int(str(key).strip())
            except Exception:
                continue
        if wp.action_id <= 0 or not wp.confirmed_regnr:
            continue
        result[wp.action_id] = wp
    return result


def _save_all(client: str, year: str, workpapers: Mapping[int, ActionWorkpaper]) -> Path:
    path = _workpapers_path(client, year)
    payload = {
        str(int(aid)): wp.to_dict()
        for aid, wp in workpapers.items()
        if wp.confirmed_regnr
    }
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    return path


def confirm_regnr(
    client: str,
    year: str,
    action_id: int,
    *,
    regnr: str,
    regnskapslinje: str = "",
    confirmed_by: str = "",
    note: str = "",
    confirmed_at: str | None = None,
) -> ActionWorkpaper:
    """Lagre en bekreftet regnr-kobling for en handling og returner workpaper."""
    if int(action_id) <= 0:
        raise ValueError("action_id må være > 0")
    if not str(regnr).strip():
        raise ValueError("regnr kan ikke være tom")

    stamp = (confirmed_at or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    workpapers = load_workpapers(client, year)
    wp = ActionWorkpaper(
        action_id=int(action_id),
        confirmed_regnr=str(regnr).strip(),
        confirmed_regnskapslinje=str(regnskapslinje or "").strip(),
        confirmed_at=stamp,
        confirmed_by=str(confirmed_by or "").strip(),
        note=str(note or ""),
    )
    workpapers[wp.action_id] = wp
    _save_all(client, year, workpapers)
    return wp


def clear_confirmation(client: str, year: str, action_id: int) -> bool:
    """Fjern bekreftet kobling for en handling. Returnerer True hvis noe ble slettet."""
    workpapers = load_workpapers(client, year)
    key = int(action_id)
    if key not in workpapers:
        return False
    del workpapers[key]
    _save_all(client, year, workpapers)
    return True


def resolve_effective_regnr(
    action_id: int,
    auto_regnr: str,
    auto_regnskapslinje: str,
    workpapers: Mapping[int, ActionWorkpaper] | None,
) -> tuple[str, str, str]:
    """Returner (regnr, regnskapslinje, source).

    source er en av: ``"confirmed"``, ``"auto"``, ``""``.
    """
    if workpapers:
        wp = workpapers.get(int(action_id))
        if wp and wp.confirmed_regnr:
            return wp.confirmed_regnr, wp.confirmed_regnskapslinje, "confirmed"
    if auto_regnr:
        return str(auto_regnr).strip(), str(auto_regnskapslinje or "").strip(), "auto"
    return "", "", ""
