from __future__ import annotations

from typing import Mapping

import pandas as pd

from formatting import format_number_no

from .. import select_batch_suggestions, select_magic_wand_suggestions
from ..rule_learning import evaluate_a07_rule_name_status
from ..suggest.models import EXCLUDED_A07_CODES
from ..suggest.rulebook import load_rulebook
from . import status as a07_control_status
from .basis import (
    account_int as _shared_account_int,
    control_gl_basis_column_for_account as _shared_control_gl_basis_column_for_account,
    normalize_gl_basis_column as _shared_normalize_gl_basis_column,
)
from .matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_account_name_lookup,
    decorate_suggestions_for_display,
    evaluate_current_mapping_suspicion,
    safe_previous_accounts_for_code,
    ui_suggestion_row_from_series,
)
from .rf1022_bridge import (
    RF1022_UNKNOWN_GROUP,
    a07_group_member_codes,
    rf1022_group_a07_codes,
)
from .rf1022_contract import (
    RF1022_ACCOUNT_COLUMNS as _RF1022_ACCOUNT_COLUMNS,
    RF1022_OVERVIEW_COLUMNS as _RF1022_OVERVIEW_COLUMNS,
)
from .rf1022_support import (
    Rf1022TreatmentDetails,
    _safe_float,
    a07_code_rf1022_group,
    format_rf1022_treatment_text,
    is_rf1022_accrual_account,
    resolve_rf1022_treatment_kind,
    rf1022_group_label,
    rf1022_post_for_group,
    rf1022_treatment_details,
    work_family_for_a07_code,
    work_family_for_rf1022_group,
)
from .statement_model import (
    CONTROL_STATEMENT_COLUMNS as _CANONICAL_CONTROL_STATEMENT_COLUMNS,
    CONTROL_STATEMENT_PAYROLL_ORDER as _CONTROL_MVP_GROUP_ORDER,
    CONTROL_STATEMENT_PAYROLL_SET as _CONTROL_MVP_GROUP_SET,
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LABELS,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    control_statement_view_requires_unclassified,
    empty_control_statement_df as _empty_control_statement_df,
    filter_control_statement_df,
    normalize_control_statement_df,
    normalize_control_statement_view,
)
from .statement_source import build_current_control_statement_rows

_CONTROL_HIDDEN_CODES = {
    "aga",
    "forskuddstrekk",
    "finansskattloenn",
    "finansskattlÃ¸nn",
}

_CONTROL_COLUMNS = ("A07Post", "AgaPliktig", "A07_Belop", "GL_Belop", "Diff")
_CONTROL_EXTRA_COLUMNS = (
    "Kode",
    "Navn",
    "Status",
    "AntallKontoer",
    "Anbefalt",
    "DagensMapping",
    "Arbeidsstatus",
    "GuidetStatus",
    "GuidetNeste",
    "MatchingReady",
    "SuggestionGuardrail",
    "SuggestionGuardrailReason",
    "CurrentMappingSuspicious",
    "CurrentMappingSuspiciousReason",
    "Rf1022GroupId",
    "WorkFamily",
    "ReconcileStatus",
    "NesteHandling",
    "Locked",
    "Hvorfor",
)
_CONTROL_GL_DATA_COLUMNS = (
    "Konto",
    "Navn",
    "IB",
    "Endring",
    "UB",
    "BelopAktiv",
    "Kol",
    "Kode",
    "Rf1022GroupId",
    "AliasStatus",
    "WorkFamily",
    "MappingAuditStatus",
    "MappingAuditReason",
    "MappingAuditRawStatus",
    "MappingAuditRawReason",
    "A07CodeDiff",
)
_CONTROL_SELECTED_ACCOUNT_COLUMNS = (
    "Konto",
    "Navn",
    "AliasStatus",
    "MappingAuditStatus",
    "MappingAuditReason",
    "IB",
    "Endring",
    "UB",
)
_HISTORY_COLUMNS = ("Kode", "Navn", "AarKontoer", "HistorikkKontoer", "Status", "KanBrukes", "Merknad")
_MAPPING_AUDIT_COLUMNS = (
    "Konto",
    "Navn",
    "CurrentA07Code",
    "CurrentRf1022GroupId",
    "ExpectedRf1022GroupId",
    "AliasStatus",
    "Kol",
    "Belop",
    "Status",
    "Reason",
    "Evidence",
)
_MAPPING_REVIEW_COLUMNS = (
    "Konto",
    "Navn",
    "Kode",
    "Rf1022GroupId",
    "ExpectedRf1022GroupId",
    "AliasStatus",
    "Kol",
    "Belop",
    "Kontroll",
    "Hvorfor",
    "Evidence",
    "AnbefaltHandling",
)
_MAPPING_AUDIT_STATUS_PRIORITY = {
    "Feil": 0,
    "Mistenkelig": 1,
    "Uavklart": 2,
    "Trygg": 3,
    "": 4,
}
_MAPPING_REVIEW_CRITICAL_STATUSES = {"Feil", "Mistenkelig"}
_CONTROL_STATEMENT_COLUMNS = _CANONICAL_CONTROL_STATEMENT_COLUMNS
def _empty_control_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[*_CONTROL_COLUMNS, *_CONTROL_EXTRA_COLUMNS])


