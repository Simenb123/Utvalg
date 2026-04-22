from __future__ import annotations


import copy
import faulthandler
import json
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Sequence

import pandas as pd

import app_paths
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
from a07_feature.control import status as a07_control_status
from a07_feature.control.data import (
    a07_code_rf1022_group,
    a07_suggestion_is_strict_auto,
    build_a07_overview_df,
    build_control_accounts_summary,
    build_control_gl_df,
    build_control_queue_df,
    build_control_selected_account_df,
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    build_global_auto_mapping_plan,
    build_history_comparison_df,
    build_mapping_history_details,
    build_rf1022_accounts_df,
    build_rf1022_candidate_df,
    build_rf1022_candidate_df_for_groups,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
    control_gl_tree_tag,
    control_queue_tree_tag,
    filter_a07_overview_df,
    filter_control_gl_df,
    filter_control_search_df,
    filter_control_queue_by_rf1022_group,
    filter_control_visible_codes_df,
    filter_suggestions_for_rf1022_group,
    filter_suggestions_df,
    reconcile_tree_tag,
    rf1022_group_a07_codes,
    rf1022_group_label,
    rf1022_post_for_group,
    RF1022_UNKNOWN_GROUP,
    select_batch_suggestion_rows,
    select_magic_wand_suggestion_rows,
    suggestion_tree_tag,
    unresolved_codes,
)
from a07_feature.control.matching import (
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
from a07_feature.rule_learning import append_a07_rule_keywords
from a07_feature.page_paths import (
    MATCHER_SETTINGS_DEFAULTS as _MATCHER_SETTINGS_DEFAULTS,
    _path_signature,
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

try:
    import client_store
except Exception:
    client_store = None

from .page_a07_dialogs import (
    apply_manual_mapping_choice,
    apply_manual_mapping_choices,
    build_a07_picker_options,
    build_gl_picker_options,
    open_manual_mapping_dialog,
    remove_mapping_accounts,
)
from .page_a07_env import messagebox
from .page_a07_frames import _empty_suggestions_df

_RF1022_GROUP_DEFAULT_CODES: dict[str, str] = {
    "100_loenn_ol": "annet",
    "100_refusjon": "sumAvgiftsgrunnlagRefusjon",
    "111_naturalytelser": "elektroniskKommunikasjon",
    "112_pensjon": "tilskuddOgPremieTilPensjon",
}

_RF1022_GROUP_NAME_HINTS: dict[str, tuple[tuple[tuple[str, ...], str], ...]] = {
    "100_loenn_ol": (
        (("overtid",), "overtidsgodtgjoerelse"),
        (("time", "timelonn", "timelÃ¸nn"), "timeloenn"),
        (("trekk", "ferie"), "trekkloennForFerie"),
        (("ferie", "feriepenger"), "feriepenger"),
        (("styre", "honorar", "verv"), "styrehonorarOgGodtgjoerelseVerv"),
        (("lonn", "lÃ¸nn", "bonus", "etterlonn", "etterlÃ¸nn"), "fastloenn"),
    ),
    "111_naturalytelser": (
        (("telefon", "mobil", "ekom", "elektron"), "elektroniskKommunikasjon"),
        (("forsik", "gruppeliv", "ulykke"), "skattepliktigDelForsikringer"),
    ),
}


def _split_mapping_accounts(value: object) -> set[str]:
    raw = str(value or "")
    return {part.strip() for part in raw.split(",") if part.strip()}


def _locked_codes_for(page: object) -> set[str]:
    getter = getattr(page, "_locked_codes", None)
    if callable(getter):
        try:
            return {str(code).strip() for code in getter() if str(code).strip()}
        except Exception:
            pass
    workspace = getattr(page, "workspace", None)
    locked = getattr(workspace, "locks", None) or ()
    return {str(code).strip() for code in locked if str(code).strip()}


def _locked_mapping_conflicts_for(
    page: object,
    accounts: Sequence[object] | None = None,
    *,
    target_code: object | None = None,
) -> list[str]:
    getter = getattr(page, "_locked_mapping_conflicts", None)
    if callable(getter):
        try:
            return getter(accounts, target_code=target_code)
        except Exception:
            pass

    locked = _locked_codes_for(page)
    if not locked:
        return []

    workspace = getattr(page, "workspace", None)
    mapping = getattr(workspace, "mapping", None) or {}
    membership = getattr(workspace, "membership", None) or {}
    effective_mapping_getter = getattr(page, "_effective_mapping", None)
    if callable(effective_mapping_getter):
        try:
            effective_mapping = effective_mapping_getter()
        except Exception:
            effective_mapping = dict(mapping)
    else:
        effective_mapping = dict(mapping)

    conflicts: list[str] = []
    target_code_s = str(target_code or "").strip()
    if target_code_s and target_code_s in locked:
        conflicts.append(target_code_s)
    target_group_code = str(membership.get(target_code_s) or "").strip()
    if target_group_code and target_group_code in locked and target_group_code not in conflicts:
        conflicts.append(target_group_code)
    for account in accounts or ():
        account_s = str(account or "").strip()
        if not account_s:
            continue
        current_code = str(effective_mapping.get(account_s) or mapping.get(account_s) or "").strip()
        if current_code and current_code in locked and current_code not in conflicts:
            conflicts.append(current_code)
    return conflicts


def _notify_locked_conflicts_for(
    page: object,
    conflicts: Sequence[object],
    *,
    focus_widget: object | None = None,
) -> bool:
    notifier = getattr(page, "_notify_locked_conflicts", None)
    if callable(notifier):
        try:
            return bool(notifier(conflicts, focus_widget=focus_widget))
        except Exception:
            pass

    codes = [str(code).strip() for code in conflicts if str(code).strip()]
    if not codes:
        return False
    preview = ", ".join(codes[:3])
    if len(codes) > 3:
        preview += ", ..."
    notify_inline = getattr(page, "_notify_inline", None)
    if callable(notify_inline):
        notify_inline(
            f"Endringen berorer laaste koder: {preview}. Laas opp for du endrer mapping.",
            focus_widget=focus_widget,
        )
        return True
    return False


class A07PageMappingActionsMixin:
    def _rf1022_group_menu_choices(self) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()
        overview_df = getattr(self, "rf1022_overview_df", None)
        if isinstance(overview_df, pd.DataFrame) and not overview_df.empty:
            for _, row in overview_df.iterrows():
                group_id = str(row.get("GroupId") or "").strip()
                if not group_id or group_id in seen:
                    continue
                label = str(row.get("Navn") or "").strip() or rf1022_group_label(group_id) or group_id
                choices.append((group_id, label))
                seen.add(group_id)
        for group_id in ("100_loenn_ol", "100_refusjon", "111_naturalytelser", "112_pensjon", "uavklart_rf1022"):
            if group_id in seen:
                continue
            label = rf1022_group_label(group_id) or group_id
            choices.append((group_id, label))
        return choices

    def _a07_code_menu_choices(self, *, limit: int = 120) -> list[tuple[str, str]]:
        choices: list[tuple[str, str]] = []
        seen: set[str] = set()

        def _add_choice(code: object, label: object | None = None) -> None:
            code_s = str(code or "").strip()
            if not code_s or code_s.startswith("A07_GROUP:") or code_s in seen:
                return
            label_s = str(label or "").strip()
            if not label_s:
                label_s = code_s
            if not label_s.lower().startswith(code_s.lower()):
                label_s = f"{code_s} - {label_s}"
            if len(label_s) > 110:
                label_s = f"{label_s[:107]}..."
            choices.append((code_s, label_s))
            seen.add(code_s)

        control_df = getattr(self, "control_df", None)
        if isinstance(control_df, pd.DataFrame) and not control_df.empty and "Kode" in control_df.columns:
            for _, row in control_df.iterrows():
                label = row.get("Navn") if "Navn" in control_df.columns else ""
                if not str(label or "").strip() and "A07Post" in control_df.columns:
                    label = row.get("A07Post")
                _add_choice(row.get("Kode"), label)
                if len(choices) >= limit:
                    return choices

        workspace = getattr(self, "workspace", None)
        a07_df = getattr(workspace, "a07_df", None)
        for option in build_a07_picker_options(a07_df if isinstance(a07_df, pd.DataFrame) else pd.DataFrame()):
            _add_choice(option.key, option.label)
            if len(choices) >= limit:
                break
        return choices

    def _activate_a07_code_for_explicit_account_action(self, code: str | None) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        try:
            self.workspace.selected_code = code_s
        except Exception:
            pass
        sync_level = getattr(self, "_sync_control_work_level_vars", None)
        if callable(sync_level):
            try:
                sync_level("a07")
            except Exception:
                pass
        sync_work_level_ui = getattr(self, "_sync_control_work_level_ui", None)
        if callable(sync_work_level_ui):
            try:
                sync_work_level_ui()
            except Exception:
                pass
        sync_tabs = getattr(self, "_sync_support_notebook_tabs", None)
        if callable(sync_tabs):
            try:
                sync_tabs()
            except Exception:
                pass
        refresh_tree = getattr(self, "_refresh_a07_tree", None)
        if callable(refresh_tree):
            try:
                refresh_tree()
            except Exception:
                pass
        focus_code = getattr(self, "_focus_control_code", None)
        if callable(focus_code):
            try:
                focus_code(code_s)
            except Exception:
                pass

    def _resolve_rf1022_target_code(
        self,
        group_id: str | None,
        accounts: Sequence[object] | None = None,
    ) -> str | None:
        group_s = str(group_id or "").strip()
        allowed_codes = tuple(rf1022_group_a07_codes(group_s))
        if not group_s or not allowed_codes:
            return None

        selected_code = str(getattr(getattr(self, "workspace", None), "selected_code", None) or "").strip()
        if selected_code in allowed_codes:
            return selected_code

        effective_mapping_getter = getattr(self, "_effective_mapping", None)
        if callable(effective_mapping_getter):
            try:
                effective_mapping = dict(effective_mapping_getter() or {})
            except Exception:
                effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        else:
            effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})

        mapped_codes: list[str] = []
        account_keys = [str(account or "").strip() for account in (accounts or ()) if str(account or "").strip()]
        for account in account_keys:
            mapped_code = str(effective_mapping.get(account) or "").strip()
            if mapped_code in allowed_codes:
                mapped_codes.append(mapped_code)
        if mapped_codes:
            unique_mapped_codes = sorted(set(mapped_codes))
            if len(unique_mapped_codes) == 1:
                return unique_mapped_codes[0]
            return None

        suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
        if isinstance(suggestions_df, pd.DataFrame) and not suggestions_df.empty and account_keys:
            scoped = filter_suggestions_for_rf1022_group(suggestions_df, group_s)
            if not scoped.empty:
                ranked: list[tuple[int, int, float, str]] = []
                account_set = set(account_keys)
                for _, row in scoped.iterrows():
                    code = str(row.get("Kode") or "").strip()
                    if code not in allowed_codes:
                        continue
                    if not a07_suggestion_is_strict_auto(row):
                        continue
                    suggestion_accounts = _split_mapping_accounts(row.get("ForslagKontoer"))
                    if not suggestion_accounts:
                        continue
                    overlap = len(account_set & suggestion_accounts)
                    if overlap <= 0:
                        continue
                    within_tolerance = 1 if bool(row.get("WithinTolerance")) else 0
                    score = float(pd.to_numeric(row.get("Score"), errors="coerce") or 0.0)
                    ranked.append((overlap, within_tolerance, score, code))
                if ranked:
                    ranked.sort(key=lambda item: (item[0], item[1], item[2], item[3]), reverse=True)
                    return ranked[0][3]

        gl_df = getattr(self, "control_gl_df", None)
        if not isinstance(gl_df, pd.DataFrame) or gl_df.empty:
            gl_df = getattr(getattr(self, "workspace", None), "gl_df", None)
        if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and account_keys:
            try:
                names = gl_df.loc[gl_df["Konto"].astype(str).str.strip().isin(account_keys), "Navn"]
            except Exception:
                names = pd.Series(dtype="object")
            names_text = " ".join(str(value or "").strip().lower() for value in names if str(value or "").strip())
            for keywords, code in _RF1022_GROUP_NAME_HINTS.get(group_s, ()):
                if code not in allowed_codes:
                    continue
                if code == "styrehonorarOgGodtgjoerelseVerv" and "honorar" in names_text:
                    if not any(token in names_text for token in ("styre", "verv", "godtgj")):
                        continue
                if all(keyword in names_text for keyword in keywords):
                    return code
                if any(keyword in names_text for keyword in keywords):
                    return code

        if len(allowed_codes) == 1:
            return allowed_codes[0]
        return None

    def _assign_accounts_to_rf1022_group(
        self,
        accounts: Sequence[object] | None,
        group_id: str | None,
        *,
        source_label: str = "RF-1022-mapping",
    ) -> None:
        account_list = [str(account or "").strip() for account in (accounts or ()) if str(account or "").strip()]
        if not account_list:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        group_s = str(group_id or "").strip()
        if not group_s:
            self._notify_inline("Velg en RF-1022-post til hoyre forst.", focus_widget=self.tree_a07)
            return
        target_code = self._resolve_rf1022_target_code(group_s, account_list)
        if not target_code:
            self._notify_inline("Fant ingen A07-detalj for valgt RF-1022-post.", focus_widget=self.tree_a07)
            return
        conflicts = _locked_mapping_conflicts_for(self, account_list, target_code=target_code)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        assigned = apply_manual_mapping_choices(self.workspace.mapping, account_list, target_code)
        autosaved = self._autosave_mapping()
        try:
            self._selected_rf1022_group_id = group_s
        except Exception:
            pass
        self._refresh_core(focus_code=target_code)
        self._focus_mapping_account(assigned[0])
        try:
            self._focus_control_code(target_code)
        except Exception:
            pass
        group_label = rf1022_group_label(group_s) or group_s
        count = len(assigned)
        if autosaved:
            self.status_var.set(
                f"{source_label}: tildelte {count} konto(er) til {group_label} via {target_code} og lagret i klientmappen."
            )
        else:
            self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {group_label} via {target_code}.")
        self._select_primary_tab()

    def _assign_selected_accounts_to_rf1022_group(self, group_id: str | None) -> None:
        self._assign_accounts_to_rf1022_group(
            self._selected_control_gl_accounts(),
            group_id,
            source_label="RF-1022-mapping",
        )

    def _assign_accounts_to_a07_code(
        self,
        accounts: Sequence[object] | None,
        code: str | None,
        *,
        source_label: str = "Mapping",
    ) -> None:
        account_list = [str(account or "").strip() for account in (accounts or ()) if str(account or "").strip()]
        if not account_list:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        code_s = str(code or "").strip()
        if not code_s:
            self._notify_inline("Velg en A07-kode forst.", focus_widget=self.tree_a07)
            return
        conflicts = _locked_mapping_conflicts_for(self, account_list, target_code=code_s)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        try:
            assigned = apply_manual_mapping_choices(self.workspace.mapping, account_list, code_s)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code_s)
            self._focus_mapping_account(assigned[0])
            self._activate_a07_code_for_explicit_account_action(code_s)
            count = len(assigned)
            if autosaved:
                self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {code_s} og lagret i klientmappen.")
            else:
                self.status_var.set(f"{source_label}: tildelte {count} konto(er) til {code_s}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke tildele konto til kode:\n{exc}")

    def _assign_selected_accounts_to_a07_code(self, code: str | None) -> None:
        self._assign_accounts_to_a07_code(
            self._selected_control_gl_accounts(),
            code,
            source_label="Mapping",
        )

    def _current_rf1022_candidate_df(self) -> pd.DataFrame:
        has_runtime_data = hasattr(self, "control_gl_df")
        try:
            return build_rf1022_candidate_df(
                self.control_gl_df,
                self._ensure_suggestion_display_fields(),
                self._selected_rf1022_group(),
                basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            )
        except Exception:
            if not has_runtime_data:
                candidates = getattr(self, "rf1022_candidate_df", None)
                if isinstance(candidates, pd.DataFrame):
                    return candidates.copy()
            return pd.DataFrame()

    def _all_rf1022_candidate_df(self) -> pd.DataFrame:
        has_runtime_data = hasattr(self, "control_gl_df")
        try:
            group_ids = [group_id for group_id, _label in self._rf1022_group_menu_choices()]
            return build_rf1022_candidate_df_for_groups(
                self.control_gl_df,
                self._ensure_suggestion_display_fields(),
                group_ids,
                basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            )
        except Exception:
            if not has_runtime_data:
                candidates = getattr(self, "rf1022_all_candidate_df", None)
                if isinstance(candidates, pd.DataFrame):
                    return candidates.copy()
            return pd.DataFrame()

    def _rf1022_candidates_with_target_codes(self, candidates: pd.DataFrame | None) -> pd.DataFrame:
        if candidates is None:
            return pd.DataFrame()
        work = candidates.copy()
        if work.empty:
            return work
        if "Kode" not in work.columns:
            work["Kode"] = ""
        if "Konto" not in work.columns:
            work["Konto"] = ""
        if "Rf1022GroupId" not in work.columns:
            work["Rf1022GroupId"] = ""
        for idx, row in work.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                continue
            account = str(row.get("Konto") or "").strip()
            group_id = str(row.get("Rf1022GroupId") or "").strip()
            resolved = str(self._resolve_rf1022_target_code(group_id, [account]) or "").strip()
            if resolved:
                work.at[idx, "Kode"] = resolved
        return work

    def _build_global_auto_mapping_plan(self, candidates: pd.DataFrame | None = None) -> pd.DataFrame:
        started = time.perf_counter()
        if candidates is None:
            candidates = self._all_rf1022_candidate_df()
        code_resolver = getattr(self, "_rf1022_candidates_with_target_codes", None)
        if callable(code_resolver):
            candidates = code_resolver(candidates)
        else:
            candidates = A07PageMappingActionsMixin._rf1022_candidates_with_target_codes(self, candidates)
        if candidates is None or candidates.empty:
            return pd.DataFrame()
        try:
            suggestions_df = self._ensure_suggestion_display_fields()
        except Exception:
            suggestions_df = pd.DataFrame()
        plan = build_global_auto_mapping_plan(
            candidates,
            getattr(self, "control_gl_df", pd.DataFrame()),
            suggestions_df,
            dict(self._effective_mapping() or {}),
            locked_codes=_locked_codes_for(self),
            basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            rulebook=getattr(self, "effective_rulebook", None),
        )
        try:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._diag(f"global_auto_plan rows={len(plan.index)} elapsed_ms={elapsed_ms}")
        except Exception:
            pass
        return plan

    @staticmethod
    def _global_auto_plan_action_counts(plan: pd.DataFrame | None) -> dict[str, int]:
        counts = {
            "safe": 0,
            "actionable": 0,
            "review": 0,
            "invalid": 0,
            "already": 0,
            "conflict": 0,
            "locked": 0,
            "blocked": 0,
        }
        if plan is None or plan.empty or "Action" not in plan.columns:
            return counts
        actions = plan["Action"].fillna("").astype(str).str.strip()
        counts["actionable"] = int((actions == "apply").sum())
        counts["safe"] = counts["actionable"] + int((actions == "already").sum())
        counts["review"] = int(actions.isin({"review", "blocked"}).sum())
        counts["blocked"] = int((actions == "blocked").sum())
        counts["invalid"] = int((actions == "invalid").sum())
        counts["already"] = int((actions == "already").sum())
        counts["conflict"] = int((actions == "conflict").sum())
        counts["locked"] = int((actions == "locked").sum())
        return counts

    def _rf1022_candidate_action_counts(self, candidates: pd.DataFrame | None) -> dict[str, int]:
        return self.get_global_auto_plan_summary(candidates)

    def get_global_auto_plan_summary(self, candidates: pd.DataFrame | None = None) -> dict[str, int]:
        """Cheap UI precheck; click handlers still build the full guarded plan."""
        started = time.perf_counter()
        counts = {
            "safe": 0,
            "actionable": 0,
            "review": 0,
            "invalid": 0,
            "already": 0,
            "conflict": 0,
            "locked": 0,
            "blocked": 0,
        }
        if candidates is None:
            candidates = self._all_rf1022_candidate_df()
        code_resolver = getattr(self, "_rf1022_candidates_with_target_codes", None)
        if callable(code_resolver):
            try:
                candidates = code_resolver(candidates)
            except Exception:
                candidates = pd.DataFrame()
        if candidates is None or candidates.empty:
            return counts

        try:
            locked = _locked_codes_for(self)
        except Exception:
            locked = set()
        try:
            current_mapping = dict(self._effective_mapping() or {})
        except Exception:
            current_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        gl_accounts: set[str] = set()
        gl_df = getattr(self, "control_gl_df", None)
        if isinstance(gl_df, pd.DataFrame) and not gl_df.empty and "Konto" in gl_df.columns:
            try:
                gl_accounts = {str(value).strip() for value in gl_df["Konto"].dropna().astype(str) if str(value).strip()}
            except Exception:
                gl_accounts = set()

        for _, row in candidates.iterrows():
            account = str(row.get("Konto") or "").strip()
            code = str(row.get("Kode") or "").strip()
            group_id = str(row.get("Rf1022GroupId") or "").strip()
            status = str(row.get("Forslagsstatus") or "").strip()
            try:
                strict = bool(a07_suggestion_is_strict_auto(row))
            except Exception:
                strict = False
            strict = strict or status == "Trygt forslag"
            if not account or not code:
                counts["invalid"] += 1
                continue
            if not strict:
                counts["review"] += 1
                continue
            if gl_accounts and account not in gl_accounts:
                counts["invalid"] += 1
                continue
            current = str(current_mapping.get(account) or "").strip()
            if current == code:
                counts["already"] += 1
                counts["safe"] += 1
                continue
            if current and current != code:
                counts["conflict"] += 1
                continue
            if code in locked:
                counts["locked"] += 1
                continue
            resolved_group = a07_code_rf1022_group(code)
            if resolved_group == RF1022_UNKNOWN_GROUP:
                counts["review"] += 1
                continue
            if group_id and group_id != resolved_group:
                counts["blocked"] += 1
                continue
            counts["actionable"] += 1
            counts["safe"] += 1
        try:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._diag(f"global_auto_summary candidates={len(candidates.index)} actionable={counts['actionable']} elapsed_ms={elapsed_ms}")
        except Exception:
            pass
        return counts

    def _selected_rf1022_candidate_row(self) -> pd.Series | None:
        tree = getattr(self, "tree_control_suggestions", None)
        if tree is None:
            return None
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        account = str(selection[0] or "").strip()
        if not account:
            return None
        candidates = self._current_rf1022_candidate_df()
        if candidates.empty or "Konto" not in candidates.columns:
            return None
        matches = candidates.loc[candidates["Konto"].astype(str).str.strip() == account]
        if matches.empty:
            return None
        return matches.iloc[0]

    def _apply_selected_rf1022_candidate(self) -> None:
        row = self._selected_rf1022_candidate_row()
        if row is None:
            self._notify_inline("Velg en RF-1022-kandidat forst.", focus_widget=self.tree_control_suggestions)
            return
        account = str(row.get("Konto") or "").strip()
        code = str(row.get("Kode") or "").strip()
        if not code:
            code = str(self._resolve_rf1022_target_code(row.get("Rf1022GroupId"), [account]) or "").strip()
        if not account or not code:
            self._notify_inline("Kandidaten mangler konto eller A07-kode.", focus_widget=self.tree_control_suggestions)
            return
        plan_builder = getattr(self, "_build_global_auto_mapping_plan", None)
        try:
            plan = plan_builder(pd.DataFrame([dict(row)])) if callable(plan_builder) else pd.DataFrame()
        except Exception:
            plan = pd.DataFrame()
        if plan is None or plan.empty or "Action" not in plan.columns:
            self._notify_inline("Kandidaten kunne ikke sikkerhetskontrolleres.", focus_widget=self.tree_control_suggestions)
            return
        plan_row = plan.iloc[0]
        action = str(plan_row.get("Action") or "").strip()
        if action != "apply":
            status = str(plan_row.get("Status") or "Maa vurderes").strip()
            reason = str(plan_row.get("Reason") or "").strip()
            suffix = f": {reason}" if reason else "."
            self._notify_inline(
                f"Kandidaten kan ikke brukes automatisk ({status}){suffix}",
                focus_widget=self.tree_control_suggestions,
            )
            return
        checked_code = str(plan_row.get("Kode") or code).strip()
        checked_account = str(plan_row.get("Konto") or account).strip()
        self._assign_accounts_to_a07_code([checked_account], checked_code, source_label="RF-1022-forslag")

    def _apply_rf1022_candidate_suggestions(self) -> None:
        all_candidates = self._all_rf1022_candidate_df()
        if all_candidates.empty:
            self._notify_inline("Fant ingen trygge RF-1022-kandidater.", focus_widget=self.tree_control_suggestions)
            return
        plan_builder = getattr(self, "_build_global_auto_mapping_plan", None)
        if callable(plan_builder):
            plan = plan_builder(all_candidates)
        else:
            plan = A07PageMappingActionsMixin._build_global_auto_mapping_plan(self, all_candidates)
        self.rf1022_auto_plan_df = plan
        counts = A07PageMappingActionsMixin._global_auto_plan_action_counts(plan)
        if plan is None or plan.empty:
            self._notify_inline("Fant ingen trygge RF-1022-kandidater.", focus_widget=self.tree_control_suggestions)
            return

        candidates = plan.loc[plan["Action"].astype(str).str.strip() == "apply"].copy()
        if candidates.empty:
            skipped = counts["invalid"] + counts["conflict"] + counts["locked"] + counts["blocked"]
            self._notify_inline(
                "Fant ingen nye RF-1022-kandidater som kunne brukes "
                f"(hoppet over {skipped}, allerede {counts['already']}, "
                f"laast/konflikt {counts['locked'] + counts['conflict']}, maa vurderes {counts['review']}).",
                focus_widget=self.tree_control_suggestions,
            )
            return

        applied: list[tuple[str, str]] = []
        invalid = 0
        conflict = 0
        locked = 0
        for _, row in candidates.iterrows():
            account = str(row.get("Konto") or "").strip()
            code = str(row.get("Kode") or "").strip()
            if not account or not code:
                invalid += 1
                continue
            current_code = str((self._effective_mapping() or {}).get(account) or "").strip()
            if current_code and current_code != code:
                conflict += 1
                continue
            conflicts = _locked_mapping_conflicts_for(self, [account], target_code=code)
            if conflicts:
                locked += 1
                continue
            apply_manual_mapping_choice(self.workspace.mapping, account, code)
            applied.append((account, code))

        if not applied:
            skipped = invalid + conflict + locked + counts["blocked"]
            self._notify_inline(
                "Fant ingen nye RF-1022-kandidater som kunne brukes "
                f"(hoppet over {skipped}, allerede {counts['already']}, "
                f"laast/konflikt {conflict + locked}, maa vurderes {counts['review']}).",
                focus_widget=self.tree_control_suggestions,
            )
            return

        autosaved = self._autosave_mapping()
        first_account, first_code = applied[0]
        self._refresh_core(focus_code=first_code)
        self._focus_mapping_account(first_account)
        try:
            self._focus_control_code(first_code)
        except Exception:
            pass
        applied_groups = 0
        try:
            applied_accounts = {account for account, _code in applied}
            applied_groups = int(
                candidates.loc[candidates["Konto"].astype(str).str.strip().isin(applied_accounts), "Rf1022GroupId"]
                .fillna("")
                .astype(str)
                .str.strip()
                .replace("", pd.NA)
                .dropna()
                .nunique()
            )
        except Exception:
            applied_groups = 0
        suffix_parts: list[str] = []
        if applied_groups:
            suffix_parts.append(f"{applied_groups} post(er)")
        skipped = invalid + conflict + locked + counts["blocked"]
        if skipped:
            suffix_parts.append(f"hoppet over {skipped}")
        if counts["already"]:
            suffix_parts.append(f"{counts['already']} allerede koblet")
        if locked:
            suffix_parts.append(f"{locked} laast")
        if conflict:
            suffix_parts.append(f"{conflict} konflikt")
        if counts["review"]:
            suffix_parts.append(f"{counts['review']} maa vurderes")
        suffix = f" ({', '.join(suffix_parts)})" if suffix_parts else ""
        if autosaved:
            self.status_var.set(
                f"Trygg auto-matching: brukte {len(applied)} sikre forslag{suffix} og lagret i klientmappen."
            )
        else:
            self.status_var.set(f"Trygg auto-matching: brukte {len(applied)} sikre forslag{suffix}.")
        self._select_primary_tab()

    def _focus_linked_code_for_selected_gl_account(self) -> None:
        accounts = self._selected_control_gl_accounts()
        account = str(accounts[0] if accounts else "").strip()
        if not account:
            self._notify_inline(
                "Velg en GL-konto til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        try:
            mapping = self._effective_mapping()
        except Exception:
            mapping = getattr(getattr(self, "workspace", None), "mapping", {}) or {}
        code = str(mapping.get(account) or "").strip()
        if not code:
            self._notify_inline(
                f"Konto {account} har ingen A07-kobling.",
                focus_widget=self.tree_control_gl,
            )
            return
        self._activate_a07_code_for_explicit_account_action(code)
        try:
            self.status_var.set(f"Konto {account} er koblet til A07-kode {code}.")
        except Exception:
            pass

    def _apply_account_code_mapping(
        self,
        konto: str | None,
        kode: str | None,
        *,
        source_label: str = "Mapping satt",
    ) -> None:
        conflicts = _locked_mapping_conflicts_for(self, [konto], target_code=kode)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return
        konto_s, kode_s = apply_manual_mapping_choice(self.workspace.mapping, konto, kode)
        autosaved = self._autosave_mapping()
        self._refresh_core(focus_code=kode_s)
        self._focus_control_code(kode_s)
        self._focus_mapping_account(konto_s)

        if autosaved:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s} og lagret i klientmappen.")
        else:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s}.")
        self._select_primary_tab()

    def _remove_mapping_accounts_checked(
        self,
        accounts: Sequence[object],
        *,
        focus_widget: object | None = None,
        refresh: str = "core",
        source_label: str = "Fjernet mapping fra",
    ) -> list[str]:
        clean_accounts = [
            str(account or "").strip()
            for account in (accounts or ())
            if str(account or "").strip()
        ]
        if not clean_accounts:
            return []
        conflicts = _locked_mapping_conflicts_for(self, clean_accounts)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=focus_widget):
            return []

        removed = remove_mapping_accounts(self.workspace.mapping, clean_accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen mapping aa fjerne.",
                focus_widget=focus_widget,
            )
            return []

        try:
            autosaved = self._autosave_mapping()
            if refresh == "none":
                pass
            elif refresh == "all":
                self._refresh_all()
            else:
                selected_code_getter = getattr(self, "_selected_control_code", None)
                try:
                    focus_code = selected_code_getter() if callable(selected_code_getter) else None
                except Exception:
                    focus_code = None
                self._refresh_core(focus_code=focus_code)
            if refresh != "none":
                self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"{source_label} {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"{source_label} {count} konto(er).")
            if refresh != "none":
                self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fjerne mapping fra konto:\n{exc}")
        return removed

    def _control_account_name_lookup(self, accounts: Sequence[object]) -> dict[str, str]:
        wanted = {str(account or "").strip() for account in accounts if str(account or "").strip()}
        if not wanted:
            return {}
        out: dict[str, str] = {}
        frames = (
            getattr(self, "control_selected_accounts_df", None),
            getattr(self, "control_gl_df", None),
            getattr(self, "mapping_df", None),
        )
        for frame in frames:
            if frame is None or getattr(frame, "empty", True):
                continue
            if "Konto" not in frame.columns or "Navn" not in frame.columns:
                continue
            work = frame.copy()
            work["Konto"] = work["Konto"].fillna("").astype(str).str.strip()
            for _, row in work.iterrows():
                account = str(row.get("Konto") or "").strip()
                if account not in wanted or account in out:
                    continue
                name = str(row.get("Navn") or "").strip()
                if name:
                    out[account] = name
        return out

    def _mapped_a07_code_for_account(self, account: object) -> str:
        account_s = str(account or "").strip()
        if not account_s:
            return ""
        effective_mapping_getter = getattr(self, "_effective_mapping", None)
        if callable(effective_mapping_getter):
            try:
                code = str((effective_mapping_getter() or {}).get(account_s) or "").strip()
                if code:
                    return code
            except Exception:
                pass
        workspace = getattr(self, "workspace", None)
        mapping = getattr(workspace, "mapping", None) or {}
        return str(mapping.get(account_s) or "").strip()

    def _notify_a07_rule_learning_changed(self) -> None:
        app = getattr(session, "APP", None)
        for attr_name in ("page_admin", "page_saldobalanse", "page_analyse"):
            other_page = getattr(app, attr_name, None)
            if other_page is None or other_page is self:
                continue
            refresh = getattr(other_page, "refresh_from_session", None)
            if callable(refresh):
                try:
                    refresh(session)
                    continue
                except TypeError:
                    try:
                        refresh()
                        continue
                    except Exception:
                        pass
                except Exception:
                    pass
            refresh_plain = getattr(other_page, "refresh", None)
            if callable(refresh_plain):
                try:
                    refresh_plain()
                except Exception:
                    pass
        admin_page = getattr(app, "page_admin", None)
        rulebook_editor = getattr(admin_page, "_rulebook_editor", None)
        reload_editor = getattr(rulebook_editor, "reload", None)
        if callable(reload_editor):
            try:
                reload_editor()
            except Exception:
                pass

    def _learn_selected_control_account_names(
        self,
        *,
        exclude: bool,
        remove_mapping: bool = False,
    ) -> None:
        accounts_getter = getattr(self, "_selected_control_account_ids", None)
        accounts = accounts_getter() if callable(accounts_getter) else []
        accounts = [str(account or "").strip() for account in accounts if str(account or "").strip()]
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst forst.",
                focus_widget=getattr(self, "tree_control_accounts", None),
            )
            return

        if remove_mapping:
            conflicts = _locked_mapping_conflicts_for(self, accounts)
            if _notify_locked_conflicts_for(self, conflicts, focus_widget=getattr(self, "tree_control_accounts", None)):
                return

        names = self._control_account_name_lookup(accounts)
        entries: list[tuple[str, str]] = []
        skipped = 0
        for account in accounts:
            code = self._mapped_a07_code_for_account(account)
            name = names.get(account, "")
            if not code or not name:
                skipped += 1
                continue
            entries.append((code, name))

        if not entries:
            self._notify_inline(
                "Fant ingen mappede kontoer med A07-kode og kontonavn aa laere av.",
                focus_widget=getattr(self, "tree_control_accounts", None),
            )
            return

        try:
            batch_result = append_a07_rule_keywords(entries, exclude=exclude)
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-regler:\n{exc}")
            return
        learned = [(result.code, result.term, bool(result.changed)) for result in batch_result.results]

        try:
            payroll_classification.invalidate_runtime_caches()
        except Exception:
            pass

        removed_count = 0
        if remove_mapping:
            remover = getattr(self, "_remove_mapping_accounts_checked", None)
            removed = (
                remover(
                    accounts,
                    focus_widget=getattr(self, "tree_control_accounts", None),
                    refresh="none",
                    source_label="Fjernet mapping fra",
                )
                if callable(remover)
                else []
            )
            removed_count = len(removed)

        try:
            self._refresh_all()
        except Exception:
            self._refresh_core(focus_code=learned[0][0])
        notify_admin = getattr(self, "_notify_a07_rule_learning_changed", None)
        if callable(notify_admin):
            try:
                notify_admin()
            except Exception:
                pass

        changed_count = sum(1 for _code, _name, changed in learned if changed)
        action = "ekskludert fra" if exclude else "lagt til som alias for"
        if remove_mapping:
            self.status_var.set(
                f"{changed_count} kontonavn {action} A07-regel, {removed_count} mapping(er) fjernet."
            )
        else:
            self.status_var.set(f"{changed_count} kontonavn {action} A07-regel.")
        if skipped:
            self.status_var.set(f"{self.status_var.get()} Hoppet over {skipped}.")

    def _append_selected_control_account_names_to_a07_alias(self) -> None:
        self._learn_selected_control_account_names(exclude=False, remove_mapping=False)

    def _exclude_selected_control_account_names_from_a07_code(self) -> None:
        self._learn_selected_control_account_names(exclude=True, remove_mapping=False)

    def _remove_selected_control_accounts_and_exclude_alias(self) -> None:
        self._learn_selected_control_account_names(exclude=True, remove_mapping=True)

    def _selected_control_account_learning_context(self) -> dict[str, object]:
        accounts_getter = getattr(self, "_selected_control_account_ids", None)
        try:
            accounts = accounts_getter() if callable(accounts_getter) else []
        except Exception:
            accounts = []
        accounts = [str(account or "").strip() for account in accounts if str(account or "").strip()]
        if not accounts:
            return {"enabled": False, "code_label": "A07-kode", "accounts": []}
        name_lookup = getattr(self, "_control_account_name_lookup", None)
        try:
            names = name_lookup(accounts) if callable(name_lookup) else {}
        except Exception:
            names = {}
        code_getter = getattr(self, "_mapped_a07_code_for_account", None)
        pairs: list[tuple[str, str, str]] = []
        codes: list[str] = []
        for account in accounts:
            try:
                code = str(code_getter(account) if callable(code_getter) else "").strip()
            except Exception:
                code = ""
            name = str((names or {}).get(account) or "").strip()
            if code and name:
                pairs.append((account, code, name))
                if code not in codes:
                    codes.append(code)
        if len(codes) == 1:
            code_label = codes[0]
        elif len(codes) > 1:
            code_label = "valgte A07-koder"
        else:
            code_label = "A07-kode"
        return {
            "enabled": bool(pairs),
            "code_label": code_label,
            "accounts": accounts,
            "pairs": pairs,
        }

    def _assign_selected_control_mapping(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            selected_group_getter = getattr(self, "_selected_rf1022_group", None)
            try:
                group_id = selected_group_getter() if callable(selected_group_getter) else ""
            except Exception:
                group_id = ""
            self._assign_accounts_to_rf1022_group(accounts, group_id, source_label="RF-1022-mapping")
            return
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return
        conflicts = _locked_mapping_conflicts_for(self, accounts, target_code=code)
        if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
            return

        try:
            assigned = apply_manual_mapping_choices(self.workspace.mapping, accounts, code)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_mapping_account(assigned[0])
            count = len(assigned)
            if autosaved:
                self.status_var.set(f"Tildelte {count} konto(er) til {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Tildelte {count} konto(er) til {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke tildele konto til kode:\n{exc}")

    def _run_selected_control_gl_action(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            selected_group_getter = getattr(self, "_selected_rf1022_group", None)
            try:
                group_id = selected_group_getter() if callable(selected_group_getter) else ""
            except Exception:
                group_id = ""
            if group_id:
                self._assign_accounts_to_rf1022_group(accounts, group_id, source_label="RF-1022-mapping")
                return
            try:
                self.tree_a07.focus_set()
            except Exception:
                pass
            self.status_var.set("Velg en RF-1022-post til hoyre for du tildeler kontoer fra GL-listen.")
            return
        if self._selected_control_code():
            self._assign_selected_control_mapping()
            return
        try:
            self.tree_a07.focus_set()
        except Exception:
            pass
        self.status_var.set("Velg en A07-kode til hoyre for du tildeler kontoer fra GL-listen.")

    def _clear_selected_control_mapping(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        remover = getattr(self, "_remove_mapping_accounts_checked", None)
        if callable(remover):
            remover(
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            )
        else:
            A07PageMappingActionsMixin._remove_mapping_accounts_checked(
                self,
                accounts,
                focus_widget=self.tree_control_gl,
                refresh="core",
                source_label="Fjernet kode fra",
            )

    def _drop_unmapped_on_control(self, event: tk.Event | None = None) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            return

        try:
            code = self._tree_iid_from_event(self.tree_a07, event)
            if not code:
                return
            self.tree_a07.selection_set(code)
            self.tree_a07.focus(code)
            self.tree_a07.see(code)
            if work_level == "rf1022":
                self._assign_accounts_to_rf1022_group(accounts, code, source_label="Drag-and-drop mot RF-1022")
                return
            conflicts = _locked_mapping_conflicts_for(self, accounts, target_code=code)
            if _notify_locked_conflicts_for(self, conflicts, focus_widget=self.tree_a07):
                return
            if len(accounts) == 1:
                self._apply_account_code_mapping(accounts[0], code, source_label="Drag-and-drop")
            else:
                assigned = apply_manual_mapping_choices(self.workspace.mapping, accounts, code)
                autosaved = self._autosave_mapping()
                self._refresh_core(focus_code=code)
                self._focus_control_code(code)
                self._focus_mapping_account(assigned[0])
                if autosaved:
                    self.status_var.set(
                        f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code} og lagret i klientmappen."
                    )
                else:
                    self.status_var.set(f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code}.")
                self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fullfore drag-and-drop-mapping:\n{exc}")
        finally:
            self._clear_control_drag_state()

    def _apply_best_suggestion_for_selected_code(self) -> None:
        code = self._selected_control_code()
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
            return
        ensure_display = getattr(self, "_ensure_suggestion_display_fields", None)
        if callable(ensure_display):
            suggestions_df = ensure_display()
        else:
            suggestions_df = getattr(getattr(self, "workspace", None), "suggestions", None)
            if not isinstance(suggestions_df, pd.DataFrame):
                suggestions_df = _empty_suggestions_df()
        best_row = best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=_locked_codes_for(self),
        )
        if code is None or best_row is None:
            self._notify_inline("Fant ikke et forslag for valgt kode.", focus_widget=self.tree_a07)
            return
        if not bool(best_row.get("WithinTolerance", False)):
            self._notify_inline(
                "Beste forslag er utenfor toleranse. Kontroller detaljene eller map manuelt.",
                focus_widget=self.tree_control_suggestions,
            )
            return
        if not a07_suggestion_is_strict_auto(best_row):
            reason = str(best_row.get("SuggestionGuardrailReason") or "").strip()
            suffix = f" ({reason})" if reason else ""
            self._notify_inline(
                f"Beste forslag er ikke trygt nok for automatisk bruk{suffix}. Kontroller eller map manuelt.",
                focus_widget=self.tree_control_suggestions,
            )
            return

        try:
            apply_suggestion_to_mapping(self.workspace.mapping, best_row)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Beste forslag brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Beste forslag brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke beste forslag:\n{exc}")

    def _apply_history_for_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_a07)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if not accounts:
            self._notify_inline("Fant ingen trygg historikk Ã¥ bruke for valgt kode.", focus_widget=self.tree_a07)
            return
        if not code or not accounts:
            messagebox.showinfo("A07", "Fant ingen trygg historikk Ã¥ bruke for valgt kode.")
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Historikk brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Historikk brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke historikk for valgt kode:\n{exc}")

    def _run_selected_control_action(self) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            group_id = str(getattr(self, "_selected_rf1022_group", lambda: None)() or "").strip()
            if not group_id:
                return
            self._select_support_tab_key("suggestions")
            try:
                self._refresh_suggestions_tree()
            except Exception:
                pass
            return
        code = self._selected_control_code()
        if not code:
            return
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker automatikk.", focus_widget=self.tree_a07)
            return

        overview_row = None
        if self.a07_overview_df is not None and not self.a07_overview_df.empty:
            matches = self.a07_overview_df.loc[self.a07_overview_df["Kode"].astype(str).str.strip() == code]
            if not matches.empty:
                overview_row = matches.iloc[0]

        status = str((overview_row.get("Status") if overview_row is not None else "") or "").strip()
        if status in {"OK", "Ekskludert"}:
            return

        current_accounts = accounts_for_code(self._effective_mapping(), code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if history_accounts:
            self._apply_history_for_selected_code()
            return

        suggestions_df = self._ensure_suggestion_display_fields()
        best_row = best_suggestion_row_for_code(
            suggestions_df,
            code,
            locked_codes=_locked_codes_for(self),
        )
        if best_row is not None and a07_suggestion_is_strict_auto(best_row):
            self._apply_best_suggestion_for_selected_code()
            return

        fallback = build_smartmapping_fallback(
            code=code,
            current_accounts=current_accounts,
            history_accounts=history_accounts,
            best_row=best_row,
        )
        self._select_support_tab_key(fallback.preferred_tab)
        if fallback.preferred_tab == "suggestions":
            self._select_best_suggestion_row_for_code(code)
        elif fallback.preferred_tab == "history":
            try:
                self._set_tree_selection(self.tree_history, code)
            except Exception:
                pass
        elif fallback.preferred_tab == "mapping" and current_accounts:
            try:
                self._set_tree_selection(self.tree_control_gl, current_accounts[0])
            except Exception:
                pass
        try:
            self.entry_control_gl_filter.focus_set()
        except Exception:
            pass
        self.status_var.set(fallback.message)

    def _apply_safe_history_mappings(self) -> tuple[int, int]:
        applied_codes = 0
        applied_accounts = 0
        effective_mapping = self._effective_mapping()
        effective_previous_mapping = self._effective_previous_mapping()
        codes = select_safe_history_codes(self.history_compare_df)
        for code in codes:
            if code in _locked_codes_for(self):
                continue
            accounts = safe_previous_accounts_for_code(
                code,
                mapping_current=effective_mapping,
                mapping_previous=effective_previous_mapping,
                gl_df=self.workspace.gl_df,
            )
            if not accounts:
                continue

            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            after_accounts = {
                account
                for account, mapped_code in self.workspace.mapping.items()
                if str(mapped_code).strip() and before.get(str(account).strip()) != str(mapped_code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)

        return applied_codes, applied_accounts

    def _apply_safe_suggestions(self) -> tuple[int, int]:
        applied_codes = 0
        applied_accounts = 0
        row_indexes = select_batch_suggestion_rows(
            self.workspace.suggestions,
            self._effective_mapping(),
            min_score=0.85,
            locked_codes=_locked_codes_for(self),
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            code = str(row.get("Kode") or "").strip()
            if code in _locked_codes_for(self):
                continue
            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            after_accounts = {
                account
                for account, code in self.workspace.mapping.items()
                if str(code).strip() and before.get(str(account).strip()) != str(code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)
        return applied_codes, applied_accounts

    def _apply_magic_wand_suggestions(
        self,
        unresolved_code_values: Sequence[object] | None = None,
    ) -> tuple[int, int, int]:
        unresolved_codes_list = [
            str(code).strip()
            for code in (unresolved_code_values or ())
            if str(code).strip()
        ]
        applied_codes = 0
        applied_accounts = 0
        applied_code_values: set[str] = set()
        row_indexes = select_magic_wand_suggestion_rows(
            self.workspace.suggestions,
            self._effective_mapping(),
            unresolved_codes=unresolved_codes_list,
            locked_codes=_locked_codes_for(self),
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            code = str(row.get("Kode") or "").strip()
            if code in _locked_codes_for(self):
                continue
            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            after_accounts = {
                account
                for account, mapped_code in self.workspace.mapping.items()
                if str(mapped_code).strip() and before.get(str(account).strip()) != str(mapped_code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)
            if code:
                applied_code_values.add(code)

        skipped_codes = max(0, len(set(unresolved_codes_list)) - len(applied_code_values))
        return applied_codes, applied_accounts, skipped_codes

    def _magic_match_clicked(self) -> None:
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/år før du kjører trygg auto-matching.",
                focus_widget=self,
            )
            return

        try:
            self._apply_rf1022_candidate_suggestions()
        except Exception as exc:
            messagebox.showerror("A07", f"Trygg auto-matching kunne ikke fullføre:\n{exc}")

    def _open_manual_mapping_clicked(
        self,
        initial_account: str | None = None,
        initial_code: str | None = None,
    ) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/Ã¥r for Ã¥ lage mapping.",
                focus_widget=self,
            )
            return

        account_options = build_gl_picker_options(self.workspace.gl_df, basis_col=self.workspace.basis_col)
        code_options = build_a07_picker_options(self.workspace.a07_df)
        if not account_options or not code_options:
            self._notify_inline("Fant ikke nok data til Ã¥ bygge avansert mapping.", focus_widget=self)
            return

        initial_account, initial_code = self._manual_mapping_defaults(
            preferred_account=initial_account,
            preferred_code=initial_code,
        )
        choice = open_manual_mapping_dialog(
            self,
            account_options=account_options,
            code_options=code_options,
            initial_account=initial_account,
            initial_code=initial_code,
            title="Ny eller rediger A07-mapping",
        )
        if choice is None:
            return

        try:
            self._apply_account_code_mapping(choice[0], choice[1], source_label="Mapping satt")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mappingen:\n{exc}")

    def _map_selected_unmapped(self) -> None:
        selection = self.tree_unmapped.selection()
        if not selection:
            self._notify_inline("Velg en umappet konto fÃ¸rst.", focus_widget=self.tree_unmapped)
            return

        self._open_manual_mapping_clicked()

    def _apply_selected_suggestion(self) -> None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        if work_level == "rf1022":
            self._apply_selected_rf1022_candidate()
            return
        row = self._selected_suggestion_row()
        if row is None:
            if self.workspace.suggestions is None or self.workspace.suggestions.empty:
                self._notify_inline("Det finnes ingen forslag Ã¥ bruke.", focus_widget=self.tree_a07)
            else:
                self._notify_inline("Velg et forslag fÃ¸rst.", focus_widget=self.tree_control_suggestions)
            return
        if self.workspace.suggestions is None or self.workspace.suggestions.empty:
            self._notify_inline("Det finnes ingen forslag Ã¥ bruke.", focus_widget=self.tree_a07)
            return

        try:
            code = str(row.get("Kode") or "").strip() or self._selected_control_code()
            if code in _locked_codes_for(self):
                self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
                return
            if code.startswith("A07_GROUP:"):
                self._notify_inline(
                    "A07-grupper er satt i avansert/legacy-modus og kan ikke brukes med trygg auto.",
                    focus_widget=self.tree_control_suggestions,
                )
                return
            if not a07_suggestion_is_strict_auto(row):
                reason = str(row.get("SuggestionGuardrailReason") or "").strip()
                suffix = f" ({reason})" if reason else ""
                self._notify_inline(
                    f"Valgt forslag er ikke trygt nok for automatisk bruk{suffix}. Bruk manuell/avansert mapping.",
                    focus_widget=self.tree_control_suggestions,
                )
                return
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            autosaved = self._autosave_mapping()
            self._refresh_core(focus_code=code)
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set("Valgt forslag er brukt i mappingen og lagret i klientmappen.")
            else:
                self.status_var.set("Valgt forslag er brukt i mappingen.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt forslag:\n{exc}")

    def _apply_selected_history_mapping(self) -> None:
        selection = self.tree_history.selection()
        if not selection:
            self._notify_inline("Velg en historikkrad fÃ¸rst.", focus_widget=self.tree_history)
            return

        code = self._selected_code_from_tree(self.tree_history)
        if code in _locked_codes_for(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_history)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if not code or not accounts:
            self._notify_inline(
                "Valgt historikk kan ikke brukes direkte. Kontoene mÃ¥ finnes i Ã¥r og ikke kollidere med annen mapping.",
                focus_widget=self.tree_history,
            )
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core(focus_code=code)
            self._focus_mapping_account(accounts[0])
            if autosaved:
                self.status_var.set(
                    f"Historisk mapping brukt for {code} ({', '.join(accounts)}) og lagret i klientmappen."
                )
            else:
                self.status_var.set(f"Historisk mapping brukt for {code} ({', '.join(accounts)}).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt historikk:\n{exc}")

    def _apply_batch_history_mappings(self) -> None:
        if self.history_compare_df is None or self.history_compare_df.empty:
            self._notify_inline("Det finnes ingen historikk Ã¥ bruke.", focus_widget=self.tree_a07)
            return

        codes = select_safe_history_codes(self.history_compare_df)
        if not codes:
            self._notify_inline(
                "Fant ingen sikre historikkmappinger. Kontoene mÃ¥ finnes i Ã¥r og ikke kollidere med annen mapping.",
                focus_widget=self.tree_a07,
            )
            return

        try:
            applied_codes, applied_accounts = self._apply_safe_history_mappings()

            if applied_codes == 0:
                self._notify_inline(
                    "Ingen historikkmappinger kunne brukes etter konfliktkontroll mot dagens mapping.",
                    focus_widget=self.tree_a07,
                )
                return

            autosaved = self._autosave_mapping(source="history", confidence=0.9)
            self._refresh_core()
            if autosaved:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer) og lagret endringen."
                )
            else:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer)."
                )
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke sikre historikkmappinger:\n{exc}")

    def _apply_batch_suggestions_clicked(self) -> None:
        self._apply_rf1022_candidate_suggestions()

    def _remove_selected_mapping(self) -> None:
        selection = self.tree_mapping.selection()
        if not selection:
            self._notify_inline("Velg en eller flere mapping-rader fÃ¸rst.", focus_widget=self.tree_mapping)
            return
        self._remove_mapping_accounts_checked(
            selection,
            focus_widget=self.tree_mapping,
            refresh="core",
            source_label="Fjernet mapping fra",
        )
        return
