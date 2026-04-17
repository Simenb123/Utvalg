from __future__ import annotations

import copy
import faulthandler
import json
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
import shutil
from tkinter import filedialog, messagebox, simpledialog
from typing import Callable

import pandas as pd

import app_paths
import classification_config
import classification_workspace
import payroll_classification
import session
from account_profile_legacy_api import AccountProfileLegacyApi
try:
    import konto_klassifisering as konto_klassifisering
except Exception:
    konto_klassifisering = None
from a07_feature import (
    A07Group,
    AccountUsageFeatures,
    A07WorkspaceData,
    SuggestConfig,
    apply_groups_to_mapping,
    apply_suggestion_to_mapping,
    build_account_usage_features,
    build_grouped_a07_df,
    derive_groups_path,
    export_a07_workbook,
    from_trial_balance,
    load_a07_groups,
    load_locks,
    load_mapping,
    load_project_state,
    mapping_to_assigned_df,
    parse_a07_json,
    reconcile_a07_vs_gl,
    save_a07_groups,
    save_locks,
    save_mapping,
    save_project_state,
    select_batch_suggestions,
    select_magic_wand_suggestions,
    suggest_mapping_candidates,
    unmapped_accounts_df,
)
from a07_feature import control_status as a07_control_status
from a07_feature import mapping_source
from a07_feature.control_matching import (
    accounts_for_code,
    best_suggestion_row_for_code,
    build_suggestion_reason_label,
    build_suggestion_status_label,
    decorate_suggestions_for_display,
    build_control_suggestion_effect_summary,
    build_control_suggestion_summary,
    build_smartmapping_fallback,
    compact_accounts,
    preferred_support_tab_key,
    safe_previous_accounts_for_code,
    select_safe_history_codes,
    ui_suggestion_row_from_series,
)
from a07_feature.page_control_data import (
    CONTROL_STATEMENT_VIEW_ALL,
    CONTROL_STATEMENT_VIEW_LABELS,
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    a07_suggestion_is_strict_auto,
    build_a07_overview_df,
    build_control_accounts_summary,
    build_control_gl_df,
    build_control_queue_df,
    build_control_selected_account_df,
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    build_history_comparison_df,
    build_mapping_history_details,
    build_rf1022_accounts_df,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
    control_gl_tree_tag,
    control_queue_tree_tag,
    filter_a07_overview_df,
    filter_control_gl_df,
    filter_control_search_df,
    filter_control_statement_df,
    filter_control_visible_codes_df,
    filter_suggestions_df,
    reconcile_tree_tag,
    rf1022_post_for_group,
    select_batch_suggestion_rows,
    select_magic_wand_suggestion_rows,
    suggestion_tree_tag,
    unresolved_codes,
    control_statement_view_requires_unclassified,
    normalize_control_statement_view,
)
from a07_feature.page_paths import (
    MATCHER_SETTINGS_DEFAULTS as _MATCHER_SETTINGS_DEFAULTS,
    bundled_default_rulebook_path as _bundled_default_rulebook_path,
    build_default_group_name,
    build_groups_df,
    build_rule_form_values,
    build_rule_payload,
    build_suggest_config,
    copy_a07_source_to_workspace,
    copy_rulebook_to_storage,
    default_a07_export_path,
    default_a07_groups_path,
    default_a07_locks_path,
    default_a07_project_path,
    default_a07_source_path,
    default_global_rulebook_path,
    ensure_default_rulebook_exists,
    find_previous_year_context as _find_previous_year_context,
    find_previous_year_mapping_path as _find_previous_year_mapping_path,
    get_a07_workspace_dir,
    get_active_trial_balance_path_for_context,
    get_context_snapshot,
    get_context_snapshot_with_paths,
    legacy_global_a07_mapping_path,
    legacy_global_a07_source_path,
    load_active_trial_balance_for_context,
    load_matcher_settings,
    load_previous_year_mapping_for_context,
    load_rulebook_document,
    normalize_matcher_settings,
    resolve_context_mapping_path,
    resolve_context_source_path,
    resolve_autosave_mapping_path,
    resolve_rulebook_path,
    save_matcher_settings,
    save_rulebook_document,
    suggest_default_mapping_path,
)
from a07_feature.page_windows import (
    build_source_overview_rows,
    open_mapping_overview,
    open_matcher_admin,
    open_source_overview,
)
from a07_feature.suggest.models import EXCLUDED_A07_CODES
from formatting import format_number_no
from trial_balance_reader import read_trial_balance
from .page_a07_dialogs import (
    _PickerOption,
    _count_nonempty_mapping,
    _editor_list_items,
    _filter_picker_options,
    _format_aliases_editor,
    _format_editor_list,
    _format_editor_ranges,
    _format_picker_amount,
    _format_special_add_editor,
    _numeric_decimals_for_column,
    _parse_aliases_editor,
    _parse_editor_ints,
    _parse_konto_tokens,
    _parse_special_add_editor,
    apply_manual_mapping_choice,
    apply_manual_mapping_choices,
    build_a07_picker_options,
    build_gl_picker_options,
    open_manual_mapping_dialog,
    remove_mapping_accounts,
)

