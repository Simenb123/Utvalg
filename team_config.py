# -*- coding: utf-8 -*-
"""team_config.py – brukeridentitet og teamfiltrering.

Leser config/team.json for å mappe Windows-brukernavn til Visena-initialer.
Brukes for å filtrere "mine klienter" basert på prosjektansvarlig/manager/medlem.
"""

from __future__ import annotations

import getpass
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "team.json"


@dataclass(frozen=True)
class TeamUser:
    windows_user: str
    visena_initials: str
    full_name: str
    email: str
    role: str


_cached_user: Optional[TeamUser] = None


def _load_config() -> dict:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        log.debug("Kunne ikke lese team.json", exc_info=True)
    return {}


def current_user() -> Optional[TeamUser]:
    """Returner TeamUser for nåværende Windows-bruker, eller None."""
    global _cached_user
    if _cached_user is not None:
        return _cached_user

    try:
        win_user = getpass.getuser().lower()
    except Exception:
        return None

    cfg = _load_config()
    users = cfg.get("users", {})

    # Prøv eksakt match på Windows-brukernavn
    entry = users.get(win_user)
    if entry is None:
        # Prøv case-insensitivt
        for k, v in users.items():
            if k.lower() == win_user:
                entry = v
                break

    if entry is None:
        return None

    _cached_user = TeamUser(
        windows_user=win_user,
        visena_initials=str(entry.get("visena_initials", "")).lower(),
        full_name=str(entry.get("full_name", "")),
        email=str(entry.get("email", "")),
        role=str(entry.get("role", "")),
    )
    return _cached_user


def current_visena_initials() -> str:
    """Returner Visena-initialer for nåværende bruker, eller tom streng."""
    u = current_user()
    return u.visena_initials if u else ""


def current_full_name() -> str:
    """Returner fullt navn for nåværende bruker, eller tom streng."""
    u = current_user()
    return u.full_name if u else ""


def list_team_members() -> list[dict]:
    """Returner alle teammedlemmer fra config/team.json.

    Hvert element: ``{"initials": str, "full_name": str, "label": str}``.
    ``label`` er formatet som vises i combobokser: "SB – Simen Bjørndalen".
    Sortert på initialer.
    """
    cfg = _load_config()
    users = cfg.get("users", {})
    out: list[dict] = []
    if not isinstance(users, dict):
        return out
    for entry in users.values():
        if not isinstance(entry, dict):
            continue
        initials = str(entry.get("visena_initials", "") or "").strip().upper()
        full_name = str(entry.get("full_name", "") or "").strip()
        if not initials and not full_name:
            continue
        label = f"{initials} – {full_name}" if initials and full_name else (initials or full_name)
        out.append({"initials": initials, "full_name": full_name, "label": label})
    out.sort(key=lambda x: x.get("initials") or x.get("full_name") or "")
    return out
