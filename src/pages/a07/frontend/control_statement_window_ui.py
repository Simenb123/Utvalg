from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from a07_feature.page_a07_constants import (
    CONTROL_STATEMENT_VIEW_LEGACY,
    CONTROL_STATEMENT_VIEW_PAYROLL,
    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _CONTROL_STATEMENT_VIEW_LABELS,
    _RF1022_ACCOUNT_COLUMNS,
    _RF1022_OVERVIEW_COLUMNS,
)
from a07_feature.page_a07_dialogs import _format_picker_amount
from a07_feature.page_a07_frames import _empty_control_statement_df
from a07_feature.page_a07_runtime_helpers import _account_profile_api_for_a07
from a07_feature.control import status as a07_control_status
from a07_feature.control.data import (
    build_control_statement_accounts_df,
    build_rf1022_accounts_df,
    build_rf1022_statement_df,
    build_rf1022_statement_summary,
)


_STATEMENT_MODE_CONTROL = "control"
_STATEMENT_MODE_RF1022 = "rf1022"
_STATEMENT_MODE_LABELS = {
    _STATEMENT_MODE_CONTROL: "Kontrolloppstilling",
    _STATEMENT_MODE_RF1022: "RF-1022 avstemming",
}


def _control_statement_window_mode_labels() -> list[str]:
    return list(_STATEMENT_MODE_LABELS.values())


def _control_statement_window_mode_from_label(value: object) -> str:
    raw = str(value or "").strip()
    for mode, label in _STATEMENT_MODE_LABELS.items():
        if raw == label or raw == mode:
            return mode
    return _STATEMENT_MODE_CONTROL


def _control_statement_window_view_labels() -> list[str]:
    return [
        label
        for view_key, label in _CONTROL_STATEMENT_VIEW_LABELS.items()
        if view_key != CONTROL_STATEMENT_VIEW_LEGACY
    ]


