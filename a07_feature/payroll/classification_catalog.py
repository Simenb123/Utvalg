from __future__ import annotations

from typing import Iterable, Sequence

from a07_feature.control.rf1022_bridge import RF1022_UNKNOWN_GROUP, resolve_a07_rf1022_group
from a07_feature.suggest.api import AccountUsageFeatures
from account_profile import AccountClassificationCatalog, AccountClassificationCatalogEntry, AccountProfileSuggestion

from .classification_guardrails import _heuristic_allowed_for_account
from .classification_shared import (
    PAYROLL_CODE_DEFAULTS,
    PAYROLL_GROUP_IDS,
    PAYROLL_RF1022_GROUPS,
    PAYROLL_TAG_IDS,
    PAYROLL_TAG_LABELS,
    _clean_text,
    _matching_terms,
    _normalize_text_shared,
)

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


def control_group_for_code(code: str | None, *, rulebook_path: str | None = None) -> str | None:
    code_s = _clean_text(code)
    if not code_s:
        return None
    resolved = resolve_a07_rf1022_group(code_s, rulebook_path=rulebook_path)
    if resolved and resolved != RF1022_UNKNOWN_GROUP:
        return resolved
    return None


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
    fallback = PAYROLL_RF1022_GROUPS.get(group_s, group_s)
    if catalog is not None:
        label = catalog.group_label(group_s, fallback=fallback)
        return fallback if label == group_s and fallback != group_s else label
    return fallback


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
