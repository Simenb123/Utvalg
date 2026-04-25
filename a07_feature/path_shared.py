from __future__ import annotations

import re
from pathlib import Path

try:
    import client_store
except Exception:
    client_store = None

try:
    import session as session_module
except Exception:
    session_module = None


_GROUP_DATA_COLUMNS = ("GroupId", "Navn", "Members", "A07_Belop", "GL_Belop", "Diff", "Locked")

MATCHER_SETTINGS_DEFAULTS: dict[str, float | int] = {
    "tolerance_rel": 0.02,
    "tolerance_abs": 100.0,
    "max_combo": 2,
    "candidates_per_code": 20,
    "top_suggestions_per_code": 5,
    "historical_account_boost": 0.12,
    "historical_combo_boost": 0.10,
}


def _clean_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _context_path_slug(value: object) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^0-9A-Za-z._-]+", "_", text)
    text = text.strip("._-")
    return text or "ukjent"


def _path_signature(path: str | Path | None) -> tuple[str | None, int | None, int | None]:
    if not path:
        return (None, None, None)

    file_path = Path(path)
    try:
        stat = file_path.stat()
        return (str(file_path), int(stat.st_mtime_ns), int(stat.st_size))
    except Exception:
        return (str(file_path), None, None)


def _safe_exists(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists()
    except Exception:
        return False