try:
    import client_store
except Exception:
    client_store = None



_A07_DIAGNOSTICS_ENABLED = True
_A07_DIAGNOSTICS_LOG = Path(tempfile.gettempdir()) / "utvalg_a07_debug.log"


_A07_COLUMNS = (
    ("Kode", "Kode", 180, "w"),
    ("Navn", "Navn", 280, "w"),
    ("Belop", "Belop", 120, "e"),
    ("Status", "Status", 120, "w"),
    ("Kontoer", "Kontoer", 200, "w"),
)

_CONTROL_COLUMNS = (
    ("Kode", "Kode", 220, "w"),
    ("Navn", "Navn", 220, "w"),
    ("A07_Belop", "A07", 120, "e"),
    ("GL_Belop", "GL", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("AntallKontoer", "Antall", 90, "e"),
    ("Status", "Status", 90, "w"),
    ("Anbefalt", "Neste", 110, "w"),
)

_CONTROL_GL_COLUMNS = (
    ("Konto", "Konto", 80, "w"),
    ("Navn", "Navn", 260, "w"),
    ("IB", "IB", 100, "e"),
    ("Endring", "Endring", 110, "e"),
    ("UB", "UB", 100, "e"),
    ("Kode", "Kode", 160, "w"),
)

_CONTROL_GL_DATA_COLUMNS = ("Konto", "Navn", "IB", "Endring", "UB", "Kode")

_CONTROL_SELECTED_ACCOUNT_COLUMNS = (
    ("Konto", "Konto", 90, "w"),
    ("Navn", "Navn", 250, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
)

_CONTROL_SUGGESTION_COLUMNS = (
    ("ForslagVisning", "Forslag", 420, "w"),
    ("Forslagsstatus", "Status", 120, "w"),
    ("HvorforKort", "Hvorfor", 240, "w"),
    ("Diff", "Diff", 110, "e"),
)

_CONTROL_GL_SCOPE_LABELS = {
    "relevante": "Relevante for valgt kode",
    "koblede": "Koblet naa",
    "forslag": "Forslag",
    "alle": "Alle kontoer",
}

_CONTROL_ALTERNATIVE_MODE_LABELS = {
    "suggestions": "Beste forslag",
    "history": "Historikk",
}
_CONTROL_HIDDEN_CODES = {
    "aga",
    "forskuddstrekk",
    "finansskattloenn",
    "finansskattlÃ¸nn",
}

_CONTROL_EXTRA_COLUMNS = (
    "DagensMapping",
    "Arbeidsstatus",
    "ReconcileStatus",
    "NesteHandling",
    "Locked",
)

_GROUP_COLUMNS = (
    ("GroupId", "Gruppe", 180, "w"),
    ("Navn", "Navn", 220, "w"),
    ("Members", "Medlemmer", 280, "w"),
    ("Locked", "LÃ¥st", 70, "center"),
)

_SUGGESTION_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("KodeNavn", "KodeNavn", 220, "w"),
    ("Basis", "Basis", 80, "w"),
    ("A07_Belop", "A07_Belop", 120, "e"),
    ("ForslagVisning", "Forslag", 320, "w"),
    ("Forslagsstatus", "Status", 110, "w"),
    ("HvorforKort", "Hvorfor", 220, "w"),
    ("Diff", "Diff", 120, "e"),
    ("GL_Sum", "GL_Sum", 120, "e"),
)

_RECONCILE_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("A07_Belop", "A07_Belop", 120, "e"),
    ("GL_Belop", "GL_Belop", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("AntallKontoer", "AntallKontoer", 110, "e"),
    ("Kontoer", "Kontoer", 200, "w"),
    ("WithinTolerance", "OK", 70, "center"),
)

_MAPPING_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Navn", 260, "w"),
    ("Kode", "Kode", 180, "w"),
)

_UNMAPPED_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Navn", 260, "w"),
    ("GL_Belop", "GL_Belop", 120, "e"),
)

_HISTORY_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("AarKontoer", "I aar", 180, "w"),
    ("HistorikkKontoer", "Historikk", 180, "w"),
    ("Status", "Status", 160, "w"),
    ("KanBrukes", "Kan brukes", 90, "center"),
    ("Merknad", "Merknad", 320, "w"),
)

