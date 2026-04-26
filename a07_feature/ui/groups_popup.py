from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..page_a07_constants import _GROUP_COLUMNS


class A07PageGroupsPopupMixin:
    def _build_groups_sidepanel(self, groups_side: ttk.LabelFrame) -> None:
        groups_actions = ttk.Frame(groups_side)
        groups_actions.pack(fill="x", pady=(0, 4))
        self.btn_create_group = ttk.Button(
            groups_actions,
            text="Opprett",
            command=self._create_group_from_selection,
        )
        self.btn_create_group.pack(side="left")
        self.btn_rename_group = ttk.Button(
            groups_actions,
            text="Gi nytt navn",
            command=self._rename_selected_group,
        )
        self.btn_rename_group.pack(side="left", padx=(6, 0))
        self.btn_remove_group = ttk.Button(
            groups_actions,
            text="Oppløs",
            command=self._remove_selected_group,
        )
        self.btn_remove_group.pack(side="left", padx=(6, 0))
        self.btn_focus_group = ttk.Button(
            groups_actions,
            text="Fokuser",
            command=self._focus_selected_group_code,
        )
        self.btn_focus_group.pack(side="left", padx=(6, 0))
        self.tree_groups = self._build_managed_tree_tab(
            groups_side,
            _GROUP_COLUMNS,
            view_id="groups",
            height=6,
        )

    def _open_groups_popup(self, group_id: str | None = None) -> None:
        popup = getattr(self, "_groups_popup", None)
        try:
            popup_exists = bool(popup.winfo_exists()) if popup is not None else False
        except Exception:
            popup_exists = False
        if popup_exists:
            try:
                popup.lift()
                popup.focus_force()
            except Exception:
                pass
            self._select_group_in_popup(group_id)
            return

        popup = tk.Toplevel(self)
        popup.title("A07-grupper")
        popup.geometry("1040x420")
        try:
            popup.transient(self.winfo_toplevel())
        except Exception:
            pass
        popup.protocol("WM_DELETE_WINDOW", self._close_groups_popup)
        self._groups_popup = popup

        body = ttk.Frame(popup, padding=8)
        body.pack(fill="both", expand=True)
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(0, 6))
        self.btn_create_group = ttk.Button(actions, text="Opprett", command=self._create_group_from_selection)
        self.btn_create_group.pack(side="left")
        self.btn_rename_group = ttk.Button(actions, text="Gi nytt navn", command=self._rename_selected_group)
        self.btn_rename_group.pack(side="left", padx=(6, 0))
        self.btn_remove_group = ttk.Button(actions, text="Oppløs", command=self._remove_selected_group)
        self.btn_remove_group.pack(side="left", padx=(6, 0))
        self.btn_focus_group = ttk.Button(actions, text="Fokuser", command=self._focus_selected_group_code)
        self.btn_focus_group.pack(side="left", padx=(6, 0))

        self.tree_groups = self._build_managed_tree_tab(
            body,
            _GROUP_COLUMNS,
            view_id="groups",
            height=10,
            selectmode="browse",
        )
        self._bind_groups_tree_events()
        self._refresh_groups_tree(force=True)
        self._select_group_in_popup(group_id)

    def _close_groups_popup(self) -> None:
        popup = getattr(self, "_groups_popup", None)
        self._groups_popup = None
        self.tree_groups = None
        self.btn_create_group = None
        self.btn_rename_group = None
        self.btn_remove_group = None
        self.btn_focus_group = None
        if popup is not None:
            try:
                popup.destroy()
            except Exception:
                pass

    def _select_group_in_popup(self, group_id: str | None) -> None:
        group_s = str(group_id or "").strip()
        if not group_s:
            return
        tree_groups = getattr(self, "tree_groups", None)
        if tree_groups is None:
            return
        try:
            children = tree_groups.get_children()
        except Exception:
            children = ()
        if group_s not in children:
            return
        try:
            self._set_tree_selection(tree_groups, group_s, reveal=True, focus=True)
        except TypeError:
            self._set_tree_selection(tree_groups, group_s)

    def _on_a07_tree_double_click(self, event: tk.Event) -> str | None:
        try:
            iid = str(self.tree_a07.identify_row(event.y) or "").strip()
        except Exception:
            iid = ""
        if iid:
            try:
                self._set_tree_selection(self.tree_a07, iid, reveal=False)
            except TypeError:
                self._set_tree_selection(self.tree_a07, iid)
            except Exception:
                pass
        code = iid or str(self._selected_control_code() or "").strip()
        if code.startswith("A07_GROUP:"):
            self._open_groups_popup(code)
            return "break"
        self._link_selected_control_rows()
        return "break"


__all__ = ["A07PageGroupsPopupMixin"]
