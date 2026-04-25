from __future__ import annotations

from typing import Optional

from ..groups import a07_code_aliases
from .rulebook import RulebookRule


def _effective_target_value(target: float, rule: Optional[RulebookRule]) -> float:
    if rule is None or rule.expected_sign is None or rule.expected_sign == 0:
        return float(target)
    if rule.expected_sign > 0:
        return abs(float(target))
    return -abs(float(target))


def _a07_group_members(code: object) -> tuple[str, ...]:
    code_s = str(code or "").strip()
    prefix = "A07_GROUP:"
    if not code_s.casefold().startswith(prefix.casefold()):
        return ()
    tail = code_s[len(prefix) :]
    members: list[str] = []
    for raw in tail.replace(";", "+").replace(",", "+").split("+"):
        member = raw.strip()
        if member:
            members.append(member)
    return tuple(members)


def _lookup_rule(rulebook: dict[str, RulebookRule], code: object) -> RulebookRule | None:
    code_s = str(code or "").strip()
    if not code_s:
        return None
    for alias in a07_code_aliases(code_s):
        found = rulebook.get(alias) or rulebook.get(alias.strip()) or rulebook.get(alias.lower())
        if found is not None:
            return found
    members = _a07_group_members(code_s)
    if not members:
        return None
    member_rules = [_lookup_rule(rulebook, member) for member in members]
    member_rules = [rule for rule in member_rules if rule is not None]
    if not member_rules:
        return None

    def _uniq(values: list[object]) -> tuple:
        out: list[object] = []
        seen: set[str] = set()
        for value in values:
            key = repr(value)
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
        return tuple(out)

    rf_groups = {str(rule.rf1022_group or "").strip() for rule in member_rules if str(rule.rf1022_group or "").strip()}
    basis_values = {str(rule.basis or "").strip() for rule in member_rules if str(rule.basis or "").strip()}
    aga_values = {rule.aga_pliktig for rule in member_rules if rule.aga_pliktig is not None}
    return RulebookRule(
        label=" + ".join(str(rule.label or "").strip() or member for rule, member in zip(member_rules, members)),
        category="a07_group",
        rf1022_group=next(iter(rf_groups)) if len(rf_groups) == 1 else None,
        aga_pliktig=next(iter(aga_values)) if len(aga_values) == 1 else None,
        allowed_ranges=_uniq([rng for rule in member_rules for rng in rule.allowed_ranges]),
        keywords=_uniq([kw for rule in member_rules for kw in (rule.keywords or ())] + list(members)),
        exclude_keywords=_uniq([kw for rule in member_rules for kw in (rule.exclude_keywords or ())]),
        boost_accounts=_uniq([acct for rule in member_rules for acct in (rule.boost_accounts or ())]),
        special_add=_uniq([item for rule in member_rules for item in (rule.special_add or ())]),
        basis=next(iter(basis_values)) if len(basis_values) == 1 else None,
        expected_sign=None,
    )


__all__ = ["_a07_group_members", "_effective_target_value", "_lookup_rule"]
