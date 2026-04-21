from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Sequence

import pandas as pd

from ..page_a07_constants import _CONTROL_DRAG_IDLE_HINT, _CONTROL_GL_COLUMNS, _CONTROL_VIEW_LABELS
from ..page_a07_dialogs import remove_mapping_accounts


class A07PageTreeUiMixin:
    def _build_tree_tab(self, parent: ttk.Frame, columns: Sequence[tuple[str, str, int, str]]) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings")
        for column_id, heading, width, anchor in columns:
            tree.heading(column_id, text=heading)
            tree.column(column_id, width=width, anchor=anchor)

        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        return tree

    def _reconfigure_tree_columns(
        self,
        tree: ttk.Treeview,
        columns: Sequence[tuple[str, str, int, str]],
    ) -> None:
        column_ids = [column_id for column_id, *_rest in columns]
        tree.configure(columns=column_ids, displaycolumns=column_ids)
        for column_id, heading, width, anchor in columns:
            tree.heading(column_id, text=heading)
            tree.column(column_id, width=width, anchor=anchor, stretch=True)

    def _selected_tree_values(self, tree: ttk.Treeview) -> tuple[str, ...]:
        selection = tree.selection()
        if not selection:
            return ()
        values = tree.item(selection[0], "values")
        return tuple(str(value) for value in (values or ()))

    def _selected_suggestion_row_from_tree(self, tree: ttk.Treeview) -> pd.Series | None:
        selection = tree.selection()
        if not selection or self.workspace.suggestions is None or self.workspace.suggestions.empty:
            return None

        selected_id = str(selection[0]).strip()
        if not selected_id:
            return None

        try:
            idx = int(selected_id)
        except Exception:
            return None

        try:
            return self.workspace.suggestions.loc[idx]
        except Exception:
            try:
                return self.workspace.suggestions.iloc[idx]
            except Exception:
                return None

    def _tree_iid_from_event(self, tree: ttk.Treeview, event: tk.Event | None = None) -> str | None:
        if event is not None:
            identify_row = getattr(tree, "identify_row", None)
            if callable(identify_row):
                try:
                    iid = str(identify_row(getattr(event, "y", 0)) or "").strip()
                except Exception:
                    iid = ""
                if iid:
                    return iid

        selection = tree.selection()
        if not selection:
            return None
        iid = str(selection[0]).strip()
        return iid or None

    def _manual_mapping_defaults(self) -> tuple[str | None, str | None]:
        konto = None
        kode = None

        control_gl_values = self._selected_tree_values(self.tree_control_gl)
        if control_gl_values:
            konto = str(control_gl_values[0]).strip() or None
            control_gl_column_ids = [column_id for column_id, *_rest in _CONTROL_GL_COLUMNS]
            try:
                code_index = control_gl_column_ids.index("Kode")
            except ValueError:
                code_index = -1
            if code_index >= 0 and len(control_gl_values) > code_index:
                raw_code = str(control_gl_values[code_index]).strip()
                numeric_probe = raw_code.replace(" ", "").replace("\xa0", "").replace(",", ".")
                if raw_code and not numeric_probe.replace(".", "", 1).replace("-", "", 1).isdigit():
                    kode = raw_code

        unmapped_values = self._selected_tree_values(self.tree_unmapped)
        if unmapped_values and konto is None:
            konto = str(unmapped_values[0]).strip() or None

        mapping_values = self._selected_tree_values(self.tree_mapping)
        if mapping_values:
            if konto is None:
                konto = str(mapping_values[0]).strip() or None
            if kode is None and len(mapping_values) >= 3:
                kode = str(mapping_values[2]).strip() or None

        control_account_values = self._selected_tree_values(self.tree_control_accounts)
        if control_account_values and konto is None:
            konto = str(control_account_values[0]).strip() or None

        if kode is None:
            select_code = getattr(self, "_selected_code_from_tree", None)
            if callable(select_code):
                try:
                    kode = select_code(self.tree_a07)
                except Exception:
                    kode = None
        if kode is None:
            for tree in (
                self.tree_control_suggestions,
                self.tree_suggestions,
            ):
                values = self._selected_tree_values(tree)
                if values:
                    kode = str(values[0]).strip() or None
                    if kode:
                        break

        return konto, kode

    def _focus_mapping_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            self.tree_mapping.selection_set(konto_s)
            self.tree_mapping.focus(konto_s)
            self.tree_mapping.see(konto_s)
        except Exception:
            pass
        try:
            children = self.tree_control_gl.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            try:
                changed = False
                if bool(self.control_gl_unmapped_only_var.get()):
                    self.control_gl_unmapped_only_var.set(False)
                    changed = True
                if str(self.control_gl_filter_var.get() or "").strip():
                    self.control_gl_filter_var.set("")
                    changed = True
                if changed:
                    self._refresh_control_gl_tree()
            except Exception:
                pass
        try:
            self.tree_control_gl.selection_set(konto_s)
            self.tree_control_gl.focus(konto_s)
            self.tree_control_gl.see(konto_s)
        except Exception:
            return
        self._sync_control_account_selection(konto_s)

    def _focus_control_code(self, code: str | None) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._pending_focus_code = code_s
            return
        try:
            children = self.tree_a07.get_children()
        except Exception:
            children = ()
        if code_s not in children:
            try:
                self.a07_filter_var.set("alle")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["alle"])
            except Exception:
                pass
            self._schedule_a07_refresh(
                delay_ms=1,
                on_complete=lambda code=code_s: self._focus_control_code(code),
            )
            return
        if not self._set_tree_selection(self.tree_a07, code_s):
            return
        try:
            if code_s in self.tree_groups.get_children():
                self._set_tree_selection(self.tree_groups, code_s)
        except Exception:
            pass
        try:
            self.after_idle(self._on_control_selection_changed)
        except Exception:
            self._on_control_selection_changed()

    def _selected_control_account_ids(self) -> list[str]:
        try:
            selection = self.tree_control_accounts.selection()
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

    def _sync_control_account_selection(self, konto: str | None) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            children = self.tree_control_accounts.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            return
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            selector(self.tree_control_accounts, konto_s)
            return
        try:
            self.tree_control_accounts.selection_set(konto_s)
            self.tree_control_accounts.focus(konto_s)
            self.tree_control_accounts.see(konto_s)
        except Exception:
            pass

    def _focus_selected_control_account_in_gl(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_accounts", None)):
            return
        accounts = self._selected_control_account_ids()
        if not accounts:
            return
        self._focus_mapping_account(accounts[0])

    def _remove_selected_control_accounts(self) -> None:
        accounts = self._selected_control_account_ids()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst forst.",
                focus_widget=self.tree_control_accounts,
            )
            return

        remover = getattr(self, "_remove_mapping_accounts_checked", None)
        if callable(remover):
            remover(
                accounts,
                focus_widget=self.tree_control_accounts,
                refresh="all",
                source_label="Fjernet mapping fra",
            )
            return

        removed = remove_mapping_accounts(self.workspace.mapping, accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen kode a fjerne.",
                focus_widget=self.tree_control_accounts,
            )
            return

        try:
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er).")
            self._select_primary_tab()
        except Exception as exc:
            self._notify_inline(
                f"Kunne ikke fjerne mapping fra konto: {exc}",
                focus_widget=self.tree_control_accounts,
                use_dialog=True,
            )

    def _focus_unmapped_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        self._set_tree_selection(self.tree_unmapped, konto_s)

    def _start_unmapped_drag(self, event: tk.Event | None = None) -> None:
        account = self._tree_iid_from_event(self.tree_unmapped, event)
        self._drag_unmapped_account = account
        self._drag_control_accounts = []
        self.control_drag_var.set(f"Dra konto {account} til kode i arbeidslisten." if account else "")
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel" if account else "Muted.TLabel")
        except Exception:
            pass

    def _start_control_gl_drag(self, event: tk.Event | None = None) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            account = self._tree_iid_from_event(self.tree_control_gl, event)
            if account:
                self._set_tree_selection(self.tree_control_gl, account)
                accounts = [account]
        self._drag_control_accounts = [str(account).strip() for account in accounts if str(account).strip()]
        self._drag_unmapped_account = None
        if not self._drag_control_accounts:
            self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
            try:
                self.lbl_control_drag.configure(style="Muted.TLabel")
            except Exception:
                pass
            return
        if len(self._drag_control_accounts) == 1:
            hint = f"Dra konto {self._drag_control_accounts[0]} til kode til hoyre."
        else:
            hint = f"Dra {len(self._drag_control_accounts)} kontoer til kode til hoyre."
        self.control_drag_var.set(hint)
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel")
        except Exception:
            pass

    def _current_drag_accounts(self) -> list[str]:
        if self._drag_control_accounts:
            return [str(account).strip() for account in self._drag_control_accounts if str(account).strip()]
        account = str(self._drag_unmapped_account or "").strip()
        return [account] if account else []

    def _clear_control_drag_state(self) -> None:
        self._drag_unmapped_account = None
        self._drag_control_accounts = []
        self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
        try:
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass

    def _track_unmapped_drop_target(self, event: tk.Event | None = None) -> None:
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            return
        code = self._tree_iid_from_event(self.tree_a07, event)
        if not code:
            return
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            selector(self.tree_a07, code)
        else:
            try:
                self.tree_a07.selection_set(code)
                self.tree_a07.focus(code)
                self.tree_a07.see(code)
            except Exception:
                pass
        if len(accounts) == 1:
            hint = f"Slipp konto {accounts[0]} pa kode {code}."
        else:
            hint = f"Slipp {len(accounts)} kontoer pa kode {code}."
        self.control_drag_var.set(hint)
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel")
        except Exception:
            pass
