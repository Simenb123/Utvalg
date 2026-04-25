from __future__ import annotations

from itertools import combinations

import pandas as pd

from .residual_models import (
    ALREADY_BALANCED,
    NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
    RESIDUAL_REVIEW_CODES,
    REVIEW_EXACT,
    SAFE_EXACT,
    SAFE_MAPPING_STATUSES,
    WEAK_MAPPING_STATUSES,
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


def _text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def _open_code_rows(a07_overview_df: pd.DataFrame | None, locked_codes: set[str]) -> list[tuple[str, int]]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return []
    rows: list[tuple[str, int]] = []
    for _, row in a07_overview_df.iterrows():
        code = _text(row.get("Kode"))
        if not code or code in locked_codes:
            continue
        diff = amount_to_cents(row.get("Diff"))
        if diff == 0:
            continue
        rows.append((code, diff))
    return rows


def _zero_diff_codes(a07_overview_df: pd.DataFrame | None) -> set[str]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return set()
    protected: set[str] = set()
    for _, row in a07_overview_df.iterrows():
        code = _text(row.get("Kode"))
        if code and amount_to_cents(row.get("Diff")) == 0:
            protected.add(code)
    return protected


def _row_amount_cents(row: pd.Series, basis_col: str) -> int:
    if "BelopAktiv" in row.index and _text(row.get("BelopAktiv")):
        return amount_to_cents(row.get("BelopAktiv"))
    preferred = _text(row.get("Kol")) or str(basis_col or "Endring")
    if preferred in row.index:
        return amount_to_cents(row.get(preferred))
    if basis_col in row.index:
        return amount_to_cents(row.get(basis_col))
    return amount_to_cents(row.get("Endring"))


def _audit_status_for_solver(row: pd.Series) -> str:
    raw_status = _text(row.get("MappingAuditRawStatus"))
    if raw_status:
        return raw_status
    return _text(row.get("MappingAuditStatus"))


def _candidate_accounts(
    control_gl_df: pd.DataFrame | None,
    *,
    effective_mapping: dict[str, str],
    basis_col: str,
    open_codes: set[str],
    protected_codes: set[str],
) -> tuple[ResidualAccountCandidate, ...]:
    if control_gl_df is None or control_gl_df.empty or "Konto" not in control_gl_df.columns:
        return ()
    candidates: list[ResidualAccountCandidate] = []
    for _, row in control_gl_df.iterrows():
        account = _text(row.get("Konto"))
        if not account:
            continue
        amount = _row_amount_cents(row, basis_col)
        if amount == 0:
            continue
        row_code = _text(row.get("Kode"))
        current_code = _text(effective_mapping.get(account)) or row_code
        audit_status = _audit_status_for_solver(row)
        if current_code in protected_codes and current_code not in open_codes:
            continue
        if current_code and audit_status in SAFE_MAPPING_STATUSES:
            continue
        if current_code and audit_status not in WEAK_MAPPING_STATUSES and current_code not in open_codes:
            continue
        source = "unmapped" if not current_code else "weak_mapping"
        candidates.append(
            ResidualAccountCandidate(
                account=account,
                name=_text(row.get("Navn")),
                amount_cents=amount,
                current_code=current_code,
                audit_status=audit_status,
                source=source,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                candidate.source != "unmapped",
                abs(candidate.amount_cents),
                candidate.account,
            ),
        )
    )


def _suspicious_accounts(
    control_gl_df: pd.DataFrame | None,
    *,
    total_open_diff_cents: int,
    effective_mapping: dict[str, str],
    basis_col: str,
    open_codes: set[str],
) -> tuple[ResidualSuspiciousAccount, ...]:
    if control_gl_df is None or control_gl_df.empty or "Konto" not in control_gl_df.columns:
        return ()
    suspects: list[ResidualSuspiciousAccount] = []
    for _, row in control_gl_df.iterrows():
        account = _text(row.get("Konto"))
        if not account:
            continue
        amount = _row_amount_cents(row, basis_col)
        if amount == 0:
            continue
        code = _text(effective_mapping.get(account)) or _text(row.get("Kode"))
        audit_status = _audit_status_for_solver(row)
        if code not in open_codes and code.casefold() != "annet" and audit_status not in {"Feil", "Uavklart", "Mistenkelig"}:
            continue
        if abs(total_open_diff_cents + amount) <= 1:
            suspects.append(
                ResidualSuspiciousAccount(
                    account=account,
                    name=_text(row.get("Navn")),
                    code=code,
                    amount_cents=amount,
                    reason="Kontoen forklarer samlet rest hvis den tas ut av de åpne kodene.",
                )
            )
    return tuple(suspects)


