from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from a07_feature.suggest.api import AccountUsageFeatures, _tokenize, score_usage_signal
from account_profile import (
    AccountClassificationCatalog,
    AccountClassificationCatalogEntry,
    AccountProfile,
    AccountProfileDocument,
    AccountProfileSuggestion,
)
from a07_feature.suggest.rulebook import RulebookRule, load_rulebook

PAYROLL_RF1022_GROUPS: dict[str, str] = {
    "100_loenn_ol": "Post 100 Lønn o.l.",
    "100_refusjon": "Post 100 Refusjon",
    "111_naturalytelser": "Post 111 Naturalytelser",
    "112_pensjon": "Post 112 Pensjon",
}

PAYROLL_TAG_LABELS: dict[str, str] = {
    "opplysningspliktig": "Opplysningspliktig",
    "aga_pliktig": "AGA-pliktig",
    "finansskatt_pliktig": "Finansskatt-pliktig",
    "feriepengergrunnlag": "Feriepengegrunnlag",
    "refusjon": "Refusjon",
    "naturalytelse": "Naturalytelse",
    "pensjon": "Pensjon",
    "styrehonorar": "Styrehonorar",
}

PAYROLL_GROUP_IDS = tuple(PAYROLL_RF1022_GROUPS.keys())
PAYROLL_TAG_IDS = tuple(PAYROLL_TAG_LABELS.keys())

PAYROLL_CODE_DEFAULTS: dict[str, dict[str, tuple[str, ...] | str]] = {
    "fastloenn": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "aga_pliktig", "feriepengergrunnlag"),
    },
    "feriepenger": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "aga_pliktig"),
    },
    "tilskuddOgPremieTilPensjon": {
        "control_group": "112_pensjon",
        "control_tags": ("pensjon",),
    },
    "sumAvgiftsgrunnlagRefusjon": {
        "control_group": "100_refusjon",
        "control_tags": ("refusjon",),
    },
    "elektroniskKommunikasjon": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "bil": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "yrkebilTjenstligbehovListepris": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "skattepliktigDelForsikringer": {
        "control_group": "111_naturalytelser",
        "control_tags": ("naturalytelse", "opplysningspliktig", "aga_pliktig"),
    },
    "styrehonorarOgGodtgjoerelseVerv": {
        "control_group": "100_loenn_ol",
        "control_tags": ("opplysningspliktig", "styrehonorar"),
    },
}

_DIRECT_NAME_HINTS: tuple[tuple[str, tuple[str, ...], float, str], ...] = (
    ("tilskuddOgPremieTilPensjon", ("pensjon", "otp"), 0.96, "Navnemønster: pensjon"),
    ("sumAvgiftsgrunnlagRefusjon", ("refusjon", "sykepenger", "foreldrepenger"), 0.96, "Navnemønster: refusjon"),
    ("elektroniskKommunikasjon", ("telefon", "mobil", "ekom"), 0.93, "Navnemønster: elektronisk kommunikasjon"),
    ("skattepliktigDelForsikringer", ("forsikring", "helseforsikring"), 0.92, "Navnemønster: forsikring"),
    ("styrehonorarOgGodtgjoerelseVerv", ("styre", "honorar", "verv"), 0.92, "Navnemønster: styrehonorar"),
    ("bil", ("firmabil", "bil"), 0.9, "Navnemønster: bil"),
)

_PAYROLL_TOKENS = (
    "lønn",
    "lonn",
    "ferie",
    "pensjon",
    "otp",
    "telefon",
    "mobil",
    "ekom",
    "forsikring",
    "bil",
    "honorar",
    "styre",
    "refusjon",
    "sykepenger",
    "forskuddstrekk",
    "aga",
    "arbeidsgiveravgift",
)

