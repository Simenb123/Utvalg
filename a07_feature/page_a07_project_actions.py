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
    filter_control_visible_codes_df,
    filter_suggestions_df,
    reconcile_tree_tag,
    rf1022_post_for_group,
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

from .page_a07_constants import _MAPPING_COLUMNS, _MATCHER_SETTINGS_DEFAULTS
from .page_a07_dialogs import _format_aliases_editor, _parse_aliases_editor
from .page_a07_env import filedialog, messagebox, session, simpledialog
from .page_a07_runtime_helpers import _clean_context_value

class A07PageProjectActionsMixin:
    def _current_project_state(self) -> dict[str, object]:
        return {
            "basis_col": self.workspace.basis_col,
            "selected_code": self._selected_control_code(),
            "selected_group": self._selected_group_id(),
        }

    def _autosave_workspace_state(self) -> bool:
        client, year = self._session_context(session)
        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        if not client_s or not year_s:
            return False

        self.groups_path = default_a07_groups_path(client_s, year_s)
        self.locks_path = default_a07_locks_path(client_s, year_s)
        self.project_path = default_a07_project_path(client_s, year_s)
        save_a07_groups(self.workspace.groups, self.groups_path)
        save_locks(self.locks_path, self.workspace.locks)
        save_project_state(self.project_path, self._current_project_state())
        self._context_snapshot = self._current_context_snapshot(client_s, year_s)
        return True

    def _autosave_mapping(
        self,
        *,
        source: str = "manual",
        confidence: float | None = 1.0,
    ) -> bool:
        client, year = self._session_context(session)
        save_path = resolve_autosave_mapping_path(
            self.mapping_path,
            a07_path=self.a07_path,
            client=client,
            year=year,
        )
        if save_path is None:
            return False

        saved = save_mapping(
            save_path,
            self.workspace.mapping,
            client=client,
            year=year,
            source=source,
            confidence=confidence,
            shadow_to_profiles=True,
        )
        self.mapping_path = Path(saved)
        self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
        self._autosave_workspace_state()
        self._context_snapshot = self._current_context_snapshot(client, year)
        return True

    def _load_a07_clicked(self) -> None:
        client, year = self._session_context(session)
        initialdir = str(get_a07_workspace_dir(client, year))
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 JSON",
            initialdir=initialdir,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_a07_source_to_workspace(path, client=client, year=year)
            self.workspace.source_a07_df = self._load_a07_source_cached(stored_path)
            self.workspace.a07_df = self.workspace.source_a07_df.copy()
            self.a07_path = Path(stored_path)
            self.a07_path_var.set(f"A07: {self.a07_path}")
            self._context_snapshot = self._current_context_snapshot(client, year)
            self._refresh_core(reason="load_a07")

            if stored_path != Path(path):
                self.status_var.set(
                    f"Lastet A07 fra {Path(path).name} og lagret kopi i klientmappen."
                )
            else:
                self.status_var.set(f"Lastet A07 fra {self.a07_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese A07-filen:\n{exc}")

    def _load_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        default_path = suggest_default_mapping_path(self.a07_path, client=client, year=year)

        if default_path.exists() or (_clean_context_value(client) and _clean_context_value(year)):
            path = default_path
        else:
            path_str = filedialog.askopenfilename(
                parent=self,
                title="Velg mapping JSON",
                initialdir=str(default_path.parent),
                initialfile=default_path.name,
                filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
            )
            if not path_str:
                return
            path = Path(path_str)

        try:
            self.workspace.mapping = self._load_mapping_file_cached(
                path,
                client=client,
                year=year,
            )
            self.mapping_path = Path(path)
            if client and year:
                try:
                    self.groups_path = default_a07_groups_path(client, year)
                    self.workspace.groups = load_a07_groups(self.groups_path)
                except Exception:
                    self.workspace.groups = {}
                try:
                    self.locks_path = default_a07_locks_path(client, year)
                    self.workspace.locks = load_locks(self.locks_path)
                except Exception:
                    self.workspace.locks = set()
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self._refresh_core()
            self.status_var.set(f"Lastet mapping fra {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese mapping-filen:\n{exc}")

    def _save_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        default_path = suggest_default_mapping_path(self.a07_path, client=client, year=year)

        out_path: Path
        if _clean_context_value(client) and _clean_context_value(year):
            out_path = default_path
        else:
            out_path_str = filedialog.asksaveasfilename(
                parent=self,
                title="Lagre mapping",
                defaultextension=".json",
                initialdir=str(default_path.parent),
                initialfile=default_path.name,
                filetypes=[("JSON", "*.json")],
            )
            if not out_path_str:
                return
            out_path = Path(out_path_str)

        try:
            saved = save_mapping(
                out_path,
                self.workspace.mapping,
                client=client,
                year=year,
                shadow_to_profiles=True,
            )
            self.mapping_path = Path(saved)
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self._autosave_workspace_state()
            self.status_var.set(f"Lagret mapping til {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mapping:\n{exc}")

    def _on_basis_changed(self) -> None:
        basis = self._selected_basis()
        if basis == self.workspace.basis_col:
            return
        self.workspace.basis_col = basis
        self._refresh_core(focus_code=self._selected_control_code())
        self._autosave_workspace_state()
        self.status_var.set(f"A07 bruker nÃ¥ basis {basis}.")

    def _create_group_from_selection(self) -> None:
        codes = self._groupable_selected_control_codes()
        self._create_group_from_codes(codes)

    def _create_group_from_codes(
        self,
        codes: Sequence[str],
        *,
        prompt_for_name: bool = False,
    ) -> str | None:
        codes = list(dict.fromkeys(str(code).strip() for code in (codes or ()) if str(code).strip()))
        if len(codes) < 2:
            self._notify_inline("Marker minst to A07-koder for Ã¥ opprette en gruppe.", focus_widget=self.tree_a07)
            return None

        default_name = self._default_group_name(codes)
        group_name = default_name
        if prompt_for_name:
            name = simpledialog.askstring("A07-gruppe", "Navn pÃ¥ gruppen:", parent=self, initialvalue=default_name)
            if name is None:
                return None
            group_name = str(name).strip() or default_name

        group_id = self._next_group_id(codes)
        self.workspace.groups[group_id] = A07Group(
            group_id=group_id,
            group_name=group_name,
            member_codes=codes,
        )
        self._autosave_workspace_state()
        self._refresh_core(focus_code=group_id)
        self._focus_control_code(group_id)
        self.status_var.set(f"Opprettet A07-gruppe {group_name} ({group_id}).")
        return group_id

    def _rename_selected_group(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            self._notify_inline("Velg en A07-gruppe fÃ¸rst.", focus_widget=self.tree_groups)
            return
        group = self.workspace.groups.get(group_id)
        if group is None:
            self._notify_inline("Fant ikke valgt A07-gruppe.", focus_widget=self.tree_groups)
            return
        current_name = str(group.group_name or group_id).strip() or group_id
        name = simpledialog.askstring("A07-gruppe", "Nytt navn pÃ¥ gruppen:", parent=self, initialvalue=current_name)
        if name is None:
            return
        updated_name = str(name).strip() or current_name
        if updated_name == current_name:
            return
        group.group_name = updated_name
        self._autosave_workspace_state()
        self._refresh_core(focus_code=group_id)
        self._focus_control_code(group_id)
        self.status_var.set(f"Oppdaterte gruppenavn til {updated_name}.")

    def _remove_selected_group(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            self._notify_inline("Velg en A07-gruppe fÃ¸rst.", focus_widget=self.tree_groups)
            return
        mapping_resolver = getattr(self, "_effective_mapping", None)
        if callable(mapping_resolver):
            effective_mapping = mapping_resolver()
        else:
            effective_mapping = dict(getattr(self.workspace, "mapping", {}) or {})
        in_use = [
            str(account).strip()
            for account, code in (effective_mapping or {}).items()
            if str(code or "").strip() == group_id and str(account).strip()
        ]
        if in_use:
            account_label = "konto" if len(in_use) == 1 else "kontoer"
            self._notify_inline(
                f"Kan ikke oppløse gruppe som fortsatt brukes i mapping ({len(in_use)} {account_label}). Fjern eller flytt mapping først.",
                focus_widget=self.tree_groups,
            )
            self._focus_control_code(group_id)
            return
        self.workspace.groups.pop(group_id, None)
        self.workspace.locks.discard(group_id)
        self._autosave_workspace_state()
        self._refresh_core()
        self.status_var.set(f"OpplÃ¸ste A07-gruppe {group_id}.")

    def _on_group_selection_changed(self) -> None:
        sync_groups_panel_visibility = getattr(self, "_sync_groups_panel_visibility", None)
        if callable(sync_groups_panel_visibility):
            sync_groups_panel_visibility()
        self._focus_selected_group_code()

    def _focus_selected_group_code(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            return
        self._focus_control_code(group_id)

    def _lock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe Ã¥ lÃ¥se fÃ¸rst.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.add(code)
        self._autosave_workspace_state()
        self._refresh_core(focus_code=code)
        self._focus_control_code(code)
        self.status_var.set(f"LÃ¥ste {code}.")

    def _unlock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe Ã¥ lÃ¥se opp fÃ¸rst.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.discard(code)
        self._autosave_workspace_state()
        self._refresh_core(focus_code=code)
        self._focus_control_code(code)
        self.status_var.set(f"LÃ¥ste opp {code}.")

    def _open_source_overview(self) -> None:
        open_source_overview(self)

    def _open_mapping_overview(self) -> None:
        open_mapping_overview(self, _MAPPING_COLUMNS)

    def _open_a07_rulebook_admin(self) -> None:
        app = getattr(session, "APP", None)
        admin_page = getattr(app, "page_admin", None)
        notebook = getattr(app, "nb", None)
        if admin_page is not None and notebook is not None:
            try:
                notebook.select(admin_page)
            except Exception:
                pass
            show_rulebook = getattr(admin_page, "show_a07_rulebook", None)
            if callable(show_rulebook):
                try:
                    show_rulebook()
                    self.status_var.set("Åpnet Admin > A07-regler.")
                    return
                except Exception:
                    pass
        self._open_matcher_admin()

    def _open_matcher_admin(self) -> None:
        self._open_legacy_matcher_admin()

    def _open_legacy_matcher_admin(self) -> None:
        open_matcher_admin(
            self,
            matcher_settings_defaults=_MATCHER_SETTINGS_DEFAULTS,
            format_aliases_editor=_format_aliases_editor,
            parse_aliases_editor=_parse_aliases_editor,
        )

    def _load_rulebook_clicked(self) -> None:
        client, year = self._session_context(session)
        current_path = resolve_rulebook_path(client, year) or default_global_rulebook_path()
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 rulebook",
            initialdir=str(current_path.parent),
            initialfile=current_path.name,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_rulebook_to_storage(path)
            self.rulebook_path = stored_path
            self.rulebook_path_var.set(f"Rulebook: {stored_path}")
            self._refresh_core(focus_code=self._selected_control_code())
            self.status_var.set(f"Rulebook lastet og lagret til {stored_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese rulebook:\n{exc}")