_CONTROL_STATEMENT_COLUMNS = (
    ("Gruppe", "Gruppe", 180, "w"),
    ("Navn", "Navn", 220, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
    ("A07", "A07", 110, "e"),
    ("Diff", "Diff", 110, "e"),
    ("Status", "Status", 140, "w"),
    ("AntallKontoer", "Antall", 90, "e"),
)

_RF1022_OVERVIEW_COLUMNS = (
    ("Post", "Post", 70, "w"),
    ("Omraade", "Omrade", 190, "w"),
    ("Kontrollgruppe", "Kontrollgruppe", 220, "w"),
    ("GL_Belop", "GL", 120, "e"),
    ("A07", "A07", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("Status", "Status", 100, "w"),
    ("AntallKontoer", "Antall", 80, "e"),
)

_RF1022_ACCOUNT_COLUMNS = (
    ("Post", "Post", 150, "w"),
    ("Konto", "Kontonr", 90, "w"),
    ("Navn", "Kontobetegnelse", 240, "w"),
    ("KostnadsfortYtelse", "Kostnadsfort", 120, "e"),
    ("TilleggTidligereAar", "Tillegg tidl. ar", 120, "e"),
    ("FradragPaalopt", "Fradrag palopt", 120, "e"),
    ("SamledeYtelser", "Samlede ytelser", 120, "e"),
    ("AgaPliktig", "AGA-pliktig", 95, "center"),
    ("AgaGrunnlag", "AGA-grunnlag", 120, "e"),
    ("Feriepengegrunnlag", "Feriep.grl.", 95, "center"),
)

_RF1022_POST_RULES = (
    (
        100,
        "LÃ¸nn o.l.",
        {
            "100_loenn_ol",
        },
    ),
    (
        100,
        "Refusjon",
        {
            "100_refusjon",
        },
    ),
    (
        111,
        "Naturalytelser",
        {
            "111_naturalytelser",
        },
    ),
    (
        112,
        "Pensjon",
        {
            "112_pensjon",
        },
    ),
    (
        100,
        "Lonn og trekk",
        {
            "Lonnskostnad",
            "Skyldig lonn",
            "Feriepenger",
            "Skyldig feriepenger",
            "Skattetrekk",
        },
    ),
    (
        110,
        "Arbeidsgiveravgift",
        {
            "Kostnadsfort arbeidsgiveravgift",
            "Kostnadsfort arbeidsgiveravgift av feriepenger",
            "Skyldig arbeidsgiveravgift",
            "Skyldig arbeidsgiveravgift av feriepenger",
        },
    ),
    (
        120,
        "Pensjon og refusjon",
        {
            "Pensjonskostnad",
            "Skyldig pensjon",
            "Refusjon",
        },
    ),
    (
        130,
        "Naturalytelser og styrehonorar",
        {
            "Naturalytelse",
            "Styrehonorar",
        },
    ),
)

_A07_FILTER_LABELS = {
    "alle": "Alle",
    "uloste": "Uloste",
    "avvik": "Avvik",
    "ikke_mappet": "Ikke mappet",
    "ok": "OK",
    "ekskludert": "Ekskludert",
}

_CONTROL_VIEW_LABELS = {
    "neste": "Neste oppgaver",
    "ulost": "UlÃ¸st",
    "forslag": "Forslag",
    "historikk": "Historikk",
    "manuell": "Manuell",
    "ferdig": "Ferdig",
    "alle": "Alle",
}

_SUGGESTION_SCOPE_LABELS = {
    "valgt_kode": "Valgt kode",
    "uloste": "Uloste koder",
    "alle": "Alle forslag",
}

_BASIS_LABELS = {
    "Endring": "Endring",
    "UB": "UB",
    "IB": "IB",
}

_CONTROL_DRAG_IDLE_HINT = "Velg kode og konto, eller dra konto inn."
_CONTROL_STATEMENT_VIEW_LABELS = dict(CONTROL_STATEMENT_VIEW_LABELS)

_NUMERIC_COLUMNS_ZERO_DECIMALS = {"AntallKontoer"}
_NUMERIC_COLUMNS_THREE_DECIMALS = {"Score"}
_NUMERIC_COLUMNS_TWO_DECIMALS = {
    "Belop",
    "Diff",
    "A07",
    "A07_Belop",
    "GL_Belop",
    "GL_Sum",
    "IB",
    "UB",
    "Endring",
    "GL_Belop",
}

_MATCHER_SETTINGS_DEFAULTS = {
    "tolerance_rel": 0.02,
    "tolerance_abs": 100.0,
    "max_combo": 2,
    "candidates_per_code": 20,
    "top_suggestions_per_code": 5,
    "historical_account_boost": 0.12,
    "historical_combo_boost": 0.10,
}


def _empty_a07_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Kode", "Navn", "Belop", "Status", "Kontoer", "Diff"])


def _empty_control_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _CONTROL_COLUMNS] + list(_CONTROL_EXTRA_COLUMNS))


