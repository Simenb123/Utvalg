from __future__ import annotations

from .selection_shared import *  # noqa: F403


class A07PageSelectionTreeMixin:
    def _selected_control_code(self) -> str | None:
        if self._selected_control_work_level() == "a07":
            return self._selected_code_from_tree(self.tree_a07)
        group_id = self._selected_rf1022_group()
        return self._first_control_code_for_group(group_id)

    def _tree_selection_key(self, tree: ttk.Treeview | None) -> str:
        try:
            return str(tree) if tree is not None else ""
        except Exception:
            return ""

    def _release_tree_selection_suppression(self, tree: ttk.Treeview | None) -> None:
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.discard(key)

    def _is_tree_selection_suppressed(self, tree: ttk.Treeview | None) -> bool:
        key = self._tree_selection_key(tree)
        return bool(key) and key in self._suppressed_tree_select_keys

    def _set_tree_selection(
        self,
        tree: ttk.Treeview,
        target: str | None,
        *,
        reveal: bool = False,
        focus: bool = False,
    ) -> bool:
        target_s = str(target or "").strip()
        if not target_s:
            return False
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.add(key)
        previous = bool(getattr(self, "_suspend_selection_sync", False))
        self._suspend_selection_sync = True
        try:
            tree.selection_set(target_s)
            if focus:
                tree.focus(target_s)
            if reveal:
                tree.see(target_s)
            try:
                self.after_idle(lambda t=tree: self._release_tree_selection_suppression(t))
            except Exception:
                self._release_tree_selection_suppression(tree)
            return True
        except Exception:
            self._release_tree_selection_suppression(tree)
            return False
        finally:
            self._suspend_selection_sync = previous

