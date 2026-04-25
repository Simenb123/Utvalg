from __future__ import annotations

from .selection_shared import *  # noqa: F403


class A07PageSelectionContextMixin:
    def _selected_control_codes(self) -> list[str]:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    out: list[str] = []
                    seen: set[str] = set()
                    try:
                        selection = self.tree_a07.selection()
                    except Exception:
                        selection = ()
                    groups = [str(item or "").strip() for item in selection or () if str(item or "").strip()]
                    if not groups:
                        current_group = str(getattr(self, "_selected_rf1022_group_id", "") or "").strip()
                        if current_group:
                            groups = [current_group]
                    control_df = getattr(self, "control_df", None)
                    if control_df is None or getattr(control_df, "empty", True):
                        return out
                    for group_id in groups:
                        try:
                            matches = control_df.loc[
                                control_df["Rf1022GroupId"].fillna("").astype(str).str.strip() == group_id
                            ]
                        except Exception:
                            matches = pd.DataFrame()
                        for code in matches.get("Kode", pd.Series(dtype="object")).fillna("").astype(str):
                            code_s = str(code).strip()
                            if not code_s or code_s in seen:
                                continue
                            out.append(code_s)
                            seen.add(code_s)
                    return out
            except Exception:
                pass
        out: list[str] = []
        seen: set[str] = set()
        try:
            selection = self.tree_a07.selection()
        except Exception:
            selection = ()
        for item in selection or ():
            code = str(item or "").strip()
            if not code or code == _CONTROL_A07_TOTAL_IID or code in seen:
                continue
            tag_checker = getattr(self, "_tree_item_has_tag", None)
            if callable(tag_checker):
                try:
                    if tag_checker(self.tree_a07, code, _SUMMARY_TOTAL_TAG):
                        continue
                except Exception:
                    pass
            out.append(code)
            seen.add(code)
        return out

    def _selected_group_id(self) -> str | None:
        try:
            selection = self.tree_groups.selection()
        except Exception:
            selection = ()
        if selection:
            group_id = str(selection[0] or "").strip()
            return group_id or None
        selected_code = str(self._selected_control_code() or "").strip()
        if selected_code.startswith("A07_GROUP:"):
            return selected_code
        return None

    def _groupable_selected_control_codes(self) -> list[str]:
        return [code for code in self._selected_control_codes() if code and not code.startswith("A07_GROUP:")]

    def _selected_control_row(self) -> pd.Series | None:
        code = str(self._selected_control_code() or "").strip()
        if not code or self.control_df is None or self.control_df.empty:
            return None
        try:
            matches = self.control_df.loc[self.control_df["Kode"].astype(str).str.strip() == code]
        except Exception:
            return None
        if matches.empty:
            return None
        try:
            return matches.iloc[0]
        except Exception:
            return None

    def _selected_code_accounts(self, code: str | None = None) -> list[str]:
        code_s = str(code or self._selected_control_code() or "").strip()
        if not code_s:
            return []
        indexes = getattr(self, "_a07_refresh_indexes", {})
        current_lookup = indexes.get("current_accounts_by_code") if isinstance(indexes, dict) else None
        if isinstance(current_lookup, dict) and code_s in current_lookup:
            return list(current_lookup.get(code_s) or [])
        return accounts_for_code(self._effective_mapping(), code_s)

    def _control_gl_label_key(self, labels: dict[str, str], raw_key: object, raw_label: object, default: str) -> str:
        key_s = str(raw_key or "").strip()
        if key_s in labels:
            return key_s
        label_s = str(raw_label or "").strip()
        for key, label in labels.items():
            if label_s == str(label):
                return key
        return default

    def _selected_control_gl_series_digits(self) -> tuple[str, ...]:
        series_vars = getattr(self, "control_gl_series_vars", None)
        if not isinstance(series_vars, list) or len(series_vars) != 10:
            return ()
        selected: list[str] = []
        for digit, var in enumerate(series_vars):
            try:
                is_selected = bool(var.get())
            except Exception:
                is_selected = False
            if is_selected:
                selected.append(str(digit))
        return tuple(selected)

    def _sync_control_gl_series_filter_from_checkboxes(self) -> str:
        selected = self._selected_control_gl_series_digits()
        key = ",".join(selected) if selected else "alle"
        label = ", ".join(f"{digit}xxx" for digit in selected) if selected else _CONTROL_GL_SERIES_LABELS["alle"]
        try:
            self.control_gl_series_filter_var.set(key)
        except Exception:
            pass
        try:
            self.control_gl_series_filter_label_var.set(label)
        except Exception:
            pass
        return key

    def _control_gl_filter_state(self) -> tuple[str, str, str, bool, bool]:
        try:
            search_text = str(self.control_gl_filter_var.get() or "")
        except Exception:
            search_text = ""
        try:
            mapping_key = self._control_gl_label_key(
                _CONTROL_GL_MAPPING_LABELS,
                self.control_gl_mapping_filter_var.get(),
                self.control_gl_mapping_filter_label_var.get(),
                "alle",
            )
        except Exception:
            mapping_key = "alle"
        try:
            series_vars = getattr(self, "control_gl_series_vars", None)
            if isinstance(series_vars, list) and len(series_vars) == 10:
                series_key = self._sync_control_gl_series_filter_from_checkboxes()
            else:
                series_key = self._control_gl_label_key(
                    _CONTROL_GL_SERIES_LABELS,
                    self.control_gl_series_filter_var.get(),
                    self.control_gl_series_filter_label_var.get(),
                    "alle",
                )
        except Exception:
            series_key = "alle"
        try:
            only_unmapped = bool(self.control_gl_unmapped_only_var.get())
        except Exception:
            only_unmapped = False
        try:
            active_only = bool(self.control_gl_active_only_var.get())
        except Exception:
            active_only = False
        return search_text, mapping_key, series_key, only_unmapped, active_only

