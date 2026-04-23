from __future__ import annotations

import re
import tkinter as tk
from tkinter import ttk
from typing import Sequence

import pandas as pd

from ..page_a07_constants import (
    _CONTROL_DRAG_IDLE_HINT,
    _CONTROL_GL_COLUMNS,
    _CONTROL_GL_MAPPING_LABELS,
    _CONTROL_GL_SERIES_LABELS,
    _CONTROL_VIEW_LABELS,
    _MAPPING_COLUMNS,
    _SUMMARY_TOTAL_TAG,
)
from ..page_a07_dialogs import remove_mapping_accounts
from ..page_a07_env import messagebox


class A07PageUiHelpersMixin:
    def _build_tree_tab(self, parent: ttk.Frame, columns: Sequence[tuple[str, str, int, str]]) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings")
        self._configure_sortable_tree_columns(tree, columns)

        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        return tree

    def _configure_sortable_tree_columns(
        self,
        tree: ttk.Treeview,
        columns: Sequence[tuple[str, str, int, str]],
    ) -> None:
        for column_id, heading, width, anchor in columns:
            tree.heading(
                column_id,
                text=heading,
                command=lambda col=column_id: self._sort_tree_by_column(tree, col),
            )
            tree.column(column_id, width=width, anchor=anchor)

    def _reconfigure_tree_columns(
        self,
        tree: ttk.Treeview,
        columns: Sequence[tuple[str, str, int, str]],
    ) -> None:
        column_ids = [column_id for column_id, *_rest in columns]
        tree.configure(columns=column_ids, displaycolumns=column_ids)
        self._configure_sortable_tree_columns(tree, columns)
        for column_id, _heading, _width, _anchor in columns:
            tree.column(column_id, stretch=True)

    def _tree_sort_state(self) -> dict[str, tuple[str, bool]]:
        state = getattr(self, "_tree_sort_state_by_key", None)
        if not isinstance(state, dict):
            state = {}
            setattr(self, "_tree_sort_state_by_key", state)
        return state

    def _tree_sort_key(self, tree: ttk.Treeview) -> str:
        try:
            return str(tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _tree_sort_columns(self, tree: ttk.Treeview) -> tuple[str, ...]:
        try:
            columns = tree["columns"]
        except Exception:
            return ()
        if isinstance(columns, str):
            return tuple(part for part in columns.split() if part)
        return tuple(str(part) for part in columns)

    def _tree_sort_value(self, value: object) -> tuple[int, float | str]:
        text = str(value or "").strip().replace("\xa0", " ")
        compact = text.replace(" ", "")
        if compact:
            numeric = compact.replace(",", ".")
            if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", numeric):
                try:
                    return (0, float(numeric))
                except Exception:
                    pass
        return (1, text.casefold())

    def _tree_item_has_tag(self, tree: ttk.Treeview, item: str, tag: str) -> bool:
        try:
            tags = tree.item(item, "tags") or ()
        except Exception:
            tags = ()
        if isinstance(tags, str):
            tag_values = {tags}
        else:
            tag_values = {str(value) for value in tags}
        return str(tag) in tag_values

    def _sort_tree_by_column(self, tree: ttk.Treeview, column_id: str) -> None:
        columns = self._tree_sort_columns(tree)
        if column_id not in columns:
            return
        col_index = columns.index(column_id)
        tree_key = self._tree_sort_key(tree)
        current_column, ascending = self._tree_sort_state().get(tree_key, ("", True))
        next_ascending = not ascending if current_column == column_id else True

        try:
            children = list(tree.get_children(""))
        except Exception:
            children = list(tree.get_children())
        if not children:
            self._tree_sort_state()[tree_key] = (column_id, next_ascending)
            return
        summary_children = [item for item in children if self._tree_item_has_tag(tree, item, _SUMMARY_TOTAL_TAG)]
        sortable_children = [item for item in children if item not in summary_children]

        def value_for(item: str) -> tuple[int, float | str]:
            try:
                raw = tree.set(item, column_id)
            except Exception:
                try:
                    values = list(tree.item(item, "values") or ())
                    raw = values[col_index] if len(values) > col_index else ""
                except Exception:
                    raw = ""
            return self._tree_sort_value(raw)

        ordered = sorted(sortable_children, key=value_for, reverse=not next_ascending) + summary_children
        for index, item in enumerate(ordered):
            try:
                tree.move(item, "", index)
            except Exception:
                break
        self._tree_sort_state()[tree_key] = (column_id, next_ascending)

    def _apply_tree_sort_if_active(self, tree: ttk.Treeview) -> None:
        column, ascending = self._tree_sort_state().get(self._tree_sort_key(tree), ("", True))
        if not column:
            return
        self._tree_sort_state()[self._tree_sort_key(tree)] = (column, not ascending)
        self._sort_tree_by_column(tree, column)

    def _selected_tree_values(self, tree: ttk.Treeview) -> tuple[str, ...]:
        selection = tree.selection()
        if not selection:
            return ()
        values = tree.item(selection[0], "values")
        return tuple(str(value) for value in (values or ()))

    def _selected_suggestion_row_from_tree(self, tree: ttk.Treeview) -> pd.Series | None:
        selection = tree.selection()
        if not selection:
            return None

        selected_id = str(selection[0]).strip()
        if not selected_id:
            return None

        selected_work_level = getattr(self, "_selected_control_work_level", None)
        try:
            if callable(selected_work_level) and selected_work_level() == "rf1022":
                candidates = getattr(self, "rf1022_candidate_df", None)
                if isinstance(candidates, pd.DataFrame) and not candidates.empty and "Konto" in candidates.columns:
                    matches = candidates.loc[candidates["Konto"].astype(str).str.strip() == selected_id]
                    if not matches.empty:
                        return matches.iloc[0]
        except Exception:
            pass

        if self.workspace.suggestions is None or self.workspace.suggestions.empty:
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
        def _is_summary_iid(iid: str) -> bool:
            tag_checker = getattr(self, "_tree_item_has_tag", None)
            if callable(tag_checker):
                try:
                    return bool(tag_checker(tree, iid, _SUMMARY_TOTAL_TAG))
                except Exception:
                    return False
            return False

        if event is not None:
            identify_row = getattr(tree, "identify_row", None)
            if callable(identify_row):
                try:
                    iid = str(identify_row(getattr(event, "y", 0)) or "").strip()
                except Exception:
                    iid = ""
                if iid:
                    return None if _is_summary_iid(iid) else iid

        selection = tree.selection()
        if not selection:
            return None
        iid = str(selection[0]).strip()
        if not iid or _is_summary_iid(iid):
            return None
        return iid

    def _manual_mapping_defaults(
        self,
        *,
        preferred_account: str | None = None,
        preferred_code: str | None = None,
    ) -> tuple[str | None, str | None]:
        konto = str(preferred_account or "").strip() or None
        kode = str(preferred_code or "").strip() or None

        control_gl_values = self._selected_tree_values(self.tree_control_gl)
        if control_gl_values and konto is None:
            konto = str(control_gl_values[0]).strip() or None
            control_gl_column_ids = [column_id for column_id, *_rest in _CONTROL_GL_COLUMNS]
            try:
                code_index = control_gl_column_ids.index("Kode")
            except ValueError:
                code_index = -1
            if kode is None and code_index >= 0 and len(control_gl_values) > code_index:
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
            if kode is None:
                mapping_column_ids = [column_id for column_id, *_rest in _MAPPING_COLUMNS]
                try:
                    code_index = mapping_column_ids.index("Kode")
                except ValueError:
                    code_index = -1
                if code_index >= 0 and len(mapping_values) > code_index:
                    kode = str(mapping_values[code_index]).strip() or None

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
            for tree in (self.tree_control_suggestions, self.tree_suggestions):
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
                mapping_var = getattr(self, "control_gl_mapping_filter_var", None)
                mapping_label_var = getattr(self, "control_gl_mapping_filter_label_var", None)
                if mapping_var is not None and str(mapping_var.get() or "").strip() != "alle":
                    mapping_var.set("alle")
                    changed = True
                if mapping_label_var is not None and str(mapping_label_var.get() or "").strip() != _CONTROL_GL_MAPPING_LABELS["alle"]:
                    mapping_label_var.set(_CONTROL_GL_MAPPING_LABELS["alle"])
                    changed = True
                series_var = getattr(self, "control_gl_series_filter_var", None)
                series_label_var = getattr(self, "control_gl_series_filter_label_var", None)
                if series_var is not None and str(series_var.get() or "").strip() != "alle":
                    series_var.set("alle")
                    changed = True
                if series_label_var is not None and str(series_label_var.get() or "").strip() != _CONTROL_GL_SERIES_LABELS["alle"]:
                    series_label_var.set(_CONTROL_GL_SERIES_LABELS["alle"])
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
        selected_work_level = getattr(self, "_selected_control_work_level", None)
        if callable(selected_work_level):
            try:
                if selected_work_level() == "rf1022":
                    control_df = getattr(self, "control_df", None)
                    if control_df is not None and not getattr(control_df, "empty", True):
                        try:
                            matches = control_df.loc[
                                control_df["Kode"].astype(str).str.strip() == code_s
                            ]
                        except Exception:
                            matches = None
                        if matches is not None and not getattr(matches, "empty", True):
                            try:
                                group_id = str(matches.iloc[0].get("Rf1022GroupId") or "").strip()
                            except Exception:
                                group_id = ""
                            if group_id:
                                try:
                                    self.workspace.selected_code = code_s
                                except Exception:
                                    pass
                                self._selected_rf1022_group_id = group_id
                                code_s = group_id
            except Exception:
                pass
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
        if not self._set_tree_selection(self.tree_a07, code_s, reveal=True, focus=True):
            return
        try:
            if code_s in self.tree_groups.get_children():
                self._set_tree_selection(self.tree_groups, code_s, reveal=True, focus=True)
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
            try:
                selector(self.tree_control_accounts, konto_s, reveal=False)
            except TypeError:
                selector(self.tree_control_accounts, konto_s)
            return
        try:
            self.tree_control_accounts.selection_set(konto_s)
            self.tree_control_accounts.focus(konto_s)
            self.tree_control_accounts.see(konto_s)
        except Exception:
            pass

    def _clear_control_gl_selection(self) -> None:
        tree = getattr(self, "tree_control_gl", None)
        if tree is None:
            return
        try:
            selection = tuple(tree.selection())
        except Exception:
            selection = ()
        if selection:
            try:
                tree.selection_remove(selection)
            except Exception:
                try:
                    tree.selection_set(())
                except Exception:
                    pass
        try:
            tree.focus("")
        except Exception:
            pass

    def _focus_selected_control_account_in_gl(self, *, allow_multi: bool = True) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_accounts", None)):
            return
        accounts = self._selected_control_account_ids()
        if not accounts:
            return
        if len(accounts) > 1 and not allow_multi:
            return
        self._focus_mapping_account(accounts[0])

    def _remove_selected_control_accounts(self) -> None:
        accounts = self._selected_control_account_ids()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst først.",
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
                "Valgte kontoer har ingen kode å fjerne.",
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
            messagebox.showerror("A07", f"Kunne ikke fjerne mapping fra konto:\n{exc}")

    def _focus_unmapped_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        self._set_tree_selection(self.tree_unmapped, konto_s, reveal=True, focus=True)

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
            hint = f"Dra konto {self._drag_control_accounts[0]} til kode til høyre."
        else:
            hint = f"Dra {len(self._drag_control_accounts)} kontoer til kode til høyre."
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
        clear_drop_target = getattr(self, "_clear_control_drop_target", None)
        if callable(clear_drop_target):
            clear_drop_target()
        self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
        try:
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass

    def _set_control_drop_target(self, iid: str | None) -> None:
        tree = getattr(self, "tree_a07", None)
        if tree is None:
            self._control_drop_target_iid = None
            return
        try:
            children = set(str(value).strip() for value in tree.get_children())
        except Exception:
            children = set()

        previous_iid = str(getattr(self, "_control_drop_target_iid", "") or "").strip()
        if previous_iid and previous_iid in children:
            try:
                current_tags = tuple(str(tag).strip() for tag in (tree.item(previous_iid, "tags") or ()))
                tree.item(previous_iid, tags=tuple(tag for tag in current_tags if tag and tag != "drop_target"))
            except Exception:
                pass

        target_iid = str(iid or "").strip()
        if not target_iid or target_iid not in children:
            self._control_drop_target_iid = None
            return

        try:
            current_tags = tuple(str(tag).strip() for tag in (tree.item(target_iid, "tags") or ()))
        except Exception:
            current_tags = ()
        normalized_tags = tuple(tag for tag in current_tags if tag and tag != "drop_target")
        try:
            tree.item(target_iid, tags=normalized_tags + ("drop_target",))
        except Exception:
            pass
        self._control_drop_target_iid = target_iid

    def _clear_control_drop_target(self) -> None:
        self._set_control_drop_target(None)

    def _track_unmapped_drop_target(self, event: tk.Event | None = None) -> None:
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            clear_drop_target = getattr(self, "_clear_control_drop_target", None)
            if callable(clear_drop_target):
                clear_drop_target()
            return
        code = self._tree_iid_from_event(self.tree_a07, event)
        if not code:
            clear_drop_target = getattr(self, "_clear_control_drop_target", None)
            if callable(clear_drop_target):
                clear_drop_target()
            return
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            try:
                selector(self.tree_a07, code, reveal=False, focus=False)
            except TypeError:
                selector(self.tree_a07, code)
        else:
            try:
                self.tree_a07.selection_set(code)
                self.tree_a07.focus(code)
                self.tree_a07.see(code)
            except Exception:
                pass
        set_drop_target = getattr(self, "_set_control_drop_target", None)
        if callable(set_drop_target):
            set_drop_target(code)
        if len(accounts) == 1:
            hint = f"Slipp konto {accounts[0]} paa kode {code}."
        else:
            hint = f"Slipp {len(accounts)} kontoer paa kode {code}."
        self.control_drag_var.set(hint)
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel")
        except Exception:
            pass
