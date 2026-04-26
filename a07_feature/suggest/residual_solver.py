from __future__ import annotations

import pandas as pd

from .residual_candidates import (
    candidate_accounts,
    residual_text,
    suggestion_evidence_by_account,
    suspicious_accounts,
)
from .residual_components import evidence_component_scenarios, group_scenarios, merge_group_scenarios
from .residual_models import (
    ALREADY_BALANCED,
    NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
    RESIDUAL_REVIEW_CODES,
    REVIEW_EXACT,
    SAFE_EXACT,
    ResidualAccountCandidate,
    ResidualAnalysis,
    ResidualChange,
    ResidualCodeResult,
    ResidualGroupScenario,
    ResidualNearMatch,
    ResidualSuspiciousAccount,
    amount_to_cents,
    cents_to_display,
)
from .residual_search import exact_subset_sum, nearest_matches, rank_for_target


def _open_code_rows(a07_overview_df: pd.DataFrame | None, locked_codes: set[str]) -> list[tuple[str, int]]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return []
    rows: list[tuple[str, int]] = []
    for _, row in a07_overview_df.iterrows():
        code = residual_text(row.get("Kode"))
        if not code or code in locked_codes:
            continue
        diff = amount_to_cents(row.get("Diff"))
        if diff != 0:
            rows.append((code, diff))
    return rows


def _zero_diff_codes(a07_overview_df: pd.DataFrame | None) -> set[str]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return set()
    protected: set[str] = set()
    for _, row in a07_overview_df.iterrows():
        code = residual_text(row.get("Kode"))
        if code and amount_to_cents(row.get("Diff")) == 0:
            protected.add(code)
    return protected


def _exact_requires_review(
    *,
    code: str,
    exact: tuple[ResidualAccountCandidate, ...],
    has_suggestion_evidence: bool,
) -> bool:
    if code.casefold() in RESIDUAL_REVIEW_CODES:
        return True
    if any(item.current_code for item in exact):
        return True
    if has_suggestion_evidence:
        return any(code not in set(candidate.evidence_codes) for candidate in exact)
    return False


def _code_result_for_exact(
    *,
    code: str,
    diff: int,
    exact: tuple[ResidualAccountCandidate, ...],
    review_required: bool,
) -> tuple[ResidualCodeResult, tuple[ResidualChange, ...]]:
    status = REVIEW_EXACT if review_required else SAFE_EXACT
    changes: list[ResidualChange] = []
    if not review_required:
        for candidate in exact:
            changes.append(
                ResidualChange(
                    account=candidate.account,
                    from_code=candidate.current_code,
                    to_code=code,
                    amount_cents=candidate.amount_cents,
                    reason="Eksakt residualtreff uten å flytte trygg mapping.",
                )
            )
    reason = "Eksakt beløp funnet, men krever vurdering." if review_required else "Trygg eksakt helkonto-løsning funnet."
    return (
        ResidualCodeResult(
            code=code,
            diff_cents=diff,
            status=status,
            exact_accounts=tuple(candidate.account for candidate in exact),
            review_required=review_required,
            explanation=reason,
        ),
        tuple(changes),
    )


def _analysis_status_text(
    *,
    changes: tuple[ResidualChange, ...],
    code_results: tuple[ResidualCodeResult, ...],
    total_before: int,
    total_after: int,
    all_open_codes_safe: bool,
) -> tuple[str, bool, str]:
    if changes and all_open_codes_safe and total_after == 0:
        return (
            SAFE_EXACT,
            True,
            f"Tryllestav fant {len(changes)} trygg(e) helkonto-endring(er). Rest etter forslag: {cents_to_display(total_after)}.",
        )
    if any(result.status == REVIEW_EXACT for result in code_results):
        return REVIEW_EXACT, False, "Fant eksakte beløp, men forslagene må vurderes manuelt før de kan brukes."
    if changes:
        return (
            NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
            False,
            "Fant noen trygge deltreff, men ikke en komplett trygg helkonto-løsning. "
            f"Rest etter deltreff: {cents_to_display(total_after)}.",
        )
    return (
        NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
        False,
        f"Ingen trygg helkonto-løsning finnes med dagens låser og kandidater. Samlet rest er {cents_to_display(total_before)}.",
    )


