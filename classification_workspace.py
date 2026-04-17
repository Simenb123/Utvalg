from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

import payroll_classification
from account_profile import (
    AccountClassificationCatalog,
    AccountProfile,
    AccountProfileDocument,
    AccountProfileSuggestion,
)


QUEUE_ALL = "Alle"
QUEUE_SUSPICIOUS = "Mistenkelig lagret"
QUEUE_READY = "Klar til forslag"
QUEUE_HISTORY = "Historikk tilgjengelig"
QUEUE_REVIEW = "Trenger vurdering"
QUEUE_UNMAPPED = "Umappet"
QUEUE_LOCKED = "Låste"
QUEUE_SAVED = "Lagret"

NEXT_APPLY_SUGGESTION = "apply_suggestion"
NEXT_APPLY_HISTORY = "apply_history"
NEXT_RESET_SAVED = "reset_saved"
NEXT_OPEN_CLASSIFIER = "open_classifier"
NEXT_REVIEW_SAVED = "review_saved"
NEXT_UNLOCK = "unlock"


@dataclass(frozen=True)
class ClassificationProvenance:
    source: str
    reason: str
    confidence: float | None = None
    derived_from: str | None = None

    @property
    def is_derived(self) -> bool:
        return bool(_clean_text(self.derived_from))

    @property
    def kind_label(self) -> str:
        return "Avledet" if self.is_derived else "Direkte"


@dataclass(frozen=True)
class ClassificationFieldState:
    value: object
    display: str
    provenance: ClassificationProvenance | None = None


@dataclass(frozen=True)
class ClassificationCurrentState:
    a07_code: ClassificationFieldState
    control_group: ClassificationFieldState
    control_tags: ClassificationFieldState
    source: str
    confidence: float | None
    locked: bool


@dataclass(frozen=True)
class ClassificationSuggestedState:
    a07_code: ClassificationFieldState | None = None
    control_group: ClassificationFieldState | None = None
    control_tags: ClassificationFieldState | None = None


@dataclass(frozen=True)
class ClassificationQueueState:
    suspicious_saved: bool = False
    strict_suggestion: bool = False
    history_available: bool = False
    needs_manual: bool = False
    locked: bool = False
    review_saved: bool = False
    unmapped: bool = False


@dataclass(frozen=True)
class ClassificationWorkspaceItem:
    account_no: str
    account_name: str
    ib: float
    movement: float
    ub: float
    current: ClassificationCurrentState
    suggested: ClassificationSuggestedState
    previous: ClassificationCurrentState
    queue_state: ClassificationQueueState
    queue_name: str
    status_label: str
    next_action: str
    next_action_label: str
    current_summary: str
    suggested_summary: str
    why_summary: str
    issue_text: str
    confidence: float | None
    confidence_label: str
    confidence_bucket: str
    payroll_relevant: bool
    result: payroll_classification.PayrollSuggestionResult | None
    rf1022_exclude_blocks: tuple[tuple[str, str], ...] = ()


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _display_text(field_state: ClassificationFieldState | None) -> str:
    """Les ``display`` trygt fra et ``ClassificationFieldState`` som kan være None."""
    if field_state is None:
        return ""
    return str(getattr(field_state, "display", "") or "").strip()


def _to_number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(pd.to_numeric([value], errors="coerce")[0] or 0.0)
    except Exception:
        return 0.0


def _source_label(source: object) -> str:
    source_s = _clean_text(source).lower()
    if source_s == "manual":
        return "Manuell"
    if source_s == "history":
        return "Historikk"
    if source_s == "legacy":
        return "Legacy"
    if source_s == "heuristic":
        return "Forslag"
    if not source_s:
        return ""
    return source_s.capitalize()


def _confidence_bucket(confidence: float | None) -> str:
    if confidence is None:
        return ""
    try:
        value = float(confidence)
    except Exception:
        return ""
    if value >= 0.9:
        return "Høy"
    if value >= 0.75:
        return "Middels"
    return "Lav"


