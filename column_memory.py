"""
column_memory.py
----------------
"Lær-av-bruk" for kolonnekart, lagret i column_memory.json.
- Flagg:
    * learning_enabled: om vi lagrer nye valg fra GUI
    * memory_enabled:   om minne skal påvirke gjett_kolonner
- Minnetyper:
    * schemas[fp] = { "mapping": {target: src}, "cols": [alle_kolonnenavn] }
      (fp = fingerprint av kolonne-sett)
    * global: normaliserte kildenavn -> { target: count, ... }
- API (brukes av GUI og io_utils):
    get_memory_weights(all_cols) -> vekter (target -> {col: weight})
    record_mapping(all_cols, mapping: Columns) -> lagre valg (hvis learning_enabled)
    is_learning_enabled() / set_learning_enabled(flag)
    is_memory_enabled() / set_memory_enabled(flag)
    list_schemas() / remove_schema(fp) / reset_all()
    list_globals_flat() / remove_global_key(norm_key) / remove_global_pair(norm_key, target)
    export_memory(path) / import_memory(path, merge=True)
"""

from __future__ import annotations
from dataclasses import asdict
from hashlib import sha1
from pathlib import Path
from typing import Dict, List, Tuple, DefaultDict, Iterable
from collections import defaultdict
import json
import re

from models import Columns

_BASE_DIR = Path(__file__).resolve().parent
_MEMORY_PATH = _BASE_DIR / "column_memory.json"

