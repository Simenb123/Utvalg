from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import pandas as pd

import account_detail_classification
import classification_config
import classification_workspace
import formatting
import konto_klassifisering
import preferences
import payroll_classification
import payroll_feedback
import session
from a07_feature import build_account_usage_features
from a07_feature import page_control_data as control_data
from analyse_mapping_service import UnmappedAccountIssue

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore


log = logging.getLogger(__name__)


ALL_COLUMNS = (
    "Konto",
    "Kontonavn",
    "Gruppe",
    "Nåværende",
    "Forslag",
    "Status",
    "A07-kode",
    "A07-forslag",
    "A07 OK",
    "RF-1022-post",
    "RF-1022-forslag",
    "RF-1022 OK",
    "Lønnsflagg",
    "Flagg-forslag",
    "Lønnsstatus",
    "Matchgrunnlag",
    "Problem",
    "Profilkilde",
    "Sikkerhet",
    "Låst",
    "IB",
    "Endring",
    "UB",
    "Antall",
    "Regnskapslinje",
    "Mappingstatus",
    "Regnr",
    "Kilde",
    "Tilleggspostering",
    "UB før ÅO",
    "UB etter ÅO",
    "Detaljklassifisering",
    "Eid selskap",
)

PAYROLL_COLUMNS = (
    "Nåværende",
    "Forslag",
    "Status",
    "A07-kode",
    "A07-forslag",
    "A07 OK",
    "RF-1022-post",
    "RF-1022-forslag",
    "RF-1022 OK",
    "Lønnsflagg",
    "Flagg-forslag",
    "Lønnsstatus",
    "Matchgrunnlag",
    "Problem",
    "Profilkilde",
    "Sikkerhet",
    "Låst",
)

DEFAULT_VISIBLE_COLUMNS = (
    "Konto",
    "Kontonavn",
    "Gruppe",
    "IB",
    "Endring",
    "UB",
    "Antall",
    "Regnskapslinje",
    "Mappingstatus",
)

DEFAULT_COLUMN_ORDER = ALL_COLUMNS

NUMERIC_COLUMNS = {
    "IB",
    "Endring",
    "UB",
    "Antall",
    "Tilleggspostering",
    "UB før ÅO",
    "UB etter ÅO",
}

COLUMN_WIDTHS = {
    "Konto": 85,
    "Kontonavn": 260,
    "Gruppe": 150,
    "Nåværende": 240,
    "Forslag": 240,
    "Status": 130,
    "A07-kode": 170,
    "A07-forslag": 170,
    "A07 OK": 65,
    "RF-1022-post": 170,
    "Lønnsflagg": 220,
    "RF-1022-forslag": 170,
    "RF-1022 OK": 80,
    "Flagg-forslag": 220,
    "Lønnsstatus": 110,
    "Matchgrunnlag": 260,
    "Problem": 220,
    "Profilkilde": 95,
    "Sikkerhet": 90,
    "Låst": 65,
    "IB": 110,
    "Endring": 110,
    "UB": 110,
    "Antall": 70,
    "Regnskapslinje": 220,
    "Mappingstatus": 110,
    "Regnr": 70,
    "Kilde": 80,
    "Tilleggspostering": 125,
    "UB før ÅO": 120,
    "UB etter ÅO": 120,
    "Detaljklassifisering": 200,
    "Eid selskap": 220,
}

MAPPING_STATUS_LABELS = {
    "interval": "Intervall",
    "override": "Overstyrt",
    "unmapped": "Umappet",
    "sumline": "Sumpost",
}

SOURCE_LABELS = {
    "HB": "HB",
    "SB": "SB",
    "AO_ONLY": "Kun ÅO",
}

FILTER_ALL = "Alle"
PRESET_CUSTOM = "Egendefinert"
WORK_MODE_STANDARD = "Standard"
WORK_MODE_PAYROLL = "Lønnsklassifisering"
WORK_MODE_OPTIONS = (WORK_MODE_STANDARD, WORK_MODE_PAYROLL)
PAYROLL_QUEUE_OPTIONS = (
    FILTER_ALL,
    classification_workspace.QUEUE_SUSPICIOUS,
    classification_workspace.QUEUE_READY,
    classification_workspace.QUEUE_HISTORY,
    classification_workspace.QUEUE_REVIEW,
    classification_workspace.QUEUE_UNMAPPED,
    classification_workspace.QUEUE_LOCKED,
)

COLUMN_PRESETS = {
    "Standard": DEFAULT_VISIBLE_COLUMNS,
    "Lønnsklassifisering": (
        "Konto",
        "Kontonavn",
        "IB",
        "Endring",
        "UB",
        "A07-kode",
        "A07-forslag",
        "A07 OK",
        "RF-1022-post",
        "RF-1022-forslag",
        "RF-1022 OK",
        "Status",
    ),
    "Lønn/A07": (
        "Konto",
        "Kontonavn",
        "Endring",
        "UB",
        "A07-kode",
        "A07-forslag",
        "RF-1022-post",
        "RF-1022-forslag",
        "Lønnsstatus",
        "Matchgrunnlag",
        "Problem",
    ),
    "Mapping": (
        "Konto",
        "Kontonavn",
        "UB",
        "Gruppe",
        "Regnskapslinje",
        "Mappingstatus",
        "Regnr",
        "Kilde",
        "Antall",
    ),
    "ÅO": (
        "Konto",
        "Kontonavn",
        "UB før ÅO",
        "Tilleggspostering",
        "UB etter ÅO",
        "Mappingstatus",
        "Regnskapslinje",
        "Kilde",
    ),
    "Kontroll": (
        "Konto",
        "Kontonavn",
        "Gruppe",
        "IB",
        "Endring",
        "UB",
        "Antall",
        "Regnskapslinje",
        "Mappingstatus",
        "Regnr",
        "Kilde",
        "Tilleggspostering",
    ),
}

PRESET_OPTIONS = tuple([*COLUMN_PRESETS.keys(), PRESET_CUSTOM])
MAPPING_STATUS_OPTIONS = (FILTER_ALL, "Intervall", "Overstyrt", "Umappet", "Sumpost")
SOURCE_OPTIONS = (FILTER_ALL, "HB", "SB", "Kun ÅO")
PAYROLL_SCOPE_OPTIONS = PAYROLL_QUEUE_OPTIONS


def _suggestion_grid_value(
    *,
    label: str,
    item: classification_workspace.ClassificationWorkspaceItem | None,
    suggested_display: str,
) -> str:
    suggested_text = str(suggested_display or "").strip()
    if item is None:
        return suggested_text
    field_pairs = {
        "A07": item.current.a07_code,
        "RF-1022": item.current.control_group,
        "Flagg": item.current.control_tags,
    }
    current_state = field_pairs.get(label)
    current_text = str(getattr(current_state, "display", "") or "").strip() if current_state is not None else ""
    matching_labels = classification_workspace.matching_suggestion_labels(item)
    if label in matching_labels:
        return suggested_text or current_text
    if (
        current_state is not None
        and bool(current_text)
        and not bool(getattr(item.queue_state, "suspicious_saved", False))
        and label not in classification_workspace.actionable_suggestion_labels(item)
    ):
        return suggested_text or current_text
    if label in classification_workspace.actionable_suggestion_labels(item):
        return suggested_text
    return suggested_text


def _normalize_classification_field_value(value: object) -> object:
    if isinstance(value, tuple):
        return tuple(sorted(str(part or "").strip() for part in value if str(part or "").strip()))
    return str(value or "").strip()


def _suggested_update_for_item(
    item: classification_workspace.ClassificationWorkspaceItem | None,
) -> dict[str, object]:
    if item is None:
        return {}
    updates: dict[str, object] = {}
    for field_name, current_state, suggested_state in (
        ("a07_code", item.current.a07_code, item.suggested.a07_code),
        ("control_group", item.current.control_group, item.suggested.control_group),
        ("control_tags", item.current.control_tags, item.suggested.control_tags),
    ):
        if suggested_state is None:
            continue
        suggested_value = _normalize_classification_field_value(suggested_state.value)
        if isinstance(suggested_value, tuple):
            if not suggested_value:
                continue
        elif not suggested_value:
            continue
        current_value = _normalize_classification_field_value(current_state.value)
        if current_value == suggested_value:
            continue
        updates[field_name] = suggested_state.value
    return updates


@dataclass(frozen=True)
class SaldobalansePayload:
    df: pd.DataFrame
    profile_document: Any
    history_document: Any
    catalog: Any
    suggestions: dict[str, payroll_classification.PayrollSuggestionResult]
    classification_items: dict[str, classification_workspace.ClassificationWorkspaceItem]


@dataclass(frozen=True)
class SaldobalanseBasePayload:
    """Expensive decorated base — computed once per (dataset, cheap-filter, include_payroll) key.

    Reused across pure-postprocess refreshes (search text, payroll_scope) so that typing
    in the search field does not rebuild the payroll/workspace pipeline.
    """

    df: pd.DataFrame  # merged + cheap-filtered + payroll-decorated, pre-search/scope/sort
    profile_document: Any
    history_document: Any
    catalog: Any
    suggestions: dict[str, payroll_classification.PayrollSuggestionResult]
    classification_items: dict[str, classification_workspace.ClassificationWorkspaceItem]
    include_payroll: bool


def _ordered_columns_for_visible(visible_cols: list[str] | tuple[str, ...]) -> list[str]:
    ordered = [col for col in visible_cols if col in ALL_COLUMNS]
    for col in ALL_COLUMNS:
        if col not in ordered:
            ordered.append(col)
    return ordered


def _preset_name_for_visible_columns(visible_cols: list[str] | tuple[str, ...]) -> str:
    cleaned = [col for col in visible_cols if col in ALL_COLUMNS]
    for preset_name, preset_cols in COLUMN_PRESETS.items():
        if cleaned == list(preset_cols):
            return preset_name
    return PRESET_CUSTOM


