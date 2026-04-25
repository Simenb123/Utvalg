from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import pandas as pd

from ..page_a07_constants import _SUMMARY_TOTAL_TAG


class A07PageTreeSelectionHelpersMixin:
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


__all__ = ["A07PageTreeSelectionHelpersMixin"]
