from __future__ import annotations

from typing import Callable

import pandas as pd

from ..control import status as a07_control_status
from ..control.data import (
    control_family_tree_tag,
    control_gl_family_tree_tag,
    filter_control_gl_df,
    filter_control_search_df,
    filter_control_visible_codes_df,
    preferred_rf1022_overview_group,
    rf1022_overview_tree_tag,
)
from ..page_a07_constants import (
    _A07_MATCHED_TAG,
    _CONTROL_A07_TOTAL_IID,
    _CONTROL_COLUMNS,
    _CONTROL_GL_COLUMNS,
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_GL_SERIES_LABELS,
    _CONTROL_RF1022_COLUMNS,
    _CONTROL_VIEW_LABELS,
    _SUMMARY_TOTAL_TAG,
)
from .support_render import A07PageSupportRenderMixin
from .tree_render import A07PageTreeRenderMixin


_A07_TOTAL_COLUMNS = ("A07_Belop", "GL_Belop", "Diff")


def _numeric_total(df: pd.DataFrame, column: str) -> float:
    if df is None or df.empty or column not in df.columns:
        return 0.0
    total = 0.0
    for value in df[column].tolist():
        if value is None:
            continue
        try:
            if pd.isna(value):
                continue
        except Exception:
            pass
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            total += float(value)
            continue
        text = str(value).strip().replace("\u00a0", " ").replace(" ", "")
        if not text or text.lower() in {"nan", "none", "null", "na"}:
            continue
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        try:
            total += float(text)
        except Exception:
            continue
    return total


def _numeric_scalar(value: object) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("\u00a0", " ").replace(" ", "")
    if not text or text.lower() in {"nan", "none", "null", "na"}:
        return None
    if "," in text and "." in text:
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except Exception:
        return None


def _a07_row_is_matched(row: pd.Series) -> bool:
    try:
        code = str(row.get("Kode") or "").strip()
    except Exception:
        code = ""
    if code == _CONTROL_A07_TOTAL_IID:
        return False
    diff_value = _numeric_scalar(row.get("Diff"))
    return diff_value is not None and abs(float(diff_value)) <= 0.005


def _filter_a07_match_state_df(df: pd.DataFrame | None, state: object) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.reset_index(drop=True)
    state_s = str(state or "alle").strip().lower()
    if state_s in {"", "alle"}:
        return df.reset_index(drop=True)
    matched = df.apply(_a07_row_is_matched, axis=1)
    if state_s == "avstemt":
        return df.loc[matched].reset_index(drop=True)
    if state_s in {"ikke_avstemt", "umatchet", "avvik"}:
        return df.loc[~matched].reset_index(drop=True)
    return df.reset_index(drop=True)


def _append_a07_total_row(df: pd.DataFrame | None) -> pd.DataFrame | None:
    if df is None or df.empty:
        return df
    display_df = df.copy()
    total_row = {column: "" for column in display_df.columns}
    total_row["Kode"] = _CONTROL_A07_TOTAL_IID
    total_row["A07Post"] = f"SUM viste A07-poster ({len(display_df.index)})"
    total_row["AgaPliktig"] = ""
    for column in _A07_TOTAL_COLUMNS:
        total_row[column] = _numeric_total(display_df, column)
    total_row["Status"] = "Sum"
    total_row["Locked"] = True
    return pd.concat([display_df, pd.DataFrame([total_row])], ignore_index=True)


def _control_a07_row_tag(row: pd.Series) -> str | None:
    try:
        code = str(row.get("Kode") or "").strip()
    except Exception:
        code = ""
    if code == _CONTROL_A07_TOTAL_IID:
        return _SUMMARY_TOTAL_TAG
    if _a07_row_is_matched(row):
        return _A07_MATCHED_TAG
    return control_family_tree_tag(row)


