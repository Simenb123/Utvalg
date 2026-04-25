"""Lokalt handlingsbibliotek — brukerdefinerte revisjonshandlinger.

Holdes strengt adskilt fra CRM/Descartes-handlinger. Lagres i JSON under
brukerens datamappe (frozen-safe via app_paths.data_dir()).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import List
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import app_paths


DEFAULT_ACTION_TYPES: tuple[str, ...] = (
    "substansiv",
    "kontroll",
    "analyse",
    "innledende",
    "annen",
)

# Bakoverkompatibelt alias — bruk load_types() for den brukerdefinerte listen.
ACTION_TYPES = DEFAULT_ACTION_TYPES


@dataclass
class LocalAction:
    id: str
    navn: str
    type: str = "substansiv"
    omraade: str = ""
    default_regnr: str = ""
    standard_arbeidspapir: str = ""
    workpaper_ids: List[str] = field(default_factory=list)
    beskrivelse: str = ""
    opprettet: str = ""
    endret: str = ""
    # Hvilken fase i revisjonsprosessen handlingen tilhører.
    # Tom streng = ikke satt (faller tilbake til keyword-gjetting i UI).
    fase: str = ""
    # Multi-RL-kobling: liste over regnr (som strenger) handlingen
    # er relevant for. Brukes i tillegg til ``default_regnr`` (som
    # beholdes for bakoverkompat).
    applies_to_regnr: List[str] = field(default_factory=list)
    # Bredde-scope: "" (bruk listen over), "alle_pl", "alle_bs", "alle".
    # Når satt overstyrer den ``applies_to_regnr`` og dekker hele gruppen.
    applies_to_scope: str = ""

    def applies_to(self, regnr: str, line_type: str = "") -> bool:
        """Returner True hvis handlingen er relevant for ``regnr``.

        ``line_type`` brukes når ``applies_to_scope`` er "alle_pl" eller
        "alle_bs" (verdier "PL" / "BS"). Hvis scope er "alle" treffer alt.
        """
        regnr_s = str(regnr or "").strip()
        if not regnr_s:
            return False
        scope = (self.applies_to_scope or "").strip().lower()
        if scope == "alle":
            return True
        if scope == "alle_pl" and (line_type or "").upper() == "PL":
            return True
        if scope == "alle_bs" and (line_type or "").upper() == "BS":
            return True
        if regnr_s in (self.applies_to_regnr or ()):
            return True
        # Bakoverkompat: gammel default_regnr-felt teller som "én RL i listen"
        if regnr_s and str(self.default_regnr or "").strip() == regnr_s:
            return True
        return False

    @staticmethod
    def new(navn: str, **kwargs: object) -> "LocalAction":
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        workpaper_ids = kwargs.pop("workpaper_ids", None)
        action = LocalAction(
            id=str(uuid.uuid4()),
            navn=str(navn).strip(),
            opprettet=now,
            endret=now,
            **{k: str(v) for k, v in kwargs.items()},  # type: ignore[arg-type]
        )
        if isinstance(workpaper_ids, list):
            action.workpaper_ids = [str(x) for x in workpaper_ids]
        return action


def library_path() -> Path:
    return app_paths.data_dir() / "action_library.json"


def _normalize(item: dict) -> LocalAction | None:
    try:
        navn = str(item.get("navn", "")).strip()
        if not navn:
            return None
        type_ = str(item.get("type", "")).strip()
        raw_ids = item.get("workpaper_ids") or []
        if not isinstance(raw_ids, list):
            raw_ids = []
        workpaper_ids = [str(x).strip() for x in raw_ids if str(x).strip()]
        # Multi-RL-felter — kan være fraværende på eldre lagrede
        # handlinger; behandle som tom liste / tom scope.
        raw_applies = item.get("applies_to_regnr") or []
        if not isinstance(raw_applies, list):
            raw_applies = []
        applies_to_regnr = [str(x).strip() for x in raw_applies if str(x).strip()]
        applies_to_scope = str(item.get("applies_to_scope", "")).strip().lower()
        if applies_to_scope not in ("", "alle", "alle_pl", "alle_bs"):
            applies_to_scope = ""

        return LocalAction(
            id=str(item.get("id") or uuid.uuid4()),
            navn=navn,
            type=type_,
            omraade=str(item.get("omraade", "")).strip(),
            default_regnr=str(item.get("default_regnr", "")).strip(),
            standard_arbeidspapir=str(item.get("standard_arbeidspapir", "")).strip(),
            workpaper_ids=workpaper_ids,
            beskrivelse=str(item.get("beskrivelse", "")).strip(),
            opprettet=str(item.get("opprettet", "")).strip(),
            endret=str(item.get("endret", "")).strip(),
            fase=str(item.get("fase", "")).strip(),
            applies_to_regnr=applies_to_regnr,
            applies_to_scope=applies_to_scope,
        )
    except Exception:
        return None


def _read_raw(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {"actions": data}


def load_library(path: Path | None = None) -> list[LocalAction]:
    p = path or library_path()
    data = _read_raw(p)
    items = data.get("actions", [])
    if not isinstance(items, list):
        return []
    out: list[LocalAction] = []
    for raw in items:
        if isinstance(raw, dict):
            a = _normalize(raw)
            if a is not None:
                out.append(a)
    return out


def load_types(path: Path | None = None) -> list[str]:
    p = path or library_path()
    data = _read_raw(p)
    raw = data.get("types")
    if isinstance(raw, list):
        out: list[str] = []
        seen: set[str] = set()
        for v in raw:
            s = str(v).strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        if out:
            return out
    return list(DEFAULT_ACTION_TYPES)


def save_library(
    actions: Iterable[LocalAction],
    path: Path | None = None,
    *,
    types: Iterable[str] | None = None,
) -> None:
    p = path or library_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_raw(p)
    payload = {
        "types": list(types) if types is not None else existing.get("types") or list(DEFAULT_ACTION_TYPES),
        "actions": [asdict(a) for a in actions],
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    tmp.replace(p)


def save_types(types: Iterable[str], path: Path | None = None) -> list[str]:
    p = path or library_path()
    actions = load_library(p)
    cleaned: list[str] = []
    seen: set[str] = set()
    for v in types:
        s = str(v).strip()
        if s and s not in seen:
            seen.add(s)
            cleaned.append(s)
    save_library(actions, p, types=cleaned)
    return cleaned


def upsert_action(action: LocalAction, path: Path | None = None) -> list[LocalAction]:
    items = load_library(path)
    action.endret = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if not action.opprettet:
        action.opprettet = action.endret
    for i, existing in enumerate(items):
        if existing.id == action.id:
            items[i] = action
            break
    else:
        items.append(action)
    save_library(items, path)
    return items


def delete_action(action_id: str, path: Path | None = None) -> list[LocalAction]:
    items = [a for a in load_library(path) if a.id != action_id]
    save_library(items, path)
    return items