def _empty_suggestions_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Kode",
            "KodeNavn",
            "Basis",
            "A07_Belop",
            "ForslagKontoer",
            "GL_Sum",
            "Diff",
            "Score",
            "ComboSize",
            "WithinTolerance",
            "Explain",
            "HitTokens",
            "HistoryAccounts",
            "UsedRulebook",
            "UsedHistory",
            "UsedUsage",
            "UsedSpecialAdd",
            "UsedResidual",
            "AmountEvidence",
            "AmountDiffAbs",
            "AnchorSignals",
            "ForslagVisning",
            "Forslagsstatus",
            "HvorforKort",
            "SuggestionGuardrail",
            "SuggestionGuardrailReason",
        ]
    )


def _empty_rf1022_overview_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_RF1022_OVERVIEW_COLUMNS))


def _empty_rf1022_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_RF1022_ACCOUNT_COLUMNS))


def _empty_a07_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Kode", "Navn", "Belop", "AgaPliktig", "GL_Belop", "Diff", "AntallKontoer", "Status", "Kontoer"]
    )


def _empty_history_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_HISTORY_COLUMNS))


def _optional_bool(value: object) -> bool | str | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = str(value or "").strip().casefold()
    if text in {"1", "true", "ja", "j", "yes", "y"}:
        return True
    if text in {"0", "false", "nei", "n", "no"}:
        return False
    if text in {"blandet", "mixed"}:
        return "Blandet"
    return None


def _format_aga_pliktig(value: object) -> str:
    parsed = _optional_bool(value)
    if parsed is True:
        return "Ja"
    if parsed is False:
        return "Nei"
    if parsed == "Blandet":
        return "Blandet"
    return ""


def _rulebook_aga_pliktig(rulebook: Mapping[str, object], code: object) -> bool | str | None:
    code_s = str(code or "").strip()
    if not code_s:
        return None
    rule = rulebook.get(code_s) if isinstance(rulebook, Mapping) else None
    return getattr(rule, "aga_pliktig", None)


def _account_int(value: object) -> int | None:
    return _shared_account_int(value)


def _normalize_gl_basis_column(value: object, *, default: str = "Endring") -> str:
    return _shared_normalize_gl_basis_column(value, default=default)


def control_gl_basis_column_for_account(
    account_no: object,
    account_name: object | None = None,
    *,
    requested_basis: object = "Endring",
) -> str:
    """Return the GL column A07 should use for this account row."""
    return _shared_control_gl_basis_column_for_account(
        account_no,
        account_name,
        requested_basis=requested_basis,
    )


def _format_amount(value: object, decimals: int = 2) -> str:
    amount = _safe_float(value)
    if amount is None:
        return "-"
    return format_number_no(float(amount), int(decimals))


def _parse_konto_tokens(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def _gl_accounts(gl_df: pd.DataFrame) -> set[str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return set()
    return {
        str(account).strip()
        for account in gl_df["Konto"].astype(str).tolist()
        if str(account).strip()
    }


def filter_control_statement_mvp_df(control_statement_df: pd.DataFrame | None) -> pd.DataFrame:
    return filter_control_statement_df(control_statement_df, view=CONTROL_STATEMENT_VIEW_PAYROLL)


from .statement_data import (
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    build_rf1022_accounts_df,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
)
from .rf1022_report import (
    RF1022_TOTAL_ROW_ID,
    append_rf1022_total_row,
    build_rf1022_summary_cards,
)
from .queue_data import (
    a07_suggestion_is_strict_auto,
    build_a07_overview_df,
    build_control_accounts_summary,
    build_control_gl_df,
    build_control_queue_df,
    build_control_selected_account_df,
    build_history_comparison_df,
    build_mapping_history_details,
    filter_a07_overview_df,
    filter_control_gl_df,
    filter_control_queue_by_rf1022_group,
    filter_control_search_df,
    filter_control_visible_codes_df,
    filter_suggestions_df,
    filter_suggestions_for_rf1022_group,
    preferred_rf1022_overview_group,
    select_batch_suggestion_rows,
    select_magic_wand_suggestion_rows,
    unresolved_codes,
)
from .global_auto import build_global_auto_mapping_plan
from .mapping_audit import (
    apply_mapping_audit_to_control_gl_df,
    apply_mapping_audit_to_mapping_df,
    build_mapping_audit_df,
    build_mapping_review_df,
    build_mapping_review_summary,
    build_mapping_review_summary_text,
    filter_mapping_rows_by_audit_status,
    next_mapping_review_problem_account,
    sort_mapping_rows_by_audit_status,
)
from .rf1022_candidates import (
    build_rf1022_candidate_df,
    build_rf1022_candidate_df_for_groups,
)
from .tree_tags import (
    control_family_tree_tag,
    control_gl_family_tree_tag,
    control_gl_tree_tag,
    control_queue_tree_tag,
    reconcile_tree_tag,
    rf1022_candidate_tree_tag,
    rf1022_overview_tree_tag,
    suggestion_tree_tag,
)
