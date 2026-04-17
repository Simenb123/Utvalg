"""Global detaljklassifisering av kontoer.

Modulen eier det globale regel-dokumentet (alias + kontointervall +
ekskludering + kategori) og en matching-motor som returnerer detalj-klasse-id
for en gitt konto. Klientspesifikke overstyringer lagres i `AccountProfile`
(runde 2) og kobles inn via `resolve_detail_class_for_account`.

Dokumentformat (JSON):
    {
      "classes": [
        {
          "id": "skyldig_mva",
          "navn": "Skyldig MVA",
          "kategori": "forpliktelse",
          "kontointervall": ["2740-2770"],
          "aliaser": ["skyldig mva"],
          "ekskluder_aliaser": [],
          "aktiv": true,
          "sortering": 10
        }
      ]
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

import classification_config


SEED_CLASSES: tuple[dict[str, Any], ...] = (
    {
        "id": "skyldig_mva",
        "navn": "Skyldig MVA",
        "kategori": "forpliktelse",
        "kontointervall": ["2740-2770"],
        "aliaser": ["skyldig mva", "utgående merverdiavgift", "mva oppgjør"],
        "ekskluder_aliaser": [],
        "aktiv": True,
        "sortering": 10,
    },
    {
        "id": "skyldig_forskuddstrekk",
        "navn": "Skyldig forskuddstrekk",
        "kategori": "forpliktelse",
        "kontointervall": ["2600-2619"],
        "aliaser": ["forskuddstrekk", "skyldig skattetrekk"],
        "ekskluder_aliaser": [],
        "aktiv": True,
        "sortering": 20,
    },
    {
        "id": "kostnadsfoert_arbeidsgiveravgift",
        "navn": "Kostnadsført arbeidsgiveravgift",
        "kategori": "kostnad",
        "kontointervall": ["5400-5499"],
        "aliaser": [],
        "ekskluder_aliaser": [],
        "aktiv": True,
        "sortering": 25,
    },
    {
        "id": "skyldig_arbeidsgiveravgift",
        "navn": "Skyldig arbeidsgiveravgift",
        "kategori": "forpliktelse",
        "kontointervall": ["2770-2779"],
        "aliaser": ["skyldig arbeidsgiveravgift", "aga"],
        "ekskluder_aliaser": ["feriepenger"],
        "aktiv": True,
        "sortering": 30,
    },
    {
        "id": "skyldig_feriepenger",
        "navn": "Skyldig feriepenger",
        "kategori": "forpliktelse",
        "kontointervall": ["2940-2949"],
        "aliaser": ["skyldig feriepenger", "avsatt feriepenger"],
        "ekskluder_aliaser": [],
        "aktiv": True,
        "sortering": 40,
    },
    {
        "id": "skyldig_arbeidsgiveravgift_feriepenger",
        "navn": "Skyldig arbeidsgiveravgift av feriepenger",
        "kategori": "forpliktelse",
        "kontointervall": ["2780-2789"],
        "aliaser": ["arbeidsgiveravgift av feriepenger", "aga feriepenger"],
        "ekskluder_aliaser": [],
        "aktiv": True,
        "sortering": 50,
    },
)


VALID_KATEGORIER: tuple[str, ...] = (
    "forpliktelse",
    "eiendel",
    "inntekt",
    "kostnad",
    "annet",
)


@dataclass(frozen=True)
class DetailClass:
    id: str
    navn: str
    kategori: str
    kontointervall: tuple[tuple[int, int], ...] = ()
    aliaser: tuple[str, ...] = ()
    ekskluder_aliaser: tuple[str, ...] = ()
    aktiv: bool = True
    sortering: int = 0
    raw_kontointervall: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "navn": self.navn,
            "kategori": self.kategori,
            "kontointervall": list(self.raw_kontointervall),
            "aliaser": list(self.aliaser),
            "ekskluder_aliaser": list(self.ekskluder_aliaser),
            "aktiv": self.aktiv,
            "sortering": self.sortering,
        }


def _clean(text: object) -> str:
    if text is None:
        return ""
    return str(text).strip()


def _string_list(values: object) -> list[str]:
    if isinstance(values, str):
        values = [values]
    elif not isinstance(values, Iterable):
        return []
    out: list[str] = []
    for item in values:
        text = _clean(item)
        if text:
            out.append(text)
    return out


def _parse_single_range(text: str) -> tuple[int, int] | None:
    stripped = _clean(text)
    if not stripped:
        return None
    match = re.match(r"^\s*(\d{3,6})\s*(?:-\s*(\d{3,6}))?\s*$", stripped)
    if not match:
        return None
    start_text, end_text = match.group(1), match.group(2)
    try:
        start = int(start_text)
    except ValueError:
        return None
    if end_text is None:
        end = start
    else:
        try:
            end = int(end_text)
        except ValueError:
            return None
    if end < start:
        start, end = end, start
    return (start, end)


def parse_ranges(values: Sequence[object] | object) -> tuple[tuple[int, int], ...]:
    out: list[tuple[int, int]] = []
    for raw in _string_list(values):
        parsed = _parse_single_range(raw)
        if parsed is not None:
            out.append(parsed)
    return tuple(out)


def _coerce_account_int(account_no: object) -> int | None:
    if account_no is None:
        return None
    if isinstance(account_no, bool):
        return None
    if isinstance(account_no, int):
        return account_no
    text = _clean(account_no)
    if not text:
        return None
    match = re.search(r"(\d{3,6})", text)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _account_in_ranges(account_no: object, ranges: tuple[tuple[int, int], ...]) -> bool:
    if not ranges:
        return False
    value = _coerce_account_int(account_no)
    if value is None:
        return False
    return any(start <= value <= end for start, end in ranges)


def _name_matches_any(name: str, aliases: Sequence[str]) -> bool:
    if not aliases:
        return False
    lower = name.casefold()
    if not lower:
        return False
    for alias in aliases:
        token = alias.casefold()
        if token and token in lower:
            return True
    return False


def _normalize_class_entry(entry: Any) -> DetailClass | None:
    if not isinstance(entry, dict):
        return None
    class_id = _clean(entry.get("id"))
    navn = _clean(entry.get("navn")) or class_id
    if not class_id:
        return None
    kategori_raw = _clean(entry.get("kategori")).casefold() or "annet"
    kategori = kategori_raw if kategori_raw in VALID_KATEGORIER else "annet"
    raw_ranges = tuple(_string_list(entry.get("kontointervall")))
    parsed_ranges = parse_ranges(raw_ranges)
    aliaser = tuple(_string_list(entry.get("aliaser")))
    ekskluder = tuple(_string_list(entry.get("ekskluder_aliaser")))
    aktiv_raw = entry.get("aktiv")
    aktiv = True if aktiv_raw is None else bool(aktiv_raw)
    try:
        sortering = int(entry.get("sortering") or 0)
    except (TypeError, ValueError):
        sortering = 0
    return DetailClass(
        id=class_id,
        navn=navn,
        kategori=kategori,
        kontointervall=parsed_ranges,
        aliaser=aliaser,
        ekskluder_aliaser=ekskluder,
        aktiv=aktiv,
        sortering=sortering,
        raw_kontointervall=raw_ranges,
    )


def normalize_document(document: Any) -> dict[str, list[dict[str, Any]]]:
    classes: list[dict[str, Any]] = []
    seen: set[str] = set()
    raw_classes: list[Any] = []
    if isinstance(document, dict):
        raw = document.get("classes")
        if isinstance(raw, list):
            raw_classes = raw
    for raw_entry in raw_classes:
        normalized = _normalize_class_entry(raw_entry)
        if normalized is None:
            continue
        if normalized.id in seen:
            continue
        seen.add(normalized.id)
        classes.append(normalized.to_dict())
    return {"classes": classes}


def _seed_document() -> dict[str, list[dict[str, Any]]]:
    return {"classes": [dict(entry) for entry in SEED_CLASSES]}


def load_detail_class_catalog() -> list[DetailClass]:
    """Les globalt dokument og returner sortert liste over gyldige klasser.

    Tom/manglende fil seedes automatisk via `classification_config`."""

    document = classification_config.load_account_detail_classification_document()
    entries: list[DetailClass] = []
    seen: set[str] = set()
    raw_classes = []
    if isinstance(document, dict):
        raw_classes = document.get("classes", []) or []
    for raw_entry in raw_classes:
        normalized = _normalize_class_entry(raw_entry)
        if normalized is None or normalized.id in seen:
            continue
        seen.add(normalized.id)
        entries.append(normalized)
    entries.sort(key=lambda dc: (dc.sortering, dc.id.casefold()))
    return entries


def match_detail_class(
    account_no: object,
    account_name: object,
    catalog: Sequence[DetailClass],
) -> str | None:
    """Returner id på første matchende klasse i sortert katalog, eller None.

    Semantikk:
      1. Inaktive klasser hoppes over.
      2. Hvis `ekskluder_aliaser` treffer kontonavnet: hard blokk, gå videre.
      3. Hvis både intervall og aliaser er definert: OR-match.
      4. Hvis kun intervall: intervall-match.
      5. Hvis kun aliaser: alias-match.
      6. Ingen av delene: klassen kan aldri matche.
    """

    name_text = _clean(account_name)
    for entry in catalog:
        if not entry.aktiv:
            continue
        if _name_matches_any(name_text, entry.ekskluder_aliaser):
            continue
        has_ranges = bool(entry.kontointervall)
        has_aliases = bool(entry.aliaser)
        if not has_ranges and not has_aliases:
            continue
        in_range = _account_in_ranges(account_no, entry.kontointervall)
        alias_hit = _name_matches_any(name_text, entry.aliaser)
        if has_ranges and has_aliases:
            if in_range or alias_hit:
                return entry.id
        elif has_ranges:
            if in_range:
                return entry.id
        elif has_aliases:
            if alias_hit:
                return entry.id
    return None


def format_detail_class_label(
    class_id: object,
    catalog: Sequence[DetailClass] | None = None,
) -> str:
    """Returner visningsnavn for en klasse-id, eller id selv om ukjent."""

    cid = _clean(class_id)
    if not cid:
        return ""
    if catalog is None:
        catalog = load_detail_class_catalog()
    for entry in catalog:
        if entry.id == cid:
            return entry.navn
    return cid


def resolve_detail_class_for_account(
    profile_override: object,
    account_no: object,
    account_name: object,
    catalog: Sequence[DetailClass] | None = None,
) -> str | None:
    """Prioritet: lagret profil-id > global regelmatch > None.

    `profile_override` er `AccountProfile.detail_class_id` eller tom streng/None.
    """

    override = _clean(profile_override)
    if override:
        return override
    if catalog is None:
        catalog = load_detail_class_catalog()
    return match_detail_class(account_no, account_name, catalog)


__all__ = [
    "DetailClass",
    "SEED_CLASSES",
    "VALID_KATEGORIER",
    "format_detail_class_label",
    "load_detail_class_catalog",
    "match_detail_class",
    "normalize_document",
    "parse_ranges",
    "resolve_detail_class_for_account",
]
