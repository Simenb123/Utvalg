"""saldobalanse_payload.py — Datalag for Saldobalanse-fanen.

Inneholder dataclasses, byggere, dekoratorer, lastere og tekst-hjelpere som
bygger DataFrame-visningen for [page_saldobalanse.py](page_saldobalanse.py).
Null UI-avhengigheter — trygt å importere fra tester og admin-siden.

Delt kontrakt (kolonner, presets, filter-etiketter) ligger her for å hindre
sirkulære importer mellom `page_saldobalanse` og kommende modul-splittinger.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

import account_detail_classification
import classification_workspace
import formatting
import konto_klassifisering
import payroll_classification
import session
from a07_feature import build_account_usage_features
from a07_feature import page_control_data as control_data
from a07_feature.control.basis import control_gl_basis_column_for_account
from analyse_mapping_service import UnmappedAccountIssue


log = logging.getLogger(__name__)


ALL_COLUMNS = (
    "Konto",
    "Kontonavn",
    "Gruppe",
    "A07-kode",
    "RF-1022-post",
    "Kol",
    "Lønnsstatus",
    "Problem",
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
    "A07-kode",
    "RF-1022-post",
    "Lønnsstatus",
    "Problem",
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
    "A07-kode",
    "RF-1022-post",
    "Detaljklassifisering",
    "Eid selskap",
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
    "A07-kode": 170,
    "RF-1022-post": 170,
    "Kol": 70,
    "Lønnsstatus": 110,
    "Problem": 220,
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
        "Kol",
        "A07-kode",
        "RF-1022-post",
    ),
    "Lønn/A07": (
        "Konto",
        "Kontonavn",
        "Endring",
        "UB",
        "Kol",
        "A07-kode",
        "RF-1022-post",
        "Lønnsstatus",
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


_MAPPING_ISSUES_CACHE: dict[tuple, list[UnmappedAccountIssue]] = {}
_GROUP_MAPPING_CACHE: dict[str, dict[str, str]] = {}


def _invalidate_mapping_issues_cache() -> None:
    """Tøm mapping-issues-cache. Kalles ved endring i klient/år eller RL-config."""
    _MAPPING_ISSUES_CACHE.clear()


def _invalidate_group_mapping_cache(client: str | None = None) -> None:
    """Tøm gruppe-mapping-cache (helt, eller kun for én klient)."""
    if client is None:
        _GROUP_MAPPING_CACHE.clear()
        return
    _GROUP_MAPPING_CACHE.pop(str(client), None)


def _load_mapping_issues(analyse_page: Any) -> list[UnmappedAccountIssue]:
    # Cache-nøkkel basert på (klient, år, id av sb-df).
    # id() på DataFrame er stabil så lenge samme objekt lever. Ved rebuild
    # av SB lages ny DataFrame → ny id → ny cache-nøkkel.
    try:
        client = str(getattr(session, "client", "") or "")
        year = _session_year()
        sb_df = getattr(analyse_page, "_rl_sb_df", None)
        df_id = id(sb_df) if sb_df is not None else 0
        cache_key = (client, year, df_id)
    except Exception:
        cache_key = None

    if cache_key is not None:
        cached = _MAPPING_ISSUES_CACHE.get(cache_key)
        if cached is not None:
            return cached

    try:
        import analyse_mapping_service

        result = analyse_mapping_service.build_page_mapping_issues(analyse_page, use_filtered_hb=False)
    except Exception as exc:
        log.debug("Kunne ikke bygge mapping-issues for Saldobalanse: %s", exc)
        result = []

    if cache_key is not None:
        _MAPPING_ISSUES_CACHE[cache_key] = result
    return result


def _load_group_mapping(client: str) -> dict[str, str]:
    if not client:
        return {}
    cached = _GROUP_MAPPING_CACHE.get(str(client))
    if cached is not None:
        return cached
    try:
        import konto_klassifisering

        result = konto_klassifisering.load(client) or {}
    except Exception:
        result = {}
    _GROUP_MAPPING_CACHE[str(client)] = result
    return result


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


_OWNED_COMPANY_CACHE: dict[tuple[str, str], dict[str, str]] = {}


def _invalidate_owned_company_cache(client: str | None = None) -> None:
    """Tøm cache for eide-selskaper-oppslaget.

    Kalles fra AR-importer/opprettelse slik at nye ownerships reflekteres
    i Saldobalanse-fanen uten app-restart.
    """
    if client is None:
        _OWNED_COMPANY_CACHE.clear()
        return
    keys_to_drop = [k for k in _OWNED_COMPANY_CACHE if k[0] == client]
    for k in keys_to_drop:
        _OWNED_COMPANY_CACHE.pop(k, None)


def _load_owned_company_name_map(client: str, year: int | None) -> dict[str, str]:
    """Returner orgnr (kun siffer) -> selskapsnavn for aktiv klients eide selskaper.

    Returnerer tom dict hvis klient eller år mangler, eller hvis AR-oppslaget feiler.
    Cachet per (client, year) — `ar_store.get_client_ownership_overview` er
    en ~3-7s operasjon som ellers ville kjørt hver refresh.
    """

    if not client:
        return {}
    cache_key = (str(client), str(year or ""))
    cached = _OWNED_COMPANY_CACHE.get(cache_key)
    if cached is not None:
        return cached
    try:
        from src.pages.ar.backend import store as ar_store
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
    _OWNED_COMPANY_CACHE[cache_key] = mapping
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
    # Fin-granulær timing så vi kan se hvor de 300-600ms faktisk går:
    # load_context, build_items, row_loop.
    import time as _time
    try:
        from src.monitoring.perf import record_event as _record_event
    except Exception:
        _record_event = None  # type: ignore[assignment]

    def _phase(label: str, t0: float) -> float:
        t1 = _time.perf_counter()
        if _record_event is not None:
            try:
                _record_event(f"sb.payroll.{label}", (t1 - t0) * 1000.0)
            except Exception:
                pass
        return t1

    _t = _time.perf_counter()
    if preloaded_context is not None:
        document, history_document, catalog = preloaded_context
    else:
        document, history_document, catalog = _load_payroll_context(client, year)
    _t = _phase("load_context", _t)
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
    _t = _phase("build_items", _t)

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
    _phase("row_loop", _t)
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
    import time as _time
    # Hver fase måles og sendes til monitoring-subsystemet (src/monitoring).
    # UTVALG_PROFILE_SB=1 gir i tillegg stderr-print via bakoverkompat i perf._parse_profile_env.
    try:
        from src.monitoring.perf import record_event as _record_event
    except Exception:
        _record_event = None  # type: ignore[assignment]

    def _tick(label: str, t0: float) -> float:
        t1 = _time.perf_counter()
        duration_ms = (t1 - t0) * 1000.0
        if _record_event is not None:
            try:
                _record_event(f"sb.base.{label}", duration_ms)
            except Exception:
                pass
        return t1

    _t = _time.perf_counter()
    base_sb_df, adjusted_sb_df, effective_sb_df = _resolve_sb_views(analyse_page)
    _t = _tick("resolve_sb_views", _t)

    effective = _normalize_sb_frame(effective_sb_df, suffix="effective")
    base = _normalize_sb_frame(base_sb_df, suffix="base")
    adjusted = _normalize_sb_frame(adjusted_sb_df, suffix="adjusted")
    _t = _tick("normalize_sb_frames", _t)

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
        # Vektorisert alternativ til df.apply(_first_text_value, axis=1):
        # bruker pandas' coalesce-mønster (først ikke-tom verdi per rad).
        cleaned_cols: list[pd.Series] = []
        for col in name_cols:
            s = merged[col].astype("string").str.strip()
            s = s.mask(s.str.lower().isin({"nan", "none", "<na>"}), "")
            s = s.fillna("")
            cleaned_cols.append(s)
        # Start med første kolonne, fyll inn fra neste der tom.
        navn = cleaned_cols[0]
        for s in cleaned_cols[1:]:
            navn = navn.mask(navn == "", s)
        merged["Kontonavn"] = navn.astype(str)
    else:
        merged["Kontonavn"] = ""

    merged["IB"] = pd.to_numeric(merged.get("IB_effective"), errors="coerce").fillna(0.0)
    merged["Endring"] = pd.to_numeric(merged.get("Endring_effective"), errors="coerce").fillna(0.0)
    merged["UB"] = pd.to_numeric(merged.get("UB_effective"), errors="coerce").fillna(0.0)
    # Vektorisert: list-comp over tolist() er typisk 10-20× raskere enn
    # df.apply(axis=1) når funksjonen er ren Python og ikke pandas-operasjoner.
    _kol_konto = merged["Konto"].tolist()
    _kol_navn = merged["Kontonavn"].tolist()
    merged["Kol"] = [
        control_gl_basis_column_for_account(k, n, requested_basis="Endring")
        for k, n in zip(_kol_konto, _kol_navn)
    ]
    merged["UB før ÅO"] = pd.to_numeric(merged.get("UB_base"), errors="coerce").fillna(merged["UB"])
    merged["UB etter ÅO"] = pd.to_numeric(merged.get("UB_adjusted"), errors="coerce").fillna(merged["UB"])
    merged["Tilleggspostering"] = merged["UB etter ÅO"] - merged["UB før ÅO"]

    _t = _tick("merge_and_normalize", _t)

    hb_counts = _build_hb_counts(getattr(analyse_page, "dataset", None))
    merged = merged.merge(hb_counts, how="left", on="Konto")
    merged["Antall"] = pd.to_numeric(merged.get("Antall"), errors="coerce").fillna(0).astype(int)
    _t = _tick("hb_counts", _t)

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

    _t = _tick("mapping_issues", _t)

    client = str(getattr(session, "client", "") or "")
    year = _session_year()
    groups = _load_group_mapping(client)
    # Pre-load group_id → label én gang (var tidligere én disk-read per konto).
    try:
        label_map = konto_klassifisering.group_label_map() or {}
    except Exception:
        label_map = {}

    def _lookup_gruppe(konto_val) -> str:
        group_id = groups.get(str(konto_val).strip(), "")
        if not group_id:
            return ""
        return label_map.get(group_id, group_id)

    merged["Gruppe"] = merged["Konto"].map(_lookup_gruppe)
    _t = _tick("group_mapping", _t)

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

    _t = _tick("filters", _t)

    if include_payroll:
        effective_usage = usage_features
        if effective_usage is None:
            effective_usage = _resolve_payroll_usage_features(analyse_page)
        _t = _tick("resolve_payroll_usage", _t)
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
        _t = _tick("decorate_payroll", _t)
    else:
        merged, _, history_document, catalog, suggestions, classification_items = _apply_blank_payroll_columns(merged)
        _t = _tick("blank_payroll", _t)
        if profile_document is None:
            profile_document = _load_account_profile_document_only(client, year)

    ownership_map = _load_owned_company_name_map(client, year)
    _t = _tick("ownership_map", _t)
    merged = _decorate_with_detail_class_and_ownership(
        merged,
        profile_document=profile_document,
        ownership_map=ownership_map,
    )
    _t = _tick("detail_class_and_ownership", _t)

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


# Stretch-sett — hvilke kolonner som skal få ``stretch=True`` i Treeview.
# Tidligere hardkodet inline i page_saldobalanse._build_ui; flyttet hit
# slik at build_column_specs har én kilde for kolonne-metadata.
STRETCH_COLUMNS = frozenset({
    "Kontonavn",
    "Regnskapslinje",
    "Problem",
})


def build_column_specs(year: int | None = None):
    """Returner `ColumnSpec`-liste for Saldobalanse-Treeview.

    Importerer `ColumnSpec` lazy for å unngå at payload-modulen drar
    inn Tkinter ved import (payload brukes også fra ikke-GUI-kontekst).

    ``year`` brukes for å formatere årsavhengige kolonne-overskrifter
    (f.eks. "IB 2025" / "UB 2024") via ``columns_vocabulary.heading``.
    """
    from ui_managed_treeview import ColumnSpec
    from src.shared.columns_vocabulary import heading

    specs = []
    for col in ALL_COLUMNS:
        specs.append(
            ColumnSpec(
                id=col,
                heading=heading(col, year=year),
                width=COLUMN_WIDTHS.get(col, 110),
                minwidth=50,
                anchor="e" if col in NUMERIC_COLUMNS else "w",
                stretch=col in STRETCH_COLUMNS,
                visible_by_default=col in DEFAULT_VISIBLE_COLUMNS,
                sortable=True,
            )
        )
    return specs