class A07PageControlStatementWindowMixin:
    def _control_statement_profile_document(self):
        state = getattr(self, "_control_statement_window_state", None) or {}
        client, year = getattr(self, "_context_key", (None, None))
        client_s = str(client or "").strip()
        year_i: int | None = None
        try:
            year_i = int(str(year).strip()) if str(year or "").strip() else None
        except Exception:
            year_i = None
        cache_key = (client_s, year_i)
        if state.get("profile_document_cache_key") == cache_key:
            return state.get("profile_document")
        document = None
        if client_s:
            try:
                document = _account_profile_api_for_a07().load_document(client=client_s, year=year_i)
            except Exception:
                document = None
        state["profile_document_cache_key"] = cache_key
        state["profile_document"] = document
        return document

    def _selected_control_statement_window_mode(self) -> str:
        state = getattr(self, "_control_statement_window_state", None) or {}
        mode_label_var = state.get("mode_label_var")
        mode_var = state.get("mode_var")
        try:
            label_value = mode_label_var.get() if mode_label_var is not None else ""
        except Exception:
            label_value = ""
        try:
            stored_value = mode_var.get() if mode_var is not None else ""
        except Exception:
            stored_value = ""
        return _control_statement_window_mode_from_label(label_value or stored_value)

    def _reconfigure_control_statement_window_tree(self, tree: ttk.Treeview, columns: list[tuple[str, str, int, str]]) -> None:
        reconfigure = getattr(self, "_reconfigure_tree_columns", None)
        if callable(reconfigure):
            reconfigure(tree, columns)
            return
        try:
            tree.configure(columns=[column_id for column_id, *_rest in columns])
        except Exception:
            pass

    def _refresh_control_statement_window_accounts(self) -> None:
        state = getattr(self, "_control_statement_window_state", None) or {}
        accounts_tree = state.get("accounts_tree")
        accounts_var = state.get("accounts_var")
        source_df = state.get("source_df")
        if accounts_tree is None:
            return

        group_id = self._selected_control_statement_window_group()
        source_df = source_df if isinstance(source_df, pd.DataFrame) else _empty_control_statement_df()
        basis_col = getattr(getattr(self, "workspace", None), "basis_col", "Endring")
        mode_key = self._selected_control_statement_window_mode()
        if mode_key == _STATEMENT_MODE_RF1022:
            columns = _RF1022_ACCOUNT_COLUMNS
            accounts_df = build_rf1022_accounts_df(
                getattr(self, "control_gl_df", None),
                source_df,
                group_id,
                basis_col=basis_col,
                profile_document=self._control_statement_profile_document(),
            )
        else:
            columns = _CONTROL_SELECTED_ACCOUNT_COLUMNS
            accounts_df = build_control_statement_accounts_df(
                getattr(self, "control_gl_df", None),
                source_df,
                group_id,
            )
        self._reconfigure_control_statement_window_tree(accounts_tree, columns)
        self._fill_tree(accounts_tree, accounts_df, columns, iid_column="Konto")

        if accounts_var is not None:
            if not group_id:
                if mode_key == _STATEMENT_MODE_RF1022:
                    accounts_var.set("Velg RF-1022-post for å se kontoene bak raden.")
                else:
                    accounts_var.set("Velg gruppe for å se kontoene bak raden.")
            else:
                if mode_key == _STATEMENT_MODE_RF1022:
                    overview_df = state.get("overview_df")
                    try:
                        row_df = overview_df.loc[
                            overview_df["GroupId"].astype(str).str.strip() == str(group_id).strip()
                        ]
                    except Exception:
                        row_df = pd.DataFrame()
                    if row_df is not None and not row_df.empty:
                        row = row_df.iloc[0]
                        label = str(row.get("Kontrollgruppe") or row.get("GroupId") or group_id).strip()
                        accounts_var.set(
                            f"{label} | {len(accounts_df)} kontoer | "
                            f"GL {_format_picker_amount(row.get('GL_Belop'))} | "
                            f"A07 {_format_picker_amount(row.get('A07'))} | "
                            f"Diff {_format_picker_amount(row.get('Diff'))}"
                        )
                    else:
                        accounts_var.set(f"Kontoer {len(accounts_df)}")
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
                                basis_col=basis_col,
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
        mode_key = self._selected_control_statement_window_mode()
        basis_col = getattr(getattr(self, "workspace", None), "basis_col", "Endring")
        if mode_key == _STATEMENT_MODE_RF1022:
            overview_df = build_rf1022_statement_df(
                source_df,
                basis_col=basis_col,
                a07_overview_df=getattr(self, "a07_overview_df", None),
                control_gl_df=getattr(self, "control_gl_df", None),
                profile_document=self._control_statement_profile_document(),
            )
            overview_columns = _RF1022_OVERVIEW_COLUMNS
            overview_iid_column = "GroupId"
            summary_text = build_rf1022_statement_summary(overview_df)
        else:
            overview_df = source_df
            overview_columns = _CONTROL_STATEMENT_COLUMNS
            overview_iid_column = "Gruppe"
            summary_text = a07_control_status.build_control_statement_overview(
                source_df,
                basis_col=basis_col,
                amount_formatter=_format_picker_amount,
            )
        state["overview_df"] = overview_df

        overview_tree = state.get("overview_tree")
        summary_var = state.get("summary_var")
        if overview_tree is not None:
            previous_group = self._selected_control_statement_window_group()
            self._reconfigure_control_statement_window_tree(overview_tree, overview_columns)
            self._fill_tree(
                overview_tree,
                overview_df,
                overview_columns,
                iid_column=overview_iid_column,
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
            summary_var.set(summary_text)

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
        mode_var = tk.StringVar(value=_STATEMENT_MODE_RF1022)
        mode_label_var = tk.StringVar(value=_STATEMENT_MODE_LABELS[_STATEMENT_MODE_RF1022])
        ttk.Button(header, text="Lukk", command=_on_close).pack(side="right")
        ttk.Label(header, text="Visning:").pack(side="right", padx=(8, 4))
        view_widget = ttk.Combobox(
            header,
            textvariable=view_label_var,
            state="readonly",
            width=18,
            values=_control_statement_window_view_labels(),
        )
        view_widget.pack(side="right")
        view_widget.set(_CONTROL_STATEMENT_VIEW_LABELS[CONTROL_STATEMENT_VIEW_PAYROLL])
        ttk.Label(header, text="Type:").pack(side="right", padx=(8, 4))
        mode_widget = ttk.Combobox(
            header,
            textvariable=mode_label_var,
            state="readonly",
            width=22,
            values=_control_statement_window_mode_labels(),
        )
        mode_widget.pack(side="right")
        mode_widget.set(_STATEMENT_MODE_LABELS[_STATEMENT_MODE_RF1022])

        body = ttk.Panedwindow(win, orient="vertical")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        upper = ttk.Frame(body)
        lower = ttk.Frame(body)
        body.add(upper, weight=3)
        body.add(lower, weight=2)

        overview_tree = self._build_tree_tab(upper, _RF1022_OVERVIEW_COLUMNS)
        accounts_top = ttk.Frame(lower, padding=(0, 0, 0, 6))
        accounts_top.pack(fill="x")
        accounts_var = tk.StringVar(value="Velg RF-1022-post for aa se kontoene bak raden.")
        ttk.Label(accounts_top, textvariable=accounts_var, style="Muted.TLabel").pack(side="left", fill="x", expand=True)
        ttk.Button(
            accounts_top,
            text="Vis i GL",
            command=self._focus_selected_control_statement_window_account_in_gl,
        ).pack(side="right")
        accounts_tree = self._build_tree_tab(lower, _CONTROL_SELECTED_ACCOUNT_COLUMNS)

        view_widget.bind("<<ComboboxSelected>>", lambda _event: self._refresh_control_statement_window(), add="+")
        mode_widget.bind("<<ComboboxSelected>>", lambda _event: self._refresh_control_statement_window(), add="+")
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
            "mode_var": mode_var,
            "mode_label_var": mode_label_var,
            "mode_widget": mode_widget,
            "source_df": _empty_control_statement_df(),
            "overview_df": _empty_control_statement_df(),
        }

        win.protocol("WM_DELETE_WINDOW", _on_close)
        self._refresh_control_statement_window()
