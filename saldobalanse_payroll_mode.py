"""saldobalanse_payroll_mode.py — Lønns-modus og forslag for Saldobalanse-fanen.

Fokusfiltrering, klassifiseringsresultater og nestehandling-logikk — funksjoner
tar `page` som første argument og leser/skriver via `page._var_*` og
`page._payroll_*` attributter. Klassen [page_saldobalanse.py](page_saldobalanse.py)
beholder tynne delegater for command=-bindings og tester.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

import classification_workspace
import payroll_classification

from saldobalanse_payload import (
    COLUMN_PRESETS,
    FILTER_ALL,
    PAYROLL_COLUMNS,
    PAYROLL_QUEUE_OPTIONS,
    PAYROLL_SCOPE_OPTIONS,
    WORK_MODE_PAYROLL,
    WORK_MODE_STANDARD,
    _load_payroll_context,
    _ordered_columns_for_visible,
    _resolve_payroll_usage_features,
    _suggested_update_for_item,
)


def is_payroll_mode(page) -> bool:
    if page._var_work_mode is None:
        return False
    return str(page._var_work_mode.get() or "").strip() == WORK_MODE_PAYROLL

def focus_payroll_accounts(
    page,
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

    if getattr(page, "_var_work_mode", None) is not None:
        try:
            page._var_work_mode.set(WORK_MODE_PAYROLL)
        except Exception:
            pass
    if page._var_preset is not None:
        try:
            page._var_preset.set("Lønnsklassifisering")
        except Exception:
            pass
    if page._var_payroll_scope is not None:
        try:
            page._var_payroll_scope.set(str(payroll_scope or FILTER_ALL))
        except Exception:
            pass
    if page._var_mapping_status is not None:
        try:
            page._var_mapping_status.set(FILTER_ALL)
        except Exception:
            pass
    if page._var_source is not None:
        try:
            page._var_source.set(FILTER_ALL)
        except Exception:
            pass
    if page._var_only_unmapped is not None:
        try:
            page._var_only_unmapped.set(False)
        except Exception:
            pass
    if page._var_only_with_ao is not None:
        try:
            page._var_only_with_ao.set(False)
        except Exception:
            pass
    if page._var_search is not None:
        try:
            page._var_search.set(normalized[0] if len(normalized) == 1 else "")
        except Exception:
            pass

    on_mode_changed = getattr(page, "_on_work_mode_changed", None)
    if callable(on_mode_changed):
        on_mode_changed(refresh=False)
    page.refresh()

    if page._tree is None or not normalized:
        return

    try:
        children = {str(item).strip() for item in page._tree.get_children()}
    except Exception:
        children = set()
    visible_accounts = [account for account in normalized if account in children]
    if not visible_accounts:
        return

    try:
        page._tree.selection_set(tuple(visible_accounts))
        page._tree.focus(visible_accounts[0])
        page._tree.see(visible_accounts[0])
        update_buttons = getattr(page, "_update_map_button_state", None)
        if callable(update_buttons):
            update_buttons()
        refresh_detail = getattr(page, "_refresh_detail_panel", None)
        if callable(refresh_detail):
            refresh_detail()
        else:
            page._set_status_detail("")
    except Exception:
        pass

def leave_payroll_mode(page) -> None:
    if page._var_work_mode is None:
        return
    try:
        page._var_work_mode.set(WORK_MODE_STANDARD)
    except Exception:
        return
    page._on_work_mode_changed()

def save_non_payroll_filters(page) -> None:
    if page._saved_non_payroll_filters is not None:
        return
    page._saved_non_payroll_filters = {
        "mapping_status": page._var_value(page._var_mapping_status, FILTER_ALL),
        "source": page._var_value(page._var_source, FILTER_ALL),
        "only_unmapped": bool(page._var_value(page._var_only_unmapped, False)),
        "include_zero": bool(page._var_value(page._var_include_zero, False)),
        "only_with_ao": bool(page._var_value(page._var_only_with_ao, False)),
        "include_ao": bool(page._var_value(page._var_include_ao_fallback, False)),
    }

def reset_hidden_filters_for_payroll_mode(page) -> None:
    page._set_var_value(page._var_mapping_status, FILTER_ALL)
    page._set_var_value(page._var_source, FILTER_ALL)
    page._set_var_value(page._var_only_unmapped, False)
    page._set_var_value(page._var_include_zero, False)
    page._set_var_value(page._var_only_with_ao, False)
    page._set_var_value(page._var_include_ao_fallback, False)

def restore_non_payroll_filters(page) -> None:
    saved = page._saved_non_payroll_filters or {}
    page._set_var_value(page._var_mapping_status, saved.get("mapping_status", FILTER_ALL))
    page._set_var_value(page._var_source, saved.get("source", FILTER_ALL))
    page._set_var_value(page._var_only_unmapped, bool(saved.get("only_unmapped", False)))
    page._set_var_value(page._var_include_zero, bool(saved.get("include_zero", False)))
    page._set_var_value(page._var_only_with_ao, bool(saved.get("only_with_ao", False)))
    page._set_var_value(page._var_include_ao_fallback, bool(saved.get("include_ao", False)))
    page._saved_non_payroll_filters = None

def on_work_mode_changed(page, *, refresh: bool = True) -> None:
    entering_payroll = page._is_payroll_mode()
    if entering_payroll:
        if page._saved_non_payroll_visible_cols is None:
            page._saved_non_payroll_visible_cols = list(page._visible_cols)
            page._saved_non_payroll_order = list(page._column_order)
        page._save_non_payroll_filters()
        page._reset_hidden_filters_for_payroll_mode()
        page._visible_cols = list(COLUMN_PRESETS["Lønnsklassifisering"])
        page._column_order = _ordered_columns_for_visible(page._visible_cols)
    elif page._saved_non_payroll_visible_cols is not None:
        page._visible_cols = list(page._saved_non_payroll_visible_cols)
        page._column_order = list(page._saved_non_payroll_order or _ordered_columns_for_visible(page._visible_cols))
        page._saved_non_payroll_visible_cols = None
        page._saved_non_payroll_order = None
        page._restore_non_payroll_filters()
    page._apply_visible_columns()
    page._sync_preset_var()
    page._sync_mode_ui()
    if refresh:
        page.refresh()

def sync_mode_ui(page) -> None:
    payroll_mode = page._is_payroll_mode()
    for widget in (
        getattr(page, "_lbl_mode", None),
        getattr(page, "_cmb_mode", None),
    ):
        page._show_grid_widget(widget, show=not payroll_mode)
    page._show_grid_widget(getattr(page, "_btn_leave_payroll", None), show=payroll_mode)
    for widget in (
        getattr(page, "_lbl_preset", None),
        getattr(page, "_cmb_preset", None),
        getattr(page, "_lbl_mapping_status", None),
        getattr(page, "_cmb_mapping_status", None),
        getattr(page, "_lbl_source", None),
        getattr(page, "_cmb_source", None),
        getattr(page, "_btn_columns", None),
        getattr(page, "_chk_include_ao", None),
        getattr(page, "_chk_only_unmapped", None),
        getattr(page, "_chk_include_zero", None),
        getattr(page, "_chk_only_with_ao", None),
        getattr(page, "_btn_use_suggestion", None),
        getattr(page, "_btn_use_history", None),
        getattr(page, "_btn_reset_suspicious", None),
        getattr(page, "_btn_map", None),
    ):
        page._show_grid_widget(widget, show=not payroll_mode)
    page._show_grid_widget(getattr(page, "_btn_primary_action", None), show=payroll_mode)
    page._show_pane_widget(page._details_frame, show=payroll_mode, weight=3)
    label = getattr(page, "_lbl_payroll_scope", None)
    if label is not None:
        try:
            label.configure(text="Kø:" if payroll_mode else "Lønn:")
        except Exception:
            pass
    classify_button = getattr(page, "_btn_classify", None)
    if classify_button is not None:
        try:
            classify_button.configure(text="Åpne klassifisering..." if payroll_mode else "Avansert klassifisering...")
        except Exception:
            pass
    details_frame = getattr(page, "_details_frame", None)
    if details_frame is not None:
        try:
            details_frame.configure(text="Detaljer")
        except Exception:
            pass
    sync_selection_actions = getattr(page, "_sync_selection_actions_visibility", None)
    if callable(sync_selection_actions):
        sync_selection_actions()

def ensure_payroll_context_loaded(page) -> tuple[Any, Any, Any]:
    client, year = page._client_context()
    if page._payroll_context_key != (client, year):
        page._profile_document = None
        page._history_document = None
        page._profile_catalog = None
        page._payroll_context_key = (client, year)
    if page._profile_document is None and client:
        page._profile_document, page._history_document, page._profile_catalog = _load_payroll_context(client, year)
    return page._profile_document, page._history_document, page._profile_catalog

def ensure_payroll_usage_features_loaded(page) -> dict[str, Any]:
    analyse_page = page._analyse_page
    dataset = getattr(analyse_page, "dataset", None) if analyse_page is not None else None
    if isinstance(dataset, pd.DataFrame):
        cache_key = (id(dataset), len(dataset.index))
    else:
        cache_key = (-1, 0)
    if page._payroll_usage_cache_key != cache_key:
        page._payroll_usage_features_cache = _resolve_payroll_usage_features(analyse_page)
        page._payroll_usage_cache_key = cache_key
    return page._payroll_usage_features_cache or {}

def payroll_result_for_account(page, account_no: str) -> payroll_classification.PayrollSuggestionResult | None:
    account_s = str(account_no or "").strip()
    if not account_s:
        return None
    result = page._payroll_suggestions.get(account_s)
    if result is not None:
        return result
    row = page._row_for_account(account_s)
    if row is None:
        return None
    document, history_document, catalog = page._ensure_payroll_context_loaded()
    if document is None:
        return None
    result = payroll_classification.classify_payroll_account(
        account_no=account_s,
        account_name=str(row.get("Kontonavn") or "").strip(),
        movement=float(pd.to_numeric([row.get("Endring")], errors="coerce")[0] or 0.0),
        current_profile=document.get(account_s),
        history_profile=history_document.get(account_s) if history_document is not None else None,
        catalog=catalog,
        usage=page._ensure_payroll_usage_features_loaded().get(account_s),
    )
    page._payroll_suggestions[account_s] = result
    return result

def history_profile_for_account(page, account_no: str) -> Any:
    if page._history_document is None:
        page._ensure_payroll_context_loaded()
    if page._history_document is None:
        return None
    try:
        return page._history_document.get(str(account_no or "").strip())
    except Exception:
        return None

def suspicious_profile_issue_for_account(
    page,
    account_no: str,
    *,
    account_name: str = "",
    profile: Any = None,
) -> str:
    profile_obj = profile if profile is not None else page._profile_for_account(account_no)
    account_name_s = str(account_name or "").strip()
    if not account_name_s:
        row = page._row_for_account(account_no)
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

def has_history_for_selected_accounts(page) -> bool:
    accounts = page._selected_accounts()
    if not accounts:
        return False
    for account in accounts:
        if page._suspicious_profile_issue_for_account(account):
            continue
        profile = page._history_profile_for_account(account)
        if profile is None:
            continue
        if (
            str(getattr(profile, "a07_code", "") or "").strip()
            or str(getattr(profile, "control_group", "") or "").strip()
            or tuple(getattr(profile, "control_tags", ()) or ())
        ):
            return True
    return False

def has_strict_suggestions_for_selected_accounts(page) -> bool:
    accounts = page._selected_accounts()
    if not accounts:
        return False
    for account in accounts:
        item = page._workspace_item_for_account(account)
        if _suggested_update_for_item(item):
            return True
    return False

def next_action_for_account(
    page,
    account_no: str,
    *,
    account_name: str = "",
    result: payroll_classification.PayrollSuggestionResult | None,
    profile: Any,
) -> str:
    suspicious_issue = page._suspicious_profile_issue_for_account(
        account_no,
        account_name=account_name,
        profile=profile,
    )
    if suspicious_issue:
        return "Nullstill lagret lønnsklassifisering."
    if bool(getattr(profile, "locked", False)):
        return "Lås opp hvis du vil endre klassifiseringen."
    workspace_item_for_account = getattr(page, "_workspace_item_for_account", None)
    item = None
    if callable(workspace_item_for_account):
        try:
            item = workspace_item_for_account(account_no)
        except Exception:
            item = None
    if _suggested_update_for_item(item):
        return "Godkjenn forslag."
    history_profile = page._history_profile_for_account(account_no)
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
