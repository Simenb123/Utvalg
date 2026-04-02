from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class UiSuggestionRow:
    kode: str
    kode_navn: str
    a07_belop: float
    gl_kontoer: list[str]
    gl_sum: float
    diff: float
    score: float | None = None
    combo_size: int = 1
    within_tolerance: bool = False
    hit_tokens: list[str] = field(default_factory=list)
    source_index: int | None = None


def select_best_suggestion_for_code(
    suggestions: Sequence[UiSuggestionRow],
    code: str,
    *,
    require_within_tolerance: bool = True,
    locked_codes: set[str] | None = None,
    exclude_hit_token_prefixes: tuple[str, ...] = ("A07_GROUP:",),
) -> UiSuggestionRow | None:
    code_str = str(code or "").strip()
    if not code_str:
        return None

    locked = {str(x).strip() for x in (locked_codes or set()) if str(x).strip()}
    if code_str in locked:
        return None

    def _is_excluded(suggestion: UiSuggestionRow) -> bool:
        if not exclude_hit_token_prefixes:
            return False
        for token in getattr(suggestion, "hit_tokens", None) or []:
            token_str = str(token)
            if any(token_str.startswith(prefix) for prefix in exclude_hit_token_prefixes):
                return True
        return False

    candidates: list[UiSuggestionRow] = []
    for suggestion in suggestions or []:
        try:
            if str(getattr(suggestion, "kode", "")).strip() != code_str:
                continue
        except Exception:
            continue

        if require_within_tolerance and not bool(getattr(suggestion, "within_tolerance", False)):
            continue
        if _is_excluded(suggestion):
            continue
        candidates.append(suggestion)

    if not candidates:
        return None

    def _score(suggestion: UiSuggestionRow) -> float:
        try:
            value = getattr(suggestion, "score", 0.0)
            return 0.0 if value is None else float(value)
        except Exception:
            return 0.0

    def _abs_diff(suggestion: UiSuggestionRow) -> float:
        try:
            return abs(float(getattr(suggestion, "diff", 0.0) or 0.0))
        except Exception:
            return 0.0

    best = candidates[0]
    for suggestion in candidates[1:]:
        if (_score(suggestion) > _score(best)) or (
            _score(suggestion) == _score(best) and _abs_diff(suggestion) < _abs_diff(best)
        ):
            best = suggestion
    return best


def _normalized_mapping(mapping_existing: dict[str, str] | None) -> dict[str, str]:
    return {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_existing or {}).items()
        if str(account).strip() and str(code).strip()
    }


def _normalized_accounts(suggestion: UiSuggestionRow) -> list[str]:
    return [
        str(account).strip()
        for account in getattr(suggestion, "gl_kontoer", ()) or ()
        if str(account).strip()
    ]


def _score(suggestion: UiSuggestionRow) -> float:
    try:
        value = getattr(suggestion, "score", 0.0)
        return 0.0 if value is None else float(value)
    except Exception:
        return 0.0


def _ordered_codes(suggestions: Sequence[UiSuggestionRow]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for suggestion in suggestions or ():
        code = str(getattr(suggestion, "kode", "")).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        ordered.append(code)
    return ordered


def select_batch_suggestions(
    suggestions: Sequence[UiSuggestionRow],
    mapping_existing: dict[str, str] | None,
    *,
    min_score: float = 0.85,
    locked_codes: set[str] | None = None,
) -> list[UiSuggestionRow]:
    mapping_nonempty = _normalized_mapping(mapping_existing)
    reserved_accounts: set[str] = set()
    selected: list[UiSuggestionRow] = []

    for code in _ordered_codes(suggestions):
        best = select_best_suggestion_for_code(suggestions, code, locked_codes=locked_codes)
        if best is None:
            continue
        if _score(best) < float(min_score):
            continue

        accounts = _normalized_accounts(best)
        if not accounts:
            continue

        conflict = False
        for account in accounts:
            existing_code = mapping_nonempty.get(account)
            if existing_code and existing_code != code:
                conflict = True
                break
            if account in reserved_accounts:
                conflict = True
                break
        if conflict:
            continue

        selected.append(best)
        reserved_accounts.update(accounts)
    return selected


def select_magic_wand_suggestions(
    suggestions: Sequence[UiSuggestionRow],
    mapping_existing: dict[str, str] | None,
    *,
    unresolved_codes: Sequence[object] | None = None,
    locked_codes: set[str] | None = None,
) -> list[UiSuggestionRow]:
    unresolved = {
        str(code).strip()
        for code in (unresolved_codes or ())
        if str(code).strip()
    }
    mapping_nonempty = _normalized_mapping(mapping_existing)
    reserved_accounts: set[str] = set()
    selected: list[UiSuggestionRow] = []

    for code in _ordered_codes(suggestions):
        if unresolved and code not in unresolved:
            continue
        best = select_best_suggestion_for_code(suggestions, code, locked_codes=locked_codes)
        if best is None:
            continue

        accounts = _normalized_accounts(best)
        if not accounts:
            continue

        conflict = False
        for account in accounts:
            existing_code = mapping_nonempty.get(account)
            if existing_code and existing_code != code:
                conflict = True
                break
            if account in reserved_accounts:
                conflict = True
                break
        if conflict:
            continue

        selected.append(best)
        reserved_accounts.update(accounts)
    return selected
