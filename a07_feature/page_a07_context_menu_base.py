from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from .page_a07_constants import _SUMMARY_TOTAL_TAG


class A07PageContextMenuBaseMixin:
    def _prepare_tree_context_selection(
        self,
        tree: ttk.Treeview,
        event: tk.Event | None = None,
        *,
        preserve_existing_selection: bool = True,
        on_selected: Callable[[], None] | None = None,
    ) -> str | None:
        iid = self._tree_iid_from_event(tree, event)
        if not iid:
            return None
        tag_checker = getattr(self, "_tree_item_has_tag", None)
        if callable(tag_checker):
            try:
                if tag_checker(tree, iid, _SUMMARY_TOTAL_TAG):
                    return None
            except Exception:
                pass

        try:
            current_selection = tuple(str(value).strip() for value in tree.selection())
        except Exception:
            current_selection = ()
        already_selected = iid in current_selection

        try:
            if preserve_existing_selection and already_selected:
                tree.focus(iid)
            else:
                self._set_tree_selection(tree, iid, reveal=False, focus=True)
        except Exception:
            return None

        try:
            tree.focus_set()
        except Exception:
            pass

        if callable(on_selected):
            try:
                on_selected()
            except Exception:
                pass
        return iid

    def _post_context_menu(self, menu: tk.Menu, event: tk.Event) -> str:
        self._active_context_menu = menu
        try:
            menu.tk_popup(int(getattr(event, "x_root", 0)), int(getattr(event, "y_root", 0)))
        finally:
            try:
                menu.grab_release()
            except Exception:
                pass
        return "break"
