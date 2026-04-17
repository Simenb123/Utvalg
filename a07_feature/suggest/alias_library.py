from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import classification_config


@dataclass(frozen=True)
class AliasConcept:
    key: str
    aliases: Tuple[str, ...] = ()
    exclude_aliases: Tuple[str, ...] = ()
    account_ranges: Tuple[Tuple[int, int], ...] = ()
    boost_accounts: Tuple[int, ...] = ()


AliasLibrary = Dict[str, AliasConcept]


def normalize_alias_term(value: object) -> str:
    text = str(value or "").strip().lower()
    replacements = {
        "ø": "oe",
        "æ": "ae",
        "å": "aa",
        "Ã¸": "oe",
        "Ã¦": "ae",
        "Ã¥": "aa",
        "_": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _parse_ranges(ranges: Sequence[object]) -> Tuple[Tuple[int, int], ...]:
    out: List[Tuple[int, int]] = []
    for raw in ranges or ():
        if raw is None:
            continue
        parts = [part.strip() for part in str(raw).split("|") if part.strip()]
        for text in parts:
            match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", text)
            if match:
                start = int(match.group(1))
                end = int(match.group(2))
                out.append((min(start, end), max(start, end)))
                continue
            single = re.match(r"^\s*(\d+)\s*$", text)
            if single:
                value = int(single.group(1))
                out.append((value, value))
    return tuple(out)


def _parse_text_list(values: object) -> Tuple[str, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()
    out: List[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw or "").strip()
        normalized = normalize_alias_term(value)
        if not value or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(value)
    return tuple(out)


def _parse_int_list(values: object) -> Tuple[int, ...]:
    if not isinstance(values, (list, tuple, set)):
        return ()
    out: List[int] = []
    seen: set[int] = set()
    for raw in values:
        try:
            value = int(raw)
        except Exception:
            continue
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return tuple(out)


def _find_alias_library_path(explicit: Optional[str] = None) -> Optional[str]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    else:
        candidates.append(classification_config.resolve_alias_path())

    filenames = (
        "config/classification/payroll_alias_library.json",
        "config/payroll_alias_library.json",
        "payroll_alias_library.json",
    )

    def add_search_roots(root: Path) -> None:
        resolved = root.resolve()
        for parent in [resolved, *list(resolved.parents)]:
            for filename in filenames:
                candidates.append(parent / filename)

    try:
        add_search_roots(Path.cwd())
    except Exception:
        pass

    try:
        add_search_roots(Path(__file__).resolve().parent)
    except Exception:
        pass

    for path in candidates:
        try:
            if path.is_file():
                return str(path)
        except Exception:
            continue
    return None


def load_alias_library(alias_library_path: Optional[str] = None) -> AliasLibrary:
    path = _find_alias_library_path(alias_library_path)
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    raw_concepts = data.get("concepts", {}) if isinstance(data, dict) else {}
    if not isinstance(raw_concepts, dict):
        return {}

    out: AliasLibrary = {}
    for raw_key, raw_value in raw_concepts.items():
        key = normalize_alias_term(raw_key)
        if not key or not isinstance(raw_value, dict):
            continue
        out[key] = AliasConcept(
            key=key,
            aliases=_parse_text_list(raw_value.get("aliases")),
            exclude_aliases=_parse_text_list(raw_value.get("exclude_aliases")),
            account_ranges=_parse_ranges(raw_value.get("account_ranges") or ()),
            boost_accounts=_parse_int_list(raw_value.get("boost_accounts")),
        )
    return out


def build_alias_expansions(library: AliasLibrary) -> Dict[str, Tuple[str, ...]]:
    expansions: Dict[str, Tuple[str, ...]] = {}
    for concept in library.values():
        terms = [concept.key, *concept.aliases]
        dedup_terms: list[str] = []
        seen: set[str] = set()
        for term in terms:
            normalized = normalize_alias_term(term)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            dedup_terms.append(str(term))
        for term in dedup_terms:
            normalized_term = normalize_alias_term(term)
            others = [candidate for candidate in dedup_terms if normalize_alias_term(candidate) != normalized_term]
            expansions[normalized_term] = tuple(others)
    return expansions


def matching_concepts(*terms: object, library: AliasLibrary) -> Tuple[AliasConcept, ...]:
    normalized_terms = {
        normalize_alias_term(term)
        for term in terms
        if normalize_alias_term(term)
    }
    if not normalized_terms:
        return ()

    out: List[AliasConcept] = []
    seen: set[str] = set()
    for concept in library.values():
        concept_terms = {
            concept.key,
            *(normalize_alias_term(alias) for alias in concept.aliases),
        }
        if normalized_terms & concept_terms:
            if concept.key in seen:
                continue
            seen.add(concept.key)
            out.append(concept)
    return tuple(out)


def rule_defaults_for_terms(*terms: object, library: AliasLibrary) -> Tuple[Tuple[Tuple[int, int], ...], Tuple[int, ...], Tuple[str, ...]]:
    matched = matching_concepts(*terms, library=library)
    range_values: List[Tuple[int, int]] = []
    boost_values: List[int] = []
    exclude_values: List[str] = []
    seen_ranges: set[Tuple[int, int]] = set()
    seen_boost: set[int] = set()
    seen_excludes: set[str] = set()
    for concept in matched:
        for item in concept.account_ranges:
            if item in seen_ranges:
                continue
            seen_ranges.add(item)
            range_values.append(item)
        for account in concept.boost_accounts:
            if account in seen_boost:
                continue
            seen_boost.add(account)
            boost_values.append(account)
        for term in concept.exclude_aliases:
            normalized = normalize_alias_term(term)
            if not normalized or normalized in seen_excludes:
                continue
            seen_excludes.add(normalized)
            exclude_values.append(term)
    return tuple(range_values), tuple(boost_values), tuple(exclude_values)
