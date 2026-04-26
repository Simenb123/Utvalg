"""Scoping store — lagring av manuelle scoping-overstyringer per klient/år.

Lagrer scoping-beslutninger (inn/ut), begrunnelser og manuelle
klassifiserings-overstyringer i en JSON-fil per klient og år.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import client_store


def _scoping_dir(client: str, year: str) -> Path:
    base = client_store.years_dir(client, year=year)
    target = base / "scoping"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _overrides_path(client: str, year: str) -> Path:
    return _scoping_dir(client, year) / "overrides.json"


def load_overrides(client: str, year: str) -> dict[str, dict[str, Any]]:
    """Last manuelle overstyringer.

    Returnerer dict: regnr → {scoping, rationale, classification}.
    """
    path = _overrides_path(client, year)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_overrides(client: str, year: str, overrides: dict[str, dict[str, Any]]) -> None:
    """Lagre manuelle overstyringer."""
    path = _overrides_path(client, year)
    path.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")


def update_line(
    client: str,
    year: str,
    regnr: str,
    *,
    scoping: str | None = None,
    rationale: str | None = None,
    classification: str | None = None,
    audit_action: str | None = None,
) -> None:
    """Oppdater overstyring for én regnskapslinje."""
    overrides = load_overrides(client, year)
    entry = overrides.get(regnr, {})
    if scoping is not None:
        entry["scoping"] = scoping
    if rationale is not None:
        entry["rationale"] = rationale
    if classification is not None:
        entry["classification"] = classification
    if audit_action is not None:
        entry["audit_action"] = audit_action
    overrides[regnr] = entry
    save_overrides(client, year, overrides)
