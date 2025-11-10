from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json, hashlib, unicodedata, time

# Fil i prosjektrot
MAP_PATH = Path(".ml_map.json")

# Friendly felt vi lagrer mapping for
FRIENDLY = [
    "Konto","Kontonavn","Bilag","Beløp","Dato","Tekst",
    "Kundenavn","Kundenr","Leverandørnavn","Leverandørnr",
    "MVA-kode","MVA-beløp","MVA-prosent",
    "Valuta","Valutabeløp",
    "Forfallsdato","Periodestart","Periodeslutt"
]

def _norm_header(h: str) -> str:
    if not h: return ""
    s = unicodedata.normalize("NFKD", str(h)).strip().lower()
    s = s.replace("\u00A0"," ").replace("\u202F"," ").replace("\xa0"," ")
    s = " ".join(s.split())
    return s

def _signature(headers: List[str]) -> str:
    base = "|".join(_norm_header(h) for h in headers)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()

def _load_raw() -> Dict[str, Any]:
    if MAP_PATH.exists():
        try:
            with MAP_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_raw(data: Dict[str, Any]):
    tmp = MAP_PATH.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(MAP_PATH)

def _migrate_if_needed(data: Dict[str, Any]) -> Dict[str, Any]:
    # Hvis data allerede har entries, returner
    if isinstance(data, dict) and "entries" in data:
        data.setdefault("version", 1)
        return data
    # Enkel migrering fra "flat" struktur {friendly:src, ...}
    if isinstance(data, dict) and all(isinstance(k, str) for k in data.keys()):
        entry = {
            "signature": "legacy",
            "headers": [],
            "mapping": data,
            "score": 1.0,
            "seen": 1,
            "last_used": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        }
        return {"version":1, "entries":[entry]}
    return {"version":1, "entries":[]}

def _best_match(entries: List[Dict[str, Any]], headers: List[str]) -> Optional[Dict[str, Any]]:
    if not entries:
        return None
    sig = _signature(headers)
    # Eksakt signatur først
    for e in entries:
        if e.get("signature") == sig:
            return e
    # Nærmatch: Jaccard på sett med normaliserte navn
    cur = set(_norm_header(h) for h in headers if h)
    best = None
    best_score = 0.0
    for e in entries:
        eheaders = set(_norm_header(h) for h in e.get("headers", []) if h)
        if not eheaders:
            continue
        inter = len(cur & eheaders)
        union = len(cur | eheaders) or 1
        jacc = inter / union
        if jacc > best_score:
            best_score = jacc
            best = e
    if best_score >= 0.6:
        return best
    return None

def suggest(headers: List[str]) -> Dict[str, Optional[str]]:
    raw = _migrate_if_needed(_load_raw())
    entries = raw.get("entries", [])
    hit = _best_match(entries, headers)
    if not hit:
        return {}
    mapping = {k: hit.get("mapping", {}).get(k) for k in FRIENDLY}
    return mapping

def update(headers: List[str], mapping: Dict[str, Optional[str]]):
    raw = _migrate_if_needed(_load_raw())
    entries = raw.get("entries", [])
    sig = _signature(headers)
    # Finn eksisterende entry
    found = None
    for e in entries:
        if e.get("signature") == sig:
            found = e; break
    if found is None:
        found = {"signature": sig, "headers": headers, "mapping": {}, "score": 1.0, "seen": 0, "last_used": ""}
        entries.append(found)
    # Oppdater mapping kun for kjente felter (bevar None)
    for k in FRIENDLY:
        val = mapping.get(k)
        if val:
            found.setdefault("mapping", {})[k] = val
    found["seen"] = int(found.get("seen", 0)) + 1
    found["last_used"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    raw["entries"] = entries
    _save_raw(raw)