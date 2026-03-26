from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class RulebookSpecialAdd:
    account: str
    basis: Optional[str] = None
    weight: float = 1.0


@dataclass(frozen=True)
class RulebookRule:
    label: Optional[str] = None
    category: Optional[str] = None
    allowed_ranges: Tuple[Tuple[int, int], ...] = ()
    keywords: Tuple[str, ...] = ()
    boost_accounts: Tuple[int, ...] = ()
    special_add: Tuple[RulebookSpecialAdd, ...] = ()
    basis: Optional[str] = None
    expected_sign: Optional[int] = None


Rulebook = Dict[str, RulebookRule]


def _parse_ranges(ranges: Sequence[str]) -> Tuple[Tuple[int, int], ...]:
    out: List[Tuple[int, int]] = []
    for raw in ranges:
        if not raw:
            continue
        parts = [part.strip() for part in str(raw).split("|") if str(part).strip()]
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


def _normalize_alias_key(value: object) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("ø", "oe").replace("æ", "ae").replace("å", "aa")
    return text


def _parse_aliases(data: object) -> Dict[str, Tuple[str, ...]]:
    if not isinstance(data, dict):
        return {}

    out: Dict[str, Tuple[str, ...]] = {}
    for raw_key, raw_values in data.items():
        key = _normalize_alias_key(raw_key)
        if not key:
            continue
        values: List[str] = []
        if isinstance(raw_values, (list, tuple, set)):
            for raw_value in raw_values:
                value = str(raw_value or "").strip()
                if value:
                    values.append(value)
        out[key] = tuple(values)
    return out


def _expand_keywords(
    *,
    code: object,
    label: object,
    raw_keywords: Sequence[object],
    aliases: Dict[str, Tuple[str, ...]],
) -> Tuple[str, ...]:
    out: List[str] = []
    seen: set[str] = set()
    pending: List[str] = []

    for value in (code, label, *(raw_keywords or ())):
        text = str(value or "").strip()
        if text:
            pending.append(text)

    while pending:
        text = pending.pop(0).strip()
        if not text:
            continue

        normalized = _normalize_alias_key(text)
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(text)

        for alias in aliases.get(normalized, ()):
            alias_text = str(alias or "").strip()
            if alias_text:
                pending.append(alias_text)

    return tuple(out)


def _parse_special_add(items: object) -> Tuple[RulebookSpecialAdd, ...]:
    if not isinstance(items, (list, tuple)):
        return ()

    out: List[RulebookSpecialAdd] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        account = str(item.get("account") or "").strip()
        if not account:
            continue

        basis = str(item.get("basis") or "").strip() or None
        weight_raw = item.get("weight", 1.0)
        try:
            weight = float(weight_raw)
        except Exception:
            weight = 1.0

        out.append(RulebookSpecialAdd(account=account, basis=basis, weight=weight))

    return tuple(out)


def _find_rulebook_path(explicit: Optional[str] = None) -> Optional[str]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))

    filenames = (
        "global_full_a07_rulebook.json",
        "a07_rulebook.json",
        "rulebook.json",
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


def load_rulebook(rulebook_path: Optional[str]) -> Rulebook:
    path = _find_rulebook_path(rulebook_path)
    if not path:
        return {}

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    aliases = _parse_aliases(data.get("aliases", {}))
    rules_raw = data.get("rules", {})
    if not isinstance(rules_raw, dict):
        return {}

    out: Rulebook = {}
    for code, rule in rules_raw.items():
        if not isinstance(rule, dict):
            continue

        label = str(rule.get("label") or "").strip() or None
        category = str(rule.get("category") or "").strip() or None
        allowed = _parse_ranges(rule.get("allowed_ranges", []) or [])
        keywords = _expand_keywords(
            code=rule.get("code") or code,
            label=label,
            raw_keywords=rule.get("keywords", []) or [],
            aliases=aliases,
        )
        boost_accounts = tuple(
            int(x)
            for x in (rule.get("boost_accounts", []) or [])
            if str(x).strip().isdigit()
        )
        special_add = _parse_special_add(rule.get("special_add", []) or [])
        basis = rule.get("basis")
        expected_sign = rule.get("expected_sign")
        if expected_sign is not None:
            try:
                expected_sign = int(expected_sign)
            except Exception:
                expected_sign = None

        out[str(code)] = RulebookRule(
            label=label,
            category=category,
            allowed_ranges=allowed,
            keywords=keywords,
            boost_accounts=boost_accounts,
            special_add=special_add,
            basis=str(basis) if basis else None,
            expected_sign=expected_sign if expected_sign in (-1, 0, 1) else None,
        )

    return out
