from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from .matching_shared import (
    _family_label,
    _normalize_semantic_text,
    _parse_konto_tokens,
    _safe_float,
    build_account_name_lookup,
    format_accounts_with_names,
    infer_semantic_family,
)


def _refund_has_specific_support(row: pd.Series) -> bool:
    account_tokens = set(_parse_konto_tokens(row.get("ForslagKontoer")))
    if "5800" in account_tokens:
        return True
    text_parts = (
        row.get("ForslagVisning"),
        row.get("HitTokens"),
        row.get("Explain"),
    )
    text = _normalize_semantic_text(" ".join(str(part or "") for part in text_parts))
    specific_tokens = (
        "nav",
        "sykepenger",
        "sykepenge",
        "foreldrepenger",
        "foreldrepenge",
        "svangerskapspenger",
    )
    return any(token in text for token in specific_tokens)


def _is_generic_refund_suggestion(row: pd.Series) -> bool:
    code_text = _normalize_semantic_text(
        " ".join(
            part
            for part in (
                str(row.get("Kode") or "").strip(),
                str(row.get("KodeNavn") or row.get("Navn") or "").strip(),
            )
            if part
        )
    )
    if "sumavgiftsgrunnlagrefusjon" not in code_text and "refusjon" not in code_text:
        return False
    return not _refund_has_specific_support(row)


def _row_has_name_anchor(row: pd.Series) -> bool:
    return bool(str(row.get("HitTokens") or "").strip()) or "navnetreff" in str(row.get("AnchorSignals") or "").lower()


def _row_has_anchor(row: pd.Series) -> bool:
    return any(
        (
            bool(row.get("UsedHistory", False)),
            bool(row.get("UsedRulebook", False)),
            bool(row.get("UsedUsage", False)),
            _row_has_name_anchor(row),
        )
    )


def _row_candidate_family(row: pd.Series) -> str:
    text_parts = [
        str(row.get("ForslagVisning") or "").strip(),
        str(row.get("HistoryAccountsVisning") or "").strip(),
        str(row.get("HitTokens") or "").strip(),
        str(row.get("Explain") or "").strip(),
    ]
    text = " ".join(part for part in text_parts if part)
    return infer_semantic_family(text)


def _row_flag(row: pd.Series, name: str, *, explain_token: str | None = None) -> bool:
    try:
        if name in row.index:
            raw = row.get(name)
            if raw is not None and not (isinstance(raw, float) and pd.isna(raw)):
                return bool(raw)
    except Exception:
        pass
    if explain_token:
        explain = str(row.get("Explain", "") or "").lower()
        return explain_token in explain
    return False


def classify_suggestion_guardrail(row: pd.Series | None) -> tuple[str, str]:
    if row is None:
        return "", ""

    expected_family = infer_semantic_family(
        " ".join(
            part
            for part in (
                str(row.get("Kode") or "").strip(),
                str(row.get("KodeNavn") or row.get("Navn") or "").strip(),
            )
            if part
        )
    )
    candidate_family = _row_candidate_family(row)
    has_anchor = _row_has_anchor(row)
    amount_evidence = str(row.get("AmountEvidence") or "").strip().lower()
    within_tolerance = bool(row.get("WithinTolerance", False))
    family_conflict = bool(expected_family and candidate_family and expected_family != candidate_family)
    suggestion_text = _normalize_semantic_text(row.get("ForslagVisning"))
    has_descriptive_name = any(char.isalpha() for char in suggestion_text)

    if family_conflict and amount_evidence in {"exact", "within_tolerance", "near"} and not has_anchor:
        return "blocked", f"Konflikt i kontonavn ({_family_label(candidate_family)})"
    if expected_family and not candidate_family and amount_evidence in {"exact", "within_tolerance", "near"} and not has_anchor:
        if has_descriptive_name:
            return "blocked", "Konflikt i kontonavn"
    if within_tolerance and _is_generic_refund_suggestion(row):
        return "review", "Generisk refusjon uten NAV/sykepenger/foreldrepenger"
    if within_tolerance and has_anchor:
        if bool(row.get("UsedHistory", False)):
            return "accepted", "Treff paa historikk"
        if bool(row.get("UsedRulebook", False)):
            return "accepted", "Treff paa regelbok"
        if bool(row.get("UsedUsage", False)):
            return "accepted", "Treff paa kontobruk"
        if _row_has_name_anchor(row):
            return "accepted", "Treff paa navn"
        return "accepted", "God kandidat"
    if family_conflict:
        return "review", f"Vurder familiekonflikt ({_family_label(candidate_family)})"
    if not has_anchor and amount_evidence in {"exact", "within_tolerance", "near"}:
        return "review", "Belop uten stotte"
    if bool(row.get("UsedHistory", False)):
        return "review", "Treff paa historikk"
    if bool(row.get("UsedRulebook", False)):
        return "review", "Treff paa regelbok"
    if bool(row.get("UsedUsage", False)):
        return "review", "Treff paa kontobruk"
    if _row_has_name_anchor(row):
        return "review", "Treff paa navn"
    return "review", "Maa vurderes"


