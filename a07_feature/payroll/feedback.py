from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import app_paths
from account_profile_legacy_api import safe_client_slug


def _feedback_path(client: str, year: int | None) -> Path:
    year_label = str(int(year)) if year is not None else "shared"
    return app_paths.data_file(
        "payroll_feedback.jsonl",
        subdir=f"feedback/{safe_client_slug(client)}/{year_label}",
    )


def append_feedback_events(
    *,
    client: str,
    year: int | None,
    events: Iterable[dict[str, object]],
) -> Path | None:
    client_s = str(client or "").strip()
    payload = [dict(event) for event in (events or ()) if isinstance(event, dict)]
    if not client_s or not payload:
        return None

    path = _feedback_path(client_s, year)
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with open(path, "a", encoding="utf-8") as handle:
        for event in payload:
            event.setdefault("timestamp", timestamp)
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=False) + "\n")
    return path
