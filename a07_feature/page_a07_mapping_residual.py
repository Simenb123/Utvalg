from __future__ import annotations

import pandas as pd

from .page_a07_mapping_shared import *  # noqa: F403
from .suggest.residual_solver import SAFE_EXACT, analyze_a07_residuals
from .suggest.residual_display import (
    merge_residual_suggestions,
    residual_analysis_to_suggestions_df,
    residual_review_summary,
)
from .page_a07_constants import _CONTROL_SUGGESTION_COLUMNS, _SUGGESTION_COLUMNS
from src.pages.a07.backend.mapping_apply import apply_residual_changes_to_mapping


def _residual_review_detail_text(review_rows: pd.DataFrame | None) -> str:
    if isinstance(review_rows, pd.DataFrame) and not review_rows.empty and "ResidualAction" in review_rows.columns:
        actions = {str(value or "").strip() for value in review_rows["ResidualAction"].tolist()}
        if actions and actions <= {"group_review"}:
            return "Tryllestav-resultat: velg gruppeforslag og trykk Opprett gruppeforslag."
    return "Tryllestav-resultat: velg rad for manuell vurdering."


class A07PageMappingResidualMixin:
    def _residual_group_codes_from_row(self, row: pd.Series | dict[str, object] | None) -> list[str]:
        if row is None:
            return []
        try:
            raw = str(row.get("ResidualGroupCodes") or "").strip()
        except Exception:
            raw = ""
        if raw:
            parts = raw.split(",")
        else:
            try:
                parts = str(row.get("Kode") or "").split("+")
            except Exception:
                parts = []
        return list(dict.fromkeys(str(part).strip() for part in parts if str(part).strip()))

    def _create_residual_group_from_suggestion(self, row: pd.Series | dict[str, object] | None) -> str | None:
        codes = self._residual_group_codes_from_row(row)
        if not codes:
            self._notify_inline("Tryllestaven fant ingen A07-koder å gruppere i valgt rad.", focus_widget=self.tree_control_suggestions)
            return None
        group_id = self._create_group_from_codes(codes)
        if not group_id:
            return None

        opener = getattr(self, "_open_groups_popup", None)
        if callable(opener):
            opener(group_id)
        try:
            raw_accounts = row.get("ResidualGroupAccounts") or row.get("ForslagKontoer")  # type: ignore[union-attr]
        except Exception:
            raw_accounts = ""
        accounts = sorted(_split_mapping_accounts(raw_accounts))
        if accounts:
            focus_account = getattr(self, "_focus_mapping_account", None)
            if callable(focus_account):
                focus_account(accounts[0])
            self.status_var.set(
                f"Opprettet/fokuserte gruppe for {', '.join(codes)}. Vurder kontoer {', '.join(accounts)} mot gruppen."
            )
        return group_id

    def _build_magic_wand_residual_analysis(self):
        try:
            effective_mapping = dict(self._effective_mapping() or {})
        except Exception:
            effective_mapping = dict(getattr(getattr(self, "workspace", None), "mapping", None) or {})
        return analyze_a07_residuals(
            getattr(self, "a07_overview_df", None),
            getattr(self, "control_gl_df", None),
            effective_mapping,
            locked_codes=_locked_codes_for(self),
            basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
            suggestions_df=getattr(getattr(self, "workspace", None), "suggestions", None),
        )

    def _apply_magic_wand_residual_changes(self, analysis) -> tuple[int, int, str]:
        changes = tuple(getattr(analysis, "changes", ()) or ())
        if not changes:
            return 0, 0, ""
        workspace = getattr(self, "workspace", None)
        if workspace is None:
            return 0, 0, ""
        if not isinstance(getattr(workspace, "mapping", None), dict):
            workspace.mapping = {}
        result = apply_residual_changes_to_mapping(
            workspace.mapping,
            changes,
            locked_codes=_locked_codes_for(self),
        )
        return result.applied_codes, result.applied_accounts, result.focus_code

    def _show_magic_wand_residual_review(self, analysis) -> int:
        residual_df = residual_analysis_to_suggestions_df(analysis)
        workspace = getattr(self, "workspace", None)
        if workspace is not None:
            combined, review_rows = merge_residual_suggestions(
                getattr(workspace, "suggestions", None),
                residual_df,
            )
            try:
                workspace.suggestions = combined
            except Exception:
                pass
        else:
            review_rows = residual_df.reset_index(drop=True) if isinstance(residual_df, pd.DataFrame) else pd.DataFrame()

        row_count = int(len(review_rows.index)) if isinstance(review_rows, pd.DataFrame) else 0
        if not row_count:
            return 0

        tree = getattr(self, "tree_control_suggestions", None)
        fill_tree = getattr(self, "_fill_tree", None)
        reconfigure = getattr(self, "_reconfigure_tree_columns", None)
        if tree is not None and callable(fill_tree):
            try:
                if callable(reconfigure):
                    reconfigure(tree, _CONTROL_SUGGESTION_COLUMNS)
                fill_tree(
                    tree,
                    review_rows,
                    _CONTROL_SUGGESTION_COLUMNS,
                    row_tag_fn=suggestion_tree_tag,
                )
            except Exception:
                pass
            try:
                children = tree.get_children()
                if children:
                    self._set_tree_selection(tree, children[0], reveal=True, focus=True)
            except Exception:
                pass

        summary = residual_review_summary(analysis, row_count)
        for attr in ("control_suggestion_summary_var", "control_alternative_summary_var"):
            var = getattr(self, attr, None)
            if var is not None:
                try:
                    var.set(summary)
                except Exception:
                    pass
        details_var = getattr(self, "suggestion_details_var", None)
        if details_var is not None:
            try:
                details_var.set(_residual_review_detail_text(review_rows))
            except Exception:
                pass
        effect_var = getattr(self, "control_suggestion_effect_var", None)
        if effect_var is not None:
            try:
                effect_var.set("")
            except Exception:
                pass

        best_button = getattr(self, "btn_control_best", None)
        if best_button is not None:
            try:
                best_button.state(["disabled"])
            except Exception:
                pass
        update_buttons = getattr(self, "_update_a07_action_button_state", None)
        if callable(update_buttons):
            try:
                update_buttons()
            except Exception:
                pass
        return row_count

    def _run_magic_wand_residual_flow(self) -> None:
        analysis = self._build_magic_wand_residual_analysis()
        if getattr(analysis, "status", "") != SAFE_EXACT or not bool(getattr(analysis, "auto_safe", False)):
            row_count = self._show_magic_wand_residual_review(analysis)
            message = residual_review_summary(analysis, row_count)
            try:
                self.status_var.set("Tryllestav krever vurdering." if row_count else "Ingen trygg 0-diff-løsning.")
            except Exception:
                pass
            details_var = getattr(self, "details_var", None)
            if details_var is not None:
                try:
                    details_var.set(message)
                except Exception:
                    pass
            self._notify_inline(
                message,
                focus_widget=getattr(self, "tree_control_suggestions", getattr(self, "tree_a07", self)),
            )
            try:
                self._select_support_tab_key("suggestions", force_render=True)
            except Exception:
                pass
            return

        try:
            applied_codes, applied_accounts, focus_code = self._apply_magic_wand_residual_changes(analysis)
            if applied_codes <= 0 or applied_accounts <= 0:
                message = str(getattr(analysis, "explanation", "") or "").strip() or (
                    "Tryllestaven fant analyse, men ingen trygg endring kunne brukes automatisk."
                )
                self._notify_inline(message, focus_widget=getattr(self, "tree_control_suggestions", self))
                return
            autosaved = self._autosave_mapping(source="magic_wand_residual", confidence=1.0)
            self._refresh_core(focus_code=focus_code)
            if focus_code:
                self._focus_control_code(focus_code)
            saved_suffix = " og lagret" if autosaved else ""
            self.status_var.set(
                f"Tryllestav brukte {applied_codes} trygg(e) residualforslag ({applied_accounts} kontoer){saved_suffix}."
            )
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Tryllestav kunne ikke fullføre:\n{exc}")


__all__ = ["A07PageMappingResidualMixin"]