_DIRECT_HINT_SCORES: dict[str, float] = {
    "tilskuddOgPremieTilPensjon": 0.96,
    "sumAvgiftsgrunnlagRefusjon": 0.96,
    "elektroniskKommunikasjon": 0.93,
    "skattepliktigDelForsikringer": 0.92,
    "styrehonorarOgGodtgjoerelseVerv": 0.92,
    "bil": 0.90,
    "yrkebilTjenstligbehovListepris": 0.90,
}

_PAYROLL_MIN_RULEBOOK_CONFIDENCE = 0.85
_PAYROLL_MIN_ALIAS_CONFIDENCE = 0.90
_PAYROLL_MIN_GENERIC_CONFIDENCE = 0.90
_STRONG_BALANCE_SHEET_PAYROLL_TOKENS = (
    "refusjon",
    "sykepenger",
    "feriepenger",
    "feriepengegjeld",
    "lonn",
    "lønn",
    "aga",
    "arbeidsgiveravgift",
    "forskuddstrekk",
    "skattetrekk",
    "trekk",
    "pensjon",
    "otp",
)
_BANK_ACCOUNT_NAME_TOKENS = (
    "bank",
    "sparekonto",
    "bedriftskonto",
    "mastercard",
    "visa",
    "kassekreditt",
)
_EQUITY_ACCOUNT_NAME_TOKENS = (
    "aksjekapital",
    "overkursfond",
    "egne aksjer",
    "egenkapital",
)
_VAT_OR_SETTLEMENT_NAME_TOKENS = (
    "merverdiavgift",
    "oppgjørskonto",
    "oppgjorskonto",
    "forhandsskatt",
    "forhåndsskatt",
)


_NON_PAYROLL_OPERATING_EXPENSE_TOKENS = (
    "leie",
    "lokale",
    "husleie",
    "parkering",
    "felleskostnad",
    "bodleie",
    "lys",
    "varme",
    "renhold",
    "frakt",
    "transport",
    "forsendelse",
    "inventar",
    "maskin",
    "kontormaskin",
    "datasystem",
    "datautstyr",
    "hardware",
    "software",
    "programvare",
    "rekvisita",
    "revisjon",
    "regnskap",
    "juridisk",
    "advokat",
    "vedlikehold",
    "service",
    "kontor",
)
_STRONG_EXPENSE_PAYROLL_NAME_TOKENS = (
    "lÃ¸nn",
    "lonn",
    "ferie",
    "pensjon",
    "otp",
    "telefon",
    "mobil",
    "ekom",
    "forsikring",
    "bil",
    "styre",
    "styrehonorar",
    "verv",
    "refusjon",
    "sykepenger",
    "forskuddstrekk",
    "aga",
    "arbeidsgiveravgift",
    "ansatt",
    "ansatte",
    "personalkostnad",
    "personalkostnader",
    "personell",
)

