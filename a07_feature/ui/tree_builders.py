from __future__ import annotations

from tkinter import ttk
from typing import Sequence


class A07PageTreeBuilderMixin:
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


__all__ = ["A07PageTreeBuilderMixin"]