def _suggestion_reason_text(suggestion: AccountProfileSuggestion | None) -> str:
    if suggestion is None:
        return ""
    reason = _clean_text(getattr(suggestion, "reason", None))
    if reason.startswith("Direkte RF-1022:") or reason.startswith("Direkte Flagg:"):
        return reason
    if reason == "Forrige år":
        return "Historikk"
    if reason == "Kode-standard":
        return "A07-standard"
    if reason.startswith("Navn/alias:"):
        alias_values = [part.strip() for part in reason.removeprefix("Navn/alias:").split(",") if part.strip()]
        return f"Navn/alias: {alias_values[0]}" if alias_values else "Navn/alias"
    if reason.startswith("Regelbok:"):
        compact_parts: list[str] = []
        reason_lower = reason.lower()
        if "konto-intervall" in reason_lower:
            compact_parts.append("konto-intervall")
        if any(marker in reason_lower for marker in ("eksplisitt kontotreff", "motkonto", "boost", "intervall", "historikk")):
            compact_parts.append("kontobruk")
        if "navn (" in reason_lower or "tekst (" in reason_lower:
            start = reason.find("(")
            end = reason.find(")", start + 1) if start >= 0 else -1
            alias_label = reason[start + 1:end].split(",")[0].strip() if end > start else ""
            compact_parts.append(f"navn/alias: {alias_label}" if alias_label else "navn/alias")
        if "periodisitet" in reason_lower:
            compact_parts.append("periodisitet")
        if "beløp/sign" in reason_lower or "bel" in reason_lower and "sign" in reason_lower:
            compact_parts.append("beløp/sign")
        if compact_parts:
            return f"Regelbok: {', '.join(compact_parts)}"
        return "Regelbok"
    if reason:
        return reason
    return _source_label(getattr(suggestion, "source", None))


def _current_field_state(
    value: object,
    display: str,
    profile: AccountProfile | None,
) -> ClassificationFieldState:
    provenance = None
    if _clean_text(display) or (isinstance(value, tuple) and value):
        provenance = ClassificationProvenance(
            source=_clean_text(getattr(profile, "source", None)),
            reason=(
                "Legacy profil"
                if _clean_text(getattr(profile, "source", None)).lower() == "legacy"
                else "Lagret profil"
            ),
            confidence=getattr(profile, "confidence", None),
        )
    return ClassificationFieldState(value=value, display=display, provenance=provenance)


def _history_snapshot(
    history_profile: AccountProfile | None,
    catalog: AccountClassificationCatalog | None,
) -> ClassificationCurrentState:
    return ClassificationCurrentState(
        a07_code=ClassificationFieldState(
            value=_clean_text(getattr(history_profile, "a07_code", None)),
            display=_clean_text(getattr(history_profile, "a07_code", None)),
            provenance=ClassificationProvenance(
                source="history",
                reason="Forrige år",
                confidence=getattr(history_profile, "confidence", None),
            )
            if history_profile is not None and _clean_text(getattr(history_profile, "a07_code", None))
            else None,
        ),
        control_group=ClassificationFieldState(
            value=_clean_text(getattr(history_profile, "control_group", None)),
            display=payroll_classification.format_control_group(
                _clean_text(getattr(history_profile, "control_group", None)),
                catalog,
            ),
            provenance=ClassificationProvenance(
                source="history",
                reason="Forrige år",
                confidence=getattr(history_profile, "confidence", None),
            )
            if history_profile is not None and _clean_text(getattr(history_profile, "control_group", None))
            else None,
        ),
        control_tags=ClassificationFieldState(
            value=tuple(getattr(history_profile, "control_tags", ()) or ()),
            display=payroll_classification.format_control_tags(getattr(history_profile, "control_tags", ()), catalog),
            provenance=ClassificationProvenance(
                source="history",
                reason="Forrige år",
                confidence=getattr(history_profile, "confidence", None),
            )
            if history_profile is not None and tuple(getattr(history_profile, "control_tags", ()) or ())
            else None,
        ),
        source=_source_label(getattr(history_profile, "source", None)),
        confidence=getattr(history_profile, "confidence", None),
        locked=bool(getattr(history_profile, "locked", False)),
    )


def _field_derived_from_a07(
    *,
    field_name: str,
    effective_code: str,
    suggestion: AccountProfileSuggestion | None,
) -> str | None:
    if suggestion is None or not effective_code:
        return None
    reason = _clean_text(getattr(suggestion, "reason", None))
    if reason.startswith("Direkte RF-1022:") or reason.startswith("Direkte Flagg:"):
        return None
    if field_name == "control_group":
        expected = payroll_classification.control_group_for_code(effective_code)
        if expected and _clean_text(suggestion.value) == _clean_text(expected):
            return "a07_standard"
    if field_name == "control_tags":
        expected_tags = tuple(sorted(payroll_classification.required_control_tags_for_code(effective_code)))
        suggestion_tags = tuple(sorted(str(tag).strip() for tag in (suggestion.value or ()) if str(tag).strip()))
        if expected_tags and suggestion_tags == expected_tags:
            return "a07_standard"
    return None


