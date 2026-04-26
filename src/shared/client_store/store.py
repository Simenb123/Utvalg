# -*- coding: utf-8 -*-
"""client_store.py – filbasert klientlager + versjonering.

Rot: ``app_paths.data_dir()/clients``. Hver klient får egen mappe, videre
inndelt i år og dtype (hb, mapping, osv.). Audit logges i jsonl.

Versjonshåndtering (VersionModel, create_version, list_versions, …) er
splittet ut til ``client_store_versions.py``.  Alt re-eksporteres herfra
for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import getpass
import hashlib
import json
import os
import re
import shutil
import time

import app_paths

log = logging.getLogger(__name__)

CLIENTS_SUBDIR = "clients"
META_FILE = "meta.json"
AUDIT_FILE = "audit_log.jsonl"
INDEX_FILE = "versions_index.json"

# Hurtigindeks for klienter (lagres i datamappen, ikke i clients-roten)
# for å unngå at selve indeksfila påvirker mtime på clients-katalogen.
CLIENTS_INDEX_FILE = "clients_index.json"

CLIENTS_INDEX_STAMP_NAME = "clients_index.stamp"

def _clients_index_stamp_path() -> Path:
    return app_paths.data_dir() / CLIENTS_INDEX_STAMP_NAME

def _clients_index_stamp_mtime_ns() -> int:
    try:
        return _clients_index_stamp_path().stat().st_mtime_ns
    except Exception:
        return 0

def _touch_clients_index_stamp() -> int:
    try:
        p = _clients_index_stamp_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
        return p.stat().st_mtime_ns
    except Exception:
        return 0

CLIENTS_INDEX_SCHEMA = 1


# --- Klient-index/cache -----------------------------------------------------
#
# Noen operasjoner (f.eks. list_versions, set_active_version) kaller
# ensure_client(..., create=False). Tidligere scannet _find_client_dir hele
# klientroten (og leste meta.json for hver klient) for *hver* slik operasjon.
# På nettverksstier med mange klienter blir dette merkbart tregt.
#
# Vi bygger derfor en enkel in-memory index som oppdateres ved behov.

_CACHE_ROOT: Optional[Path] = None
_CACHE_ROOT_MTIME: Optional[float] = None
_CACHE_STAMP_NS: Optional[int] = None

# Key: normalized name (display_name OR folder name) -> (display_name, dir)
_CLIENT_CACHE: Dict[str, tuple[str, Path]] = {}

# Unike display names (sortert)
_CLIENT_LIST: List[str] = []


def _norm_key(s: str) -> str:
    return (s or "").strip().casefold()


def _clients_index_path() -> Path:
    """Path til klientindeks (lagres i datamappen)."""

    return app_paths.data_dir() / CLIENTS_INDEX_FILE


def _clients_root_mtime_ns(root: Path) -> int:
    try:
        return int(root.stat().st_mtime_ns)
    except Exception:
        return 0


def _write_clients_index_from_cache(root: Path) -> None:
    """Write a stable on-disk clients index.

    We store both the clients-root mtime (legacy) *and* a separate stamp mtime.
    The stamp is what we prefer for validation, since directory mtimes on some
    network shares can be noisy/unstable.
    """

    global _CLIENT_LIST, _CLIENT_CACHE, _CACHE_STAMP_NS

    if not _CLIENT_LIST or not _CLIENT_CACHE:
        return

    path = _clients_index_path()

    try:
        mtime_ns = _clients_root_mtime_ns(root)
        if mtime_ns <= 0:
            return

        stamp_ns = _touch_clients_index_stamp()
        if stamp_ns:
            _CACHE_STAMP_NS = stamp_ns

        clients = []
        for display in _CLIENT_LIST:
            k = _norm_key(display)
            if not k:
                continue
            disp2, cdir = _CLIENT_CACHE.get(k, (None, None))
            if not disp2 or cdir is None:
                continue
            clients.append({"display_name": disp2, "dir": str(cdir.name)})

        payload = {
            "schema": CLIENTS_INDEX_SCHEMA,
            "clients_root_mtime_ns": mtime_ns,
            "clients_stamp_mtime_ns": stamp_ns,
            "clients": clients,
        }
        _write_json_atomic(path, payload)
    except Exception as e:
        log.debug("Could not write clients index: %s", e)


def _try_load_clients_index(root: Path) -> bool:
    global _CACHE_ROOT, _CACHE_ROOT_MTIME, _CACHE_STAMP_NS, _CLIENT_CACHE, _CLIENT_LIST

    try:
        p = _clients_index_path()
        if not p.exists():
            return False
        obj = _read_json(p)
        if not isinstance(obj, dict):
            return False
        if int(obj.get("schema", -1) or -1) != CLIENTS_INDEX_SCHEMA:
            return False

        # Prefer stamp-based validation when available. This avoids needless rescans
        # on some network shares where directory mtimes can be noisy/unstable.
        try:
            stored_stamp_ns = int(obj.get("clients_stamp_mtime_ns", 0) or 0)
        except Exception:
            stored_stamp_ns = 0
        current_stamp_ns = _clients_index_stamp_mtime_ns()

        if stored_stamp_ns and current_stamp_ns:
            if stored_stamp_ns != current_stamp_ns:
                return False
        else:
            # Legacy fallback: validate by clients root mtime.
            try:
                stored_ns = int(obj.get("clients_root_mtime_ns", 0) or 0)
            except Exception:
                return False
            current_ns = _clients_root_mtime_ns(root)
            if not stored_ns or not current_ns or stored_ns != current_ns:
                return False

        raw = obj.get("clients", [])
        if not isinstance(raw, list) or not raw:
            return False

        cache: dict[str, tuple[str, Path]] = {}
        display_by_norm: dict[str, str] = {}

        for item in raw:
            if not isinstance(item, dict):
                continue
            display = str(item.get("display_name") or "").strip()
            dir_name = str(item.get("dir") or "").strip()
            if not display or not dir_name:
                continue
            d = root / dir_name

            k_disp = _norm_key(display)
            k_dir = _norm_key(dir_name)

            if k_disp:
                cache[k_disp] = (display, d)
                display_by_norm.setdefault(k_disp, display)
            if k_dir and k_dir not in cache:
                cache[k_dir] = (display, d)

        if not cache:
            return False

        _CACHE_ROOT = root
        try:
            _CACHE_ROOT_MTIME = float(root.stat().st_mtime)
        except Exception:
            _CACHE_ROOT_MTIME = -1.0

        _CACHE_STAMP_NS = current_stamp_ns or stored_stamp_ns or None

        _CLIENT_CACHE = cache
        _CLIENT_LIST = sorted(display_by_norm.values(), key=lambda s: s.lower())
        return True
    except Exception:
        return False


def _rebuild_client_cache(root: Path) -> None:
    global _CACHE_ROOT, _CACHE_ROOT_MTIME, _CLIENT_CACHE, _CLIENT_LIST

    _CACHE_ROOT = root
    try:
        _CACHE_ROOT_MTIME = float(root.stat().st_mtime)
    except Exception:
        _CACHE_ROOT_MTIME = -1.0

    cache: Dict[str, tuple[str, Path]] = {}
    display_by_norm: Dict[str, str] = {}

    try:
        dirs = list(root.iterdir())
    except Exception:
        dirs = []

    for d in dirs:
        if not d.is_dir():
            continue

        # Systemmapper (arkiv/trash, etc.) skal ikke vises som klienter
        if d.name.startswith("_"):
            continue

        display = d.name
        meta_p = d / META_FILE
        if meta_p.exists():
            try:
                meta = _read_json(meta_p)
            except Exception:
                meta = {}
            display = (meta.get("display_name") or "").strip() or d.name

        k_disp = _norm_key(display)
        if k_disp:
            # Normalisert display-name
            cache.setdefault(k_disp, (display, d))
            display_by_norm.setdefault(k_disp, display)

        # Også normalisert mappe-navn (client_id). Dette gjør lookup rask
        # selv om noen skulle gi oss client_id i stedet for display_name.
        k_dir = _norm_key(d.name)
        if k_dir:
            cache.setdefault(k_dir, (display, d))

    _CLIENT_CACHE = cache
    _CLIENT_LIST = sorted(display_by_norm.values(), key=lambda s: (s or "").casefold())

    # Lag en hurtigindeks for rask oppstart (best effort)
    _write_clients_index_from_cache(root)


def _ensure_client_cache(*, force: bool = False) -> None:
    """Sørg for at klientcache er bygget og oppdatert."""

    root = _root()
    global _CACHE_ROOT, _CACHE_ROOT_MTIME, _CACHE_STAMP_NS

    # På oppstart (eller ved bytte av datamappe) vil cachen være tom. Da prøver vi først
    # å laste en hurtigindeks (clients_index.json). Hvis den ikke passer, faller vi
    # tilbake til full scanning.
    if _CACHE_ROOT != root:
        if (not force) and _try_load_clients_index(root):
            return
        _rebuild_client_cache(root)
        return

    if force or not _CLIENT_CACHE:
        if (not force) and _try_load_clients_index(root):
            return
        _rebuild_client_cache(root)
        return

    current_stamp_ns = _clients_index_stamp_mtime_ns()
    # Dersom root-mappen har endret mtime, rebuild (fanger nye mapper).
    try:
        mtime = float(root.stat().st_mtime)
    except Exception:
        mtime = -1.0

    # Hvis stamp finnes og matcher, anser vi cachen som gyldig uavhengig av
    # eventuell mtime-støy på nettverksdisk.
    if current_stamp_ns and _CACHE_STAMP_NS and current_stamp_ns == _CACHE_STAMP_NS:
        return

    if (current_stamp_ns and _CACHE_STAMP_NS and current_stamp_ns != _CACHE_STAMP_NS) or (mtime != _CACHE_ROOT_MTIME):
        if _try_load_clients_index(root):
            return
        _rebuild_client_cache(root)



def _cache_add_client(display_name: str, client_dir: Path) -> None:
    """Oppdater cache med én klient (unngå full rescan).

    Dette er kritisk for ytelse ved import: når vi lager mange klientmapper endres
    mtime på clients-root for hver opprettelse. Uten inkrementell oppdatering vil
    `_ensure_client_cache()` trigge full rescan for hver klient (O(n^2)), som på
    nettverksdisk kan ta *mange* timer.
    """

    global _CLIENT_CACHE, _CLIENT_LIST, _CACHE_ROOT, _CACHE_ROOT_MTIME

    root = _root()
    if _CACHE_ROOT != root or _CLIENT_CACHE is None or _CLIENT_LIST is None:
        _rebuild_client_cache(root)

    assert _CLIENT_CACHE is not None
    assert _CLIENT_LIST is not None

    dn = (display_name or "").strip()
    if not dn:
        return

    k_disp = _norm_key(dn)
    if k_disp:
        _CLIENT_CACHE[k_disp] = (dn, client_dir)

    k_dir = _norm_key(client_dir.name)
    if k_dir:
        _CLIENT_CACHE[k_dir] = (dn, client_dir)

    if dn not in _CLIENT_LIST:
        _CLIENT_LIST.append(dn)
        _CLIENT_LIST.sort(key=lambda s: (s or "").casefold())

    # Oppdater mtime snapshot slik at vi ikke trigget rescan på neste kall.
    try:
        _CACHE_ROOT_MTIME = float(root.stat().st_mtime)
    except Exception:
        pass


def _cache_remove_client(display_name: str) -> None:
    """Fjern klient fra in-memory cache (best effort)."""

    global _CLIENT_CACHE, _CLIENT_LIST

    if _CLIENT_CACHE is None or _CLIENT_LIST is None:
        return

    dn = (display_name or "").strip()
    if not dn:
        return

    key = _norm_key(dn)
    hit = _CLIENT_CACHE.pop(key, None)
    if hit is None:
        return

    # Også fjern index på mappenavn.
    try:
        _CLIENT_CACHE.pop(_norm_key(hit[1].name), None)
    except Exception:
        pass

    try:
        _CLIENT_LIST.remove(hit[0])
    except Exception:
        pass

def _now() -> float:
    return float(time.time())

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

def _user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return ""

def _safe_slug(name: str) -> str:
    s = (name or "").strip().replace(" ", "_")
    s = re.sub(r'[<>:"/\\|?*]', "_", s)
    s = re.sub(r"[^0-9A-Za-z_\-\.æøåÆØÅ]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "client"

def normalize_year(year: Any) -> str:
    s = ("" if year is None else str(year)).strip()
    m = re.search(r"(\d{4})", s)
    return m.group(1) if m else (s or "unknown")

def _root() -> Path:
    p = app_paths.data_dir() / CLIENTS_SUBDIR
    app_paths.ensure_dir(p)
    return p


def get_clients_root() -> Path:
    """Public wrapper for rotmappen til klientlageret."""

    return _root()

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _write_json_atomic(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)

def _append_audit(client_dir: Path, event: Dict[str, Any]) -> None:
    try:
        client_dir.mkdir(parents=True, exist_ok=True)
        ev = dict(event or {})
        ev.setdefault("ts", _now())
        ev.setdefault("user", _user())
        ev.setdefault("pid", os.getpid())
        with open(client_dir / AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        # Audit må aldri knekke appen
        return

def audit_log_path(display_name: str) -> Path:
    return ensure_client(display_name) / AUDIT_FILE

def _sha256(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _copy_and_sha256_atomic(src: Path, dst: Path, *, chunk: int = 1024 * 1024) -> str:
    """Kopier fil til `dst` og beregn SHA256 i én og samme lesepassasje.

    Dette er viktig for ytelse (særlig på nettverksstier) – tidligere ble filen
    lest to ganger (hash + copy2).

    Skriver først til en midlertidig fil og "committer" så med os.replace for
    å unngå halvt skrevne filer ved avbrudd.
    """

    src = Path(src)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Unik tmp-fil i samme mappe (kreves for atomisk os.replace på Windows).
    tmp = dst.with_suffix(dst.suffix + ".uploading")
    i = 1
    while tmp.exists():
        tmp = dst.with_suffix(dst.suffix + f".uploading{i}")
        i += 1

    h = hashlib.sha256()
    try:
        with open(src, "rb") as fsrc, open(tmp, "wb") as fdst:
            while True:
                b = fsrc.read(chunk)
                if not b:
                    break
                h.update(b)
                fdst.write(b)
        # Best effort: kopier filmetadata (mtime osv.) uten å lese filen på nytt.
        try:
            shutil.copystat(src, tmp)
        except Exception:
            pass
    except Exception:
        # Rydd opp tmp ved feil
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        raise

    sha = h.hexdigest()
    os.replace(tmp, dst)
    return sha

def list_clients() -> List[str]:
    _ensure_client_cache()
    return list(_CLIENT_LIST)


def persist_clients_index() -> None:
    """Skriv hurtigindeks (clients_index.json) basert på cache.

    Dette er kun for ytelse (raskere oppstart på nettverksstasjoner).
    Funksjonen er *best effort* og skal ikke kaste i normal bruk.
    """

    try:
        if not _CLIENT_CACHE:
            _ensure_client_cache()
        _write_clients_index_from_cache(_root())
    except Exception:
        return



def refresh_client_cache() -> None:
    """Tving full refresh av klientcache.

    Brukes hvis klientmapper endres manuelt på disk, eller når datamappe byttes.
    """

    global _CLIENT_CACHE, _CLIENT_LIST, _CACHE_ROOT, _CACHE_ROOT_MTIME, _CACHE_STAMP_NS

    _CLIENT_CACHE = None
    _CLIENT_LIST = None
    _CACHE_ROOT = None
    _CACHE_ROOT_MTIME = None
    _CACHE_STAMP_NS = None

    # Fjern hurtigindeks + stamp for å tvinge rescan.
    try:
        _clients_index_path().unlink()
    except Exception:
        pass
    try:
        _clients_index_stamp_path().unlink()
    except Exception:
        pass

    _ensure_client_cache()


def _find_client_dir(display_name: str) -> Optional[Path]:
    dn = (display_name or "").strip()
    if not dn:
        return None
    root = _root()

    # Rask sjekk på forventet slug-map (verifiser meta for å håndtere kollisjoner)
    cand = root / _safe_slug(dn)
    try:
        if cand.exists() and cand.is_dir():
            meta = _read_json(cand / META_FILE)
            if (meta.get("display_name") or "").strip() == dn:
                _cache_add_client(dn, cand)
                return cand
    except Exception:
        pass

    # Cache lookup
    _ensure_client_cache()
    hit = _CLIENT_CACHE.get(_norm_key(dn))
    if hit is not None:
        return hit[1]

    # Cache miss: Som standard scanner vi *ikke* filsystemet her.
    #
    # Å iterere over alle klientmapper (og lese meta.json) ved hver lookup
    # gir O(n^2) under import og kan bli ekstremt tregt på nettverksdisker.
    #
    # Hvis du mistenker at klienter er opprettet manuelt utenfor appen,
    # kall refresh_client_cache() og forsøk igjen.
    return None

def ensure_client(display_name: str, *, persist_index: bool = True, create: bool = True) -> Path:
    dn = (display_name or "").strip()
    if not dn:
        raise ValueError("Tomt klientnavn")

    existing = _find_client_dir(dn)
    if existing is not None:
        return existing
    if not create:
        raise FileNotFoundError(f"Fant ikke klientmappen for {dn!r}")

    root = _root()
    slug = _safe_slug(dn)
    d = root / slug
    i = 2
    while d.exists():
        d = root / f"{slug}_{i}"
        i += 1

    d.mkdir(parents=True, exist_ok=True)
    _write_json_atomic(d / META_FILE, {"display_name": dn, "client_id": d.name, "created_at": _now()})
    _append_audit(d, {"action": "client_created", "client_display": dn, "client_id": d.name})
    _cache_add_client(dn, d)

    if persist_index:
        try:
            persist_clients_index()
        except Exception as e:
            log.debug("Could not persist clients index after ensure_client: %s", e)

    return d


def update_client_display_name(old_display_name: str, new_display_name: str) -> bool:
    """Oppdater display-navn for en eksisterende klient (ikke destruktivt).

    Dette flytter *ikke* mapper og sletter ikke data. Kun meta.json og cache
    oppdateres slik at klienten blir søkbar på nytt navn.
    """
    old_dn = (old_display_name or "").strip()
    new_dn = (new_display_name or "").strip()
    if not old_dn or not new_dn or old_dn == new_dn:
        return False

    d = _find_client_dir(old_dn)
    if d is None:
        return False

    meta_p = d / META_FILE
    meta: dict = {}
    try:
        if meta_p.exists():
            meta = _read_json(meta_p)
    except Exception:
        meta = {}

    meta["display_name"] = new_dn
    meta["updated_at"] = _now_iso()
    _write_json_atomic(meta_p, meta)

    # Audit (best effort)
    try:
        _append_audit(d, {"event": "update_display_name", "from": old_dn, "to": new_dn})
    except Exception:
        pass

    # Oppdater cache: fjern gammel key, legg til ny key
    try:
        _cache_remove_client(old_dn)
    except Exception:
        pass
    _cache_add_client(new_dn, d)

    # Oppdater hurtigindeks (ytelse; best effort)
    try:
        persist_clients_index()
    except Exception:
        pass

    return True


def read_client_meta(display_name: str) -> dict:
    """Les meta.json for en klient. Returnerer tom dict hvis ikke funnet."""
    d = _find_client_dir((display_name or "").strip())
    if d is None:
        return {}
    meta_p = d / META_FILE
    try:
        if meta_p.exists():
            return _read_json(meta_p)
    except Exception:
        pass
    return {}


def update_client_meta(display_name: str, updates: dict) -> bool:
    """Merger nye felt inn i meta.json uten å fjerne eksisterende.

    Returnerer True hvis oppdatering ble utført.
    """
    dn = (display_name or "").strip()
    if not dn or not updates:
        return False

    d = _find_client_dir(dn)
    if d is None:
        return False

    meta_p = d / META_FILE
    try:
        meta = _read_json(meta_p) if meta_p.exists() else {}
    except Exception:
        meta = {}

    meta.update(updates)
    meta["updated_at"] = _now_iso()
    _write_json_atomic(meta_p, meta)

    try:
        _append_audit(d, {"event": "update_client_meta", "fields": list(updates.keys())})
    except Exception:
        pass

    return True


def delete_client(display_name: str, *, hard: bool = False) -> Path:
    """Slett/arkiver en klient.

    Standard (hard=False): klientmappen flyttes til <clients_root>/_deleted_clients/
    slik at det kan angres manuelt. Returnerer ny plassering.

    hard=True: sletter mappen permanent (shutil.rmtree). Bruk med forsiktighet.
    """

    dn = str(display_name or "").strip()
    if not dn:
        raise ValueError("Tomt klientnavn")

    d = _find_client_dir(dn)
    if d is None or (not d.exists()):
        raise FileNotFoundError(f"Fant ikke klient: {dn}")

    # Audit før flytting (soft delete)
    if not hard:
        try:
            _append_audit(d, {"action": "client_deleted", "display_name": dn})
        except Exception:
            pass

    if hard:
        import shutil

        shutil.rmtree(d)
        deleted_to = d
    else:
        trash_root = _root() / "_deleted_clients"
        trash_root.mkdir(parents=True, exist_ok=True)

        ts = time.strftime("%Y%m%d_%H%M%S")
        target = trash_root / f"{d.name}__{ts}"
        i = 2
        while target.exists():
            target = trash_root / f"{d.name}__{ts}_{i}"
            i += 1

        try:
            d.rename(target)
        except Exception:
            import shutil

            shutil.move(str(d), str(target))
        deleted_to = target

    _cache_remove_client(dn)

    # Oppdater root-mtime i cache (slik at vi ikke trigger full rebuild unødvendig)
    global _CACHE_ROOT_MTIME
    try:
        _CACHE_ROOT_MTIME = float(_root().stat().st_mtime)
    except Exception:
        pass

    # Oppdater hurtigindeks
    try:
        persist_clients_index()
    except Exception:
        pass

    return deleted_to


def years_dir(display_name: str, *, year: str) -> Path:
    """Base-mappe for et gitt år under klienten (years/<YYYY>/)."""

    c = ensure_client(display_name)
    y = normalize_year(year)
    p = c / "years" / y
    p.mkdir(parents=True, exist_ok=True)
    return p

def exports_dir(display_name: str, *, year: str) -> Path:
    """Mappe for eksporterte dokumenter (years/<YYYY>/exports/).

    Opprettes automatisk ved første kall.
    """
    p = years_dir(display_name, year=year) / "exports"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Re-eksport fra client_store_versions (bakoverkompatibilitet)
#
# Bruker __getattr__ (PEP 562) for å unngå sirkulær import.
# «from client_store import VersionModel» fungerer som før.
# ---------------------------------------------------------------------------

_VERSIONS_NAMES = frozenset({
    "DuplicateContentError", "VersionModel", "create_version",
    "datasets_dir", "delete_version", "get_active_version",
    "get_active_version_id", "get_dataset_cache_meta",
    "get_version", "list_versions", "set_active_version",
    "set_dataset_cache_meta", "versions_dir",
})


def __getattr__(name: str):  # noqa: E302
    if name in _VERSIONS_NAMES:
        from . import versions as _csv
        val = getattr(_csv, name)
        # Cache i modulens namespace slik at neste oppslag er direkte.
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