@dataclass(frozen=True)
class PayrollSuggestionResult:
    suggestions: dict[str, AccountProfileSuggestion]
    payroll_relevant: bool
    payroll_status: str
    unclear_reason: str | None = None
    has_strict_auto: bool = False
    is_unclear: bool = False


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_text_shared(value: object) -> str:
    text = _clean_text(value).casefold()
    replacements = {
        "ø": "o",
        "æ": "ae",
        "å": "a",
        "Ã¸": "o",
        "Ã¦": "ae",
        "Ã¥": "a",
        "-": " ",
        "_": " ",
        "/": " ",
        ",": " ",
        ".": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _normalize_text(value: object) -> str:
    text = _clean_text(value).casefold()
    replacements = {
        "ø": "o",
        "æ": "ae",
        "å": "a",
        "-": " ",
        "_": " ",
        "/": " ",
        ",": " ",
        ".": " ",
    }
    for before, after in replacements.items():
        text = text.replace(before, after)
    return " ".join(text.split())


def _normalized_phrase_match(text_norm: str, term: object) -> bool:
    candidate = _normalize_text_shared(term)
    if not candidate:
        return False
    text_tokens = tuple(token for token in text_norm.split() if token)
    candidate_tokens = tuple(token for token in candidate.split() if token)
    if not candidate_tokens:
        return False
    if len(candidate_tokens) > 1:
        return f" {candidate} " in f" {text_norm} "
    needle = candidate_tokens[0]
    for token in text_tokens:
        if token == needle:
            return True
        if len(needle) >= 5 and (token.startswith(needle) or token.endswith(needle)):
            return True
    return False


def _matching_terms(text_norm: str, terms: Iterable[object]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        if _normalized_phrase_match(text_norm, term):
            cleaned = _clean_text(term)
            if cleaned and cleaned not in hits:
                hits.append(cleaned)
    return hits


def _has_strong_expense_payroll_signal(name_norm: str) -> bool:
    return bool(_matching_terms(name_norm, _STRONG_EXPENSE_PAYROLL_NAME_TOKENS))


def _has_non_payroll_operating_expense_signal(name_norm: str) -> bool:
    return bool(_matching_terms(name_norm, _NON_PAYROLL_OPERATING_EXPENSE_TOKENS))


def _code_tokens_for_rule(code: str, rule: RulebookRule | None) -> set[str]:
    tokens = _tokenize(str(code or ""))
    if rule is not None:
        tokens |= _tokenize(str(rule.label or ""))
        for keyword in tuple(rule.keywords or ()):
            tokens |= _tokenize(str(keyword or ""))
    return tokens


def _to_number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


def _account_no_int(account_no: str) -> int | None:
    try:
        return int(str(account_no).strip())
    except Exception:
        return None


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


_DEFAULT_RULEBOOK_CACHE: Mapping[str, RulebookRule] | None = None


def invalidate_runtime_caches() -> None:
    global _DEFAULT_RULEBOOK_CACHE
    _DEFAULT_RULEBOOK_CACHE = None


def _default_rulebook() -> Mapping[str, RulebookRule]:
    global _DEFAULT_RULEBOOK_CACHE
    if _DEFAULT_RULEBOOK_CACHE is None:
        try:
            _DEFAULT_RULEBOOK_CACHE = load_rulebook(None)
        except Exception:
            _DEFAULT_RULEBOOK_CACHE = {}
    return _DEFAULT_RULEBOOK_CACHE or {}


def _in_allowed_ranges(account_no: str, ranges: Sequence[tuple[int, int]] | None) -> bool:
    konto_i = _account_no_int(account_no)
    if konto_i is None or not ranges:
        return False
    return any(start <= konto_i <= end for start, end in ranges)


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


def payroll_group_options(catalog: AccountClassificationCatalog | None) -> list[tuple[str, str]]:
    if catalog is None:
        return sorted(PAYROLL_RF1022_GROUPS.items(), key=lambda item: item[0])
    rows: list[tuple[str, str]] = []
    for entry in catalog.active_groups_for("kontrolloppstilling"):
        if entry.id in PAYROLL_RF1022_GROUPS:
            rows.append((entry.id, entry.label))
    if rows:
        return rows
    return sorted(PAYROLL_RF1022_GROUPS.items(), key=lambda item: item[0])


def payroll_tag_options(catalog: AccountClassificationCatalog | None) -> list[tuple[str, str]]:
    if catalog is None:
        return sorted(PAYROLL_TAG_LABELS.items(), key=lambda item: item[0])
    rows: list[tuple[str, str]] = []
    for entry in catalog.active_tags_for("kontrolloppstilling"):
        if entry.id in PAYROLL_TAG_IDS:
            rows.append((entry.id, entry.label))
    if rows:
        return rows
    return sorted(PAYROLL_TAG_LABELS.items(), key=lambda item: item[0])


def _fallback_group_entries() -> tuple[AccountClassificationCatalogEntry, ...]:
    return tuple(
        AccountClassificationCatalogEntry(
            id=group_id,
            label=label,
            category="payroll_rf1022_group",
            active=True,
            sort_order=index,
            applies_to=("kontrolloppstilling",),
        )
        for index, (group_id, label) in enumerate(sorted(PAYROLL_RF1022_GROUPS.items()), start=1)
    )


def _fallback_tag_entries() -> tuple[AccountClassificationCatalogEntry, ...]:
    return tuple(
        AccountClassificationCatalogEntry(
            id=tag_id,
            label=label,
            category="payroll_tag",
            active=True,
            sort_order=index,
            applies_to=("kontrolloppstilling",),
        )
        for index, (tag_id, label) in enumerate(sorted(PAYROLL_TAG_LABELS.items()), start=1)
    )


def _payroll_group_entries(catalog: AccountClassificationCatalog | None) -> tuple[AccountClassificationCatalogEntry, ...]:
    if catalog is not None:
        entries = tuple(entry for entry in catalog.active_groups_for("kontrolloppstilling") if entry.id in PAYROLL_GROUP_IDS)
        if entries:
            return entries
    return _fallback_group_entries()


def _payroll_tag_entries(catalog: AccountClassificationCatalog | None) -> tuple[AccountClassificationCatalogEntry, ...]:
    if catalog is not None:
        entries = tuple(entry for entry in catalog.active_tags_for("kontrolloppstilling") if entry.id in PAYROLL_TAG_IDS)
        if entries:
            return entries
    return _fallback_tag_entries()


def _catalog_entry_terms(entry: AccountClassificationCatalogEntry) -> tuple[str, ...]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw in (entry.label, *tuple(entry.aliases or ())):
        cleaned = _clean_text(raw)
        if not cleaned:
            continue
        normalized = _normalize_text_shared(cleaned)
        if normalized in seen:
            continue
        seen.add(normalized)
        terms.append(cleaned)
    return tuple(terms)


def _catalog_entry_exclude_terms(entry: AccountClassificationCatalogEntry) -> tuple[str, ...]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw in tuple(getattr(entry, "exclude_aliases", ()) or ()):
        cleaned = _clean_text(raw)
        if not cleaned:
            continue
        normalized = _normalize_text_shared(cleaned)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(cleaned)
    return tuple(terms)


def _usage_signal_text(usage: AccountUsageFeatures | None) -> str:
    if usage is None:
        return ""
    tokens: list[str] = []
    for raw in tuple(getattr(usage, "top_text_tokens", ()) or ()):
        cleaned = _clean_text(raw)
        if not cleaned:
            continue
        normalized = _normalize_text_shared(cleaned)
        if normalized and normalized not in tokens:
            tokens.append(normalized)
    return " ".join(tokens)


def _direct_catalog_exclude_hits(
    *,
    account_name: str,
    usage: AccountUsageFeatures | None,
    entry: AccountClassificationCatalogEntry,
) -> list[str]:
    """Returner liste med ekskluder-alias som treffer navn/kontobruk."""
    exclude_terms = _catalog_entry_exclude_terms(entry)
    if not exclude_terms:
        return []
    name_norm = _normalize_text_shared(account_name)
    usage_norm = _usage_signal_text(usage)
    hits: list[str] = []
    for term_hit in _matching_terms(name_norm, exclude_terms):
        if term_hit not in hits:
            hits.append(term_hit)
    if usage_norm:
        for term_hit in _matching_terms(usage_norm, exclude_terms):
            if term_hit not in hits:
                hits.append(term_hit)
    return hits


def detect_rf1022_exclude_blocks(
    *,
    account_no: str,
    account_name: str,
    catalog: AccountClassificationCatalog | None,
    usage: AccountUsageFeatures | None = None,
) -> list[tuple[str, str]]:
    """Returner (gruppelabel, ekskluder-alias) for grupper som ble blokkert
    av ekskluder-alias, men som ellers ville hatt positivt katalogtreff.

    Brukes av GUI for å gjøre blokkeringer sporbare i hvorfor-panelet.
    """
    if not _heuristic_allowed_for_account(account_no=account_no, account_name=account_name):
        return []
    results: list[tuple[str, str]] = []
    name_norm = _normalize_text_shared(account_name)
    usage_norm = _usage_signal_text(usage)
    for entry in _payroll_group_entries(catalog):
        terms = _catalog_entry_terms(entry)
        if not terms:
            continue
        exclude_hits = _direct_catalog_exclude_hits(
            account_name=account_name, usage=usage, entry=entry
        )
        if not exclude_hits:
            continue
        would_match = bool(_matching_terms(name_norm, terms))
        if not would_match and usage_norm:
            would_match = bool(_matching_terms(usage_norm, terms))
        if would_match:
            results.append((entry.label, exclude_hits[0]))
    return results


def _direct_catalog_signals(
    *,
    account_name: str,
    usage: AccountUsageFeatures | None,
    entry: AccountClassificationCatalogEntry,
) -> tuple[float, list[str]]:
    name_norm = _normalize_text_shared(account_name)
    usage_norm = _usage_signal_text(usage)
    terms = _catalog_entry_terms(entry)
    if not terms:
        return 0.0, []

    if _direct_catalog_exclude_hits(account_name=account_name, usage=usage, entry=entry):
        return 0.0, []

    name_hits = _matching_terms(name_norm, terms)
    usage_hits = _matching_terms(usage_norm, terms) if usage_norm else []

    score = 0.0
    reason_parts: list[str] = []
    if name_hits:
        score = max(score, min(0.97, 0.90 + 0.03 * max(len(name_hits) - 1, 0)))
        reason_parts.append(f"navn/alias: {name_hits[0]}")
    if usage_hits:
        score = max(score, min(0.96, 0.90 + 0.02 * max(len(usage_hits) - 1, 0)))
        reason_parts.append(f"kontobruk: {usage_hits[0]}")
    if name_hits and usage_hits:
        score = min(0.99, score + 0.03)
    return score, reason_parts


def _format_direct_reason(prefix: str, reason_parts: Sequence[str]) -> str:
    cleaned: list[str] = []
    for raw in reason_parts:
        text = _clean_text(raw)
        if text and text not in cleaned:
            cleaned.append(text)
    if not cleaned:
        return prefix
    return f"{prefix}: {', '.join(cleaned)}"


def _suggest_control_group_from_catalog(
    *,
    account_no: str,
    account_name: str,
    catalog: AccountClassificationCatalog | None,
    usage: AccountUsageFeatures | None = None,
) -> AccountProfileSuggestion | None:
    if not _heuristic_allowed_for_account(account_no=account_no, account_name=account_name):
        return None
    best_entry: AccountClassificationCatalogEntry | None = None
    best_score = 0.0
    best_reasons: list[str] = []
    for entry in _payroll_group_entries(catalog):
        score, reason_parts = _direct_catalog_signals(account_name=account_name, usage=usage, entry=entry)
        if score > best_score:
            best_entry = entry
            best_score = score
            best_reasons = reason_parts
    if best_entry is None or best_score <= 0:
        return None
    return AccountProfileSuggestion(
        field_name="control_group",
        value=best_entry.id,
        source="heuristic",
        confidence=best_score,
        reason=_format_direct_reason("Direkte RF-1022", best_reasons),
    )


def _suggest_control_tags_from_catalog(
    *,
    account_no: str,
    account_name: str,
    catalog: AccountClassificationCatalog | None,
    usage: AccountUsageFeatures | None = None,
    current_tags: Iterable[str] | None = None,
) -> AccountProfileSuggestion | None:
    if not _heuristic_allowed_for_account(account_no=account_no, account_name=account_name):
        return None
    current_tag_set = {tag for tag in (_clean_text(tag) for tag in (current_tags or ())) if tag}
    matched_entries: list[tuple[int, str]] = []
    best_confidence = 0.0
    aggregate_reasons: list[str] = []
    for entry in _payroll_tag_entries(catalog):
        score, reason_parts = _direct_catalog_signals(account_name=account_name, usage=usage, entry=entry)
        if score <= 0 or entry.id in current_tag_set:
            continue
        matched_entries.append((int(entry.sort_order), entry.id))
        best_confidence = max(best_confidence, score)
        for part in reason_parts:
            if part not in aggregate_reasons:
                aggregate_reasons.append(part)
    if not matched_entries:
        return None
    suggested_tags = tuple(
        tag_id
        for _, tag_id in sorted(matched_entries, key=lambda item: (item[0], item[1]))
    )
    if not suggested_tags:
        return None
    return AccountProfileSuggestion(
        field_name="control_tags",
        value=tuple(sorted(current_tag_set | set(suggested_tags))),
        source="heuristic",
        confidence=best_confidence,
        reason=_format_direct_reason("Direkte Flagg", aggregate_reasons),
    )


def control_group_for_code(code: str | None) -> str | None:
    code_s = _clean_text(code)
    if not code_s:
        return None
    raw = PAYROLL_CODE_DEFAULTS.get(code_s, {}).get("control_group")
    value = _clean_text(raw)
    return value or None


def required_control_tags_for_code(code: str | None) -> tuple[str, ...]:
    code_s = _clean_text(code)
    if not code_s:
        return ()
    raw = PAYROLL_CODE_DEFAULTS.get(code_s, {}).get("control_tags", ())
    if not isinstance(raw, tuple):
        raw = tuple(raw) if isinstance(raw, (list, set)) else ()
    return tuple(tag for tag in (_clean_text(tag) for tag in raw) if tag)


def format_control_group(group_id: str | None, catalog: AccountClassificationCatalog | None = None) -> str:
    group_s = _clean_text(group_id)
    if not group_s:
        return ""
    if catalog is not None:
        return catalog.group_label(group_s, fallback=PAYROLL_RF1022_GROUPS.get(group_s, group_s))
    return PAYROLL_RF1022_GROUPS.get(group_s, group_s)


def format_control_tags(tags: Iterable[str] | None, catalog: AccountClassificationCatalog | None = None) -> str:
    cleaned = []
    seen: set[str] = set()
    for raw in tags or ():
        tag = _clean_text(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        if catalog is not None:
            cleaned.append(catalog.tag_label(tag, fallback=PAYROLL_TAG_LABELS.get(tag, tag)))
        else:
            cleaned.append(PAYROLL_TAG_LABELS.get(tag, tag))
    return ", ".join(cleaned)


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


def _iter_account_rows(accounts_df: pd.DataFrame | Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    if isinstance(accounts_df, pd.DataFrame):
        rows: list[dict[str, object]] = []
        for _, row in accounts_df.iterrows():
            rows.append(
                {
                    "Konto": _clean_text(row.get("Konto")),
                    "Kontonavn": _clean_text(row.get("Kontonavn") or row.get("Navn")),
                    "IB": row.get("IB"),
                    "Endring": row.get("Endring"),
                    "UB": row.get("UB"),
                }
            )
        return rows
    return [dict(row) for row in accounts_df]


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


def classify_payroll_account(
    *,
    account_no: str,
    account_name: str,
    movement: float,
    current_profile: AccountProfile | None = None,
    history_profile: AccountProfile | None = None,
    catalog: AccountClassificationCatalog | None = None,
    usage: AccountUsageFeatures | None = None,
    rulebook_path: str | None = None,
) -> PayrollSuggestionResult:
    suggestions: dict[str, AccountProfileSuggestion] = {}

    if history_profile is not None:
        if (
            not _clean_text(current_profile.a07_code if current_profile else None)
            and history_profile.a07_code
            and _a07_suggestion_allowed_for_account(account_no=account_no, account_name=account_name)
        ):
            suggestions["a07_code"] = AccountProfileSuggestion(
                field_name="a07_code",
                value=history_profile.a07_code,
                source="history",
                confidence=1.0,
                reason="Forrige år",
            )
        if not _clean_text(current_profile.control_group if current_profile else None) and history_profile.control_group:
            suggestions["control_group"] = AccountProfileSuggestion(
                field_name="control_group",
                value=history_profile.control_group,
                source="history",
                confidence=1.0,
                reason="Forrige år",
            )
        if not tuple(getattr(current_profile, "control_tags", ()) or ()) and history_profile.control_tags:
            suggestions["control_tags"] = AccountProfileSuggestion(
                field_name="control_tags",
                value=tuple(history_profile.control_tags),
                source="history",
                confidence=1.0,
                reason="Forrige år",
            )

    code_suggestion = suggest_a07_code(
        account_no=account_no,
        account_name=account_name,
        movement=movement,
        usage=usage,
        history_profile=history_profile,
        rulebook_path=rulebook_path,
    )
    if code_suggestion is not None:
        # Keep the engine suggestion visible even when a classification is
        # already stored. This lets the UI show what the engine currently
        # believes, instead of looking empty on rows where current and
        # suggested values happen to agree.
        suggestions["a07_code"] = code_suggestion

    current_group = _clean_text(current_profile.control_group if current_profile else None)
    current_tags = tuple(getattr(current_profile, "control_tags", ()) or ())
    current_tag_set = {tag for tag in current_tags if _clean_text(tag)}

    direct_group_suggestion = _suggest_control_group_from_catalog(
        account_no=account_no,
        account_name=account_name,
        catalog=catalog,
        usage=usage,
    )
    if direct_group_suggestion is not None:
        suggestions["control_group"] = direct_group_suggestion

    direct_tag_suggestion = _suggest_control_tags_from_catalog(
        account_no=account_no,
        account_name=account_name,
        catalog=catalog,
        usage=usage,
        current_tags=current_tags,
    )
    if direct_tag_suggestion is not None:
        suggestions["control_tags"] = direct_tag_suggestion

    effective_code = _clean_text(current_profile.a07_code if current_profile else None)
    if not effective_code and isinstance(suggestions.get("a07_code"), AccountProfileSuggestion):
        effective_code = _clean_text(suggestions["a07_code"].value)

    default_group = control_group_for_code(effective_code)
    default_tags = required_control_tags_for_code(effective_code)

    if default_group and "control_group" not in suggestions:
        source = suggestions.get("a07_code").source if "a07_code" in suggestions else "heuristic"
        confidence = suggestions.get("a07_code").confidence if "a07_code" in suggestions else 0.9
        reason = suggestions.get("a07_code").reason if "a07_code" in suggestions else "Kode-standard"
        suggestions["control_group"] = AccountProfileSuggestion(
            field_name="control_group",
            value=default_group,
            source=source,
            confidence=confidence,
            reason=reason,
        )

    missing_default_tags = tuple(tag for tag in default_tags if tag not in current_tag_set)
    if missing_default_tags:
        existing_tag_suggestion = suggestions.get("control_tags")
        if isinstance(existing_tag_suggestion, AccountProfileSuggestion):
            existing_tags = tuple(
                tag
                for tag in (_clean_text(tag) for tag in (existing_tag_suggestion.value or ()))
                if tag
            )
            suggestions["control_tags"] = AccountProfileSuggestion(
                field_name="control_tags",
                value=tuple(sorted(set(existing_tags) | set(default_tags))),
                source=existing_tag_suggestion.source,
                confidence=max(float(existing_tag_suggestion.confidence or 0.0), 0.85),
                reason=existing_tag_suggestion.reason,
            )
        else:
            source = suggestions.get("a07_code").source if "a07_code" in suggestions else "heuristic"
            confidence = suggestions.get("a07_code").confidence if "a07_code" in suggestions else 0.85
            reason = suggestions.get("a07_code").reason if "a07_code" in suggestions else "Kode-standard"
            suggestions["control_tags"] = AccountProfileSuggestion(
                field_name="control_tags",
                value=tuple(sorted(set(current_tags) | set(default_tags))),
                source=source,
                confidence=confidence,
                reason=reason,
            )

    suggestions = {
        field_name: suggestion
        for field_name, suggestion in suggestions.items()
        if is_actionable_payroll_suggestion(suggestion)
    }

    effective_code = _clean_text(current_profile.a07_code if current_profile else None)
    if not effective_code and isinstance(suggestions.get("a07_code"), AccountProfileSuggestion):
        effective_code = _clean_text(suggestions["a07_code"].value)
    default_group = control_group_for_code(effective_code)
    default_tags = required_control_tags_for_code(effective_code)
    missing_default_tags = tuple(tag for tag in default_tags if tag not in current_tag_set)

    has_conflicting_group = bool(
        effective_code and current_group and default_group and current_group != default_group
    )
    missing_core = not _clean_text(current_profile.a07_code if current_profile else None) or (
        bool(default_group) and not current_group
    )
    missing_tags = bool(effective_code and missing_default_tags)
    has_suggestions = bool(suggestions)
    has_strict_auto = any(is_strict_auto_suggestion(suggestion) for suggestion in suggestions.values())
    payroll_relevant = payroll_relevant_for_account(
        account_no=account_no,
        account_name=account_name,
        current_profile=current_profile,
        suggestion_map=suggestions,
    )
    heuristic_only = has_suggestions and not has_strict_auto
    is_unclear = bool(has_conflicting_group or missing_tags or heuristic_only)

    if not payroll_relevant and not _has_payroll_profile_state(current_profile):
        status = ""
        unclear_reason = None
    elif bool(getattr(current_profile, "locked", False)):
        status = "Låst"
        unclear_reason = None
    elif has_conflicting_group:
        status = "Uklar"
        unclear_reason = "A07-kode og RF-1022-post peker i ulike retninger."
    elif missing_core or missing_tags:
        status = "Forslag" if has_suggestions else "Umappet"
        unclear_reason = "Manglende RF-1022-post eller lønnsflagg." if missing_tags else None
    elif current_profile is not None and current_profile.source == "history":
        status = "Historikk"
        unclear_reason = None
    elif current_profile is not None and current_profile.source in {"manual", "legacy"}:
        status = "Manuell"
        unclear_reason = None
    elif has_suggestions:
        status = "Forslag"
        unclear_reason = None
    else:
        status = "Klar"
        unclear_reason = None

    _ = catalog
    return PayrollSuggestionResult(
        suggestions=suggestions,
        payroll_relevant=payroll_relevant,
        payroll_status=status,
        unclear_reason=unclear_reason,
        has_strict_auto=has_strict_auto,
        is_unclear=is_unclear,
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


def build_payroll_suggestion_map(
    accounts_df: pd.DataFrame | Sequence[Mapping[str, object]],
    *,
    document: AccountProfileDocument,
    history_document: AccountProfileDocument | None = None,
    catalog: AccountClassificationCatalog | None = None,
    usage_features: Mapping[str, AccountUsageFeatures] | None = None,
    rulebook_path: str | None = None,
) -> dict[str, PayrollSuggestionResult]:
    results: dict[str, PayrollSuggestionResult] = {}
    for row in _iter_account_rows(accounts_df):
        account_no = _clean_text(row.get("Konto"))
        if not account_no:
            continue
        account_name = _clean_text(row.get("Kontonavn"))
        current_profile = document.get(account_no)
        history_profile = history_document.get(account_no) if history_document is not None else None
        results[account_no] = classify_payroll_account(
            account_no=account_no,
            account_name=account_name,
            movement=_to_number(row.get("Endring")),
            current_profile=current_profile,
            history_profile=history_profile,
            catalog=catalog,
            usage=(usage_features or {}).get(account_no),
            rulebook_path=rulebook_path,
        )
    return results


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
