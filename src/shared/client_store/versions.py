# -*- coding: utf-8 -*-
"""client_store_versions.py – versjonshåndtering for klientlageret.

Inneholder:
  - VersionModel / DuplicateContentError
  - list_versions, get_active_version, get_version, create_version, …
  - datasets_dir, get_dataset_cache_meta, set_dataset_cache_meta

Splittet ut fra client_store.py for oversiktlighet. client_store re-eksporterer
alt herfra for bakoverkompatibilitet.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Importerer client_store som modul (ikke «from … import») for å unngå
# sirkulær import — client_store re-eksporterer fra denne filen.
# ---------------------------------------------------------------------------

from . import store as _cs

# ---------------------------------------------------------------------------
# Cache for versjonsindekser per klient/år/type
# ---------------------------------------------------------------------------

# Key: (normalized display_name, normalized year, normalized dtype)
# Value: (mtime_ns, index_payload)
_VERSIONS_INDEX_CACHE: Dict[tuple[str, str, str], tuple[int, Dict[str, Any]]] = {}


# ---------------------------------------------------------------------------
# Datamodeller
# ---------------------------------------------------------------------------

@dataclass
class VersionModel:
    id: str
    client_display: str
    year: str
    dtype: str
    filename: str
    path: str
    created_at: float
    meta: Dict[str, Any] | None = None


class DuplicateContentError(Exception):
    def __init__(self, existing_id: str, existing_filename: str) -> None:
        super().__init__(f"Duplicate content (id={existing_id}, file={existing_filename})")
        self.existing_id = existing_id
        self.existing_filename = existing_filename


# ---------------------------------------------------------------------------
# Interne hjelpere
# ---------------------------------------------------------------------------

def _vdir(display_name: str, *, year: str, dtype: str, create: bool = True) -> Path:
    c = _cs.ensure_client(display_name, create=create)
    y = _cs.normalize_year(year)
    p = c / "years" / y / "versions" / dtype.lower()
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def versions_dir(display_name: str, *, year: str, dtype: str) -> Path:
    return _vdir(display_name, year=year, dtype=dtype)


def _index_path(display_name: str, *, year: str, dtype: str, create: bool = True) -> Path:
    return _vdir(display_name, year=year, dtype=dtype, create=create) / _cs.INDEX_FILE


def _versions_index_cache_key(display_name: str, *, year: str, dtype: str) -> tuple[str, str, str]:
    return (_cs._norm_key(display_name), _cs.normalize_year(year), (dtype or "").strip().casefold())


def _default_versions_index() -> Dict[str, Any]:
    return {"versions": [], "active_id": None}


def _load_index(display_name: str, *, year: str, dtype: str) -> Dict[str, Any]:
    try:
        p = _index_path(display_name, year=year, dtype=dtype, create=False)
    except FileNotFoundError:
        return _default_versions_index()
    if not p.exists():
        return _default_versions_index()
    cache_key = _versions_index_cache_key(display_name, year=year, dtype=dtype)
    try:
        mtime_ns = int(p.stat().st_mtime_ns)
    except Exception:
        mtime_ns = 0
    cached = _VERSIONS_INDEX_CACHE.get(cache_key)
    if cached and cached[0] == mtime_ns:
        return dict(cached[1])
    obj = _cs._read_json(p)
    if not isinstance(obj, dict):
        return _default_versions_index()
    obj.setdefault("versions", [])
    obj.setdefault("active_id", None)
    if mtime_ns:
        _VERSIONS_INDEX_CACHE[cache_key] = (mtime_ns, dict(obj))
    return obj


def _save_index(display_name: str, *, year: str, dtype: str, idx: Dict[str, Any]) -> None:
    path = _index_path(display_name, year=year, dtype=dtype)
    _cs._write_json_atomic(path, idx)
    cache_key = _versions_index_cache_key(display_name, year=year, dtype=dtype)
    try:
        mtime_ns = int(path.stat().st_mtime_ns)
    except Exception:
        _VERSIONS_INDEX_CACHE.pop(cache_key, None)
    else:
        _VERSIONS_INDEX_CACHE[cache_key] = (mtime_ns, dict(idx))


# ---------------------------------------------------------------------------
# Offentlige funksjoner
# ---------------------------------------------------------------------------

def list_versions(display_name: str, *, year: str, dtype: str) -> List[VersionModel]:
    idx = _load_index(display_name, year=year, dtype=dtype)
    out: List[VersionModel] = []
    for v in idx.get("versions", []) or []:
        try:
            out.append(VersionModel(**v))
        except Exception:
            continue
    out.sort(key=lambda x: x.created_at or 0.0)
    return out


def get_active_version(display_name: str, *, year: str, dtype: str) -> Optional[VersionModel]:
    idx = _load_index(display_name, year=year, dtype=dtype)
    aid = idx.get("active_id")
    if not aid:
        return None
    for v in idx.get("versions", []) or []:
        if (v or {}).get("id") == aid:
            try:
                return VersionModel(**v)
            except Exception:
                return None
    return None


def get_active_version_id(display_name: str, *, year: str, dtype: str) -> Optional[str]:
    """Return the active version id (or None).

    Backwards-compat helper used by some UI code.
    The canonical API is ``get_active_version()``.
    """
    v = get_active_version(display_name, year=year, dtype=dtype)
    return v.id if v else None


def get_version(display_name: str, *, year: str, dtype: str, version_id: str) -> Optional[VersionModel]:
    """Hent en spesifikk versjon ved id."""
    if not version_id:
        return None
    idx = _load_index(display_name, year=year, dtype=dtype)
    for v in idx.get("versions", []) or []:
        if (v or {}).get("id") == version_id:
            try:
                return VersionModel(**v)
            except Exception:
                return None
    return None


def datasets_dir(display_name: str, *, year: str, dtype: str) -> Path:
    """Mappe for ferdigbygde datasett (sqlite-cache) per klient/år/type."""
    y = _cs.normalize_year(year)
    return _cs.years_dir(display_name, year=y) / "datasets" / dtype


def get_dataset_cache_meta(
    display_name: str,
    *,
    year: str,
    dtype: str,
    version_id: str,
) -> Optional[Dict[str, Any]]:
    """Henter dataset-cache-meta fra versjons-meta (hvis den finnes)."""
    v = get_version(display_name, year=year, dtype=dtype, version_id=version_id)
    if v is None:
        return None
    dc = (v.meta or {}).get("dataset_cache")
    if isinstance(dc, dict):
        return dc
    return None


def set_dataset_cache_meta(
    display_name: str,
    *,
    year: str,
    dtype: str,
    version_id: str,
    dataset_cache: Dict[str, Any],
) -> None:
    """Oppdaterer versjons-meta med peker til ferdigbygd datasett-cache."""
    y = _cs.normalize_year(year)
    idx = _load_index(display_name, year=y, dtype=dtype)
    versions = idx.get("versions", []) or []

    updated = False
    for rec in versions:
        if (rec or {}).get("id") != version_id:
            continue
        meta = rec.get("meta")
        if not isinstance(meta, dict):
            meta = {}
        meta["dataset_cache"] = dict(dataset_cache)
        rec["meta"] = meta
        updated = True
        break

    if not updated:
        raise KeyError(f"Version not found: {display_name=} {y=} {dtype=} {version_id=}")

    idx["versions"] = versions
    _save_index(display_name, year=y, dtype=dtype, idx=idx)
    _cs._append_audit(
        _cs.ensure_client(display_name),
        {
            "action": "dataset_cache_set",
            "year": y,
            "dtype": dtype,
            "version_id": version_id,
            "dataset_cache": {
                k: dataset_cache.get(k)
                for k in ("signature", "file", "built_at", "rows", "cols", "schema_version")
                if k in dataset_cache
            },
        },
    )


def create_version(
    display_name: str,
    *,
    year: str,
    dtype: str,
    src_path: Path,
    make_active: bool = True,
    period_from: Optional[int] = None,
    period_to: Optional[int] = None,
    period_label: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> VersionModel:
    """Importer en fil til klientlageret som en ny versjon (kopierer filen)."""
    src_path = Path(src_path)
    if not src_path.exists() or not src_path.is_file():
        raise FileNotFoundError(str(src_path))

    cdir = _cs.ensure_client(display_name)
    y = _cs.normalize_year(year)
    idx = _load_index(display_name, year=y, dtype=dtype)

    ts = _cs._now()
    dt_s = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    base_id = f"{src_path.name} | {dt_s}"
    vid = base_id
    existing_ids = {v.get("id") for v in idx.get("versions", []) or []}
    if vid in existing_ids:
        n = 2
        while True:
            cand = f"{base_id} | #{n}"
            if cand not in existing_ids:
                vid = cand
                break
            n += 1

    dst_dir = _vdir(display_name, year=y, dtype=dtype)
    dst = dst_dir / src_path.name
    i = 1
    while dst.exists():
        dst = dst_dir / f"{src_path.stem}_{i}{src_path.suffix}"
        i += 1

    # Kopier + hash i én pass
    sha = _cs._copy_and_sha256_atomic(src_path, dst)

    # Duplikatsjekk etter at sha er kjent.
    for v in idx.get("versions", []) or []:
        if ((v or {}).get("meta") or {}).get("sha256") == sha:
            ex_id = str((v or {}).get("id") or "")
            ex_fn = str((v or {}).get("filename") or "")
            # Rydd opp kopien vi nettopp skrev
            try:
                if dst.exists():
                    dst.unlink()
            except Exception:
                pass
            _cs._append_audit(
                cdir,
                {
                    "action": "version_duplicate_rejected",
                    "client_display": (display_name or "").strip(),
                    "client_id": cdir.name,
                    "year": y,
                    "dtype": dtype,
                    "sha256": sha,
                    "source_path": str(src_path),
                    "existing_id": ex_id,
                    "existing_filename": ex_fn,
                },
            )
            raise DuplicateContentError(ex_id, ex_fn)

    rec_meta = dict(meta or {})
    rec_meta.update({"sha256": sha, "source_path": str(src_path)})
    if period_from is not None:
        try:
            rec_meta["period_from"] = int(period_from)
        except Exception:
            rec_meta["period_from"] = period_from
    if period_to is not None:
        try:
            rec_meta["period_to"] = int(period_to)
        except Exception:
            rec_meta["period_to"] = period_to
    if period_label is not None and str(period_label).strip():
        rec_meta["period_label"] = str(period_label).strip()

    rec = VersionModel(
        id=vid,
        client_display=(display_name or "").strip(),
        year=y,
        dtype=dtype,
        filename=dst.name,
        path=str(dst),
        created_at=ts,
        meta=rec_meta,
    )

    idx.setdefault("versions", []).append(asdict(rec))
    if make_active:
        idx["active_id"] = vid
    _save_index(display_name, year=y, dtype=dtype, idx=idx)
    _cs._append_audit(
        cdir,
        {
            "action": "version_created",
            "client_display": rec.client_display,
            "client_id": cdir.name,
            "year": rec.year,
            "dtype": rec.dtype,
            "version_id": rec.id,
            "filename": rec.filename,
            "path": rec.path,
            "active": bool(make_active),
            "meta": rec.meta or {},
        },
    )
    return rec


def set_active_version(display_name: str, *, year: str, dtype: str, version_id: str) -> bool:
    idx = _load_index(display_name, year=year, dtype=dtype)
    if not any((v or {}).get("id") == version_id for v in idx.get("versions", []) or []):
        return False
    prev = idx.get("active_id")
    idx["active_id"] = version_id
    _save_index(display_name, year=_cs.normalize_year(year), dtype=dtype, idx=idx)
    cdir = _cs.ensure_client(display_name)
    _cs._append_audit(
        cdir,
        {
            "action": "version_set_active",
            "client_display": (display_name or "").strip(),
            "client_id": cdir.name,
            "year": _cs.normalize_year(year),
            "dtype": dtype,
            "previous_active_id": prev,
            "active_id": version_id,
        },
    )
    return True


def delete_version(display_name: str, *, year: str, dtype: str, version_id: str) -> bool:
    idx = _load_index(display_name, year=year, dtype=dtype)
    versions = idx.get("versions", []) or []
    victim = next((v for v in versions if (v or {}).get("id") == version_id), None)
    keep = [v for v in versions if (v or {}).get("id") != version_id]
    if len(keep) == len(versions):
        return False

    file_deleted = False
    victim_path = ""
    if victim and victim.get("path"):
        try:
            p = Path(str(victim.get("path") or ""))
            victim_path = str(p)
            if p.exists():
                p.unlink()
                file_deleted = True
        except Exception:
            file_deleted = False

    prev_active = idx.get("active_id")
    idx["versions"] = keep
    if prev_active == version_id:
        idx["active_id"] = None
        if keep:
            keep_sorted = sorted(keep, key=lambda x: float((x or {}).get("created_at") or 0.0))
            idx["active_id"] = (keep_sorted[-1] or {}).get("id")

    _save_index(display_name, year=_cs.normalize_year(year), dtype=dtype, idx=idx)
    cdir = _cs.ensure_client(display_name)
    _cs._append_audit(
        cdir,
        {
            "action": "version_deleted",
            "client_display": (display_name or "").strip(),
            "client_id": cdir.name,
            "year": _cs.normalize_year(year),
            "dtype": dtype,
            "version_id": version_id,
            "previous_active_id": prev_active,
            "active_id": idx.get("active_id"),
            "file_deleted": file_deleted,
            "path": victim_path,
        },
    )
    return True
