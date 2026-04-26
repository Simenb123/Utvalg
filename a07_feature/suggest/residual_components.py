from __future__ import annotations

from itertools import combinations

from .residual_models import ResidualAccountCandidate, ResidualGroupScenario
from .residual_search import exact_subset_sum, nearest_matches, rank_for_target


def group_scenarios(
    open_rows: list[tuple[str, int]],
    candidates: tuple[ResidualAccountCandidate, ...],
    *,
    limit: int = 3,
) -> tuple[ResidualGroupScenario, ...]:
    if len(open_rows) < 2:
        return ()
    work_rows = sorted(open_rows, key=lambda item: (-abs(item[1]), item[0]))[:8]
    scenarios: list[ResidualGroupScenario] = []
    for size in range(2, min(3, len(work_rows)) + 1):
        for combo in combinations(work_rows, size):
            codes = tuple(code for code, _diff in combo)
            diff = sum(diff for _code, diff in combo)
            if diff == 0:
                scenarios.append(ResidualGroupScenario(codes=codes, diff_cents=diff, reason="Åpne koder nuller hverandre ut samlet."))
                continue
            ranked = rank_for_target(candidates, diff)
            exact = exact_subset_sum(ranked, diff)
            if exact:
                amount = sum(candidate.amount_cents for candidate in exact)
                scenarios.append(
                    ResidualGroupScenario(
                        codes=codes,
                        diff_cents=diff,
                        accounts=tuple(candidate.account for candidate in exact),
                        amount_cents=amount,
                        diff_after_cents=diff - amount,
                        reason="Åpne koder kan vurderes samlet som gruppe.",
                    )
                )
                continue
            near = nearest_matches(ranked, diff, limit=1)
            if near:
                best = near[0]
                scenarios.append(
                    ResidualGroupScenario(
                        codes=codes,
                        diff_cents=diff,
                        accounts=best.accounts,
                        amount_cents=best.amount_cents,
                        diff_after_cents=best.diff_after_cents,
                        reason="Gruppe gir nesten-treff, men krever vurdering.",
                    )
                )
    scenarios.sort(key=lambda item: (abs(item.diff_after_cents), not item.accounts and item.diff_cents != 0, len(item.codes), item.codes))
    return tuple(scenarios[: max(0, int(limit))])


def evidence_component_scenarios(
    open_rows: list[tuple[str, int]],
    candidates: tuple[ResidualAccountCandidate, ...],
    *,
    limit: int = 3,
) -> tuple[ResidualGroupScenario, ...]:
    diff_by_code = {code: diff for code, diff in open_rows}
    evidence_candidates = [candidate for candidate in candidates if candidate.evidence_codes and candidate.evidence_score > 0]
    if len(diff_by_code) < 2 or not evidence_candidates:
        return ()

    code_neighbors: dict[str, set[str]] = {code: set() for code in diff_by_code}
    account_neighbors: dict[str, set[str]] = {}
    candidate_by_account = {candidate.account: candidate for candidate in evidence_candidates}
    for candidate in evidence_candidates:
        codes = {code for code in candidate.evidence_codes if code in diff_by_code}
        if not codes:
            continue
        account_neighbors[candidate.account] = codes
        for code in codes:
            code_neighbors.setdefault(code, set()).add(candidate.account)

    scenarios: list[ResidualGroupScenario] = []
    seen_codes: set[str] = set()
    for start_code in sorted(code_neighbors):
        if start_code in seen_codes:
            continue
        component_codes, component_accounts = _connected_component(start_code, code_neighbors, account_neighbors)
        seen_codes.update(component_codes)
        if len(component_codes) < 2:
            continue
        scenarios.extend(_component_to_scenario(component_codes, component_accounts, diff_by_code, candidate_by_account))
    scenarios.sort(key=lambda item: (abs(item.diff_after_cents), -len(item.codes), item.codes))
    return tuple(scenarios[: max(0, int(limit))])


def merge_group_scenarios(
    evidence_scenarios: tuple[ResidualGroupScenario, ...],
    legacy_scenarios: tuple[ResidualGroupScenario, ...],
    *,
    limit: int = 3,
) -> tuple[ResidualGroupScenario, ...]:
    scenario_keys: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    merged: list[ResidualGroupScenario] = []
    for scenario in (*evidence_scenarios, *legacy_scenarios):
        key = (tuple(scenario.codes), tuple(scenario.accounts))
        if key in scenario_keys:
            continue
        scenario_keys.add(key)
        merged.append(scenario)
    return tuple(merged[: max(0, int(limit))])


def _connected_component(
    start_code: str,
    code_neighbors: dict[str, set[str]],
    account_neighbors: dict[str, set[str]],
) -> tuple[set[str], set[str]]:
    pending_codes = [start_code]
    pending_accounts: list[str] = []
    component_codes: set[str] = set()
    component_accounts: set[str] = set()
    while pending_codes or pending_accounts:
        while pending_codes:
            code = pending_codes.pop()
            if code in component_codes:
                continue
            component_codes.add(code)
            pending_accounts.extend(account for account in code_neighbors.get(code, set()) if account not in component_accounts)
        while pending_accounts:
            account = pending_accounts.pop()
            if account in component_accounts:
                continue
            component_accounts.add(account)
            pending_codes.extend(code for code in account_neighbors.get(account, set()) if code not in component_codes)
    return component_codes, component_accounts


def _component_to_scenario(
    component_codes: set[str],
    component_accounts: set[str],
    diff_by_code: dict[str, int],
    candidate_by_account: dict[str, ResidualAccountCandidate],
) -> tuple[ResidualGroupScenario, ...]:
    codes = tuple(sorted(component_codes))
    diff = sum(diff_by_code[code] for code in codes)
    component_candidates = tuple(
        sorted(
            (candidate_by_account[account] for account in component_accounts if account in candidate_by_account),
            key=lambda candidate: (-candidate.evidence_score, candidate.account),
        )
    )
    exact = exact_subset_sum(rank_for_target(component_candidates, diff), diff)
    if exact:
        amount = sum(candidate.amount_cents for candidate in exact)
        return (
            ResidualGroupScenario(
                codes=codes,
                diff_cents=diff,
                accounts=tuple(candidate.account for candidate in exact),
                amount_cents=amount,
                diff_after_cents=diff - amount,
                reason="Strukturert evidens peker på at åpne koder bør vurderes samlet.",
            ),
        )
    near = nearest_matches(rank_for_target(component_candidates, diff), diff, limit=1)
    if not near:
        return ()
    best = near[0]
    return (
        ResidualGroupScenario(
            codes=codes,
            diff_cents=diff,
            accounts=best.accounts,
            amount_cents=best.amount_cents,
            diff_after_cents=best.diff_after_cents,
            reason="Strukturert evidens gir komponentforslag, men krever vurdering.",
        ),
    )


__all__ = ["evidence_component_scenarios", "group_scenarios", "merge_group_scenarios"]