def _norm_header(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[\s_\-]+", "", s)
    s = s.replace(".", "").replace(",", "")
    return s

def fingerprint_columns(cols: List[str]) -> str:
    normed = sorted(_norm_header(c) for c in cols)
    raw = "|".join(normed).encode("utf-8")
    return sha1(raw).hexdigest()

def _load() -> dict:
    if not _MEMORY_PATH.exists():
        return {"version": 2, "flags": {"learning_enabled": True, "memory_enabled": True}, "global": {}, "schemas": {}}
    try:
        data = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
    except Exception:
        data = {"version": 2, "flags": {"learning_enabled": True, "memory_enabled": True}, "global": {}, "schemas": {}}
    # oppgrader strukturer (v1 -> v2)
    if "flags" not in data:
        data["flags"] = {"learning_enabled": True, "memory_enabled": True}
    if "version" not in data:
        data["version"] = 2
    # sikr at schemas har "mapping"/"cols"
    schemas = data.get("schemas", {})
    changed = False
    for fp, entry in list(schemas.items()):
        if isinstance(entry, dict) and "mapping" not in entry:
            # gammel form: bare {target: src, ...}
            schemas[fp] = {"mapping": entry, "cols": []}
            changed = True
    if changed:
        data["schemas"] = schemas
    return data

def _save(mem: dict) -> None:
    tmp = _MEMORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(_MEMORY_PATH)

# ---------------- Flags ----------------

def is_learning_enabled() -> bool:
    return bool(_load().get("flags", {}).get("learning_enabled", True))

def is_memory_enabled() -> bool:
    return bool(_load().get("flags", {}).get("memory_enabled", True))

def set_learning_enabled(flag: bool) -> None:
    mem = _load()
    mem.setdefault("flags", {})["learning_enabled"] = bool(flag)
    _save(mem)

def set_memory_enabled(flag: bool) -> None:
    mem = _load()
    mem.setdefault("flags", {})["memory_enabled"] = bool(flag)
    _save(mem)

# ------------- Main API for io_utils -------------

def record_mapping(all_cols: List[str], mapping: Columns) -> None:
    """Lagre manuelle valg (hvis learning_enabled)."""
    mem = _load()
    if not mem.get("flags", {}).get("learning_enabled", True):
        return  # læring avskrudd

    g = mem.setdefault("global", {})
    s = mem.setdefault("schemas", {})

    # 1) Schema
    fp = fingerprint_columns(all_cols)
    entry = s.setdefault(fp, {"mapping": {}, "cols": list(all_cols)})
    # oppdater "cols" med sist-seen (kan endres litt mellom filer)
    entry["cols"] = list(all_cols)
    for target, src in mapping.__dict__.items():
        if not src:
            continue
        if src in all_cols:
            entry["mapping"][target] = src

    # 2) Global: bump teller for src->target
    def _bump(src: str, targ: str):
        if not src:
            return
        n = _norm_header(src)
        g.setdefault(n, {})
        g[n][targ] = int(g[n].get(targ, 0)) + 1

    for targ in ["konto", "kontonavn", "bilag", "belop", "debit", "credit", "tekst", "dato", "part"]:
        src = getattr(mapping, targ, "")
        if src:
            _bump(src, targ)

    _save(mem)

def get_memory_weights(all_cols: List[str]) -> Dict[str, Dict[str, float]]:
    """Vekter basert på minne. Returnerer tomt hvis memory_enabled=False."""
    mem = _load()
    if not mem.get("flags", {}).get("memory_enabled", True):
        return {}

    weights: Dict[str, Dict[str, float]] = defaultdict(dict)

    # Schema (eksakt fingerprint)
    fp = fingerprint_columns(all_cols)
    s_entry = mem.get("schemas", {}).get(fp, {})
    if isinstance(s_entry, dict):
        mapping = s_entry.get("mapping", {}) if "mapping" in s_entry else s_entry
        for targ, src in mapping.items():
            if src in all_cols:
                weights.setdefault(targ, {})[src] = weights.get(targ, {}).get(src, 0.0) + 400.0

    # Global (akkumulerte valg)
    g = mem.get("global", {})
    for src in all_cols:
        n = _norm_header(src)
        if n not in g:
            continue
        for targ, cnt in g[n].items():
            w = 20.0 * float(cnt)
            weights.setdefault(targ, {})[src] = weights.get(targ, {}).get(src, 0.0) + w

    return weights

# ------------- Management (for GUI) -------------

def list_schemas() -> List[dict]:
    """Returner liste over schema-oppføringer med fp, cols, mapping."""
    mem = _load()
    out = []
    for fp, entry in mem.get("schemas", {}).items():
        if isinstance(entry, dict) and "mapping" in entry:
            out.append({"fp": fp, "cols": entry.get("cols", []), "mapping": entry.get("mapping", {})})
        else:  # legacy
            out.append({"fp": fp, "cols": [], "mapping": entry})
    return out

def remove_schema(fp: str) -> None:
    mem = _load()
    if fp in mem.get("schemas", {}):
        mem["schemas"].pop(fp, None)
        _save(mem)

def reset_all() -> None:
    mem = _load()
    mem["schemas"] = {}
    mem["global"] = {}
    _save(mem)

def list_globals_flat() -> List[tuple]:
    """Returner [(norm_key, target, count), ...]."""
    mem = _load()
    out = []
    for norm_key, d in mem.get("global", {}).items():
        for targ, cnt in d.items():
            out.append((norm_key, targ, int(cnt)))
    out.sort(key=lambda r: (-r[2], r[0], r[1]))
    return out

def remove_global_key(norm_key: str) -> None:
    mem = _load()
    mem.get("global", {}).pop(norm_key, None)
    _save(mem)

def remove_global_pair(norm_key: str, target: str) -> None:
    mem = _load()
    d = mem.get("global", {}).get(norm_key, {})
    if target in d:
        d.pop(target, None)
    if not d:
        mem.get("global", {}).pop(norm_key, None)
    _save(mem)

def export_memory(path: str) -> None:
    mem = _load()
    Path(path).write_text(json.dumps(mem, ensure_ascii=False, indent=2), encoding="utf-8")

def import_memory(path: str, merge: bool = True) -> None:
    """Importer/merg kolonneminne fra fil."""
    try:
        incoming = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return
    mem = _load()

    # flags – behold lokale hvis merge
    if not merge:
        mem["flags"] = incoming.get("flags", {"learning_enabled": True, "memory_enabled": True})

    # schemas
    s = mem.setdefault("schemas", {})
    for fp, entry in incoming.get("schemas", {}).items():
        if fp not in s or not merge:
            s[fp] = entry
        else:
            # merge mapping (lokalt vinner ved konflikt)
            loc_map = s[fp].get("mapping", {}) if "mapping" in s[fp] else s[fp]
            inc_map = entry.get("mapping", {}) if "mapping" in entry else entry
            loc_map.update({k: v for k, v in inc_map.items() if k not in loc_map})
            if "mapping" in s[fp]:
                s[fp]["mapping"] = loc_map
            else:
                s[fp] = {"mapping": loc_map, "cols": s[fp].get("cols", [])}

    # global
    g = mem.setdefault("global", {})
    for norm_key, targ_map in incoming.get("global", {}).items():
        dst = g.setdefault(norm_key, {})
        for targ, cnt in targ_map.items():
            dst[targ] = int(dst.get(targ, 0)) + int(cnt)

    _save(mem)