def _empty_gl_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Konto", "Navn", "IB", "UB", "Endring", "Belop"])


def _empty_suggestions_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _SUGGESTION_COLUMNS])


def _empty_reconcile_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _RECONCILE_COLUMNS])


def _empty_mapping_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _MAPPING_COLUMNS])


def _empty_unmapped_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _UNMAPPED_COLUMNS])


def _empty_history_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _HISTORY_COLUMNS])


def _empty_groups_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _GROUP_COLUMNS])


def _empty_control_statement_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["Gruppe", "Navn", "IB", "Endring", "UB", "A07", "Diff", "Status", "AntallKontoer", "Kontoer", "Kilder"]
    )


def _empty_rf1022_overview_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["GroupId", "Post", "Omraade", "Kontrollgruppe", "GL_Belop", "A07", "Diff", "Status", "AntallKontoer"]
    )


def _empty_rf1022_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Konto", "Navn", "GL_Belop", "A07Kode"])


def _account_profile_api_for_a07() -> AccountProfileLegacyApi:
    return AccountProfileLegacyApi(
        base_dir=Path(app_paths.data_dir()) / "konto_klassifisering_profiles",
        catalog_path=classification_config.resolve_catalog_path(),
    )


def _load_code_profile_state(
    client: str | None,
    year: str | int | None,
    mapping_current: dict[str, str] | None,
    gl_df: pd.DataFrame | None = None,
) -> dict[str, dict[str, object]]:
    client_s = _clean_context_value(client)
    if not client_s:
        return {}

    year_i: int | None = None
    year_s = _clean_context_value(year)
    if year_s:
        try:
            year_i = int(year_s)
        except Exception:
            year_i = None

    try:
        document = mapping_source.load_current_document(client_s, year=year_i)
    except Exception:
        document = None
    try:
        if year_i is None:
            history_document = None
        else:
            history_document, _ = mapping_source.load_nearest_prior_document(
                client_s, year_i
            )
    except Exception:
        history_document = None
    try:
        catalog = konto_klassifisering.load_catalog() if konto_klassifisering is not None else None
    except Exception:
        catalog = None
    if document is None:
        return {}

    rows: list[dict[str, object]] = []
    gl_by_account: dict[str, dict[str, object]] = {}
    if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and "Konto" in gl_df.columns:
        gl_source = gl_df.copy()
        gl_source["Konto"] = gl_source["Konto"].astype(str).str.strip()
        for _, row in gl_source.iterrows():
            account_s = str(row.get("Konto") or "").strip()
            if not account_s or account_s in gl_by_account:
                continue
            gl_by_account[account_s] = {
                "Kontonavn": str(row.get("Navn") or row.get("Kontonavn") or "").strip(),
                "IB": row.get("IB"),
                "Endring": row.get("Endring"),
                "UB": row.get("UB"),
            }
    for account, mapped_code in (mapping_current or {}).items():
        account_s = str(account or "").strip()
        code_s = str(mapped_code or "").strip()
        if not account_s or not code_s:
            continue
        row = {"Konto": account_s, **gl_by_account.get(account_s, {})}
        rows.append(row)

    items_by_account = classification_workspace.build_workspace_items(
        rows,
        document=document,
        history_document=history_document,
        catalog=catalog,
    )
    state_by_code = classification_workspace.build_code_workspace_state(
        mapping_current or {},
        items_by_account,
    )
    normalized: dict[str, dict[str, object]] = {}
    for code, raw in state_by_code.items():
        sources = {str(value).strip() for value in raw.get("sources", set()) if str(value).strip()}
        if sources == {"history"}:
            source = "history"
        elif "manual" in sources:
            source = "manual"
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
            "why_summary": str(raw.get("why_summary") or "").strip(),
        }
    return normalized


def _path_name(value: str | Path | None, *, empty: str = "ikke valgt") -> str:
    if not value:
        return empty
    try:
        return Path(str(value)).name or str(value)
    except Exception:
        return str(value)


def _clean_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _build_usage_features_for_a07(df: object) -> dict[str, AccountUsageFeatures]:
    if isinstance(df, pd.DataFrame) and not df.empty:
        try:
            return build_account_usage_features(df)
        except Exception:
            return {}
    return {}


