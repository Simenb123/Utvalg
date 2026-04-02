"""Tests for treeview_column_manager.py — TreeviewColumnManager."""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tree(columns):
    """Create a mock Treeview with headings."""
    tree = MagicMock()
    tree.__setitem__ = MagicMock()
    tree.__getitem__ = MagicMock(return_value=list(columns))
    # heading() returns display text
    heading_map = {c: c.upper() for c in columns}
    tree.heading.side_effect = lambda col, *a, **kw: heading_map.get(col, col)
    tree.identify_region.return_value = "heading"
    return tree


def _make_mgr(tree=None, *, all_cols=("a", "b", "c"), default_visible=None,
              pinned_cols=(), view_id="test",
              stored_visible=None, stored_order=None):
    """Create a TreeviewColumnManager with optional stored preferences.

    stored_visible: simulated saved visible cols list (or None for no saved prefs)
    stored_order: simulated saved column order list (or None for no saved order)
    """
    from treeview_column_manager import TreeviewColumnManager

    if tree is None:
        tree = _make_tree(all_cols)

    with patch("treeview_column_manager.TreeviewColumnManager.load_from_preferences"):
        mgr = TreeviewColumnManager(
            tree, view_id=view_id, all_cols=all_cols,
            default_visible=default_visible, pinned_cols=pinned_cols,
        )

    # If stored prefs were requested, simulate loading them
    if stored_visible is not None or stored_order is not None:
        pref_map = {
            mgr._pref_key: stored_visible,
            mgr._order_key: stored_order,
        }
        with patch("preferences.get", side_effect=lambda k, d=None: pref_map.get(k, d)):
            mgr.load_from_preferences()
            mgr.apply_visible()

    return mgr


# ---------------------------------------------------------------------------
# Tests: Init and defaults
# ---------------------------------------------------------------------------

class TestInit:
    def test_default_visible_is_all_cols(self):
        mgr = _make_mgr(all_cols=("x", "y", "z"))
        assert mgr._visible == ["x", "y", "z"]

    def test_default_order_is_all_cols(self):
        mgr = _make_mgr(all_cols=("x", "y", "z"))
        assert mgr._order == ["x", "y", "z"]

    def test_custom_default_visible(self):
        mgr = _make_mgr(all_cols=("x", "y", "z"), default_visible=("x", "z"))
        assert mgr._visible == ["x", "z"]

    def test_pinned_cols_stored(self):
        mgr = _make_mgr(pinned_cols=("a",))
        assert mgr._pinned == {"a"}

    def test_apply_visible_sets_displaycolumns(self):
        tree = _make_tree(("a", "b", "c"))
        mgr = _make_mgr(tree=tree)
        mgr.apply_visible()
        tree.__setitem__.assert_called_with("displaycolumns", ["a", "b", "c"])


# ---------------------------------------------------------------------------
# Tests: Toggle
# ---------------------------------------------------------------------------

class TestToggle:
    def test_toggle_off(self):
        mgr = _make_mgr()
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("b")
        assert "b" not in mgr._visible
        assert mgr._visible == ["a", "c"]

    def test_toggle_on(self):
        mgr = _make_mgr()
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("b")  # off
            mgr.toggle_column("b")  # on again
        assert mgr._visible == ["a", "b", "c"]

    def test_toggle_pinned_does_nothing(self):
        mgr = _make_mgr(pinned_cols=("a",))
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("a")
        assert "a" in mgr._visible

    def test_toggle_preserves_order(self):
        mgr = _make_mgr(all_cols=("a", "b", "c", "d"))
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("b")  # off
            mgr.toggle_column("c")  # off
            mgr.toggle_column("b")  # on → should be before d
        assert mgr._visible == ["a", "b", "d"]

    def test_toggle_respects_custom_order(self):
        """After user reorders columns, toggle-on should use the custom order."""
        mgr = _make_mgr(all_cols=("a", "b", "c", "d"))
        mgr._order = ["d", "c", "b", "a"]  # reversed order
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("c")  # off
            mgr.toggle_column("c")  # on → in custom order, c is before b and a
        # c should be before b in visible list (d, c, b, a order)
        assert mgr._visible.index("c") < mgr._visible.index("b")


