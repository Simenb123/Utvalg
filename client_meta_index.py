# -*- coding: utf-8 -*-
"""client_meta_index.py – lokal metadata-indeks for klienter.

Samler org_number, client_number, responsible, manager og team_members
i én lokal JSON-fil for instant oppslag uten nettverks-I/O.

Erstatter det separate team_index.json — denne har alle felt.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

_INDEX_FILE = "client_meta_index.json"
_cache: Optional[dict[str, dict]] = None


def _index_path() -> Path:
    import app_paths
    return app_paths.data_dir() / _INDEX_FILE


def load_index() -> dict[str, dict]:
    """Les lokal metadata-indeks (~50KB, <10ms)."""
    p = _index_path()
    try:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        log.debug("Kunne ikke lese %s", p, exc_info=True)
    return {}


def _write_index(index: dict[str, dict]) -> None:
    """Skriv indeks til disk."""
    p = _index_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        log.debug("Kunne ikke skrive %s", p, exc_info=True)


def rebuild_index(all_clients: list[str]) -> dict[str, dict]:
    """Bygg indeks fra meta.json for alle klienter.

    Tregt over nettverk (~5-10s for 615 klienter) — kjøres i bakgrunn.
    """
    import client_store

    index: dict[str, dict] = {}
    for dn in all_clients:
        meta = client_store.read_client_meta(dn)
        entry: dict = {}
        for key in ("org_number", "client_number", "visena_responsible",
                     "visena_manager", "visena_team_members"):
            val = meta.get(key, "")
            if val:
                # Bruk korte nøkler i indeksen
                short = key.replace("visena_", "")
                entry[short] = val
        index[dn] = entry

    _write_index(index)
    return index


def get_index() -> dict[str, dict]:
    """Smart loader med in-memory cache.

    Returnerer cached dict hvis tilgjengelig,
    leser fra fil hvis ikke, returnerer tom dict som fallback.
    """
    global _cache
    if _cache is not None:
        return _cache

    _cache = load_index()
    return _cache


def invalidate_cache() -> None:
    """Nullstill in-memory cache (f.eks. etter berikelse)."""
    global _cache
    _cache = None


def update_entry(display_name: str, updates: dict) -> None:
    """Oppdater én klient i indeksen (in-memory + disk)."""
    global _cache
    if _cache is None:
        _cache = load_index()

    entry = _cache.get(display_name, {})
    entry.update(updates)
    _cache[display_name] = entry

    _write_index(_cache)
