"""Thin shell for the consolidation workspace."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore
    simpledialog = None  # type: ignore
    ttk = None  # type: ignore

import pandas as pd

import session
from ..backend import storage, tb_import
from ..backend.control_rows import append_control_rows
from ..backend.models import (
    AssociateAdjustmentRow,
    AssociateCase,
    CompanyTB,
    ConsolidationProject,
    EliminationSuggestion,
)
from .common import (
    DETAIL_LINE_COLUMN_SPECS as _DETAIL_LINE_COLUMN_SPECS,
    DETAIL_TB_COLUMN_SPECS as _DETAIL_TB_COLUMN_SPECS,
    build_detail_meta_text as _build_detail_meta_text,
    fmt_no as _fmt_no,
    format_count_label as _format_count_label,
    format_filtered_count_label as _format_filtered_count_label,
    is_line_basis_company as _is_line_basis_company,
)
from . import associate as _assoc
from . import company_actions as _company_actions
from . import elim as _elim
from . import elim_ui as _elim_ui
from . import fx as _fx_ctx
from . import imports as _import_ctx
from . import project as _project_ctx
from . import run as _run_ctx
from . import shell_ui as _shell_ui
from . import view as _view_ctx
from treeview_column_manager import TreeviewColumnManager

try:
    from ui_treeview_sort import enable_treeview_sorting
except Exception:  # pragma: no cover
    enable_treeview_sorting = None  # type: ignore

logger = logging.getLogger(__name__)


class ConsolidationPage(ttk.Frame):  # type: ignore[misc]
    _RESULT_MODE_KEYS = {
        "Valgt selskap": "company",
        "Konsolidert": "consolidated",
        "Per selskap": "per_company",
    }
    _KURS_COLS = {"Kurs"}

    def __init__(self, master=None):
        self._tk_ok = True
        try:
            super().__init__(master)
        except Exception:
            self._tk_ok = False
            self._status_var = None
            return

        self._project: Optional[ConsolidationProject] = None
        self._company_tbs: dict[str, pd.DataFrame] = {}
        self._company_line_bases: dict[str, pd.DataFrame] = {}
        self._mapped_tbs: dict[str, pd.DataFrame] = {}
        self._mapping_review_accounts: dict[str, set[str]] = {}
        self._mapping_review_details: dict[str, list[str]] = {}
        self._result_df: Optional[pd.DataFrame] = None
        self._last_run_result = None
        self._readiness_report = None
        self._current_detail_cid: Optional[str] = None
        self._suggestions: list[EliminationSuggestion] = []
        self._associate_manual_rows: list[AssociateAdjustmentRow] = []
        self._current_associate_case_id: Optional[str] = None
        self._intervals: Optional[pd.DataFrame] = None
        self._regnskapslinjer: Optional[pd.DataFrame] = None
        self._regnr_to_name: dict[int, str] = {}
        self._status_var = tk.StringVar(value="Velg klient og aar for aa starte.")
        self._readiness_status_var = tk.StringVar(value="")
        self._build_ui()

    def _build_ui(self) -> None:
        _shell_ui.build_ui(self)

    def _select_left_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        _shell_ui.select_left_tab(self, fallback_index, tab_ref_attr)

    def _select_right_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        _shell_ui.select_right_tab(self, fallback_index, tab_ref_attr)

    def _select_elim_tab(self, fallback_index: int, tab_ref_attr: str) -> None:
        _shell_ui.select_elim_tab(self, fallback_index, tab_ref_attr)

    def _is_associate_workspace_active(self) -> bool:
        return _shell_ui.is_associate_workspace_active(self)

    def _update_workspace_layout(self) -> None:
        _shell_ui.update_workspace_layout(self)

    def _on_left_tab_changed(self, _event=None) -> None:
        _shell_ui.on_left_tab_changed(self, _event)

    def _on_elim_tab_changed(self, _event=None) -> None:
        _shell_ui.on_elim_tab_changed(self, _event)

    def _make_company_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        return _shell_ui.make_company_tree(self, parent)

    def _build_controls_tab(self, parent: ttk.Frame) -> None:
        _shell_ui.build_controls_tab(self, parent)

    def _make_detail_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        return _shell_ui.make_detail_tree(self, parent)

    def _build_result_tab(self, parent: ttk.Frame) -> None:
        _shell_ui.build_result_tab(self, parent)

    def _build_grunnlag_tab(self, parent: ttk.Frame) -> None:
        _shell_ui.build_grunnlag_tab(self, parent)

    def _on_result_line_select(self, event=None) -> None:
        _shell_ui.on_result_line_select(self, event)

    def _populate_grunnlag(self, regnr: int, *, is_sumpost: bool = False) -> None:
        _view_ctx.populate_grunnlag(self, regnr, is_sumpost=is_sumpost, fmt_no=_fmt_no)

    def _build_elimination_tab(self, parent: ttk.Frame) -> None:
        _elim_ui.build_elimination_tab(self, parent)

    def _build_enkel_elim_tab(self, parent: ttk.Frame) -> None:
        _elim_ui.build_enkel_elim_tab(self, parent)

    def _build_forslag_tab(self, parent: ttk.Frame) -> None:
        _elim_ui.build_forslag_tab(self, parent)

    def _build_journaler_tab(self, parent: ttk.Frame) -> None:
        _elim_ui.build_journaler_tab(self, parent)

    def _build_valuta_tab(self, parent: ttk.Frame) -> None:
        _fx_ctx.build_valuta_tab(self, parent)

    def _build_associate_cases_tab(self, parent: ttk.Frame) -> None:
        _assoc.build_associate_cases_tab(self, parent)

    def _refresh_associate_investor_choices(self) -> None:
        _assoc.refresh_investor_choices(self)

    def _associate_parse_float(self, raw: object) -> float:
        return _assoc._parse_float(raw)

    def _associate_parse_int(self, raw: object) -> int:
        return _assoc._parse_int(raw)

    def _associate_regnr_display(self, raw: object) -> str:
        return _assoc._regnr_display(self, raw)

    def _refresh_associate_mapping_summary(self) -> None:
        _assoc._refresh_mapping_summary(self)

    def _set_associate_mapping_visibility(self, visible: bool) -> None:
        _assoc._set_mapping_visibility(self, visible)

    def _on_toggle_associate_mapping(self) -> None:
        _assoc.on_toggle_associate_mapping(self)

    def _on_reset_associate_mapping(self) -> None:
        _assoc.on_reset_associate_mapping(self)

    def _find_duplicate_company_for_associate(self, case):
        return _assoc._find_duplicate_company(self, case)

    def _build_associate_next_step_text(self, case):
        return _assoc._build_next_step_text(self, case)

    def _refresh_associate_case_actions(self, case) -> None:
        _assoc.refresh_associate_case_actions(self, case)

    def _current_associate_case(self):
        return _assoc.current_associate_case(self)

    def _clear_associate_case_form(self) -> None:
        _assoc.clear_associate_case_form(self)

    def _load_default_line_mapping_into_ui(self) -> None:
        _assoc.load_default_line_mapping_into_ui(self)

    def _populate_associate_case_form(self, case) -> None:
        _assoc.populate_associate_case_form(self, case)

    def _build_associate_case_from_form(self, *, existing=None):
        return _assoc._build_case_from_form(self, existing=existing)

    def _refresh_associate_adjustment_tree(self) -> None:
        _assoc.refresh_associate_adjustment_tree(self)

    def _refresh_associate_case_tree(self) -> None:
        _assoc.refresh_associate_case_tree(self)

    def _refresh_associate_case_views(self, case) -> None:
        _assoc.refresh_associate_case_views(self, case)

    def _on_new_associate_case(self) -> None:
        _assoc.on_new_associate_case(self)

    def _on_associate_case_selected(self, _event=None) -> None:
        _assoc.on_associate_case_selected(self, _event)

    def _on_save_associate_case(self) -> None:
        _assoc.on_save_associate_case(self)

    def _on_delete_associate_case(self) -> None:
        _assoc.on_delete_associate_case(self)

    def _on_generate_associate_journal(self) -> None:
        _assoc.on_generate_associate_journal(self)

    def _on_open_associate_journal(self) -> None:
        _assoc.on_open_associate_journal(self)

    def _open_associate_case_by_id(self, case_id: str) -> None:
        _assoc.open_associate_case_by_id(self, case_id)

    def _on_add_associate_adjustment(self) -> None:
        _assoc.on_add_associate_adjustment(self)

    def _on_edit_associate_adjustment(self) -> None:
        _assoc.on_edit_associate_adjustment(self)

    def _on_delete_associate_adjustment(self) -> None:
        _assoc.on_delete_associate_adjustment(self)

    def _apply_associate_field_suggestions(self, suggestions, *, source_mode: str, source_ref: str) -> int:
        return _assoc._apply_field_suggestions(self, suggestions, source_mode=source_mode, source_ref=source_ref)

    def _on_import_associate_line_support(self) -> None:
        _assoc.on_import_associate_line_support(self)

    def _on_import_associate_pdf_support(self) -> None:
        _assoc.on_import_associate_pdf_support(self)

    def refresh_from_session(self, sess: object) -> None:
        _project_ctx.refresh_from_session(self, sess, storage_module=storage)

    def _ensure_project(self) -> ConsolidationProject:
        return _project_ctx.ensure_project(self, session_module=session, storage_module=storage)

    def _update_session_tb_button(self, sess: object) -> None:
        _project_ctx.update_session_tb_button(self, sess)

    def _resolve_active_client_tb(self) -> Optional[tuple[pd.DataFrame, str, str]]:
        return _project_ctx.resolve_active_client_tb(self, session_module=session)

    def _on_use_session_tb(self) -> None:
        _project_ctx.on_use_session_tb(self, storage_module=storage, simpledialog_module=simpledialog, messagebox_module=messagebox)

    def _load_company_tbs(self) -> None:
        _project_ctx.load_company_tbs(self, storage_module=storage)

    def _load_company_line_bases(self) -> None:
        _project_ctx.load_company_line_bases(self, storage_module=storage)

    def _load_analyse_parent_overrides(self) -> dict[str, int]:
        return _project_ctx.load_analyse_parent_overrides(self)

    def _get_parent_override_deviation_details(self) -> list[str]:
        return _project_ctx.get_parent_override_deviation_details(self)

    def _get_effective_company_overrides(self, company_id: str) -> dict[str, int]:
        return _project_ctx.get_effective_company_overrides(self, company_id)

    def _get_effective_company_tb(self, company_id: str) -> pd.DataFrame | None:
        return _project_ctx.get_effective_company_tb(self, company_id)

    def _get_effective_company_basis(self, company_id: str) -> pd.DataFrame | None:
        return _project_ctx.get_effective_company_basis(self, company_id)

    def _get_effective_tbs(self) -> dict[str, pd.DataFrame]:
        return _project_ctx.get_effective_tbs(self)

    def _compute_mapping_status(self) -> None:
        _project_ctx.compute_mapping_status(self)

    def _update_status(self) -> None:
        if self._project is None:
            try:
                self._refresh_readiness()
            except Exception:
                pass
            return
        nc = len(self._project.companies)
        ne = len(self._project.eliminations)
        na = len(getattr(self._project, "associate_cases", []) or [])
        basis_modes = {"Regnskapslinjer" if _is_line_basis_company(company) else "TB" for company in self._project.companies}
        basis_label = " + ".join(sorted(basis_modes)) if basis_modes else "TB"
        last_run = ""
        if self._project.runs:
            from datetime import datetime
            last_run = f" | Siste run: {datetime.fromtimestamp(self._project.runs[-1].run_at).strftime('%H:%M')}"
        associate_text = f" | {na} tilknyttede" if na else ""
        self._status_var.set(f"{nc} selskaper | {ne} elimineringer{associate_text}{last_run}")
        try:
            self._lbl_statusbar.configure(text=f"Konsolidering | {self._project.client} / {self._project.year} | {basis_label}")
        except Exception:
            pass
        try:
            self._refresh_readiness()
        except Exception:
            pass

    def _split_unmapped_counts(self, company_id: str) -> tuple[int, int]:
        return _project_ctx.split_unmapped_counts(self, company_id)

    def _refresh_readiness(self) -> None:
        _project_ctx.refresh_readiness(self)

    def _refresh_controls_tree(self) -> None:
        _project_ctx.refresh_controls_tree(self)

    def _open_selected_readiness_issue(self) -> None:
        _project_ctx.open_selected_readiness_issue(self)

    def _refresh_company_tree(self) -> None:
        _company_actions.refresh_company_tree(self)

    def _refresh_journal_tree(self) -> None:
        _elim.refresh_journal_tree(self)

    def _refresh_elim_lines(self, journal) -> None:
        _elim.refresh_elim_lines(self, journal)

    def _configure_detail_tree_columns(self, *, line_basis: bool) -> None:
        _view_ctx.configure_detail_tree_columns(self, line_basis=line_basis, detail_tb_column_specs=_DETAIL_TB_COLUMN_SPECS, detail_line_column_specs=_DETAIL_LINE_COLUMN_SPECS)

    def _set_detail_context(self, company: CompanyTB | None, basis: pd.DataFrame | None) -> None:
        if hasattr(self, "_detail_meta_var"):
            self._detail_meta_var.set(_build_detail_meta_text(company, basis))

    def _show_company_detail(self, company_id: str) -> None:
        _view_ctx.show_company_detail(self, company_id, build_detail_meta_text=_build_detail_meta_text)

    def _populate_detail_tree(self, tb: pd.DataFrame, company_id: str) -> None:
        _view_ctx.populate_detail_tree(self, tb, company_id, fmt_no=_fmt_no, format_count_label=_format_count_label, format_filtered_count_label=_format_filtered_count_label)

    def _populate_line_basis_detail_tree(self, basis: pd.DataFrame) -> None:
        _view_ctx.populate_line_basis_detail_tree(self, basis, fmt_no=_fmt_no, format_count_label=_format_count_label, format_filtered_count_label=_format_filtered_count_label)

    def _on_detail_filter_changed(self) -> None:
        _view_ctx.on_detail_filter_changed(self)

    def _build_company_result(self, company_id: str) -> None:
        _view_ctx.build_company_result(self, company_id)

    def _build_regnskap_from_agg(self, agg: dict[int, float], col_name: str) -> pd.DataFrame | None:
        from src.shared.regnskap.mapping import compute_sumlinjer
        if self._regnskapslinjer is None:
            return None
        skeleton = self._regnskapslinjer[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
        skeleton["regnr"] = skeleton["regnr"].astype(int)
        result = skeleton.copy()
        leaf_mask = ~result["sumpost"]
        result[col_name] = result["regnr"].map(lambda regnr: agg.get(int(regnr), 0.0))
        result.loc[result["sumpost"], col_name] = 0.0
        base_values = {int(regnr): float(value) for regnr, value in zip(result.loc[leaf_mask, "regnr"], result.loc[leaf_mask, col_name])}
        all_values = compute_sumlinjer(base_values=base_values, regnskapslinjer=self._regnskapslinjer)
        result.loc[result["sumpost"], col_name] = result.loc[result["sumpost"], "regnr"].map(lambda regnr, values=all_values: float(values.get(int(regnr), 0.0)))
        return result.sort_values("regnr").reset_index(drop=True)

    def _on_ao_toggled(self) -> None:
        _run_ctx.on_ao_toggled(self)

    @property
    def _result_col_mgr(self) -> TreeviewColumnManager:
        mgrs = getattr(self, "_result_col_mgrs", None)
        if mgrs is None:
            raise AttributeError("_result_col_mgr")
        mode = self._result_mode_var.get() if getattr(self, "_result_mode_var", None) else "Valgt selskap"
        return mgrs[self._RESULT_MODE_KEYS.get(mode, "company")]

    def _on_result_mode_changed(self) -> None:
        _view_ctx.on_result_mode_changed(self)

    def _fx_cols_active(self) -> tuple[bool, bool, bool]:
        return _view_ctx.fx_cols_active(self)

    def _refresh_result_view(self) -> None:
        _view_ctx.refresh_result_view(self)

    def _ensure_consolidated_fx_cols(self, show_before: bool, show_effect: bool) -> pd.DataFrame:
        return _view_ctx.ensure_consolidated_fx_cols(self, show_before=show_before, show_effect=show_effect)

    def _get_per_company_columns(self, df: pd.DataFrame | None = None) -> list[str]:
        return _view_ctx.get_per_company_columns(self, df)

    def _show_empty_result(self, message: str = "") -> None:
        _view_ctx.show_empty_result(self, message)

    def _reset_result_tree_display_state(self) -> None:
        _view_ctx.reset_result_tree_display_state(self)

    def _populate_result_tree(self, result_df: pd.DataFrame, data_cols: list[str] | None = None) -> None:
        _view_ctx.populate_result_tree(self, result_df, data_cols=data_cols, fmt_no=_fmt_no, append_control_rows_fn=append_control_rows, enable_treeview_sorting_fn=enable_treeview_sorting, kurs_cols=self._KURS_COLS)

    def _compute_preview(self, draft_lines) -> None:
        _elim.compute_preview(self, draft_lines)

    def _clear_preview(self) -> None:
        _elim.clear_preview(self)

    def _show_result(self, result_df: pd.DataFrame) -> None:
        _view_ctx.show_result(self, result_df)

    def _ensure_consolidated_result(self) -> bool:
        return _view_ctx.ensure_consolidated_result(self)

    def _invalidate_run_cache(self) -> None:
        _run_ctx.invalidate_run_cache(self)

    def _rerun_consolidation(self) -> None:
        _run_ctx.rerun_consolidation(self)

    def _copy_tree_to_clipboard(self, tree: ttk.Treeview) -> None:
        _company_actions.copy_tree_to_clipboard(self, tree)

    def _on_show_unmapped(self) -> None:
        _view_ctx.on_show_unmapped(self)

    def _on_company_right_click(self, event) -> None:
        _company_actions.on_company_right_click(self, event)

    def _on_detail_right_click(self, event) -> None:
        _company_actions.on_detail_right_click(self, event)

    def _on_result_right_click(self, event) -> None:
        _company_actions.on_result_right_click(self, event)

    def _on_detail_double_click(self, event) -> None:
        _company_actions.on_detail_double_click(self, event)

    def _on_change_mapping(self) -> None:
        _company_actions.on_change_mapping(self)

    def _on_mapping_overrides_changed(self, company_id: str, new_overrides: dict[str, int]) -> None:
        _company_actions.on_mapping_overrides_changed(self, company_id, new_overrides)

    def _find_company_by_name(self, name: str) -> CompanyTB | None:
        return _import_ctx.find_company_by_name(self, name)

    def _on_import_selected_company_from_client_list(self) -> None:
        _import_ctx.on_import_selected_company_from_client_list(self, storage_module=storage, tb_import_module=tb_import, simpledialog_module=simpledialog, messagebox_module=messagebox)

    def _on_import_company_from_client_list(self) -> None:
        _import_ctx.on_import_company_from_client_list(self, storage_module=storage, tb_import_module=tb_import, simpledialog_module=simpledialog, messagebox_module=messagebox)

    def _import_company_from_client_list(self, *, target_company: CompanyTB | None = None) -> None:
        _import_ctx.import_company_from_client_list(self, target_company=target_company, storage_module=storage, tb_import_module=tb_import, simpledialog_module=simpledialog, messagebox_module=messagebox)

    def import_company_from_client_name(self, client_display: str, *, target_company_name: str | None = None, target_company: CompanyTB | None = None, silent: bool = False) -> CompanyTB | None:
        return _import_ctx.import_company_from_client_name(self, client_display, target_company_name=target_company_name, target_company=target_company, silent=silent, storage_module=storage, tb_import_module=tb_import, messagebox_module=messagebox)

    def create_or_update_associate_case_from_ar_relation(self, **kwargs) -> AssociateCase | None:
        return _assoc.create_or_update_associate_case_from_ar_relation(self, **kwargs)

    def import_companies_from_ar_batch(self, rows: list[dict[str, Any]]) -> list[CompanyTB | None]:
        return _import_ctx.import_companies_from_ar_batch(self, rows, storage_module=storage, tb_import_module=tb_import, messagebox_module=messagebox)

    def create_associate_cases_from_ar_batch(self, rows: list[dict[str, Any]], *, year: str | None = None) -> list[AssociateCase | None]:
        from src.pages.ar.backend.store import classify_relation_type
        results: list[AssociateCase | None] = []
        for row in rows:
            try:
                results.append(
                    self.create_or_update_associate_case_from_ar_relation(
                        company_name=str(row.get("company_name") or "").strip(),
                        company_orgnr=str(row.get("company_orgnr") or "").strip(),
                        ownership_pct=float(row.get("ownership_pct") or 0.0),
                        matched_client=str(row.get("matched_client") or "").strip(),
                        relation_type=str(row.get("relation_type") or "").strip() or classify_relation_type(float(row.get("ownership_pct") or 0.0)),
                        source_ref=f"AR {year}" if year else "AR batch",
                        note=str(row.get("note") or "").strip(),
                    )
                )
            except Exception:
                logger.exception("Batch-opprettelse tilknyttet feilet for %s", row.get("company_name"))
                results.append(None)
        return results

    def _on_reimport_company(self) -> None:
        _import_ctx.on_reimport_company(self, filedialog_module=filedialog, simpledialog_module=simpledialog, messagebox_module=messagebox, storage_module=storage, tb_import_module=tb_import)

    def _on_company_select(self, _event=None) -> None:
        _company_actions.on_company_select(self, _event)

    def _on_set_parent(self) -> None:
        _company_actions.on_set_parent(self)

    def _on_delete_company(self, _event=None) -> None:
        _company_actions.on_delete_company(self, _event)

    def _on_import_company(self) -> None:
        _import_ctx.on_import_company(self, filedialog_module=filedialog, simpledialog_module=simpledialog, messagebox_module=messagebox, storage_module=storage, tb_import_module=tb_import)

    def _ensure_line_import_config(self) -> bool:
        return _import_ctx.ensure_line_import_config(self, messagebox_module=messagebox)

    def _on_export_company_line_template(self) -> None:
        _import_ctx.on_export_company_line_template(self, filedialog_module=filedialog, messagebox_module=messagebox)

    def _on_import_company_lines(self) -> None:
        _import_ctx.on_import_company_lines(self, filedialog_module=filedialog, simpledialog_module=simpledialog, messagebox_module=messagebox, storage_module=storage)

    def _on_import_company_pdf(self) -> None:
        _import_ctx.on_import_company_pdf(self, filedialog_module=filedialog, simpledialog_module=simpledialog, messagebox_module=messagebox, storage_module=storage)

    def _import_saft_direct(self, path: str) -> None:
        _import_ctx.import_saft_direct(self, path, simpledialog_module=simpledialog, messagebox_module=messagebox, tb_import_module=tb_import, storage_module=storage)

    def _finalize_import(self, df: pd.DataFrame, name: str, source_path: Path, *, existing_company: CompanyTB | None = None, source_type: str | None = None, source_file: str | None = None) -> CompanyTB:
        return _import_ctx.finalize_import(self, df, name, source_path, existing_company=existing_company, source_type=source_type, source_file=source_file, storage_module=storage, tb_import_module=tb_import, messagebox_module=messagebox)

    def _finalize_line_basis_import(self, df: pd.DataFrame, name: str, source_path: Path, *, source_type: str, existing_company: CompanyTB | None = None) -> None:
        _import_ctx.finalize_line_basis_import(self, df, name, source_path, source_type=source_type, existing_company=existing_company, storage_module=storage, messagebox_module=messagebox)

    def _select_and_show_company(self, company_id: str) -> None:
        _company_actions.select_and_show_company(self, company_id)

    def _on_journal_select(self, _event=None) -> None:
        _elim.on_journal_select(self, _event)

    def _on_open_selected_associate_from_journal(self) -> None:
        _assoc.on_open_selected_associate_from_journal(self)

    def _populate_elim_combos(self) -> None:
        _elim.populate_elim_combos(self)

    def _parse_regnr_from_combo(self, val: str):
        return _elim._parse_regnr_from_combo(val)

    def _get_sum_foer_elim(self, regnr: int):
        return _elim.get_sum_foer_elim(self, regnr)

    def _on_elim_line_selected(self) -> None:
        _elim.on_elim_line_selected(self)

    def _on_elim_combo_filter(self, event=None) -> None:
        _elim.on_elim_combo_filter(self, event)

    def _on_elim_level_changed(self) -> None:
        _elim.on_elim_level_changed(self)

    def _on_use_result_rl(self) -> None:
        _elim.on_use_result_rl(self)

    def _ensure_elim_draft_voucher_no(self) -> int:
        return _elim.ensure_elim_draft_voucher_no(self)

    def _update_elim_draft_header(self) -> None:
        _elim.update_elim_draft_header(self)

    def _begin_new_elim_draft(self, reset_inputs: bool = True) -> None:
        _elim.begin_new_elim_draft(self, reset_inputs)

    def _load_journal_into_draft(self, journal, *, copy_mode: bool) -> None:
        _elim.load_journal_into_draft(self, journal, copy_mode=copy_mode)

    def _on_draft_add_line(self) -> None:
        _elim.on_draft_add_line(self)

    def _on_draft_edit_line(self) -> None:
        _elim.on_draft_edit_line(self)

    def _on_draft_remove_line(self) -> None:
        _elim.on_draft_remove_line(self)

    def _on_draft_clear(self) -> None:
        _elim.on_draft_clear(self)

    def _refresh_draft_tree(self) -> None:
        _elim.refresh_draft_tree(self)

    def _on_create_simple_elim(self) -> None:
        _elim.on_create_simple_elim(self)

    def _on_delete_simple_elim(self) -> None:
        _elim.on_delete_simple_elim(self)

    def _refresh_simple_elim_tree(self) -> None:
        _elim.refresh_simple_elim_tree(self)

    def _on_simple_elim_selected(self, _event=None) -> None:
        _elim.on_simple_elim_selected(self, _event)

    def _show_elim_detail(self, journal_id: str) -> None:
        _elim.show_elim_detail(self, journal_id)

    def _on_load_journal_to_draft(self) -> None:
        _elim.on_load_journal_to_draft(self)

    def _on_copy_journal_to_draft(self) -> None:
        _elim.on_copy_journal_to_draft(self)

    def _on_new_journal(self) -> None:
        _elim.on_new_journal(self)

    def _on_delete_journal(self) -> None:
        _elim.on_delete_journal(self)

    def _on_add_elim_line(self) -> None:
        _elim.on_add_elim_line(self)

    def _on_delete_elim_line(self) -> None:
        _elim.on_delete_elim_line(self)

    def _on_generate_suggestions(self) -> None:
        _elim.on_generate_suggestions(self)

    def _refresh_suggestion_tree(self) -> None:
        _elim.refresh_suggestion_tree(self)

    def _on_suggestion_select(self, _event=None) -> None:
        _elim.on_suggestion_select(self, _event)

    def _show_suggestion_detail(self, suggestion) -> None:
        _elim.show_suggestion_detail(self, suggestion)

    def _on_create_journal_from_suggestion(self) -> None:
        _elim.on_create_journal_from_suggestion(self)

    def _on_ignore_suggestion(self) -> None:
        _elim.on_ignore_suggestion(self)

    def _has_foreign_currency(self) -> bool:
        return _fx_ctx.has_foreign_currency(self)

    def _update_valuta_tab_visibility(self) -> None:
        _fx_ctx.update_valuta_tab_visibility(self)

    def _refresh_fx_tree(self) -> None:
        _fx_ctx.refresh_fx_tree(self)

    def _on_save_fx_settings(self) -> None:
        _fx_ctx.on_save_fx_settings(self)

    def _on_edit_fx_rate(self) -> None:
        _fx_ctx.on_edit_fx_rate(self)

    def _on_run(self) -> None:
        _run_ctx.on_run(self)

    def _build_unmapped_warnings(self, tbs: dict[str, pd.DataFrame]) -> list[str]:
        return _run_ctx.build_unmapped_warnings(self, tbs)

    def _prepare_tbs_for_run(self) -> dict[str, pd.DataFrame]:
        return _run_ctx.prepare_tbs_for_run(self)

    def _on_export(self) -> None:
        _run_ctx.on_export(self)
