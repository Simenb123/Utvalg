from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass

import pandas as pd

from a07_feature.control.data import (
    RF1022_UNKNOWN_GROUP,
    a07_code_rf1022_group,
    a07_suggestion_is_strict_auto,
)

from .control_actions import apply_accounts_to_code


AUTO_ACTION_COUNT_KEYS = (
    "safe",
    "actionable",
    "review",
    "invalid",
    "already",
    "conflict",
    "locked",
    "blocked",
)


@dataclass(frozen=True)
class AutoPlanApplyResult:
    applied: tuple[tuple[str, str], ...] = ()
    invalid: int = 0
    conflict: int = 0
    locked: int = 0

    @property
    def skipped(self) -> int:
        return self.invalid + self.conflict + self.locked


def empty_auto_action_counts() -> dict[str, int]:
    return {key: 0 for key in AUTO_ACTION_COUNT_KEYS}


def global_auto_plan_action_counts(plan: pd.DataFrame | None) -> dict[str, int]:
    counts = empty_auto_action_counts()
    if plan is None or plan.empty or "Action" not in plan.columns:
        return counts
    actions = plan["Action"].fillna("").astype(str).str.strip()
    counts["actionable"] = int((actions == "apply").sum())
    counts["safe"] = counts["actionable"] + int((actions == "already").sum())
    counts["review"] = int(actions.isin({"review", "blocked"}).sum())
    counts["blocked"] = int((actions == "blocked").sum())
    counts["invalid"] = int((actions == "invalid").sum())
    counts["already"] = int((actions == "already").sum())
    counts["conflict"] = int((actions == "conflict").sum())
    counts["locked"] = int((actions == "locked").sum())
    return counts


def _text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def rf1022_candidate_summary_counts(
    candidates: pd.DataFrame | None,
    *,
    locked_codes: set[str] | None = None,
    solved_codes: set[str] | None = None,
    current_mapping: Mapping[object, object] | None = None,
    gl_accounts: set[str] | None = None,
) -> dict[str, int]:
    counts = empty_auto_action_counts()
    if candidates is None or candidates.empty:
        return counts

    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    solved = {str(code).strip() for code in (solved_codes or set()) if str(code).strip()}
    mapping = {
        str(account).strip(): str(code).strip()
        for account, code in dict(current_mapping or {}).items()
        if str(account).strip()
    }
    gl_set = {str(account).strip() for account in (gl_accounts or set()) if str(account).strip()}

    for _, row in candidates.iterrows():
        account = _text(row.get("Konto"))
        code = _text(row.get("Kode"))
        group_id = _text(row.get("Rf1022GroupId"))
        status = _text(row.get("Forslagsstatus"))
        try:
            strict = bool(a07_suggestion_is_strict_auto(row))
        except Exception:
            strict = False
        strict = strict or status == "Trygt forslag"

        if not account or not code:
            counts["invalid"] += 1
            continue
        if not strict:
            counts["review"] += 1
            continue
        if gl_set and account not in gl_set:
            counts["invalid"] += 1
            continue
        if code in solved:
            counts["already"] += 1
            counts["safe"] += 1
            continue

        current = str(mapping.get(account) or "").strip()
        if current == code:
            counts["already"] += 1
            counts["safe"] += 1
            continue
        if current and current != code:
            counts["conflict"] += 1
            continue
        if code in locked:
            counts["locked"] += 1
            continue

        resolved_group = a07_code_rf1022_group(code)
        if resolved_group == RF1022_UNKNOWN_GROUP:
            counts["review"] += 1
            continue
        if group_id and group_id != resolved_group:
            counts["blocked"] += 1
            continue

        counts["actionable"] += 1
        counts["safe"] += 1
    return counts


def apply_rf1022_auto_plan_to_mapping(
    mapping: MutableMapping[str, str],
    plan: pd.DataFrame | None,
    *,
    effective_mapping: Mapping[object, object] | None = None,
    locked_conflicts_fn: Callable[[str, str], object] | None = None,
) -> AutoPlanApplyResult:
    if plan is None or plan.empty or "Action" not in plan.columns:
        return AutoPlanApplyResult()

    effective = {
        str(account).strip(): str(code).strip()
        for account, code in dict(effective_mapping or {}).items()
        if str(account).strip()
    }
    applied: list[tuple[str, str]] = []
    invalid = 0
    conflict = 0
    locked = 0

    candidates = plan.loc[plan["Action"].fillna("").astype(str).str.strip() == "apply"].copy()
    for _, row in candidates.iterrows():
        account = _text(row.get("Konto"))
        code = _text(row.get("Kode"))
        if not account or not code:
            invalid += 1
            continue

        current_code = str(effective.get(account) or mapping.get(account) or "").strip()
        if current_code and current_code != code:
            conflict += 1
            continue
        if locked_conflicts_fn is not None and locked_conflicts_fn(account, code):
            locked += 1
            continue

        apply_accounts_to_code(mapping, [account], code)
        effective[account] = code
        applied.append((account, code))

    return AutoPlanApplyResult(
        applied=tuple(applied),
        invalid=invalid,
        conflict=conflict,
        locked=locked,
    )


__all__ = [
    "AUTO_ACTION_COUNT_KEYS",
    "AutoPlanApplyResult",
    "apply_rf1022_auto_plan_to_mapping",
    "empty_auto_action_counts",
    "global_auto_plan_action_counts",
    "rf1022_candidate_summary_counts",
]
