from __future__ import annotations

import difflib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence


_CLIENT_PREFIX_RE = re.compile(r"^\s*\d{2,12}\s+")
_CLIENT_NONWORD_RE = re.compile(r"[^0-9a-zæøå]+", re.IGNORECASE)
_COMPANY_SUFFIXES = {
    "as",
    "asa",
    "ans",
    "da",
    "sa",
    "ba",
    "ks",
    "nuf",
    "enk",
    "enkeltpersonforetak",
}


def _default_user_data_root(app_name: str) -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / app_name
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / app_name
    return Path.home() / ".local" / "share" / app_name


def _configured_crm_db_path() -> Optional[Path]:
    path = os.environ.get("CRMSYSTEM_DB_PATH", "").strip()
    if path:
        return Path(os.path.expandvars(os.path.expanduser(path))).resolve()

    cfg_path = _default_user_data_root("CRMSystem") / "user_config.json"
    try:
        if cfg_path.exists():
            payload = json.loads(cfg_path.read_text(encoding="utf-8"))
            db_path = str((payload or {}).get("db_path") or "").strip()
            if db_path:
                return Path(os.path.expandvars(os.path.expanduser(db_path))).resolve()
    except Exception:
        pass

    data_dir = os.environ.get("CRMSYSTEM_DATA_DIR", "").strip()
    if data_dir:
        return Path(os.path.expandvars(os.path.expanduser(data_dir))).resolve() / "crm.sqlite"

    repo_default = Path(__file__).resolve().parent.parent / "CRMSystem" / "src" / "data" / "crm.sqlite"
    if repo_default.exists():
        return repo_default

    installed_default = _default_user_data_root("CRMSystem") / "data" / "crm.sqlite"
    if installed_default.exists():
        return installed_default

    return None


@dataclass(frozen=True)
class CRMSystemMaterialityRecord:
    client_number: str
    client_name: str
    engagement_year: int | None
    materiality: float | None
    pmateriality: float | None
    clearly_triv: float | None
    source_updated_at: str
    last_synced_at_utc: str
    last_changed_at_utc: str


@dataclass(frozen=True)
class CRMSystemLookupResult:
    db_path: Path | None
    matched_client_number: str
    record: CRMSystemMaterialityRecord | None
    error: str = ""


def _as_int(value: object) -> int | None:
    try:
        if value is None:
            return None
        return int(float(value))  # type: ignore[arg-type]
    except Exception:
        return None


def _as_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return None


def discover_crm_db_path() -> Optional[Path]:
    return _configured_crm_db_path()


def normalize_client_name(value: object) -> str:
    raw = _CLIENT_PREFIX_RE.sub("", str(value or "").strip())
    if not raw:
        return ""
    raw = raw.casefold().replace("&", " og ")
    raw = _CLIENT_NONWORD_RE.sub(" ", raw)
    tokens = [token for token in raw.split() if token]
    while tokens and tokens[-1] in _COMPANY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def suggest_client_numbers_from_name(display_name: str, *, limit: int = 5) -> list[str]:
    db_path = discover_crm_db_path()
    if db_path is None:
        return []
    try:
        db_exists = db_path.exists()
    except Exception:
        return []
    if not db_exists:
        return []

    normalized_target = normalize_client_name(display_name)
    if not normalized_target:
        return []

    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
    except Exception:
        return []

    try:
        table_exists = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='clients'"
        ).fetchone()
        if table_exists is None:
            return []

        exact_matches: list[str] = []
        loose_matches: list[str] = []
        fuzzy_matches: list[tuple[float, str]] = []
        seen: set[str] = set()
        rows = con.execute("SELECT client_number, client_name FROM clients").fetchall()
        for row in rows:
            client_number = str(row["client_number"] or "").strip()
            if not client_number or client_number in seen:
                continue
            normalized_name = normalize_client_name(row["client_name"])
            if not normalized_name:
                continue
            if normalized_name == normalized_target:
                exact_matches.append(client_number)
                seen.add(client_number)
                continue
            if normalized_target in normalized_name or normalized_name in normalized_target:
                loose_matches.append(client_number)
                seen.add(client_number)
                continue

            ratio = difflib.SequenceMatcher(None, normalized_target, normalized_name).ratio()
            if ratio >= 0.90:
                fuzzy_matches.append((ratio, client_number))

        if exact_matches:
            return exact_matches[:limit]
        if len(loose_matches) == 1:
            return loose_matches[:1]
        if not loose_matches and fuzzy_matches:
            fuzzy_matches.sort(reverse=True)
            best_ratio, best_number = fuzzy_matches[0]
            next_ratio = fuzzy_matches[1][0] if len(fuzzy_matches) > 1 else 0.0
            if best_ratio >= 0.93 and (best_ratio - next_ratio) >= 0.03:
                return [best_number]
        return []
    except Exception:
        return []
    finally:
        con.close()


