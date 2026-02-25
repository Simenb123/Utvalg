# -*- coding: utf-8 -*-
"""dataset_pane_store.py

Kompatibilitets-wrapper.

Implementasjonen ble flyttet til ``dataset_pane_store_section.py`` for å holde
filene mindre og mer oversiktlige.
"""

from __future__ import annotations

from typing import Optional

from dataset_pane_store_section import ClientStoreSection, DEFAULT_YEAR


try:
    import client_store

    _HAS_CLIENT_STORE = True
except Exception:
    client_store = None
    _HAS_CLIENT_STORE = False


from pathlib import Path


def get_active_version_path(display_name: str, year: str, dtype: str = "hb") -> Optional[str]:
    """Returnerer path til aktiv versjon (string) eller None.

    Viktig: returnerer None hvis filen ikke finnes på disk.
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        v = client_store.get_active_version(display_name, year=year, dtype=dtype)
        p = getattr(v, "path", None)
        if not p:
            return None
        pp = Path(str(p))
        return str(pp) if pp.exists() else None
    except Exception:
        return None


def get_version_path(display_name: str, year: str, dtype: str, version_id: str) -> Optional[str]:
    """Returnerer path til en gitt versjon (string) eller None.

    Viktig: returnerer None hvis filen ikke finnes på disk.
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        versions = client_store.list_versions(display_name, year=year, dtype=dtype)
        v = next((x for x in versions if getattr(x, "id", None) == version_id), None)
        if v is None:
            return None
        p = getattr(v, "path", None)
        if not p:
            return None
        pp = Path(str(p))
        return str(pp) if pp.exists() else None
    except Exception:
        return None


__all__ = [
    "ClientStoreSection",
    "DEFAULT_YEAR",
    "client_store",
    "_HAS_CLIENT_STORE",
    "get_active_version_path",
    "get_version_path",
]
