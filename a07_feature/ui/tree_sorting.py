from __future__ import annotations

from functools import cmp_to_key
import re
from tkinter import ttk

from ..page_a07_constants import _SUMMARY_TOTAL_TAG


class A07PageTreeSortingMixin:
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

    def _tree_sort_value(self, value: object) -> tuple[bool, int, float | str]:
        text = str(value or "").strip().replace("\u2212", "-")
        compact = re.sub(r"[\s\u00a0\u202f\u2007]", "", text).replace("%", "")
        if not compact:
            return (True, 2, "")
        numeric = compact
        if "," in numeric and "." in numeric:
            numeric = numeric.replace(".", "").replace(",", ".")
        elif "," in numeric:
            numeric = numeric.replace(",", ".")
        elif numeric.count(".") > 1:
            numeric = numeric.replace(".", "")
        elif "." in numeric:
            left, right = numeric.rsplit(".", 1)
            digits_left = left.lstrip("+-").isdigit()
            if digits_left and right.isdigit() and len(right) == 3:
                numeric = left + right
        if re.fullmatch(r"[-+]?\d+(?:\.\d+)?", numeric):
            try:
                return (False, 0, float(numeric))
            except Exception:
                pass
        return (False, 1, text.casefold())

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

        def value_for(item: str) -> tuple[bool, int, float | str]:
            try:
                raw = tree.set(item, column_id)
            except Exception:
                try:
                    values = list(tree.item(item, "values") or ())
                    raw = values[col_index] if len(values) > col_index else ""
                except Exception:
                    raw = ""
            return self._tree_sort_value(raw)

        def compare(left: str, right: str) -> int:
            left_missing, left_type, left_value = value_for(left)
            right_missing, right_type, right_value = value_for(right)
            if left_missing != right_missing:
                return 1 if left_missing else -1
            if left_type != right_type:
                return -1 if left_type < right_type else 1
            if left_value == right_value:
                return 0
            result = -1 if left_value < right_value else 1
            return result if next_ascending else -result

        ordered = sorted(sortable_children, key=cmp_to_key(compare)) + summary_children
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


__all__ = ["A07PageTreeSortingMixin"]
