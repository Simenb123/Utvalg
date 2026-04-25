from __future__ import annotations

from typing import Sequence

import pandas as pd

from .data import RF1022_UNKNOWN_GROUP, work_family_for_a07_code, work_family_for_rf1022_group
from .rf1022_report import RF1022_TOTAL_ROW_ID


def rf1022_candidate_tree_tag(row: pd.Series) -> str:
    status = str(row.get("Forslagsstatus") or "").strip()
    return "suggestion_ok" if status == "Trygt forslag" else "suggestion_review"


def _family_tag_from_name(family: object, *, suspicious: bool = False) -> str:
    if suspicious:
        return "family_warning"
    family_s = str(family or "").strip().lower()
    if family_s in {"payroll", "refund", "natural", "pension"}:
        return f"family_{family_s}"
    return "family_unknown"


def _status_tag_from_values(*values: object) -> str | None:
    tokens = {str(value or "").strip().casefold() for value in values if str(value or "").strip()}
    if tokens & {"feil", "mistenkelig", "mistenkelig kobling", "mistenkelig rest", "blocked", "konflikt"}:
        return "family_warning"
    if tokens & {
        "uavklart",
        "uavklart rf-1022",
        "uavklart_rf1022",
        "maa vurderes",
        "må vurderes",
        "maa avklares",
        "må avklares",
        "kontroller kobling",
        "har forslag",
        "har historikk",
        "forslag",
        "historikk",
        "review",
        "krever splitt",
        "laast 0-diff",
        "låst 0-diff",
    }:
        return "suggestion_review"
    if tokens & {"trygg", "ferdig", "avstemt", "trygt forslag", "accepted"}:
        return "suggestion_ok"
    return None


def control_family_tree_tag(row: pd.Series) -> str:
    status_tag = _status_tag_from_values(
        row.get("MappingAuditStatus"),
        row.get("GuidetStatus"),
        row.get("Arbeidsstatus"),
        row.get("Status"),
        row.get("Rf1022GroupId"),
    )
    try:
        diff_value = pd.to_numeric(row.get("Diff"), errors="coerce")
    except Exception:
        diff_value = float("nan")
    try:
        gl_value = pd.to_numeric(row.get("GL_Belop"), errors="coerce")
    except Exception:
        gl_value = float("nan")
    try:
        account_count = int(pd.to_numeric(row.get("AntallKontoer"), errors="coerce") or 0)
    except Exception:
        account_count = 0
    mapping_text = str(row.get("DagensMapping") or row.get("Kontoer") or "").strip()
    has_linked_gl = (
        account_count > 0
        or bool(mapping_text)
        or (pd.notna(gl_value) and abs(float(gl_value)) > 0.005)
    )
    non_audit_status_tag = _status_tag_from_values(
        row.get("GuidetStatus"),
        row.get("Arbeidsstatus"),
        row.get("Status"),
        row.get("Rf1022GroupId"),
    )
    if status_tag == "family_warning" and non_audit_status_tag == "family_warning":
        return status_tag
    if has_linked_gl and pd.notna(diff_value) and abs(float(diff_value)) <= 0.005:
        return "suggestion_ok"
    if status_tag == "family_warning":
        return status_tag
    if status_tag is not None:
        return status_tag
    suspicious = bool(row.get("CurrentMappingSuspicious", False))
    family = str(row.get("WorkFamily") or "").strip()
    if not family:
        family = work_family_for_a07_code(row.get("Kode"))
    return _family_tag_from_name(family, suspicious=suspicious)


def rf1022_overview_tree_tag(row: pd.Series) -> str:
    if str(row.get("GroupId") or "").strip() == RF1022_TOTAL_ROW_ID:
        return "summary_total"
    if str(row.get("GroupId") or "").strip() == RF1022_UNKNOWN_GROUP:
        return "family_warning"
    for column in ("Diff", "AgaDiff"):
        try:
            value = pd.to_numeric(row.get(column), errors="coerce")
        except Exception:
            value = float("nan")
        if pd.notna(value) and abs(float(value)) > 0.005:
            return "suggestion_review"
    status_tag = _status_tag_from_values(row.get("Status"), row.get("Kontroll"))
    if status_tag is not None:
        return status_tag
    family = str(row.get("WorkFamily") or "").strip()
    if not family:
        family = work_family_for_rf1022_group(row.get("GroupId"))
    return _family_tag_from_name(family)


def control_gl_family_tree_tag(row: pd.Series) -> str:
    status_tag = _status_tag_from_values(row.get("MappingAuditStatus"), row.get("Kontroll"), row.get("Status"))
    if status_tag is not None:
        return status_tag
    mapped_code = str(row.get("Kode") or "").strip()
    if not mapped_code:
        return "family_unknown"
    family = str(row.get("WorkFamily") or "").strip() or work_family_for_a07_code(mapped_code)
    return _family_tag_from_name(family)