def _safe_exists(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists()
    except Exception:
        return False


def _rulebook_has_rules(path: Path | None) -> bool:
    if not _safe_exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    rules = data.get("rules", {})
    return isinstance(rules, dict) and bool(rules)


def default_global_rulebook_path() -> Path:
    try:
        return app_paths.data_dir() / "a07" / "global_full_a07_rulebook.json"
    except Exception:
        return Path("a07") / "global_full_a07_rulebook.json"


def copy_rulebook_to_storage(source_path: str | Path) -> Path:
    source = Path(source_path)
    target = default_global_rulebook_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        same = source.resolve() == target.resolve()
    except Exception:
        same = False

    if not same:
        shutil.copy2(source, target)

    return target


def bundled_default_rulebook_path() -> Path | None:
    return _bundled_default_rulebook_path()


def ensure_default_rulebook_exists() -> Path | None:
    target = default_global_rulebook_path()
    if _rulebook_has_rules(target):
        return target

    source_candidates = (
        classification_config.repo_rulebook_path(),
        bundled_default_rulebook_path(),
    )
    source = None
    for candidate in source_candidates:
        candidate_path = Path(candidate) if candidate is not None else None
        try:
            same_target = candidate_path is not None and candidate_path.resolve() == target.resolve()
        except Exception:
            same_target = False
        if same_target:
            continue
        if _rulebook_has_rules(candidate_path):
            source = candidate_path
            break
    if source is None:
        return target if _safe_exists(target) else None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target
    except Exception:
        try:
            return source if source.exists() else None
        except Exception:
            return None


def resolve_rulebook_path(client: str | None, year: str | int | None) -> Path | None:
    _ = (client, year)
    return ensure_default_rulebook_exists()


def find_previous_year_mapping_path(
    client: str | None,
    year: str | int | None,
) -> tuple[Path | None, str | None]:
    return _find_previous_year_mapping_path(client, year)


def find_previous_year_context(
    client: str | None,
    year: str | int | None,
) -> str | None:
    return _find_previous_year_context(client, year)


def count_unsolved_a07_codes(a07_overview_df: pd.DataFrame) -> int:
    if a07_overview_df is None or a07_overview_df.empty:
        return 0
    excluded = {str(code).strip() for code in EXCLUDED_A07_CODES}
    count = 0
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode", "") or "").strip()
        status = str(row.get("Status", "") or "").strip().lower()
        if not code or code in excluded:
            continue
        if status in {"ok", "ferdig", "ekskludert"}:
            continue
        count += 1
    return count



build_control_statement_summary = lambda row, accounts_df, *, basis_col="Endring": a07_control_status.build_control_statement_summary(  # noqa: E731
    row,
    accounts_df,
    basis_col=basis_col,
    amount_formatter=_format_picker_amount,
)
build_control_statement_overview = lambda control_statement_df, *, basis_col="Endring", selected_row=None: a07_control_status.build_control_statement_overview(  # noqa: E731
    control_statement_df,
    basis_col=basis_col,
    selected_row=selected_row,
    amount_formatter=_format_picker_amount,
)
control_recommendation_label = lambda *, has_history, best_suggestion: a07_control_status.control_recommendation_label(  # noqa: E731
    has_history=has_history,
    best_suggestion=best_suggestion,
)
control_next_action_label = lambda status, *, has_history, best_suggestion: a07_control_status.control_next_action_label(  # noqa: E731
    status,
    has_history=has_history,
    best_suggestion=best_suggestion,
)
is_saldobalanse_follow_up_action = lambda next_action: a07_control_status.is_saldobalanse_follow_up_action(next_action)  # noqa: E731
control_follow_up_guidance = lambda next_action: a07_control_status.control_follow_up_guidance(next_action)  # noqa: E731
compact_control_next_action = lambda next_action: a07_control_status.compact_control_next_action(next_action)  # noqa: E731
control_intro_text = lambda work_label, *, has_history, best_suggestion: a07_control_status.control_intro_text(  # noqa: E731
    work_label,
    has_history=has_history,
    best_suggestion=best_suggestion,
)
filter_control_queue_df = lambda control_df, view_key: (  # noqa: E731
    _empty_control_df()
    if control_df is None
    else a07_control_status.filter_control_queue_df(control_df, view_key)
)
build_control_bucket_summary = a07_control_status.build_control_bucket_summary
count_pending_control_items = a07_control_status.count_pending_control_items
control_tree_tag = a07_control_status.control_tree_tag
control_action_style = a07_control_status.control_action_style

__all__ = [name for name in globals() if not name.startswith("__")]
