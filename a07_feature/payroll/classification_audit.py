from __future__ import annotations

import pandas as pd

from account_profile import AccountProfile, AccountProfileDocument

from .classification_a07_engine import _direct_hint_code
from .classification_guardrails import _has_payroll_profile_state, is_strict_auto_suggestion
from .classification_shared import (
    PayrollSuggestionResult,
    _BANK_ACCOUNT_NAME_TOKENS,
    _EQUITY_ACCOUNT_NAME_TOKENS,
    _STRONG_BALANCE_SHEET_PAYROLL_TOKENS,
    _VAT_OR_SETTLEMENT_NAME_TOKENS,
    _account_no_int,
    _clean_text,
    _default_rulebook,
    _has_non_payroll_operating_expense_signal,
    _has_strong_expense_payroll_signal,
    _in_allowed_ranges,
    _matching_terms,
    _normalize_text_shared,
    _to_number,
)

def suspicious_saved_payroll_profile_issue(
    *,
    account_no: str,
    account_name: str,
    current_profile: AccountProfile | None = None,
) -> str | None:
    if not _has_payroll_profile_state(current_profile):
        return None

    konto_i = _account_no_int(account_no)
    name_norm = _normalize_text_shared(account_name)

    if konto_i is not None:
        if 1000 <= konto_i <= 1399:
            return "Anleggsmiddel-/immateriell konto har lagret lønnsklassifisering."
        if 1900 <= konto_i <= 1999:
            return "Bank-/kassekonto har lagret lønnsklassifisering."
        if 2000 <= konto_i <= 2399:
            return "Egenkapitalkonto har lagret lønnsklassifisering."
        if 2400 <= konto_i <= 2599 and not _matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS):
            return "Gjeldskonto uten tydelig lønnssignal har lagret lønnsklassifisering."
        if 2600 <= konto_i <= 2699 and not _matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS):
            return "Trekk-/oppgjørskonto uten tydelig lønnssignal har lagret lønnsklassifisering."
        if 2700 <= konto_i <= 2749:
            return "MVA-/oppgjørskonto har lagret lønnsklassifisering."
        if 2750 <= konto_i <= 2799 and not _matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS):
            return "Skyldig-/avgiftskonto uten tydelig lønnssignal har lagret lønnsklassifisering."
        if 2900 <= konto_i <= 2999 and not _matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS):
            return "Påløpt-/skyldigkonto uten tydelig lønnssignal har lagret lønnsklassifisering."
        if 1400 <= konto_i <= 1799 and not _matching_terms(name_norm, _STRONG_BALANCE_SHEET_PAYROLL_TOKENS):
            return "Balansekonto uten tydelig lønnssignal har lagret lønnsklassifisering."
        if 6000 <= konto_i <= 7999 and _has_non_payroll_operating_expense_signal(name_norm) and not _has_strong_expense_payroll_signal(name_norm):
            return "Ordinær driftskostnad uten tydelig lønnssignal har lagret lønnsklassifisering."

    if _matching_terms(name_norm, _BANK_ACCOUNT_NAME_TOKENS):
        return "Kontoen ser ut som bank-/kortkonto, men har lagret lønnsklassifisering."
    if _matching_terms(name_norm, _EQUITY_ACCOUNT_NAME_TOKENS):
        return "Kontoen ser ut som egenkapital, men har lagret lønnsklassifisering."
    if _matching_terms(name_norm, _VAT_OR_SETTLEMENT_NAME_TOKENS):
        return "Kontoen ser ut som MVA-/oppgjørskonto, men har lagret lønnsklassifisering."
    if _has_non_payroll_operating_expense_signal(name_norm) and not _has_strong_expense_payroll_signal(name_norm):
        return "Kontoen ser ut som ordinær driftskostnad, men har lagret lønnsklassifisering."
    current_code = _clean_text(getattr(current_profile, "a07_code", None))
    if current_code:
        rulebook = _default_rulebook()
        current_rule = rulebook.get(current_code)
        if current_rule is not None and current_rule.allowed_ranges and not _in_allowed_ranges(account_no, current_rule.allowed_ranges):
            for other_code, other_rule in rulebook.items():
                if other_code == current_code or not other_rule.allowed_ranges:
                    continue
                if not _in_allowed_ranges(account_no, other_rule.allowed_ranges):
                    continue
                other_label = _clean_text(getattr(other_rule, "label", "")) or other_code
                return f"Kontoen ligger i standardintervallet for {other_label}, ikke lagret A07-kode."

        hinted_code, hinted_score, _hint_reason = _direct_hint_code(account_name, rulebook)
        if hinted_code and hinted_code != current_code and hinted_score >= 0.9:
            hinted_rule = rulebook.get(hinted_code)
            hinted_label = _clean_text(getattr(hinted_rule, "label", "")) or hinted_code
            return f"Kontoen peker tydeligere mot {hinted_label} enn lagret A07-kode."
    return None

def profile_source_label(profile: AccountProfile | None) -> str:
    if profile is None:
        return ""
    source = _clean_text(profile.source)
    if source == "manual":
        return "Manuell"
    if source == "history":
        return "Historikk"
    if source == "legacy":
        return "Legacy"
    if source == "heuristic":
        return "Forslag"
    return source.capitalize() if source else ""


def confidence_label(value: float | None) -> str:
    if value is None:
        return ""
    try:
        return f"{float(value) * 100:.0f}%"
    except Exception:
        return ""


def strict_auto_profile_updates(result: PayrollSuggestionResult | None) -> dict[str, object]:
    if result is None or not result.suggestions:
        return {}
    fields: dict[str, object] = {}
    for field_name, suggestion in result.suggestions.items():
        if not is_strict_auto_suggestion(suggestion):
            continue
        if field_name == "a07_code" and isinstance(suggestion.value, str):
            fields["a07_code"] = str(suggestion.value or "").strip()
        elif field_name == "control_group" and isinstance(suggestion.value, str):
            fields["control_group"] = str(suggestion.value or "").strip()
        elif field_name == "control_tags" and isinstance(suggestion.value, tuple):
            fields["control_tags"] = tuple(str(tag or "").strip() for tag in suggestion.value if str(tag or "").strip())
    return fields


def rf1022_tag_totals(
    gl_df: pd.DataFrame | None,
    document: AccountProfileDocument,
    *,
    basis_col: str = "Endring",
) -> dict[str, float]:
    totals = {
        "opplysningspliktig": 0.0,
        "aga_pliktig": 0.0,
        "finansskatt_pliktig": 0.0,
    }
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return totals

    value_col = basis_col if basis_col in gl_df.columns else "Endring"
    for _, row in gl_df.iterrows():
        account_no = _clean_text(row.get("Konto"))
        if not account_no:
            continue
        profile = document.get(account_no)
        if profile is None:
            continue
        value = _to_number(row.get(value_col))
        for tag in totals:
            if tag in tuple(profile.control_tags or ()):
                totals[tag] += value
    return totals
