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