def evaluate_current_mapping_suspicion(
    *,
    code: object,
    code_name: object,
    current_accounts: Sequence[object],
    history_accounts: Sequence[object],
    gl_df: pd.DataFrame,
    profile_state: Mapping[str, object] | None = None,
    account_name_lookup: Mapping[str, object] | None = None,
) -> tuple[bool, str]:
    current = [str(account).strip() for account in (current_accounts or ()) if str(account).strip()]
    if not current:
        return False, ""

    expected_family = infer_semantic_family(f"{str(code or '').strip()} {str(code_name or '').strip()}")
    if not expected_family:
        return False, ""

    lookup = account_name_lookup if account_name_lookup is not None else build_account_name_lookup(gl_df)
    mapped_names = [str(lookup.get(account) or "").strip() for account in current]
    mapped_families = {
        infer_semantic_family(f"{account} {lookup.get(account, '')}")
        for account in current
        if infer_semantic_family(f"{account} {lookup.get(account, '')}")
    }
    history = {str(account).strip() for account in (history_accounts or ()) if str(account).strip()}
    has_history_support = bool(history and history == set(current))
    profile_source = str((profile_state or {}).get("source") or "").strip().lower()
    has_profile_support = profile_source in {"history", "rulebook"}
    if has_history_support or has_profile_support:
        return False, ""

    if not mapped_families:
        if any(mapped_names):
            return True, f"Forventer {_family_label(expected_family)}, men fant ingen tydelig match i kontonavn"
        return False, ""
    if expected_family in mapped_families:
        return False, ""

    mapped_label = ", ".join(sorted(_family_label(family) for family in mapped_families))
    return True, f"Forventer {_family_label(expected_family)}, men fant {mapped_label}"


