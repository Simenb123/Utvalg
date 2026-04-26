# -*- coding: utf-8 -*-
"""dataset_pane_store.py

Kompatibilitets-wrapper.

Implementasjonen ble flyttet til ``dataset_pane_store_section.py`` for å holde
filene mindre og mer oversiktlige.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .pane_store_section import ClientStoreSection, DEFAULT_YEAR


try:
    import client_store

    _HAS_CLIENT_STORE = True
except Exception:
    client_store = None
    _HAS_CLIENT_STORE = False


def _path_exists(p: object) -> bool:
    try:
        if not p:
            return False
        return Path(str(p)).exists()
    except Exception:
        return False


def get_active_version_path(display_name: str, year: str, dtype: str = "hb") -> Optional[str]:
    """Returnerer path til aktiv versjon (string) eller None.

    Viktig: Når en versjon er slettet manuelt fra disk (eller når en delt
    nettverksressurs ikke er tilgjengelig) kan metadata peke på en fil som ikke
    lenger eksisterer. Da skal vi returnere None slik at GUI ikke blir stående
    og peke på en "spøkelsesfil".
    """

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        v = client_store.get_active_version(display_name, year=year, dtype=dtype)
        p = getattr(v, "path", None)
        if _path_exists(p):
            return str(p)
        return None
    except Exception:
        return None


def get_version_path(display_name: str, year: str, dtype: str, version_id: str) -> Optional[str]:
    """Returnerer path til en gitt versjon (string) eller None."""

    if not _HAS_CLIENT_STORE or client_store is None:
        return None
    try:
        v = client_store.get_version(display_name, year=year, dtype=dtype, version_id=version_id)
        p = getattr(v, "path", None)
        if _path_exists(p):
            return str(p)
        return None
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