# ---------------------------------------------------------------------------
# Tests: Reset
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_restores_defaults(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"), default_visible=("a", "c"))
        with patch.object(mgr, "save_to_preferences"):
            mgr._visible = ["a"]
            mgr.reset_to_default()
        assert mgr._visible == ["a", "c"]

    def test_reset_restores_order(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        with patch.object(mgr, "save_to_preferences"):
            mgr._order = ["c", "b", "a"]
            mgr.reset_to_default()
        assert mgr._order == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Tests: Column order
# ---------------------------------------------------------------------------

class TestColumnOrder:
    def test_apply_uses_order_for_displaycolumns(self):
        tree = _make_tree(("a", "b", "c"))
        mgr = _make_mgr(tree=tree)
        mgr._order = ["c", "b", "a"]
        mgr.apply_visible()
        tree.__setitem__.assert_called_with("displaycolumns", ["c", "b", "a"])

    def test_apply_with_partial_visibility_respects_order(self):
        tree = _make_tree(("a", "b", "c"))
        mgr = _make_mgr(tree=tree)
        mgr._order = ["c", "b", "a"]
        mgr._visible = ["a", "c"]  # b hidden
        mgr.apply_visible()
        tree.__setitem__.assert_called_with("displaycolumns", ["c", "a"])

    def test_chooser_dialog_saves_order(self):
        """open_chooser_dialog should store both order and visible from dialog result."""
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        with patch("views_column_chooser.open_column_chooser",
                    return_value=(["c", "a", "b"], ["c", "b"])):
            with patch.object(mgr, "save_to_preferences") as mock_save:
                mgr.open_chooser_dialog()
        assert mgr._order == ["c", "a", "b"]
        assert mgr._visible == ["c", "b"]
        mock_save.assert_called_once()

    def test_chooser_dialog_none_result_no_change(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        original_order = list(mgr._order)
        original_visible = list(mgr._visible)
        with patch("views_column_chooser.open_column_chooser", return_value=None):
            mgr.open_chooser_dialog()
        assert mgr._order == original_order
        assert mgr._visible == original_visible


# ---------------------------------------------------------------------------
# Tests: Preferences persistence
# ---------------------------------------------------------------------------

class TestPreferences:
    def test_load_valid_prefs(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"), stored_visible=["a", "c"])
        assert mgr._visible == ["a", "c"]

    def test_load_prefs_with_invalid_cols_filters_them(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"), stored_visible=["a", "gone", "c"])
        assert mgr._visible == ["a", "c"]

    def test_load_empty_prefs_uses_defaults(self):
        mgr = _make_mgr(all_cols=("a", "b"), stored_visible=[])
        assert mgr._visible == ["a", "b"]

    def test_load_none_prefs_uses_defaults(self):
        mgr = _make_mgr(all_cols=("a", "b"), stored_visible=None)
        assert mgr._visible == ["a", "b"]

    def test_load_prefs_ensures_pinned(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"), pinned_cols=("a",),
                         stored_visible=["b", "c"])
        assert "a" in mgr._visible
        assert mgr._visible[0] == "a"

    def test_save_stores_both_visible_and_order(self):
        mgr = _make_mgr(view_id="myview")
        mgr._visible = ["a", "c"]
        mgr._order = ["c", "a", "b"]
        with patch("preferences.set") as mock_set:
            mgr.save_to_preferences()
            assert mock_set.call_count == 2
            mock_set.assert_any_call("consolidation.myview.visible_cols", ["a", "c"])
            mock_set.assert_any_call("consolidation.myview.column_order", ["c", "a", "b"])

    def test_load_restores_saved_order(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"),
                         stored_visible=["a", "c"],
                         stored_order=["c", "b", "a"])
        assert mgr._order == ["c", "b", "a"]

    def test_load_order_with_missing_cols_appends_them(self):
        """Stored order missing 'b' → 'b' appended at end."""
        mgr = _make_mgr(all_cols=("a", "b", "c"),
                         stored_order=["c", "a"])
        assert mgr._order == ["c", "a", "b"]

    def test_load_order_with_extra_cols_filters_them(self):
        """Stored order has 'gone' → filtered out."""
        mgr = _make_mgr(all_cols=("a", "b", "c"),
                         stored_order=["c", "gone", "a", "b"])
        assert mgr._order == ["c", "a", "b"]

    def test_load_no_stored_order_uses_all_cols(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"), stored_order=None)
        assert mgr._order == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Tests: update_columns (dynamic trees)
# ---------------------------------------------------------------------------

class TestUpdateColumns:
    def test_new_cols_added_as_visible(self):
        mgr = _make_mgr(all_cols=("a", "b"))
        mgr.update_columns(("a", "b", "c"))
        assert "c" in mgr._visible
        assert mgr._all_cols == ["a", "b", "c"]

    def test_removed_cols_pruned(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        mgr.update_columns(("a", "c"))
        assert "b" not in mgr._visible
        assert mgr._all_cols == ["a", "c"]

    def test_pinned_always_included(self):
        mgr = _make_mgr(all_cols=("a", "b"), pinned_cols=("a",))
        with patch.object(mgr, "save_to_preferences"):
            mgr.toggle_column("b")  # hide b
        mgr.update_columns(("a", "b", "c"))
        assert "a" in mgr._visible

    def test_update_sets_new_default_visible(self):
        mgr = _make_mgr(all_cols=("a", "b"))
        mgr.update_columns(("x", "y"))
        assert mgr._default_visible == ["x", "y"]

    def test_update_preserves_order_for_existing_cols(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        mgr._order = ["c", "b", "a"]
        mgr.update_columns(("a", "b", "c", "d"))
        # c, b, a should keep their order, d appended
        assert mgr._order == ["c", "b", "a", "d"]

    def test_update_removes_gone_cols_from_order(self):
        mgr = _make_mgr(all_cols=("a", "b", "c"))
        mgr._order = ["c", "b", "a"]
        mgr.update_columns(("a", "c"))
        assert mgr._order == ["c", "a"]


# ---------------------------------------------------------------------------
# Tests: Header right-click detection
# ---------------------------------------------------------------------------

class TestHeaderDetection:
    def test_on_right_click_heading_returns_break(self):
        tree = _make_tree(("a", "b"))
        tree.identify_region.return_value = "heading"
        mgr = _make_mgr(tree=tree)

        event = MagicMock()
        result = mgr.on_right_click(event)
        assert result == "break"

    def test_on_right_click_cell_returns_none(self):
        tree = _make_tree(("a", "b"))
        tree.identify_region.return_value = "cell"
        mgr = _make_mgr(tree=tree)

        event = MagicMock()
        result = mgr.on_right_click(event)
        assert result is None

    def test_on_right_click_tree_region_returns_none(self):
        tree = _make_tree(("a", "b"))
        tree.identify_region.return_value = "tree"
        mgr = _make_mgr(tree=tree)

        event = MagicMock()
        result = mgr.on_right_click(event)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: Pinned-first guarantee
# ---------------------------------------------------------------------------

class TestPinnedFirst:
    """Pinned columns must always come first in order, after every mutation."""

    def test_init_pinned_first_in_order(self):
        mgr = _make_mgr(all_cols=("x", "pinA", "y", "pinB"),
                         pinned_cols=("pinA", "pinB"))
        assert mgr._order[0] in ("pinA", "pinB")
        assert mgr._order[1] in ("pinA", "pinB")
        assert set(mgr._order[:2]) == {"pinA", "pinB"}

    def test_load_prefs_normalizes_order(self):
        """Saved order with pinned not first → normalized after load."""
        mgr = _make_mgr(all_cols=("a", "b", "c"), pinned_cols=("a",),
                         stored_visible=["a", "b", "c"],
                         stored_order=["c", "b", "a"])
        assert mgr._order[0] == "a"

    def test_reset_pinned_first(self):
        mgr = _make_mgr(all_cols=("x", "p", "y"), pinned_cols=("p",))
        with patch.object(mgr, "save_to_preferences"):
            mgr.reset_to_default()
        assert mgr._order[0] == "p"

    def test_update_columns_pinned_first(self):
        mgr = _make_mgr(all_cols=("a", "b"), pinned_cols=("b",))
        mgr.update_columns(("a", "b", "c"))
        assert mgr._order[0] == "b"

    def test_chooser_dialog_normalizes_order(self):
        """Dialog returns order with pinned last → normalized to first."""
        mgr = _make_mgr(all_cols=("a", "b", "c"), pinned_cols=("a",))
        with patch("views_column_chooser.open_column_chooser",
                    return_value=(["c", "b", "a"], ["a", "b", "c"])):
            with patch.object(mgr, "save_to_preferences"):
                mgr.open_chooser_dialog()
        assert mgr._order[0] == "a"
        # rest preserves user order
        assert mgr._order[1:] == ["c", "b"]

    def test_apply_pinned_first_in_displaycolumns(self):
        tree = _make_tree(("p", "a", "b"))
        mgr = _make_mgr(tree=tree, all_cols=("p", "a", "b"), pinned_cols=("p",))
        mgr._order = ["a", "b", "p"]  # wrong order
        mgr._normalize_order()
        mgr.apply_visible()
        tree.__setitem__.assert_called_with("displaycolumns", ["p", "a", "b"])