def _group_scenarios(
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
                scenarios.append(
                    ResidualGroupScenario(
                        codes=codes,
                        diff_cents=diff,
                        reason="Åpne koder nuller hverandre ut samlet.",
                    )
                )
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
    scenarios.sort(
        key=lambda item: (
            abs(item.diff_after_cents),
            not item.accounts and item.diff_cents != 0,
            len(item.codes),
            item.codes,
        )
    )
    return tuple(scenarios[: max(0, int(limit))])


def analyze_a07_residuals(
    a07_overview_df: pd.DataFrame | None,
    control_gl_df: pd.DataFrame | None,
    effective_mapping: dict[str, str] | None = None,
    *,
    locked_codes: set[str] | None = None,
    basis_col: str = "Endring",
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
    candidates = _candidate_accounts(
        control_gl_df,
        effective_mapping=mapping,
        basis_col=basis_col,
        open_codes=open_codes,
        protected_codes=protected_codes,
    )
    changes: list[ResidualChange] = []
    code_results: list[ResidualCodeResult] = []

    for code, diff in open_rows:
        ranked = rank_for_target(candidates, diff)
        exact = exact_subset_sum(ranked, diff)
        if exact:
            review_required = code.casefold() in RESIDUAL_REVIEW_CODES or any(item.current_code for item in exact)
            status = REVIEW_EXACT if review_required else SAFE_EXACT
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
            reason = (
                "Eksakt beløp funnet, men krever vurdering."
                if review_required
                else "Trygg eksakt helkonto-løsning funnet."
            )
            code_results.append(
                ResidualCodeResult(
                    code=code,
                    diff_cents=diff,
                    status=status,
                    exact_accounts=tuple(candidate.account for candidate in exact),
                    review_required=review_required,
                    explanation=reason,
                )
            )
            continue
        near = nearest_matches(ranked, diff)
        code_results.append(
            ResidualCodeResult(
                code=code,
                diff_cents=diff,
                status=NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
                near_matches=near,
                review_required=True,
                explanation="Ingen eksakt trygg helkonto-kombinasjon funnet.",
            )
        )

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
    suspicious = _suspicious_accounts(
        control_gl_df,
        total_open_diff_cents=total_before,
        effective_mapping=mapping,
        basis_col=basis_col,
        open_codes=open_codes,
    )
    group_scenarios = _group_scenarios(open_rows, candidates)

    if changes and all_open_codes_safe and total_after == 0:
        status = SAFE_EXACT
        auto_safe = True
        explanation = (
            f"Tryllestav fant {len(changes)} trygg(e) helkonto-endring(er). "
            f"Rest etter forslag: {cents_to_display(total_after)}."
        )
    elif any(result.status == REVIEW_EXACT for result in code_results):
        status = REVIEW_EXACT
        auto_safe = False
        explanation = "Fant eksakte beløp, men forslagene må vurderes manuelt før de kan brukes."
    elif changes:
        status = NO_SAFE_WHOLE_ACCOUNT_SOLUTION
        auto_safe = False
        explanation = (
            "Fant noen trygge deltreff, men ikke en komplett trygg helkonto-løsning. "
            f"Rest etter deltreff: {cents_to_display(total_after)}."
        )
    else:
        status = NO_SAFE_WHOLE_ACCOUNT_SOLUTION
        auto_safe = False
        explanation = (
            "Ingen trygg helkonto-løsning finnes med dagens låser og kandidater. "
            f"Samlet rest er {cents_to_display(total_before)}."
        )
    if suspicious:
        first = suspicious[0]
        explanation += f" Mistenkelig konto: {first.account} {first.name} ({cents_to_display(first.amount_cents)})."

    return ResidualAnalysis(
        status=status,
        auto_safe=auto_safe,
        changes=tuple(changes),
        total_diff_before_cents=total_before,
        total_diff_after_cents=total_after,
        affected_codes=tuple(sorted(safe_change_codes)),
        explanation=explanation,
        code_results=tuple(code_results),
        suspicious_accounts=suspicious,
        group_scenarios=group_scenarios,
        review_required=not auto_safe,
    )


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
