from __future__ import annotations

from typing import Mapping

from a07_feature.suggest.api import AccountUsageFeatures, score_usage_signal
from a07_feature.suggest.rulebook import RulebookRule, load_rulebook
from account_profile import AccountProfile, AccountProfileSuggestion

from .classification_guardrails import _a07_suggestion_allowed_for_account
from .classification_shared import (
    _DIRECT_HINT_SCORES,
    _account_no_int,
    _clean_text,
    _code_tokens_for_rule,
    _matching_terms,
    _normalize_text_shared,
    _sign,
)

def _score_rule_match(
    *,
    code: str,
    account_no: str,
    account_name: str,
    movement: float,
    rule: RulebookRule,
    usage: AccountUsageFeatures | None = None,
    historical_accounts: set[str] | None = None,
) -> tuple[float, str | None]:
    konto_i = _account_no_int(account_no)
    name_norm = _normalize_text_shared(account_name)
    reason_parts: list[str] = []
    score = 0.0

    in_range = False
    if konto_i is not None and rule.allowed_ranges:
        in_range = any(start <= konto_i <= end for start, end in rule.allowed_ranges)
        if in_range:
            score += 0.38
            reason_parts.append("konto-intervall")

    if konto_i is not None and rule.boost_accounts and konto_i in rule.boost_accounts:
        score = max(score, 0.98)
        reason_parts.append("eksplisitt kontotreff")

    keyword_hits = _matching_terms(name_norm, rule.keywords)
    if keyword_hits:
        score += min(0.52, 0.22 + 0.11 * len(keyword_hits))
        reason_parts.append(f"navn ({', '.join(keyword_hits[:2])})")

    negative_hits = _matching_terms(name_norm, tuple(rule.exclude_keywords or ()))
    if negative_hits:
        if not in_range and not (konto_i is not None and rule.boost_accounts and konto_i in rule.boost_accounts):
            return 0.0, None
        score -= min(0.55, 0.22 + 0.08 * len(negative_hits))
        reason_parts.append(f"blokkerer ({', '.join(negative_hits[:2])})")

    if rule.expected_sign in (-1, 1) and movement:
        if _sign(movement) == int(rule.expected_sign):
            score += 0.04
            reason_parts.append("beløp/sign")
        else:
            score -= 0.08

    usage_score, usage_reasons = score_usage_signal(
        code_tokens=_code_tokens_for_rule(code, rule),
        rule=rule,
        usage=usage,
        historical_accounts=historical_accounts,
    )
    if usage_score > 0:
        score += min(0.24, 0.24 * usage_score)
        for marker in usage_reasons:
            if marker == "periodisitet":
                reason_parts.append("periodisitet")
            elif marker.startswith("tekst:"):
                reason_parts.append(marker.replace("tekst:", "tekst ("))
            else:
                reason_parts.append(marker)

    if score <= 0:
        return 0.0, None
    score = max(0.0, min(0.99, score))
    if not reason_parts:
        return score, "Regelbok"
    cleaned_reasons: list[str] = []
    for item in reason_parts:
        text = str(item or "").strip()
        if not text:
            continue
        if text.startswith("tekst (") and not text.endswith(")"):
            text = text + ")"
        if text not in cleaned_reasons:
            cleaned_reasons.append(text)
    return score, f"Regelbok: {', '.join(cleaned_reasons)}"

def _direct_hint_code(account_name: str, rulebook: Mapping[str, RulebookRule] | None) -> tuple[str | None, float, str | None]:
    name_norm = _normalize_text_shared(account_name)
    best_code = None
    best_score = 0.0
    best_reason = None
    for code, rule in (rulebook or {}).items():
        negative_hits = _matching_terms(name_norm, tuple(rule.exclude_keywords or ()))
        if negative_hits:
            continue
        positive_hits = _matching_terms(name_norm, tuple(rule.keywords or ()))
        if code == "styrehonorarOgGodtgjoerelseVerv":
            anchored_hits = [hit for hit in positive_hits if _normalize_text_shared(hit) in {"styre", "styrehonorar", "verv"}]
            if not anchored_hits:
                continue
        if not positive_hits:
            continue
        score = min(0.97, float(_DIRECT_HINT_SCORES.get(code, 0.88)) + 0.02 * max(len(positive_hits) - 1, 0))
        reason = f"Navn/alias: {', '.join(positive_hits[:2])}"
        if score > best_score:
            best_code = code
            best_score = score
            best_reason = reason
    return best_code, best_score, best_reason

def suggest_a07_code(
    *,
    account_no: str,
    account_name: str,
    movement: float,
    usage: AccountUsageFeatures | None = None,
    history_profile: AccountProfile | None = None,
    rulebook_path: str | None = None,
) -> AccountProfileSuggestion | None:
    if not _a07_suggestion_allowed_for_account(account_no=account_no, account_name=account_name):
        return None
    try:
        rulebook = load_rulebook(rulebook_path)
    except Exception:
        rulebook = {}
    best_code, best_score, best_reason = _direct_hint_code(account_name, rulebook)
    historical_accounts: set[str] = set()
    if history_profile is not None:
        account_from_history = _clean_text(getattr(history_profile, "account_no", None))
        if account_from_history:
            historical_accounts.add(account_from_history)

    for code, rule in (rulebook or {}).items():
        score, reason = _score_rule_match(
            code=code,
            account_no=account_no,
            account_name=account_name,
            movement=movement,
            rule=rule,
            usage=usage,
            historical_accounts=historical_accounts,
        )
        if score > best_score:
            best_code = code
            best_score = score
            best_reason = reason

    if not best_code:
        return None
    return AccountProfileSuggestion(
        field_name="a07_code",
        value=best_code,
        source="heuristic",
        confidence=best_score,
        reason=best_reason or "Heuristisk treff",
    )
