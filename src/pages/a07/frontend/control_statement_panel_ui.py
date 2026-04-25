from __future__ import annotations

import pandas as pd

from a07_feature.page_a07_constants import _CONTROL_SELECTED_ACCOUNT_COLUMNS, _CONTROL_STATEMENT_COLUMNS
from a07_feature.page_a07_dialogs import _format_picker_amount
from a07_feature.control import status as a07_control_status
from a07_feature.control.data import build_control_statement_accounts_df


class A07PageControlStatementPanelMixin:
    def _selected_control_statement_account_ids(self) -> list[str]:
        tree = getattr(self, "tree_control_statement_accounts", None)
        if tree is None:
            return []
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        accounts: list[str] = []
        seen: set[str] = set()
        for iid in selection:
            konto = str(iid).strip()
            if not konto or konto in seen:
                continue
            accounts.append(konto)
            seen.add(konto)
        return accounts

    def _focus_selected_control_statement_account_in_gl(self) -> None:
        accounts = self._selected_control_statement_account_ids()
        if accounts:
            self._focus_mapping_account(accounts[0])

    def _update_control_statement_overview(self, selected_row: pd.Series | None = None) -> None:
        try:
            self.control_statement_summary_var.set(
                a07_control_status.build_control_statement_overview(
                    self.control_statement_df,
                    basis_col=self.workspace.basis_col,
                    selected_row=selected_row,
                    amount_formatter=_format_picker_amount,
                )
            )
        except Exception:
            self.control_statement_summary_var.set("Ingen kontrollgrupper er klassifisert ennÃ¥.")

    def _on_control_statement_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        previous_group = self._selected_control_statement_group()
        self.control_statement_df = self._build_current_control_statement_df()
        self.control_statement_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self._update_control_statement_overview()
        self._loaded_support_tabs.discard("control_statement")
        statement_tree = getattr(self, "tree_control_statement", None)
        if self._active_support_tab_key() == "control_statement" and statement_tree is not None:
            self._fill_tree(
                statement_tree,
                self.control_statement_df,
                _CONTROL_STATEMENT_COLUMNS,
                iid_column="Gruppe",
                row_tag_fn=lambda row: a07_control_status.control_tree_tag(row.get("Status")),
            )
            if previous_group and previous_group in statement_tree.get_children():
                self._set_tree_selection(statement_tree, previous_group)
            self._ensure_control_statement_selection()
            self._refresh_control_statement_details()

    def _ensure_control_statement_selection(self) -> None:
        statement_tree = getattr(self, "tree_control_statement", None)
        if statement_tree is None:
            return
        try:
            children = statement_tree.get_children()
        except Exception:
            children = ()
        if not children:
            return
        target = self._selected_control_statement_group()
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    current_group = str(getattr(self, "_selected_rf1022_group", lambda: None)() or "").strip()
                    if current_group and current_group in children:
                        target = current_group
            except Exception:
                pass
        if not target or target not in children:
            target = str(children[0]).strip() or None
        if target:
            self._set_tree_selection(statement_tree, target)

    def _set_control_accounts_mode(self, mode: str) -> None:
        btn_remove = getattr(self, "btn_control_remove_accounts", None)
        if str(mode).strip() == "control_statement":
            if btn_remove is not None:
                try:
                    btn_remove.state(["disabled"])
                except Exception:
                    pass
        else:
            if btn_remove is not None:
                try:
                    btn_remove.state(["!disabled"])
                except Exception:
                    pass

    def _refresh_control_statement_details(self) -> None:
        self._set_control_accounts_mode("control_statement")
        selected_account = None
        try:
            current_accounts = self.tree_control_statement_accounts.selection()
            if current_accounts:
                selected_account = str(current_accounts[0]).strip() or None
        except Exception:
            selected_account = None

        row = self._selected_control_statement_row()
        group_id = self._selected_control_statement_group()
        accounts_df = build_control_statement_accounts_df(
            self.control_gl_df,
            self.control_statement_df,
            group_id,
        )
        self.control_selected_accounts_df = accounts_df
        self.control_statement_accounts_df = accounts_df
        self._update_control_statement_overview(row)
        self.control_statement_accounts_summary_var.set(
            a07_control_status.build_control_statement_summary(
                row,
                accounts_df,
                basis_col=self.workspace.basis_col,
                amount_formatter=_format_picker_amount,
            )
        )
        self._fill_tree(
            self.tree_control_statement_accounts,
            accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )
        try:
            children = self.tree_control_statement_accounts.get_children()
        except Exception:
            children = ()
        if selected_account and selected_account in children:
            self._set_tree_selection(self.tree_control_statement_accounts, selected_account)
        elif children:
            self._set_tree_selection(self.tree_control_statement_accounts, str(children[0]).strip() or None)

    def _on_control_statement_selected(self) -> None:
        if bool(getattr(self, "_suspend_tree_selection_events", False)):
            return
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    group_id = self._selected_control_statement_group()
                    if group_id:
                        try:
                            self._selected_rf1022_group_id = group_id
                        except Exception:
                            pass
                        try:
                            children = self.tree_a07.get_children()
                        except Exception:
                            children = ()
                        if group_id in children:
                            try:
                                self._set_tree_selection(self.tree_a07, group_id)
                            except Exception:
                                pass
            except Exception:
                pass
        self._refresh_control_statement_details()
