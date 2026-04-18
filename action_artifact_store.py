"""Lagring av arbeidspapir-artefakter og kommentarer per handling/klient/år.

To JSON-filer i `years/<YYYY>/`:

- `arbeidspapir_index.json` — hvilke filer ble produsert av hvilken handling
  (brukes som revisjonsspor og som kilde for fil-listen i handling-detalj-popup).
- `action_comments.json` — revisors fritekst-kommentarer per handling.

`action_key` er strengen `"L:<uuid>"` for lokale handlinger og `str(action_id)`
for CRM-handlinger.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:  # frivillig — utenom testmiljø har vi client_store
    import client_store
except Exception:  # pragma: no cover
    client_store = None  # type: ignore


ARTIFACT_INDEX_NAME = "arbeidspapir_index.json"
COMMENTS_NAME = "action_comments.json"


@dataclass
class Artifact:
    action_key: str
    workpaper_id: str
    workpaper_navn: str
    file_path: str  # absolutt sti — snapshot-øyeblikket
    filename: str
    size: int = 0
    kjort_at: str = ""
    kjort_av: str = ""

    @staticmethod
    def from_path(
        *,
        action_key: str,
        workpaper_id: str,
        workpaper_navn: str,
        path: Path,
        kjort_av: str = "",
    ) -> "Artifact":
        stat = path.stat() if path.exists() else None
        return Artifact(
            action_key=action_key,
            workpaper_id=workpaper_id,
            workpaper_navn=workpaper_navn,
            file_path=str(path),
            filename=path.name,
            size=stat.st_size if stat else 0,
            kjort_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            kjort_av=kjort_av,
        )


@dataclass
class Comment:
    action_key: str
    text: str = ""
    updated_at: str = ""
    updated_by: str = ""


# ---------------------------------------------------------------------------
# Stier


def _year_dir(client: str, year: str) -> Path | None:
    if not (client and year and client_store):
        return None
    try:
        return client_store.years_dir(client, year=year)
    except Exception:
        return None


def artifact_index_path(client: str, year: str) -> Path | None:
    d = _year_dir(client, year)
    return (d / ARTIFACT_INDEX_NAME) if d else None


def comments_path(client: str, year: str) -> Path | None:
    d = _year_dir(client, year)
    return (d / COMMENTS_NAME) if d else None


# ---------------------------------------------------------------------------
# Artifact index


def _read_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_artifacts(client: str, year: str) -> list[Artifact]:
    p = artifact_index_path(client, year)
    data = _read_json(p)
    raw = data.get("artifacts", [])
    if not isinstance(raw, list):
        return []
    out: list[Artifact] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                Artifact(
                    action_key=str(item.get("action_key", "")).strip(),
                    workpaper_id=str(item.get("workpaper_id", "")).strip(),
                    workpaper_navn=str(item.get("workpaper_navn", "")).strip(),
                    file_path=str(item.get("file_path", "")).strip(),
                    filename=str(item.get("filename", "")).strip(),
                    size=int(item.get("size", 0) or 0),
                    kjort_at=str(item.get("kjort_at", "")).strip(),
                    kjort_av=str(item.get("kjort_av", "")).strip(),
                )
            )
        except Exception:
            continue
    return out


def save_artifacts(client: str, year: str, items: Iterable[Artifact]) -> None:
    p = artifact_index_path(client, year)
    if p is None:
        return
    _write_json(p, {"artifacts": [asdict(a) for a in items]})


def register_artifact(client: str, year: str, artifact: Artifact) -> list[Artifact]:
    items = load_artifacts(client, year)
    # Dedup på (action_key, file_path) — nyeste erstatter eldre
    key = (artifact.action_key, artifact.file_path)
    items = [a for a in items if (a.action_key, a.file_path) != key]
    items.append(artifact)
    save_artifacts(client, year, items)
    return items


def artifacts_for(client: str, year: str, action_key: str) -> list[Artifact]:
    return [a for a in load_artifacts(client, year) if a.action_key == action_key]


def prune_missing(client: str, year: str) -> list[Artifact]:
    """Fjerner manifestoppføringer der filen er slettet."""
    items = [a for a in load_artifacts(client, year) if Path(a.file_path).exists()]
    save_artifacts(client, year, items)
    return items


# ---------------------------------------------------------------------------
# Kommentarer


def load_comments(client: str, year: str) -> dict[str, Comment]:
    p = comments_path(client, year)
    data = _read_json(p)
    raw = data.get("comments", {})
    out: dict[str, Comment] = {}
    if isinstance(raw, dict):
        for key, val in raw.items():
            if not isinstance(val, dict):
                continue
            k = str(key).strip()
            if not k:
                continue
            out[k] = Comment(
                action_key=k,
                text=str(val.get("text", "")),
                updated_at=str(val.get("updated_at", "")).strip(),
                updated_by=str(val.get("updated_by", "")).strip(),
            )
    return out


def save_comment(
    client: str, year: str, action_key: str, text: str, *, updated_by: str = ""
) -> Comment:
    p = comments_path(client, year)
    if p is None:
        return Comment(action_key=action_key, text=text)
    comments = load_comments(client, year)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cleaned = (text or "").rstrip()
    if not cleaned:
        comments.pop(action_key, None)
    else:
        comments[action_key] = Comment(
            action_key=action_key, text=cleaned, updated_at=now, updated_by=updated_by,
        )
    payload = {"comments": {k: asdict(c) for k, c in comments.items()}}
    _write_json(p, payload)
    return comments.get(action_key, Comment(action_key=action_key))


def get_comment(client: str, year: str, action_key: str) -> Comment:
    return load_comments(client, year).get(action_key, Comment(action_key=action_key))