def analyze_a07_residuals(
    a07_overview_df: pd.DataFrame | None,
    control_gl_df: pd.DataFrame | None,
    effective_mapping: dict[str, str] | None = None,
    *,
    locked_codes: set[str] | None = None,
    basis_col: str = "Endring",
    suggestions_df: pd.DataFrame | None = None,
) -> ResidualAnalysis:
    mapping = {str(k).strip(): str(v).strip() for k, v in (effective_mapping or {}).items() if str(k).strip()}
    protected_codes = set(locked_codes or set()) | _zero_diff_codes(a07_overview_df)
    open_rows = _open_code_rows(a07_overview_df, protected_codes)
    if not open_rows:
        return ResidualAnalysis(
            status=ALREADY_BALANCED,
            auto_safe=False,
            changes=(),
            total_diff_before_cents=0,
            total_diff_after_cents=0,
            affected_codes=(),
            explanation="Ingen åpne A07-differanser å analysere.",
            code_results=(),
        )

    open_codes = {code for code, _diff in open_rows}
    total_before = sum(diff for _code, diff in open_rows)
    suggestion_evidence = suggestion_evidence_by_account(suggestions_df, open_codes=open_codes)
    candidates = candidate_accounts(
        control_gl_df,
        effective_mapping=mapping,
        basis_col=basis_col,
        open_codes=open_codes,
        protected_codes=protected_codes,
        suggestion_evidence=suggestion_evidence,
    )
    changes, code_results = _solve_open_codes(open_rows, candidates, has_suggestion_evidence=bool(suggestion_evidence))
    total_after, safe_change_codes, all_open_codes_safe = _safe_result_totals(total_before, changes, code_results)
    suspicious = suspicious_accounts(
        control_gl_df,
        total_open_diff_cents=total_before,
        effective_mapping=mapping,
        basis_col=basis_col,
        open_codes=open_codes,
    )
    scenarios = merge_group_scenarios(
        evidence_component_scenarios(open_rows, candidates),
        group_scenarios(open_rows, candidates),
    )
    status, auto_safe, explanation = _analysis_status_text(
        changes=changes,
        code_results=code_results,
        total_before=total_before,
        total_after=total_after,
        all_open_codes_safe=all_open_codes_safe,
    )
    if suspicious:
        first = suspicious[0]
        explanation += f" Mistenkelig konto: {first.account} {first.name} ({cents_to_display(first.amount_cents)})."

    return ResidualAnalysis(
        status=status,
        auto_safe=auto_safe,
        changes=changes,
        total_diff_before_cents=total_before,
        total_diff_after_cents=total_after,
        affected_codes=tuple(sorted(safe_change_codes)),
        explanation=explanation,
        code_results=code_results,
        suspicious_accounts=suspicious,
        group_scenarios=scenarios,
        review_required=not auto_safe,
    )


def _solve_open_codes(
    open_rows: list[tuple[str, int]],
    candidates: tuple[ResidualAccountCandidate, ...],
    *,
    has_suggestion_evidence: bool,
) -> tuple[tuple[ResidualChange, ...], tuple[ResidualCodeResult, ...]]:
    changes: list[ResidualChange] = []
    code_results: list[ResidualCodeResult] = []
    for code, diff in open_rows:
        ranked = rank_for_target(candidates, diff)
        exact = exact_subset_sum(ranked, diff)
        if exact:
            result, result_changes = _code_result_for_exact(
                code=code,
                diff=diff,
                exact=exact,
                review_required=_exact_requires_review(code=code, exact=exact, has_suggestion_evidence=has_suggestion_evidence),
            )
            code_results.append(result)
            changes.extend(result_changes)
            continue
        code_results.append(
            ResidualCodeResult(
                code=code,
                diff_cents=diff,
                status=NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
                near_matches=nearest_matches(ranked, diff),
                review_required=True,
                explanation="Ingen eksakt trygg helkonto-kombinasjon funnet.",
            )
        )
    return tuple(changes), tuple(code_results)


def _safe_result_totals(
    total_before: int,
    changes: tuple[ResidualChange, ...],
    code_results: tuple[ResidualCodeResult, ...],
) -> tuple[int, set[str], bool]:
    solved_diffs = {
        result.code: result.diff_cents
        for result in code_results
        if result.status == SAFE_EXACT and any(change.to_code == result.code for change in changes)
    }
    total_after = total_before - sum(solved_diffs.values())
    safe_change_codes = {change.to_code for change in changes}
    all_open_codes_safe = bool(code_results) and all(
        result.status == SAFE_EXACT and result.code in safe_change_codes
        for result in code_results
    )
    return total_after, safe_change_codes, all_open_codes_safe


__all__ = [
    "ALREADY_BALANCED",
    "NO_SAFE_WHOLE_ACCOUNT_SOLUTION",
    "REVIEW_EXACT",
    "SAFE_EXACT",
    "ResidualAccountCandidate",
    "ResidualAnalysis",
    "ResidualChange",
    "ResidualCodeResult",
    "ResidualGroupScenario",
    "ResidualNearMatch",
    "ResidualSuspiciousAccount",
    "amount_to_cents",
    "analyze_a07_residuals",
    "cents_to_display",
    "exact_subset_sum",
]
