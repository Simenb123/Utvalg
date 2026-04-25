from __future__ import annotations

from .support_render_shared import *  # noqa: F403


class A07PageSupportFiltersMixin:
    def _safe_auto_matching_is_active(self) -> bool:
        return _page_safe_auto_matching_is_active(self)

    def _batch_auto_button_text(self) -> str:
        return _batch_auto_button_text_for(self)

    def _mapping_filter_key_from_label(self, value: object) -> str:
        raw = str(value or "").strip()
        if not raw:
            return "alle"
        raw_cf = raw.casefold()
        for key, label in _MAPPING_FILTER_LABELS.items():
            if raw_cf in {str(key).casefold(), str(label).casefold()}:
                return key
        return "alle"

    def _selected_mapping_filter_key(self) -> str:
        widget = getattr(self, "mapping_filter_widget", None)
        if widget is not None:
            try:
                if not bool(widget.winfo_manager()):
                    return "alle"
            except Exception:
                pass
            try:
                value = widget.get()
            except Exception:
                value = ""
            key = self._mapping_filter_key_from_label(value)
            if key:
                return key
        var = getattr(self, "mapping_filter_var", None)
        try:
            return self._mapping_filter_key_from_label(var.get() if var is not None else "alle")
        except Exception:
            return "alle"

    def _support_tab_context_key(self, tab_key: str | None = None) -> tuple[object, ...]:
        key = str(tab_key or self._active_support_tab_key() or "").strip()
        try:
            work_level = self._selected_control_work_level()
        except Exception:
            work_level = "a07"
        try:
            rf_group = self._selected_rf1022_group() if work_level == "rf1022" else ""
        except Exception:
            rf_group = ""
        try:
            selected_code = self._selected_control_code()
        except Exception:
            selected_code = ""
        try:
            mapping_filter = self._selected_mapping_filter_key() if key in {"mapping", "both"} else ""
        except Exception:
            mapping_filter = ""
        try:
            suggestion_scope = self._selected_suggestion_scope() if key in {"suggestions", "both"} else ""
        except Exception:
            suggestion_scope = ""
        try:
            mapping = self._effective_mapping()
            mapping_signature = (len(mapping), hash(tuple(sorted((str(k), str(v)) for k, v in mapping.items()))))
        except Exception:
            mapping_signature = (0, 0)
        return (
            key,
            work_level,
            str(rf_group or "").strip(),
            str(selected_code or "").strip(),
            str(mapping_filter or "").strip(),
            str(suggestion_scope or "").strip(),
            mapping_signature,
        )

    def _invalidate_control_support(self, reason: str = "", *, rerender: bool = True) -> None:
        if bool(getattr(self, "_control_details_visible", False)):
            self._support_requested = True
        loaded_tabs = getattr(self, "_loaded_support_tabs", None)
        if isinstance(loaded_tabs, set):
            loaded_tabs.clear()
        context_keys = getattr(self, "_loaded_support_context_keys", None)
        if isinstance(context_keys, dict):
            context_keys.clear()
        else:
            self._loaded_support_context_keys = {}
        try:
            self._diag(f"invalidate control support reason={reason}")
        except Exception:
            pass
        if not rerender or not bool(getattr(self, "_control_details_visible", False)):
            return
        if bool(getattr(self, "_support_views_ready", False)):
            schedule_render = getattr(self, "_schedule_active_support_render", None)
            if callable(schedule_render):
                try:
                    schedule_render(force=True)
                    return
                except Exception:
                    pass
            try:
                self._render_active_support_tab(force=True)
            except Exception:
                pass
        else:
            schedule = getattr(self, "_schedule_support_refresh", None)
            if callable(schedule):
                try:
                    schedule()
                except Exception:
                    pass

    def _update_a07_action_button_state(self, summary: dict[str, int] | None = None) -> None:
        best_enabled = False
        best_label = "Bruk trygg kandidat"
        batch_enabled = False
        magic_enabled = False
        try:
            work_level = self._selected_control_work_level()
        except Exception:
            work_level = "a07"

        row = None
        tree = getattr(self, "tree_control_suggestions", None)
        if tree is not None:
            try:
                row = self._selected_suggestion_row_from_tree(tree)
            except Exception:
                row = None

        if row is not None:
            if work_level == "rf1022":
                summary_getter = getattr(self, "get_global_auto_plan_summary", None)
                if callable(summary_getter):
                    try:
                        best_enabled = bool(int(summary_getter(pd.DataFrame([dict(row)])).get("actionable", 0) or 0))
                    except Exception:
                        best_enabled = False
            else:
                try:
                    code = str(row.get("Kode") or "").strip()
                except Exception:
                    code = ""
                try:
                    locked = set(self._locked_codes())
                except Exception:
                    locked = set()
                source = str(row.get("SuggestionSource") or "").strip()
                action = str(row.get("ResidualAction") or "").strip()
                if source == "residual_solver" and action == "group_review":
                    codes_raw = str(row.get("ResidualGroupCodes") or code).strip()
                    group_codes = [part.strip() for part in codes_raw.replace(" + ", ",").split(",") if part.strip()]
                    best_enabled = bool(group_codes) and not any(group_code in locked for group_code in group_codes)
                    best_label = "Opprett gruppeforslag"
                else:
                    best_enabled = (
                        bool(code)
                        and not code.startswith("A07_GROUP:")
                        and code not in locked
                        and a07_suggestion_is_strict_auto(row)
                    )

        if summary is None:
            summary_getter = getattr(self, "get_global_auto_plan_summary", None)
            if callable(summary_getter):
                try:
                    summary = summary_getter()
                except Exception:
                    summary = None
        if isinstance(summary, dict):
            try:
                batch_enabled = bool(int(summary.get("actionable", 0) or 0))
            except Exception:
                batch_enabled = False
        if not _page_safe_auto_matching_is_active(self):
            batch_enabled = False
        elif work_level != "rf1022":
            try:
                magic_enabled = bool(unresolved_codes(self.a07_overview_df))
            except Exception:
                magic_enabled = False

        best_button = getattr(self, "btn_control_best", None)
        if best_button is not None:
            try:
                best_button.configure(text=best_label)
                best_button.state(["!disabled"] if best_enabled else ["disabled"])
            except Exception:
                pass
        batch_button = getattr(self, "btn_control_batch_suggestions", None)
        if batch_button is not None:
            try:
                batch_button.configure(text=_batch_auto_button_text_for(self))
                batch_button.state(["!disabled"] if batch_enabled else ["disabled"])
            except Exception:
                pass
        magic_button = getattr(self, "btn_control_magic", None)
        if magic_button is not None:
            try:
                magic_button.configure(text="Tryllestav: finn 0-diff")
                magic_button.state(["!disabled"] if magic_enabled else ["disabled"])
            except Exception:
                pass

    def _on_mapping_filter_changed(self, _event: object | None = None) -> None:
        self._mapping_filter_user_selected = True
        key = self._selected_mapping_filter_key()
        self._set_mapping_filter_key(key)
        self._invalidate_control_support("mapping-filter", rerender=True)

    def _set_mapping_filter_key(self, key: object) -> None:
        key_s = str(key or "alle").strip().casefold()
        if key_s not in _MAPPING_FILTER_LABELS:
            key_s = "alle"
        label = _MAPPING_FILTER_LABELS.get(key_s, _MAPPING_FILTER_LABELS["alle"])
        try:
            self.mapping_filter_var.set(key_s)
        except Exception:
            pass
        try:
            self.mapping_filter_label_var.set(label)
        except Exception:
            pass
        widget = getattr(self, "mapping_filter_widget", None)
        if widget is not None:
            try:
                widget.set(label)
            except Exception:
                pass

    def _maybe_default_mapping_filter_to_critical(self, accounts_df: pd.DataFrame | None) -> None:
        widget = getattr(self, "mapping_filter_widget", None)
        try:
            if widget is None or not bool(widget.winfo_manager()):
                self._set_mapping_filter_key("alle")
                return
        except Exception:
            pass
        if bool(getattr(self, "_mapping_filter_user_selected", False)):
            return
        current_key = self._selected_mapping_filter_key()
        summary = build_mapping_review_summary(accounts_df)
        if current_key == "kritiske" and summary.get("kritiske", 0) == 0:
            self._set_mapping_filter_key("alle")
            return
        if current_key != "alle":
            return
        if summary.get("kritiske", 0) > 0:
            self._set_mapping_filter_key("kritiske")

    def _control_accounts_summary_text(self, accounts_df: pd.DataFrame, summary_label: object) -> str:
        base = build_control_accounts_summary(
            accounts_df,
            summary_label,
            basis_col=getattr(getattr(self, "workspace", None), "basis_col", "Endring"),
        )
        review = build_mapping_review_summary_text(accounts_df)
        if review and not review.startswith("Ingen koblinger"):
            return f"{base} | {review}"
        return base

    def _rf1022_overview_diff_abs(self, group_id: object) -> float:
        group_s = str(group_id or "").strip()
        overview_df = getattr(self, "rf1022_overview_df", None)
        if not group_s or not isinstance(overview_df, pd.DataFrame) or overview_df.empty:
            return 0.0
        try:
            matches = overview_df.loc[overview_df["GroupId"].fillna("").astype(str).str.strip() == group_s]
        except Exception:
            return 0.0
        if matches.empty:
            return 0.0
        try:
            return float(pd.to_numeric(pd.Series([matches.iloc[0].get("Diff")]), errors="coerce").fillna(0.0).iloc[0])
        except Exception:
            return 0.0

    def _should_default_rf1022_to_mapping(self, group_id: object, accounts_df: pd.DataFrame | None) -> bool:
        group_s = str(group_id or "").strip()
        if not group_s or group_s == RF1022_UNKNOWN_GROUP:
            return False
        candidates = getattr(self, "rf1022_candidate_df", None)
        has_candidates = isinstance(candidates, pd.DataFrame) and not candidates.empty
        if has_candidates:
            return False
        has_accounts = isinstance(accounts_df, pd.DataFrame) and not accounts_df.empty
        return has_accounts or abs(self._rf1022_overview_diff_abs(group_s)) > 0.005

    def _filter_visible_mapping_accounts_df(self, accounts_df: pd.DataFrame | None) -> pd.DataFrame:
        columns = [c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
        if accounts_df is None:
            return pd.DataFrame(columns=columns)
        work = accounts_df.copy()
        if work.empty:
            return pd.DataFrame(columns=columns)
        work = filter_mapping_rows_by_audit_status(work, self._selected_mapping_filter_key())
        return work.reindex(columns=columns, fill_value="").reset_index(drop=True)

    def _active_support_tab_key(self) -> str | None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return None
        notebook = getattr(self, "control_support_nb", None)
        if notebook is None:
            return "both"
        try:
            current_tab = notebook.nametowidget(notebook.select())
        except Exception:
            return None
        if current_tab is self.tab_suggestions:
            return "suggestions"
        if current_tab is self.tab_history:
            return "history"
        if current_tab is self.tab_control_statement:
            return "control_statement"
        if current_tab is self.tab_unmapped:
            return "unmapped"
        if current_tab is self.tab_mapping:
            return "mapping"
        return None