def _suggested_field_state(
    *,
    field_name: str,
    suggestion: AccountProfileSuggestion | None,
    catalog: AccountClassificationCatalog | None,
    effective_code: str,
) -> ClassificationFieldState | None:
    if suggestion is None:
        return None
    if field_name == "a07_code":
        display = _clean_text(suggestion.value)
    elif field_name == "control_group":
        display = payroll_classification.format_control_group(_clean_text(suggestion.value), catalog)
    elif field_name == "control_tags":
        display = payroll_classification.format_control_tags(suggestion.value, catalog)
    else:
        display = _clean_text(suggestion.value)
    provenance = ClassificationProvenance(
        source=_clean_text(getattr(suggestion, "source", None)),
        reason=_suggestion_reason_text(suggestion),
        confidence=getattr(suggestion, "confidence", None),
        derived_from=_field_derived_from_a07(
            field_name=field_name,
            effective_code=effective_code,
            suggestion=suggestion,
        ),
    )
    return ClassificationFieldState(value=suggestion.value, display=display, provenance=provenance)


def _format_summary(
    *,
    a07_display: str,
    group_display: str,
    tags_display: str,
    empty_text: str,
) -> str:
    parts: list[str] = []
    if a07_display:
        parts.append(f"A07 {a07_display}")
    if group_display:
        parts.append(f"RF-1022 {group_display}")
    if tags_display:
        parts.append(f"Flagg {tags_display}")
    return " | ".join(parts) if parts else empty_text


def _why_summary(suggested: ClassificationSuggestedState) -> str:
    parts: list[str] = []
    for label, field_state in (
        ("A07", suggested.a07_code),
        ("RF-1022", suggested.control_group),
        ("Flagg", suggested.control_tags),
    ):
        if field_state is None or field_state.provenance is None:
            continue
        provenance = field_state.provenance
        if provenance.derived_from == "a07_standard":
            parts.append(f"{label}: avledet fra A07-standard")
        elif provenance.reason:
            parts.append(f"{label}: {_human_reason_text(provenance.reason)}")
        elif provenance.source:
            parts.append(f"{label}: {_source_label(provenance.source)}")
    return " | ".join(parts)


def _human_reason_text(reason: object) -> str:
    reason_s = _clean_text(reason)
    if reason_s.startswith("Direkte RF-1022:"):
        direct = reason_s.removeprefix("Direkte RF-1022:").strip()
        return direct or "direkte treff"
    if reason_s.startswith("Direkte Flagg:"):
        direct = reason_s.removeprefix("Direkte Flagg:").strip()
        return direct or "direkte treff"
    if reason_s == "Forrige år":
        return "Historikk"
    if reason_s == "Kode-standard":
        return "A07-standard"
    if reason_s.startswith("Navn/alias:"):
        alias_values = [part.strip() for part in reason_s.removeprefix("Navn/alias:").split(",") if part.strip()]
        return f"navn/alias: {alias_values[0]}" if alias_values else "navn/alias"
    if reason_s.startswith("Regelbok:"):
        compact_parts: list[str] = []
        reason_lower = reason_s.lower()
        if "konto-intervall" in reason_lower:
            compact_parts.append("konto-intervall")
        if "eksplisitt kontotreff" in reason_lower:
            compact_parts.append("eksplisitt kontotreff")
        if "periodisitet" in reason_lower:
            compact_parts.append("periodisitet")
        if "historikk" in reason_lower:
            compact_parts.append("historikk")
        alias_match = re.search(r"navn \(([^)]+)\)", reason_s, re.IGNORECASE)
        if alias_match:
            compact_parts.append(f"navn/alias: {alias_match.group(1).split(',')[0].strip()}")
        text_match = re.search(r"tekst \(([^)]+)\)", reason_s, re.IGNORECASE)
        if text_match:
            compact_parts.append(f"kontobruk: {text_match.group(1).split(',')[0].strip()}")
        if compact_parts:
            return ", ".join(dict.fromkeys(compact_parts))
        return "regelbok"
    return reason_s


def _field_why_line(label: str, field_state: ClassificationFieldState | None) -> str:
    if field_state is None or field_state.provenance is None:
        return ""
    provenance = field_state.provenance
    if provenance.derived_from == "a07_standard":
        return f"{label}: Avledet fra A07-standard"
    if provenance.reason:
        return f"{label}: {_human_reason_text(provenance.reason)}"
    if provenance.source:
        return f"{label}: {_source_label(provenance.source)}"
    return ""


