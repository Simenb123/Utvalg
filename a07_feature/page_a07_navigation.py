from __future__ import annotations

from .page_a07_context_shared import *  # noqa: F403


class A07PageNavigationMixin:
    def _open_saldobalanse_workspace(
        self,
        *,
        accounts: Sequence[str] | None = None,
        payroll_scope: str | None = None,
        status_text: str | None = None,
    ) -> bool:
        try:
            host = self.winfo_toplevel()
        except Exception:
            host = None
        notebook = getattr(host, "nb", None)
        saldobalanse_page = getattr(host, "page_saldobalanse", None)
        if notebook is None or saldobalanse_page is None:
            return False
        try:
            notebook.select(saldobalanse_page)
        except Exception:
            return False
        refresh = getattr(saldobalanse_page, "refresh_from_session", None)
        if callable(refresh):
            try:
                refresh(session)
            except Exception:
                pass
        focus_accounts = getattr(saldobalanse_page, "focus_payroll_accounts", None)
        if callable(focus_accounts):
            try:
                focus_accounts(
                    list(accounts or ()),
                    payroll_scope=str(payroll_scope or classification_workspace.QUEUE_ALL),
                )
            except TypeError:
                try:
                    focus_accounts(list(accounts or ()))
                except Exception:
                    pass
            except Exception:
                pass
        if status_text:
            try:
                self.status_var.set(status_text)
            except Exception:
                pass
        return True

    def _open_saldobalanse_for_selected_accounts(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        label = (
            f"Apnet Saldobalanse for klassifisering av konto {accounts[0]}."
            if len(accounts) == 1
            else f"Apnet Saldobalanse for klassifisering av {len(accounts)} kontoer."
        )
        if not self._open_saldobalanse_workspace(accounts=accounts, status_text=label):
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_control_gl)

    def _open_saldobalanse_for_selected_code_classification(self) -> None:
        code = str(self._selected_control_code() or "").strip()
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return
        accounts = self._selected_code_accounts(code)
        row = self._selected_control_row()
        next_action = str((row.get("NesteHandling") if row is not None else "") or "").strip()
        if a07_control_status.is_saldobalanse_follow_up_action(next_action):
            label = f"{next_action} A07 viser behovet, men klassifiseringen gjores i Saldobalanse."
            payroll_scope = a07_control_status.saldobalanse_queue_for_control_action(next_action)
        elif accounts:
            label = f"Apnet Saldobalanse for klassifisering av kontoene bak {code}."
            payroll_scope = classification_workspace.QUEUE_ALL
        else:
            label = f"Apnet Saldobalanse for klassifisering av {code}."
            payroll_scope = classification_workspace.QUEUE_ALL
        try:
            opened = self._open_saldobalanse_workspace(
                accounts=accounts,
                payroll_scope=payroll_scope,
                status_text=label,
            )
        except TypeError:
            opened = self._open_saldobalanse_workspace(accounts=accounts, status_text=label)
        if not opened:
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_a07)

    def _open_saldobalanse_for_selected_group_classification(self) -> None:
        group_id = str(self._selected_group_id() or "").strip()
        if not group_id:
            self._notify_inline("Velg en gruppe forst.", focus_widget=self.tree_groups)
            return
        indexes = getattr(self, "_a07_refresh_indexes", {})
        current_lookup = indexes.get("current_accounts_by_code") if isinstance(indexes, dict) else None
        if isinstance(current_lookup, dict) and group_id in current_lookup:
            accounts = list(current_lookup.get(group_id) or [])
        else:
            accounts = accounts_for_code(self._effective_mapping(), group_id)
        label = (
            f"Apnet Saldobalanse for klassifisering av kontoene bak gruppen {group_id}."
            if accounts
            else f"Apnet Saldobalanse fra gruppen {group_id}."
        )
        if not self._open_saldobalanse_workspace(accounts=accounts, status_text=label):
            self._notify_inline("Fant ikke Saldobalanse-fanen i denne visningen.", focus_widget=self.tree_groups)

    def _sync_groups_panel_visibility(self) -> None:
        try:
            group_count = int(len(self.groups_df.index)) if self.groups_df is not None else 0
        except Exception:
            group_count = 0

        selected_group = str(self._selected_group_id() or "").strip()
        create_button = getattr(self, "btn_create_group", None)
        remove_button = getattr(self, "btn_remove_group", None)
        if create_button is not None:
            try:
                if self._groupable_selected_control_codes():
                    create_button.state(["!disabled"])
                else:
                    create_button.state(["disabled"])
            except Exception:
                pass
        if remove_button is not None:
            try:
                if selected_group:
                    remove_button.state(["!disabled"])
                else:
                    remove_button.state(["disabled"])
            except Exception:
                pass
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is not None and getattr(self, "control_groups_panel", None) is not None:
            try:
                tree_groups.configure(height=max(2, min(group_count or 2, 4)))
            except Exception:
                pass
        lower_body = getattr(self, "control_lower_body", None)
        groups_panel = getattr(self, "control_groups_panel", None)
        if lower_body is not None and groups_panel is not None:
            try:
                pane_names = tuple(str(value) for value in lower_body.panes())
            except Exception:
                pane_names = ()
            panel_name = str(groups_panel)
            should_show = bool(getattr(self, "_control_advanced_visible", False))
            if should_show and panel_name not in pane_names:
                try:
                    lower_body.add(groups_panel, weight=1)
                except Exception:
                    pass
            elif not should_show and panel_name in pane_names:
                try:
                    lower_body.forget(groups_panel)
                except Exception:
                    pass

    def _sync_control_panel_visibility(self) -> None:
        label_specs = (
            ("lbl_control_meta", getattr(self, "control_meta_var", None)),
            ("lbl_control_summary", getattr(self, "control_summary_var", None)),
            ("lbl_control_next", getattr(self, "control_next_var", None)),
        )
        if bool(getattr(self, "_compact_control_status", False)):
            for label_name, _variable in label_specs:
                label = getattr(self, label_name, None)
                if label is None:
                    continue
                try:
                    if bool(label.winfo_manager()):
                        label.pack_forget()
                except Exception:
                    pass
            smart_button = getattr(self, "btn_control_smart", None)
            control_panel = getattr(self, "control_panel", None)
            try:
                smart_visible = bool(smart_button.winfo_manager()) if smart_button is not None else False
            except Exception:
                smart_visible = False
            if control_panel is not None and not smart_visible:
                try:
                    control_panel.pack_forget()
                except Exception:
                    pass
            return
        for label_name, variable in label_specs:
            label = getattr(self, label_name, None)
            if label is None or variable is None:
                continue
            try:
                text = str(variable.get() or "").strip()
            except Exception:
                text = ""
            try:
                visible = bool(label.winfo_manager())
            except Exception:
                visible = False
            if text and not visible:
                try:
                    label.pack(anchor="w", pady=(2, 0))
                except Exception:
                    pass
            elif not text and visible:
                try:
                    label.pack_forget()
                except Exception:
                    pass