class A07PageRenderMixin(A07PageSupportRenderMixin, A07PageTreeRenderMixin):
    def _refresh_a07_tree(self) -> None:
        work_level = self._selected_control_work_level()
        try:
            selection = self.tree_a07.selection()
        except Exception:
            selection = ()
        current_selection = str(selection[0] or "").strip() if selection else ""
        if not current_selection:
            current_selection = str(self.tree_a07.focus() or "").strip()
        if work_level == "rf1022":
            filtered = self.rf1022_overview_df.copy() if self.rf1022_overview_df is not None else self.rf1022_overview_df
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            self._reconfigure_tree_columns(self.tree_a07, _CONTROL_RF1022_COLUMNS)
            self._fill_tree(
                self.tree_a07,
                filtered,
                _CONTROL_RF1022_COLUMNS,
                iid_column="GroupId",
                row_tag_fn=rf1022_overview_tree_tag,
            )
        else:
            filtered = filter_control_visible_codes_df(self.control_df)
            filtered = a07_control_status.filter_control_queue_df(filtered, self._selected_a07_filter())
            filtered = _filter_a07_match_state_df(
                filtered,
                getattr(getattr(self, "a07_match_filter_var", None), "get", lambda: "alle")(),
            )
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            if (
                filtered.empty
                and self._selected_a07_filter() == "neste"
                and self.control_df is not None
                and not filter_control_visible_codes_df(self.control_df).empty
                and a07_control_status.count_pending_control_items(filter_control_visible_codes_df(self.control_df)) == 0
            ):
                self.a07_filter_var.set("ferdig")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["ferdig"])
                try:
                    self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["ferdig"])
                except Exception:
                    pass
                filtered = a07_control_status.filter_control_queue_df(filter_control_visible_codes_df(self.control_df), "ferdig")
                filtered = _filter_a07_match_state_df(
                    filtered,
                    getattr(getattr(self, "a07_match_filter_var", None), "get", lambda: "alle")(),
                )
                filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            display_df = _append_a07_total_row(filtered)
            self._reconfigure_tree_columns(self.tree_a07, _CONTROL_COLUMNS)
            self._fill_tree(
                self.tree_a07,
                display_df,
                _CONTROL_COLUMNS,
                iid_column="Kode",
                row_tag_fn=_control_a07_row_tag,
            )

        children = self.tree_a07.get_children()
        if work_level != "rf1022":
            children = tuple(child for child in children if str(child) != _CONTROL_A07_TOTAL_IID)
        if not children:
            return

        if work_level == "rf1022":
            target = preferred_rf1022_overview_group(
                filtered,
                children,
                preferred_group=current_selection,
            ) or children[0]
            self._selected_rf1022_group_id = str(target or "").strip() or None
        else:
            target = current_selection if current_selection and current_selection in children else children[0]
        self._set_tree_selection(self.tree_a07, target, reveal=False, focus=False)

    def _refresh_a07_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
        work_level = self._selected_control_work_level()
        try:
            selection = self.tree_a07.selection()
        except Exception:
            selection = ()
        current_selection = str(selection[0] or "").strip() if selection else ""
        if not current_selection:
            current_selection = str(self.tree_a07.focus() or "").strip()
        if work_level == "rf1022":
            filtered = self.rf1022_overview_df.copy() if self.rf1022_overview_df is not None else self.rf1022_overview_df
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            columns = _CONTROL_RF1022_COLUMNS
            iid_column = "GroupId"
            row_tag_fn = rf1022_overview_tree_tag
        else:
            filtered = filter_control_visible_codes_df(self.control_df)
            filtered = a07_control_status.filter_control_queue_df(filtered, self._selected_a07_filter())
            filtered = _filter_a07_match_state_df(
                filtered,
                getattr(getattr(self, "a07_match_filter_var", None), "get", lambda: "alle")(),
            )
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            if (
                filtered.empty
                and self._selected_a07_filter() == "neste"
                and self.control_df is not None
                and not filter_control_visible_codes_df(self.control_df).empty
                and a07_control_status.count_pending_control_items(filter_control_visible_codes_df(self.control_df)) == 0
            ):
                self.a07_filter_var.set("ferdig")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["ferdig"])
                try:
                    self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["ferdig"])
                except Exception:
                    pass
                filtered = a07_control_status.filter_control_queue_df(filter_control_visible_codes_df(self.control_df), "ferdig")
                filtered = _filter_a07_match_state_df(
                    filtered,
                    getattr(getattr(self, "a07_match_filter_var", None), "get", lambda: "alle")(),
                )
                filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
            columns = _CONTROL_COLUMNS
            iid_column = "Kode"
            row_tag_fn = _control_a07_row_tag
            filtered = _append_a07_total_row(filtered)
        self._reconfigure_tree_columns(self.tree_a07, columns)

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_a07.get_children()
                if work_level != "rf1022":
                    children = tuple(child for child in children if str(child) != _CONTROL_A07_TOTAL_IID)
                if children:
                    if work_level == "rf1022":
                        target = preferred_rf1022_overview_group(
                            filtered,
                            children,
                            preferred_group=current_selection,
                        ) or children[0]
                    else:
                        target = current_selection if current_selection and current_selection in children else children[0]
                    if work_level == "rf1022":
                        self._selected_rf1022_group_id = str(target or "").strip() or None
                    self._set_tree_selection(self.tree_a07, target, reveal=False, focus=False)
            if on_complete is not None:
                on_complete()

        if filtered is None or len(filtered.index) <= 500:
            self._fill_tree(
                self.tree_a07,
                filtered,
                columns,
                iid_column=iid_column,
                row_tag_fn=row_tag_fn,
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_a07,
            filtered,
            columns,
            iid_column=iid_column,
            row_tag_fn=row_tag_fn,
            on_complete=_after_fill,
        )

    def _refresh_control_gl_tree(self) -> None:
        selected_account = self._selected_control_gl_account()
        search_text, mapping_filter, account_series, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            mapping_filter=mapping_filter,
            account_series=account_series,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        self._fill_tree(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_family_tree_tag(row),
        )

        children = self.tree_control_gl.get_children()
        if not children:
            return

        if selected_account and selected_account in children:
            self._set_tree_selection(self.tree_control_gl, selected_account)
        else:
            self._clear_control_gl_selection()

    def _refresh_control_gl_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
        selected_account = self._selected_control_gl_account()
        search_text, mapping_filter, account_series, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            mapping_filter=mapping_filter,
            account_series=account_series,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_control_gl.get_children()
                if children and selected_account and selected_account in children:
                    self._set_tree_selection(self.tree_control_gl, selected_account)
                else:
                    self._clear_control_gl_selection()
            if on_complete is not None:
                on_complete()

        if filtered_gl_df is None or len(filtered_gl_df.index) <= 1200:
            self._fill_tree(
                self.tree_control_gl,
                filtered_gl_df,
                _CONTROL_GL_COLUMNS,
                iid_column="Konto",
                row_tag_fn=lambda row: control_gl_family_tree_tag(row),
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_family_tree_tag(row),
            on_complete=_after_fill,
        )

    def _retag_control_gl_tree(self) -> bool:
        try:
            tree = self.tree_control_gl
            children = tuple(tree.get_children())
        except Exception:
            return False
        if not children:
            return False

        search_text, mapping_filter, account_series, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            mapping_filter=mapping_filter,
            account_series=account_series,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        if filtered_gl_df is None or filtered_gl_df.empty:
            return False

        try:
            filtered_iids = [
                str(row.get("Konto") or "").strip()
                for _, row in filtered_gl_df.iterrows()
                if str(row.get("Konto") or "").strip()
            ]
            if tuple(filtered_iids) != children:
                return False
        except Exception:
            return False

        try:
            for _, row in filtered_gl_df.iterrows():
                iid = str(row.get("Konto") or "").strip()
                if not iid:
                    continue
                tag = control_gl_family_tree_tag(row)
                tree.item(iid, tags=((str(tag),) if tag else ()))
        except Exception:
            return False
        return True

    def _on_control_gl_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        try:
            mapping_label = str(self.control_gl_mapping_filter_label_var.get() or "").strip()
            for key, label in _CONTROL_GL_MAPPING_LABELS.items():
                if mapping_label == label:
                    self.control_gl_mapping_filter_var.set(key)
                    break
        except Exception:
            pass
        try:
            series_vars = getattr(self, "control_gl_series_vars", None)
            if isinstance(series_vars, list) and len(series_vars) == 10:
                sync_series = getattr(self, "_sync_control_gl_series_filter_from_checkboxes", None)
                if callable(sync_series):
                    sync_series()
            else:
                series_label = str(self.control_gl_series_filter_label_var.get() or "").strip()
                for key, label in _CONTROL_GL_SERIES_LABELS.items():
                    if series_label == label:
                        self.control_gl_series_filter_var.set(key)
                        break
        except Exception:
            pass
        self._schedule_control_gl_refresh()
        self._update_control_transfer_buttons()

    def _on_control_gl_series_filter_changed(self) -> None:
        sync_series = getattr(self, "_sync_control_gl_series_filter_from_checkboxes", None)
        if callable(sync_series):
            sync_series()
        self._on_control_gl_filter_changed()

    def _on_control_code_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)
