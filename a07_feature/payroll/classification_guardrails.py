from __future__ import annotations

from typing import Mapping

from account_profile import AccountProfile, AccountProfileSuggestion

from .classification_shared import (
    _PAYROLL_MIN_ALIAS_CONFIDENCE,
    _PAYROLL_MIN_GENERIC_CONFIDENCE,
    _PAYROLL_MIN_RULEBOOK_CONFIDENCE,
    _PAYROLL_TOKENS,
    _STRONG_BALANCE_SHEET_PAYROLL_TOKENS,
    _account_no_int,
    _clean_text,
    _has_non_payroll_operating_expense_signal,
    _has_strong_expense_payroll_signal,
    _matching_terms,
    _normalize_text_shared,
)

def _heuristic_allowed_for_account(
    *,
    account_no: str,
    account_name: str,
) -> bool:
    konto_i = _account_no_int(account_no)
    name_norm = _normalize_text_shared(account_name)
    if konto_i is None:
        return True
    if 1000 <= konto_i <= 1399:
        return False
    if 1900 <= konto_i <= 1999:
        return False
    if 2000 <= konto_i <= 2399:
        return False
    if 1400 <= konto_i <= 1799:
        return bool(_matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS))
    if 2400 <= konto_i <= 2599:
        return False
    if 2600 <= konto_i <= 2699:
        return bool(_matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS))
    if 2700 <= konto_i <= 2749:
        return False
    if 2750 <= konto_i <= 2799:
        return bool(_matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS))
    if 2900 <= konto_i <= 2999:
        return bool(_matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS))
    if 6000 <= konto_i <= 7999:
        if _has_non_payroll_operating_expense_signal(name_norm) and not _has_strong_expense_payroll_signal(name_norm):
            return False
    return True

def is_strict_auto_suggestion(suggestion: AccountProfileSuggestion | None) -> bool:
    if suggestion is None:
        return False
    if suggestion.source in {"history", "manual"}:
        return True
    reason = _clean_text(suggestion.reason)
    confidence = float(suggestion.confidence or 0.0)
    return reason.startswith("Regelbok:") and confidence >= 0.9


def is_actionable_payroll_suggestion(suggestion: AccountProfileSuggestion | None) -> bool:
    if suggestion is None:
        return False
    source = _clean_text(getattr(suggestion, "source", None))
    if source in {"history", "manual", "legacy"}:
        return True
    confidence = float(getattr(suggestion, "confidence", 0.0) or 0.0)
    reason = _clean_text(getattr(suggestion, "reason", None))
    if reason.startswith("Regelbok:") or reason == "Kode-standard":
        return confidence >= _PAYROLL_MIN_RULEBOOK_CONFIDENCE
    if reason.startswith("Navn/alias:"):
        return confidence >= _PAYROLL_MIN_ALIAS_CONFIDENCE
    if reason.startswith("Direkte RF-1022:") or reason.startswith("Direkte Flagg:"):
        lowered = reason.casefold()
        if "navn/alias:" in lowered:
            return confidence >= _PAYROLL_MIN_ALIAS_CONFIDENCE
        return confidence >= _PAYROLL_MIN_GENERIC_CONFIDENCE
    return confidence >= _PAYROLL_MIN_GENERIC_CONFIDENCE


def _has_payroll_profile_state(profile: AccountProfile | None) -> bool:
    if profile is None:
        return False
    return bool(
        _clean_text(profile.a07_code)
        or _clean_text(profile.control_group)
        or tuple(getattr(profile, "control_tags", ()) or ())
        or bool(getattr(profile, "locked", False))
    )

def payroll_relevant_for_account(
    *,
    account_no: str,
    account_name: str,
    current_profile: AccountProfile | None = None,
    suggestion_map: Mapping[str, AccountProfileSuggestion] | None = None,
) -> bool:
    if _has_payroll_profile_state(current_profile):
        return True
    if suggestion_map:
        if any(is_actionable_payroll_suggestion(suggestion) for suggestion in suggestion_map.values()):
            return True
    konto_i = _account_no_int(account_no)
    if konto_i is not None and 5000 <= konto_i <= 5999:
        return True
    name_norm = _normalize_text_shared(account_name)
    return bool(_matching_terms(name_norm, _PAYROLL_TOKENS))

def _a07_suggestion_allowed_for_account(
    *,
    account_no: str,
    account_name: str,
) -> bool:
    konto_i = _account_no_int(account_no)
    if konto_i is None:
        return _heuristic_allowed_for_account(account_no=account_no, account_name=account_name)
    if 1400 <= konto_i <= 2999:
        return False
    return _heuristic_allowed_for_account(account_no=account_no, account_name=account_name)
