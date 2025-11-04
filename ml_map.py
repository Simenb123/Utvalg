from __future__ import annotations
import json, hashlib
from pathlib import Path
from typing import Dict, List

_DB = Path(".ml_map.json")

def _fingerprint(headers: List[str]) -> str:
    norm = "|".join([str(h).strip().lower() for h in headers])
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()

def _load() -> Dict[str, Dict]:
    if _DB.exists():
        try: return json.loads(_DB.read_text(encoding="utf-8"))
        except Exception: return {}
    return {}

def _save(db: Dict[str, Dict]) -> None:
    try: _DB.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception: pass

def _jaccard(a: List[str], b: List[str]) -> float:
    A = {x.strip().lower() for x in a}
    B = {x.strip().lower() for x in b}
    if not A or not B: return 0.0
    return len(A & B) / float(len(A | B))

def _co_occurrence_hint(headers: List[str], mapping: Dict[str, str]) -> Dict[str, str]:
    hs = [h.strip().lower() for h in headers]
    out = dict(mapping)
    if any(("kontonr" in h or "kontonummer" in h) for h in hs):
        if "konto" in hs and "kontonavn" not in out.values():
            out.setdefault("kontonavn", headers[hs.index("konto")])
    for idx, h in enumerate(hs):
        if "forfall" in h and "due" not in out:
            out["due"] = headers[idx]
        if ("periodestart" in h or "start" in h and "periode" in h) and "periodestart" not in out:
            out["periodestart"] = headers[idx]
        if ("periodeslutt" in h or ("slutt" in h and "periode" in h)) and "periodeslutt" not in out:
            out["periodeslutt"] = headers[idx]
    return out

def suggest(headers: List[str]) -> Dict[str, str]:
    db = _load(); key = _fingerprint(headers)
    if key in db:
        return db[key]
    best_key, best_score = None, 0.0
    for k, v in db.items():
        score = _jaccard(headers, k.split("|"))
        if score > best_score:
            best_key, best_score = k, score
    if best_key and best_score >= 0.7:
        cand = db[best_key]
        return _co_occurrence_hint(headers, cand)
    return {}

def learn(headers: List[str], mapping: Dict[str, str]) -> None:
    if not headers: return
    db = _load(); key = _fingerprint(headers)
    clean = {k: v for k, v in mapping.items() if v}
    if not clean: return
    db[key] = clean; _save(db)