def _normalize_field_value_for_compare(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(sorted(_clean_text(part) for part in value if _clean_text(part)))
    return _clean_text(value)


def _field_matches_current(
    current_state: ClassificationFieldState | None,
    suggested_state: ClassificationFieldState | None,
) -> bool:
    if suggested_state is None:
        return False
    current_value = _normalize_field_value_for_compare(getattr(current_state, "value", None))
    suggested_value = _normalize_field_value_for_compare(suggested_state.value)
    if isinstance(current_value, tuple):
        return bool(current_value) and current_value == suggested_value
    return bool(current_value) and current_value == suggested_value


def matching_suggestion_labels(item: ClassificationWorkspaceItem) -> tuple[str, ...]:
    labels: list[str] = []
    for label, current_state, suggested_state in (
        ("A07", item.current.a07_code, item.suggested.a07_code),
        ("RF-1022", item.current.control_group, item.suggested.control_group),
        ("Flagg", item.current.control_tags, item.suggested.control_tags),
    ):
        if _field_matches_current(current_state, suggested_state):
            labels.append(label)
    return tuple(labels)


def _field_has_actionable_suggestion(
    current_state: ClassificationFieldState | None,
    suggested_state: ClassificationFieldState | None,
) -> bool:
    if suggested_state is None:
        return False
    current_value = _normalize_field_value_for_compare(getattr(current_state, "value", None))
    suggested_value = _normalize_field_value_for_compare(suggested_state.value)
    if isinstance(suggested_value, tuple):
        return bool(suggested_value) and current_value != suggested_value
    return bool(suggested_value) and current_value != suggested_value


def actionable_suggestion_labels(item: ClassificationWorkspaceItem) -> tuple[str, ...]:
    labels: list[str] = []
    for label, current_state, suggested_state in (
        ("A07", item.current.a07_code, item.suggested.a07_code),
        ("RF-1022", item.current.control_group, item.suggested.control_group),
        ("Flagg", item.current.control_tags, item.suggested.control_tags),
    ):
        if _field_has_actionable_suggestion(current_state, suggested_state):
            labels.append(label)
    return tuple(labels)


def has_actionable_suggestion(item: ClassificationWorkspaceItem) -> bool:
    return bool(actionable_suggestion_labels(item))


def _summary_suggestion_display(
    current_state: ClassificationFieldState | None,
    suggested_state: ClassificationFieldState | None,
) -> str:
    if suggested_state is None:
        return ""
    if _field_matches_current(current_state, suggested_state):
        return ""
    if _field_has_actionable_suggestion(current_state, suggested_state):
        return _display_text(suggested_state)
    return ""


def _next_action_for_item(
    *,
    suspicious_saved: bool,
    locked: bool,
    strict_suggestion: bool,
    history_available: bool,
    review_saved: bool,
) -> tuple[str, str]:
    if suspicious_saved:
        return NEXT_RESET_SAVED, "Nullstill lagret lønnsklassifisering."
    if locked:
        return NEXT_UNLOCK, "Lås opp hvis du vil endre klassifiseringen."
    if strict_suggestion:
        return NEXT_APPLY_SUGGESTION, "Godkjenn forslag."
    if history_available:
        return NEXT_APPLY_HISTORY, "Bruk fjorårets klassifisering."
    if review_saved:
        return NEXT_REVIEW_SAVED, "Kontroller lagret klassifisering."
    return NEXT_OPEN_CLASSIFIER, "Åpne klassifisering."


def build_workspace_item(
    *,
    account_no: str,
    account_name: str,
    ib: object = 0.0,
    movement: object = 0.0,
    ub: object = 0.0,
    current_profile: AccountProfile | None = None,
    history_profile: AccountProfile | None = None,
    catalog: AccountClassificationCatalog | None = None,
    usage: Any = None,
    rulebook_path: str | None = None,
) -> ClassificationWorkspaceItem:
    account_no_s = _clean_text(account_no)
    account_name_s = _clean_text(account_name)
    ib_f = _to_number(ib)
    movement_f = _to_number(movement)
    ub_f = _to_number(ub)

    result = payroll_classification.classify_payroll_account(
        account_no=account_no_s,
        account_name=account_name_s,
        movement=movement_f,
        current_profile=current_profile,
        history_profile=history_profile,
        catalog=catalog,
        usage=usage,
        rulebook_path=rulebook_path,
    )
    suggestions = dict(result.suggestions) if result is not None else {}

    actual_a07 = _clean_text(getattr(current_profile, "a07_code", None))
    actual_group_id = _clean_text(getattr(current_profile, "control_group", None))
    actual_tags = tuple(getattr(current_profile, "control_tags", ()) or ())

    current = ClassificationCurrentState(
        a07_code=_current_field_state(actual_a07, actual_a07, current_profile),
        control_group=_current_field_state(
            actual_group_id,
            payroll_classification.format_control_group(actual_group_id, catalog),
            current_profile,
        ),
        control_tags=_current_field_state(
            actual_tags,
            payroll_classification.format_control_tags(actual_tags, catalog),
            current_profile,
        ),
        source=_source_label(getattr(current_profile, "source", None)),
        confidence=getattr(current_profile, "confidence", None),
        locked=bool(getattr(current_profile, "locked", False)),
    )
    previous = _history_snapshot(history_profile, catalog)

    effective_code = actual_a07
    a07_suggestion = suggestions.get("a07_code")
    if not effective_code and a07_suggestion is not None:
        effective_code = _clean_text(a07_suggestion.value)

    suggested = ClassificationSuggestedState(
        a07_code=_suggested_field_state(
            field_name="a07_code",
            suggestion=a07_suggestion,
            catalog=catalog,
            effective_code=effective_code,
        ),
        control_group=_suggested_field_state(
            field_name="control_group",
            suggestion=suggestions.get("control_group"),
            catalog=catalog,
            effective_code=effective_code,
        ),
        control_tags=_suggested_field_state(
            field_name="control_tags",
            suggestion=suggestions.get("control_tags"),
            catalog=catalog,
            effective_code=effective_code,
        ),
    )

    issue_text = _clean_text(
        payroll_classification.suspicious_saved_payroll_profile_issue(
            account_no=account_no_s,
            account_name=account_name_s,
            current_profile=current_profile,
        )
    )

    has_current_state = payroll_classification._has_payroll_profile_state(current_profile)
    has_history_state = payroll_classification._has_payroll_profile_state(history_profile)
    strict_suggestion = any(
        (
            _field_has_actionable_suggestion(current.a07_code, suggested.a07_code),
            _field_has_actionable_suggestion(current.control_group, suggested.control_group),
            _field_has_actionable_suggestion(current.control_tags, suggested.control_tags),
        )
    )
    history_available = bool(has_history_state and not has_current_state)
    locked = bool(getattr(current_profile, "locked", False))
    actionable_suggestions = bool(
        any(
            (
                _field_has_actionable_suggestion(current.a07_code, suggested.a07_code),
                _field_has_actionable_suggestion(current.control_group, suggested.control_group),
                _field_has_actionable_suggestion(current.control_tags, suggested.control_tags),
            )
        )
    )
    review_saved = bool(has_current_state and not issue_text and not locked and not actionable_suggestions)
    unmapped = bool(not has_current_state and not suggestions)
    needs_manual = bool(
        not issue_text
        and not locked
        and not strict_suggestion
        and not history_available
        and (
            unmapped
            or bool(getattr(result, "is_unclear", False))
            or actionable_suggestions
            or _clean_text(getattr(result, "payroll_status", None)) in {"Umappet", "Uklar"}
        )
    )
    queue_state = ClassificationQueueState(
        suspicious_saved=bool(issue_text),
        strict_suggestion=strict_suggestion,
        history_available=history_available,
        needs_manual=needs_manual,
        locked=locked,
        review_saved=review_saved,
        unmapped=unmapped,
    )
    if queue_state.suspicious_saved:
        queue_name = QUEUE_SUSPICIOUS
        status_label = "Mistenkelig"
    elif queue_state.locked:
        queue_name = QUEUE_LOCKED
        status_label = "Låst"
    elif queue_state.strict_suggestion:
        queue_name = QUEUE_READY
        status_label = "Klar til forslag"
    elif queue_state.history_available:
        queue_name = QUEUE_HISTORY
        status_label = "Historikk tilgjengelig"
    elif queue_state.unmapped:
        queue_name = QUEUE_UNMAPPED
        status_label = "Umappet"
    elif queue_state.needs_manual:
        queue_name = QUEUE_REVIEW
        status_label = "Trenger vurdering"
    elif queue_state.review_saved:
        queue_name = QUEUE_SAVED
        status_label = "Lagret"
    else:
        queue_name = QUEUE_REVIEW
        status_label = _clean_text(getattr(result, "payroll_status", None)) or "Trenger vurdering"

    next_action, next_action_label = _next_action_for_item(
        suspicious_saved=queue_state.suspicious_saved,
        locked=queue_state.locked,
        strict_suggestion=queue_state.strict_suggestion,
        history_available=queue_state.history_available,
        review_saved=queue_state.review_saved,
    )

    top_confidence = None
    top_suggestion = None
    if suggestions:
        ranked = sorted(
            suggestions.values(),
            key=lambda suggestion: (
                0 if payroll_classification.is_strict_auto_suggestion(suggestion) else 1,
                -(float(getattr(suggestion, "confidence", 0.0) or 0.0)),
                getattr(suggestion, "field_name", ""),
            ),
        )
        top_suggestion = ranked[0] if ranked else None
    if top_suggestion is not None:
        top_confidence = getattr(top_suggestion, "confidence", None)
    elif getattr(current_profile, "confidence", None) is not None:
        top_confidence = getattr(current_profile, "confidence", None)

    rf1022_exclude_blocks = tuple(
        payroll_classification.detect_rf1022_exclude_blocks(
            account_no=account_no_s,
            account_name=account_name_s,
            catalog=catalog,
            usage=usage,
        )
    )

    return ClassificationWorkspaceItem(
        account_no=account_no_s,
        account_name=account_name_s,
        ib=ib_f,
        movement=movement_f,
        ub=ub_f,
        current=current,
        suggested=suggested,
        previous=previous,
        queue_state=queue_state,
        queue_name=queue_name,
        status_label=status_label,
        next_action=next_action,
        next_action_label=next_action_label,
        current_summary=_format_summary(
            a07_display=_display_text(current.a07_code),
            group_display=_display_text(current.control_group),
            tags_display=_display_text(current.control_tags),
            empty_text="Ikke klassifisert",
        ),
        suggested_summary=_format_summary(
            a07_display=_summary_suggestion_display(current.a07_code, suggested.a07_code),
            group_display=_summary_suggestion_display(current.control_group, suggested.control_group),
            tags_display=_summary_suggestion_display(current.control_tags, suggested.control_tags),
            empty_text="Ingen forslag",
        ),
        why_summary=_why_summary(suggested),
        issue_text=issue_text,
        confidence=top_confidence,
        confidence_label=payroll_classification.confidence_label(top_confidence),
        confidence_bucket=_confidence_bucket(top_confidence),
        payroll_relevant=bool(getattr(result, "payroll_relevant", False)),
        result=result,
        rf1022_exclude_blocks=rf1022_exclude_blocks,
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


def build_workspace_items(
    accounts_df: pd.DataFrame | Sequence[Mapping[str, object]],
    *,
    document: AccountProfileDocument,
    history_document: AccountProfileDocument | None = None,
    catalog: AccountClassificationCatalog | None = None,
    usage_features: Mapping[str, Any] | None = None,
    rulebook_path: str | None = None,
) -> dict[str, ClassificationWorkspaceItem]:
    items: dict[str, ClassificationWorkspaceItem] = {}
    for row in _iter_account_rows(accounts_df):
        account_no = _clean_text(row.get("Konto"))
        if not account_no:
            continue
        items[account_no] = build_workspace_item(
            account_no=account_no,
            account_name=_clean_text(row.get("Kontonavn")),
            ib=row.get("IB"),
            movement=row.get("Endring"),
            ub=row.get("UB"),
            current_profile=document.get(account_no),
            history_profile=history_document.get(account_no) if history_document is not None else None,
            catalog=catalog,
            usage=(usage_features or {}).get(account_no),
            rulebook_path=rulebook_path,
        )
    return items


def queue_matches(item: ClassificationWorkspaceItem, queue_name: str | None) -> bool:
    queue_s = _clean_text(queue_name) or QUEUE_ALL
    if queue_s == QUEUE_ALL:
        return True
    if queue_s == QUEUE_SUSPICIOUS:
        return item.queue_state.suspicious_saved
    if queue_s == QUEUE_READY or queue_s == "Kun forslag":
        return item.queue_state.strict_suggestion
    if queue_s == QUEUE_HISTORY:
        return item.queue_state.history_available
    if queue_s == QUEUE_REVIEW or queue_s in {"Kun uklare", "Kun lønnsrelevante"}:
        return item.queue_state.needs_manual or item.queue_state.review_saved
    if queue_s == QUEUE_UNMAPPED or queue_s == "Kun lønnsumappede":
        return item.queue_state.unmapped
    if queue_s == QUEUE_LOCKED:
        return item.queue_state.locked
    if queue_s == QUEUE_SAVED:
        return item.queue_state.review_saved
    return True


def _guided_next_step_text(item: ClassificationWorkspaceItem) -> str:
    action = _clean_text(item.next_action)
    label = _clean_text(item.next_action_label)
    if action == NEXT_APPLY_SUGGESTION:
        return f"Primærhandling: {label or 'Godkjenn forslag.'}"
    if action == NEXT_APPLY_HISTORY:
        return f"Primærhandling: {label or 'Bruk fjorårets klassifisering.'}"
    if action == NEXT_RESET_SAVED:
        return f"Primærhandling: {label or 'Nullstill lagret lønnsklassifisering.'}"
    if action == NEXT_UNLOCK:
        return f"Primærhandling: {label or 'Lås opp hvis du vil endre klassifiseringen.'}"
    if action == NEXT_REVIEW_SAVED:
        return f"Primærhandling: {label or 'Kontroller lagret klassifisering.'}"
    return f"Primærhandling: {label or 'Åpne klassifisering.'}"


def format_why_panel(item: ClassificationWorkspaceItem) -> dict[str, str]:
    current_state = getattr(item, "current", None)
    suggested_state = getattr(item, "suggested", None)
    previous_state = getattr(item, "previous", None)

    current_a07 = getattr(current_state, "a07_code", None)
    current_group = getattr(current_state, "control_group", None)
    current_tags = getattr(current_state, "control_tags", None)
    suggested_a07 = getattr(suggested_state, "a07_code", None)
    suggested_group = getattr(suggested_state, "control_group", None)
    suggested_tags = getattr(suggested_state, "control_tags", None)
    previous_a07 = getattr(previous_state, "a07_code", None)
    previous_group = getattr(previous_state, "control_group", None)
    previous_tags = getattr(previous_state, "control_tags", None)

    current_summary = item.current_summary or _format_summary(
        a07_display=_display_text(current_a07),
        group_display=_display_text(current_group),
        tags_display=_display_text(current_tags),
        empty_text="Ikke klassifisert",
    )
    suggested_summary = item.suggested_summary or _format_summary(
        a07_display=_display_text(suggested_a07),
        group_display=_display_text(suggested_group),
        tags_display=_display_text(suggested_tags),
        empty_text="Ingen forslag",
    )
    agreement_labels = matching_suggestion_labels(item)

    current_lines = [f"Nå: {current_summary}"]
    if getattr(current_state, "source", ""):
        current_lines.append(f"Kilde: {current_state.source}")
    if getattr(current_state, "locked", False):
        current_lines.append("Låst: Ja")
    if _display_text(previous_a07) or _display_text(previous_group) or _display_text(previous_tags):
        current_lines.extend(
            [
                "Historikk:",
                f"A07: {_display_text(previous_a07) or '-'}",
                f"RF-1022: {_display_text(previous_group) or '-'}",
                f"Flagg: {_display_text(previous_tags) or '-'}",
            ]
        )

    suggested_lines = [_guided_next_step_text(item)]
    if suggested_summary == "Ingen forslag" and (
        _display_text(current_a07) or _display_text(current_group) or _display_text(current_tags)
    ):
        suggested_lines.append("Forslag: Ingen nytt forslag - lagret klassifisering brukes")
    else:
        suggested_lines.append(f"Forslag: {suggested_summary}")
    if item.confidence_bucket:
        if item.confidence_label:
            suggested_lines.append(f"Tillit: {item.confidence_bucket} ({item.confidence_label})")
        else:
            suggested_lines.append(f"Tillit: {item.confidence_bucket}")

    why_lines: list[str] = []
    if item.issue_text:
        why_lines.append(f"Problem: {item.issue_text}")
    for label, field_state in (
        ("A07", suggested_a07),
        ("RF-1022", suggested_group),
        ("Flagg", suggested_tags),
    ):
        why_line = _field_why_line(label, field_state)
        if why_line:
            why_lines.append(why_line)
    for group_label, blocking_term in tuple(getattr(item, "rf1022_exclude_blocks", ()) or ()):
        label = _clean_text(group_label)
        term = _clean_text(blocking_term)
        if not label or not term:
            continue
        why_lines.append(f"Blokkert av ekskluder-alias: {term} (ville ellers truffet {label})")
    if not why_lines:
        why_lines.append("Ingen sterke signaler. Vurder kontoen manuelt i klassifisering.")
    control_group_text = _display_text(current_group) or _display_text(suggested_group)
    treatment_text = ""
    if control_group_text:
        try:
            from a07_feature.page_control_data import format_rf1022_treatment_text

            treatment_text = format_rf1022_treatment_text(
                account_no=item.account_no,
                account_name=item.account_name,
                ib=item.ib,
                endring=item.movement,
                ub=item.ub,
                post_text=control_group_text,
            )
        except Exception:
            treatment_text = ""
    return {
        "headline": f"{item.account_no} | {item.account_name or 'Uten navn'} | Status: {item.status_label}",
        "current": "\n".join(current_lines),
        "suggested": "\n".join(suggested_lines),
        "why": "\n".join(why_lines),
        "treatment": treatment_text or "RF-1022-behandling er ikke avklart ennå.",
        "next": item.next_action_label,
    }


def build_code_workspace_state(
    mapping_current: Mapping[str, str],
    items_by_account: Mapping[str, ClassificationWorkspaceItem],
) -> dict[str, dict[str, object]]:
    state_by_code: dict[str, dict[str, object]] = {}
    for account_no, mapped_code in (mapping_current or {}).items():
        account_s = _clean_text(account_no)
        code_s = _clean_text(mapped_code)
        item = items_by_account.get(account_s)
        if not account_s or not code_s or item is None:
            continue
        bucket = state_by_code.setdefault(
            code_s,
            {
                "sources": set(),
                "confidence": None,
                "locked": False,
                "missing_control_group": False,
                "missing_control_tags": False,
                "control_conflict": False,
                "queue_names": set(),
                "why_summary": [],
            },
        )
        source = _clean_text(item.current.a07_code.provenance.source if item.current.a07_code.provenance else item.current.source)
        if source:
            cast_sources = bucket["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add(source)
        if item.confidence is not None:
            try:
                current_conf = bucket.get("confidence")
                bucket["confidence"] = max(float(current_conf or 0.0), float(item.confidence))
            except Exception:
                bucket["confidence"] = item.confidence
        if item.current.locked:
            bucket["locked"] = True
        expected_group = payroll_classification.control_group_for_code(code_s)
        required_tags = set(payroll_classification.required_control_tags_for_code(code_s))
        current_group = _clean_text(item.current.control_group.value)
        current_tags = {
            _clean_text(tag)
            for tag in (item.current.control_tags.value if isinstance(item.current.control_tags.value, tuple) else ())
            if _clean_text(tag)
        }
        if expected_group and not current_group:
            bucket["missing_control_group"] = True
        if expected_group and current_group and current_group != expected_group:
            bucket["control_conflict"] = True
        if required_tags and not required_tags.issubset(current_tags):
            bucket["missing_control_tags"] = True
        queue_names = bucket["queue_names"]
        assert isinstance(queue_names, set)
        queue_names.add(item.queue_name)
        why_summary = _clean_text(item.why_summary or item.issue_text)
        if why_summary:
            cast_why = bucket["why_summary"]
            assert isinstance(cast_why, list)
            if why_summary not in cast_why:
                cast_why.append(why_summary)

    normalized: dict[str, dict[str, object]] = {}
    for code, raw in state_by_code.items():
        sources = {str(value).strip() for value in raw.get("sources", set()) if str(value).strip()}
        if sources == {"history"}:
            source = "history"
        elif "manual" in sources:
            source = "manual"
        elif "legacy" in sources and sources == {"legacy"}:
            source = "legacy"
        elif "history" in sources:
            source = "manual"
        else:
            source = next(iter(sorted(sources)), "unknown")
        normalized[code] = {
            "source": source,
            "sources": tuple(sorted(sources)),
            "confidence": raw.get("confidence"),
            "locked": bool(raw.get("locked", False)),
            "missing_control_group": bool(raw.get("missing_control_group", False)),
            "missing_control_tags": bool(raw.get("missing_control_tags", False)),
            "control_conflict": bool(raw.get("control_conflict", False)),
            "queue_names": tuple(sorted(str(value) for value in raw.get("queue_names", set()))),
            "why_summary": " | ".join(list(raw.get("why_summary", []))[:3]),
        }
    return normalized
