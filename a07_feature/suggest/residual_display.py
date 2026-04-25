from __future__ import annotations

from decimal import Decimal

import pandas as pd

from .residual_models import (
    NO_SAFE_WHOLE_ACCOUNT_SOLUTION,
    REVIEW_EXACT,
    SAFE_EXACT,
    SCENARIO_GROUP,
    SCENARIO_REVIEW,
    SCENARIO_SAFE_EXACT,
    SCENARIO_SPLIT,
    SCENARIO_SUSPICIOUS,
    ResidualAnalysis,
    cents_to_display,
)


RESIDUAL_SUGGESTION_SOURCE = "residual_solver"


def _amount(cents: int) -> Decimal:
    return Decimal(int(cents)) / Decimal(100)


def _accounts_raw_text(accounts: tuple[str, ...]) -> str:
    return ",".join(str(account).strip() for account in accounts if str(account).strip())


def _accounts_text(accounts: tuple[str, ...], *, limit: int = 3) -> str:
    items = [str(account).strip() for account in accounts if str(account).strip()]
    if not items:
        return ""
    if limit > 0 and len(items) > limit:
        preview = ", ".join(items[:limit])
        return f"{preview} +{len(items) - limit}"
    return ", ".join(items)


def _status_for_exact(result_status: str, *, review_required: bool, auto_safe: bool, code: str) -> tuple[str, str, str]:
    if result_status == SAFE_EXACT and auto_safe and not review_required:
        return SCENARIO_SAFE_EXACT, "accepted", "Trygg helkonto-løsning"
    if str(code or "").strip().casefold() == "annet":
        return SCENARIO_REVIEW, "review", "Treffer beløp, men kode er annet"
    if review_required or result_status == REVIEW_EXACT:
        return SCENARIO_REVIEW, "review", "Treffer beløp, krever vurdering"
    return SCENARIO_REVIEW, "review", "Trygt deltreff, men ikke komplett"


def _base_row(
    *,
    code: str,
    accounts: tuple[str, ...],
    a07_cents: int | None,
    gl_cents: int | None,
    diff_cents: int | None,
    status: str,
    guardrail: str,
    reason: str,
    action: str,
    combo_size: int,
    within_tolerance: bool,
    score: float,
) -> dict[str, object]:
    return {
        "Kode": str(code or "").strip(),
        "KodeNavn": str(code or "").strip(),
        "Basis": "Residual",
        "A07_Belop": "" if a07_cents is None else _amount(a07_cents),
        "ForslagKontoer": _accounts_raw_text(accounts),
        "ForslagVisning": _accounts_text(accounts),
        "GL_Sum": "" if gl_cents is None else _amount(gl_cents),
        "Diff": "" if diff_cents is None else _amount(diff_cents),
        "Score": score,
        "ComboSize": combo_size,
        "WithinTolerance": within_tolerance,
        "Explain": reason,
        "HitTokens": "",
        "HistoryAccounts": "",
        "Forslagsstatus": status,
        "HvorforKort": reason,
        "SuggestionGuardrail": guardrail,
        "SuggestionGuardrailReason": reason,
        "SuggestionSource": RESIDUAL_SUGGESTION_SOURCE,
        "ResidualAction": action,
        "UsedResidual": True,
        "AmountEvidence": "exact" if within_tolerance else "near",
    }


