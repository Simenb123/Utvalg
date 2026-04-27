"""Lokalt arbeidspapir-bibliotek — katalog over arbeidspapir-typer.

Holder kartoteket adskilt fra handlingsbiblioteket. Hvert arbeidspapir kan
senere peke på en eksisterende generator (excel/PDF/HTML-eksport) via
`generator_id`, men i denne runden er det kun en tekst-referanse.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import app_paths
from . import generators as workpaper_generators


DEFAULT_KATEGORIER: tuple[str, ...] = ("generert", "manuell")


@dataclass
class Workpaper:
    id: str
    navn: str
    kategori: str = "manuell"
    generator_id: str = ""
    beskrivelse: str = ""
    mal: str = ""
    opprettet: str = ""
    endret: str = ""

    @staticmethod
    def new(navn: str, **kwargs: object) -> "Workpaper":
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return Workpaper(
            id=str(uuid.uuid4()),
            navn=str(navn).strip(),
            opprettet=now,
            endret=now,
            **{k: str(v) for k, v in kwargs.items()},  # type: ignore[arg-type]
        )


def library_path() -> Path:
    return app_paths.data_dir() / "workpaper_library.json"


def _read_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {"workpapers": data}


def _normalize(item: dict) -> Workpaper | None:
    try:
        navn = str(item.get("navn", "")).strip()
        if not navn:
            return None
        return Workpaper(
            id=str(item.get("id") or uuid.uuid4()),
            navn=navn,
            kategori=str(item.get("kategori", "manuell")).strip() or "manuell",
            generator_id=str(item.get("generator_id", "")).strip(),
            beskrivelse=str(item.get("beskrivelse", "")).strip(),
            mal=str(item.get("mal", "")).strip(),
            opprettet=str(item.get("opprettet", "")).strip(),
            endret=str(item.get("endret", "")).strip(),
        )
    except Exception:
        return None


def load_library(path: Path | None = None) -> list[Workpaper]:
    p = path or library_path()
    data = _read_raw(p)
    items = data.get("workpapers", [])
    if not isinstance(items, list):
        return []
    out: list[Workpaper] = []
    for raw in items:
        if isinstance(raw, dict):
            wp = _normalize(raw)
            if wp is not None:
                out.append(wp)
    return out


def save_library(items: Iterable[Workpaper], path: Path | None = None) -> None:
    p = path or library_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"workpapers": [asdict(w) for w in items]}
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    tmp.replace(p)


def upsert_workpaper(wp: Workpaper, path: Path | None = None) -> list[Workpaper]:
    items = load_library(path)
    wp.endret = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not wp.opprettet:
        wp.opprettet = wp.endret
    for i, existing in enumerate(items):
        if existing.id == wp.id:
            items[i] = wp
            break
    else:
        items.append(wp)
    save_library(items, path)
    return items


def delete_workpaper(wp_id: str, path: Path | None = None) -> list[Workpaper]:
    items = [w for w in load_library(path) if w.id != wp_id]
    save_library(items, path)
    return items


def by_id(items: Iterable[Workpaper]) -> dict[str, Workpaper]:
    return {w.id: w for w in items}


def list_builtins() -> list[Workpaper]:
    """Returnerer de innebygde generatorene som Workpaper-objekter.

    Disse kommer fra `workpaper_generators.BUILTIN_GENERATORS` og er låste —
    kan ikke slettes eller redigeres, men kobles til handlinger som vanlig.
    """
    return [
        Workpaper(
            id=g.id,
            navn=g.navn,
            kategori="generert",
            generator_id=g.method_name,
            beskrivelse=g.beskrivelse,
        )
        for g in workpaper_generators.BUILTIN_GENERATORS
    ]


def list_all(path: Path | None = None) -> list[Workpaper]:
    """Alle arbeidspapir — innebygde først, deretter brukerdefinerte."""
    return list_builtins() + load_library(path)


def is_builtin(wp_id: str) -> bool:
    return workpaper_generators.is_builtin(wp_id)
