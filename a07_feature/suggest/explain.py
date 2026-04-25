from __future__ import annotations

from typing import List, Optional, Set

from .rulebook import RulebookRule


def _build_explain_text(
    *,
    selected_basis: str,
    rule: Optional[RulebookRule],
    hit_tokens: Set[str],
    history_accounts: Set[str],
    usage_reasons: Set[str],
    residual_target: float,
    special_add_raw: float,
    diff_total: float,
) -> str:
    parts: List[str] = [f"basis={selected_basis}"]

    if hit_tokens:
        parts.append("navn=" + ",".join(sorted(hit_tokens)))

    rule_parts: List[str] = []
    if rule:
        if rule.allowed_ranges:
            rule_parts.append("kontonr")
        if rule.boost_accounts:
            rule_parts.append("boost")
        if rule.expected_sign is not None:
            rule_parts.append(f"sign={rule.expected_sign}")
        if rule.special_add:
            rule_parts.append("special_add")
    if rule_parts:
        parts.append("regel=" + ",".join(rule_parts))

    if history_accounts:
        parts.append("historikk=" + ",".join(sorted(history_accounts)))
    if usage_reasons:
        parts.append("bruk=" + ",".join(sorted(usage_reasons)))

    parts.append(f"residual={float(residual_target):.2f}")
    if abs(float(special_add_raw)) > 0.000001:
        parts.append(f"special={float(special_add_raw):.2f}")
    parts.append(f"diff={float(diff_total):.2f}")
    return " | ".join(parts)


__all__ = ["_build_explain_text"]