def load_materiality_from_crm(client_numbers: Sequence[str]) -> CRMSystemLookupResult:
    db_path = discover_crm_db_path()
    if db_path is None:
        return CRMSystemLookupResult(
            db_path=None,
            matched_client_number="",
            record=None,
            error="Fant ikke CRMSystem-database. Sett CRMSYSTEM_DB_PATH eller konfigurer CRMSystem først.",
        )

    try:
        db_exists = db_path.exists()
    except Exception as exc:
        return CRMSystemLookupResult(
            db_path=db_path,
            matched_client_number="",
            record=None,
            error=f"Har ikke tilgang til CRMSystem-database: {exc}",
        )

    if not db_exists:
        return CRMSystemLookupResult(
            db_path=db_path,
            matched_client_number="",
            record=None,
            error=f"CRMSystem-database finnes ikke på disk: {db_path}",
        )

    try:
        con = sqlite3.connect(str(db_path))
        con.row_factory = sqlite3.Row
    except Exception as exc:
        return CRMSystemLookupResult(
            db_path=db_path,
            matched_client_number="",
            record=None,
            error=f"Kunne ikke åpne CRMSystem-database: {exc}",
        )

    try:
        table_exists = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='client_audit_info'"
        ).fetchone()
        if table_exists is None:
            return CRMSystemLookupResult(
                db_path=db_path,
                matched_client_number="",
                record=None,
                error="CRMSystem-databasen mangler tabellen client_audit_info.",
            )

        tried: list[str] = []
        for client_number in client_numbers:
            cn = str(client_number or "").strip()
            if not cn or cn in tried:
                continue
            tried.append(cn)
            row = con.execute(
                """
                SELECT ai.client_number,
                       COALESCE(c.client_name, '') AS client_name,
                       ai.engagement_year,
                       ai.materiality,
                       ai.pmateriality,
                       ai.clearly_triv,
                       ai.source_updated_at,
                       ai.last_synced_at_utc,
                       ai.last_changed_at_utc
                  FROM client_audit_info ai
             LEFT JOIN clients c
                    ON c.client_number = ai.client_number
                 WHERE ai.client_number = ?
                """,
                (cn,),
            ).fetchone()
            if row is None:
                continue

            record = CRMSystemMaterialityRecord(
                client_number=str(row["client_number"] or "").strip(),
                client_name=str(row["client_name"] or "").strip(),
                engagement_year=_as_int(row["engagement_year"]),
                materiality=_as_float(row["materiality"]),
                pmateriality=_as_float(row["pmateriality"]),
                clearly_triv=_as_float(row["clearly_triv"]),
                source_updated_at=str(row["source_updated_at"] or "").strip(),
                last_synced_at_utc=str(row["last_synced_at_utc"] or "").strip(),
                last_changed_at_utc=str(row["last_changed_at_utc"] or "").strip(),
            )
            return CRMSystemLookupResult(
                db_path=db_path,
                matched_client_number=cn,
                record=record,
                error="",
            )

        return CRMSystemLookupResult(
            db_path=db_path,
            matched_client_number="",
            record=None,
            error="Fant ingen vesentlighetsverdier for klienten i CRMSystem.",
        )
    except Exception as exc:
        return CRMSystemLookupResult(
            db_path=db_path,
            matched_client_number="",
            record=None,
            error=f"Feil ved lesing fra CRMSystem: {exc}",
        )
    finally:
        con.close()
