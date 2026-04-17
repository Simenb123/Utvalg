from __future__ import annotations

from .page_a07_shared import *  # noqa: F401,F403
from .page_a07_support_render import A07PageSupportRenderMixin
from .page_a07_tree_render import A07PageTreeRenderMixin


class A07PageRenderMixin(A07PageSupportRenderMixin, A07PageTreeRenderMixin):
    def _refresh_a07_tree(self) -> None:
        selected_code = self._selected_code_from_tree(self.tree_a07)
        filtered = filter_control_visible_codes_df(self.control_df)
        filtered = filter_control_queue_df(filtered, self._selected_a07_filter())
        filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
        if (
            filtered.empty
            and self._selected_a07_filter() == "neste"
            and self.control_df is not None
            and not filter_control_visible_codes_df(self.control_df).empty
            and count_pending_control_items(filter_control_visible_codes_df(self.control_df)) == 0
        ):
            self.a07_filter_var.set("ferdig")
            self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["ferdig"])
            try:
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["ferdig"])
            except Exception:
                pass
            filtered = filter_control_queue_df(filter_control_visible_codes_df(self.control_df), "ferdig")
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
        self._fill_tree(
            self.tree_a07,
            filtered,
            _CONTROL_COLUMNS,
            iid_column="Kode",
            row_tag_fn=control_queue_tree_tag,
        )

        children = self.tree_a07.get_children()
        if not children:
            return

        target = selected_code if selected_code and selected_code in children else children[0]
        self._set_tree_selection(self.tree_a07, target)

    def _refresh_a07_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
        selected_code = self._selected_code_from_tree(self.tree_a07)
        filtered = filter_control_visible_codes_df(self.control_df)
        filtered = filter_control_queue_df(filtered, self._selected_a07_filter())
        filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
        if (
            filtered.empty
            and self._selected_a07_filter() == "neste"
            and self.control_df is not None
            and not filter_control_visible_codes_df(self.control_df).empty
            and count_pending_control_items(filter_control_visible_codes_df(self.control_df)) == 0
        ):
            self.a07_filter_var.set("ferdig")
            self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["ferdig"])
            try:
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["ferdig"])
            except Exception:
                pass
            filtered = filter_control_queue_df(filter_control_visible_codes_df(self.control_df), "ferdig")
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_a07.get_children()
                if children:
                    target = selected_code if selected_code and selected_code in children else children[0]
                    self._set_tree_selection(self.tree_a07, target)
            if on_complete is not None:
                on_complete()

        if filtered is None or len(filtered.index) <= 500:
            self._fill_tree(
                self.tree_a07,
                filtered,
                _CONTROL_COLUMNS,
                iid_column="Kode",
                row_tag_fn=control_queue_tree_tag,
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_a07,
            filtered,
            _CONTROL_COLUMNS,
            iid_column="Kode",
            row_tag_fn=control_queue_tree_tag,
            on_complete=_after_fill,
        )

    def _refresh_control_gl_tree(self) -> None:
        selected_account = self._selected_control_gl_account()
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        filtered_gl_df = self._apply_control_gl_scope(filtered_gl_df, selected_code=selected_code)
        self._fill_tree(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
        )

        children = self.tree_control_gl.get_children()
        if not children:
            return

        if selected_account and selected_account in children:
            self._set_tree_selection(self.tree_control_gl, selected_account)
        else:
            self._clear_control_gl_selection()

    def _refresh_control_gl_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
        selected_account = self._selected_control_gl_account()
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        filtered_gl_df = self._apply_control_gl_scope(filtered_gl_df, selected_code=selected_code)

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_control_gl.get_children()
                if children and selected_account and selected_account in children:
                    self._set_tree_selection(self.tree_control_gl, selected_account)
                else:
                    self._clear_control_gl_selection()
            if on_complete is not None:
                on_complete()

        if filtered_gl_df is None or len(filtered_gl_df.index) <= 1200:
            self._fill_tree(
                self.tree_control_gl,
                filtered_gl_df,
                _CONTROL_GL_COLUMNS,
                iid_column="Konto",
                row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
            on_complete=_after_fill,
        )

    def _retag_control_gl_tree(self) -> bool:
        try:
            tree = self.tree_control_gl
            children = tuple(tree.get_children())
        except Exception:
            return False
        if not children:
            return False

        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        filtered_gl_df = self._apply_control_gl_scope(filtered_gl_df, selected_code=self._selected_code_from_tree(self.tree_a07))
        if filtered_gl_df is None or filtered_gl_df.empty:
            return False

        try:
            filtered_iids = [
                str(row.get("Konto") or "").strip()
                for _, row in filtered_gl_df.iterrows()
                if str(row.get("Konto") or "").strip()
            ]
            if tuple(filtered_iids) != children:
                return False
        except Exception:
            return False

        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        try:
            for _, row in filtered_gl_df.iterrows():
                iid = str(row.get("Konto") or "").strip()
                if not iid:
                    continue
                tag = control_gl_tree_tag(row, selected_code, suggested_accounts)
                tree.item(iid, tags=((str(tag),) if tag else ()))
        except Exception:
            return False
        return True

    def _on_control_gl_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._schedule_control_gl_refresh()
        self._update_control_transfer_buttons()

    def _on_control_code_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)
