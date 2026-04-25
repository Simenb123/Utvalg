from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from a07_feature.suggest.api import AccountUsageFeatures
from account_profile import AccountClassificationCatalog, AccountProfile, AccountProfileDocument, AccountProfileSuggestion

from .classification_a07_engine import suggest_a07_code
from .classification_catalog import (
    _suggest_control_tags_from_catalog,
    control_group_for_code,
    required_control_tags_for_code,
)
from .classification_guardrails import (
    _a07_suggestion_allowed_for_account,
    _has_payroll_profile_state,
    is_actionable_payroll_suggestion,
    is_strict_auto_suggestion,
    payroll_relevant_for_account,
)
from .classification_shared import PayrollSuggestionResult, _clean_text, _to_number

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

    default_group = control_group_for_code(effective_code, rulebook_path=rulebook_path)
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
    default_group = control_group_for_code(effective_code, rulebook_path=rulebook_path)
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
