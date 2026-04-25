from __future__ import annotations

import pandas as pd

from ..page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _CONTROL_STATEMENT_VIEW_LABELS,
    control_statement_view_requires_unclassified,
)
from .. import page_a07_env as _env
from ..page_a07_frames import _empty_control_statement_df
from ..page_a07_runtime_helpers import _clean_context_value
from .data import (
    build_control_statement_export_df,
    filter_control_statement_df,
    normalize_control_statement_view,
)


class A07PageControlStatementViewStateMixin:
    def _build_control_statement_view_df(
        self,
        view: object,
        *,
        include_unclassified: bool | None = None,
    ) -> pd.DataFrame:
        view_key = normalize_control_statement_view(view)
        include_flag = (
            control_statement_view_requires_unclassified(view_key)
            if include_unclassified is None
            else bool(include_unclassified)
        )
        if self.workspace.gl_df is None or self.workspace.gl_df.empty:
            return _empty_control_statement_df()
        client, year = self._session_context(_env.session)
        if not _clean_context_value(client):
            return _empty_control_statement_df()
        base_df = getattr(self, "control_statement_base_df", None)
        if isinstance(base_df, pd.DataFrame) and not base_df.empty:
            return filter_control_statement_df(base_df, view=view_key)
        return filter_control_statement_df(
            build_control_statement_export_df(
                client=client,
                year=year,
                gl_df=self.workspace.gl_df,
                reconcile_df=self.reconcile_df,
                mapping_current=self._effective_mapping(),
                include_unclassified=include_flag,
            ),
            view=view_key,
        )

    def _selected_control_statement_view(self) -> str:
        try:
            label_value = self.control_statement_view_label_var.get()
        except Exception:
            label_value = ""
        try:
            stored_value = self.control_statement_view_var.get()
        except Exception:
            stored_value = ""
        return normalize_control_statement_view(label_value or stored_value or CONTROL_STATEMENT_VIEW_PAYROLL)

    def _sync_control_statement_view_vars(self, view: object) -> str:
        view_key = normalize_control_statement_view(view)
        view_label = _CONTROL_STATEMENT_VIEW_LABELS.get(
            view_key,
            _CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL],
        )
        try:
            self.control_statement_view_var.set(view_key)
        except Exception:
            pass
        try:
            self.control_statement_view_label_var.set(view_label)
        except Exception:
            pass
        try:
            self.control_statement_include_unclassified_var.set(
                control_statement_view_requires_unclassified(view_key)
            )
        except Exception:
            pass
        return view_key

    def _set_control_statement_view_from_menu(self, view: object) -> None:
        view_key = self._sync_control_statement_view_vars(view)
        widget = getattr(self, "control_statement_view_widget", None)
        if widget is not None:
            try:
                widget.set(_CONTROL_STATEMENT_VIEW_LABELS.get(view_key, ""))
            except Exception:
                pass
        self._on_control_statement_filter_changed()

    def _on_control_statement_view_changed(self) -> None:
        self._sync_control_statement_view_vars(self._selected_control_statement_view())
        self._on_control_statement_filter_changed()

    def _selected_control_statement_group(self) -> str | None:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "rf1022"
        except Exception:
            work_level = "rf1022"

        if work_level == "rf1022":
            selected_group = getattr(self, "_selected_rf1022_group", None)
            if callable(selected_group):
                try:
                    group_id = str(selected_group() or "").strip()
                except Exception:
                    group_id = ""
                if group_id:
                    return group_id
        else:
            control_row = None
            selected_row = getattr(self, "_selected_control_row", None)
            if callable(selected_row):
                try:
                    control_row = selected_row()
                except Exception:
                    control_row = None
            if control_row is None:
                selected_code = getattr(self, "_selected_control_code", None)
                try:
                    code = str(selected_code() if callable(selected_code) else "").strip()
                except Exception:
                    code = ""
                control_df = getattr(self, "control_df", None)
                if code and isinstance(control_df, pd.DataFrame) and not control_df.empty:
                    try:
                        matches = control_df.loc[control_df["Kode"].astype(str).str.strip() == code]
                    except Exception:
                        matches = pd.DataFrame()
                    if not matches.empty:
                        control_row = matches.iloc[0]
            if control_row is not None:
                try:
                    group_id = str(control_row.get("Rf1022GroupId") or "").strip()
                except Exception:
                    group_id = ""
                if group_id:
                    return group_id

        return None

    def _selected_control_statement_row(self) -> pd.Series | None:
        group_id = self._selected_control_statement_group()
        if not group_id or self.control_statement_df is None or self.control_statement_df.empty:
            return None
        try:
            matches = self.control_statement_df.loc[
                self.control_statement_df["Gruppe"].astype(str).str.strip() == group_id
            ]
        except Exception:
            return None
        if matches.empty:
            return None
        try:
            return matches.iloc[0]
        except Exception:
            return None

    def _build_current_control_statement_df(
        self,
        *,
        include_unclassified: bool | None = None,
        view: str | None = None,
    ) -> pd.DataFrame:
        view_key = self._sync_control_statement_view_vars(view or self._selected_control_statement_view())
        return self._build_control_statement_view_df(
            view_key,
            include_unclassified=include_unclassified,
        )

    def _selected_control_statement_window_view(self) -> str:
        state = getattr(self, "_control_statement_window_state", None) or {}
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

    def _sync_control_statement_window_view_vars(self, view: object) -> str:
        state = getattr(self, "_control_statement_window_state", None) or {}
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

    def _selected_control_statement_window_group(self) -> str | None:
        state = getattr(self, "_control_statement_window_state", None) or {}
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
