from __future__ import annotations

import csv
import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import app_paths
import client_store
import preferences


GLOBAL_DIR = "aksjonaerregister"
IMPORTS_DIR = "imports"
DB_FILE = "ar_index.sqlite"
MANUAL_FILE = "manual_owned_changes.json"
MANUAL_OWNER_FILE = "manual_owner_changes.json"
ACCEPTED_FILE = "accepted_owned_base.json"
SCHEMA_VERSION = 2
_YEAR_RE = re.compile(r"(20\d{2})")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_orgnr(value: object) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) == 9 else ""


def _relation_key(company_orgnr: str, company_name: str) -> str:
    orgnr = normalize_orgnr(company_orgnr)
    if orgnr:
        return f"org:{orgnr}"
    return f"name:{_normalize_text(company_name).casefold()}"


def classify_relation_type(ownership_pct: float) -> str:
    pct = float(ownership_pct or 0.0)
    if pct > 50.0:
        return "datter"
    if abs(pct - 50.0) < 1e-9:
        return "vurder"
    if pct >= 20.0:
        return "tilknyttet"
    return "investering"


def parse_year_from_filename(path: str | Path) -> str:
    match = _YEAR_RE.search(Path(path).stem)
    return match.group(1) if match else ""


def _global_dir() -> Path:
    target = app_paths.data_dir() / GLOBAL_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _db_path() -> Path:
    return _global_dir() / DB_FILE


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_imports (
            year TEXT PRIMARY KEY,
            source_file TEXT NOT NULL,
            imported_at_utc TEXT NOT NULL,
            rows_read INTEGER NOT NULL DEFAULT 0,
            relations_count INTEGER NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ownership_relations (
            year TEXT NOT NULL,
            company_orgnr TEXT NOT NULL,
            company_name TEXT NOT NULL,
            shareholder_orgnr TEXT NOT NULL DEFAULT '',
            shareholder_name TEXT NOT NULL,
            shareholder_kind TEXT NOT NULL DEFAULT 'unknown',
            shares INTEGER NOT NULL DEFAULT 0,
            total_shares INTEGER NOT NULL DEFAULT 0,
            ownership_pct REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (year, company_orgnr, shareholder_orgnr, shareholder_name)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_ownership_company ON ownership_relations (year, company_orgnr)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_ownership_shareholder_orgnr ON ownership_relations (year, shareholder_orgnr)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_company_imports (
            import_id TEXT PRIMARY KEY,
            client TEXT NOT NULL DEFAULT '',
            target_year TEXT NOT NULL,
            register_year TEXT NOT NULL DEFAULT '',
            company_orgnr TEXT NOT NULL,
            company_name TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            stored_file_path TEXT NOT NULL DEFAULT '',
            imported_at_utc TEXT NOT NULL,
            rows_read INTEGER NOT NULL DEFAULT 0,
            shareholders_count INTEGER NOT NULL DEFAULT 0,
            schema_version INTEGER NOT NULL DEFAULT 2
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_rci_client_year ON registry_company_imports (client, target_year)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_rci_company_year ON registry_company_imports (company_orgnr, target_year)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_import_shareholders (
            import_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            shareholder_id TEXT NOT NULL DEFAULT '',
            shareholder_name TEXT NOT NULL,
            shareholder_kind TEXT NOT NULL DEFAULT 'unknown',
            shareholder_orgnr TEXT NOT NULL DEFAULT '',
            shares_start INTEGER NOT NULL DEFAULT 0,
            shares_end INTEGER NOT NULL DEFAULT 0,
            total_shares_start INTEGER NOT NULL DEFAULT 0,
            total_shares_end INTEGER NOT NULL DEFAULT 0,
            ownership_pct_start REAL NOT NULL DEFAULT 0,
            ownership_pct_end REAL NOT NULL DEFAULT 0,
            page_number INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (import_id, seq)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_ris_import ON registry_import_shareholders (import_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS registry_import_transactions (
            import_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            shareholder_ref TEXT NOT NULL DEFAULT '',
            direction TEXT NOT NULL DEFAULT '',
            trans_type TEXT NOT NULL DEFAULT '',
            shares INTEGER NOT NULL DEFAULT 0,
            date TEXT NOT NULL DEFAULT '',
            amount REAL NOT NULL DEFAULT 0,
            page_number INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (import_id, seq)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_rit_import ON registry_import_transactions (import_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_rit_sh_ref ON registry_import_transactions (import_id, shareholder_ref)"
    )
    return conn


def _client_ar_dir(client: str, year: str) -> Path:
    target = client_store.years_dir(client, year=year) / GLOBAL_DIR
    target.mkdir(parents=True, exist_ok=True)
    return target


def _manual_changes_path(client: str, year: str) -> Path:
    return _client_ar_dir(client, year) / MANUAL_FILE


def _accepted_state_path(client: str, year: str) -> Path:
    return _client_ar_dir(client, year) / ACCEPTED_FILE


def _manual_owner_changes_path(client: str, year: str) -> Path:
    return _client_ar_dir(client, year) / MANUAL_OWNER_FILE


def _client_imports_dir(client: str, year: str, company_orgnr: str, import_id: str) -> Path:
    base = _client_ar_dir(client, year) / IMPORTS_DIR
    orgnr = normalize_orgnr(company_orgnr) or "unknown"
    target = base / orgnr / import_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def _store_registry_pdf_copy(
    client: str, year: str, company_orgnr: str, import_id: str, source_path: str | Path
) -> str:
    """Copy ``source_path`` into the managed imports folder and return stored path."""
    src = Path(source_path)
    if not src.exists():
        return ""
    target_dir = _client_imports_dir(client, year, company_orgnr, import_id)
    dest = target_dir / src.name
    try:
        if dest.resolve() == src.resolve():
            return str(dest)
    except Exception:
        pass
    try:
        shutil.copy2(src, dest)
    except Exception:
        return ""
    return str(dest)


def _shareholder_ref_key(sh_id: object, sh_name: object) -> str:
    """Stable key to join transactions back to a shareholder across years."""
    ident = str(sh_id or "").strip()
    if ident:
        return f"id:{ident}"
    name = _normalize_text(sh_name).casefold()
    return f"name:{name}" if name else ""


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _parse_int(value: object) -> int:
    text = _normalize_text(value).replace(" ", "")
    if not text:
        return 0
    try:
        return int(float(text))
    except Exception:
        return 0


def _shareholder_kind(shareholder_orgnr: str, raw_identifier: object) -> str:
    if shareholder_orgnr:
        return "company"
    digits = "".join(ch for ch in str(raw_identifier or "") if ch.isdigit())
    if len(digits) in {4, 11}:
        return "person"
    return "unknown"


@dataclass
class ManualOwnedChange:
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str = ""
    company_orgnr: str = ""
    ownership_pct: float = 0.0
    relation_type: str = ""
    note: str = ""
    updated_at_utc: str = field(default_factory=_utc_now_z)


def load_manual_owned_changes(client: str, year: str) -> list[ManualOwnedChange]:
    payload = _read_json(_manual_changes_path(client, year))
    if not isinstance(payload, list):
        return []
    out: list[ManualOwnedChange] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                ManualOwnedChange(
                    change_id=str(item.get("change_id") or str(uuid.uuid4())),
                    company_name=_normalize_text(item.get("company_name")),
                    company_orgnr=normalize_orgnr(item.get("company_orgnr")),
                    ownership_pct=float(item.get("ownership_pct") or 0.0),
                    relation_type=_normalize_text(item.get("relation_type")),
                    note=_normalize_text(item.get("note")),
                    updated_at_utc=_normalize_text(item.get("updated_at_utc")) or _utc_now_z(),
                )
            )
        except Exception:
            continue
    return out


def save_manual_owned_changes(client: str, year: str, changes: list[ManualOwnedChange]) -> Path:
    serialized = [asdict(change) for change in changes]
    path = _manual_changes_path(client, year)
    _write_json_atomic(path, serialized)
    return path


def upsert_manual_owned_change(client: str, year: str, change: ManualOwnedChange) -> list[ManualOwnedChange]:
    changes = load_manual_owned_changes(client, year)
    replaced = False
    for idx, existing in enumerate(changes):
        if existing.change_id == change.change_id:
            change.updated_at_utc = _utc_now_z()
            changes[idx] = change
            replaced = True
            break
    if not replaced:
        change.updated_at_utc = _utc_now_z()
        changes.append(change)
    save_manual_owned_changes(client, year, changes)
    return changes


def delete_manual_owned_change(client: str, year: str, change_id: str) -> list[ManualOwnedChange]:
    changes = [item for item in load_manual_owned_changes(client, year) if item.change_id != change_id]
    save_manual_owned_changes(client, year, changes)
    return changes


# ── Manuelle aksjonær-endringer (eier-siden) ───────────────────
# Speiler ManualOwnedChange-mønsteret, men for klientens aksjonærer.
# ``op`` er enten ``"upsert"`` (legg til / overstyr) eller ``"remove"``
# (fjern en eier fra RF-1086-grunnlaget). Endringene lagres separat fra
# RF-1086-data og overstyrer registerdata ved lesetid. Ved ny import som
# konflikterer med en manuell overstyring, genereres en pending change
# som må aksepteres eksplisitt i Registerendringer-fanen.

MANUAL_OWNER_OP_UPSERT = "upsert"
MANUAL_OWNER_OP_REMOVE = "remove"
_VALID_OWNER_OPS = (MANUAL_OWNER_OP_UPSERT, MANUAL_OWNER_OP_REMOVE)


@dataclass
class ManualOwnerChange:
    change_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    op: str = MANUAL_OWNER_OP_UPSERT
    shareholder_name: str = ""
    shareholder_orgnr: str = ""
    shareholder_kind: str = ""  # "company" | "person" | "unknown" | ""
    shares: int = 0
    total_shares: int = 0
    ownership_pct: float = 0.0
    note: str = ""
    updated_at_utc: str = field(default_factory=_utc_now_z)


def _coerce_owner_op(value: object) -> str:
    raw = _normalize_text(value).lower()
    return raw if raw in _VALID_OWNER_OPS else MANUAL_OWNER_OP_UPSERT


def load_manual_owner_changes(client: str, year: str) -> list[ManualOwnerChange]:
    payload = _read_json(_manual_owner_changes_path(client, year))
    if not isinstance(payload, list):
        return []
    out: list[ManualOwnerChange] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                ManualOwnerChange(
                    change_id=str(item.get("change_id") or str(uuid.uuid4())),
                    op=_coerce_owner_op(item.get("op")),
                    shareholder_name=_normalize_text(item.get("shareholder_name")),
                    shareholder_orgnr=normalize_orgnr(item.get("shareholder_orgnr")),
                    shareholder_kind=_normalize_text(item.get("shareholder_kind")),
                    shares=_parse_int(item.get("shares")),
                    total_shares=_parse_int(item.get("total_shares")),
                    ownership_pct=float(item.get("ownership_pct") or 0.0),
                    note=_normalize_text(item.get("note")),
                    updated_at_utc=_normalize_text(item.get("updated_at_utc")) or _utc_now_z(),
                )
            )
        except Exception:
            continue
    return out


def save_manual_owner_changes(client: str, year: str, changes: list[ManualOwnerChange]) -> Path:
    serialized = [asdict(change) for change in changes]
    path = _manual_owner_changes_path(client, year)
    _write_json_atomic(path, serialized)
    return path


def upsert_manual_owner_change(
    client: str, year: str, change: ManualOwnerChange
) -> list[ManualOwnerChange]:
    change.op = _coerce_owner_op(change.op)
    changes = load_manual_owner_changes(client, year)
    replaced = False
    for idx, existing in enumerate(changes):
        if existing.change_id == change.change_id:
            change.updated_at_utc = _utc_now_z()
            changes[idx] = change
            replaced = True
            break
    if not replaced:
        change.updated_at_utc = _utc_now_z()
        changes.append(change)
    save_manual_owner_changes(client, year, changes)
    return changes


def delete_manual_owner_change(
    client: str, year: str, change_id: str
) -> list[ManualOwnerChange]:
    changes = [
        item for item in load_manual_owner_changes(client, year)
        if item.change_id != change_id
    ]
    save_manual_owner_changes(client, year, changes)
    return changes


def _manual_owner_match_key(change: ManualOwnerChange) -> str:
    if change.shareholder_orgnr:
        return f"org:{change.shareholder_orgnr}"
    name = change.shareholder_name.casefold()
    return f"name:{name}" if name else f"id:{change.change_id}"


def _merge_owners(
    register_rows: list[dict[str, Any]],
    manual_changes: list[ManualOwnerChange],
) -> list[dict[str, Any]]:
    """Slå sammen RF-1086-eiere med manuelle overstyringer.

    Manuelle endringer overstyrer alltid RF-1086 ved samme shareholder-key
    (org.nr, ellers navn). ``op=remove`` filtrerer raden vekk.
    ``op=upsert`` oppdaterer eksisterende rad eller legger til ny.
    """
    by_key: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for row in register_rows:
        key = _shareholder_union_key(row)
        if not key:
            continue
        if key not in by_key:
            order.append(key)
        enriched = dict(row)
        enriched.setdefault("source", "register")
        enriched.setdefault("manual_change_id", "")
        by_key[key] = enriched

    removed_keys: set[str] = set()
    for change in manual_changes:
        key = _manual_owner_match_key(change)
        if change.op == MANUAL_OWNER_OP_REMOVE:
            removed_keys.add(key)
            by_key.pop(key, None)
            continue
        base = by_key.get(key, {})
        merged: dict[str, Any] = dict(base)
        merged.update({
            "shareholder_name": change.shareholder_name or _normalize_text(base.get("shareholder_name")),
            "shareholder_orgnr": change.shareholder_orgnr or normalize_orgnr(base.get("shareholder_orgnr")),
            "shareholder_kind": change.shareholder_kind or _normalize_text(base.get("shareholder_kind")) or "unknown",
            "shares": int(change.shares or 0),
            "total_shares": int(change.total_shares or base.get("total_shares") or 0),
            "ownership_pct": float(change.ownership_pct or 0.0),
            "source": "manual_override" if base else "manual",
            "manual_change_id": change.change_id,
            "manual_note": change.note,
        })
        if key not in by_key:
            order.append(key)
        by_key[key] = merged
    return [by_key[k] for k in order if k in by_key]


def _candidate_owner_signature(row: dict[str, Any]) -> tuple[int, int, float]:
    return (
        int(row.get("shares") or 0),
        int(row.get("total_shares") or 0),
        round(float(row.get("ownership_pct") or 0.0), 6),
    )


def build_pending_owner_changes(
    manual_changes: list[ManualOwnerChange],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Generer pending-rader for aksjonærer der RF-1086-importen avviker
    fra en aktiv manuell overstyring.

    ``manual_changes`` er alle lagrede manuelle eier-endringer.
    ``candidate_rows`` er de rå RF-1086-radene (uten manuell merge).

    Returnert rad har samme form som ``pending_changes`` for eide selskaper,
    slik at eksisterende accept-knapper kan brukes (change_type='owner_*').
    """
    by_key: dict[str, dict[str, Any]] = {}
    for row in candidate_rows:
        key = _shareholder_union_key(row)
        if key:
            by_key[key] = row

    pending: list[dict[str, Any]] = []
    for change in manual_changes:
        key = _manual_owner_match_key(change)
        candidate = by_key.get(key)
        if change.op == MANUAL_OWNER_OP_REMOVE:
            # Registerdata reintroduserer en aksjonær vi har fjernet manuelt.
            if candidate:
                pending.append({
                    "kind": "owner",
                    "change_type": "owner_restored",
                    "shareholder_name": change.shareholder_name
                        or _normalize_text(candidate.get("shareholder_name")),
                    "shareholder_orgnr": change.shareholder_orgnr
                        or normalize_orgnr(candidate.get("shareholder_orgnr")),
                    "manual_change_id": change.change_id,
                    "current_pct": 0.0,
                    "current_shares": 0,
                    "candidate_pct": float(candidate.get("ownership_pct") or 0.0),
                    "candidate_shares": int(candidate.get("shares") or 0),
                    "candidate_total_shares": int(candidate.get("total_shares") or 0),
                    "current_source": "manual_removal",
                    "candidate_source": "register_candidate",
                })
            continue
        # op == upsert
        manual_sig = (
            int(change.shares or 0),
            int(change.total_shares or 0),
            round(float(change.ownership_pct or 0.0), 6),
        )
        if candidate is None:
            # Manuell eier finnes ikke i registeret — ingen konflikt.
            continue
        cand_sig = _candidate_owner_signature(candidate)
        if manual_sig == cand_sig:
            continue
        pending.append({
            "kind": "owner",
            "change_type": "owner_overwrite",
            "shareholder_name": change.shareholder_name
                or _normalize_text(candidate.get("shareholder_name")),
            "shareholder_orgnr": change.shareholder_orgnr
                or normalize_orgnr(candidate.get("shareholder_orgnr")),
            "manual_change_id": change.change_id,
            "current_pct": float(change.ownership_pct or 0.0),
            "current_shares": int(change.shares or 0),
            "current_total_shares": int(change.total_shares or 0),
            "candidate_pct": float(candidate.get("ownership_pct") or 0.0),
            "candidate_shares": int(candidate.get("shares") or 0),
            "candidate_total_shares": int(candidate.get("total_shares") or 0),
            "current_source": "manual_override",
            "candidate_source": "register_candidate",
        })
    return pending


def accept_pending_owner_changes(
    client: str,
    year: str,
    keys: list[str] | None = None,
) -> list[ManualOwnerChange]:
    """Aksepter RF-1086-verdier over manuelle overstyringer ved å slette
    de aktuelle manuelle endringene. Etter dette vil merge bruke
    RF-1086-data direkte.

    ``keys`` er en liste av ``manual_change_id``-er. Hvis ``None`` aksepteres
    alle manuelle eier-endringer (full registeroverstyring).
    """
    existing = load_manual_owner_changes(client, year)
    if not existing:
        return []
    if keys is None:
        save_manual_owner_changes(client, year, [])
        return existing
    target = set(keys)
    kept = [c for c in existing if c.change_id not in target]
    removed = [c for c in existing if c.change_id in target]
    save_manual_owner_changes(client, year, kept)
    return removed


def _normalize_owned_row(row: dict[str, Any], *, default_source: str) -> dict[str, Any]:
    pct = float(row.get("ownership_pct") or 0.0)
    relation = _normalize_text(row.get("relation_type")) or classify_relation_type(pct)
    return {
        "company_name": _normalize_text(row.get("company_name")),
        "company_orgnr": normalize_orgnr(row.get("company_orgnr")),
        "ownership_pct": pct,
        "shares": int(row.get("shares") or 0),
        "total_shares": int(row.get("total_shares") or 0),
        "relation_type": relation,
        "source": _normalize_text(row.get("source")) or default_source,
        "note": _normalize_text(row.get("note")),
        "manual_change_id": _normalize_text(row.get("manual_change_id")),
    }


def _sort_owned_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (_normalize_owned_row(row, default_source="accepted_register") for row in rows),
        key=lambda item: (-float(item.get("ownership_pct") or 0.0), str(item.get("company_name") or "").casefold()),
    )


def load_accepted_owned_base(client: str, year: str) -> dict[str, Any]:
    payload = _read_json(_accepted_state_path(client, year))
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("rows")
    payload["rows"] = _sort_owned_rows(rows) if isinstance(rows, list) else []
    return payload


def save_accepted_owned_base(
    client: str,
    year: str,
    rows: list[dict[str, Any]],
    *,
    source_kind: str,
    source_year: str,
    register_year: str = "",
    note: str = "",
) -> dict[str, Any]:
    payload = {
        "client": _normalize_text(client),
        "year": str(year or "").strip(),
        "source_kind": _normalize_text(source_kind),
        "source_year": str(source_year or "").strip(),
        "register_year": str(register_year or "").strip(),
        "note": _normalize_text(note),
        "updated_at_utc": _utc_now_z(),
        "rows": _sort_owned_rows(rows),
    }
    _write_json_atomic(_accepted_state_path(client, year), payload)
    return payload


def load_registry_meta(year: str) -> dict[str, Any]:
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT year, source_file, imported_at_utc, rows_read, relations_count, schema_version
            FROM registry_imports
            WHERE year = ?
            """,
            (str(year),),
        ).fetchone()
        return dict(row) if row is not None else {}
    finally:
        conn.close()


def list_imported_years() -> list[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT year FROM registry_imports ORDER BY CAST(year AS INTEGER)",
        ).fetchall()
        return [str(row[0]) for row in rows if str(row[0] or "").strip()]
    finally:
        conn.close()


def import_registry_csv(path: str | Path, *, year: str) -> dict[str, Any]:
    target_year = str(year or "").strip() or parse_year_from_filename(path)
    if not target_year:
        raise ValueError("Fant ikke år for aksjonærregisteret.")

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Fant ikke filen: {file_path}")

    csv.field_size_limit(10_000_000)
    conn = _connect()
    rows_read = 0
    try:
        with conn:
            conn.execute("DELETE FROM ownership_relations WHERE year = ?", (target_year,))
            conn.execute("DELETE FROM registry_imports WHERE year = ?", (target_year,))
            with file_path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
                reader = csv.DictReader(handle, delimiter=";")
                for raw_row in reader:
                    if not isinstance(raw_row, dict):
                        continue
                    company_orgnr = normalize_orgnr(raw_row.get("Orgnr"))
                    company_name = _normalize_text(raw_row.get("Selskap"))
                    shareholder_name = _normalize_text(raw_row.get("Navn aksjonær"))
                    shareholder_orgnr = normalize_orgnr(raw_row.get("Fødselsår/orgnr"))
                    shares = _parse_int(raw_row.get("Antall aksjer"))
                    total_shares = _parse_int(raw_row.get("Antall aksjer selskap"))
                    if not company_orgnr or not company_name or not shareholder_name:
                        continue
                    rows_read += 1
                    conn.execute(
                        """
                        INSERT INTO ownership_relations (
                            year, company_orgnr, company_name, shareholder_orgnr,
                            shareholder_name, shareholder_kind, shares, total_shares, ownership_pct
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                        ON CONFLICT(year, company_orgnr, shareholder_orgnr, shareholder_name)
                        DO UPDATE SET
                            company_name = excluded.company_name,
                            shareholder_kind = excluded.shareholder_kind,
                            shares = ownership_relations.shares + excluded.shares,
                            total_shares = CASE
                                WHEN excluded.total_shares > ownership_relations.total_shares
                                    THEN excluded.total_shares
                                ELSE ownership_relations.total_shares
                            END
                        """,
                        (
                            target_year,
                            company_orgnr,
                            company_name,
                            shareholder_orgnr,
                            shareholder_name,
                            _shareholder_kind(shareholder_orgnr, raw_row.get("Fødselsår/orgnr")),
                            shares,
                            total_shares,
                        ),
                    )

            conn.execute(
                """
                UPDATE ownership_relations
                SET ownership_pct = CASE
                    WHEN total_shares > 0 THEN ROUND((shares * 100.0) / total_shares, 6)
                    ELSE 0
                END
                WHERE year = ?
                """,
                (target_year,),
            )
            relations_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM ownership_relations WHERE year = ?",
                    (target_year,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO registry_imports (
                    year, source_file, imported_at_utc, rows_read, relations_count, schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    target_year,
                    file_path.name,
                    _utc_now_z(),
                    rows_read,
                    relations_count,
                    SCHEMA_VERSION,
                ),
            )
    finally:
        conn.close()

    return load_registry_meta(target_year)


def import_registry_pdf(
    parse_result: object,
    *,
    year: str,
    source_file: str = "RF-1086.pdf",
    client: str = "",
    source_path: str | Path | None = None,
) -> dict[str, Any]:
    """Import shareholder data from a parsed RF-1086 PDF.

    ``parse_result`` is an ``ar_registry_pdf_parser.ParseResult`` instance.

    When ``client`` and ``source_path`` are provided, a managed copy of the
    source PDF is stored under the client's year folder and detailed import
    history is written to ``registry_company_imports``,
    ``registry_import_shareholders`` and ``registry_import_transactions``.
    Otherwise only the legacy year-level ``registry_imports`` row is written.
    """
    target_year = str(year or "").strip()
    if not target_year:
        raise ValueError("Mangler år for aksjonærregisteret.")

    header = parse_result.header  # type: ignore[attr-defined]
    shareholders = parse_result.shareholders  # type: ignore[attr-defined]
    company_orgnr = normalize_orgnr(header.company_orgnr)
    company_name = _normalize_text(header.company_name)
    total_shares_end = int(header.antall_aksjer_end or 0)
    total_shares_start = int(getattr(header, "antall_aksjer_start", 0) or 0)
    register_year = _normalize_text(getattr(header, "year", ""))
    client_name = _normalize_text(client)

    write_detailed = bool(client_name and company_orgnr)
    import_id = uuid.uuid4().hex if write_detailed else ""
    stored_path = ""
    if write_detailed and source_path:
        stored_path = _store_registry_pdf_copy(
            client_name, target_year, company_orgnr, import_id, source_path
        )

    conn = _connect()
    rows_read = 0
    try:
        with conn:
            # Only delete data for this specific company — not the entire year
            conn.execute(
                "DELETE FROM ownership_relations WHERE year = ? AND company_orgnr = ?",
                (target_year, company_orgnr),
            )

            detailed_shareholders: list[tuple[Any, ...]] = []
            detailed_transactions: list[tuple[Any, ...]] = []
            tx_seq = 0
            for sh_seq, sh in enumerate(shareholders, start=1):
                sh_id = str(sh.shareholder_id or "").strip()
                sh_name = _normalize_text(sh.shareholder_name)
                if not sh_name:
                    continue
                sh_kind = str(sh.shareholder_kind or "unknown")
                sh_orgnr = normalize_orgnr(sh_id) if sh_kind == "company" else ""
                shares_start = int(getattr(sh, "shares_start", 0) or 0)
                shares_end = int(sh.shares_end or 0)
                page_nr = int(getattr(sh, "page_number", 0) or 0)
                pct_start = round((shares_start * 100.0) / total_shares_start, 6) if total_shares_start > 0 else 0.0
                pct_end = round((shares_end * 100.0) / total_shares_end, 6) if total_shares_end > 0 else 0.0
                rows_read += 1
                conn.execute(
                    """
                    INSERT INTO ownership_relations (
                        year, company_orgnr, company_name, shareholder_orgnr,
                        shareholder_name, shareholder_kind, shares, total_shares, ownership_pct
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(year, company_orgnr, shareholder_orgnr, shareholder_name)
                    DO UPDATE SET
                        company_name = excluded.company_name,
                        shareholder_kind = excluded.shareholder_kind,
                        shares = ownership_relations.shares + excluded.shares,
                        total_shares = CASE
                            WHEN excluded.total_shares > ownership_relations.total_shares
                                THEN excluded.total_shares
                            ELSE ownership_relations.total_shares
                        END
                    """,
                    (
                        target_year,
                        company_orgnr,
                        company_name,
                        sh_orgnr,
                        sh_name,
                        sh_kind,
                        shares_end,
                        total_shares_end,
                    ),
                )
                if write_detailed:
                    detailed_shareholders.append(
                        (
                            import_id,
                            sh_seq,
                            sh_id,
                            sh_name,
                            sh_kind,
                            sh_orgnr,
                            shares_start,
                            shares_end,
                            total_shares_start,
                            total_shares_end,
                            pct_start,
                            pct_end,
                            page_nr,
                        )
                    )
                    sh_ref = _shareholder_ref_key(sh_id, sh_name)
                    for tx in getattr(sh, "transactions", []) or []:
                        tx_seq += 1
                        detailed_transactions.append(
                            (
                                import_id,
                                tx_seq,
                                sh_ref,
                                _normalize_text(getattr(tx, "direction", "")),
                                _normalize_text(getattr(tx, "trans_type", "")),
                                int(getattr(tx, "shares", 0) or 0),
                                _normalize_text(getattr(tx, "date", "")),
                                float(getattr(tx, "amount", 0.0) or 0.0),
                                page_nr,
                            )
                        )

            conn.execute(
                """
                UPDATE ownership_relations
                SET ownership_pct = CASE
                    WHEN total_shares > 0 THEN ROUND((shares * 100.0) / total_shares, 6)
                    ELSE 0
                END
                WHERE year = ?
                """,
                (target_year,),
            )
            relations_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM ownership_relations WHERE year = ?",
                    (target_year,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                INSERT INTO registry_imports (
                    year, source_file, imported_at_utc, rows_read, relations_count, schema_version
                )
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(year) DO UPDATE SET
                    source_file = excluded.source_file,
                    imported_at_utc = excluded.imported_at_utc,
                    rows_read = excluded.rows_read,
                    relations_count = excluded.relations_count,
                    schema_version = excluded.schema_version
                """,
                (
                    target_year,
                    source_file,
                    _utc_now_z(),
                    rows_read,
                    relations_count,
                    SCHEMA_VERSION,
                ),
            )

            if write_detailed:
                imported_at = _utc_now_z()
                conn.execute(
                    """
                    INSERT INTO registry_company_imports (
                        import_id, client, target_year, register_year, company_orgnr,
                        company_name, source_file, stored_file_path, imported_at_utc,
                        rows_read, shareholders_count, schema_version
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        import_id,
                        client_name,
                        target_year,
                        register_year,
                        company_orgnr,
                        company_name,
                        source_file,
                        stored_path,
                        imported_at,
                        rows_read,
                        len(detailed_shareholders),
                        SCHEMA_VERSION,
                    ),
                )
                if detailed_shareholders:
                    conn.executemany(
                        """
                        INSERT INTO registry_import_shareholders (
                            import_id, seq, shareholder_id, shareholder_name, shareholder_kind,
                            shareholder_orgnr, shares_start, shares_end, total_shares_start,
                            total_shares_end, ownership_pct_start, ownership_pct_end, page_number
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        detailed_shareholders,
                    )
                if detailed_transactions:
                    conn.executemany(
                        """
                        INSERT INTO registry_import_transactions (
                            import_id, seq, shareholder_ref, direction, trans_type,
                            shares, date, amount, page_number
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        detailed_transactions,
                    )
    finally:
        conn.close()

    meta = dict(load_registry_meta(target_year))
    meta["import_id"] = import_id
    meta["stored_file_path"] = stored_path
    meta["register_year"] = register_year
    meta["target_year"] = target_year
    meta["company_orgnr"] = company_orgnr
    meta["company_name"] = company_name
    meta["client"] = client_name
    return meta


def _query_relations(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    conn = _connect()
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def list_owned_companies(owner_orgnr: str, year: str) -> list[dict[str, Any]]:
    orgnr = normalize_orgnr(owner_orgnr)
    if not orgnr:
        return []
    return _query_relations(
        """
        SELECT year, company_orgnr, company_name, shareholder_orgnr, shareholder_name,
               shareholder_kind, shares, total_shares, ownership_pct
        FROM ownership_relations
        WHERE year = ? AND shareholder_orgnr = ?
        ORDER BY ownership_pct DESC, company_name COLLATE NOCASE
        """,
        (str(year), orgnr),
    )


def list_company_owners(company_orgnr: str, year: str) -> list[dict[str, Any]]:
    orgnr = normalize_orgnr(company_orgnr)
    if not orgnr:
        return []
    return _query_relations(
        """
        SELECT year, company_orgnr, company_name, shareholder_orgnr, shareholder_name,
               shareholder_kind, shares, total_shares, ownership_pct
        FROM ownership_relations
        WHERE year = ? AND company_orgnr = ?
        ORDER BY ownership_pct DESC, shareholder_name COLLATE NOCASE
        """,
        (str(year), orgnr),
    )


def list_company_owners_with_fallback(
    company_orgnr: str,
    target_year: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Return owners from the latest imported AR year up to ``target_year``.

    RF-1086 is company-specific in Utvalg. When the active client year is
    2025, a holding company further up the chain may still only have a 2024
    import. For indirect ownership we therefore need fallback per company,
    not one global lookup year for the whole chain.
    """
    orgnr = normalize_orgnr(company_orgnr)
    if not orgnr:
        return "", []

    target = _parse_year_value(target_year)
    candidates = [
        yr for yr in list_imported_years()
        if _parse_year_value(yr) and (target <= 0 or _parse_year_value(yr) <= target)
    ]
    for yr in sorted(candidates, key=_parse_year_value, reverse=True):
        owners = list_company_owners(orgnr, yr)
        if owners:
            return yr, owners
    return "", []


def get_client_orgnr(client: str) -> str:
    client_name = _normalize_text(client)
    orgnr = _get_client_orgnr_from_index(client_name)
    if orgnr:
        return orgnr
    orgnr = _get_client_orgnr_from_preferences(client_name)
    if orgnr:
        return orgnr
    try:
        meta = client_store.read_client_meta(client_name)
    except Exception:
        meta = {}
    return normalize_orgnr(meta.get("org_number"))


def _get_client_orgnr_from_index(client: str) -> str:
    client_name = _normalize_text(client)
    if not client_name:
        return ""
    try:
        from client_meta_index import get_index

        index = get_index() or {}
        meta = index.get(client_name)
        if isinstance(meta, dict):
            orgnr = normalize_orgnr(meta.get("org_number"))
            if orgnr:
                return orgnr
        folded = client_name.casefold()
        for display_name, meta in index.items():
            if str(display_name or "").strip().casefold() != folded:
                continue
            if not isinstance(meta, dict):
                continue
            orgnr = normalize_orgnr(meta.get("org_number"))
            if orgnr:
                return orgnr
    except Exception:
        return ""
    return ""


def _get_client_orgnr_from_preferences(client: str) -> str:
    client_name = _normalize_text(client)
    if not client_name:
        return ""
    safe = "".join(ch if ch.isalnum() else "_" for ch in client_name)
    raw = preferences.get(f"regnskap.noter.{safe}.__meta__.klientdata")
    if not isinstance(raw, str) or not raw.strip():
        return ""
    try:
        payload = json.loads(raw)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    return normalize_orgnr(payload.get("orgnr"))


def find_client_by_orgnr(orgnr: str) -> str:
    target = normalize_orgnr(orgnr)
    if not target:
        return ""
    try:
        from client_meta_index import get_index

        index = get_index() or {}
        for display_name, meta in index.items():
            if normalize_orgnr((meta or {}).get("org_number")) == target:
                return str(display_name)
        if index:
            return ""
    except Exception:
        pass

    try:
        for display_name in client_store.list_clients():
            if get_client_orgnr(display_name) == target:
                return str(display_name)
    except Exception:
        pass
    return ""


def _list_client_years(client: str) -> list[str]:
    try:
        client_dir = client_store.ensure_client(client, create=False)
    except Exception:
        return []
    years_root = client_dir / "years"
    if not years_root.exists():
        return []
    years = [item.name for item in years_root.iterdir() if item.is_dir() and str(item.name).isdigit()]
    return sorted(years, key=lambda item: int(item))


def _parse_year_value(value: object) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else 0


def _is_same_orgnr(lhs: object, rhs: object) -> bool:
    left = normalize_orgnr(lhs)
    right = normalize_orgnr(rhs)
    return bool(left and right and left == right)


def _split_self_relations(
    rows: list[dict[str, Any]],
    *,
    client_orgnr: str,
    orgnr_key: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not normalize_orgnr(client_orgnr):
        return [], [dict(row) for row in rows]

    self_rows: list[dict[str, Any]] = []
    other_rows: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if _is_same_orgnr(item.get(orgnr_key), client_orgnr):
            self_rows.append(item)
        else:
            other_rows.append(item)
    return self_rows, other_rows


def _summarize_self_ownership(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {}
    pct = sum(float(row.get("ownership_pct") or 0.0) for row in rows)
    shares = sum(int(row.get("shares") or 0) for row in rows)
    total_shares = 0
    source = ""
    for row in rows:
        total_shares = max(total_shares, int(row.get("total_shares") or 0))
        if not source:
            source = _normalize_text(row.get("source"))
    return {
        "ownership_pct": pct,
        "shares": shares,
        "total_shares": total_shares,
        "source": source,
        "count": len(rows),
    }


def _build_register_rows(client_orgnr: str, year: str, *, source: str) -> list[dict[str, Any]]:
    rows = list_owned_companies(client_orgnr, year)
    normalized: list[dict[str, Any]] = []
    for row in rows:
        normalized.append(
            _normalize_owned_row(
                {
                    "company_name": row.get("company_name"),
                    "company_orgnr": row.get("company_orgnr"),
                    "ownership_pct": row.get("ownership_pct"),
                    "shares": row.get("shares"),
                    "total_shares": row.get("total_shares"),
                    "relation_type": classify_relation_type(float(row.get("ownership_pct") or 0.0)),
                    "source": source,
                },
                default_source=source,
            )
        )
    return _sort_owned_rows(normalized)


def _find_latest_imported_year(target_year: str) -> str:
    target = _parse_year_value(target_year)
    years = [year for year in list_imported_years() if _parse_year_value(year) and _parse_year_value(year) <= target]
    return years[-1] if years else ""


def _find_previous_effective_rows(client: str, year: str, client_orgnr: str) -> tuple[str, list[dict[str, Any]]]:
    target = _parse_year_value(year)
    if target <= 0:
        return "", []

    candidate_years = {
        yr
        for yr in _list_client_years(client) + list_imported_years()
        if 0 < _parse_year_value(yr) < target
    }
    for prev_year in sorted(candidate_years, key=_parse_year_value, reverse=True):
        accepted = load_accepted_owned_base(client, prev_year)
        accepted_rows = accepted.get("rows") if isinstance(accepted.get("rows"), list) else []
        manual_changes = load_manual_owned_changes(client, prev_year)
        effective_rows = _merge_owned_relations(accepted_rows, manual_changes)
        if effective_rows:
            return prev_year, effective_rows
        if client_orgnr and load_registry_meta(prev_year):
            imported_rows = _build_register_rows(client_orgnr, prev_year, source="accepted_register")
            if imported_rows:
                return prev_year, imported_rows
    return "", []


def ensure_accepted_owned_base(client: str, year: str) -> dict[str, Any]:
    existing = load_accepted_owned_base(client, year)
    if existing:
        return existing

    client_name = _normalize_text(client)
    target_year = str(year or "").strip()
    client_orgnr = get_client_orgnr(client_name)

    prev_year, prev_rows = _find_previous_effective_rows(client_name, target_year, client_orgnr)
    if prev_rows:
        carried = []
        for row in prev_rows:
            item = dict(row)
            item["source"] = "carry_forward"
            item["manual_change_id"] = ""
            carried.append(item)
        return save_accepted_owned_base(
            client_name,
            target_year,
            carried,
            source_kind="carry_forward",
            source_year=prev_year,
            register_year=prev_year,
            note=f"Viderefort fra {prev_year}",
        )

    if client_orgnr and load_registry_meta(target_year):
        imported_rows = _build_register_rows(client_orgnr, target_year, source="accepted_register")
        if imported_rows:
            return save_accepted_owned_base(
                client_name,
                target_year,
                imported_rows,
                source_kind="register_baseline",
                source_year=target_year,
                register_year=target_year,
                note=f"Opprettet fra register {target_year}",
            )
    return {}


def _merge_owned_relations(
    imported_rows: list[dict[str, Any]],
    manual_changes: list[ManualOwnedChange],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for row in imported_rows:
        key = _relation_key(str(row.get("company_orgnr", "")), str(row.get("company_name", "")))
        merged[key] = _normalize_owned_row(dict(row), default_source="register")

    for change in manual_changes:
        key = _relation_key(change.company_orgnr, change.company_name)
        base = merged.get(
            key,
            {
                "company_name": change.company_name,
                "company_orgnr": normalize_orgnr(change.company_orgnr),
                "ownership_pct": 0.0,
                "shares": 0,
                "total_shares": 0,
                "relation_type": "",
                "source": "manual",
                "note": "",
                "manual_change_id": "",
            },
        )
        base["company_name"] = change.company_name or base.get("company_name", "")
        base["company_orgnr"] = normalize_orgnr(change.company_orgnr) or base.get("company_orgnr", "")
        base["ownership_pct"] = float(change.ownership_pct or 0.0)
        base["relation_type"] = change.relation_type or base.get("relation_type", "")
        base["note"] = change.note
        base["manual_change_id"] = change.change_id
        base["source"] = "manual_override" if key in merged else "manual"
        merged[key] = base

    return sorted(
        merged.values(),
        key=lambda item: (-float(item.get("ownership_pct") or 0.0), str(item.get("company_name") or "").casefold()),
    )


def _ownership_signature(row: dict[str, Any]) -> tuple[str, str, float, str]:
    return (
        _normalize_text(row.get("company_name")).casefold(),
        normalize_orgnr(row.get("company_orgnr")),
        round(float(row.get("ownership_pct") or 0.0), 6),
        _normalize_text(row.get("relation_type")).casefold(),
    )


def build_pending_ownership_changes(
    effective_rows: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_map = {
        _relation_key(row.get("company_orgnr"), row.get("company_name")): dict(row)
        for row in effective_rows
    }
    candidate_map = {
        _relation_key(row.get("company_orgnr"), row.get("company_name")): dict(row)
        for row in candidate_rows
    }

    changes: list[dict[str, Any]] = []
    for key in sorted(set(current_map) | set(candidate_map)):
        current = current_map.get(key)
        candidate = candidate_map.get(key)
        if current is None and candidate is not None:
            changes.append(
                {
                    "change_key": key,
                    "change_type": "added",
                    "company_name": candidate.get("company_name", ""),
                    "company_orgnr": candidate.get("company_orgnr", ""),
                    "current_pct": None,
                    "candidate_pct": float(candidate.get("ownership_pct") or 0.0),
                    "current_relation": "",
                    "candidate_relation": candidate.get("relation_type", ""),
                    "current_source": "",
                    "candidate_source": candidate.get("source", ""),
                }
            )
            continue
        if current is not None and candidate is None:
            changes.append(
                {
                    "change_key": key,
                    "change_type": "removed",
                    "company_name": current.get("company_name", ""),
                    "company_orgnr": current.get("company_orgnr", ""),
                    "current_pct": float(current.get("ownership_pct") or 0.0),
                    "candidate_pct": None,
                    "current_relation": current.get("relation_type", ""),
                    "candidate_relation": "",
                    "current_source": current.get("source", ""),
                    "candidate_source": "",
                }
            )
            continue
        assert current is not None and candidate is not None
        if _ownership_signature(current) != _ownership_signature(candidate):
            changes.append(
                {
                    "change_key": key,
                    "change_type": "changed",
                    "company_name": candidate.get("company_name") or current.get("company_name", ""),
                    "company_orgnr": candidate.get("company_orgnr") or current.get("company_orgnr", ""),
                    "current_pct": float(current.get("ownership_pct") or 0.0),
                    "candidate_pct": float(candidate.get("ownership_pct") or 0.0),
                    "current_relation": current.get("relation_type", ""),
                    "candidate_relation": candidate.get("relation_type", ""),
                    "current_source": current.get("source", ""),
                    "candidate_source": candidate.get("source", ""),
                }
            )

    order = {"changed": 0, "added": 1, "removed": 2}
    return sorted(
        changes,
        key=lambda item: (
            order.get(str(item.get("change_type")), 9),
            str(item.get("company_name") or "").casefold(),
        ),
    )


def accept_pending_ownership_changes(
    client: str,
    year: str,
    change_keys: list[str] | None = None,
) -> dict[str, Any]:
    client_name = _normalize_text(client)
    target_year = str(year or "").strip()
    ensure_accepted_owned_base(client_name, target_year)

    accepted = load_accepted_owned_base(client_name, target_year)
    base_rows = [dict(row) for row in (accepted.get("rows") or [])]
    manual_changes = load_manual_owned_changes(client_name, target_year)
    effective_rows = _merge_owned_relations(base_rows, manual_changes)
    client_orgnr = get_client_orgnr(client_name)
    candidate_rows = _build_register_rows(client_orgnr, target_year, source="accepted_register") if client_orgnr and load_registry_meta(target_year) else []
    pending = build_pending_ownership_changes(effective_rows, candidate_rows)
    accepted_keys = set(change_keys or [str(item.get("change_key")) for item in pending])
    if not accepted_keys:
        return get_client_ownership_overview(client_name, target_year)

    base_map = {
        _relation_key(row.get("company_orgnr"), row.get("company_name")): dict(row)
        for row in base_rows
    }
    candidate_map = {
        _relation_key(row.get("company_orgnr"), row.get("company_name")): dict(row)
        for row in candidate_rows
    }

    remaining_manual: list[ManualOwnedChange] = []
    for change in manual_changes:
        key = _relation_key(change.company_orgnr, change.company_name)
        if key not in accepted_keys:
            remaining_manual.append(change)

    for key in accepted_keys:
        if key in candidate_map:
            row = dict(candidate_map[key])
            row["source"] = "accepted_register"
            row["note"] = ""
            row["manual_change_id"] = ""
            base_map[key] = _normalize_owned_row(row, default_source="accepted_register")
        else:
            base_map.pop(key, None)

    save_manual_owned_changes(client_name, target_year, remaining_manual)
    save_accepted_owned_base(
        client_name,
        target_year,
        list(base_map.values()),
        source_kind="accepted_update",
        source_year=target_year,
        register_year=target_year,
        note="Oppdatert etter aksepterte registerendringer",
    )
    return get_client_ownership_overview(client_name, target_year)


def detect_circular_ownership(year: str) -> list[tuple[str, ...]]:
    """Detect circular ownership chains in the registry for a given year.

    Returns a list of cycles, each represented as a tuple of org.nrs forming the cycle.
    """
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT shareholder_orgnr, company_orgnr FROM ownership_relations WHERE year = ?",
            (str(year),),
        ).fetchall()
    finally:
        conn.close()

    # Build adjacency list: shareholder -> set of owned companies
    graph: dict[str, set[str]] = {}
    for row in rows:
        src = normalize_orgnr(row["shareholder_orgnr"])
        dst = normalize_orgnr(row["company_orgnr"])
        if src and dst and src != dst:
            graph.setdefault(src, set()).add(dst)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {node: WHITE for node in graph}
    # Also add nodes that appear only as destinations
    for neighbors in graph.values():
        for n in neighbors:
            if n not in color:
                color[n] = WHITE

    cycles: list[tuple[str, ...]] = []
    path: list[str] = []

    def dfs(node: str) -> None:
        color[node] = GRAY
        path.append(node)
        for neighbor in graph.get(node, ()):
            if color.get(neighbor, WHITE) == GRAY:
                # Found cycle: extract from the start of the cycle in path
                idx = path.index(neighbor)
                cycles.append(tuple(path[idx:]))
            elif color.get(neighbor, WHITE) == WHITE:
                dfs(neighbor)
        path.pop()
        color[node] = BLACK

    for node in list(color):
        if color[node] == WHITE:
            dfs(node)

    return cycles


def _find_owners_with_fallback(client_orgnr: str, target_year: str) -> tuple[str, list[dict[str, Any]]]:
    """Find owners of *client_orgnr* using the best available imported year.

    A PDF import (RF-1086) is company-specific, so the "latest imported year"
    might not contain data for the client.  Walk backwards through imported
    years until we find one that has ownership data for the client.
    """
    target = _parse_year_value(target_year)
    imported = [
        yr for yr in list_imported_years()
        if _parse_year_value(yr) and _parse_year_value(yr) <= target
    ]
    for yr in reversed(imported):
        owners = list_company_owners(client_orgnr, yr)
        if owners:
            return yr, owners
    return "", []


def _find_owners_prior_to(client_orgnr: str, target_year: str) -> tuple[str, list[dict[str, Any]]]:
    """Walk backwards strictly *before* ``target_year`` for a base comparison."""
    target = _parse_year_value(target_year)
    if target <= 0:
        return "", []
    imported = [
        yr for yr in list_imported_years()
        if 0 < _parse_year_value(yr) < target
    ]
    for yr in reversed(imported):
        owners = list_company_owners(client_orgnr, yr)
        if owners:
            return yr, owners
    return "", []


def _shareholder_union_key(row: dict[str, Any]) -> str:
    orgnr = normalize_orgnr(row.get("shareholder_orgnr"))
    if orgnr:
        return f"org:{orgnr}"
    name = _normalize_text(row.get("shareholder_name")).casefold()
    return f"name:{name}" if name else ""


def list_company_imports(
    *,
    client: str = "",
    target_year: str = "",
    company_orgnr: str = "",
    limit: int = 0,
) -> list[dict[str, Any]]:
    """Return rows from ``registry_company_imports`` filtered by given criteria."""
    clauses: list[str] = []
    params: list[Any] = []
    if client:
        clauses.append("client = ?")
        params.append(_normalize_text(client))
    if target_year:
        clauses.append("target_year = ?")
        params.append(str(target_year).strip())
    if company_orgnr:
        clauses.append("company_orgnr = ?")
        params.append(normalize_orgnr(company_orgnr))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = f" LIMIT {int(limit)}" if limit and limit > 0 else ""
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            SELECT * FROM registry_company_imports
            {where}
            ORDER BY imported_at_utc DESC{limit_sql}
            """,
            tuple(params),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _latest_import_for(client: str, target_year: str, company_orgnr: str) -> dict[str, Any]:
    rows = list_company_imports(
        client=client, target_year=target_year, company_orgnr=company_orgnr, limit=1
    )
    return rows[0] if rows else {}


def _latest_import_before(
    client: str, target_year: str, company_orgnr: str
) -> tuple[str, dict[str, Any]]:
    target = _parse_year_value(target_year)
    if target <= 0:
        return "", {}
    rows = list_company_imports(client=client, company_orgnr=company_orgnr)
    for row in rows:
        yr = _parse_year_value(row.get("target_year"))
        if 0 < yr < target:
            return str(row.get("target_year") or ""), dict(row)
    return "", {}


def _load_import_detail(import_id: str) -> dict[str, Any]:
    """Return full detail for an import_id: header + shareholders + transactions."""
    if not import_id:
        return {}
    conn = _connect()
    try:
        hdr = conn.execute(
            "SELECT * FROM registry_company_imports WHERE import_id = ?",
            (import_id,),
        ).fetchone()
        if hdr is None:
            return {}
        sh_rows = conn.execute(
            "SELECT * FROM registry_import_shareholders WHERE import_id = ? ORDER BY seq",
            (import_id,),
        ).fetchall()
        tx_rows = conn.execute(
            "SELECT * FROM registry_import_transactions WHERE import_id = ? ORDER BY seq",
            (import_id,),
        ).fetchall()
    finally:
        conn.close()

    shareholders = [dict(r) for r in sh_rows]
    transactions = [dict(r) for r in tx_rows]
    by_ref: dict[str, dict[str, Any]] = {}
    for sh in shareholders:
        ref = _shareholder_ref_key(sh.get("shareholder_id"), sh.get("shareholder_name"))
        if ref:
            by_ref.setdefault(ref, {"shareholder": sh, "transactions": []})
    for tx in transactions:
        ref = _normalize_text(tx.get("shareholder_ref"))
        if ref in by_ref:
            by_ref[ref]["transactions"].append(tx)
    return {
        "header": dict(hdr),
        "shareholders": shareholders,
        "transactions": transactions,
        "by_ref": by_ref,
    }


def _sh_ref_from_relation_row(row: dict[str, Any]) -> str:
    """Best-effort shareholder_ref lookup for an ownership_relations row."""
    orgnr = normalize_orgnr(row.get("shareholder_orgnr"))
    if orgnr:
        return f"id:{orgnr}"
    name = _normalize_text(row.get("shareholder_name")).casefold()
    return f"name:{name}" if name else ""


def _build_owners_compare(
    base_rows: list[dict[str, Any]],
    current_rows: list[dict[str, Any]],
    *,
    current_import_detail: dict[str, Any] | None,
    base_year: str,
    current_year: str,
    current_import_id: str,
    manual_changes: list[ManualOwnerChange] | None = None,
) -> list[dict[str, Any]]:
    base_map = {
        _shareholder_union_key(r): r
        for r in base_rows
        if _shareholder_union_key(r)
    }
    current_map = {
        _shareholder_union_key(r): r
        for r in current_rows
        if _shareholder_union_key(r)
    }

    detail = current_import_detail or {}
    by_ref = detail.get("by_ref") or {}
    key_to_ref: dict[str, str] = {}
    for sh in detail.get("shareholders") or []:
        orgnr = normalize_orgnr(sh.get("shareholder_orgnr"))
        name = _normalize_text(sh.get("shareholder_name")).casefold()
        ref = _shareholder_ref_key(sh.get("shareholder_id"), sh.get("shareholder_name"))
        if not ref:
            continue
        if orgnr:
            key_to_ref.setdefault(f"org:{orgnr}", ref)
        if name:
            key_to_ref.setdefault(f"name:{name}", ref)

    out: list[dict[str, Any]] = []
    for key in sorted(set(base_map) | set(current_map)):
        base = base_map.get(key) or {}
        current = current_map.get(key) or {}
        picked = current or base
        shares_base = int(base.get("shares") or 0)
        shares_current = int(current.get("shares") or 0)
        pct_base = float(base.get("ownership_pct") or 0.0)
        pct_current = float(current.get("ownership_pct") or 0.0)

        ref = key_to_ref.get(key, "")
        ref_detail = by_ref.get(ref) or {}
        tx_list = ref_detail.get("transactions") or []
        sh_meta = ref_detail.get("shareholder") or {}
        bought = sum(int(t.get("shares") or 0) for t in tx_list if _normalize_text(t.get("direction")) == "tilgang")
        sold = sum(int(t.get("shares") or 0) for t in tx_list if _normalize_text(t.get("direction")) == "avgang")
        tx_value = sum(float(t.get("amount") or 0.0) for t in tx_list)

        if not base and current:
            change_type = "new"
        elif base and not current:
            change_type = "removed"
        elif shares_base != shares_current or abs(pct_base - pct_current) > 1e-6:
            change_type = "changed"
        else:
            change_type = "unchanged"

        manual_change_id = _normalize_text(
            (current or base).get("manual_change_id")
        )
        row_source = _normalize_text((current or base).get("source")) or (
            "register" if (base or current) else ""
        )
        out.append({
            "shareholder_name": _normalize_text(picked.get("shareholder_name")),
            "shareholder_orgnr": normalize_orgnr(picked.get("shareholder_orgnr")),
            "shareholder_kind": _normalize_text(picked.get("shareholder_kind")) or "unknown",
            "shareholder_ref": ref,
            "shares_base": shares_base,
            "shares_current": shares_current,
            "shares_delta": shares_current - shares_base,
            "ownership_pct_base": pct_base,
            "ownership_pct_current": pct_current,
            "ownership_pct_delta": pct_current - pct_base,
            "shares_bought": bought,
            "shares_sold": sold,
            "transaction_value_total": tx_value,
            "change_type": change_type,
            "source_kind": "register" if (base or current) else "",
            "source": row_source,
            "manual_change_id": manual_change_id,
            "manual_note": _normalize_text((current or base).get("manual_note")),
            "current_import_id": current_import_id if current else "",
            "page_number": int(sh_meta.get("page_number") or 0),
            "base_year": base_year,
            "current_year": current_year,
        })

    # Surface manually-hidden (op=remove) owners so the user can undo them
    # from the compare view. A hidden row has zero shares and a flag.
    if manual_changes:
        seen_keys = {_shareholder_union_key(r) for r in out if _shareholder_union_key(r)}
        for change in manual_changes:
            if change.op != MANUAL_OWNER_OP_REMOVE:
                continue
            synth = {
                "shareholder_orgnr": change.shareholder_orgnr,
                "shareholder_name": change.shareholder_name,
            }
            synth_key = _shareholder_union_key(synth)
            if not synth_key or synth_key in seen_keys:
                continue
            seen_keys.add(synth_key)
            out.append({
                "shareholder_name": change.shareholder_name,
                "shareholder_orgnr": change.shareholder_orgnr,
                "shareholder_kind": change.shareholder_kind or "unknown",
                "shareholder_ref": "",
                "shares_base": 0,
                "shares_current": 0,
                "shares_delta": 0,
                "ownership_pct_base": 0.0,
                "ownership_pct_current": 0.0,
                "ownership_pct_delta": 0.0,
                "shares_bought": 0,
                "shares_sold": 0,
                "transaction_value_total": 0.0,
                "change_type": "hidden",
                "source_kind": "",
                "source": "manual_hidden",
                "manual_change_id": change.change_id,
                "manual_note": change.note,
                "current_import_id": "",
                "page_number": 0,
                "base_year": base_year,
                "current_year": current_year,
            })

    change_order = {"new": 0, "changed": 1, "removed": 2, "unchanged": 3, "hidden": 4}
    return sorted(
        out,
        key=lambda r: (
            change_order.get(r.get("change_type"), 9),
            -float(r.get("ownership_pct_current") or 0.0),
            str(r.get("shareholder_name") or "").casefold(),
        ),
    )


def get_shareholder_trace_detail(
    client: str,
    year: str,
    shareholder_key: str,
) -> dict[str, Any]:
    """Return per-shareholder trace (transactions, source import, previous state).

    ``shareholder_key`` is either ``"org:<orgnr>"`` or ``"name:<casefolded>"``
    matching :func:`_shareholder_union_key`.
    """
    client_name = _normalize_text(client)
    target_year = str(year or "").strip()
    client_orgnr = get_client_orgnr(client_name)
    key = _normalize_text(shareholder_key)
    if not client_orgnr or not target_year or not key:
        return {}

    current_import = _latest_import_for(client_name, target_year, client_orgnr)
    current_detail = _load_import_detail(current_import.get("import_id", "")) if current_import else {}

    by_ref = current_detail.get("by_ref") or {}
    key_to_ref: dict[str, str] = {}
    for sh in current_detail.get("shareholders") or []:
        orgnr = normalize_orgnr(sh.get("shareholder_orgnr"))
        name = _normalize_text(sh.get("shareholder_name")).casefold()
        ref = _shareholder_ref_key(sh.get("shareholder_id"), sh.get("shareholder_name"))
        if not ref:
            continue
        if orgnr:
            key_to_ref.setdefault(f"org:{orgnr}", ref)
        if name:
            key_to_ref.setdefault(f"name:{name}", ref)

    ref = key_to_ref.get(key, "")
    ref_detail = by_ref.get(ref) or {}

    # Previous year's snapshot for context (via ownership_relations)
    prev_year, prev_rows = _find_owners_prior_to(client_orgnr, target_year)
    prev_row: dict[str, Any] = {}
    for row in prev_rows:
        if _shareholder_union_key(row) == key:
            prev_row = dict(row)
            break

    return {
        "shareholder_key": key,
        "current_import": current_import,
        "shareholder": ref_detail.get("shareholder") or {},
        "transactions": ref_detail.get("transactions") or [],
        "previous_snapshot": prev_row,
        "previous_year": prev_year,
        "stored_file_path": _normalize_text(current_import.get("stored_file_path")) if current_import else "",
    }


def get_client_ownership_overview(client: str, year: str) -> dict[str, Any]:
    client_name = _normalize_text(client)
    target_year = str(year or "").strip()
    client_orgnr = get_client_orgnr(client_name)
    current_meta = load_registry_meta(target_year) if target_year else {}
    accepted = ensure_accepted_owned_base(client_name, target_year) if target_year else {}
    accepted_rows = accepted.get("rows") if isinstance(accepted.get("rows"), list) else []
    manual_changes = load_manual_owned_changes(client_name, target_year) if target_year else []
    effective_rows = _merge_owned_relations(accepted_rows, manual_changes)
    self_owned_rows, effective_rows = _split_self_relations(
        effective_rows,
        client_orgnr=client_orgnr,
        orgnr_key="company_orgnr",
    )

    owner_year, incoming = _find_owners_with_fallback(client_orgnr, target_year) if client_orgnr and target_year else ("", [])
    owners_meta = load_registry_meta(owner_year) if owner_year else {}
    self_owner_rows, incoming = _split_self_relations(
        incoming,
        client_orgnr=client_orgnr,
        orgnr_key="shareholder_orgnr",
    )

    manual_owner_changes = (
        load_manual_owner_changes(client_name, target_year) if target_year else []
    )
    # Når target_year mangler eget register, brukes fallback fra et tidligere år.
    # Men hvis brukeren har registrert manuelle eier-endringer for target_year,
    # representerer disse hele eierbildet for året — fallback-registeret skal
    # ikke lekke gjennom som "nå-tall" eller bli merget inn.
    fallback_active = bool(owner_year) and owner_year != target_year
    manual_replaces_fallback = fallback_active and bool(manual_owner_changes)
    if manual_replaces_fallback:
        register_owner_rows_raw: list[dict[str, Any]] = []
        owner_year = target_year
        owners_meta = {}
    else:
        register_owner_rows_raw = list(incoming)
    incoming = _merge_owners(register_owner_rows_raw, manual_owner_changes)
    pending_owner_changes = build_pending_owner_changes(
        manual_owner_changes,
        register_owner_rows_raw,
    )

    candidate_rows = (
        _build_register_rows(client_orgnr, target_year, source="register_candidate")
        if client_orgnr and target_year and current_meta
        else []
    )
    _, candidate_rows = _split_self_relations(
        candidate_rows,
        client_orgnr=client_orgnr,
        orgnr_key="company_orgnr",
    )
    pending_changes = build_pending_ownership_changes(effective_rows, candidate_rows) if candidate_rows else []
    # Eier-side pending changes slås inn i samme liste. Accept/reject i
    # Registerendringer-fanen ruter etter 'kind' ('owner' vs. eide-standard).
    if pending_owner_changes:
        pending_changes = list(pending_changes) + list(pending_owner_changes)
    self_ownership = _summarize_self_ownership(self_owned_rows)
    if not self_ownership:
        self_ownership = _summarize_self_ownership(
            [
                {
                    "ownership_pct": row.get("ownership_pct"),
                    "shares": row.get("shares"),
                    "total_shares": row.get("total_shares"),
                    "source": "owners_register",
                }
                for row in self_owner_rows
            ]
        )

    for row in effective_rows:
        row["relation_type"] = _normalize_text(row.get("relation_type")) or classify_relation_type(float(row.get("ownership_pct") or 0.0))
        match = find_client_by_orgnr(row.get("company_orgnr"))
        row["matched_client"] = match
        if match:
            try:
                row["has_active_sb"] = client_store.get_active_version(match, year=target_year, dtype="sb") is not None
            except Exception:
                row["has_active_sb"] = False
        else:
            row["has_active_sb"] = False

    for row in incoming:
        row["matched_client"] = find_client_by_orgnr(row.get("shareholder_orgnr"))

    # ── Sporbar import: detailed history for this client/year/company ──
    import_trace_current: dict[str, Any] = {}
    import_history: list[dict[str, Any]] = []
    current_import_detail: dict[str, Any] = {}
    base_year_used = ""
    base_owner_rows: list[dict[str, Any]] = []

    if client_orgnr and target_year:
        import_trace_current = _latest_import_for(client_name, target_year, client_orgnr)
        if import_trace_current:
            current_import_detail = _load_import_detail(
                import_trace_current.get("import_id", "")
            )
        import_history = list_company_imports(
            client=client_name, company_orgnr=client_orgnr
        )

    current_owner_year_used = owner_year
    current_owner_rows = incoming

    if client_orgnr:
        # Base skal være strengt eldre enn året som faktisk brukes som
        # "current" (ikke klientens valgte år). Hvis klient er på 2025 og
        # fallback finner 2024, skal base være 2023 eller eldre — ellers
        # sammenligner vi 2024 mot seg selv.
        prior_anchor = current_owner_year_used or target_year
        base_year_used, base_owner_rows = _find_owners_prior_to(client_orgnr, prior_anchor)
        _, base_owner_rows = _split_self_relations(
            base_owner_rows, client_orgnr=client_orgnr, orgnr_key="shareholder_orgnr",
        )

    owners_compare = _build_owners_compare(
        base_owner_rows,
        current_owner_rows,
        current_import_detail=current_import_detail,
        base_year=base_year_used,
        current_year=current_owner_year_used,
        current_import_id=_normalize_text(import_trace_current.get("import_id")) if import_trace_current else "",
        manual_changes=manual_owner_changes,
    )

    owners_compare_trace_available = bool(import_trace_current)
    owners_compare_changed = [
        row for row in owners_compare
        if _normalize_text(row.get("change_type")) not in ("", "unchanged")
    ]

    return {
        "client": client_name,
        "year": target_year,
        "client_orgnr": client_orgnr,
        "registry_meta": current_meta,
        "accepted_meta": accepted,
        "owners_meta": owners_meta,
        "owners_year_used": owner_year,
        "owners_current_year_used": current_owner_year_used,
        "owners_base_year_used": base_year_used,
        "owned_companies": effective_rows,
        "owners": incoming,
        "owners_compare": owners_compare,
        "owners_compare_trace_available": owners_compare_trace_available,
        "owners_compare_changed": owners_compare_changed,
        "self_ownership": self_ownership,
        "manual_changes": manual_changes,
        "manual_owner_changes": manual_owner_changes,
        "pending_changes": pending_changes,
        "pending_owner_changes": pending_owner_changes,
        "current_register_rows": candidate_rows,
        "import_trace_current": import_trace_current,
        "import_history": import_history,
    }
