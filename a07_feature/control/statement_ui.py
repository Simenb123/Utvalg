from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..page_a07_constants import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_STATEMENT_VIEW_LABELS,
    control_statement_view_requires_unclassified,
)
from ..page_a07_dialogs import _format_picker_amount
from ..page_a07_env import session
from ..page_a07_frames import _empty_control_statement_df
from ..page_a07_runtime_helpers import _clean_context_value
from . import status as a07_control_status
from .data import (
    build_control_statement_accounts_df,
    build_control_statement_export_df,
    filter_control_statement_df,
    normalize_control_statement_view,
)


class A07PageControlStatementMixin:
    def _sync_control_statement_tab_layout(self) -> None:
        overview_tree = getattr(self, "tree_control_statement", None)
        overview_frame = getattr(overview_tree, "master", None)
        accounts_panel = getattr(self, "control_statement_accounts_panel", None)

        if overview_frame is not None:
            try:
                if bool(overview_frame.winfo_manager()):
                    overview_frame.pack_forget()
            except Exception:
                pass
        if accounts_panel is not None:
            try:
                if not bool(accounts_panel.winfo_manager()):
                    accounts_panel.pack(fill="both", expand=True)
            except Exception:
                pass

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
        client, year = self._session_context(session)
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

        try:
            selection = self.tree_control_statement.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        group_id = str(selection[0] or "").strip()
        return group_id or None

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

    def _refresh_control_statement_window_accounts(self) -> None:
        state = getattr(self, "_control_statement_window_state", None) or {}
        accounts_tree = state.get("accounts_tree")
        accounts_var = state.get("accounts_var")
        source_df = state.get("source_df")
        if accounts_tree is None:
            return

        group_id = self._selected_control_statement_window_group()
        accounts_df = build_control_statement_accounts_df(
            self.control_gl_df,
            source_df if isinstance(source_df, pd.DataFrame) else _empty_control_statement_df(),
            group_id,
        )
        self._fill_tree(
            accounts_tree,
            accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )

        if accounts_var is not None:
            if not group_id:
                accounts_var.set("Velg gruppe for aa se kontoene bak raden.")
            else:
                try:
                    row_df = source_df.loc[source_df["Gruppe"].astype(str).str.strip() == str(group_id).strip()]
                except Exception:
                    row_df = pd.DataFrame()
                if row_df is not None and not row_df.empty:
                    row = row_df.iloc[0]
                    accounts_var.set(
                        a07_control_status.build_control_statement_summary(
                            row,
                            accounts_df,
                            basis_col=self.workspace.basis_col,
                            amount_formatter=_format_picker_amount,
                        )
                    )
                else:
                    accounts_var.set(f"Kontoer {len(accounts_df)}")

    def _refresh_control_statement_window(self) -> None:
        state = getattr(self, "_control_statement_window_state", None)
        win = getattr(self, "_control_statement_window", None)
        if not state or win is None:
            return
        try:
            if not win.winfo_exists():
                self._control_statement_window = None
                self._control_statement_window_state = None
                return
        except Exception:
            self._control_statement_window = None
            self._control_statement_window_state = None
            return

        view_key = self._sync_control_statement_window_view_vars(self._selected_control_statement_window_view())
        source_df = self._build_control_statement_view_df(view_key)
        state["source_df"] = source_df

        overview_tree = state.get("overview_tree")
        summary_var = state.get("summary_var")
        if overview_tree is not None:
            previous_group = self._selected_control_statement_window_group()
            self._fill_tree(
                overview_tree,
                source_df,
                _CONTROL_STATEMENT_COLUMNS,
                iid_column="Gruppe",
                row_tag_fn=lambda row: a07_control_status.control_tree_tag(row.get("Status")),
            )
            try:
                children = overview_tree.get_children()
            except Exception:
                children = ()
            target = None
            if previous_group and previous_group in children:
                target = previous_group
            elif children:
                target = str(children[0]).strip() or None
            if target:
                self._set_tree_selection(overview_tree, target)

        if summary_var is not None:
            summary_var.set(
                a07_control_status.build_control_statement_overview(
                    source_df,
                    basis_col=self.workspace.basis_col,
                    amount_formatter=_format_picker_amount,
                )
            )

        self._refresh_control_statement_window_accounts()

    def _focus_selected_control_statement_window_account_in_gl(self) -> None:
        state = getattr(self, "_control_statement_window_state", None) or {}
        tree = state.get("accounts_tree")
        if tree is None:
            return
        try:
            selection = tree.selection()
        except Exception:
            selection = ()
        if not selection:
            return
        account = str(selection[0] or "").strip()
        if account:
            self._focus_mapping_account(account)

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

    def _open_control_statement_window(self) -> None:
        existing = getattr(self, "_control_statement_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    self._refresh_control_statement_window()
                    existing.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("Kontrolloppstilling")
        win.geometry("1260x760")
        self._control_statement_window = win

        def _on_close() -> None:
            try:
                win.destroy()
            finally:
                self._control_statement_window = None
                self._control_statement_window_state = None

        header = ttk.Frame(win, padding=10)
        header.pack(fill="x")
        summary_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=summary_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)

        view_var = tk.StringVar(value=CONTROL_STATEMENT_VIEW_PAYROLL)
        view_label_var = tk.StringVar(value=_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        ttk.Button(header, text="Lukk", command=_on_close).pack(side="right")
        ttk.Button(header, text="RF-1022...", command=self._open_rf1022_window).pack(side="right", padx=(8, 0))
        ttk.Label(header, text="Visning:").pack(side="right", padx=(8, 4))
        view_widget = ttk.Combobox(
            header,
            textvariable=view_label_var,
            state="readonly",
            width=18,
            values=[_CONTROL_STATEMENT_VIEW_LABELS[key] for key in _CONTROL_STATEMENT_VIEW_LABELS],
        )
        view_widget.pack(side="right")
        view_widget.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])

        body = ttk.Panedwindow(win, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        upper = ttk.Frame(body)
        lower = ttk.Frame(body)
        body.add(upper, weight=3)
        body.add(lower, weight=2)

        overview_tree = self._build_tree_tab(upper, _CONTROL_STATEMENT_COLUMNS)
        accounts_top = ttk.Frame(lower, padding=(0, 0, 0, 6))
        accounts_top.pack(fill="x")
        accounts_var = tk.StringVar(value="Velg gruppe for aa se kontoene bak raden.")
        ttk.Label(accounts_top, textvariable=accounts_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(
            accounts_top,
            text="Vis i GL",
            command=self._focus_selected_control_statement_window_account_in_gl,
        ).pack(side="right")
        accounts_tree = self._build_tree_tab(lower, _CONTROL_SELECTED_ACCOUNT_COLUMNS)

        view_widget.bind("<<ComboboxSelected>>", lambda _event: self._refresh_control_statement_window(), add="+")
        overview_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_control_statement_window_accounts(), add="+")
        accounts_tree.bind(
            "<Double-1>",
            lambda _event: self._focus_selected_control_statement_window_account_in_gl(),
            add="+",
        )
        accounts_tree.bind(
            "<Return>",
            lambda _event: self._focus_selected_control_statement_window_account_in_gl(),
            add="+",
        )

        self._control_statement_window_state = {
            "overview_tree": overview_tree,
            "accounts_tree": accounts_tree,
            "summary_var": summary_var,
            "accounts_var": accounts_var,
            "view_var": view_var,
            "view_label_var": view_label_var,
            "view_widget": view_widget,
            "source_df": _empty_control_statement_df(),
        }

        win.protocol("WM_DELETE_WINDOW", _on_close)
        self._refresh_control_statement_window()

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
            self.control_statement_summary_var.set("Ingen kontrollgrupper er klassifisert ennå.")

    def _on_control_statement_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        previous_group = self._selected_control_statement_group()
        self.control_statement_df = self._build_current_control_statement_df()
        self.control_statement_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self._update_control_statement_overview()
        self._loaded_support_tabs.discard("control_statement")
        if self._active_support_tab_key() == "control_statement":
            self._fill_tree(
                self.tree_control_statement,
                self.control_statement_df,
                _CONTROL_STATEMENT_COLUMNS,
                iid_column="Gruppe",
                row_tag_fn=lambda row: a07_control_status.control_tree_tag(row.get("Status")),
            )
            if previous_group and previous_group in self.tree_control_statement.get_children():
                self._set_tree_selection(self.tree_control_statement, previous_group)
            self._ensure_control_statement_selection()
            self._refresh_control_statement_details()

    def _ensure_control_statement_selection(self) -> None:
        try:
            children = self.tree_control_statement.get_children()
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
            self._set_tree_selection(self.tree_control_statement, target)

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