def control_gl_tree_tag(
    row: pd.Series,
    selected_code: str | None,
    suggested_accounts: Sequence[object] | None = None,
) -> str:
    _ = (selected_code, suggested_accounts)
    mapped_code = str(row.get("Kode") or "").strip()
    if not mapped_code:
        return "control_gl_unmapped"
    return "control_gl_mapped"


def reconcile_tree_tag(row: pd.Series) -> str:
    try:
        within = bool(row.get("WithinTolerance", False))
    except Exception:
        within = False
    return "reconcile_ok" if within else "reconcile_diff"


def control_queue_tree_tag(row: pd.Series) -> str:
    status_tag = _status_tag_from_values(
        row.get("MappingAuditStatus"),
        row.get("GuidetStatus"),
        row.get("Arbeidsstatus"),
        row.get("Status"),
        row.get("Rf1022GroupId"),
    )
    try:
        diff_value = pd.to_numeric(row.get("Diff"), errors="coerce")
    except Exception:
        diff_value = float("nan")
    try:
        gl_value = pd.to_numeric(row.get("GL_Belop"), errors="coerce")
    except Exception:
        gl_value = float("nan")
    try:
        account_count = int(pd.to_numeric(row.get("AntallKontoer"), errors="coerce") or 0)
    except Exception:
        account_count = 0
    mapping_text = str(row.get("DagensMapping") or row.get("Kontoer") or "").strip()
    has_linked_gl = (
        account_count > 0
        or bool(mapping_text)
        or (pd.notna(gl_value) and abs(float(gl_value)) > 0.005)
    )
    non_audit_status_tag = _status_tag_from_values(
        row.get("GuidetStatus"),
        row.get("Arbeidsstatus"),
        row.get("Status"),
        row.get("Rf1022GroupId"),
    )
    if status_tag == "family_warning" and non_audit_status_tag == "family_warning":
        return "control_manual"
    if has_linked_gl and pd.notna(diff_value) and abs(float(diff_value)) <= 0.005:
        return "control_done"
    if status_tag == "suggestion_ok":
        return "control_done"
    if status_tag == "suggestion_review":
        return "control_review"
    if status_tag == "family_warning":
        return "control_manual"
    if pd.notna(diff_value) and abs(float(diff_value)) <= 0.005:
        return "control_done"
    status_s = str(row.get("GuidetStatus") or row.get("Arbeidsstatus") or row.get("Status") or "").strip()
    if status_s in {"Har forslag", "Har historikk", "Forslag", "Historikk"}:
        return "control_review"
    if status_s in {
        "Mistenkelig kobling",
        "Maa avklares",
        "Lonnskontroll",
        "Kontroller kobling",
        "Ulost",
        "UlÃ¸st",
        "UlÃ¸st",
        "Manuell",
    }:
        return "control_manual"
    if status_s == "Ferdig":
        return "control_done"
    if pd.notna(diff_value):
        return "control_manual"
    if status_s:
        return "control_manual"
    return "control_default"


def suggestion_tree_tag(row: pd.Series) -> str:
    status_tag = _status_tag_from_values(row.get("Forslagsstatus"), row.get("Status"), row.get("SuggestionGuardrail"))
    if status_tag == "family_warning":
        return "suggestion_review"
    if status_tag in {"suggestion_ok", "suggestion_review"}:
        return status_tag
    guardrail = str(row.get("SuggestionGuardrail") or "").strip().lower()
    if guardrail == "accepted":
        return "suggestion_ok"
    if guardrail in {"review", "blocked"}:
        return "suggestion_review"
    try:
        explain = str(row.get("Explain", "") or "").lower()
        has_history = bool(str(row.get("HistoryAccounts", "") or "").strip())
        score = float(row.get("Score") or 0.0)
        visual_strict_auto = bool(row.get("WithinTolerance", False)) and (
            has_history or ("regel=" in explain and score >= 0.9)
        )
    except Exception:
        visual_strict_auto = False
    if visual_strict_auto:
        return "suggestion_ok"
    try:
        if bool(row.get("WithinTolerance", False)) or float(row.get("Score") or 0.0) >= 0.85:
            return "suggestion_review"
    except Exception:
        pass
    return "suggestion_default"


__all__ = [
    "control_family_tree_tag",
    "control_gl_family_tree_tag",
    "control_gl_tree_tag",
    "control_queue_tree_tag",
    "reconcile_tree_tag",
    "rf1022_candidate_tree_tag",
    "rf1022_overview_tree_tag",
    "suggestion_tree_tag",
]
