"""preferences.py

JSON-backed preferences with global & per-client scopes.

Hvor lagres filen?
-----------------
I utviklingsmodus (ikke PyInstaller/frozen):
  - Bruker historisk plassering i prosjektmappen (``.session/preferences.json``
    hvis mulig, ellers ``preferences.json`` / ``.preferences.json``).

I PyInstaller *onefile* (frozen):
  - Lagrer i en stabil per-bruker mappe (typisk AppData) for at innstillinger
    ikke skal havne i en midlertidig utpakkingsmappe.

Overstyring:
  - UTVALG_DATA_DIR: sett eksplisitt datamappe
  - UTVALG_PORTABLE=1: (frozen) lagre ved siden av .exe

Compatible API:
  - get(key, default=None, client=None)
  - set(key, value, client=None)
  - get_int/get_float/get_bool
  - get_last_client()/set_last_client()
  - load()  -> dict   (compat shim; returns internal data)
  - save(data=None)   (compat shim; persists; if data provided, replaces internal)
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict

import app_paths

_LOCK = threading.RLock()
_HERE = os.path.dirname(os.path.abspath(__file__))


def _legacy_candidates() -> list[str]:
    """Historiske plasseringer i repo/prosjektmappe."""

    return [
        os.path.join(_HERE, ".session", "preferences.json"),
        os.path.join(_HERE, "preferences.json"),
        os.path.join(_HERE, ".preferences.json"),
    ]


_PREFS_PATH: str | None = None


def _prefs_path() -> str:
    """Finn og cache sti for preferences.json."""
    global _PREFS_PATH
    if _PREFS_PATH:
        return _PREFS_PATH

    # I frozen-modus: skriv til per-bruker data mappe.
    if app_paths.is_frozen():
        # Legg i en .session undermappe for å beholde gammel struktur.
        _PREFS_PATH = str(app_paths.data_file("preferences.json", subdir=".session"))
        return _PREFS_PATH

    # Ikke frozen: behold gammel oppførsel
    for cand in _legacy_candidates():
        if os.path.exists(cand):
            _PREFS_PATH = cand
            return _PREFS_PATH

    # Default: .session/preferences.json
    _PREFS_PATH = _legacy_candidates()[0]
    return _PREFS_PATH


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

_DATA: Dict[str, Any] = {
    "global": {},
    "clients": {},
    "last_client": None,
}

def _deep_get(d: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    cur = d
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur

def _deep_set(d: Dict[str, Any], dotted: str, value: Any) -> None:
    cur = d
    parts = dotted.split(".")
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value

def _load() -> None:
    global _DATA
    with _LOCK:
        try:
            path = _prefs_path()

            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        _DATA["global"] = obj.get("global", {}) or {}
                        _DATA["clients"] = obj.get("clients", {}) or {}
                        _DATA["last_client"] = obj.get("last_client")
                return

            # Best effort migrering til AppData ved frozen:
            # Hvis vi ikke har filen i data-mappen enda, prøv å lese fra
            # legacy-lokasjoner (ved siden av exe / cwd).
            if app_paths.is_frozen():
                legacy = app_paths.best_effort_legacy_paths(
                    Path(app_paths.executable_dir()) / ".session" / "preferences.json",
                    Path(app_paths.executable_dir()) / "preferences.json",
                    Path.cwd() / ".session" / "preferences.json",
                    Path.cwd() / "preferences.json",
                    Path.cwd() / ".preferences.json",
                )
                for lp in legacy:
                    try:
                        with open(lp, "r", encoding="utf-8") as f:
                            obj = json.load(f)
                        if isinstance(obj, dict):
                            _DATA["global"] = obj.get("global", {}) or {}
                            _DATA["clients"] = obj.get("clients", {}) or {}
                            _DATA["last_client"] = obj.get("last_client")
                            # Lagre til ny sti
                            _save()
                            return
                    except Exception:
                        continue
        except Exception:
            pass

def _save() -> None:
    with _LOCK:
        try:
            path = _prefs_path()
            _ensure_dir(path)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_DATA, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except Exception:
            pass

_load()

def get(key: str, default: Any = None, client: str | None = None) -> Any:
    with _LOCK:
        if client:
            cdict = _DATA.get("clients", {}).get(client, {})
            return _deep_get(cdict, key, default)
        return _deep_get(_DATA.get("global", {}), key, default)

def set(key: str, value: Any, client: str | None = None) -> None:
    with _LOCK:
        if client:
            _deep_set(_DATA.setdefault("clients", {}).setdefault(client, {}), key, value)
        else:
            _deep_set(_DATA.setdefault("global", {}), key, value)
        _save()

def get_int(key: str, default: int = 0, client: str | None = None) -> int:
    val = get(key, default, client)
    try:
        return int(val)
    except Exception:
        return default

def get_float(key: str, default: float = 0.0, client: str | None = None) -> float:
    val = get(key, default, client)
    try:
        return float(val)
    except Exception:
        return default

def get_bool(key: str, default: bool = False, client: str | None = None) -> bool:
    val = get(key, default, client)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
    try:
        return bool(val)
    except Exception:
        return default

def set_last_client(client: str | None) -> None:
    with _LOCK:
        _DATA["last_client"] = client
        _save()

def get_last_client() -> str | None:
    with _LOCK:
        return _DATA.get("last_client")

def load() -> Dict[str, Any]:
    with _LOCK:
        return {
            "global": dict(_DATA.get("global", {})),
            "clients": {k: dict(v) for k, v in _DATA.get("clients", {}).items()},
            "last_client": _DATA.get("last_client"),
        }

def save(data: Dict[str, Any] | None = None) -> None:
    with _LOCK:
        if data is not None and isinstance(data, dict):
            _DATA.clear()
            _DATA.update({
                "global": data.get("global", {}) or {},
                "clients": data.get("clients", {}) or {},
                "last_client": data.get("last_client"),
            })
        _save()
