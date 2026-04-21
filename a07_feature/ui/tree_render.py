from __future__ import annotations

import time
from decimal import Decimal
from tkinter import ttk
from typing import Callable, Sequence

import pandas as pd

from formatting import format_number_no

from ..page_a07_dialogs import _numeric_decimals_for_column


class A07PageTreeRenderMixin:
    def _fill_tree(
        self,
        tree: ttk.Treeview,
        df: pd.DataFrame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        iid_column: str | None = None,
        row_tag_fn: Callable[[pd.Series], str | None] | None = None,
    ) -> None:
        start_ts = time.perf_counter()
        tree_name = self._tree_debug_name(tree)
        row_count = 0 if df is None else int(len(df.index))
        self._diag(f"fill_tree start tree={tree_name} rows={row_count}")
        children = tree.get_children()
        if children:
            tree.delete(*children)

        if df is None or df.empty:
            self._diag(
                f"fill_tree done tree={tree_name} rows=0 elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            return

        used_iids: set[str] = set()
        for idx, row in df.iterrows():
            values = [self._format_value(row.get(column_id), column_id) for column_id, *_rest in columns]
            iid = self._normalize_tree_iid(row, idx, iid_column, used_iids)
            tags: tuple[str, ...] = ()
            if row_tag_fn is not None:
                try:
                    tag = row_tag_fn(row)
                except Exception:
                    tag = None
                if tag:
                    tags = (str(tag),)
            self._insert_tree_row(tree, iid=iid, values=values, tags=tags)
        self._diag(
            f"fill_tree done tree={tree_name} rows={row_count} elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
        )

    def _tree_fill_key(self, tree: ttk.Treeview) -> str:
        try:
            return str(tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _cancel_tree_fill(self, tree: ttk.Treeview) -> None:
        key = self._tree_fill_key(tree)
        job = self._tree_fill_jobs.pop(key, None)
        if job is None:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass

    def _normalize_tree_iid(
        self,
        row: pd.Series,
        idx: object,
        iid_column: str | None,
        used_iids: set[str],
    ) -> str:
        base_iid = str(idx)
        if iid_column:
            try:
                candidate = str(row.get(iid_column, "") or "").strip()
            except Exception:
                candidate = ""
            if candidate:
                base_iid = candidate

        iid = base_iid
        suffix = 2
        while iid in used_iids:
            iid = f"{base_iid}__{suffix}"
            suffix += 1
        used_iids.add(iid)
        return iid

    def _insert_tree_row(
        self,
        tree: ttk.Treeview,
        *,
        iid: str,
        values: Sequence[object],
        tags: tuple[str, ...],
    ) -> None:
        try:
            tree.insert("", "end", iid=iid, values=values, tags=tags)
        except Exception:
            try:
                tree.insert("", "end", values=values, tags=tags)
            except Exception:
                pass

    def _fill_tree_chunked(
        self,
        tree: ttk.Treeview,
        df: pd.DataFrame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        iid_column: str | None = None,
        row_tag_fn: Callable[[pd.Series], str | None] | None = None,
        on_complete: Callable[[], None] | None = None,
        batch_size: int = 60,
    ) -> None:
        start_ts = time.perf_counter()
        tree_name = self._tree_debug_name(tree)
        self._cancel_tree_fill(tree)
        key = self._tree_fill_key(tree)
        token = int(self._tree_fill_tokens.get(key, 0)) + 1
        self._tree_fill_tokens[key] = token

        children = tree.get_children()
        if children:
            tree.delete(*children)

        if df is None or df.empty:
            self._diag(
                f"fill_tree_chunked done tree={tree_name} rows=0 elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            if on_complete is not None:
                try:
                    self.after_idle(on_complete)
                except Exception:
                    on_complete()
            return

        total = len(df.index)
        self._diag(f"fill_tree_chunked start tree={tree_name} rows={total} batch_size={batch_size}")
        state = {"index": 0, "used_iids": set()}
        column_ids = [column_id for column_id, *_rest in columns]

        def _run_batch() -> None:
            if self._tree_fill_tokens.get(key) != token:
                self._tree_fill_jobs.pop(key, None)
                return
            start = int(state["index"])
            end = min(start + max(1, int(batch_size)), total)
            chunk = df.iloc[start:end]
            for idx, row in chunk.iterrows():
                values = [self._format_value(row.get(column_id), column_id) for column_id in column_ids]
                iid = self._normalize_tree_iid(row, idx, iid_column, state["used_iids"])
                tags: tuple[str, ...] = ()
                if row_tag_fn is not None:
                    try:
                        tag = row_tag_fn(row)
                    except Exception:
                        tag = None
                    if tag:
                        tags = (str(tag),)
                self._insert_tree_row(tree, iid=iid, values=values, tags=tags)
            state["index"] = end
            if end < total:
                self._tree_fill_jobs[key] = self.after(1, _run_batch)
                return
            self._tree_fill_jobs.pop(key, None)
            self._diag(
                f"fill_tree_chunked done tree={tree_name} rows={total} elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            if on_complete is not None:
                try:
                    self.after_idle(on_complete)
                except Exception:
                    on_complete()

        try:
            self._tree_fill_jobs[key] = self.after_idle(_run_batch)
        except Exception:
            _run_batch()

    def _format_value(self, value: object, column_id: str) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Ja" if value else "Nei"
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        decimals = _numeric_decimals_for_column(column_id)
        if decimals is not None:
            if isinstance(value, Decimal):
                return format_number_no(value, decimals)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return format_number_no(value, decimals)
            if isinstance(value, str):
                formatted = format_number_no(value, decimals)
                return formatted if formatted != value else value

        return str(value)
