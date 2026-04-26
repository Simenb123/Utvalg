from __future__ import annotations

from itertools import combinations
from typing import Iterable, Sequence

from .residual_models import ResidualAccountCandidate, ResidualNearMatch


def exact_subset_sum(
    candidates: Sequence[ResidualAccountCandidate],
    target_cents: int,
    *,
    max_candidates: int = 28,
) -> tuple[ResidualAccountCandidate, ...]:
    work = list(candidates)[: max(0, int(max_candidates))]
    if target_cents == 0:
        return ()
    if not work:
        return ()

    mid = len(work) // 2
    left = work[:mid]
    right = work[mid:]
    left_sums: dict[int, tuple[int, ...]] = {}
    for mask in range(1 << len(left)):
        total = 0
        indexes: list[int] = []
        for idx, candidate in enumerate(left):
            if mask & (1 << idx):
                total += candidate.amount_cents
                indexes.append(idx)
        previous = left_sums.get(total)
        if previous is None or len(indexes) < len(previous):
            left_sums[total] = tuple(indexes)

    for mask in range(1 << len(right)):
        total = 0
        right_indexes: list[int] = []
        for idx, candidate in enumerate(right):
            if mask & (1 << idx):
                total += candidate.amount_cents
                right_indexes.append(mid + idx)
        need = int(target_cents) - total
        left_indexes = left_sums.get(need)
        if left_indexes is None:
            continue
        indexes = tuple(left_indexes) + tuple(right_indexes)
        if not indexes:
            continue
        return tuple(work[idx] for idx in indexes)
    return ()


def nearest_matches(
    candidates: Sequence[ResidualAccountCandidate],
    target_cents: int,
    *,
    max_candidates: int = 35,
    limit: int = 3,
) -> tuple[ResidualNearMatch, ...]:
    work = list(candidates)[: max(0, int(max_candidates))]
    scored: list[ResidualNearMatch] = []
    for size in (1, 2):
        for combo in combinations(work, size):
            amount = sum(candidate.amount_cents for candidate in combo)
            scored.append(
                ResidualNearMatch(
                    accounts=tuple(candidate.account for candidate in combo),
                    amount_cents=amount,
                    diff_after_cents=int(target_cents) - amount,
                )
            )
    scored.sort(key=lambda item: (abs(item.diff_after_cents), len(item.accounts), item.accounts))
    return tuple(scored[: max(0, int(limit))])


def rank_for_target(
    candidates: Iterable[ResidualAccountCandidate],
    target_cents: int,
) -> tuple[ResidualAccountCandidate, ...]:
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -int(getattr(candidate, "evidence_score", 0) or 0),
                abs(abs(candidate.amount_cents) - abs(target_cents)),
                candidate.source != "unmapped",
                candidate.account,
            ),
        )
    )


__all__ = ["exact_subset_sum", "nearest_matches", "rank_for_target"]
