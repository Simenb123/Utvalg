from __future__ import annotations

import traceback

import pandas as pd

from .page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _BASIS_LABELS,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_SUGGESTION_COLUMNS,
    _GROUP_COLUMNS,
    _MAPPING_COLUMNS,
)
from .page_a07_dialogs import _format_picker_amount
from .page_a07_env import session
from .page_a07_frames import (
    _empty_control_statement_df,
    _empty_history_df,
    _empty_mapping_df,
    _empty_reconcile_df,
    _empty_rf1022_overview_df,
    _empty_suggestions_df,
    _empty_unmapped_df,
)
from .control import status as a07_control_status
from .control.data import filter_control_statement_df, preferred_rf1022_overview_group


def _coerce_refresh_warnings(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        scope = str(entry.get("scope") or "").strip()
        message = str(entry.get("message") or "").strip()
        detail = str(entry.get("detail") or "").strip()
        if not scope and not message and not detail:
            continue
        out.append({"scope": scope, "message": message, "detail": detail})
    return out


def _format_refresh_warning_details(warnings: list[dict[str, str]]) -> str:
    if not warnings:
        return ""
    parts: list[str] = []
    for warning in warnings[:3]:
        scope = warning.get("scope", "")
        message = warning.get("message", "")
        label = f"{scope}: {message}" if scope and message else (message or scope)
        detail = warning.get("detail", "")
        if detail:
            label = f"{label} ({detail})" if label else detail
        if label:
            parts.append(label)
    remaining = len(warnings) - len(parts)
    if remaining > 0:
        parts.append(f"{remaining} flere")
    return "Advarsler: " + "; ".join(parts)


def _empty_selected_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[column_id for column_id, *_rest in _CONTROL_SELECTED_ACCOUNT_COLUMNS])


def _rebuild_refresh_indexes(page: object) -> None:
    rebuild = getattr(page, "_rebuild_a07_refresh_indexes", None)
    if callable(rebuild):
        rebuild()
        return
    from .page_a07_background import A07PageBackgroundMixin

    A07PageBackgroundMixin._rebuild_a07_refresh_indexes(page)


def _auto_refresh_signature(page: object, auto_payload: dict[str, object]) -> tuple[tuple[str, str], ...]:
    helper = getattr(page, "_auto_refresh_signature", None)
    if callable(helper):
        return helper(auto_payload)
    from .page_a07_background import A07PageBackgroundMixin

    return A07PageBackgroundMixin._auto_refresh_signature(page, auto_payload)


def _claim_auto_refresh_signature(page: object, signature: tuple[tuple[str, str], ...]) -> bool:
    helper = getattr(page, "_claim_auto_refresh_signature", None)
    if callable(helper):
        return bool(helper(signature))
    from .page_a07_background import A07PageBackgroundMixin

    return bool(A07PageBackgroundMixin._claim_auto_refresh_signature(page, signature))


def _sync_post_core_selection(page: object, target_code: str) -> None:
    page.workspace.selected_code = target_code or None
    page._update_history_details_from_selection()
    page._update_control_panel()
    page._update_control_transfer_buttons()


def _refresh_support_after_selection(page: object) -> None:
    if not bool(getattr(page, "_control_details_visible", False)):
        return
    schedule_render = getattr(page, "_schedule_active_support_render", None)
    if callable(schedule_render):
        try:
            schedule_render(force=True)
            return
        except Exception:
            pass
    try:
        page._refresh_control_support_trees()
    except Exception:
        pass
    try:
        active_tab = page._active_support_tab_key()
    except Exception:
        active_tab = None
    if active_tab:
        try:
            page._render_active_support_tab(force=True)
        except Exception:
            pass


def _clear_core_support_trees(page: object) -> None:
    tree_control_suggestions = getattr(page, "tree_control_suggestions", None)
    if tree_control_suggestions is not None:
        page._fill_tree(
            tree_control_suggestions,
            _empty_suggestions_df(),
            _CONTROL_SUGGESTION_COLUMNS,
        )
    tree_control_accounts = getattr(page, "tree_control_accounts", None)
    if tree_control_accounts is not None:
        page._fill_tree(
            tree_control_accounts,
            _empty_selected_accounts_df(),
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )


