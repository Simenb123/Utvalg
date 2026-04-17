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
from a07_feature import control_status as a07_control_status
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

from . import page_a07_shared as _shared
from .page_a07_shared import *  # noqa: F401,F403

class A07PageRf1022Mixin:
    def _export_clicked(self) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du eksporterer.",
                focus_widget=self,
            )
            return

        client, year = self._session_context(session)
        default_path = default_a07_export_path(client, year)
        out_path_str = filedialog.asksaveasfilename(
            parent=self,
            title="Eksporter A07-kontroll",
            defaultextension=".xlsx",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            filetypes=[("Excel", "*.xlsx")],
        )
        if not out_path_str:
            return

        try:
            control_statement_df = self.control_statement_df.copy(deep=True)
            exported = export_a07_workbook(
                out_path_str,
                overview_df=self.a07_overview_df,
                reconcile_df=self.reconcile_df,
                mapping_df=self.mapping_df,
                control_statement_df=control_statement_df,
                suggestions_df=self.workspace.suggestions,
                unmapped_df=self.unmapped_df,
            )
            self.status_var.set(f"Eksporterte A07-kontroll til {Path(exported).name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke eksportere A07-kontroll:\n{exc}")

    def _selected_rf1022_view(self) -> str:
        state = getattr(self, "_rf1022_state", None) or {}
        view_label_var = state.get("view_label_var")
        view_var = state.get("view_var")
        try:
            label_value = view_label_var.get() if view_label_var is not None else ""
        except Exception:
            label_value = ""
        try:
            stored_value = view_var.get() if view_var is not None else ""
        except Exception:
            stored_value = ""
        return normalize_control_statement_view(
            label_value or stored_value or CONTROL_STATEMENT_VIEW_PAYROLL
        )

    def _sync_rf1022_view_vars(self, view: object) -> str:
        state = getattr(self, "_rf1022_state", None) or {}
        view_key = normalize_control_statement_view(view)
        view_label = _CONTROL_STATEMENT_VIEW_LABELS.get(
            view_key,
            _CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL],
        )
        view_var = state.get("view_var")
        view_label_var = state.get("view_label_var")
        try:
            if view_var is not None:
                view_var.set(view_key)
        except Exception:
            pass
        try:
            if view_label_var is not None:
                view_label_var.set(view_label)
        except Exception:
            pass
        return view_key

    def _on_rf1022_view_changed(self) -> None:
        self._sync_rf1022_view_vars(self._selected_rf1022_view())
        self._refresh_rf1022_window()

    def _build_rf1022_source_df(self, *, view: object | None = None) -> pd.DataFrame:
        view_key = self._sync_rf1022_view_vars(view or self._selected_rf1022_view())
        base_df = getattr(self, "control_statement_base_df", None)
        if isinstance(base_df, pd.DataFrame) and not base_df.empty:
            return filter_control_statement_df(base_df, view=view_key)
        if self.workspace.gl_df is None or self.workspace.gl_df.empty:
            return _empty_control_statement_df()

        client, year = self._session_context(session)
        client_s = _clean_context_value(client)
        if not client_s:
            return _empty_control_statement_df()

        include_flag = control_statement_view_requires_unclassified(view_key)
        return filter_control_statement_df(
            build_control_statement_export_df(
                client=client_s,
                year=year,
                gl_df=self.workspace.gl_df,
                reconcile_df=self.reconcile_df,
                mapping_current=self._effective_mapping(),
                include_unclassified=include_flag,
            ),
            view=view_key,
        )

    def _build_rf1022_tag_totals(self) -> dict[str, float]:
        if self.workspace.gl_df is None or self.workspace.gl_df.empty:
            return {}
        document = self._load_rf1022_profile_document()
        if document is None:
            return {}
        return payroll_classification.rf1022_tag_totals(
            self.workspace.gl_df,
            document,
            basis_col=self.workspace.basis_col,
        )

    def _load_rf1022_profile_document(self):
        state = getattr(self, "_rf1022_state", None) or {}
        cached = state.get("profile_document")
        if cached is not None:
            return cached
        client, year = self._session_context(session)
        client_s = _clean_context_value(client)
        if not client_s:
            return None
        year_i: int | None = None
        year_s = _clean_context_value(year)
        if year_s:
            try:
                year_i = int(year_s)
            except Exception:
                year_i = None
        try:
            document = _account_profile_api_for_a07().load_document(client=client_s, year=year_i)
        except Exception:
            document = None
        state["profile_document"] = document
        if getattr(self, "_rf1022_state", None) is not None:
            self._rf1022_state["profile_document"] = document
        return document

    def _selected_rf1022_group_id(self) -> str | None:
        state = getattr(self, "_rf1022_state", None) or {}
        tree = state.get("overview_tree")
        if tree is None:
            return None
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        return str(selection[0] or "").strip() or None

    def _selected_rf1022_account(self) -> str | None:
        state = getattr(self, "_rf1022_state", None) or {}
        tree = state.get("accounts_tree")
        if tree is None:
            return None
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        return str(selection[0] or "").strip() or None

    def _focus_rf1022_selected_account_in_gl(self) -> None:
        account = self._selected_rf1022_account()
        if not account:
            return
        self._focus_mapping_account(account)

    def _refresh_rf1022_accounts(self) -> None:
        state = getattr(self, "_rf1022_state", None) or {}
        accounts_tree = state.get("accounts_tree")
        accounts_var = state.get("accounts_var")
        source_df = state.get("source_df")
        if accounts_tree is None:
            return

        group_id = self._selected_rf1022_group_id()
        accounts_df = build_rf1022_accounts_df(
            self.control_gl_df,
            source_df if isinstance(source_df, pd.DataFrame) else _empty_control_statement_df(),
            group_id,
            basis_col=self.workspace.basis_col,
            profile_document=self._load_rf1022_profile_document(),
        )
        self._fill_tree(
            accounts_tree,
            accounts_df,
            _RF1022_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )

        if accounts_var is not None:
            if not group_id:
                accounts_var.set("Velg en post for aa se kontoene bak raden.")
            else:
                try:
                    row_df = source_df.loc[source_df["Gruppe"].astype(str).str.strip() == str(group_id).strip()]
                except Exception:
                    row_df = pd.DataFrame()
                if row_df is not None and not row_df.empty:
                    row = row_df.iloc[0]
                    amount = self._format_value(row.get(self.workspace.basis_col), self.workspace.basis_col)
                    accounts_var.set(f"{row.get('Navn') or group_id} | Kontoer {len(accounts_df)} | GL {amount or '-'}")
                else:
                    accounts_var.set(f"Kontoer {len(accounts_df)}")

    def _refresh_rf1022_window(self) -> None:
        state = getattr(self, "_rf1022_state", None)
        win = getattr(self, "_rf1022_window", None)
        if not state or win is None:
            return
        try:
            if not win.winfo_exists():
                self._rf1022_window = None
                self._rf1022_state = None
                return
        except Exception:
            self._rf1022_window = None
            self._rf1022_state = None
            return

        view_key = self._selected_rf1022_view()
        source_df = self._build_rf1022_source_df(view=view_key)
        overview_df = build_rf1022_statement_df(source_df, basis_col=self.workspace.basis_col)
        state["source_df"] = source_df
        state["overview_df"] = overview_df

        overview_tree = state.get("overview_tree")
        summary_var = state.get("summary_var")
        if overview_tree is not None:
            previous_group = self._selected_rf1022_group_id()
            self._fill_tree(
                overview_tree,
                overview_df,
                _RF1022_OVERVIEW_COLUMNS,
                iid_column="GroupId",
                row_tag_fn=lambda row: control_tree_tag(row.get("Status")),
            )
            try:
                children = overview_tree.get_children()
            except Exception:
                children = ()
            target = None
            if previous_group and previous_group in children:
                target = previous_group
            elif children:
                target = str(children[0]).strip() or None
            if target:
                self._set_tree_selection(overview_tree, target)

        if summary_var is not None:
            summary_var.set(
                build_rf1022_statement_summary(
                    overview_df,
                    tag_totals=self._build_rf1022_tag_totals(),
                )
            )

        self._refresh_rf1022_accounts()

    def _open_rf1022_window(self) -> None:
        existing = self._rf1022_window
        if existing is not None:
            try:
                if existing.winfo_exists():
                    self._refresh_rf1022_window()
                    existing.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("RF-1022 spesifikasjon")
        win.geometry("1540x820")
        self._rf1022_window = win

        header = ttk.Frame(win, padding=10)
        header.pack(fill="x")
        summary_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=summary_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)

        view_var = tk.StringVar(value=CONTROL_STATEMENT_VIEW_PAYROLL)
        view_label_var = tk.StringVar(value=_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        ttk.Button(header, text="Lukk", command=win.destroy).pack(side="right")
        ttk.Label(header, text="Visning:").pack(side="right", padx=(8, 4))
        view_widget = ttk.Combobox(
            header,
            textvariable=view_label_var,
            state="readonly",
            width=16,
            values=[_CONTROL_STATEMENT_VIEW_LABELS[key] for key in _CONTROL_STATEMENT_VIEW_LABELS],
        )
        view_widget.pack(side="right")
        view_widget.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])

        body = ttk.Panedwindow(win, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        upper = ttk.Frame(body)
        lower = ttk.Frame(body)
        body.add(upper, weight=3)
        body.add(lower, weight=2)

        overview_tree = self._build_tree_tab(upper, _RF1022_OVERVIEW_COLUMNS)
        accounts_top = ttk.Frame(lower, padding=(0, 0, 0, 6))
        accounts_top.pack(fill="x")
        accounts_var = tk.StringVar(value="Velg en post for aa se kontoene bak raden.")
        ttk.Label(accounts_top, textvariable=accounts_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(accounts_top, text="Vis i GL", command=self._focus_rf1022_selected_account_in_gl).pack(side="right")
        accounts_tree = self._build_tree_tab(lower, _RF1022_ACCOUNT_COLUMNS)

        view_widget.bind("<<ComboboxSelected>>", lambda _event: self._on_rf1022_view_changed(), add="+")
        overview_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_rf1022_accounts(), add="+")
        accounts_tree.bind("<Double-1>", lambda _event: self._focus_rf1022_selected_account_in_gl(), add="+")
        accounts_tree.bind("<Return>", lambda _event: self._focus_rf1022_selected_account_in_gl(), add="+")

        self._rf1022_state = {
            "overview_tree": overview_tree,
            "accounts_tree": accounts_tree,
            "summary_var": summary_var,
            "accounts_var": accounts_var,
            "view_var": view_var,
            "view_label_var": view_label_var,
            "view_widget": view_widget,
            "source_df": _empty_control_statement_df(),
            "overview_df": _empty_rf1022_overview_df(),
            "profile_document": None,
        }

        def _on_close() -> None:
            try:
                win.destroy()
            finally:
                self._rf1022_window = None
                self._rf1022_state = None

        win.protocol("WM_DELETE_WINDOW", _on_close)
        self._refresh_rf1022_window()
