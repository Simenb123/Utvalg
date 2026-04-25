from __future__ import annotations

from .selection_shared import *  # noqa: F403


class A07PageSelectionScopeMixin:
    def _selected_a07_filter(self) -> str:
        if getattr(self, "a07_filter_widget", None) is None:
            return "alle"
        try:
            label = str(self.a07_filter_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _CONTROL_VIEW_LABELS.items():
            if value == label:
                return key

        fallback = str(self.a07_filter_var.get() or "").strip().lower()
        return fallback or "alle"

    def _selected_suggestion_scope(self) -> str:
        try:
            label = str(self.suggestion_scope_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _SUGGESTION_SCOPE_LABELS.items():
            if value == label:
                return key

        fallback = str(self.suggestion_scope_var.get() or "").strip().lower()
        return fallback or "valgt_kode"

    def _control_work_level_for_gl_scope(self) -> str:
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            work_level = selected_work_level() if callable(selected_work_level) else "a07"
        except Exception:
            work_level = "a07"
        return work_level if work_level in _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL else "a07"

    def _control_gl_scope_keys_for_work_level(self, work_level: str | None = None) -> tuple[str, ...]:
        level = str(work_level or self._control_work_level_for_gl_scope()).strip().lower()
        return _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL.get(level, _CONTROL_GL_SCOPE_KEYS_BY_WORK_LEVEL["a07"])

    def _control_gl_scope_labels_for_work_level(self, work_level: str | None = None) -> dict[str, str]:
        level = str(work_level or self._control_work_level_for_gl_scope()).strip().lower()
        return _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL.get(level, _CONTROL_GL_SCOPE_LABELS_BY_WORK_LEVEL["a07"])

    def _normalize_control_gl_scope(self, scope_key: str | None, *, work_level: str | None = None) -> str:
        scope = str(scope_key or "").strip().lower()
        scope = _CONTROL_GL_SCOPE_ALIASES.get(scope, scope)
        keys = self._control_gl_scope_keys_for_work_level(work_level)
        if scope in keys:
            return scope
        return "alle"

    def _control_gl_scope_label(self, scope_key: str | None, *, work_level: str | None = None) -> str:
        scope = self._normalize_control_gl_scope(scope_key, work_level=work_level)
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        return labels.get(scope, _CONTROL_GL_SCOPE_LABELS.get(scope, _CONTROL_GL_SCOPE_LABELS["alle"]))

    def _sync_control_gl_scope_widget(self) -> None:
        work_level = self._control_work_level_for_gl_scope()
        keys = self._control_gl_scope_keys_for_work_level(work_level)
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        current = self._normalize_control_gl_scope(self._selected_control_gl_scope(), work_level=work_level)
        if current not in keys:
            current = "alle"
        label_values = [labels[key] for key in keys]
        try:
            self.control_gl_scope_var.set(current)
            self.control_gl_scope_label_var.set(labels[current])
        except Exception:
            pass
        widget = getattr(self, "control_gl_scope_widget", None)
        if widget is not None:
            try:
                widget.configure(values=label_values, state="readonly")
                widget.set(labels[current])
            except Exception:
                pass

    def _selected_control_gl_scope(self) -> str:
        widget = getattr(self, "control_gl_scope_widget", None)
        try:
            label = str(widget.get() or "").strip() if widget is not None else ""
        except Exception:
            label = ""

        work_level = self._control_work_level_for_gl_scope()
        labels = self._control_gl_scope_labels_for_work_level(work_level)
        for key, value in labels.items():
            if value == label:
                return self._normalize_control_gl_scope(key, work_level=work_level)
        for key, value in _CONTROL_GL_SCOPE_LABELS.items():
            if value == label:
                return self._normalize_control_gl_scope(key, work_level=work_level)

        fallback = str(self.control_gl_scope_var.get() or "").strip().lower()
        return self._normalize_control_gl_scope(fallback or "alle", work_level=work_level)

    def _set_control_gl_scope(self, scope_key: str | None) -> None:
        scope = self._normalize_control_gl_scope(scope_key)
        label = self._control_gl_scope_label(scope)
        try:
            self.control_gl_scope_var.set(scope)
            self.control_gl_scope_label_var.set(label)
        except Exception:
            pass
        widget = getattr(self, "control_gl_scope_widget", None)
        if widget is not None:
            try:
                widget.set(label)
            except Exception:
                pass
        self._on_control_gl_filter_changed()

    def _on_control_gl_scope_changed(self) -> None:
        scope = self._selected_control_gl_scope()
        try:
            self.control_gl_scope_var.set(scope)
            self.control_gl_scope_label_var.set(self._control_gl_scope_label(scope))
        except Exception:
            pass
        self._on_control_gl_filter_changed()

    def _apply_control_gl_scope(
        self,
        control_gl_df: pd.DataFrame,
        *,
        selected_code: str | None = None,
    ) -> pd.DataFrame:
        if control_gl_df is None or control_gl_df.empty:
            return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

        scope = self._normalize_control_gl_scope(self._selected_control_gl_scope())
        if scope == "alle":
            return control_gl_df.reset_index(drop=True)

        code = str(selected_code or "").strip()
        work = control_gl_df.copy()
        code_values = work.get("Kode", pd.Series("", index=work.index)).fillna("").astype(str).str.strip()
        work_level = self._control_work_level_for_gl_scope()
        group_id = str(getattr(self, "_selected_rf1022_group", lambda: None)() or "").strip() if work_level == "rf1022" else ""
        if work_level == "rf1022" and group_id and "Rf1022GroupId" in work.columns:
            group_values = work["Rf1022GroupId"].fillna("").astype(str).str.strip()
        else:
            group_values = pd.Series("", index=work.index, dtype="object")

        if scope == "koblede":
            if work_level == "rf1022" and group_id and "Rf1022GroupId" in work.columns:
                return work.loc[group_values == group_id].reset_index(drop=True)
            if not code:
                return work.iloc[0:0].copy().reset_index(drop=True)
            return work.loc[code_values == code].reset_index(drop=True)

        if scope == "forslag":
            if work_level == "rf1022":
                return work.iloc[0:0].copy().reset_index(drop=True)
            suggestion_accounts = set(self._selected_control_suggestion_accounts())
            if not suggestion_accounts:
                return work.iloc[0:0].copy().reset_index(drop=True)
            account_values = work.get("Konto", pd.Series("", index=work.index)).fillna("").astype(str).str.strip()
            out = work.loc[account_values.isin(suggestion_accounts)].copy()
            if code and "AliasStatus" in out.columns:
                effective_rulebook = getattr(self, "effective_rulebook", None)
                if effective_rulebook is None:
                    try:
                        effective_rulebook = load_rulebook(str(getattr(self, "rulebook_path", "") or "") or None)
                    except Exception:
                        effective_rulebook = {}
                out["AliasStatus"] = out.apply(
                    lambda row: evaluate_a07_rule_name_status(code, row.get("Navn"), effective_rulebook),
                    axis=1,
                )
            return out.reset_index(drop=True)

        return work.iloc[0:0].copy().reset_index(drop=True)

    def _selected_control_alternative_mode(self) -> str:
        notebook = getattr(self, "control_support_nb", None)
        if notebook is not None:
            try:
                current_tab = notebook.nametowidget(notebook.select())
            except Exception:
                current_tab = None
            if current_tab is getattr(self, "tab_history", None):
                return "history"
            if current_tab is getattr(self, "tab_suggestions", None):
                return "suggestions"
        widget = getattr(self, "control_alternative_mode_widget", None)
        try:
            label = str(widget.get() or "").strip() if widget is not None else ""
        except Exception:
            label = ""

        for key, value in _CONTROL_ALTERNATIVE_MODE_LABELS.items():
            if value == label:
                return key

        fallback = str(self.control_alternative_mode_var.get() or "").strip().lower()
        return fallback or "suggestions"

    def _selected_basis(self) -> str:
        try:
            label = str(self.basis_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _BASIS_LABELS.items():
            if value == label:
                return key

        fallback = str(self.basis_var.get() or "").strip()
        return fallback if fallback in _BASIS_LABELS else "Endring"