def apply_context_restore_payload(page: object, payload: dict[str, object]) -> None:
    context_warnings = _coerce_refresh_warnings(payload.get("warnings"))
    page._a07_refresh_warnings = context_warnings
    for warning in context_warnings:
        page._diag(f"context warning {warning}")
    page.workspace.gl_df = payload["gl_df"]
    page.tb_path = payload["tb_path"]
    page.workspace.source_a07_df = payload["source_a07_df"]
    page.workspace.a07_df = payload["a07_df"]
    page.a07_path = payload["a07_path"]
    page.workspace.mapping = payload["mapping"]
    page.mapping_path = payload["mapping_path"]
    page.workspace.groups = payload["groups"]
    page.groups_path = payload["groups_path"]
    page.workspace.locks = payload["locks"]
    page.locks_path = payload["locks_path"]
    page.workspace.project_meta = payload["project_meta"]
    page.project_path = payload["project_path"]
    page.workspace.basis_col = payload["basis_col"]
    page.basis_var.set(_BASIS_LABELS[page.workspace.basis_col])
    page.previous_mapping = payload["previous_mapping"]
    page.previous_mapping_path = payload["previous_mapping_path"]
    page.previous_mapping_year = payload["previous_mapping_year"]
    page.effective_a07_mapping = None
    page.effective_previous_a07_mapping = None
    page.rulebook_path = payload["rulebook_path"]
    page._pending_focus_code = payload["pending_focus_code"]
    client, year = page._session_context(session)
    page._context_snapshot = page._current_context_snapshot(client, year)
    page._start_core_refresh()


def apply_core_state(page: object, payload: dict[str, object]) -> dict[str, object]:
    diag = getattr(page, "_diag", lambda *_args, **_kwargs: None)
    combined_warnings = [
        *_coerce_refresh_warnings(getattr(page, "_a07_refresh_warnings", [])),
        *_coerce_refresh_warnings(payload.get("warnings")),
    ]
    page._a07_refresh_warnings = combined_warnings
    for warning in combined_warnings:
        diag(f"core warning {warning}")
    page.rulebook_path = payload["rulebook_path"]
    page.effective_rulebook = payload.get("effective_rulebook")
    page.matcher_settings = payload["matcher_settings"]
    page.previous_mapping = payload["previous_mapping"]
    page.previous_mapping_path = payload["previous_mapping_path"]
    page.previous_mapping_year = payload["previous_mapping_year"]
    if "groups" in payload:
        page.workspace.groups = payload["groups"]
    page.effective_a07_mapping = dict(payload.get("effective_mapping") or {})
    page.effective_previous_a07_mapping = dict(payload.get("effective_previous_mapping") or {})
    page.workspace.a07_df = payload["grouped_a07_df"]
    page.workspace.membership = payload["membership"]
    page.workspace.suggestions = payload["suggestions"]
    page.reconcile_df = payload.get("reconcile_df", _empty_reconcile_df())
    page.mapping_df = payload.get("mapping_df", _empty_mapping_df())
    page.mapping_audit_df = payload.get("mapping_audit_df", pd.DataFrame())
    page.mapping_review_df = payload.get("mapping_review_df", pd.DataFrame())
    page.unmapped_df = payload.get("unmapped_df", _empty_unmapped_df())
    page.control_gl_df = payload["control_gl_df"]
    page.a07_overview_df = payload["a07_overview_df"]
    page.control_df = payload["control_df"]
    page.rf1022_overview_df = payload.get("rf1022_overview_df", _empty_rf1022_overview_df())
    page.groups_df = payload["groups_df"]
    page.control_statement_base_df = payload.get(
        "control_statement_base_df",
        payload.get("control_statement_df", _empty_control_statement_df()),
    )
    try:
        _rebuild_refresh_indexes(page)
    except Exception as exc:
        diag(f"rebuild_a07_refresh_indexes failed: {exc}")

    current_control_statement_view = CONTROL_STATEMENT_VIEW_PAYROLL
    selected_control_statement_view = getattr(page, "_selected_control_statement_view", None)
    if callable(selected_control_statement_view):
        try:
            current_control_statement_view = selected_control_statement_view()
        except Exception:
            current_control_statement_view = CONTROL_STATEMENT_VIEW_PAYROLL
    if current_control_statement_view == CONTROL_STATEMENT_VIEW_PAYROLL:
        page.control_statement_df = payload.get(
            "control_statement_df",
            filter_control_statement_df(
                page.control_statement_base_df,
                view=CONTROL_STATEMENT_VIEW_PAYROLL,
            ),
        ).copy(deep=True)
    else:
        page.control_statement_df = page._build_current_control_statement_df(
            view=current_control_statement_view,
        )

    page.history_compare_df = _empty_history_df()
    page.control_statement_accounts_df = _empty_selected_accounts_df()
    page.control_suggestion_summary_var.set("Velg A07-kode til hoyre for aa se beste forslag.")
    page.control_suggestion_effect_var.set("Velg et forslag for aa se hva som blir koblet.")
    page.control_accounts_summary_var.set("Velg A07-kode til hoyre for aa se hva som er koblet na.")
    statement_accounts_var = getattr(page, "control_statement_accounts_summary_var", None)
    if statement_accounts_var is not None:
        statement_accounts_var.set("Velg gruppe i kontrolloppstillingen for aa se kontoene bak raden.")
    summary_var = getattr(page, "control_statement_summary_var", None)
    if summary_var is not None:
        try:
            summary_var.set(
                a07_control_status.build_control_statement_overview(
                    page.control_statement_df,
                    basis_col=page.workspace.basis_col,
                    amount_formatter=_format_picker_amount,
                )
            )
        except Exception:
            pass
    page._support_views_ready = True
    page._support_views_dirty = False
    page._history_compare_ready = False
    page._loaded_support_tabs.clear()
    try:
        page._loaded_support_context_keys.clear()
    except Exception:
        page._loaded_support_context_keys = {}

    pending_focus_code = str(page._pending_focus_code or "").strip()
    page._pending_focus_code = None
    selected_group_id = str(getattr(page, "_selected_rf1022_group_id", "") or "").strip()
    selected_work_level = getattr(page, "_selected_control_work_level", None)
    try:
        work_level = selected_work_level() if callable(selected_work_level) else "a07"
    except Exception:
        work_level = "a07"

    return {
        "restart": False,
        "pending_focus_code": pending_focus_code,
        "selected_group_id": selected_group_id,
        "work_level": work_level,
    }


