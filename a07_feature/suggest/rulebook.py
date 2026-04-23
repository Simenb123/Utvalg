from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Sequence, Tuple

import classification_config

from ..groups import a07_code_aliases


@dataclass(frozen=True)
class RulebookSpecialAdd:
    account: str
    basis: Optional[str] = None
    weight: float = 1.0
    keywords: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RulebookRule:
    label: Optional[str] = None
    category: Optional[str] = None
    rf1022_group: Optional[str] = None
    aga_pliktig: Optional[bool] = None
    allowed_ranges: Tuple[Tuple[int, int], ...] = ()
    keywords: Tuple[str, ...] = ()
    exclude_keywords: Tuple[str, ...] = ()
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
    replacements = {
        "ø": "oe",
        "æ": "ae",
        "å": "aa",
        "Ã¸": "oe",
        "Ã¦": "ae",
        "Ã¥": "aa",
        "ÃƒÂ¸": "oe",
        "ÃƒÂ¦": "ae",
        "ÃƒÂ¥": "aa",
        "_": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _optional_bool(value: object) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value or "").strip().casefold()
    if text in {"1", "true", "ja", "j", "yes", "y"}:
        return True
    if text in {"0", "false", "nei", "n", "no"}:
        return False
    return None


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

        raw_keywords = item.get("keywords", []) or item.get("name_keywords", []) or []
        if isinstance(raw_keywords, str):
            keyword_values = [part.strip() for part in re.split(r"[\n;,]+", raw_keywords) if part.strip()]
        elif isinstance(raw_keywords, (list, tuple, set)):
            keyword_values = [str(part or "").strip() for part in raw_keywords if str(part or "").strip()]
        else:
            keyword_values = []

        out.append(
            RulebookSpecialAdd(
                account=account,
                basis=basis,
                weight=weight,
                keywords=tuple(dict.fromkeys(keyword_values)),
            )
        )

    return tuple(out)


def _find_rulebook_path(explicit: Optional[str] = None) -> Optional[str]:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    else:
        candidates.append(classification_config.resolve_rulebook_path())

    filenames = (
        "config/classification/global_full_a07_rulebook.json",
        "global_full_a07_rulebook.json",
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


@lru_cache(maxsize=16)
def _load_rulebook_cached(path: str, mtime_ns: int) -> Rulebook:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    aliases: Dict[str, Tuple[str, ...]] = {}
    rules_raw = data.get("rules", {})
    if not isinstance(rules_raw, dict):
        return {}

    out: Rulebook = {}
    for code, rule in rules_raw.items():
        if not isinstance(rule, dict):
            continue

        label = str(rule.get("label") or "").strip() or None
        category = str(rule.get("category") or "").strip() or None
        rf1022_group = str(rule.get("rf1022_group") or "").strip() or None
        aga_pliktig = _optional_bool(rule.get("aga_pliktig"))
        raw_keywords = tuple(rule.get("keywords", []) or [])

        allowed = _parse_ranges(rule.get("allowed_ranges", []) or [])

        keywords = _expand_keywords(
            code=rule.get("code") or code,
            label=label,
            raw_keywords=raw_keywords,
            aliases=aliases,
        )
        exclude_keywords = _expand_keywords(
            code="",
            label="",
            raw_keywords=rule.get("exclude_keywords", []) or [],
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

        parsed_rule = RulebookRule(
            label=label,
            category=category,
            rf1022_group=rf1022_group,
            aga_pliktig=aga_pliktig,
            allowed_ranges=allowed,
            keywords=keywords,
            exclude_keywords=exclude_keywords,
            boost_accounts=boost_accounts,
            special_add=special_add,
            basis=str(basis) if basis else None,
            expected_sign=expected_sign if expected_sign in (-1, 0, 1) else None,
        )
        for alias in a07_code_aliases(code):
            alias_s = str(alias or "").strip()
            if alias_s and alias_s not in out:
                out[alias_s] = parsed_rule

    return out


def clear_rulebook_cache() -> None:
    _load_rulebook_cached.cache_clear()


def load_rulebook(rulebook_path: Optional[str]) -> Rulebook:
    path = _find_rulebook_path(rulebook_path)
    if not path:
        return {}

    try:
        mtime_ns = Path(path).stat().st_mtime_ns
    except Exception:
        mtime_ns = 0
    return dict(_load_rulebook_cached(str(path), int(mtime_ns)))
