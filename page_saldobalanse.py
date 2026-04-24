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
import saldobalanse_actions
import saldobalanse_columns
import saldobalanse_detail_panel
import saldobalanse_payroll_mode
import session

from src.shared.columns_vocabulary import active_year_from_session, heading
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


from saldobalanse_payload import (
    ALL_COLUMNS,
    PAYROLL_COLUMNS,
    DEFAULT_VISIBLE_COLUMNS,
    DEFAULT_COLUMN_ORDER,
    NUMERIC_COLUMNS,
    COLUMN_WIDTHS,
    MAPPING_STATUS_LABELS,
    SOURCE_LABELS,
    FILTER_ALL,
    PRESET_CUSTOM,
    WORK_MODE_STANDARD,
    WORK_MODE_PAYROLL,
    WORK_MODE_OPTIONS,
    PAYROLL_QUEUE_OPTIONS,
    COLUMN_PRESETS,
    PRESET_OPTIONS,
    MAPPING_STATUS_OPTIONS,
    SOURCE_OPTIONS,
    PAYROLL_SCOPE_OPTIONS,
    STALE_OWNED_COMPANY_LABEL,
    SaldobalansePayload,
    SaldobalanseBasePayload,
    _suggestion_grid_value,
    _normalize_classification_field_value,
    _suggested_update_for_item,
    _ordered_columns_for_visible,
    _preset_name_for_visible_columns,
    _resolve_sb_views,
    _resolve_sb_columns,
    _normalize_sb_frame,
    _first_text_value,
    _build_hb_counts,
    _load_mapping_issues,
    _load_group_mapping,
    _group_label,
    _session_year,
    _load_account_profile_document_only,
    _load_payroll_context,
    _resolve_payroll_usage_features,
    _top_payroll_suggestion,
    _payroll_problem_text,
    _suggestion_reason_text,
    _payroll_match_basis_text,
    _rf1022_treatment_text,
    _load_owned_company_name_map,
    _format_owned_company_display,
    _decorate_with_detail_class_and_ownership,
    _apply_blank_payroll_columns,
    _decorate_with_payroll_columns,
    _build_decorated_base_payload,
    build_saldobalanse_payload,
    build_saldobalanse_df,
)


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
        # Retired widgets — kept as None so saldobalanse_payroll_mode.sync_mode_ui
        # and other callers that do ``getattr(page, "_xxx", None)`` continue to
        # find a stable attribute rather than raising. The underlying Tk vars
        # (`_var_work_mode`, `_var_preset`, `_var_payroll_scope`, `_var_only_unmapped`,
        # `_var_only_with_ao`) still exist so A07's focus_payroll_accounts can
        # drive state programmatically even without UI controls.
        self._btn_columns = None
        self._btn_refresh = None
        self._chk_only_unmapped = None
        self._chk_only_with_ao = None
        self._lbl_mode = None
        self._cmb_mode = None
        self._lbl_preset = None
        self._cmb_preset = None
        self._lbl_payroll_scope = None
        self._cmb_payroll_scope = None
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
        # Sjekk om klient/år faktisk har endret seg — i så fall må også
        # modul-level cacher (gruppe-mapping, mapping-issues, owned-company)
        # tømmes fordi de er per klient/år.
        try:
            new_client, new_year = self._client_context()
        except Exception:
            new_client, new_year = None, None
        prev_context = getattr(self, "_last_session_context", None)
        current_context = (str(new_client or ""), str(new_year or ""))
        if prev_context != current_context:
            SaldobalansePage._invalidate_module_caches(self)
            self._last_session_context = current_context

        SaldobalansePage._invalidate_payload_cache(self)
        # Oppdater tree-headings med nytt aktivt år
        self._apply_vocabulary_labels()
        try:
            self.after(100, self.refresh)
        except Exception:
            self.refresh()

    def _apply_vocabulary_labels(self) -> None:
        """Oppdater tree-headings med aktivt år fra felles vokabular.
        Brukes på saldo-kolonner (IB, UB, Endring, …); fane-spesifikke
        kolonne-IDs returneres uendret av heading()."""
        try:
            yr = active_year_from_session()
            for col in ALL_COLUMNS:
                self._tree.heading(col, text=heading(col, year=yr))
        except Exception:
            pass

    def _is_payroll_mode(self) -> bool:
        return saldobalanse_payroll_mode.is_payroll_mode(self)


    def focus_payroll_accounts(
        self,
        accounts: list[str] | tuple[str, ...] | None = None,
        *,
        payroll_scope: str = FILTER_ALL,
    ) -> None:
        saldobalanse_payroll_mode.focus_payroll_accounts(self, accounts, payroll_scope=payroll_scope)


    def _leave_payroll_mode(self) -> None:
        saldobalanse_payroll_mode.leave_payroll_mode(self)


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

        self._chk_include_zero = ttk.Checkbutton(
            top,
            text="Vis null",
            variable=self._var_include_zero,
            command=self.refresh,
        )
        self._chk_include_zero.grid(row=0, column=3, sticky="w", padx=(0, 8))

        self._lbl_mapping_status = ttk.Label(top, text="Mapping:")
        self._lbl_mapping_status.grid(row=1, column=0, sticky="w", pady=(6, 0))
        cmb_mapping = ttk.Combobox(
            top,
            textvariable=self._var_mapping_status,
            values=MAPPING_STATUS_OPTIONS,
            state="readonly",
            width=14,
        )
        cmb_mapping.grid(row=1, column=1, sticky="w", padx=(6, 8), pady=(6, 0))
        self._cmb_mapping_status = cmb_mapping

        self._lbl_source = ttk.Label(top, text="Kilde:")
        self._lbl_source.grid(row=1, column=2, sticky="w", pady=(6, 0))
        cmb_source = ttk.Combobox(
            top,
            textvariable=self._var_source,
            values=SOURCE_OPTIONS,
            state="readonly",
            width=10,
        )
        cmb_source.grid(row=1, column=3, sticky="w", padx=(0, 8), pady=(6, 0))
        self._cmb_source = cmb_source

        self._btn_map = ttk.Button(top, text="Map valgt konto...", command=self._map_selected_account)
        self._btn_map.grid(row=1, column=4, padx=(0, 8), pady=(6, 0))
        self._btn_export = ttk.Button(top, text="Eksporter Excel...", command=self._export_current_view_to_excel)
        self._btn_export.grid(row=1, column=5, pady=(6, 0))

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
        # Kolonnedefinisjoner, sortering, kolonne-meny, bredde-persist
        # og dra-rekkefølge håndteres av ManagedTreeview. Kolonne-preset-
        # bytte går via ``self._managed_tree.column_manager.set_visible_columns``.
        # Gammel Saldobalanse-preference-nøkler auto-migreres til
        # ``ui.saldobalanse.*`` første gang siden lastes.
        from ui_managed_treeview import ManagedTreeview
        from saldobalanse_payload import build_column_specs
        self._managed_tree = ManagedTreeview(
            self._tree,
            view_id="saldobalanse",
            column_specs=build_column_specs(active_year_from_session()),
            pref_prefix="ui",
            on_body_right_click=self._open_context_menu,
            legacy_pref_keys={
                "visible_cols": "saldobalanse.columns.visible",
                "column_order": "saldobalanse.columns.order",
            },
        )

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
            # <Button-3> håndteres av ManagedTreeview: header → kolonne-meny,
            # body → ``on_body_right_click=self._open_context_menu``.
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
            cmb_mapping.bind("<<ComboboxSelected>>", lambda _event: self._schedule_refresh(80), add="+")
            cmb_source.bind("<<ComboboxSelected>>", lambda _event: self._schedule_refresh(80), add="+")
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
        saldobalanse_payroll_mode.save_non_payroll_filters(self)


    def _reset_hidden_filters_for_payroll_mode(self) -> None:
        saldobalanse_payroll_mode.reset_hidden_filters_for_payroll_mode(self)


    def _restore_non_payroll_filters(self) -> None:
        saldobalanse_payroll_mode.restore_non_payroll_filters(self)


    def _payroll_intro_sections(self) -> dict[str, str]:
        return saldobalanse_detail_panel.payroll_intro_sections(self)


    def _selection_detail_sections(
        self,
        items: list[classification_workspace.ClassificationWorkspaceItem],
        *,
        button_label: str,
    ) -> dict[str, str]:
        return saldobalanse_detail_panel.selection_detail_sections(self, items, button_label=button_label)


    def _on_work_mode_changed(self, *, refresh: bool = True) -> None:
        saldobalanse_payroll_mode.on_work_mode_changed(self, refresh=refresh)


    def _sync_mode_ui(self) -> None:
        saldobalanse_payroll_mode.sync_mode_ui(self)


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
        saldobalanse_detail_panel.refresh_detail_panel(self)


    def _refresh_selection_totals(self) -> None:
        saldobalanse_detail_panel.refresh_selection_totals(self)


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
        saldobalanse_columns.load_column_preferences(self)

    def _persist_column_preferences(self) -> None:
        saldobalanse_columns.persist_column_preferences(self)

    def _apply_visible_columns(self) -> None:
        saldobalanse_columns.apply_visible_columns(self)

    def _sync_preset_var(self) -> None:
        saldobalanse_columns.sync_preset_var(self)

    def _on_preset_changed(self) -> None:
        saldobalanse_columns.on_preset_changed(self)

    def _open_column_chooser(self) -> None:
        saldobalanse_columns.open_column_chooser(self)

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
        return saldobalanse_payroll_mode.ensure_payroll_context_loaded(self)


    def _ensure_payroll_usage_features_loaded(self) -> dict[str, Any]:
        return saldobalanse_payroll_mode.ensure_payroll_usage_features_loaded(self)


    def _payroll_result_for_account(self, account_no: str) -> payroll_classification.PayrollSuggestionResult | None:
        return saldobalanse_payroll_mode.payroll_result_for_account(self, account_no)


    def _history_profile_for_account(self, account_no: str) -> Any:
        return saldobalanse_payroll_mode.history_profile_for_account(self, account_no)


    def _suspicious_profile_issue_for_account(
        self,
        account_no: str,
        *,
        account_name: str = "",
        profile: Any = None,
    ) -> str:
        return saldobalanse_payroll_mode.suspicious_profile_issue_for_account(self, account_no, account_name=account_name, profile=profile)


    def _has_history_for_selected_accounts(self) -> bool:
        return saldobalanse_payroll_mode.has_history_for_selected_accounts(self)


    def _has_strict_suggestions_for_selected_accounts(self) -> bool:
        return saldobalanse_payroll_mode.has_strict_suggestions_for_selected_accounts(self)


    def _next_action_for_account(
        self,
        account_no: str,
        *,
        account_name: str = "",
        result: payroll_classification.PayrollSuggestionResult | None,
        profile: Any,
    ) -> str:
        return saldobalanse_payroll_mode.next_action_for_account(self, account_no, account_name=account_name, result=result, profile=profile)


    def _selected_payroll_detail_text(self) -> str:
        return saldobalanse_detail_panel.selected_payroll_detail_text(self)


    def _sync_status_text(self) -> None:
        saldobalanse_detail_panel.sync_status_text(self)


    def _set_status_detail(self, text: str) -> None:
        saldobalanse_detail_panel.set_status_detail(self, text)


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

        Tømmer også payroll-context-cachen (_profile_document, _history_document,
        _profile_catalog). Uten dette ville set_owned_company / set_detail_class
        ikke vises før app-restart fordi ensure_payroll_context_loaded
        returnerer cached document som ikke har de nye verdiene.
        """
        try:
            self._base_payload_cache = None
            self._base_payload_cache_key = None
        except Exception:
            pass
        # Tving re-lesing av profil-dokument fra disk — dette er kilden
        # for owned_company_orgnr og detail_class_id i payload-decorate.
        try:
            self._profile_document = None
            self._history_document = None
            self._profile_catalog = None
            self._payroll_context_key = None
        except Exception:
            pass
        # NB: tidligere tømte vi også modul-level cacher her (group_mapping,
        # mapping_issues, owned_company). Det ble fjernet fordi denne
        # metoden kalles ved hver tab-aktivering via refresh_from_session,
        # som eliminerte cache-effekten (3s+ per SB-åpning). Modul-cacher
        # invalideres nå kun ved _hard_refresh (Oppfrisk) og ved
        # klassifiserings-endring (context-meny-handlers + Avansert
        # klassifisering). Se _invalidate_module_caches().

    def _invalidate_module_caches(self) -> None:
        """Tøm modul-level cacher i saldobalanse_payload.

        Kalles ved eksplisitte endringer i underliggende data:
        - Oppfrisk-knappen (_hard_refresh)
        - Lagret endring i klassifisering/A07/gruppe/owned-company
        - Klient-bytte (senere kan denne koble seg på session-change)
        """
        try:
            saldobalanse_payload._invalidate_group_mapping_cache()
            saldobalanse_payload._invalidate_mapping_issues_cache()
            saldobalanse_payload._invalidate_owned_company_cache()
        except Exception:
            pass

    def _hard_refresh(self) -> None:
        """Invalidate cache and refresh — used by Oppfrisk and programmatic reloads."""
        SaldobalansePage._invalidate_payload_cache(self)
        SaldobalansePage._invalidate_module_caches(self)
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
        # Send timing-events til monitoring-subsystemet (src/monitoring).
        # Tre events per refresh: base, postprocess, render. Sett
        # UTVALG_PROFILE_SB=1 (eller UTVALG_PROFILE=sb) for å se dem på
        # stderr i tillegg til persistent event-logg.
        try:
            from src.monitoring.perf import record_event as _record_event
            _meta_base = {"rows": int(len(df.index)), "cache": "hit" if _base_cache_hit else "rebuilt"}
            _record_event("sb.refresh.base", (_t_base_end - _t_start) * 1000.0, meta=_meta_base)
            _record_event("sb.refresh.postprocess", (_t_postprocess_end - _t_base_end) * 1000.0)
            _record_event("sb.refresh.render", (_t_render_end - _t_postprocess_end) * 1000.0,
                          meta={"rows": int(len(df.index))})
            _record_event("sb.refresh", (_t_render_end - _t_start) * 1000.0,
                          meta={"rows": int(len(df.index)), "cache": "hit" if _base_cache_hit else "rebuilt"})
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

        missing_cols = {col for col in ALL_COLUMNS if col not in df.columns}
        row_count = int(len(df.index))
        if row_count == 0:
            return

        def _series_as_str_list(column: str) -> list[str]:
            if column not in df.columns:
                return [""] * row_count
            try:
                return df[column].astype(str).tolist()
            except Exception:
                return [""] * row_count

        konto_series = _series_as_str_list("Konto")
        mapping_series = _series_as_str_list("Mappingstatus")
        status_series = _series_as_str_list("Status")
        locked_series = _series_as_str_list("Låst")

        # Pre-format every column's values up front so the per-row loop
        # only has to zip the already-string lists together. This skips
        # 34-lookup-per-row dict access plus format dispatch inside the
        # hot loop — the bulk of Python-side render time on a full page.
        empty_col: list[str] = [""] * row_count
        formatted: dict[str, list[str]] = {}
        for col in ALL_COLUMNS:
            if col in missing_cols:
                formatted[col] = empty_col
                continue
            try:
                raw = df[col].tolist()
            except Exception:
                formatted[col] = empty_col
                continue
            if col in amount_cols:
                formatted[col] = [fmt_amount(v) for v in raw]
            elif col == "Antall":
                out: list[str] = []
                for v in raw:
                    if v is None or (isinstance(v, float) and v != v):  # NaN check
                        out.append("")
                        continue
                    try:
                        ivalue = int(v or 0)
                    except Exception:
                        ivalue = 0
                    out.append(format_int_no(v) if ivalue else "")
                formatted[col] = out
            elif col == "Regnr":
                out = []
                for v in raw:
                    if v is None or (isinstance(v, float) and v != v):
                        out.append("")
                        continue
                    try:
                        out.append(str(int(v)))
                    except Exception:
                        out.append("")
                formatted[col] = out
            else:
                formatted[col] = ["" if v is None else str(v or "") for v in raw]

        # Pre-resolve per-row tag tuples so the insert loop stays thin.
        def _row_tags(mapping_status: str, payroll_status: str, locked_raw: str) -> tuple[str, ...]:
            if locked_raw and locked_raw.strip():
                return ("payroll_locked",)
            if payroll_status in unclear_set:
                return ("payroll_unclear",)
            if payroll_status in suggestion_set:
                return ("payroll_suggestion",)
            if mapping_status in problem_set:
                return ("problem",)
            if mapping_status == "Overstyrt":
                return ("override",)
            return ()

        tag_list = [
            _row_tags(mapping_series[i], status_series[i], locked_series[i])
            for i in range(row_count)
        ]
        column_lists = [formatted[col] for col in ALL_COLUMNS]

        # Pre-beregn alle (iid, values, tags)-tuples før Tk-loopen. Sparer
        # per-rad generator-kall + tuple-konstruksjon inne i hot loop.
        values_per_row = list(zip(*column_lists))

        insert = tree.insert
        for idx in range(row_count):
            try:
                insert(
                    "",
                    "end",
                    iid=konto_series[idx],
                    values=values_per_row[idx],
                    tags=tag_list[idx],
                )
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
        saldobalanse_actions.map_selected_account(self)

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
        return saldobalanse_actions.build_feedback_events(self, updates, action_type=action_type)

    def _persist_payroll_updates(
        self,
        updates: dict[str, dict[str, object]],
        *,
        source: str = "manual",
        confidence: float | None = 1.0,
        status_text: str | None = None,
        feedback_action: str | None = None,
    ) -> None:
        saldobalanse_actions.persist_payroll_updates(
            self,
            updates,
            source=source,
            confidence=confidence,
            status_text=status_text,
            feedback_action=feedback_action,
        )

    def _edit_detail_class_for_selected_accounts(self) -> None:
        saldobalanse_actions.edit_detail_class_for_selected_accounts(self)

    def _edit_owned_company_for_selected_accounts(self) -> None:
        saldobalanse_actions.edit_owned_company_for_selected_accounts(self)

    def _prompt_detail_class_choice(
        self,
        catalog: list[Any],
        current_id: str,
    ) -> str | None:
        return saldobalanse_actions.prompt_detail_class_choice(self, catalog, current_id)

    def _prompt_owned_company_choice(
        self,
        ownership_map: dict[str, str],
        current_orgnr: str,
    ) -> str | None:
        return saldobalanse_actions.prompt_owned_company_choice(self, ownership_map, current_orgnr)

    def _open_advanced_classification(self) -> None:
        saldobalanse_actions.open_advanced_classification(self)

    def _assign_a07_to_selected_accounts(self, code: str) -> None:
        saldobalanse_actions.assign_a07_to_selected_accounts(self, code)

    def _assign_group_to_selected_accounts(self, group_id: str) -> None:
        saldobalanse_actions.assign_group_to_selected_accounts(self, group_id)

    def _add_tag_to_selected_accounts(self, tag_id: str) -> None:
        saldobalanse_actions.add_tag_to_selected_accounts(self, tag_id)

    def _remove_tag_from_selected_accounts(self, tag_id: str) -> None:
        saldobalanse_actions.remove_tag_from_selected_accounts(self, tag_id)

    def _append_selected_account_name_to_a07_alias(self, code: str) -> None:
        saldobalanse_actions.append_selected_account_name_to_a07_alias(self, code)

    def _append_selected_account_to_a07_boost(self, code: str) -> None:
        saldobalanse_actions.append_selected_account_to_a07_boost(self, code)

    def _append_selected_account_name_to_rf1022_alias(self, group_id: str) -> None:
        saldobalanse_actions.append_selected_account_name_to_rf1022_alias(self, group_id)

    def _after_rule_learning_saved(self, message: str) -> None:
        saldobalanse_actions.after_rule_learning_saved(self, message)

    def _apply_history_to_selected_accounts(self) -> None:
        saldobalanse_actions.apply_history_to_selected_accounts(self)

    def _apply_best_suggestions_to_selected_accounts(self) -> None:
        saldobalanse_actions.apply_best_suggestions_to_selected_accounts(self)

    def _toggle_lock_selected_accounts(self) -> None:
        saldobalanse_actions.toggle_lock_selected_accounts(self)

    def _clear_selected_payroll_fields(self) -> None:
        saldobalanse_actions.clear_selected_payroll_fields(self)

    def _clear_selected_suspicious_payroll_fields(self) -> None:
        saldobalanse_actions.clear_selected_suspicious_payroll_fields(self)

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
            alias_menu.add_cascade(label="Kontonavn -> A07-alias", menu=a07_alias_menu)
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