def restore_core_selection(
    page: object,
    *,
    pending_focus_code: str,
    selected_group_id: str,
    work_level: str,
) -> bool:
    target_group = ""
    target_code = ""
    try:
        code_children = tuple(page.tree_a07.get_children())
    except Exception:
        code_children = ()
    if work_level == "rf1022":
        if code_children:
            if selected_group_id and selected_group_id in code_children:
                target_group = str(selected_group_id)
            else:
                target_group = str(
                    preferred_rf1022_overview_group(
                        getattr(page, "rf1022_overview_df", None),
                        code_children,
                    )
                    or code_children[0]
                )
    else:
        if code_children:
            if pending_focus_code and pending_focus_code in code_children:
                target_code = str(pending_focus_code)
            else:
                target_code = str(code_children[0])

    if target_group:
        try:
            page._set_tree_selection(page.tree_a07, target_group)
        except Exception:
            pass
        try:
            page._selected_rf1022_group_id = target_group
            focus_code = pending_focus_code
            if not focus_code:
                selected_code_getter = getattr(page, "_selected_control_code", None)
                if callable(selected_code_getter):
                    try:
                        focus_code = str(selected_code_getter() or "").strip()
                    except Exception:
                        focus_code = ""
            _sync_post_core_selection(page, focus_code)
            page._skip_initial_control_followup = False
            _refresh_support_after_selection(page)
        except Exception:
            pass
        return True

    if target_code:
        try:
            page._set_tree_selection(page.tree_a07, target_code)
        except Exception:
            pass
        try:
            _sync_post_core_selection(page, target_code)
            page._skip_initial_control_followup = False
            _refresh_support_after_selection(page)
        except Exception:
            pass
        return True

    return False