def residual_analysis_to_suggestions_df(analysis: ResidualAnalysis | None) -> pd.DataFrame:
    if analysis is None:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []

    for suspect in tuple(getattr(analysis, "suspicious_accounts", ()) or ()):
        account = str(getattr(suspect, "account", "") or "").strip()
        name = str(getattr(suspect, "name", "") or "").strip()
        code = str(getattr(suspect, "code", "") or "").strip()
        display = f"{account} {name}".strip()
        reason = "Forklarer samlet rest"
        row = _base_row(
            code=code,
            accounts=(account,) if account else (),
            a07_cents=None,
            gl_cents=int(getattr(suspect, "amount_cents", 0) or 0),
            diff_cents=int(getattr(analysis, "total_diff_before_cents", 0) or 0),
            status=SCENARIO_SUSPICIOUS,
            guardrail="review",
            reason=reason,
            action="suspicious_residual",
            combo_size=1 if account else 0,
            within_tolerance=False,
            score=0.0,
        )
        row["ForslagVisning"] = display or row["ForslagVisning"]
        row["Explain"] = f"{reason}: {cents_to_display(int(getattr(suspect, 'amount_cents', 0) or 0))}"
        rows.append(row)

    for scenario in tuple(getattr(analysis, "group_scenarios", ()) or ()):
        codes = tuple(str(code).strip() for code in getattr(scenario, "codes", ()) if str(code).strip())
        accounts = tuple(str(account).strip() for account in getattr(scenario, "accounts", ()) if str(account).strip())
        if not codes:
            continue
        code_text = " + ".join(codes)
        reason = str(getattr(scenario, "reason", "") or "Vurder kodene samlet som gruppe.")
        rows.append(
            _base_row(
                code=code_text,
                accounts=accounts,
                a07_cents=int(getattr(scenario, "diff_cents", 0) or 0),
                gl_cents=int(getattr(scenario, "amount_cents", 0) or 0) if accounts else None,
                diff_cents=int(getattr(scenario, "diff_after_cents", 0) or 0),
                status=SCENARIO_GROUP,
                guardrail="review",
                reason=reason,
                action="group_review",
                combo_size=max(len(accounts), len(codes)),
                within_tolerance=not bool(getattr(scenario, "diff_after_cents", 0) or 0),
                score=0.0,
            )
        )
        rows[-1]["ResidualGroupCodes"] = ",".join(codes)
        rows[-1]["ResidualGroupAccounts"] = _accounts_raw_text(accounts)
        rows[-1]["ForslagVisning"] = f"Gruppe: {_accounts_text(codes, limit=2)}"
        if accounts:
            rows[-1]["Explain"] = f"{reason} Kontoer: {_accounts_text(accounts, limit=8)}."
        rows[-1]["HvorforKort"] = "Opprett gruppeforslag"

    for result in tuple(getattr(analysis, "code_results", ()) or ()):
        code = str(getattr(result, "code", "") or "").strip()
        diff_cents = int(getattr(result, "diff_cents", 0) or 0)
        exact_accounts = tuple(str(account).strip() for account in getattr(result, "exact_accounts", ()) if str(account).strip())
        if exact_accounts:
            status, guardrail, reason = _status_for_exact(
                str(getattr(result, "status", "") or ""),
                review_required=bool(getattr(result, "review_required", False)),
                auto_safe=bool(getattr(analysis, "auto_safe", False)),
                code=code,
            )
            rows.append(
                _base_row(
                    code=code,
                    accounts=exact_accounts,
                    a07_cents=diff_cents,
                    gl_cents=diff_cents,
                    diff_cents=0,
                    status=status,
                    guardrail=guardrail,
                    reason=reason,
                    action="exact_review" if guardrail != "accepted" else "safe_exact",
                    combo_size=len(exact_accounts),
                    within_tolerance=True,
                    score=1.0,
                )
            )
            continue

        near_matches = tuple(getattr(result, "near_matches", ()) or ())
        if near_matches:
            for near in near_matches:
                accounts = tuple(str(account).strip() for account in getattr(near, "accounts", ()) if str(account).strip())
                rows.append(
                    _base_row(
                        code=code,
                        accounts=accounts,
                        a07_cents=diff_cents,
                        gl_cents=int(getattr(near, "amount_cents", 0) or 0),
                        diff_cents=int(getattr(near, "diff_after_cents", 0) or 0),
                        status=SCENARIO_SPLIT,
                        guardrail="review",
                        reason="Nesten-treff",
                        action="near_review",
                        combo_size=len(accounts),
                        within_tolerance=False,
                        score=0.0,
                    )
                )
            continue

        if str(getattr(result, "status", "") or "") == NO_SAFE_WHOLE_ACCOUNT_SOLUTION:
            rows.append(
                _base_row(
                    code=code,
                    accounts=(),
                    a07_cents=diff_cents,
                    gl_cents=None,
                    diff_cents=diff_cents,
                    status=SCENARIO_SPLIT,
                    guardrail="review",
                    reason="Ingen helkonto-kombinasjon",
                    action="manual_split_required",
                    combo_size=0,
                    within_tolerance=False,
                    score=0.0,
                )
            )

    return pd.DataFrame(rows)


def merge_residual_suggestions(
    suggestions_df: pd.DataFrame | None,
    residual_df: pd.DataFrame | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if isinstance(suggestions_df, pd.DataFrame) and not suggestions_df.empty:
        base = suggestions_df.copy(deep=True)
        if "SuggestionSource" in base.columns:
            base = base.loc[base["SuggestionSource"].fillna("").astype(str) != RESIDUAL_SUGGESTION_SOURCE].copy()
    else:
        base = pd.DataFrame()
    base = base.reset_index(drop=True)

    if residual_df is None or residual_df.empty:
        return base, pd.DataFrame()

    residual = residual_df.copy(deep=True)
    for column in base.columns:
        if column not in residual.columns:
            residual[column] = ""
    for column in residual.columns:
        if column not in base.columns:
            base[column] = ""
    residual = residual[list(base.columns)]
    start = len(base.index)
    combined = pd.concat([base, residual], ignore_index=True)
    review_rows = combined.iloc[start:].copy()
    return combined, review_rows


def residual_review_summary(analysis: ResidualAnalysis | None, row_count: int) -> str:
    if analysis is None:
        return "Tryllestav fant ingen analyse."
    suspicious = tuple(getattr(analysis, "suspicious_accounts", ()) or ())
    if suspicious:
        first = suspicious[0]
        account = str(getattr(first, "account", "") or "").strip()
        return f"Ingen trygg 0-diff-løsning. Mistenkelig konto: {account}."
    if row_count:
        return f"Ingen trygg 0-diff-løsning. {row_count} funn må vurderes."
    explanation = str(getattr(analysis, "explanation", "") or "").strip()
    return explanation or "Ingen trygg 0-diff-løsning."


__all__ = [
    "RESIDUAL_SUGGESTION_SOURCE",
    "merge_residual_suggestions",
    "residual_analysis_to_suggestions_df",
    "residual_review_summary",
]