def _backfill_evidence_fields(work: pd.DataFrame) -> None:
    def _str_col(name: str) -> pd.Series:
        if name in work.columns:
            return work[name].fillna("").astype(str)
        return pd.Series([""] * len(work), index=work.index)

    def _bool_col(name: str) -> pd.Series:
        if name in work.columns:
            return work[name].fillna(False).astype(bool)
        return pd.Series([False] * len(work), index=work.index)

    explain_lower = _str_col("Explain").str.lower()
    history_nonempty = _str_col("HistoryAccounts").str.strip().ne("")
    hits_nonempty = _str_col("HitTokens").str.strip().ne("")

    if "UsedHistory" not in work.columns:
        work["UsedHistory"] = history_nonempty
    else:
        work["UsedHistory"] = work["UsedHistory"].fillna(False).astype(bool)

    if "UsedRulebook" not in work.columns:
        work["UsedRulebook"] = explain_lower.str.contains("regel=", regex=False)
    else:
        work["UsedRulebook"] = work["UsedRulebook"].fillna(False).astype(bool)

    if "UsedUsage" not in work.columns:
        work["UsedUsage"] = explain_lower.str.contains("bruk=", regex=False)
    else:
        work["UsedUsage"] = work["UsedUsage"].fillna(False).astype(bool)

    if "UsedSpecialAdd" not in work.columns:
        work["UsedSpecialAdd"] = explain_lower.str.contains("special_add", regex=False)
    else:
        work["UsedSpecialAdd"] = work["UsedSpecialAdd"].fillna(False).astype(bool)

    if "UsedResidual" not in work.columns:
        work["UsedResidual"] = False
    else:
        work["UsedResidual"] = work["UsedResidual"].fillna(False).astype(bool)

    if "AmountDiffAbs" not in work.columns:
        if "Diff" in work.columns:
            work["AmountDiffAbs"] = work["Diff"].apply(lambda v: abs(_safe_float(v)))
        else:
            work["AmountDiffAbs"] = 0.0
    else:
        work["AmountDiffAbs"] = work["AmountDiffAbs"].apply(_safe_float)

    if "AmountEvidence" not in work.columns:
        def _derive_evidence(row: pd.Series) -> str:
            diff_abs = _safe_float(row.get("AmountDiffAbs"))
            if diff_abs <= 0.01 and bool(row.get("WithinTolerance", False)):
                return "exact"
            if bool(row.get("WithinTolerance", False)):
                return "within_tolerance"
            if _safe_float(row.get("Score")) >= 0.70:
                return "near"
            return "weak"

        work["AmountEvidence"] = [_derive_evidence(row) for _, row in work.iterrows()]
    else:
        work["AmountEvidence"] = work["AmountEvidence"].fillna("").astype(str)

    if "AnchorSignals" not in work.columns:
        signals: list[str] = []
        for idx in work.index:
            parts: list[str] = []
            if bool(hits_nonempty.get(idx, False)):
                parts.append("navnetreff")
            if bool(work.at[idx, "UsedUsage"]):
                parts.append("kontobruk")
            if bool(history_nonempty.get(idx, False)):
                parts.append("historikk")
            if bool(work.at[idx, "UsedSpecialAdd"]):
                parts.append("special_add")
            signals.append(",".join(parts))
        work["AnchorSignals"] = signals
    else:
        work["AnchorSignals"] = work["AnchorSignals"].fillna("").astype(str)


def decorate_suggestions_for_display(suggestions_df: pd.DataFrame, gl_df: pd.DataFrame) -> pd.DataFrame:
    if suggestions_df is None:
        return pd.DataFrame()
    if suggestions_df.empty:
        work = suggestions_df.copy()
        if "ForslagVisning" not in work.columns:
            work["ForslagVisning"] = ""
        if "HistoryAccountsVisning" not in work.columns:
            work["HistoryAccountsVisning"] = ""
        if "SuggestionGuardrail" not in work.columns:
            work["SuggestionGuardrail"] = ""
        if "SuggestionGuardrailReason" not in work.columns:
            work["SuggestionGuardrailReason"] = ""
        return work

    account_names = build_account_name_lookup(gl_df)
    work = suggestions_df.copy()
    if "ForslagKontoer" in work.columns:
        work["ForslagVisning"] = work["ForslagKontoer"].apply(
            lambda value: format_accounts_with_names(value, account_names=account_names)
        )
    elif "ForslagVisning" not in work.columns:
        work["ForslagVisning"] = ""
    if "HistoryAccounts" in work.columns:
        work["HistoryAccountsVisning"] = work["HistoryAccounts"].apply(
            lambda value: format_accounts_with_names(value, account_names=account_names)
        )
    elif "HistoryAccountsVisning" not in work.columns:
        work["HistoryAccountsVisning"] = ""
    _backfill_evidence_fields(work)
    guardrails = [classify_suggestion_guardrail(row) for _, row in work.iterrows()]
    work["SuggestionGuardrail"] = [guardrail for guardrail, _reason in guardrails]
    work["SuggestionGuardrailReason"] = [reason for _guardrail, reason in guardrails]

    from .matching_display import build_suggestion_reason_label, build_suggestion_status_label

    work["Forslagsstatus"] = [build_suggestion_status_label(row) for _, row in work.iterrows()]
    work["HvorforKort"] = [build_suggestion_reason_label(row) for _, row in work.iterrows()]
    return work


__all__ = [
    "_backfill_evidence_fields",
    "_is_generic_refund_suggestion",
    "_refund_has_specific_support",
    "_row_flag",
    "_row_has_anchor",
    "_row_has_name_anchor",
    "classify_suggestion_guardrail",
    "decorate_suggestions_for_display",
    "evaluate_current_mapping_suspicion",
]