def finalize_core_refresh_ui(
    page: object,
    *,
    pending_focus_code: str,
    selected_group_id: str,
    work_level: str,
) -> None:
    diag = getattr(page, "_diag", lambda *_args, **_kwargs: None)
    cancel_watchdog = getattr(page, "_cancel_refresh_watchdog", lambda: None)
    try:
        diag("finalize_core_refresh start")
        tree_groups = getattr(page, "tree_groups", None)
        if tree_groups is not None:
            page._fill_tree(tree_groups, page.groups_df, _GROUP_COLUMNS, iid_column="GroupId")
        sync_groups_panel_visibility = getattr(page, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()
        tree_statement_accounts = getattr(page, "tree_control_statement_accounts", None)
        if tree_statement_accounts is not None:
            page._fill_tree(
                tree_statement_accounts,
                _empty_selected_accounts_df(),
                _CONTROL_SELECTED_ACCOUNT_COLUMNS,
                iid_column="Konto",
            )
        page._update_control_panel()
        page._update_control_transfer_buttons()
        page._update_summary()
        refresh_control_statement_window = getattr(page, "_refresh_control_statement_window", None)
        if callable(refresh_control_statement_window):
            refresh_control_statement_window()
        refresh_warnings = _coerce_refresh_warnings(getattr(page, "_a07_refresh_warnings", []))
        if refresh_warnings:
            page.status_var.set("A07 oppdatert med advarsler.")
            page.details_var.set(_format_refresh_warning_details(refresh_warnings))
        else:
            auto_summary = str(getattr(page, "_pending_auto_mapping_summary", "") or "").strip()
            if auto_summary:
                page.status_var.set("A07 oppdatert og auto-matchet.")
                page.details_var.set(auto_summary)
                page._pending_auto_mapping_summary = ""
            else:
                page.status_var.set("A07 oppdatert.")
                page.details_var.set("Velg konto og kode for aa jobbe videre. Historikk lastes ved behov.")
        try:
            page._set_control_details_visible(True)
            page._support_requested = True
        except Exception:
            pass

        selection_restored = restore_core_selection(
            page,
            pending_focus_code=pending_focus_code,
            selected_group_id=selected_group_id,
            work_level=work_level,
        )
        if not selection_restored:
            _clear_core_support_trees(page)
        page._pending_support_refresh = False
        if page._pending_session_refresh:
            page._pending_session_refresh = False
            if page._context_has_changed():
                page._schedule_session_refresh()
        diag("finalize_core_refresh complete")
    except Exception as exc:
        diag(f"finalize_core_refresh error: {exc}")
        diag(traceback.format_exc())
        page.status_var.set("A07-oppdatering feilet i ferdigstilling.")
        page.details_var.set(str(exc))
    finally:
        page._refresh_in_progress = False
        cancel_watchdog()


def apply_core_refresh_payload(page: object, payload: dict[str, object]) -> None:
    state = apply_core_state(page, payload)
    if bool(state.get("restart")):
        return

    def _finalize() -> None:
        finalize_core_refresh_ui(
            page,
            pending_focus_code=str(state.get("pending_focus_code") or ""),
            selected_group_id=str(state.get("selected_group_id") or ""),
            work_level=str(state.get("work_level") or "a07"),
        )

    refresh_control_gl = getattr(page, "_refresh_control_gl_tree_chunked", None)
    refresh_a07 = getattr(page, "_refresh_a07_tree_chunked", None)
    if callable(refresh_control_gl) and callable(refresh_a07):
        refresh_control_gl(on_complete=lambda: refresh_a07(on_complete=_finalize))
        return
    page._refresh_control_gl_tree()
    page._refresh_a07_tree()
    _finalize()


def apply_support_refresh_payload(page: object, payload: dict[str, object]) -> None:
    page.history_compare_df = payload["history_compare_df"]
    page._history_compare_ready = True
    page._support_views_ready = True
    page._support_views_dirty = False
    page._loaded_support_tabs.discard("history")
    try:
        page._loaded_support_context_keys.pop("history", None)
    except Exception:
        pass

    def _apply_support_ui_updates() -> None:
        active_tab = page._active_support_tab_key()
        if bool(getattr(page, "_control_details_visible", False)):
            page._refresh_control_support_trees()
            if active_tab:
                page._render_active_support_tab(force=True)
        page._update_history_details_from_selection()
        page._update_control_panel()
        page._update_control_transfer_buttons()
        page._update_summary()

    try:
        page.after_idle(_apply_support_ui_updates)
    except Exception:
        _apply_support_ui_updates()


__all__ = [
    "apply_context_restore_payload",
    "apply_core_refresh_payload",
    "apply_core_state",
    "apply_support_refresh_payload",
    "finalize_core_refresh_ui",
    "restore_core_selection",
]
