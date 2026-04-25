from __future__ import annotations

from pathlib import Path

import pandas as pd

from a07_feature import export_a07_workbook
from a07_feature.control.data import build_control_statement_export_df, filter_control_statement_df
from a07_feature.control.statement_model import normalize_control_statement_view
from a07_feature.page_a07_constants import CONTROL_STATEMENT_VIEW_PAYROLL, _CONTROL_STATEMENT_VIEW_LABELS
from a07_feature.page_a07_env import filedialog, messagebox, session
from a07_feature.page_a07_runtime_helpers import _clean_context_value
from a07_feature.page_paths import default_a07_export_path
from src.pages.a07.backend.rf1022 import build_rf1022_source_df


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
        return normalize_control_statement_view(label_value or stored_value or CONTROL_STATEMENT_VIEW_PAYROLL)

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

    def _build_rf1022_source_df(self, *, view: object | None = None) -> pd.DataFrame:
        view_key = self._sync_rf1022_view_vars(view or self._selected_rf1022_view())
        base_df = getattr(self, "control_statement_base_df", None)
        gl_df = getattr(self.workspace, "gl_df", None)
        if isinstance(base_df, pd.DataFrame) and not base_df.empty:
            return build_rf1022_source_df(
                view=view_key,
                control_statement_base_df=base_df,
                gl_df=gl_df,
                client=None,
                year=None,
                reconcile_df=None,
                mapping_current=None,
                build_export_df=build_control_statement_export_df,
                filter_statement_df=filter_control_statement_df,
            )
        if gl_df is None or gl_df.empty:
            return build_rf1022_source_df(
                view=view_key,
                control_statement_base_df=base_df,
                gl_df=gl_df,
                client=None,
                year=None,
                reconcile_df=None,
                mapping_current=None,
                build_export_df=build_control_statement_export_df,
                filter_statement_df=filter_control_statement_df,
            )

        client, year = self._session_context(session)
        return build_rf1022_source_df(
            view=view_key,
            control_statement_base_df=base_df,
            gl_df=gl_df,
            client=_clean_context_value(client),
            year=year,
            reconcile_df=getattr(self, "reconcile_df", None),
            mapping_current=self._effective_mapping(),
            build_export_df=build_control_statement_export_df,
            filter_statement_df=filter_control_statement_df,
        )


__all__ = [
    "A07PageRf1022Mixin",
    "build_control_statement_export_df",
    "filter_control_statement_df",
]