def _resolve_sb_views(analyse_page: Any) -> tuple[Optional[pd.DataFrame], Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    try:
        import page_analyse_rl

        return page_analyse_rl._resolve_analysis_sb_views(page=analyse_page)
    except Exception:
        base_sb_df = getattr(analyse_page, "_rl_sb_df", None)
        try:
            effective_sb_df = analyse_page._get_effective_sb_df()
        except Exception:
            effective_sb_df = base_sb_df
        return base_sb_df, effective_sb_df, effective_sb_df


def _resolve_sb_columns(sb_df: pd.DataFrame) -> dict[str, str]:
    try:
        import page_analyse_sb

        return page_analyse_sb._resolve_sb_columns(sb_df)
    except Exception:
        col_map: dict[str, str] = {}
        for col in sb_df.columns:
            lowered = str(col).strip().lower()
            if lowered == "konto":
                col_map["konto"] = col
            elif lowered == "kontonavn":
                col_map["kontonavn"] = col
            elif lowered == "ib":
                col_map["ib"] = col
            elif lowered in {"netto", "endring"}:
                col_map["endring"] = col
            elif lowered == "ub":
                col_map["ub"] = col
        return col_map


def _normalize_sb_frame(sb_df: Optional[pd.DataFrame], *, suffix: str) -> pd.DataFrame:
    columns = [
        "Konto",
        f"Kontonavn_{suffix}",
        f"IB_{suffix}",
        f"Endring_{suffix}",
        f"UB_{suffix}",
    ]
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return pd.DataFrame(columns=columns)

    col_map = _resolve_sb_columns(sb_df)
    konto_col = col_map.get("konto")
    if not konto_col:
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame({"Konto": sb_df[konto_col].astype(str).str.strip()})
    frame[f"Kontonavn_{suffix}"] = (
        sb_df[col_map["kontonavn"]].fillna("").astype(str)
        if "kontonavn" in col_map
        else ""
    )
    frame[f"IB_{suffix}"] = (
        pd.to_numeric(sb_df[col_map["ib"]], errors="coerce").fillna(0.0)
        if "ib" in col_map
        else 0.0
    )
    ub_values = (
        pd.to_numeric(sb_df[col_map["ub"]], errors="coerce").fillna(0.0)
        if "ub" in col_map
        else pd.Series(0.0, index=sb_df.index)
    )
    frame[f"UB_{suffix}"] = ub_values
    if "endring" in col_map:
        frame[f"Endring_{suffix}"] = pd.to_numeric(sb_df[col_map["endring"]], errors="coerce").fillna(0.0)
    else:
        frame[f"Endring_{suffix}"] = ub_values - frame[f"IB_{suffix}"]

    out = (
        frame.groupby("Konto", as_index=False)
        .agg(
            **{
                f"Kontonavn_{suffix}": (f"Kontonavn_{suffix}", "first"),
                f"IB_{suffix}": (f"IB_{suffix}", "sum"),
                f"Endring_{suffix}": (f"Endring_{suffix}", "sum"),
                f"UB_{suffix}": (f"UB_{suffix}", "sum"),
            }
        )
    )
    return out


def _first_text_value(values: pd.Series) -> str:
    for value in values.tolist():
        text = str(value or "").strip()
        if text and text.lower() not in {"nan", "none", "<na>"}:
            return text
    return ""


def _build_hb_counts(hb_df: Any) -> pd.DataFrame:
    if hb_df is None or not isinstance(hb_df, pd.DataFrame) or hb_df.empty or "Konto" not in hb_df.columns:
        return pd.DataFrame(columns=["Konto", "Antall"])

    frame = pd.DataFrame({"Konto": hb_df["Konto"].astype(str).str.strip()})
    frame["Antall"] = 1
    return frame.groupby("Konto", as_index=False).agg(Antall=("Antall", "sum"))


def _load_mapping_issues(analyse_page: Any) -> list[UnmappedAccountIssue]:
    try:
        import analyse_mapping_service

        return analyse_mapping_service.build_page_mapping_issues(analyse_page, use_filtered_hb=False)
    except Exception as exc:
        log.debug("Kunne ikke bygge mapping-issues for Saldobalanse: %s", exc)
        return []


def _load_group_mapping(client: str) -> dict[str, str]:
    if not client:
        return {}
    try:
        import konto_klassifisering

        return konto_klassifisering.load(client)
    except Exception:
        return {}


def _group_label(group_id: str) -> str:
    if not group_id:
        return ""
    try:
        return konto_klassifisering.group_label(group_id) or group_id
    except Exception:
        return group_id


def _session_year() -> int | None:
    raw_year = getattr(session, "year", None)
    try:
        return int(str(raw_year).strip()) if str(raw_year).strip() else None
    except Exception:
        return None


def _load_account_profile_document_only(client: str, year: int | None) -> Any:
    """Last kun profil-dokumentet for aktiv klient/år — uten historikk og katalog.

    Brukes av `include_payroll=False`-banen for å kunne vise lagrede overstyringer
    (detail_class_id, owned_company_orgnr) uten å kjøre hele lønns-konteksten.
    """

    if not client:
        return None
    try:
        return konto_klassifisering.load_document(client, year=year)
    except Exception:
        return None


def _load_payroll_context(client: str, year: int | None) -> tuple[Any, Any, Any]:
    if not client:
        return None, None, None
    try:
        document = konto_klassifisering.load_document(client, year=year)
    except Exception:
        document = None
    history_document = None
    if year:
        try:
            history_document = konto_klassifisering.load_document(client, year=year - 1)
        except Exception:
            history_document = None
    try:
        catalog = konto_klassifisering.load_catalog()
    except Exception:
        catalog = None
    return document, history_document, catalog


def _resolve_payroll_usage_features(analyse_page: Any) -> dict[str, Any]:
    dataset = getattr(analyse_page, "dataset", None)
    if isinstance(dataset, pd.DataFrame) and not dataset.empty:
        try:
            return build_account_usage_features(dataset)
        except Exception:
            return {}
    fallback = getattr(session, "dataset", None)
    if isinstance(fallback, pd.DataFrame) and not fallback.empty:
        try:
            return build_account_usage_features(fallback)
        except Exception:
            return {}
    return {}


def _top_payroll_suggestion(
    result: payroll_classification.PayrollSuggestionResult | None,
) -> Any:
    if result is None or not result.suggestions:
        return None
    ranked = sorted(
        result.suggestions.values(),
        key=lambda suggestion: (
            0 if payroll_classification.is_strict_auto_suggestion(suggestion) else 1,
            -(float(suggestion.confidence or 0.0)),
            suggestion.field_name,
        ),
    )
    return ranked[0] if ranked else None


def _payroll_problem_text(
    result: payroll_classification.PayrollSuggestionResult | None,
    top_suggestion: Any,
) -> str:
    problem = str(getattr(result, "unclear_reason", "") or "").strip()
    if problem:
        return problem
    return str(getattr(top_suggestion, "reason", "") or "").strip()


def _suggestion_reason_text(suggestion: Any) -> str:
    reason = str(getattr(suggestion, "reason", "") or "").strip()
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
        alias_match = re.search(r"(?:navn|tekst)\s*\(([^)]+)\)", reason, flags=re.IGNORECASE)
        if "konto-intervall" in reason_lower:
            compact_parts.append("konto-intervall")
        if any(marker in reason_lower for marker in ("eksplisitt kontotreff", "motkonto", "boost", "intervall", "historikk")):
            compact_parts.append("kontobruk")
        if alias_match:
            alias_values = [part.strip() for part in alias_match.group(1).split(",") if part.strip()]
            alias_label = alias_values[0] if alias_values else ""
            compact_parts.append(f"navn/alias: {alias_label}" if alias_label else "navn/alias")
        elif any(marker in reason_lower for marker in ("navn (", "tekst (")):
            compact_parts.append("navn/alias")
        if "periodisitet" in reason_lower:
            compact_parts.append("periodisitet")
        if "beløp/sign" in reason_lower:
            compact_parts.append("beløp/sign")
        if compact_parts:
            return f"Regelbok: {', '.join(compact_parts)}"
        return "Regelbok"
    if reason:
        return reason
    source = str(getattr(suggestion, "source", "") or "").strip()
    if source == "history":
        return "Historikk"
    if source == "manual":
        return "Manuell"
    if source == "legacy":
        return "Legacy"
    return source.capitalize() if source else ""


def _payroll_match_basis_text(
    result: payroll_classification.PayrollSuggestionResult | None,
) -> str:
    if result is None or not result.suggestions:
        return ""

    suggestion_map = dict(result.suggestions)
    parts: list[str] = []

    a07_suggestion = suggestion_map.get("a07_code")
    if a07_suggestion is not None:
        reason = _suggestion_reason_text(a07_suggestion)
        if reason:
            parts.append(f"A07: {reason}")

    grouped_fields: list[tuple[str, str]] = []
    for field_name, label in (
        ("control_group", "RF-1022"),
        ("control_tags", "Flagg"),
    ):
        suggestion = suggestion_map.get(field_name)
        if suggestion is None:
            continue
        reason = _suggestion_reason_text(suggestion)
        if reason:
            grouped_fields.append((label, reason))

    if len(grouped_fields) == 2 and grouped_fields[0][1] == grouped_fields[1][1]:
        parts.append(f"RF-1022/Flagg: {grouped_fields[0][1]}")
    else:
        for label, reason in grouped_fields:
            parts.append(f"{label}: {reason}")

    return " | ".join(parts)


def _rf1022_treatment_text(
    account_no: object,
    account_name: object,
    *,
    ib: object,
    endring: object,
    ub: object,
    rf1022_text: object = "",
) -> str:
    return control_data.format_rf1022_treatment_text(
        account_no=account_no,
        account_name=account_name,
        ib=ib,
        endring=endring,
        ub=ub,
        group_id="",
        post_text=rf1022_text,
    )

    def _amount_or_zero(value: object) -> float:
        try:
            numeric = pd.to_numeric([value], errors="coerce")[0]
        except Exception:
            return 0.0
        try:
            if pd.isna(numeric):
                return 0.0
        except Exception:
            return 0.0
        try:
            return float(numeric)
        except Exception:
            return 0.0

    account_s = str(account_no or "").strip()
    account_name_s = str(account_name or "").strip()
    rf1022_s = str(rf1022_text or "").strip()
    ib_value = _amount_or_zero(ib)
    endring_value = _amount_or_zero(endring)
    ub_value = _amount_or_zero(ub)
    normalized = f"{account_s} {account_name_s}".casefold()

    if "refusjon" in rf1022_s.casefold():
        return f"RF-1022: Endring -> refusjon/grunnlag {formatting.fmt_amount(endring_value)}"
    if "pensjon" in rf1022_s.casefold():
        return f"RF-1022: Endring -> pensjonsgrunnlag {formatting.fmt_amount(endring_value)}"

    is_accrual_account = account_s.startswith("29") or any(
        token in normalized
        for token in (
            "skyldig",
            "avsatt",
            "avsetning",
            "påløpt",
            "pålop",
            "palopt",
            "feriepengegjeld",
        )
    )
    if is_accrual_account:
        addition = abs(ib_value)
        deduction = abs(ub_value)
        net = addition - deduction
        return (
            "RF-1022: +|IB| "
            f"{formatting.fmt_amount(addition)} - |UB| {formatting.fmt_amount(deduction)}"
            f" = {formatting.fmt_amount(net)}"
        )

    return f"RF-1022: Endring -> kostnadsført {formatting.fmt_amount(endring_value)}"


STALE_OWNED_COMPANY_LABEL = "utgått kobling"


def _load_owned_company_name_map(client: str, year: int | None) -> dict[str, str]:
    """Returner orgnr (kun siffer) -> selskapsnavn for aktiv klients eide selskaper.

    Returnerer tom dict hvis klient eller år mangler, eller hvis AR-oppslaget feiler.
    """

    if not client:
        return {}
    try:
        import ar_store
    except Exception:
        return {}
    try:
        overview = ar_store.get_client_ownership_overview(client, str(year or ""))
    except Exception:
        return {}
    mapping: dict[str, str] = {}
    rows = overview.get("owned_companies", []) if isinstance(overview, dict) else []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        orgnr_raw = row.get("company_orgnr")
        digits = "".join(ch for ch in str(orgnr_raw or "") if ch.isdigit())
        if not digits:
            continue
        name = str(row.get("company_name") or "").strip()
        if name:
            mapping[digits] = name
    return mapping


def _format_owned_company_display(
    orgnr: str,
    ownership_map: dict[str, str],
) -> str:
    cleaned = "".join(ch for ch in str(orgnr or "") if ch.isdigit())
    if not cleaned:
        return ""
    name = ownership_map.get(cleaned)
    if name:
        return f"{name} ({cleaned})"
    return f"{STALE_OWNED_COMPANY_LABEL} ({cleaned})"


def _decorate_with_detail_class_and_ownership(
    merged: pd.DataFrame,
    *,
    profile_document: Any,
    ownership_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Alltid-på-kolonner: Detaljklassifisering + Eid selskap.

    Leser override fra `AccountProfile.detail_class_id` / `.owned_company_orgnr`
    og faller tilbake på global regelmatch for detaljklasse.
    """

    if merged.empty:
        work = merged.copy()
        work["Detaljklassifisering"] = ""
        work["Eid selskap"] = ""
        return work

    try:
        catalog = account_detail_classification.load_detail_class_catalog()
    except Exception:
        catalog = []

    map_lookup: dict[str, str] = dict(ownership_map or {})

    detail_values: list[str] = []
    owned_values: list[str] = []
    for _, row in merged.iterrows():
        konto = str(row.get("Konto") or "").strip()
        name = str(row.get("Kontonavn") or "").strip()
        profile = profile_document.get(konto) if profile_document is not None and konto else None
        profile_override = str(getattr(profile, "detail_class_id", "") or "") if profile else ""
        class_id = account_detail_classification.resolve_detail_class_for_account(
            profile_override, konto, name, catalog
        )
        detail_values.append(
            account_detail_classification.format_detail_class_label(class_id, catalog)
            if class_id
            else ""
        )
        profile_orgnr = str(getattr(profile, "owned_company_orgnr", "") or "") if profile else ""
        owned_values.append(_format_owned_company_display(profile_orgnr, map_lookup))

    work = merged.copy()
    work["Detaljklassifisering"] = detail_values
    work["Eid selskap"] = owned_values
    return work


def _apply_blank_payroll_columns(
    merged: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    Any,
    Any,
    Any,
    dict[str, payroll_classification.PayrollSuggestionResult],
    dict[str, classification_workspace.ClassificationWorkspaceItem],
]:
    work = merged.copy()
    for column in PAYROLL_COLUMNS:
        work[column] = ""
    work["_payroll_relevant"] = False
    work["_payroll_has_suggestions"] = False
    work["_payroll_locked"] = False
    work["_payroll_unmapped"] = False
    work["_payroll_unclear"] = False
    work["_payroll_suspicious_saved"] = False
    return work, None, None, None, {}, {}


def _decorate_with_payroll_columns(
    merged: pd.DataFrame,
    *,
    client: str,
    year: int | None,
    usage_features: dict[str, Any] | None = None,
    preloaded_context: tuple[Any, Any, Any] | None = None,
) -> tuple[
    pd.DataFrame,
    Any,
    Any,
    Any,
    dict[str, payroll_classification.PayrollSuggestionResult],
    dict[str, classification_workspace.ClassificationWorkspaceItem],
]:
    if preloaded_context is not None:
        document, history_document, catalog = preloaded_context
    else:
        document, history_document, catalog = _load_payroll_context(client, year)
    suggestions: dict[str, payroll_classification.PayrollSuggestionResult] = {}
    items: dict[str, classification_workspace.ClassificationWorkspaceItem] = {}
    if merged.empty:
        work, _, _, _, _, _ = _apply_blank_payroll_columns(merged)
        work["_payroll_unmapped"] = True
        return work, document, history_document, catalog, suggestions, items

    if document is not None:
        items = classification_workspace.build_workspace_items(
            merged[["Konto", "Kontonavn", "Endring", "UB"]],
            document=document,
            history_document=history_document,
            catalog=catalog,
            usage_features=usage_features,
        )
        suggestions = {
            account_no: item.result
            for account_no, item in items.items()
            if item.result is not None
        }

    work = merged.copy()
    current_summary_values: list[str] = []
    suggested_summary_values: list[str] = []
    status_label_values: list[str] = []
    a07_values: list[str] = []
    a07_suggestion_values: list[str] = []
    a07_ok_values: list[str] = []
    rf1022_values: list[str] = []
    rf1022_suggestion_values: list[str] = []
    rf1022_ok_values: list[str] = []
    tag_values: list[str] = []
    tag_suggestion_values: list[str] = []
    status_values: list[str] = []
    match_basis_values: list[str] = []
    problem_values: list[str] = []
    source_values: list[str] = []
    confidence_values: list[str] = []
    locked_values: list[str] = []
    payroll_relevant_values: list[bool] = []
    payroll_suggestion_values: list[bool] = []
    payroll_locked_values: list[bool] = []
    payroll_unmapped_values: list[bool] = []
    payroll_unclear_values: list[bool] = []
    payroll_suspicious_values: list[bool] = []

    for _, row in work.iterrows():
        konto = str(row.get("Konto") or "").strip()
        profile = document.get(konto) if document is not None and konto else None
        item = items.get(konto)
        result = suggestions.get(konto)
        suggestion_map = dict(result.suggestions) if result is not None else {}

        actual_a07 = str(getattr(profile, "a07_code", "") or "").strip()
        actual_group_id = str(getattr(profile, "control_group", "") or "").strip()
        actual_group = payroll_classification.format_control_group(actual_group_id, catalog)
        actual_tags = payroll_classification.format_control_tags(getattr(profile, "control_tags", ()), catalog)

        suggested_a07 = ""
        if "a07_code" in suggestion_map and isinstance(suggestion_map["a07_code"].value, str):
            suggested_a07 = str(suggestion_map["a07_code"].value or "").strip()
        suggested_group = ""
        if "control_group" in suggestion_map and isinstance(suggestion_map["control_group"].value, str):
            suggested_group = payroll_classification.format_control_group(
                str(suggestion_map["control_group"].value or "").strip(),
                catalog,
            )
        suggested_tags = ""
        if "control_tags" in suggestion_map and isinstance(suggestion_map["control_tags"].value, tuple):
            suggested_tags = payroll_classification.format_control_tags(
                suggestion_map["control_tags"].value,
                catalog,
            )

        top_suggestion = _top_payroll_suggestion(result)
        confidence = getattr(profile, "confidence", None)
        if confidence is None and top_suggestion is not None:
            confidence = top_suggestion.confidence

        payroll_status = result.payroll_status if result is not None else ""
        profile_source = payroll_classification.profile_source_label(profile)
        locked = bool(getattr(profile, "locked", False))
        missing_a07 = not actual_a07
        missing_group = not actual_group_id
        has_suggestions = bool(suggestion_map)
        payroll_relevant = bool(result.payroll_relevant) if result is not None else False
        suspicious_issue = item.issue_text if item is not None else payroll_classification.suspicious_saved_payroll_profile_issue(
            account_no=konto,
            account_name=str(row.get("Kontonavn") or "").strip(),
            current_profile=profile,
        )
        matching_labels = classification_workspace.matching_suggestion_labels(item) if item is not None else set()
        current_summary_values.append(item.current_summary if item is not None else "")
        suggested_summary_values.append(item.suggested_summary if item is not None else "")
        status_label_values.append(item.status_label if item is not None else payroll_status)
        a07_values.append(actual_a07)
        a07_suggestion_values.append(
            _suggestion_grid_value(label="A07", item=item, suggested_display=suggested_a07)
        )
        a07_ok_values.append("✓" if "A07" in matching_labels else "")
        rf1022_values.append(actual_group)
        rf1022_suggestion_values.append(
            _suggestion_grid_value(label="RF-1022", item=item, suggested_display=suggested_group)
        )
        rf1022_ok_values.append("✓" if "RF-1022" in matching_labels else "")
        tag_values.append(actual_tags)
        tag_suggestion_values.append(
            _suggestion_grid_value(label="Flagg", item=item, suggested_display=suggested_tags)
        )
        status_values.append(payroll_status)
        match_basis_values.append(item.why_summary if item is not None else _payroll_match_basis_text(result))
        problem_values.append(suspicious_issue or _payroll_problem_text(result, top_suggestion))
        source_values.append(profile_source)
        confidence_values.append(payroll_classification.confidence_label(confidence))
        locked_values.append("Ja" if locked else "")
        payroll_relevant_values.append(payroll_relevant)
        payroll_suggestion_values.append(has_suggestions)
        payroll_locked_values.append(locked)
        payroll_unmapped_values.append(missing_a07 or missing_group)
        payroll_unclear_values.append(bool(getattr(result, "is_unclear", False)))
        payroll_suspicious_values.append(bool(suspicious_issue))

    work["Nåværende"] = current_summary_values
    work["Forslag"] = suggested_summary_values
    work["Status"] = status_label_values
    work["A07-kode"] = a07_values
    work["A07-forslag"] = a07_suggestion_values
    work["A07 OK"] = a07_ok_values
    work["RF-1022-post"] = rf1022_values
    work["RF-1022-forslag"] = rf1022_suggestion_values
    work["RF-1022 OK"] = rf1022_ok_values
    work["Lønnsflagg"] = tag_values
    work["Flagg-forslag"] = tag_suggestion_values
    work["Lønnsstatus"] = status_values
    work["Matchgrunnlag"] = match_basis_values
    work["Problem"] = problem_values
    work["Profilkilde"] = source_values
    work["Sikkerhet"] = confidence_values
    work["Låst"] = locked_values
    work["_payroll_relevant"] = payroll_relevant_values
    work["_payroll_has_suggestions"] = payroll_suggestion_values
    work["_payroll_locked"] = payroll_locked_values
    work["_payroll_unmapped"] = payroll_unmapped_values
    work["_payroll_unclear"] = payroll_unclear_values
    work["_payroll_suspicious_saved"] = payroll_suspicious_values
    return work, document, history_document, catalog, suggestions, items


def _build_decorated_base_payload(
    *,
    analyse_page: Any,
    only_unmapped: bool = False,
    include_zero: bool = False,
    mapping_status_filter: str = FILTER_ALL,
    source_filter: str = FILTER_ALL,
    only_with_ao: bool = False,
    include_payroll: bool = True,
    profile_document: Any = None,
    history_document: Any = None,
    catalog: Any = None,
    usage_features: dict[str, Any] | None = None,
) -> SaldobalanseBasePayload:
    """Expensive part — merge + cheap filters + payroll decoration. Cacheable.

    Optional preloaded arguments (``profile_document``, ``history_document``,
    ``catalog``, ``usage_features``) let the page-level caches bypass re-loading
    inside this function. If not given, the existing disk/session loaders are used.
    """
    base_sb_df, adjusted_sb_df, effective_sb_df = _resolve_sb_views(analyse_page)

    effective = _normalize_sb_frame(effective_sb_df, suffix="effective")
    base = _normalize_sb_frame(base_sb_df, suffix="base")
    adjusted = _normalize_sb_frame(adjusted_sb_df, suffix="adjusted")

    if effective.empty and base.empty and adjusted.empty:
        empty_df = pd.DataFrame(columns=ALL_COLUMNS)
        return SaldobalanseBasePayload(
            df=empty_df,
            profile_document=None,
            history_document=None,
            catalog=None,
            suggestions={},
            classification_items={},
            include_payroll=include_payroll,
        )

    merged = effective.merge(base, how="outer", on="Konto").merge(adjusted, how="outer", on="Konto")
    merged["Konto"] = merged["Konto"].fillna("").astype(str).str.strip()
    merged = merged.loc[merged["Konto"] != ""].copy()

    name_cols = [col for col in ("Kontonavn_effective", "Kontonavn_base", "Kontonavn_adjusted") if col in merged.columns]
    if name_cols:
        merged["Kontonavn"] = merged[name_cols].apply(_first_text_value, axis=1)
    else:
        merged["Kontonavn"] = ""

    merged["IB"] = pd.to_numeric(merged.get("IB_effective"), errors="coerce").fillna(0.0)
    merged["Endring"] = pd.to_numeric(merged.get("Endring_effective"), errors="coerce").fillna(0.0)
    merged["UB"] = pd.to_numeric(merged.get("UB_effective"), errors="coerce").fillna(0.0)
    merged["UB før ÅO"] = pd.to_numeric(merged.get("UB_base"), errors="coerce").fillna(merged["UB"])
    merged["UB etter ÅO"] = pd.to_numeric(merged.get("UB_adjusted"), errors="coerce").fillna(merged["UB"])
    merged["Tilleggspostering"] = merged["UB etter ÅO"] - merged["UB før ÅO"]

    hb_counts = _build_hb_counts(getattr(analyse_page, "dataset", None))
    merged = merged.merge(hb_counts, how="left", on="Konto")
    merged["Antall"] = pd.to_numeric(merged.get("Antall"), errors="coerce").fillna(0).astype(int)

    issues = _load_mapping_issues(analyse_page)
    if issues:
        issue_df = pd.DataFrame(
            [
                {
                    "Konto": issue.konto,
                    "Regnskapslinje": issue.regnskapslinje,
                    "Mappingstatus": MAPPING_STATUS_LABELS.get(issue.mapping_status, issue.mapping_status),
                    "Regnr": issue.regnr,
                    "Kilde": SOURCE_LABELS.get(issue.kilde, issue.kilde),
                    "_mapping_status_code": issue.mapping_status,
                }
                for issue in issues
            ]
        )
        merged = merged.merge(issue_df, how="left", on="Konto")
    else:
        merged["Regnskapslinje"] = ""
        merged["Mappingstatus"] = ""
        merged["Regnr"] = pd.Series(dtype="Int64")
        merged["Kilde"] = ""
        merged["_mapping_status_code"] = ""

    client = str(getattr(session, "client", "") or "")
    year = _session_year()
    groups = _load_group_mapping(client)
    merged["Gruppe"] = merged["Konto"].map(lambda konto: _group_label(groups.get(str(konto).strip(), "")))

    # Cheap filters first — narrows payroll decoration to the visible subset.
    if not include_zero:
        has_activity = (
            merged[["IB", "Endring", "UB"]].abs().sum(axis=1) > 0.005
        ) | (merged["Antall"] > 0)
        merged = merged.loc[has_activity].copy()

    if only_unmapped:
        merged = merged.loc[merged["_mapping_status_code"].isin({"unmapped", "sumline"})].copy()

    if mapping_status_filter and mapping_status_filter != FILTER_ALL:
        merged = merged.loc[merged["Mappingstatus"].astype(str) == str(mapping_status_filter)].copy()

    if source_filter and source_filter != FILTER_ALL:
        merged = merged.loc[merged["Kilde"].astype(str) == str(source_filter)].copy()

    if only_with_ao:
        merged = merged.loc[pd.to_numeric(merged["Tilleggspostering"], errors="coerce").fillna(0.0).abs() > 0.005].copy()

    if include_payroll:
        effective_usage = usage_features
        if effective_usage is None:
            effective_usage = _resolve_payroll_usage_features(analyse_page)
        preloaded_ctx: tuple[Any, Any, Any] | None
        if profile_document is not None:
            preloaded_ctx = (profile_document, history_document, catalog)
        else:
            preloaded_ctx = None
        merged, profile_document, history_document, catalog, suggestions, classification_items = _decorate_with_payroll_columns(
            merged,
            client=client,
            year=year,
            usage_features=effective_usage,
            preloaded_context=preloaded_ctx,
        )
    else:
        merged, _, history_document, catalog, suggestions, classification_items = _apply_blank_payroll_columns(merged)
        if profile_document is None:
            profile_document = _load_account_profile_document_only(client, year)

    ownership_map = _load_owned_company_name_map(client, year)
    merged = _decorate_with_detail_class_and_ownership(
        merged,
        profile_document=profile_document,
        ownership_map=ownership_map,
    )

    return SaldobalanseBasePayload(
        df=merged,
        profile_document=profile_document,
        history_document=history_document,
        catalog=catalog,
        suggestions=suggestions,
        classification_items=classification_items,
        include_payroll=include_payroll,
    )


def build_saldobalanse_payload(
    *,
    analyse_page: Any,
    search_text: str = "",
    only_unmapped: bool = False,
    include_zero: bool = False,
    mapping_status_filter: str = FILTER_ALL,
    source_filter: str = FILTER_ALL,
    only_with_ao: bool = False,
    payroll_scope: str = FILTER_ALL,
    include_payroll: bool = True,
    base_payload: SaldobalanseBasePayload | None = None,
) -> SaldobalansePayload:
    """Build the final payload. If ``base_payload`` is provided, skip the expensive
    merge + cheap-filter + payroll-decorate step and apply only search / payroll_scope / sort.

    Callers with a fresh/cached base_payload must pre-validate that the cached payload
    was built with the same cheap-filter + include_payroll inputs.
    """
    if base_payload is None:
        base_payload = _build_decorated_base_payload(
            analyse_page=analyse_page,
            only_unmapped=only_unmapped,
            include_zero=include_zero,
            mapping_status_filter=mapping_status_filter,
            source_filter=source_filter,
            only_with_ao=only_with_ao,
            include_payroll=include_payroll,
        )

    merged = base_payload.df
    profile_document = base_payload.profile_document
    history_document = base_payload.history_document
    catalog = base_payload.catalog
    suggestions = base_payload.suggestions
    classification_items = base_payload.classification_items

    if merged.empty:
        return SaldobalansePayload(
            df=merged.reindex(columns=ALL_COLUMNS, fill_value="").reset_index(drop=True)
            if not merged.empty
            else pd.DataFrame(columns=ALL_COLUMNS),
            profile_document=profile_document,
            history_document=history_document,
            catalog=catalog,
            suggestions=suggestions,
            classification_items=classification_items,
        )

    payroll_scope_s = str(payroll_scope or FILTER_ALL).strip()
    if payroll_scope_s != FILTER_ALL:
        allowed_accounts = {
            account_no
            for account_no, item in classification_items.items()
            if classification_workspace.queue_matches(item, payroll_scope_s)
        }
        if allowed_accounts:
            merged = merged.loc[merged["Konto"].astype(str).isin(allowed_accounts)].copy()
        else:
            merged = merged.iloc[0:0].copy()

    search = str(search_text or "").strip().lower()
    if search:
        haystack = (
            merged["Konto"].astype(str)
            + " "
            + merged["Kontonavn"].astype(str)
            + " "
            + merged["Gruppe"].fillna("").astype(str)
            + " "
            + merged["Nåværende"].fillna("").astype(str)
            + " "
            + merged["Forslag"].fillna("").astype(str)
            + " "
            + merged["Status"].fillna("").astype(str)
            + " "
            + merged["A07-kode"].fillna("").astype(str)
            + " "
            + merged["A07-forslag"].fillna("").astype(str)
            + " "
            + merged["RF-1022-post"].fillna("").astype(str)
            + " "
            + merged["RF-1022-forslag"].fillna("").astype(str)
            + " "
            + merged["Lønnsflagg"].fillna("").astype(str)
            + " "
            + merged["Flagg-forslag"].fillna("").astype(str)
            + " "
            + merged["Lønnsstatus"].fillna("").astype(str)
            + " "
            + merged["Matchgrunnlag"].fillna("").astype(str)
            + " "
            + merged["Problem"].fillna("").astype(str)
            + " "
            + merged["Regnskapslinje"].fillna("").astype(str)
            + " "
            + merged["Mappingstatus"].fillna("").astype(str)
        ).str.lower()
        merged = merged.loc[haystack.str.contains(search, na=False)].copy()

    try:
        merged["_konto_num"] = pd.to_numeric(merged["Konto"], errors="coerce")
        merged = merged.sort_values(["_konto_num", "Konto"], kind="mergesort", na_position="last")
    except Exception:
        merged = merged.sort_values("Konto", kind="mergesort")

    merged["Regnr"] = pd.to_numeric(merged.get("Regnr"), errors="coerce").astype("Int64")

    out = merged.reindex(columns=ALL_COLUMNS, fill_value="").reset_index(drop=True)
    return SaldobalansePayload(
        df=out,
        profile_document=profile_document,
        history_document=history_document,
        catalog=catalog,
        suggestions=suggestions,
        classification_items=classification_items,
    )


def build_saldobalanse_df(
    *,
    analyse_page: Any,
    search_text: str = "",
    only_unmapped: bool = False,
    include_zero: bool = False,
    mapping_status_filter: str = FILTER_ALL,
    source_filter: str = FILTER_ALL,
    only_with_ao: bool = False,
    payroll_scope: str = FILTER_ALL,
    include_payroll: bool = True,
) -> pd.DataFrame:
    return build_saldobalanse_payload(
        analyse_page=analyse_page,
        search_text=search_text,
        only_unmapped=only_unmapped,
        include_zero=include_zero,
        mapping_status_filter=mapping_status_filter,
        source_filter=source_filter,
        only_with_ao=only_with_ao,
        payroll_scope=payroll_scope,
        include_payroll=include_payroll,
    ).df


class SaldobalansePage(ttk.Frame):  # type: ignore[misc]
    def __init__(self, master: Any = None) -> None:
        super().__init__(master)
        self._analyse_page: Any = None
        self._df_last = pd.DataFrame(columns=ALL_COLUMNS)

        self._var_search = tk.StringVar(value="") if tk is not None else None
        self._var_work_mode = tk.StringVar(value=WORK_MODE_STANDARD) if tk is not None else None
        self._var_preset = tk.StringVar(value="Standard") if tk is not None else None
        self._var_mapping_status = tk.StringVar(value=FILTER_ALL) if tk is not None else None
        self._var_source = tk.StringVar(value=FILTER_ALL) if tk is not None else None
        self._var_payroll_scope = tk.StringVar(value=FILTER_ALL) if tk is not None else None
        self._var_only_unmapped = tk.BooleanVar(value=False) if tk is not None else None
        self._var_include_zero = tk.BooleanVar(value=False) if tk is not None else None
        self._var_only_with_ao = tk.BooleanVar(value=False) if tk is not None else None
        self._var_include_ao_fallback = tk.BooleanVar(value=False) if tk is not None else None

        self._tree = None
        self._status_var = tk.StringVar(value="Ingen saldobalanse lastet.") if tk is not None else None
        self._btn_use_suggestion = None
        self._btn_use_history = None
        self._btn_reset_suspicious = None
        self._btn_primary_action = None
        self._btn_leave_payroll = None
        self._btn_export = None
        self._btn_map = None
        self._btn_classify = None
        self._chk_include_ao = None
        self._selection_actions_frame = None
        self._selection_actions_summary_var = tk.StringVar(value="") if tk is not None else None
        self._btn_selection_use_suggestion = None
        self._btn_selection_use_history = None
        self._btn_selection_reset_suspicious = None
        self._btn_selection_unlock = None
        self._body_pane = None
        self._details_frame = None
        self._menu_tree = None
        self._profile_document = None
        self._history_document = None
        self._profile_catalog = None
        self._payroll_suggestions: dict[str, payroll_classification.PayrollSuggestionResult] = {}
        self._classification_items: dict[str, classification_workspace.ClassificationWorkspaceItem] = {}
        self._a07_options: list[tuple[str, str]] = []
        self._a07_options_loaded: bool = False
        self._status_base_text = "Ingen saldobalanse lastet."
        self._status_detail_text = ""
        self._payroll_context_key: tuple[str, int | None] | None = None
        self._payroll_usage_features_cache: dict[str, Any] | None = None
        self._payroll_usage_cache_key: tuple[int, int] | None = None
        self._refresh_after_id: str | None = None
        self._base_payload_cache: SaldobalanseBasePayload | None = None
        self._base_payload_cache_key: tuple | None = None
        self._detail_headline_var = tk.StringVar(value="Velg en konto for å se klassifisering.") if tk is not None else None
        self._detail_current_var = tk.StringVar(value="") if tk is not None else None
        self._detail_suggested_var = tk.StringVar(value="") if tk is not None else None
        self._detail_treatment_var = tk.StringVar(value="") if tk is not None else None
        self._detail_next_var = tk.StringVar(value="") if tk is not None else None
        self._detail_why_var = tk.StringVar(value="") if tk is not None else None
        self._selection_totals_var = tk.StringVar(value="") if tk is not None else None
        self._current_primary_action = ""
        self._saved_non_payroll_visible_cols: list[str] | None = None
        self._saved_non_payroll_order: list[str] | None = None
        self._saved_non_payroll_filters: dict[str, object] | None = None
        self._column_order = list(DEFAULT_COLUMN_ORDER)
        self._visible_cols = list(DEFAULT_VISIBLE_COLUMNS)
        self._load_column_preferences()
        self._build_ui()

    def set_analyse_page(self, page: Any) -> None:
        self._analyse_page = page
        SaldobalansePage._invalidate_payload_cache(self)
        self._sync_shared_vars()
        self.refresh()

    def refresh_from_session(self, session_obj: Any = None, **_kw: object) -> None:
        SaldobalansePage._invalidate_payload_cache(self)
        try:
            self.after(100, self.refresh)
        except Exception:
            self.refresh()

    def _is_payroll_mode(self) -> bool:
        if self._var_work_mode is None:
            return False
        return str(self._var_work_mode.get() or "").strip() == WORK_MODE_PAYROLL

    def focus_payroll_accounts(
        self,
        accounts: list[str] | tuple[str, ...] | None = None,
        *,
        payroll_scope: str = FILTER_ALL,
    ) -> None:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in accounts or ():
            account = str(raw or "").strip()
            if not account or account in seen:
                continue
            normalized.append(account)
            seen.add(account)

        if getattr(self, "_var_work_mode", None) is not None:
            try:
                self._var_work_mode.set(WORK_MODE_PAYROLL)
            except Exception:
                pass
        if self._var_preset is not None:
            try:
                self._var_preset.set("Lønnsklassifisering")
            except Exception:
                pass
        if self._var_payroll_scope is not None:
            try:
                self._var_payroll_scope.set(str(payroll_scope or FILTER_ALL))
            except Exception:
                pass
        if self._var_mapping_status is not None:
            try:
                self._var_mapping_status.set(FILTER_ALL)
            except Exception:
                pass
        if self._var_source is not None:
            try:
                self._var_source.set(FILTER_ALL)
            except Exception:
                pass
        if self._var_only_unmapped is not None:
            try:
                self._var_only_unmapped.set(False)
            except Exception:
                pass
        if self._var_only_with_ao is not None:
            try:
                self._var_only_with_ao.set(False)
            except Exception:
                pass
        if self._var_search is not None:
            try:
                self._var_search.set(normalized[0] if len(normalized) == 1 else "")
            except Exception:
                pass

        on_mode_changed = getattr(self, "_on_work_mode_changed", None)
        if callable(on_mode_changed):
            on_mode_changed(refresh=False)
        self.refresh()

        if self._tree is None or not normalized:
            return

        try:
            children = {str(item).strip() for item in self._tree.get_children()}
        except Exception:
            children = set()
        visible_accounts = [account for account in normalized if account in children]
        if not visible_accounts:
            return

        try:
            self._tree.selection_set(tuple(visible_accounts))
            self._tree.focus(visible_accounts[0])
            self._tree.see(visible_accounts[0])
            update_buttons = getattr(self, "_update_map_button_state", None)
            if callable(update_buttons):
                update_buttons()
            refresh_detail = getattr(self, "_refresh_detail_panel", None)
            if callable(refresh_detail):
                refresh_detail()
            else:
                self._set_status_detail("")
        except Exception:
            pass

    def _leave_payroll_mode(self) -> None:
        if self._var_work_mode is None:
            return
        try:
            self._var_work_mode.set(WORK_MODE_STANDARD)
        except Exception:
            return
        self._on_work_mode_changed()

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)

        top = ttk.Frame(self, padding=(8, 6, 8, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self._lbl_search = ttk.Label(top, text="Søk:")
        self._lbl_search.grid(row=0, column=0, sticky="w")
        ent_search = ttk.Entry(top, textvariable=self._var_search)
        ent_search.grid(row=0, column=1, sticky="ew", padx=(6, 8))
        self._ent_search = ent_search

        self._chk_include_ao = ttk.Checkbutton(
            top,
            text="Inkl. ÅO",
            variable=self._var_include_ao_fallback,
            command=self._on_include_ao_toggled,
        )
        self._chk_include_ao.grid(row=0, column=2, sticky="w", padx=(0, 8))

        self._chk_only_unmapped = ttk.Checkbutton(
            top,
            text="Kun umappede",
            variable=self._var_only_unmapped,
            command=self.refresh,
        )
        self._chk_only_unmapped.grid(row=0, column=3, sticky="w", padx=(0, 8))
        self._chk_include_zero = ttk.Checkbutton(
            top,
            text="Vis null",
            variable=self._var_include_zero,
            command=self.refresh,
        )
        self._chk_include_zero.grid(row=0, column=4, sticky="w", padx=(0, 8))
        self._chk_only_with_ao = ttk.Checkbutton(
            top,
            text="Kun m/ÅO",
            variable=self._var_only_with_ao,
            command=self.refresh,
        )
        self._chk_only_with_ao.grid(row=0, column=5, sticky="w", padx=(0, 8))
        self._lbl_mode = ttk.Label(top, text="Modus:")
        self._lbl_mode.grid(row=0, column=6, sticky="w", padx=(8, 0))
        cmb_mode = ttk.Combobox(
            top,
            textvariable=self._var_work_mode,
            values=WORK_MODE_OPTIONS,
            state="readonly",
            width=18,
        )
        cmb_mode.grid(row=0, column=7, sticky="w", padx=(6, 0))
        self._cmb_mode = cmb_mode
        self._btn_leave_payroll = ttk.Button(top, text="Vanlig saldobalanse", command=self._leave_payroll_mode)
        self._btn_leave_payroll.grid(row=0, column=8, padx=(8, 0))

        self._lbl_preset = ttk.Label(top, text="Preset:")
        self._lbl_preset.grid(row=1, column=0, sticky="w", pady=(6, 0))
        cmb_preset = ttk.Combobox(top, textvariable=self._var_preset, values=PRESET_OPTIONS, state="readonly", width=16)
        cmb_preset.grid(row=1, column=1, sticky="w", padx=(6, 8), pady=(6, 0))
        self._cmb_preset = cmb_preset

        self._lbl_mapping_status = ttk.Label(top, text="Mapping:")
        self._lbl_mapping_status.grid(row=1, column=2, sticky="w", pady=(6, 0))
        cmb_mapping = ttk.Combobox(
            top,
            textvariable=self._var_mapping_status,
            values=MAPPING_STATUS_OPTIONS,
            state="readonly",
            width=14,
        )
        cmb_mapping.grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(6, 0))
        self._cmb_mapping_status = cmb_mapping

        self._lbl_source = ttk.Label(top, text="Kilde:")
        self._lbl_source.grid(row=1, column=4, sticky="w", pady=(6, 0))
        cmb_source = ttk.Combobox(
            top,
            textvariable=self._var_source,
            values=SOURCE_OPTIONS,
            state="readonly",
            width=10,
        )
        cmb_source.grid(row=1, column=5, sticky="w", padx=(0, 8), pady=(6, 0))
        self._cmb_source = cmb_source

        self._lbl_payroll_scope = ttk.Label(top, text="Lønn:")
        self._lbl_payroll_scope.grid(row=1, column=6, sticky="w", pady=(6, 0))
        cmb_payroll = ttk.Combobox(
            top,
            textvariable=self._var_payroll_scope,
            values=PAYROLL_SCOPE_OPTIONS,
            state="readonly",
            width=18,
        )
        cmb_payroll.grid(row=1, column=7, sticky="w", padx=(0, 8), pady=(6, 0))
        self._cmb_payroll_scope = cmb_payroll

        self._btn_columns = ttk.Button(top, text="Kolonner...", command=self._open_column_chooser)
        self._btn_columns.grid(row=1, column=8, padx=(0, 8), pady=(6, 0))
        self._btn_primary_action = ttk.Button(top, text="Godkjenn forslag", command=self._run_primary_action)
        self._btn_primary_action.grid(row=1, column=9, padx=(0, 8), pady=(6, 0))
        self._btn_use_suggestion = ttk.Button(top, text="Godkjenn forslag", command=self._apply_best_suggestions_to_selected_accounts)
        self._btn_use_suggestion.grid(row=1, column=10, padx=(0, 8), pady=(6, 0))
        self._btn_use_history = ttk.Button(top, text="Bruk fjorårets klassifisering", command=self._apply_history_to_selected_accounts)
        self._btn_use_history.grid(row=1, column=11, padx=(0, 8), pady=(6, 0))
        self._btn_reset_suspicious = ttk.Button(top, text="Nullstill mistenkelige", command=self._clear_selected_suspicious_payroll_fields)
        self._btn_reset_suspicious.grid(row=1, column=12, padx=(0, 8), pady=(6, 0))
        self._btn_map = ttk.Button(top, text="Map valgt konto...", command=self._map_selected_account)
        self._btn_map.grid(row=1, column=13, padx=(0, 8), pady=(6, 0))
        self._btn_classify = ttk.Button(top, text="Avansert klassifisering...", command=self._open_advanced_classification)
        self._btn_classify.grid(row=1, column=14, padx=(0, 8), pady=(6, 0))
        self._btn_export = ttk.Button(top, text="Eksporter Excel...", command=self._export_current_view_to_excel)
        self._btn_export.grid(row=1, column=15, padx=(0, 8), pady=(6, 0))
        self._btn_refresh = ttk.Button(top, text="Oppfrisk", command=self._hard_refresh)
        self._btn_refresh.grid(row=1, column=16, pady=(6, 0))

        ttk.Label(self, textvariable=self._status_var, padding=(8, 0, 8, 4)).grid(row=1, column=0, sticky="ew")

        selection_actions = ttk.Frame(self, padding=(8, 0, 8, 4))
        selection_actions.grid(row=2, column=0, sticky="ew")
        selection_actions.columnconfigure(0, weight=1)
        self._selection_actions_frame = selection_actions
        ttk.Label(
            selection_actions,
            textvariable=self._selection_actions_summary_var,
            style="Muted.TLabel",
            justify="left",
        ).grid(row=0, column=0, sticky="w")
        self._body_pane = ttk.Panedwindow(self, orient="horizontal")
        self._body_pane.grid(row=3, column=0, sticky="nsew")

        tree_frame = ttk.Frame(self._body_pane, padding=(8, 0, 4, 8))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self._body_pane.add(tree_frame, weight=5)

        details_frame = ttk.LabelFrame(self._body_pane, text="Detaljer", padding=(8, 8, 8, 8))
        self._body_pane.add(details_frame, weight=3)
        self._details_frame = details_frame

        self._tree = ttk.Treeview(tree_frame, columns=ALL_COLUMNS, show="headings", selectmode="extended")
        self._tree.grid(row=0, column=0, sticky="nsew")
        for col in ALL_COLUMNS:
            anchor = "e" if col in NUMERIC_COLUMNS else "w"
            stretch = col in {
                "Kontonavn",
                "Regnskapslinje",
                "Lønnsflagg",
                "Flagg-forslag",
                "A07-forslag",
                "RF-1022-forslag",
                "Matchgrunnlag",
                "Problem",
            }
            self._tree.heading(col, text=col)
            self._tree.column(col, width=COLUMN_WIDTHS.get(col, 110), minwidth=50, stretch=stretch, anchor=anchor)

        try:
            self._tree.tag_configure("problem", foreground="#9C1C1C")
            self._tree.tag_configure("override", foreground="#1A56A0")
            self._tree.tag_configure("payroll_suggestion", foreground="#0D5C63")
            self._tree.tag_configure("payroll_locked", foreground="#6C3483")
            self._tree.tag_configure("payroll_unclear", foreground="#B33A3A")
        except Exception:
            pass

        y_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        self._tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        ttk.Label(
            self,
            textvariable=self._selection_totals_var,
            style="Muted.TLabel",
            padding=(8, 0, 8, 6),
            anchor="w",
            justify="left",
        ).grid(row=4, column=0, sticky="ew")

        ttk.Label(
            details_frame,
            textvariable=self._detail_headline_var,
            style="Section.TLabel",
            wraplength=360,
            justify="left",
        ).pack(anchor="w", fill="x")
        for title, variable in (
            ("Nå", self._detail_current_var),
            ("Forslag", self._detail_suggested_var),
            ("RF-1022-behandling", self._detail_treatment_var),
            ("Neste handling", self._detail_next_var),
        ):
            section = ttk.LabelFrame(details_frame, text=title, padding=(6, 6, 6, 6))
            section.pack(fill="x", pady=(8, 0))
            ttk.Label(
                section,
                textvariable=variable,
                style="Muted.TLabel",
                wraplength=360,
                justify="left",
            ).pack(anchor="w", fill="x")

        try:
            self._tree.bind("<<TreeviewSelect>>", lambda _event: self._on_tree_selection_changed(), add="+")
            self._tree.bind("<Double-1>", lambda _event: self._map_selected_account(), add="+")
            self._tree.bind("<Button-3>", self._open_context_menu, add="+")
            self._tree.bind("<Return>", lambda _event: self._open_advanced_classification(), add="+")
            self._tree.bind("<Control-h>", lambda _event: self._apply_history_to_selected_accounts(), add="+")
            self._tree.bind("<Control-b>", lambda _event: self._apply_best_suggestions_to_selected_accounts(), add="+")
            self._tree.bind("<Delete>", lambda _event: self._clear_selected_payroll_fields(), add="+")
        except Exception:
            pass

        try:
            self._var_search.trace_add("write", lambda *_: self._schedule_refresh(250))
        except Exception:
            pass
        try:
            cmb_mode.bind("<<ComboboxSelected>>", lambda _event: self._on_work_mode_changed(), add="+")
            cmb_preset.bind("<<ComboboxSelected>>", lambda _event: self._on_preset_changed(), add="+")
            cmb_mapping.bind("<<ComboboxSelected>>", lambda _event: self._schedule_refresh(80), add="+")
            cmb_source.bind("<<ComboboxSelected>>", lambda _event: self._schedule_refresh(80), add="+")
            cmb_payroll.bind("<<ComboboxSelected>>", lambda _event: self._schedule_refresh(80), add="+")
        except Exception:
            pass

        self._apply_visible_columns()
        self._sync_preset_var()
        self._sync_shared_vars()
        self._sync_mode_ui()
        self._refresh_detail_panel()
        self._update_map_button_state()

    def _sync_shared_vars(self) -> None:
        if self._chk_include_ao is None:
            return
        analyse_page = self._analyse_page
        shared_var = getattr(analyse_page, "_var_include_ao", None) if analyse_page is not None else None
        try:
            if shared_var is not None:
                self._chk_include_ao.configure(variable=shared_var, state="normal")
            else:
                self._chk_include_ao.configure(variable=self._var_include_ao_fallback, state="disabled")
        except Exception:
            pass

    def _show_grid_widget(self, widget: Any, *, show: bool) -> None:
        if widget is None:
            return
        try:
            manager = widget.winfo_manager()
        except Exception:
            manager = ""
        if show:
            if manager != "grid":
                try:
                    widget.grid()
                except Exception:
                    pass
            return
        if manager == "grid":
            try:
                widget.grid_remove()
            except Exception:
                pass

    def _show_pane_widget(self, widget: Any, *, show: bool, weight: int = 1) -> None:
        pane = self._body_pane
        if pane is None or widget is None:
            return
        try:
            pane_paths = {str(path) for path in pane.panes()}
        except Exception:
            pane_paths = set()
        widget_path = str(widget)
        if show and widget_path not in pane_paths:
            try:
                pane.add(widget, weight=weight)
            except Exception:
                pass
        if not show and widget_path in pane_paths:
            try:
                pane.forget(widget)
            except Exception:
                pass

    def _var_value(self, var: Any, default: object = "") -> object:
        if var is None:
            return default
        try:
            return var.get()
        except Exception:
            return default

    def _set_var_value(self, var: Any, value: object) -> None:
        if var is None:
            return
        try:
            var.set(value)
        except Exception:
            pass

    def _save_non_payroll_filters(self) -> None:
        if self._saved_non_payroll_filters is not None:
            return
        self._saved_non_payroll_filters = {
            "mapping_status": self._var_value(self._var_mapping_status, FILTER_ALL),
            "source": self._var_value(self._var_source, FILTER_ALL),
            "only_unmapped": bool(self._var_value(self._var_only_unmapped, False)),
            "include_zero": bool(self._var_value(self._var_include_zero, False)),
            "only_with_ao": bool(self._var_value(self._var_only_with_ao, False)),
            "include_ao": bool(self._var_value(self._var_include_ao_fallback, False)),
        }

    def _reset_hidden_filters_for_payroll_mode(self) -> None:
        self._set_var_value(self._var_mapping_status, FILTER_ALL)
        self._set_var_value(self._var_source, FILTER_ALL)
        self._set_var_value(self._var_only_unmapped, False)
        self._set_var_value(self._var_include_zero, False)
        self._set_var_value(self._var_only_with_ao, False)
        self._set_var_value(self._var_include_ao_fallback, False)

    def _restore_non_payroll_filters(self) -> None:
        saved = self._saved_non_payroll_filters or {}
        self._set_var_value(self._var_mapping_status, saved.get("mapping_status", FILTER_ALL))
        self._set_var_value(self._var_source, saved.get("source", FILTER_ALL))
        self._set_var_value(self._var_only_unmapped, bool(saved.get("only_unmapped", False)))
        self._set_var_value(self._var_include_zero, bool(saved.get("include_zero", False)))
        self._set_var_value(self._var_only_with_ao, bool(saved.get("only_with_ao", False)))
        self._set_var_value(self._var_include_ao_fallback, bool(saved.get("include_ao", False)))
        self._saved_non_payroll_filters = None

    def _payroll_intro_sections(self) -> dict[str, str]:
        return {
            "headline": "Lønnsklassifisering",
            "current": (
                "Køer\n"
                "Mistenkelig lagret: åpenbart feil lagret klassifisering.\n"
                "Klar til forslag: trygge forslag klare til bruk.\n"
                "Historikk tilgjengelig: fjoråret finnes, men er ikke brukt ennå.\n"
                "Trenger vurdering: forslag finnes, men må vurderes.\n"
                "Umappet: ingen klassifisering er satt.\n"
                "Låste: beholdes uendret til du låser opp."
            ),
            "suggested": (
                "Forslag\n"
                "1. Velg kø øverst.\n"
                "2. Velg konto i listen.\n"
                "3. Les forslag og neste handling.\n"
                "4. Bruk primærknappen når den passer.\n"
                "5. Behandle flere kontoer samlet bare når de faktisk skal likt."
            ),
            "treatment": "RF-1022-behandling vises her for valgt konto.",
            "next": "Velg en konto for å få én tydelig anbefalt handling.",
            "why": "",
        }

    def _selection_detail_sections(
        self,
        items: list[classification_workspace.ClassificationWorkspaceItem],
        *,
        button_label: str,
    ) -> dict[str, str]:
        queue_order = (
            classification_workspace.QUEUE_SUSPICIOUS,
            classification_workspace.QUEUE_READY,
            classification_workspace.QUEUE_HISTORY,
            classification_workspace.QUEUE_REVIEW,
            classification_workspace.QUEUE_UNMAPPED,
            classification_workspace.QUEUE_LOCKED,
            classification_workspace.QUEUE_SAVED,
        )
        queue_counts: dict[str, int] = {}
        for item in items:
            queue_counts[item.queue_name] = queue_counts.get(item.queue_name, 0) + 1
        queue_parts = [f"{name}: {queue_counts[name]}" for name in queue_order if queue_counts.get(name)]
        remaining = [name for name in queue_counts if name not in queue_order]
        queue_parts.extend(f"{name}: {queue_counts[name]}" for name in sorted(remaining))
        mixed_selection = len(queue_counts) > 1
        return {
            "headline": f"{len(items)} valgte kontoer",
            "current": "Utvalg\n" + ("\n".join(queue_parts) if queue_parts else "Ingen kontoer valgt."),
            "suggested": (
                "Forslag\n"
                + (
                    f"Primærhandling: {button_label}\n"
                    "Bruk den bare når den passer for hele utvalget."
                    if button_label
                    else "Velg en konto for å få en tydelig anbefalt handling."
                )
            ),
            "treatment": (
                "RF-1022-behandling må vurderes per konto."
                if mixed_selection
                else "RF-1022-behandling kan som regel håndteres samlet for dette utvalget."
            ),
            "next": (
                "Åpne klassifisering hvis kontoene trenger ulik behandling."
                if mixed_selection
                else (button_label or "Velg konto for å få en tydelig anbefalt handling.")
            ),
            "why": "",
        }

    def _on_work_mode_changed(self, *, refresh: bool = True) -> None:
        entering_payroll = self._is_payroll_mode()
        if entering_payroll:
            if self._saved_non_payroll_visible_cols is None:
                self._saved_non_payroll_visible_cols = list(self._visible_cols)
                self._saved_non_payroll_order = list(self._column_order)
            self._save_non_payroll_filters()
            self._reset_hidden_filters_for_payroll_mode()
            self._visible_cols = list(COLUMN_PRESETS["Lønnsklassifisering"])
            self._column_order = _ordered_columns_for_visible(self._visible_cols)
        elif self._saved_non_payroll_visible_cols is not None:
            self._visible_cols = list(self._saved_non_payroll_visible_cols)
            self._column_order = list(self._saved_non_payroll_order or _ordered_columns_for_visible(self._visible_cols))
            self._saved_non_payroll_visible_cols = None
            self._saved_non_payroll_order = None
            self._restore_non_payroll_filters()
        self._apply_visible_columns()
        self._sync_preset_var()
        self._sync_mode_ui()
        if refresh:
            self.refresh()

    def _sync_mode_ui(self) -> None:
        payroll_mode = self._is_payroll_mode()
        for widget in (
            getattr(self, "_lbl_mode", None),
            getattr(self, "_cmb_mode", None),
        ):
            self._show_grid_widget(widget, show=not payroll_mode)
        self._show_grid_widget(getattr(self, "_btn_leave_payroll", None), show=payroll_mode)
        for widget in (
            getattr(self, "_lbl_preset", None),
            getattr(self, "_cmb_preset", None),
            getattr(self, "_lbl_mapping_status", None),
            getattr(self, "_cmb_mapping_status", None),
            getattr(self, "_lbl_source", None),
            getattr(self, "_cmb_source", None),
            getattr(self, "_btn_columns", None),
            getattr(self, "_chk_include_ao", None),
            getattr(self, "_chk_only_unmapped", None),
            getattr(self, "_chk_include_zero", None),
            getattr(self, "_chk_only_with_ao", None),
            getattr(self, "_btn_use_suggestion", None),
            getattr(self, "_btn_use_history", None),
            getattr(self, "_btn_reset_suspicious", None),
            getattr(self, "_btn_map", None),
        ):
            self._show_grid_widget(widget, show=not payroll_mode)
        self._show_grid_widget(getattr(self, "_btn_primary_action", None), show=payroll_mode)
        self._show_pane_widget(self._details_frame, show=payroll_mode, weight=3)
        label = getattr(self, "_lbl_payroll_scope", None)
        if label is not None:
            try:
                label.configure(text="Kø:" if payroll_mode else "Lønn:")
            except Exception:
                pass
        classify_button = getattr(self, "_btn_classify", None)
        if classify_button is not None:
            try:
                classify_button.configure(text="Åpne klassifisering..." if payroll_mode else "Avansert klassifisering...")
            except Exception:
                pass
        details_frame = getattr(self, "_details_frame", None)
        if details_frame is not None:
            try:
                details_frame.configure(text="Detaljer")
            except Exception:
                pass
        sync_selection_actions = getattr(self, "_sync_selection_actions_visibility", None)
        if callable(sync_selection_actions):
            sync_selection_actions()

    def _workspace_item_for_account(self, account_no: str) -> classification_workspace.ClassificationWorkspaceItem | None:
        account_s = str(account_no or "").strip()
        if not account_s:
            return None
        item = self._classification_items.get(account_s)
        if item is not None:
            return item
        row = self._row_for_account(account_s)
        if row is None:
            return None
        document, history_document, catalog = self._ensure_payroll_context_loaded()
        if document is None:
            return None
        try:
            item = classification_workspace.build_workspace_item(
                account_no=account_s,
                account_name=str(row.get("Kontonavn") or "").strip(),
                ib=row.get("IB"),
                movement=row.get("Endring"),
                ub=row.get("UB"),
                current_profile=document.get(account_s),
                history_profile=history_document.get(account_s) if history_document is not None else None,
                catalog=catalog,
                usage=self._ensure_payroll_usage_features_loaded().get(account_s),
            )
        except Exception:
            return None
        self._classification_items[account_s] = item
        return item

    def _selected_workspace_items(self) -> list[classification_workspace.ClassificationWorkspaceItem]:
        items: list[classification_workspace.ClassificationWorkspaceItem] = []
        for account in self._selected_accounts():
            item = self._workspace_item_for_account(account)
            if item is not None:
                items.append(item)
        return items

    def _determine_primary_action(
        self,
        items: list[classification_workspace.ClassificationWorkspaceItem],
    ) -> tuple[str, str]:
        if not items:
            return "", ""
        actions = {item.next_action for item in items}
        if len(actions) == 1:
            action = next(iter(actions))
        elif actions == {classification_workspace.NEXT_REVIEW_SAVED, classification_workspace.NEXT_OPEN_CLASSIFIER}:
            action = classification_workspace.NEXT_OPEN_CLASSIFIER
        else:
            return classification_workspace.NEXT_OPEN_CLASSIFIER, "Åpne klassifisering"
        if action == classification_workspace.NEXT_APPLY_SUGGESTION:
            return action, "Godkjenn forslag" if len(items) == 1 else f"Godkjenn forslag ({len(items)})"
        if action == classification_workspace.NEXT_APPLY_HISTORY:
            if len(items) == 1:
                return action, "Bruk fjorårets klassifisering"
            return action, f"Bruk fjorårets klassifisering ({len(items)})"
        if action == classification_workspace.NEXT_RESET_SAVED:
            return action, "Nullstill mistenkelige" if len(items) > 1 else "Nullstill lagret"
        if action == classification_workspace.NEXT_UNLOCK:
            return action, "Lås opp"
        return action, "Åpne klassifisering"

    def _run_primary_action(self) -> None:
        action = str(self._current_primary_action or "").strip()
        if not action:
            return
        if action == classification_workspace.NEXT_APPLY_SUGGESTION:
            self._apply_best_suggestions_to_selected_accounts()
            return
        if action == classification_workspace.NEXT_APPLY_HISTORY:
            self._apply_history_to_selected_accounts()
            return
        if action == classification_workspace.NEXT_RESET_SAVED:
            self._clear_selected_suspicious_payroll_fields()
            return
        if action == classification_workspace.NEXT_UNLOCK:
            self._toggle_lock_selected_accounts()
            return
        self._open_advanced_classification()

    def _refresh_detail_panel(self) -> None:
        headline_var = self._detail_headline_var
        current_var = self._detail_current_var
        suggested_var = self._detail_suggested_var
        treatment_var = getattr(self, "_detail_treatment_var", None)
        next_var = getattr(self, "_detail_next_var", None)
        why_var = self._detail_why_var
        if (
            headline_var is None
            or current_var is None
            or suggested_var is None
            or treatment_var is None
            or next_var is None
            or why_var is None
        ):
            return
        items = self._selected_workspace_items()
        action, button_label = self._determine_primary_action(items)
        self._current_primary_action = action
        if len(items) == 1:
            detail = classification_workspace.format_why_panel(items[0])
            headline_var.set(detail["headline"])
            current_var.set(detail["current"])
            suggested_var.set(detail["suggested"])
            treatment_var.set(detail.get("treatment", ""))
            next_var.set(detail.get("next", ""))
            why_var.set(detail.get("why", ""))
            self._set_status_detail(
                " | ".join(
                    part
                    for part in (
                        f"Valgt {items[0].account_no}",
                        items[0].account_name or "-",
                        f"Status {items[0].status_label}",
                    )
                    if part
                )
            )
        elif items:
            detail = self._selection_detail_sections(items, button_label=button_label)
            headline_var.set(detail["headline"])
            current_var.set(detail["current"])
            suggested_var.set(detail["suggested"])
            treatment_var.set(detail.get("treatment", ""))
            next_var.set(detail.get("next", ""))
            why_var.set(detail.get("why", ""))
            self._set_status_detail(f"{len(items)} valgte kontoer" + (f" | {button_label}" if button_label else ""))
        else:
            if self._is_payroll_mode():
                intro = self._payroll_intro_sections()
                headline_var.set(intro["headline"])
                current_var.set(intro["current"])
                suggested_var.set(intro["suggested"])
                treatment_var.set(intro.get("treatment", ""))
                next_var.set(intro.get("next", ""))
                why_var.set(intro.get("why", ""))
                self._set_status_detail("Velg kø og konto for å starte.")
            else:
                headline_var.set("Velg en konto for å se klassifisering.")
                current_var.set("")
                suggested_var.set("")
                treatment_var.set("")
                next_var.set("")
                why_var.set("")
                self._set_status_detail("")
        sync_selection_actions = getattr(self, "_sync_selection_actions_visibility", None)
        if callable(sync_selection_actions):
            sync_selection_actions()
        refresh_totals = getattr(self, "_refresh_selection_totals", None)
        if callable(refresh_totals):
            refresh_totals()

    def _refresh_selection_totals(self) -> None:
        summary_var = getattr(self, "_selection_totals_var", None)
        if summary_var is None:
            return
        accounts = self._selected_accounts()
        if not accounts or self._df_last.empty:
            try:
                summary_var.set("")
            except Exception:
                pass
            return
        try:
            subset = self._df_last.loc[self._df_last["Konto"].astype(str).isin(accounts)].copy()
        except Exception:
            subset = pd.DataFrame()
        if subset.empty:
            try:
                summary_var.set("")
            except Exception:
                pass
            return
        ib_series = subset["IB"] if "IB" in subset.columns else pd.Series(0.0, index=subset.index)
        change_series = subset["Endring"] if "Endring" in subset.columns else pd.Series(0.0, index=subset.index)
        ub_series = subset["UB"] if "UB" in subset.columns else pd.Series(0.0, index=subset.index)
        total_change = float(pd.to_numeric(change_series, errors="coerce").fillna(0.0).sum())
        total_ub = float(pd.to_numeric(ub_series, errors="coerce").fillna(0.0).sum())
        total_ib = float(pd.to_numeric(ib_series, errors="coerce").fillna(0.0).sum())
        parts = [
            f"{len(subset.index)} valgt",
            f"IB {formatting.fmt_amount(total_ib)}",
            f"Endring {formatting.fmt_amount(total_change)}",
            f"UB {formatting.fmt_amount(total_ub)}",
        ]
        if len(subset.index) == 1:
            row = subset.iloc[0]
            parts.append(f"{row.get('Konto') or '-'} {row.get('Kontonavn') or '-'}")
        try:
            summary_var.set(" | ".join(parts))
        except Exception:
            pass

    def _sync_selection_actions_visibility(self) -> None:
        frame = getattr(self, "_selection_actions_frame", None)
        summary_var = getattr(self, "_selection_actions_summary_var", None)
        if frame is None:
            return
        payroll_mode = self._is_payroll_mode()
        selection = self._selected_accounts()
        show = payroll_mode and bool(selection)
        self._show_grid_widget(frame, show=show)
        if summary_var is None:
            return
        if not show:
            try:
                summary_var.set("")
            except Exception:
                pass
            return
        items = self._selected_workspace_items()
        action, label = self._determine_primary_action(items)
        _ = action
        summary_parts = [f"{len(selection)} valgt"]
        if not self._df_last.empty:
            try:
                subset = self._df_last.loc[self._df_last["Konto"].astype(str).isin(selection)].copy()
            except Exception:
                subset = pd.DataFrame()
            if not subset.empty:
                ib_series = subset["IB"] if "IB" in subset.columns else pd.Series(0.0, index=subset.index)
                change_series = subset["Endring"] if "Endring" in subset.columns else pd.Series(0.0, index=subset.index)
                ub_series = subset["UB"] if "UB" in subset.columns else pd.Series(0.0, index=subset.index)
                total_ib = float(pd.to_numeric(ib_series, errors="coerce").fillna(0.0).sum())
                total_change = float(pd.to_numeric(change_series, errors="coerce").fillna(0.0).sum())
                total_ub = float(pd.to_numeric(ub_series, errors="coerce").fillna(0.0).sum())
                summary_parts.append(f"IB {formatting.fmt_amount(total_ib)}")
                summary_parts.append(f"Endring {formatting.fmt_amount(total_change)}")
                summary_parts.append(f"UB {formatting.fmt_amount(total_ub)}")
        if label:
            summary_parts.append(f"Neste: {label}")
        try:
            summary_var.set(" | ".join(summary_parts))
        except Exception:
            pass

    def _load_column_preferences(self) -> None:
        try:
            order = preferences.get("saldobalanse.columns.order", None)
            visible = preferences.get("saldobalanse.columns.visible", None)
        except Exception:
            order = None
            visible = None

        if isinstance(order, list):
            cleaned = [col for col in order if col in ALL_COLUMNS]
            for col in ALL_COLUMNS:
                if col not in cleaned:
                    cleaned.append(col)
            if cleaned:
                self._column_order = cleaned

        if isinstance(visible, list):
            cleaned_visible = [col for col in visible if col in ALL_COLUMNS]
            if cleaned_visible:
                self._visible_cols = cleaned_visible

    def _persist_column_preferences(self) -> None:
        try:
            preferences.set("saldobalanse.columns.order", list(self._column_order))
            preferences.set("saldobalanse.columns.visible", list(self._visible_cols))
        except Exception:
            pass

    def _apply_visible_columns(self) -> None:
        if self._tree is None:
            return
        visible = [col for col in self._column_order if col in self._visible_cols]
        if not visible:
            visible = list(DEFAULT_VISIBLE_COLUMNS)
        try:
            self._tree["displaycolumns"] = visible
        except Exception:
            pass

    def _sync_preset_var(self) -> None:
        if self._var_preset is None:
            return
        try:
            self._var_preset.set(_preset_name_for_visible_columns(self._visible_cols))
        except Exception:
            pass

    def _on_preset_changed(self) -> None:
        if self._var_preset is None:
            return
        preset_name = str(self._var_preset.get() or "").strip()
        preset_cols = COLUMN_PRESETS.get(preset_name)
        if not preset_cols:
            return
        if self._var_work_mode is not None:
            try:
                if preset_name in {"Lønnsklassifisering", "Lønn/A07"}:
                    self._var_work_mode.set(WORK_MODE_PAYROLL)
                elif self._is_payroll_mode():
                    self._var_work_mode.set(WORK_MODE_STANDARD)
            except Exception:
                pass
        self._visible_cols = list(preset_cols)
        self._column_order = _ordered_columns_for_visible(list(preset_cols))
        self._apply_visible_columns()
        self._persist_column_preferences()
        self._sync_mode_ui()
        self.refresh()

    def _open_column_chooser(self) -> None:
        try:
            from views_column_chooser import open_column_chooser
        except Exception:
            return

        res = open_column_chooser(
            self,
            all_cols=list(ALL_COLUMNS),
            visible_cols=list(self._visible_cols),
            initial_order=list(self._column_order),
            default_visible_cols=list(DEFAULT_VISIBLE_COLUMNS),
            default_order=list(DEFAULT_COLUMN_ORDER),
        )
        if not res:
            return

        order, visible = res
        self._column_order = [col for col in order if col in ALL_COLUMNS]
        for col in ALL_COLUMNS:
            if col not in self._column_order:
                self._column_order.append(col)
        self._visible_cols = [col for col in visible if col in ALL_COLUMNS]
        self._apply_visible_columns()
        self._persist_column_preferences()
        self._sync_preset_var()
        self.refresh()

    def _clear_tree(self) -> None:
        if self._tree is None:
            return
        try:
            items = self._tree.get_children("")
        except Exception:
            items = ()
        if not items:
            return
        try:
            self._tree.delete(*items)
            return
        except Exception:
            pass
        for item in items:
            try:
                self._tree.delete(item)
            except Exception:
                continue

    def _should_include_payroll_payload(self) -> bool:
        is_payroll_mode = getattr(self, "_is_payroll_mode", None)
        if callable(is_payroll_mode) and is_payroll_mode():
            return True
        payroll_scope = self._var_payroll_scope.get() if self._var_payroll_scope is not None else FILTER_ALL
        if str(payroll_scope or FILTER_ALL).strip() != FILTER_ALL:
            return True
        return any(column in PAYROLL_COLUMNS for column in self._visible_cols)

    def _row_for_account(self, account_no: str) -> pd.Series | None:
        if self._df_last is None or self._df_last.empty:
            return None
        account_s = str(account_no or "").strip()
        if not account_s:
            return None
        try:
            match = self._df_last.loc[self._df_last["Konto"].astype(str).str.strip() == account_s]
        except Exception:
            return None
        if match is None or match.empty:
            return None
        return match.iloc[0]

    def _ensure_payroll_context_loaded(self) -> tuple[Any, Any, Any]:
        client, year = self._client_context()
        if self._payroll_context_key != (client, year):
            self._profile_document = None
            self._history_document = None
            self._profile_catalog = None
            self._payroll_context_key = (client, year)
        if self._profile_document is None and client:
            self._profile_document, self._history_document, self._profile_catalog = _load_payroll_context(client, year)
        return self._profile_document, self._history_document, self._profile_catalog

    def _ensure_payroll_usage_features_loaded(self) -> dict[str, Any]:
        analyse_page = self._analyse_page
        dataset = getattr(analyse_page, "dataset", None) if analyse_page is not None else None
        if isinstance(dataset, pd.DataFrame):
            cache_key = (id(dataset), len(dataset.index))
        else:
            cache_key = (-1, 0)
        if self._payroll_usage_cache_key != cache_key:
            self._payroll_usage_features_cache = _resolve_payroll_usage_features(analyse_page)
            self._payroll_usage_cache_key = cache_key
        return self._payroll_usage_features_cache or {}

    def _payroll_result_for_account(self, account_no: str) -> payroll_classification.PayrollSuggestionResult | None:
        account_s = str(account_no or "").strip()
        if not account_s:
            return None
        result = self._payroll_suggestions.get(account_s)
        if result is not None:
            return result
        row = self._row_for_account(account_s)
        if row is None:
            return None
        document, history_document, catalog = self._ensure_payroll_context_loaded()
        if document is None:
            return None
        result = payroll_classification.classify_payroll_account(
            account_no=account_s,
            account_name=str(row.get("Kontonavn") or "").strip(),
            movement=float(pd.to_numeric([row.get("Endring")], errors="coerce")[0] or 0.0),
            current_profile=document.get(account_s),
            history_profile=history_document.get(account_s) if history_document is not None else None,
            catalog=catalog,
            usage=self._ensure_payroll_usage_features_loaded().get(account_s),
        )
        self._payroll_suggestions[account_s] = result
        return result

    def _history_profile_for_account(self, account_no: str) -> Any:
        if self._history_document is None:
            self._ensure_payroll_context_loaded()
        if self._history_document is None:
            return None
        try:
            return self._history_document.get(str(account_no or "").strip())
        except Exception:
            return None

    def _suspicious_profile_issue_for_account(
        self,
        account_no: str,
        *,
        account_name: str = "",
        profile: Any = None,
    ) -> str:
        profile_obj = profile if profile is not None else self._profile_for_account(account_no)
        account_name_s = str(account_name or "").strip()
        if not account_name_s:
            row = self._row_for_account(account_no)
            if row is not None:
                account_name_s = str(row.get("Kontonavn") or "").strip()
        return str(
            payroll_classification.suspicious_saved_payroll_profile_issue(
                account_no=str(account_no or "").strip(),
                account_name=account_name_s,
                current_profile=profile_obj,
            )
            or ""
        ).strip()

    def _has_history_for_selected_accounts(self) -> bool:
        accounts = self._selected_accounts()
        if not accounts:
            return False
        for account in accounts:
            if self._suspicious_profile_issue_for_account(account):
                continue
            profile = self._history_profile_for_account(account)
            if profile is None:
                continue
            if (
                str(getattr(profile, "a07_code", "") or "").strip()
                or str(getattr(profile, "control_group", "") or "").strip()
                or tuple(getattr(profile, "control_tags", ()) or ())
            ):
                return True
        return False

    def _has_strict_suggestions_for_selected_accounts(self) -> bool:
        accounts = self._selected_accounts()
        if not accounts:
            return False
        for account in accounts:
            item = self._workspace_item_for_account(account)
            if _suggested_update_for_item(item):
                return True
        return False

    def _next_action_for_account(
        self,
        account_no: str,
        *,
        account_name: str = "",
        result: payroll_classification.PayrollSuggestionResult | None,
        profile: Any,
    ) -> str:
        suspicious_issue = self._suspicious_profile_issue_for_account(
            account_no,
            account_name=account_name,
            profile=profile,
        )
        if suspicious_issue:
            return "Nullstill lagret lønnsklassifisering."
        if bool(getattr(profile, "locked", False)):
            return "Lås opp hvis du vil endre klassifiseringen."
        workspace_item_for_account = getattr(self, "_workspace_item_for_account", None)
        item = None
        if callable(workspace_item_for_account):
            try:
                item = workspace_item_for_account(account_no)
            except Exception:
                item = None
        if _suggested_update_for_item(item):
            return "Godkjenn forslag."
        history_profile = self._history_profile_for_account(account_no)
        has_history = history_profile is not None and (
            str(getattr(history_profile, "a07_code", "") or "").strip()
            or str(getattr(history_profile, "control_group", "") or "").strip()
            or tuple(getattr(history_profile, "control_tags", ()) or ())
        )
        if has_history and not payroll_classification._has_payroll_profile_state(profile):
            return "Bruk fjorårets klassifisering eller åpne klassifisering."
        if result is not None and result.suggestions:
            return "Godkjenn forslag eller åpne klassifisering."
        status = str(getattr(result, "payroll_status", "") or "").strip()
        if status in {"Umappet", "Uklar"}:
            return "Åpne klassifisering og sett A07, RF-1022 og flagg."
        if status == "Manuell":
            return "Kontroller at lagret klassifisering faktisk er riktig."
        if status == "Historikk":
            return "Kontroller at historikken fortsatt passer i år."
        return ""

    def _selected_payroll_detail_text(self) -> str:
        account_no, account_name = self._selected_account()
        if not account_no:
            return ""
        row = self._row_for_account(account_no)
        if row is None:
            return ""
        result = self._payroll_result_for_account(account_no)
        profile = self._profile_for_account(account_no)
        catalog = self._profile_catalog

        parts = [f"Valgt {account_no}"]
        if account_name:
            parts.append(account_name)

        actual_a07 = str(getattr(profile, "a07_code", "") or "").strip()
        actual_group = payroll_classification.format_control_group(
            str(getattr(profile, "control_group", "") or "").strip(),
            catalog,
        )
        actual_tags = payroll_classification.format_control_tags(getattr(profile, "control_tags", ()), catalog)
        suggestion_map = dict(result.suggestions) if result is not None else {}

        suggested_a07 = ""
        if "a07_code" in suggestion_map and isinstance(suggestion_map["a07_code"].value, str):
            suggested_a07 = str(suggestion_map["a07_code"].value or "").strip()
        suggested_group = ""
        if "control_group" in suggestion_map and isinstance(suggestion_map["control_group"].value, str):
            suggested_group = payroll_classification.format_control_group(
                str(suggestion_map["control_group"].value or "").strip(),
                catalog,
            )
        suggested_tags = ""
        if "control_tags" in suggestion_map and isinstance(suggestion_map["control_tags"].value, tuple):
            suggested_tags = payroll_classification.format_control_tags(suggestion_map["control_tags"].value, catalog)

        if actual_a07:
            parts.append(f"Lagret A07: {actual_a07}")
        elif suggested_a07:
            parts.append(f"Forslag A07: {suggested_a07}")

        if actual_group:
            parts.append(f"Lagret RF-1022: {actual_group}")
        elif suggested_group:
            parts.append(f"Forslag RF-1022: {suggested_group}")

        if actual_tags:
            parts.append(f"Lagrede flagg: {actual_tags}")
        elif suggested_tags:
            parts.append(f"Forslag flagg: {suggested_tags}")

        if result is not None and result.payroll_status:
            parts.append(f"Status: {result.payroll_status}")

        confidence = getattr(profile, "confidence", None)
        top_suggestion = _top_payroll_suggestion(result)
        if confidence is None and top_suggestion is not None:
            confidence = top_suggestion.confidence
        confidence_text = payroll_classification.confidence_label(confidence)
        if confidence_text:
            parts.append(f"Sikkerhet: {confidence_text}")

        match_basis = _payroll_match_basis_text(result)
        if match_basis:
            parts.append(f"Match: {match_basis}")

        rf1022_text = str(actual_group or suggested_group or "").strip()
        treatment_text = _rf1022_treatment_text(
            account_no,
            account_name,
            ib=row.get("IB"),
            endring=row.get("Endring"),
            ub=row.get("UB"),
            rf1022_text=rf1022_text,
        )
        if treatment_text:
            parts.append(treatment_text)

        problem = self._suspicious_profile_issue_for_account(
            account_no,
            account_name=account_name,
            profile=profile,
        )
        if not problem:
            problem = _payroll_problem_text(result, top_suggestion) if result is not None else ""
        if problem:
            parts.append(problem)

        next_action = self._next_action_for_account(
            account_no,
            account_name=account_name,
            result=result,
            profile=profile,
        )
        if next_action:
            parts.append(f"Neste: {next_action}")

        if len(parts) == 2:
            parts.append("Ingen lagret klassifisering eller forslag.")
        return " | ".join(parts)

    def _sync_status_text(self) -> None:
        if self._status_var is None:
            return
        text = self._status_base_text
        if self._status_detail_text:
            text = f"{text} | {self._status_detail_text}" if text else self._status_detail_text
        try:
            self._status_var.set(text)
        except Exception:
            pass

    def _set_status_detail(self, text: str) -> None:
        self._status_detail_text = str(text or "").strip()
        self._sync_status_text()

    def _on_tree_selection_changed(self) -> None:
        self._update_map_button_state()
        self._refresh_detail_panel()

    def _explicitly_selected_accounts(self) -> list[str]:
        if self._tree is None:
            return []
        try:
            selection = list(self._tree.selection())
        except Exception:
            selection = []
        return [str(item).strip() for item in selection if str(item).strip()]

    def _restore_tree_selection(self, accounts: Sequence[str], *, focused_account: str = "") -> None:
        if self._tree is None:
            return
        try:
            children = {str(item).strip() for item in self._tree.get_children()}
        except Exception:
            children = set()
        visible_accounts = [str(account).strip() for account in accounts if str(account).strip() in children]
        try:
            if visible_accounts:
                self._tree.selection_set(tuple(visible_accounts))
                target_focus = focused_account if focused_account in visible_accounts else visible_accounts[0]
                self._tree.focus(target_focus)
                self._tree.see(target_focus)
                return
            if focused_account and focused_account in children:
                self._tree.focus(focused_account)
                self._tree.see(focused_account)
        except Exception:
            pass

    def _prepare_context_menu_selection(self, row_id: str) -> None:
        if self._tree is None or not row_id:
            return
        current_selection = set(self._explicitly_selected_accounts())
        try:
            if row_id not in current_selection:
                self._tree.selection_set(row_id)
            self._tree.focus(row_id)
            refresh_detail = getattr(self, "_refresh_detail_panel", None)
            if callable(refresh_detail):
                refresh_detail()
            else:
                self._set_status_detail(self._selected_payroll_detail_text())
        except Exception:
            pass

    def _export_current_view_to_excel(self) -> None:
        if self._df_last is None or self._df_last.empty:
            self._set_status("Ingen rader å eksportere fra saldobalansen.")
            return

        visible_columns = [col for col in self._column_order if col in self._visible_cols and col in self._df_last.columns]
        if not visible_columns:
            visible_columns = [col for col in ALL_COLUMNS if col in self._df_last.columns]
        if not visible_columns:
            self._set_status("Fant ingen synlige kolonner å eksportere.")
            return

        export_df = self._df_last.loc[:, visible_columns].copy()
        selected_accounts = self._selected_accounts()
        sheets: dict[str, pd.DataFrame] = {"Saldobalanse": export_df}
        selected_count = 0
        if selected_accounts and "Konto" in export_df.columns:
            selected_set = {str(account or "").strip() for account in selected_accounts if str(account or "").strip()}
            selected_df = export_df.loc[export_df["Konto"].astype(str).str.strip().isin(selected_set)].copy()
            if not selected_df.empty:
                sheets["Valgte kontoer"] = selected_df
                selected_count = len(selected_df.index)

        client, year = self._client_context()
        safe_client = re.sub(r'[\\\\/:*?\"<>|]+', "_", str(client or "").strip()).strip(" ._")
        filename_parts = ["saldobalanse"]
        if safe_client:
            filename_parts.append(safe_client)
        if year:
            filename_parts.append(str(year))
        default_filename = "_".join(filename_parts) + ".xlsx"

        try:
            import analyse_export_excel
            import controller_export

            path = analyse_export_excel.open_save_dialog(
                title="Eksporter saldobalanse til Excel",
                default_filename=default_filename,
                master=self,
            )
            if not path:
                return
            saved_path = controller_export.export_to_excel(path, sheets=sheets)
        except Exception as exc:
            log.exception("Excel-eksport fra saldobalanse feilet")
            self._set_status(f"Kunne ikke eksportere saldobalansen: {exc}")
            return

        file_name = Path(saved_path).name if saved_path else default_filename
        if selected_count:
            self._set_status(
                f"Eksporterte {len(export_df.index)} rader til {file_name} | Valgte kontoer: {selected_count}"
            )
        else:
            self._set_status(f"Eksporterte {len(export_df.index)} rader til {file_name}")

    def _invalidate_payload_cache(self) -> None:
        """Drop the cached expensive payroll-decorated base payload.

        Call this whenever the inputs to classification change (mutations, admin saves,
        explicit ``Oppfrisk``). Pure filter/search/scope changes do NOT invalidate — the
        cached base is reused and only postprocessing is rerun.
        """
        try:
            self._base_payload_cache = None
            self._base_payload_cache_key = None
        except Exception:
            pass

    def _hard_refresh(self) -> None:
        """Invalidate cache and refresh — used by Oppfrisk and programmatic reloads."""
        SaldobalansePage._invalidate_payload_cache(self)
        try:
            self._a07_options_loaded = False
        except Exception:
            pass
        self.refresh()

    def _ensure_a07_options_loaded(self) -> None:
        """Load the static A07 code dropdown options once per page lifetime.

        ``load_a07_code_options()`` reads the catalog from disk; the result does not
        depend on client/year so caching it across refreshes avoids redundant I/O.
        Invalidated only via ``_hard_refresh`` (Oppfrisk).
        """
        if getattr(self, "_a07_options_loaded", False):
            return
        try:
            self._a07_options = konto_klassifisering.load_a07_code_options()
        except Exception:
            self._a07_options = []
        try:
            self._a07_options_loaded = True
        except Exception:
            pass

    def _build_base_payload_key(
        self,
        *,
        only_unmapped: bool,
        include_zero: bool,
        mapping_status_filter: str,
        source_filter: str,
        only_with_ao: bool,
        include_payroll: bool,
    ) -> tuple:
        """Cache key for the expensive base payload.

        Includes client/year, underlying SB frame identities, and cheap-filter inputs.
        Excludes ``search_text`` and ``payroll_scope`` since those only affect postprocess.
        """
        client_context = getattr(self, "_client_context", None)
        if callable(client_context):
            try:
                client, year = client_context()
            except Exception:
                client, year = "", None
        else:
            client, year = "", None
        analyse_page = getattr(self, "_analyse_page", None)
        try:
            base, adjusted, effective = _resolve_sb_views(analyse_page)
        except Exception:
            base = adjusted = effective = None

        def _fp(frame) -> tuple:
            if frame is None:
                return (None, 0)
            try:
                return (id(frame), int(len(frame)))
            except Exception:
                return (id(frame), 0)

        dataset = getattr(analyse_page, "dataset", None)
        return (
            client,
            year,
            _fp(base),
            _fp(adjusted),
            _fp(effective),
            _fp(dataset),
            bool(include_zero),
            bool(only_unmapped),
            str(mapping_status_filter or FILTER_ALL),
            str(source_filter or FILTER_ALL),
            bool(only_with_ao),
            bool(include_payroll),
        )

    def _schedule_refresh(self, delay_ms: int = 220) -> None:
        """Coalesce rapid refresh triggers (typing, filter toggles) into a single call."""
        SaldobalansePage._cancel_scheduled_refresh(self)
        try:
            self._refresh_after_id = self.after(max(0, int(delay_ms)), self._run_scheduled_refresh)
        except Exception:
            self.refresh()

    def _cancel_scheduled_refresh(self) -> None:
        after_id = getattr(self, "_refresh_after_id", None)
        if after_id is None:
            return
        self._refresh_after_id = None
        try:
            self.after_cancel(after_id)
        except Exception:
            pass

    def _run_scheduled_refresh(self) -> None:
        self._refresh_after_id = None
        self.refresh()

    def refresh(self) -> None:
        SaldobalansePage._cancel_scheduled_refresh(self)
        preserved_selection = self._explicitly_selected_accounts()
        try:
            preserved_focus = str(self._tree.focus()).strip() if self._tree is not None else ""
        except Exception:
            preserved_focus = ""
        analyse_page = self._analyse_page
        if analyse_page is None:
            self._df_last = pd.DataFrame(columns=ALL_COLUMNS)
            self._profile_document = None
            self._history_document = None
            self._profile_catalog = None
            self._payroll_suggestions = {}
            self._classification_items = {}
            self._clear_tree()
            self._set_status("Saldobalanse kobles til Analyse når appen er klar.")
            self._refresh_detail_panel()
            self._update_map_button_state()
            return

        search_text = self._var_search.get() if self._var_search is not None else ""
        only_unmapped = bool(self._var_only_unmapped.get()) if self._var_only_unmapped is not None else False
        include_zero = bool(self._var_include_zero.get()) if self._var_include_zero is not None else False
        mapping_status_filter = self._var_mapping_status.get() if self._var_mapping_status is not None else FILTER_ALL
        source_filter = self._var_source.get() if self._var_source is not None else FILTER_ALL
        only_with_ao = bool(self._var_only_with_ao.get()) if self._var_only_with_ao is not None else False
        payroll_scope = self._var_payroll_scope.get() if self._var_payroll_scope is not None else FILTER_ALL
        include_payroll = self._should_include_payroll_payload()

        import time as _time
        _t_start = _time.perf_counter()
        _t_base_end = _t_start
        _base_cache_hit = False

        try:
            base_key = SaldobalansePage._build_base_payload_key(
                self,
                only_unmapped=only_unmapped,
                include_zero=include_zero,
                mapping_status_filter=mapping_status_filter,
                source_filter=source_filter,
                only_with_ao=only_with_ao,
                include_payroll=include_payroll,
            )
            cached_base: SaldobalanseBasePayload | None
            prior_cache = getattr(self, "_base_payload_cache", None)
            prior_key = getattr(self, "_base_payload_cache_key", None)
            if prior_cache is not None and prior_key == base_key:
                cached_base = prior_cache
                _base_cache_hit = True
            else:
                preloaded_profile = None
                preloaded_history = None
                preloaded_catalog = None
                preloaded_usage: dict[str, Any] | None = None
                if include_payroll:
                    try:
                        ensure_ctx = getattr(self, "_ensure_payroll_context_loaded", None)
                        if callable(ensure_ctx):
                            preloaded_profile, preloaded_history, preloaded_catalog = ensure_ctx()
                    except Exception:
                        preloaded_profile = preloaded_history = preloaded_catalog = None
                    try:
                        ensure_usage = getattr(self, "_ensure_payroll_usage_features_loaded", None)
                        if callable(ensure_usage):
                            preloaded_usage = ensure_usage()
                    except Exception:
                        preloaded_usage = None
                cached_base = _build_decorated_base_payload(
                    analyse_page=analyse_page,
                    only_unmapped=only_unmapped,
                    include_zero=include_zero,
                    mapping_status_filter=mapping_status_filter,
                    source_filter=source_filter,
                    only_with_ao=only_with_ao,
                    include_payroll=include_payroll,
                    profile_document=preloaded_profile,
                    history_document=preloaded_history,
                    catalog=preloaded_catalog,
                    usage_features=preloaded_usage,
                )
                try:
                    self._base_payload_cache = cached_base
                    self._base_payload_cache_key = base_key
                except Exception:
                    pass
            _t_base_end = _time.perf_counter()

            payload = build_saldobalanse_payload(
                analyse_page=analyse_page,
                search_text=search_text,
                only_unmapped=only_unmapped,
                include_zero=include_zero,
                mapping_status_filter=mapping_status_filter,
                source_filter=source_filter,
                only_with_ao=only_with_ao,
                payroll_scope=payroll_scope,
                include_payroll=include_payroll,
                base_payload=cached_base,
            )
        except Exception as exc:
            log.exception("Saldobalanse refresh feilet")
            SaldobalansePage._invalidate_payload_cache(self)
            self._df_last = pd.DataFrame(columns=ALL_COLUMNS)
            self._profile_document = None
            self._history_document = None
            self._profile_catalog = None
            self._payroll_suggestions = {}
            self._classification_items = {}
            self._clear_tree()
            self._set_status(f"Kunne ikke laste saldobalansen: {exc}")
            self._refresh_detail_panel()
            self._update_map_button_state()
            return

        df = payload.df
        self._df_last = df
        self._profile_document = payload.profile_document
        self._history_document = payload.history_document
        self._profile_catalog = payload.catalog
        self._payroll_suggestions = payload.suggestions
        self._classification_items = dict(payload.classification_items or {})
        _t_postprocess_end = _time.perf_counter()
        SaldobalansePage._ensure_a07_options_loaded(self)
        self._render_df(df)
        _t_render_end = _time.perf_counter()
        if log.isEnabledFor(logging.DEBUG):
            try:
                log.debug(
                    "[saldobalanse] refresh rows=%d base=%.3fs(%s) postprocess=%.3fs render=%.3fs",
                    int(len(df.index)),
                    _t_base_end - _t_start,
                    "cache-hit" if _base_cache_hit else "rebuilt",
                    _t_postprocess_end - _t_base_end,
                    _t_render_end - _t_postprocess_end,
                )
            except Exception:
                pass
        self._restore_tree_selection(preserved_selection, focused_account=preserved_focus)
        if df.empty:
            self._set_status("Ingen kontoer matcher dette utvalget.")
        else:
            total_ub = float(pd.to_numeric(df["UB"], errors="coerce").fillna(0.0).sum())
            self._set_status(f"{len(df.index)} kontoer | Sum UB: {formatting.fmt_amount(total_ub)}")
        self._refresh_detail_panel()
        self._update_map_button_state()

    def _render_df(self, df: pd.DataFrame) -> None:
        self._clear_tree()
        if self._tree is None or df.empty:
            return

        tree = self._tree
        fmt_amount = formatting.fmt_amount
        format_int_no = formatting.format_int_no
        amount_cols = {"IB", "Endring", "UB", "Tilleggspostering", "UB før ÅO", "UB etter ÅO"}
        unclear_set = {"Uklar", "Mistenkelig", "Trenger vurdering"}
        suggestion_set = {"Forslag", "Klar til forslag", "Historikk tilgjengelig"}
        problem_set = {"Umappet", "Sumpost"}

        columns = [col for col in ALL_COLUMNS if col in df.columns]
        missing_cols = [col for col in ALL_COLUMNS if col not in df.columns]

        try:
            konto_series = df["Konto"].astype(str).tolist()
        except Exception:
            konto_series = ["" for _ in range(len(df.index))]
        mapping_series = (
            df["Mappingstatus"].astype(str).tolist() if "Mappingstatus" in df.columns else ["" for _ in konto_series]
        )
        status_series = (
            df["Status"].astype(str).tolist() if "Status" in df.columns else ["" for _ in konto_series]
        )
        locked_series = (
            df["Låst"].astype(str).tolist() if "Låst" in df.columns else ["" for _ in konto_series]
        )

        column_values: dict[str, list[Any]] = {col: df[col].tolist() for col in columns}
        row_count = len(konto_series)

        for idx in range(row_count):
            mapping_status = mapping_series[idx]
            payroll_status = status_series[idx]
            locked = (locked_series[idx] or "").strip()
            if locked:
                tags: tuple[str, ...] = ("payroll_locked",)
            elif payroll_status in unclear_set:
                tags = ("payroll_unclear",)
            elif payroll_status in suggestion_set:
                tags = ("payroll_suggestion",)
            elif mapping_status in problem_set:
                tags = ("problem",)
            elif mapping_status == "Overstyrt":
                tags = ("override",)
            else:
                tags = ()

            values: list[str] = []
            for col in ALL_COLUMNS:
                if col in missing_cols:
                    values.append("")
                    continue
                value = column_values[col][idx]
                if col in amount_cols:
                    values.append(fmt_amount(value))
                elif col == "Antall":
                    if value is None or pd.isna(value):
                        values.append("")
                    else:
                        try:
                            ivalue = int(value or 0)
                        except Exception:
                            ivalue = 0
                        values.append(format_int_no(value) if ivalue else "")
                elif col == "Regnr":
                    if value is None or pd.isna(value):
                        values.append("")
                    else:
                        try:
                            values.append(str(int(value)))
                        except Exception:
                            values.append("")
                else:
                    values.append(str(value or ""))

            try:
                tree.insert("", "end", iid=konto_series[idx], values=tuple(values), tags=tags)
            except Exception:
                continue

    def _set_status(self, text: str) -> None:
        self._status_base_text = str(text or "").strip()
        self._sync_status_text()

    def _on_include_ao_toggled(self) -> None:
        analyse_page = self._analyse_page
        if analyse_page is None:
            self.refresh()
            return
        try:
            analyse_page._on_include_ao_changed()
        except Exception:
            pass
        SaldobalansePage._invalidate_payload_cache(self)
        self.refresh()

    def _selected_accounts(self) -> list[str]:
        selection = self._explicitly_selected_accounts()
        if not selection:
            try:
                focused = self._tree.focus()
            except Exception:
                focused = ""
            if focused:
                selection = [focused]
        return [str(item).strip() for item in selection if str(item).strip()]

    def _selected_account(self) -> tuple[str, str]:
        selection = self._selected_accounts()
        if not selection:
            return "", ""
        konto = selection[0]
        kontonavn = ""
        if not self._df_last.empty:
            try:
                match = self._df_last.loc[self._df_last["Konto"].astype(str).str.strip() == konto]
                if match is not None and not match.empty:
                    kontonavn = str(match.iloc[0].get("Kontonavn") or "").strip()
            except Exception:
                kontonavn = ""
        return konto, kontonavn

    def _selected_suspicious_accounts(self) -> list[str]:
        suspicious: list[str] = []
        for account in self._selected_accounts():
            if self._suspicious_profile_issue_for_account(account):
                suspicious.append(account)
        return suspicious

    def _update_map_button_state(self) -> None:
        selection = self._selected_accounts()
        has_selection = bool(selection)
        has_history = has_selection and self._has_history_for_selected_accounts()
        has_suggestion = has_selection and self._has_strict_suggestions_for_selected_accounts()
        has_suspicious = bool(self._selected_suspicious_accounts())
        profile_for_account = getattr(self, "_profile_for_account", None)
        profiles = (
            [profile_for_account(account) for account in selection]
            if selection and callable(profile_for_account)
            else []
        )
        all_locked = bool(selection) and all(
            bool(getattr(profile, "locked", False)) for profile in profiles if profile is not None
        )
        has_locked = any(bool(getattr(profile, "locked", False)) for profile in profiles if profile is not None)
        selected_workspace_items = getattr(self, "_selected_workspace_items", None)
        determine_primary_action = getattr(self, "_determine_primary_action", None)
        items = selected_workspace_items() if callable(selected_workspace_items) else []
        if callable(determine_primary_action):
            action, label = determine_primary_action(items)
        else:
            action, label = "", ""
        self._current_primary_action = action
        primary_button = getattr(self, "_btn_primary_action", None)
        if primary_button is not None:
            try:
                primary_button.configure(text=label or "Velg konto")
                payroll_mode_check = getattr(self, "_is_payroll_mode", None)
                payroll_mode = payroll_mode_check() if callable(payroll_mode_check) else False
                if payroll_mode and action:
                    primary_button.state(["!disabled"])
                else:
                    primary_button.state(["disabled"])
            except Exception:
                pass
        if self._btn_use_suggestion is not None:
            try:
                if has_suggestion:
                    self._btn_use_suggestion.state(["!disabled"])
                else:
                    self._btn_use_suggestion.state(["disabled"])
            except Exception:
                pass
        if self._btn_use_history is not None:
            try:
                if has_history:
                    self._btn_use_history.state(["!disabled"])
                else:
                    self._btn_use_history.state(["disabled"])
            except Exception:
                pass
        if self._btn_reset_suspicious is not None:
            try:
                if has_suspicious:
                    self._btn_reset_suspicious.state(["!disabled"])
                else:
                    self._btn_reset_suspicious.state(["disabled"])
            except Exception:
                pass
        if self._btn_map is not None:
            try:
                if len(selection) == 1:
                    self._btn_map.state(["!disabled"])
                else:
                    self._btn_map.state(["disabled"])
            except Exception:
                pass
        if self._btn_classify is not None:
            try:
                if selection:
                    self._btn_classify.state(["!disabled"])
                else:
                    self._btn_classify.state(["disabled"])
            except Exception:
                pass
        export_button = getattr(self, "_btn_export", None)
        if export_button is not None:
            try:
                if self._df_last is not None and not self._df_last.empty:
                    export_button.state(["!disabled"])
                else:
                    export_button.state(["disabled"])
            except Exception:
                pass
        selection_use_suggestion = getattr(self, "_btn_selection_use_suggestion", None)
        if selection_use_suggestion is not None:
            try:
                if has_suggestion:
                    selection_use_suggestion.state(["!disabled"])
                else:
                    selection_use_suggestion.state(["disabled"])
            except Exception:
                pass
        selection_use_history = getattr(self, "_btn_selection_use_history", None)
        if selection_use_history is not None:
            try:
                if has_history:
                    selection_use_history.state(["!disabled"])
                else:
                    selection_use_history.state(["disabled"])
            except Exception:
                pass
        selection_reset_suspicious = getattr(self, "_btn_selection_reset_suspicious", None)
        if selection_reset_suspicious is not None:
            try:
                if has_suspicious:
                    selection_reset_suspicious.state(["!disabled"])
                else:
                    selection_reset_suspicious.state(["disabled"])
            except Exception:
                pass
        selection_unlock = getattr(self, "_btn_selection_unlock", None)
        if selection_unlock is not None:
            try:
                selection_unlock.configure(text="Lås opp" if all_locked else "Lås")
                if has_selection and (has_locked or not all_locked):
                    selection_unlock.state(["!disabled"])
                else:
                    selection_unlock.state(["disabled"])
            except Exception:
                pass
        sync_selection_actions = getattr(self, "_sync_selection_actions_visibility", None)
        if callable(sync_selection_actions):
            sync_selection_actions()

    def _map_selected_account(self) -> None:
        konto, kontonavn = self._selected_account()
        if not konto or self._analyse_page is None:
            return
        try:
            import page_analyse_sb

            page_analyse_sb.remap_sb_account(page=self._analyse_page, konto=konto, kontonavn=kontonavn)
        except Exception:
            return
        SaldobalansePage._invalidate_payload_cache(self)
        self.refresh()

    def _client_context(self) -> tuple[str, int | None]:
        return str(getattr(session, "client", "") or ""), _session_year()

    def _profile_for_account(self, account_no: str) -> Any:
        if self._profile_document is None:
            self._ensure_payroll_context_loaded()
        if self._profile_document is None:
            return None
        try:
            return self._profile_document.get(account_no)
        except Exception:
            return None

    def _build_feedback_events(
        self,
        updates: dict[str, dict[str, object]],
        *,
        action_type: str,
    ) -> list[dict[str, object]]:
        def _num(value: object) -> float:
            try:
                return float(pd.to_numeric([value], errors="coerce")[0])
            except Exception:
                return 0.0

        if self._df_last is None or self._df_last.empty:
            return []

        by_account = self._df_last.copy()
        by_account["Konto"] = by_account["Konto"].astype(str).str.strip()
        by_account = by_account.set_index("Konto", drop=False)

        events: list[dict[str, object]] = []
        for account, fields in updates.items():
            account_s = str(account or "").strip()
            if not account_s or not isinstance(fields, dict):
                continue
            row = by_account.loc[account_s] if account_s in by_account.index else None
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0] if not row.empty else None
            result = self._payroll_suggestions.get(account_s)
            suggestion_rows: list[dict[str, object]] = []
            if result is not None:
                for suggestion in result.suggestions.values():
                    value = suggestion.value
                    if isinstance(value, tuple):
                        value_out: object = list(value)
                    else:
                        value_out = value
                    suggestion_rows.append(
                        {
                            "field_name": suggestion.field_name,
                            "value": value_out,
                            "source": suggestion.source,
                            "confidence": suggestion.confidence,
                            "reason": suggestion.reason,
                        }
                    )
            events.append(
                {
                    "action_type": action_type,
                    "account_no": account_s,
                    "account_name": "" if row is None else str(row.get("Kontonavn") or "").strip(),
                    "amount_basis": {
                        "IB": 0.0 if row is None else _num(row.get("IB")),
                        "Endring": 0.0 if row is None else _num(row.get("Endring")),
                        "UB": 0.0 if row is None else _num(row.get("UB")),
                    },
                    "selected": {
                        key: (list(value) if isinstance(value, tuple) else value)
                        for key, value in fields.items()
                    },
                    "suggestions": suggestion_rows,
                }
            )
        return events

    def _persist_payroll_updates(
        self,
        updates: dict[str, dict[str, object]],
        *,
        source: str = "manual",
        confidence: float | None = 1.0,
        status_text: str | None = None,
        feedback_action: str | None = None,
    ) -> None:
        client, year = self._client_context()
        if not client or not updates:
            return
        feedback_events = self._build_feedback_events(updates, action_type=feedback_action or source)
        try:
            konto_klassifisering.update_profiles(
                client,
                updates,
                year=year,
                source=source,
                confidence=confidence,
            )
        except Exception as exc:
            self._set_status(f"Kunne ikke lagre klassifisering: {exc}")
            return
        try:
            payroll_feedback.append_feedback_events(
                client=client,
                year=year,
                events=feedback_events,
            )
        except Exception:
            log.debug("Kunne ikke skrive payroll-feedbacklogg.", exc_info=True)
        SaldobalansePage._invalidate_payload_cache(self)
        self.refresh()
        if status_text:
            self._set_status_detail("")
            self._set_status(status_text)

    def _edit_detail_class_for_selected_accounts(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        try:
            catalog = account_detail_classification.load_detail_class_catalog()
        except Exception:
            catalog = []
        # Nåverdi hentes fra første konto
        first = accounts[0]
        current_id = ""
        profile = self._profile_for_account(first)
        if profile is not None:
            current_id = str(getattr(profile, "detail_class_id", "") or "")
        chosen = self._prompt_detail_class_choice(catalog, current_id)
        if chosen is None:
            return
        updates = {account: {"detail_class_id": chosen} for account in accounts}
        status_msg = (
            f"Fjernet detaljklasse-overstyring på {len(accounts)} kontoer."
            if chosen == ""
            else f"Satte detaljklassifisering på {len(accounts)} kontoer."
        )
        self._persist_payroll_updates(
            updates,
            status_text=status_msg,
            feedback_action="manual_set_detail_class",
        )

    def _edit_owned_company_for_selected_accounts(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        client, year = self._client_context()
        ownership_map = _load_owned_company_name_map(client, year)
        first = accounts[0]
        current_orgnr = ""
        profile = self._profile_for_account(first)
        if profile is not None:
            current_orgnr = str(getattr(profile, "owned_company_orgnr", "") or "")
        chosen = self._prompt_owned_company_choice(ownership_map, current_orgnr)
        if chosen is None:
            return
        updates = {account: {"owned_company_orgnr": chosen} for account in accounts}
        status_msg = (
            f"Fjernet selskapskobling på {len(accounts)} kontoer."
            if chosen == ""
            else f"Koblet {len(accounts)} kontoer til eid selskap."
        )
        self._persist_payroll_updates(
            updates,
            status_text=status_msg,
            feedback_action="manual_set_owned_company",
        )

    def _prompt_detail_class_choice(
        self,
        catalog: list[Any],
        current_id: str,
    ) -> str | None:
        """Modal dropdown; returner valgt id, "" for tom, eller None hvis avbrutt."""

        if tk is None or ttk is None:
            return None
        options: list[tuple[str, str]] = [("", "(ingen overstyring — bruk global regel)")]
        for entry in catalog:
            label = f"{getattr(entry, 'navn', '') or getattr(entry, 'id', '')}"
            options.append((str(getattr(entry, "id", "") or ""), label))

        dlg = tk.Toplevel(self)
        dlg.title("Sett detaljklassifisering")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        ttk.Label(dlg, text="Velg detaljklasse:").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        display_values = [label for _id, label in options]
        var = tk.StringVar(value="")
        current_label = next((lab for _id, lab in options if _id == current_id), display_values[0])
        var.set(current_label)
        combo = ttk.Combobox(dlg, textvariable=var, values=display_values, state="readonly", width=50)
        combo.grid(row=1, column=0, padx=10, pady=4, sticky="ew")

        result: dict[str, str | None] = {"value": None}

        def _ok() -> None:
            chosen_label = var.get()
            for cid, lab in options:
                if lab == chosen_label:
                    result["value"] = cid
                    break
            dlg.destroy()

        def _cancel() -> None:
            result["value"] = None
            dlg.destroy()

        buttons = ttk.Frame(dlg)
        buttons.grid(row=2, column=0, pady=(10, 10))
        ttk.Button(buttons, text="Lagre", command=_ok).pack(side="left", padx=6)
        ttk.Button(buttons, text="Avbryt", command=_cancel).pack(side="left", padx=6)
        dlg.bind("<Return>", lambda _e: _ok())
        dlg.bind("<Escape>", lambda _e: _cancel())
        self.wait_window(dlg)
        return result["value"]

    def _prompt_owned_company_choice(
        self,
        ownership_map: dict[str, str],
        current_orgnr: str,
    ) -> str | None:
        """Modal dropdown; returner valgt orgnr, "" for tom, eller None hvis avbrutt."""

        if tk is None or ttk is None:
            return None

        entries: list[tuple[str, str]] = [("", "(ingen kobling)")]
        for orgnr, name in sorted(ownership_map.items(), key=lambda item: item[1].casefold()):
            entries.append((orgnr, f"{name} ({orgnr})"))

        cleaned_current = "".join(ch for ch in str(current_orgnr or "") if ch.isdigit())
        stale = bool(cleaned_current) and cleaned_current not in ownership_map
        if stale:
            entries.append(
                (cleaned_current, f"{STALE_OWNED_COMPANY_LABEL} ({cleaned_current})")
            )

        dlg = tk.Toplevel(self)
        dlg.title("Sett eid selskap")
        dlg.transient(self.winfo_toplevel())
        dlg.grab_set()
        ttk.Label(dlg, text="Velg eid selskap:").grid(row=0, column=0, padx=10, pady=(10, 4), sticky="w")
        display_values = [label for _val, label in entries]
        var = tk.StringVar(value="")
        current_label = next(
            (lab for org, lab in entries if org == cleaned_current),
            display_values[0],
        )
        var.set(current_label)
        combo = ttk.Combobox(dlg, textvariable=var, values=display_values, state="readonly", width=50)
        combo.grid(row=1, column=0, padx=10, pady=4, sticky="ew")

        result: dict[str, str | None] = {"value": None}

        def _ok() -> None:
            chosen_label = var.get()
            for orgnr, lab in entries:
                if lab == chosen_label:
                    result["value"] = orgnr
                    break
            dlg.destroy()

        def _cancel() -> None:
            result["value"] = None
            dlg.destroy()

        buttons = ttk.Frame(dlg)
        buttons.grid(row=2, column=0, pady=(10, 10))
        ttk.Button(buttons, text="Lagre", command=_ok).pack(side="left", padx=6)
        ttk.Button(buttons, text="Avbryt", command=_cancel).pack(side="left", padx=6)
        dlg.bind("<Return>", lambda _e: _ok())
        dlg.bind("<Escape>", lambda _e: _cancel())
        self.wait_window(dlg)
        return result["value"]

    def _open_advanced_classification(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        try:
            from views_konto_klassifisering import open_klassifisering_editor
        except Exception:
            return
        subset = self._df_last.loc[self._df_last["Konto"].astype(str).isin(accounts), ["Konto", "Kontonavn", "IB", "Endring", "UB"]].copy()
        client, year = self._client_context()
        open_klassifisering_editor(
            self,
            client=client,
            year=year,
            kontoer=subset.rename(columns={"Kontonavn": "Navn"}),
            on_save=self._hard_refresh,
        )
        self._hard_refresh()

    def _assign_a07_to_selected_accounts(self, code: str) -> None:
        code_s = str(code or "").strip()
        accounts = self._selected_accounts()
        if not code_s or not accounts:
            return
        updates = {account: {"a07_code": code_s} for account in accounts}
        self._persist_payroll_updates(
            updates,
            status_text=f"Tildelte A07-kode {code_s} til {len(accounts)} kontoer.",
            feedback_action="manual_assign_a07",
        )

    def _assign_group_to_selected_accounts(self, group_id: str) -> None:
        group_s = str(group_id or "").strip()
        accounts = self._selected_accounts()
        if not group_s or not accounts:
            return
        updates = {account: {"control_group": group_s} for account in accounts}
        self._persist_payroll_updates(
            updates,
            status_text=f"Tildelte RF-1022-post til {len(accounts)} kontoer.",
            feedback_action="manual_assign_rf1022",
        )

    def _add_tag_to_selected_accounts(self, tag_id: str) -> None:
        tag_s = str(tag_id or "").strip()
        accounts = self._selected_accounts()
        if not tag_s or not accounts:
            return
        updates: dict[str, dict[str, object]] = {}
        for account in accounts:
            current = self._profile_for_account(account)
            tags = set(getattr(current, "control_tags", ()) or ())
            tags.add(tag_s)
            updates[account] = {"control_tags": tuple(sorted(tags))}
        self._persist_payroll_updates(
            updates,
            status_text=f"La til lønnsflagg på {len(accounts)} kontoer.",
            feedback_action="manual_add_tag",
        )

    def _remove_tag_from_selected_accounts(self, tag_id: str) -> None:
        tag_s = str(tag_id or "").strip()
        accounts = self._selected_accounts()
        if not tag_s or not accounts:
            return
        updates: dict[str, dict[str, object]] = {}
        for account in accounts:
            current = self._profile_for_account(account)
            tags = {tag for tag in (getattr(current, "control_tags", ()) or ()) if str(tag).strip() and str(tag).strip() != tag_s}
            updates[account] = {"control_tags": tuple(sorted(tags))}
        self._persist_payroll_updates(
            updates,
            status_text=f"Fjernet lønnsflagg på {len(accounts)} kontoer.",
            feedback_action="manual_remove_tag",
        )

    def _append_selected_account_name_to_a07_alias(self, code: str) -> None:
        code_s = str(code or "").strip()
        _account_no, account_name = self._selected_account()
        alias_text = str(account_name or "").strip()
        if not code_s or not alias_text:
            self._set_status("Velg én konto med kontonavn for å legge til A07-alias.")
            return
        document = classification_config.load_alias_library_document()
        concepts = document.setdefault("concepts", {})
        payload = concepts.setdefault(code_s, {})
        aliases = [str(value).strip() for value in payload.get("aliases", []) if str(value).strip()]
        if alias_text not in aliases:
            aliases.append(alias_text)
        payload["aliases"] = aliases
        concepts[code_s] = payload
        document["concepts"] = concepts
        path = classification_config.save_alias_library_document(document)
        self._after_rule_learning_saved(f"La til kontonavn som A07-alias for {code_s}: {alias_text} ({path.name})")

    def _append_selected_account_to_a07_boost(self, code: str) -> None:
        code_s = str(code or "").strip()
        account_no, _account_name = self._selected_account()
        if not code_s or not account_no:
            self._set_status("Velg én konto for å legge kontonummer til A07-oppsettet.")
            return
        document = classification_config.load_alias_library_document()
        concepts = document.setdefault("concepts", {})
        payload = concepts.setdefault(code_s, {})
        boost_accounts: list[int] = []
        for raw in payload.get("boost_accounts", []):
            try:
                boost_accounts.append(int(raw))
            except Exception:
                continue
        try:
            account_int = int(str(account_no).strip())
        except Exception:
            self._set_status("Kunne ikke lese kontonummeret som heltall.")
            return
        if account_int not in boost_accounts:
            boost_accounts.append(account_int)
        payload["boost_accounts"] = sorted(boost_accounts)
        concepts[code_s] = payload
        document["concepts"] = concepts
        path = classification_config.save_alias_library_document(document)
        self._after_rule_learning_saved(f"La til konto {account_no} som A07-boost for {code_s} ({path.name})")

    def _append_selected_account_name_to_rf1022_alias(self, group_id: str) -> None:
        group_s = str(group_id or "").strip()
        _account_no, account_name = self._selected_account()
        alias_text = str(account_name or "").strip()
        if not group_s or not alias_text:
            self._set_status("Velg én konto med kontonavn for å legge til RF-1022-alias.")
            return
        document = classification_config.load_catalog_document()
        raw_groups = document.get("groups")
        if isinstance(raw_groups, list):
            groups = raw_groups
        elif isinstance(raw_groups, dict):
            groups = list(raw_groups.values())
        else:
            groups = []
        payload = next(
            (
                entry
                for entry in groups
                if isinstance(entry, dict) and str(entry.get("id", "") or "").strip() == group_s
            ),
            None,
        )
        if payload is None:
            payload = {
                "id": group_s,
                "label": group_s,
                "active": True,
                "sort_order": 9999,
                "applies_to": ["analyse", "a07", "kontrolloppstilling"],
                "aliases": [],
                "category": "payroll_rf1022_group",
            }
            groups.append(payload)
        aliases = [str(value).strip() for value in payload.get("aliases", []) if str(value).strip()]
        if alias_text not in aliases:
            aliases.append(alias_text)
        payload["aliases"] = aliases
        document["groups"] = groups
        path = classification_config.save_catalog_document(document)
        self._after_rule_learning_saved(f"La til kontonavn som RF-1022-alias for {group_s}: {alias_text} ({path.name})")

    def _after_rule_learning_saved(self, message: str) -> None:
        try:
            payroll_classification.invalidate_runtime_caches()
        except Exception:
            pass
        SaldobalansePage._invalidate_payload_cache(self)
        app = getattr(session, "APP", None)
        for attr_name in ("page_a07", "page_analyse"):
            page = getattr(app, attr_name, None)
            refresh = getattr(page, "refresh_from_session", None)
            if callable(refresh):
                try:
                    refresh(session)
                except Exception:
                    continue
        self.refresh()
        self._set_status(f"{message} Forslagscache er nullstilt. Bruk Oppfrisk om du vil kontrollere endringen på nytt.")

    def _apply_history_to_selected_accounts(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        if self._history_document is None:
            self._ensure_payroll_context_loaded()
        if self._history_document is None:
            return
        updates: dict[str, dict[str, object]] = {}
        skipped_missing = 0
        skipped_same = 0
        for account in accounts:
            history_profile = self._history_document.get(account)
            if history_profile is None:
                skipped_missing += 1
                continue
            history_update = {
                "a07_code": str(getattr(history_profile, "a07_code", "") or "").strip(),
                "control_group": str(getattr(history_profile, "control_group", "") or "").strip(),
                "control_tags": tuple(getattr(history_profile, "control_tags", ()) or ()),
            }
            current_profile = self._profile_for_account(account)
            current_state = {
                "a07_code": str(getattr(current_profile, "a07_code", "") or "").strip() if current_profile else "",
                "control_group": str(getattr(current_profile, "control_group", "") or "").strip()
                if current_profile
                else "",
                "control_tags": tuple(getattr(current_profile, "control_tags", ()) or ()) if current_profile else (),
            }
            if all(
                _normalize_classification_field_value(current_state[key])
                == _normalize_classification_field_value(value)
                for key, value in history_update.items()
            ):
                skipped_same += 1
                continue
            updates[account] = history_update
        if not updates:
            reasons: list[str] = []
            if skipped_same:
                reasons.append(f"{skipped_same} allerede i samsvar med historikk")
            if skipped_missing:
                reasons.append(f"{skipped_missing} uten historikk")
            reason_text = f" ({', '.join(reasons)})" if reasons else ""
            self._set_status(f"Ingen kontoer oppdatert med fjorårets klassifisering{reason_text}.")
            return
        skipped_total = len(accounts) - len(updates)
        self._persist_payroll_updates(
            updates,
            source="history",
            confidence=1.0,
            status_text=(
                f"Brukte fjorårets klassifisering på {len(updates)} kontoer."
                + (f" Hoppet over {skipped_total}." if skipped_total else "")
            ),
            feedback_action="use_history",
        )

    def _apply_best_suggestions_to_selected_accounts(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        updates: dict[str, dict[str, object]] = {}
        skipped_locked = 0
        skipped_without_suggestion = 0
        skipped_same = 0
        for account in accounts:
            item = self._workspace_item_for_account(account)
            if item is None:
                skipped_without_suggestion += 1
                continue
            if bool(getattr(item.current, "locked", False)):
                skipped_locked += 1
                continue
            fields = _suggested_update_for_item(item)
            if fields:
                updates[account] = fields
            elif classification_workspace.matching_suggestion_labels(item):
                skipped_same += 1
            else:
                skipped_without_suggestion += 1
        if not updates:
            reasons: list[str] = []
            if skipped_same:
                reasons.append(f"{skipped_same} i samsvar")
            if skipped_locked:
                reasons.append(f"{skipped_locked} låst")
            if skipped_without_suggestion:
                reasons.append(f"{skipped_without_suggestion} uten forslag")
            reason_text = f" ({', '.join(reasons)})" if reasons else ""
            self._set_status(f"Ingen forslag godkjent{reason_text}.")
            return
        skipped_total = len(accounts) - len(updates)
        self._persist_payroll_updates(
            updates,
            source="heuristic",
            confidence=0.9,
            status_text=(
                f"Godkjente forslag på {len(updates)} kontoer."
                + (f" Hoppet over {skipped_total}." if skipped_total else "")
            ),
            feedback_action="approve_suggestion",
        )

    def _toggle_lock_selected_accounts(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        profiles = [self._profile_for_account(account) for account in accounts]
        should_lock = not all(bool(getattr(profile, "locked", False)) for profile in profiles if profile is not None)
        updates = {account: {"locked": should_lock} for account in accounts}
        self._persist_payroll_updates(
            updates,
            status_text=f"{'Låste' if should_lock else 'Låste opp'} {len(accounts)} kontoer.",
            feedback_action="toggle_lock",
        )

    def _clear_selected_payroll_fields(self) -> None:
        accounts = self._selected_accounts()
        if not accounts:
            return
        updates = {
            account: {
                "a07_code": "",
                "control_group": "",
                "control_tags": (),
            }
            for account in accounts
        }
        self._persist_payroll_updates(
            updates,
            status_text=f"Nullstilte lønnsklassifisering på {len(accounts)} kontoer.",
            feedback_action="clear_payroll_fields",
        )

    def _clear_selected_suspicious_payroll_fields(self) -> None:
        accounts = self._selected_suspicious_accounts()
        if not accounts:
            self._set_status("Fant ingen mistenkelige lagrede lønnsklassifiseringer i utvalget.")
            return
        updates = {
            account: {
                "a07_code": "",
                "control_group": "",
                "control_tags": (),
            }
            for account in accounts
        }
        self._persist_payroll_updates(
            updates,
            status_text=f"Nullstilte lønnsklassifisering på {len(accounts)} mistenkelige kontoer.",
            feedback_action="clear_suspicious_payroll_fields",
        )

    def _open_context_menu(self, event: Any) -> None:
        if self._tree is None or tk is None:
            return
        try:
            row_id = self._tree.identify_row(event.y)
        except Exception:
            row_id = ""
        if row_id:
            self._prepare_context_menu_selection(row_id)
        accounts = self._selected_accounts()
        if not accounts:
            return
        has_history = self._has_history_for_selected_accounts()
        has_suggestion = self._has_strict_suggestions_for_selected_accounts()

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label="Godkjenn forslag",
            command=self._apply_best_suggestions_to_selected_accounts,
            state="normal" if has_suggestion else "disabled",
        )
        menu.add_command(
            label="Bruk fjorårets klassifisering",
            command=self._apply_history_to_selected_accounts,
            state="normal" if has_history else "disabled",
        )
        menu.add_separator()

        a07_menu = tk.Menu(menu, tearoff=0)
        for code, label in self._a07_options[:80]:
            item_label = f"{code} - {label}" if label else code
            a07_menu.add_command(label=item_label, command=lambda value=code: self._assign_a07_to_selected_accounts(value))
        if not self._a07_options:
            a07_menu.add_command(label="Ingen koder funnet", state="disabled")
        menu.add_cascade(label="Tildel A07-kode", menu=a07_menu)

        group_menu = tk.Menu(menu, tearoff=0)
        for group_id, label in payroll_classification.payroll_group_options(self._profile_catalog):
            group_menu.add_command(label=label, command=lambda value=group_id: self._assign_group_to_selected_accounts(value))
        menu.add_cascade(label="Tildel RF-1022-post", menu=group_menu)

        tag_add_menu = tk.Menu(menu, tearoff=0)
        tag_remove_menu = tk.Menu(menu, tearoff=0)
        for tag_id, label in payroll_classification.payroll_tag_options(self._profile_catalog):
            tag_add_menu.add_command(label=label, command=lambda value=tag_id: self._add_tag_to_selected_accounts(value))
            tag_remove_menu.add_command(label=label, command=lambda value=tag_id: self._remove_tag_from_selected_accounts(value))
        menu.add_cascade(label="Legg til lønnsflagg", menu=tag_add_menu)
        menu.add_cascade(label="Fjern lønnsflagg", menu=tag_remove_menu)

        if len(accounts) == 1:
            alias_menu = tk.Menu(menu, tearoff=0)
            a07_alias_menu = tk.Menu(alias_menu, tearoff=0)
            a07_boost_menu = tk.Menu(alias_menu, tearoff=0)
            for code, label in self._a07_options[:80]:
                item_label = f"{code} - {label}" if label else code
                a07_alias_menu.add_command(
                    label=item_label,
                    command=lambda value=code: self._append_selected_account_name_to_a07_alias(value),
                )
                a07_boost_menu.add_command(
                    label=item_label,
                    command=lambda value=code: self._append_selected_account_to_a07_boost(value),
                )
            rf1022_alias_menu = tk.Menu(alias_menu, tearoff=0)
            for group_id, label in payroll_classification.payroll_group_options(self._profile_catalog):
                rf1022_alias_menu.add_command(
                    label=label,
                    command=lambda value=group_id: self._append_selected_account_name_to_rf1022_alias(value),
                )
            alias_menu.add_cascade(label="Kontonavn -> A07-alias", menu=a07_alias_menu)
            alias_menu.add_cascade(label="Kontonavn -> RF-1022-alias", menu=rf1022_alias_menu)
            alias_menu.add_separator()
            alias_menu.add_cascade(label="Konto -> prioriter A07-kode (avansert)", menu=a07_boost_menu)
            menu.add_cascade(label="Lær av denne raden", menu=alias_menu)

        menu.add_separator()
        menu.add_command(label="Lås / lås opp", command=self._toggle_lock_selected_accounts)
        menu.add_command(label="Nullstill lønnsklassifisering", command=self._clear_selected_payroll_fields)
        menu.add_separator()
        menu.add_command(
            label="Sett detaljklassifisering…",
            command=self._edit_detail_class_for_selected_accounts,
        )
        menu.add_command(
            label="Sett eid selskap…",
            command=self._edit_owned_company_for_selected_accounts,
        )
        menu.add_separator()
        menu.add_command(label="Åpne avansert klassifisering...", command=self._open_advanced_classification)
        self._menu_tree = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
