from __future__ import annotations

import pandas as pd

from a07_feature.control.evidence import candidate_text, candidate_tokens, normalize_candidate_evidence

from .residual_models import (
    SAFE_MAPPING_STATUSES,
    WEAK_MAPPING_STATUSES,
    ResidualAccountCandidate,
    ResidualSuspiciousAccount,
    amount_to_cents,
)


def residual_text(value: object) -> str:
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def row_amount_cents(row: pd.Series, basis_col: str) -> int:
    if "BelopAktiv" in row.index and residual_text(row.get("BelopAktiv")):
        return amount_to_cents(row.get("BelopAktiv"))
    preferred = residual_text(row.get("Kol")) or str(basis_col or "Endring")
    if preferred in row.index:
        return amount_to_cents(row.get(preferred))
    if basis_col in row.index:
        return amount_to_cents(row.get(basis_col))
    return amount_to_cents(row.get("Endring"))


def audit_status_for_solver(row: pd.Series) -> str:
    raw_status = residual_text(row.get("MappingAuditRawStatus"))
    if raw_status:
        return raw_status
    return residual_text(row.get("MappingAuditStatus"))


def suggestion_evidence_by_account(
    suggestions_df: pd.DataFrame | None,
    *,
    open_codes: set[str],
) -> dict[str, dict[str, object]]:
    if suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
        return {}
    out: dict[str, dict[str, object]] = {}
    for _, row in suggestions_df.iterrows():
        code = candidate_text(row, "Kode")
        if not code or code not in open_codes:
            continue
        accounts = candidate_tokens(row.get("ForslagKontoer"))
        if not accounts:
            continue
        evidence = normalize_candidate_evidence(row)
        guardrail = candidate_text(row, "SuggestionGuardrail").casefold()
        has_semantic = evidence.has_semantic_support
        has_amount = evidence.amount_evidence in {"exact", "within_tolerance", "near"} or evidence.within_tolerance
        if not has_semantic and not has_amount:
            continue
        score = int(has_semantic) * 2 + int(has_amount) + int(guardrail == "accepted")
        if evidence.used_rulebook or evidence.used_special_add:
            score += 1
        summary_parts: list[str] = []
        if evidence.used_rulebook:
            summary_parts.append("regelbok")
        if evidence.used_usage:
            summary_parts.append("kontobruk")
        if evidence.used_special_add:
            summary_parts.append("tilleggsregel")
        if evidence.has_name_anchor:
            summary_parts.append("navn")
        if has_amount:
            summary_parts.append(evidence.amount_evidence or "belop")
        for account in accounts:
            bucket = out.setdefault(account, {"codes": set(), "score": 0, "summary": set()})
            bucket["codes"].add(code)  # type: ignore[union-attr]
            bucket["score"] = max(int(bucket.get("score") or 0), score)
            bucket["summary"].update(summary_parts)  # type: ignore[union-attr]
    return out


def candidate_accounts(
    control_gl_df: pd.DataFrame | None,
    *,
    effective_mapping: dict[str, str],
    basis_col: str,
    open_codes: set[str],
    protected_codes: set[str],
    suggestion_evidence: dict[str, dict[str, object]] | None = None,
) -> tuple[ResidualAccountCandidate, ...]:
    if control_gl_df is None or control_gl_df.empty or "Konto" not in control_gl_df.columns:
        return ()
    candidates: list[ResidualAccountCandidate] = []
    for _, row in control_gl_df.iterrows():
        account = residual_text(row.get("Konto"))
        if not account:
            continue
        amount = row_amount_cents(row, basis_col)
        if amount == 0:
            continue
        row_code = residual_text(row.get("Kode"))
        current_code = residual_text(effective_mapping.get(account)) or row_code
        audit_status = audit_status_for_solver(row)
        if current_code in protected_codes and current_code not in open_codes:
            continue
        if current_code and audit_status in SAFE_MAPPING_STATUSES:
            continue
        if current_code and audit_status not in WEAK_MAPPING_STATUSES and current_code not in open_codes:
            continue
        support = (suggestion_evidence or {}).get(account, {})
        evidence_codes = tuple(sorted(str(code) for code in support.get("codes", set()) if str(code)))
        evidence_summary = ", ".join(sorted(str(item) for item in support.get("summary", set()) if str(item)))
        candidates.append(
            ResidualAccountCandidate(
                account=account,
                name=residual_text(row.get("Navn")),
                amount_cents=amount,
                current_code=current_code,
                audit_status=audit_status,
                source="unmapped" if not current_code else "weak_mapping",
                evidence_codes=evidence_codes,
                evidence_score=int(support.get("score") or 0),
                evidence_summary=evidence_summary,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -int(candidate.evidence_score or 0),
                candidate.source != "unmapped",
                abs(candidate.amount_cents),
                candidate.account,
            ),
        )
    )


def suspicious_accounts(
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
        account = residual_text(row.get("Konto"))
        if not account:
            continue
        amount = row_amount_cents(row, basis_col)
        if amount == 0:
            continue
        code = residual_text(effective_mapping.get(account)) or residual_text(row.get("Kode"))
        audit_status = audit_status_for_solver(row)
        if code not in open_codes and code.casefold() != "annet" and audit_status not in {"Feil", "Uavklart", "Mistenkelig"}:
            continue
        if abs(total_open_diff_cents + amount) <= 1:
            suspects.append(
                ResidualSuspiciousAccount(
                    account=account,
                    name=residual_text(row.get("Navn")),
                    code=code,
                    amount_cents=amount,
                    reason="Kontoen forklarer samlet rest hvis den tas ut av de åpne kodene.",
                )
            )
    return tuple(suspects)


__all__ = [
    "audit_status_for_solver",
    "candidate_accounts",
    "residual_text",
    "row_amount_cents",
    "suggestion_evidence_by_account",
    "suspicious_accounts",
]
