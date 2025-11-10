"""
preferences.py  — JSON-backed preferences with global & per-client scopes.
Compatible API:
  - get(key, default=None, client=None)
  - set(key, value, client=None)
  - get_int/get_float/get_bool
  - get_last_client()/set_last_client()
  - load()  -> dict   (compat shim; returns internal data)
  - save(data=None)   (compat shim; persists; if data provided, replaces internal)
Storage:
  - Uses '.session/preferences.json' if present/possible, else falls back to 'preferences.json' in project root.
"""
from __future__ import annotations
import os, json, threading
from typing import Any, Dict

_LOCK = threading.RLock()
_HERE = os.path.dirname(os.path.abspath(__file__))

_CANDIDATES = [
    os.path.join(_HERE, ".session", "preferences.json"),
    os.path.join(_HERE, "preferences.json"),
]
for _cand in _CANDIDATES:
    if os.path.exists(_cand):
        _PREFS_PATH = _cand
        break
else:
    _PREFS_PATH = _CANDIDATES[0]

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
            if os.path.exists(_PREFS_PATH):
                with open(_PREFS_PATH, "r", encoding="utf-8") as f:
                    obj = json.load(f)
                    if isinstance(obj, dict):
                        _DATA["global"] = obj.get("global", {}) or {}
                        _DATA["clients"] = obj.get("clients", {}) or {}
                        _DATA["last_client"] = obj.get("last_client")
        except Exception:
            pass

def _save() -> None:
    with _LOCK:
        try:
            _ensure_dir(_PREFS_PATH)
            tmp = _PREFS_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_DATA, f, ensure_ascii=False, indent=2)
            os.replace(tmp, _PREFS_PATH)
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
