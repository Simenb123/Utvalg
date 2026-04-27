"""Tests for ui_managed_treeview.ManagedTreeview.

Focus areas:
1. Construction + ColumnSpec handling
2. Preferences integration (new key scheme)
3. Backward-compat via ``legacy_pref_keys``
4. Width load/save round-trip + validation bounds
5. Binding wiring on the ``tree`` mock

These tests use MagicMock for ttk.Treeview to avoid requiring an actual
Tk display. Integration with a real Treeview is covered by the
consolidation-page tests that already use ManagedTreeview in the wild.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tree(columns=("a", "b", "c")):
    """MagicMock of ttk.Treeview that supports subscript + heading."""
    tree = MagicMock()
    tree.__setitem__ = MagicMock()
    tree.__getitem__ = MagicMock(return_value=list(columns))
    tree.identify_region = MagicMock(return_value="heading")
    tree.heading = MagicMock(return_value="")
    tree.column = MagicMock()
    tree.bind = MagicMock()
    tree.after_idle = MagicMock()
    # after() queues but we don't execute — stabilize_layout only schedules
    tree.after = MagicMock(return_value="after-id")
    return tree


def _make_specs():
    from src.shared.ui.managed_treeview import ColumnSpec
    return [
        ColumnSpec(id="a", heading="A", width=100, visible_by_default=True),
        ColumnSpec(id="b", heading="B", width=120, visible_by_default=True),
        ColumnSpec(id="c", heading="C", width=80, visible_by_default=False),
    ]


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

class TestConstruction:
    def test_minimal_construction(self):
        from src.shared.ui.managed_treeview import ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="test", column_specs=_make_specs(),
                pref_prefix="testui", auto_bind=False,
            )
        assert mt.view_id == "test"
        assert mt.pref_prefix == "testui"
        assert mt._width_pref_key == "testui.test.column_widths"

    def test_column_manager_uses_same_prefix_and_view_id(self):
        from src.shared.ui.managed_treeview import ManagedTreeview
        tree = _make_tree()
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="myview", column_specs=_make_specs(),
                pref_prefix="myapp", auto_bind=False,
            )
        assert mt.column_manager._pref_key == "myapp.myview.visible_cols"
        assert mt.column_manager._order_key == "myapp.myview.column_order"

    def test_str_specs_are_normalized_to_columnspec(self):
        from src.shared.ui.managed_treeview import ManagedTreeview
        tree = _make_tree(("x", "y"))
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="test", column_specs=["x", "y"],
                auto_bind=False,
            )
        assert [s.id for s in mt._specs] == ["x", "y"]
        # default values
        assert all(s.sortable for s in mt._specs)
        assert all(s.visible_by_default for s in mt._specs)

    def test_pinned_cols_propagate_to_manager(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [
            ColumnSpec(id="a", pinned=True),
            ColumnSpec(id="b"),
            ColumnSpec(id="c"),
        ]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="test", column_specs=specs,
                auto_bind=False,
            )
        assert mt._pinned == ("a",)
        assert mt.column_manager._pinned == frozenset({"a"})


# ---------------------------------------------------------------------------
# Width helpers
# ---------------------------------------------------------------------------

class TestWidthHelpers:
    def test_load_widths_strips_bad_values(self):
        from src.shared.ui.managed_treeview import _load_widths
        fake_store = {"mykey": {"a": 100, "b": "bad", "c": 5, "d": 2000, "e": 80}}
        with patch("preferences.get", side_effect=lambda k, d=None: fake_store.get(k, d)):
            got = _load_widths("mykey")
        # 5 is < 40 and 2000 is > 1600 — both rejected. "bad" not int.
        assert got == {"a": 100, "e": 80}

    def test_save_widths_enforces_bounds(self):
        from src.shared.ui.managed_treeview import _save_widths
        saved = {}
        def _setter(k, v):
            saved[k] = v
        with patch("preferences.set", side_effect=_setter):
            _save_widths("mykey", {"a": 100, "b": 5, "c": 2000, "d": "bad"})
        assert saved["mykey"] == {"a": 100}

    def test_load_widths_tolerates_non_dict(self):
        from src.shared.ui.managed_treeview import _load_widths
        with patch("preferences.get", return_value="not-a-dict"):
            assert _load_widths("mykey") == {}


# ---------------------------------------------------------------------------
# Legacy preference-key migration
# ---------------------------------------------------------------------------

class TestLegacyMigration:
    def test_migrates_when_new_missing_and_legacy_present(self):
        from src.shared.ui.managed_treeview import _migrate_legacy_pref_keys
        store = {
            "legacy.visible": ["a", "b"],
            "legacy.order": ["b", "a"],
        }

        def _get(k, d=None):
            return store.get(k, d)

        def _set(k, v):
            store[k] = v

        with patch("preferences.get", side_effect=_get), \
             patch("preferences.set", side_effect=_set):
            _migrate_legacy_pref_keys(
                view_id="myview",
                pref_prefix="ui",
                legacy={
                    "visible_cols": "legacy.visible",
                    "column_order": "legacy.order",
                },
            )
        assert store["ui.myview.visible_cols"] == ["a", "b"]
        assert store["ui.myview.column_order"] == ["b", "a"]
        # Legacy keys are preserved (not deleted) — intentional for rollback.
        assert store["legacy.visible"] == ["a", "b"]

    def test_does_not_overwrite_existing_new_key(self):
        from src.shared.ui.managed_treeview import _migrate_legacy_pref_keys
        store = {
            "ui.myview.visible_cols": ["new", "value"],
            "legacy.visible": ["old", "value"],
        }

        def _get(k, d=None):
            return store.get(k, d)

        def _set(k, v):
            store[k] = v

        with patch("preferences.get", side_effect=_get), \
             patch("preferences.set", side_effect=_set):
            _migrate_legacy_pref_keys(
                view_id="myview",
                pref_prefix="ui",
                legacy={"visible_cols": "legacy.visible"},
            )
        # New key must NOT be overwritten.
        assert store["ui.myview.visible_cols"] == ["new", "value"]

    def test_no_op_when_both_missing(self):
        from src.shared.ui.managed_treeview import _migrate_legacy_pref_keys
        store = {}

        def _get(k, d=None):
            return store.get(k, d)

        def _set(k, v):
            store[k] = v

        with patch("preferences.get", side_effect=_get), \
             patch("preferences.set", side_effect=_set):
            _migrate_legacy_pref_keys(
                view_id="myview",
                pref_prefix="ui",
                legacy={"visible_cols": "legacy.missing"},
            )
        assert store == {}

    def test_ignores_unknown_aspect(self):
        """Only known aspects (visible_cols, column_order, column_widths)
        trigger migration. Bogus aspect names are silently skipped."""
        from src.shared.ui.managed_treeview import _migrate_legacy_pref_keys
        store = {"legacy.weird": "something"}

        def _get(k, d=None):
            return store.get(k, d)

        def _set(k, v):
            store[k] = v

        with patch("preferences.get", side_effect=_get), \
             patch("preferences.set", side_effect=_set):
            _migrate_legacy_pref_keys(
                view_id="myview",
                pref_prefix="ui",
                legacy={"made_up_aspect": "legacy.weird"},
            )
        # No "ui.myview.made_up_aspect" key written.
        assert list(store.keys()) == ["legacy.weird"]

    def test_managedtreeview_triggers_migration_before_loading(self):
        """End-to-end: ManagedTreeview with legacy_pref_keys reads the
        legacy value through the migration path so column_manager sees
        it under the new name."""
        from src.shared.ui.managed_treeview import ManagedTreeview
        store = {
            "saldobalanse.columns.visible": ["a", "b"],
            "saldobalanse.columns.order": ["b", "a", "c"],
        }

        def _get(k, d=None):
            return store.get(k, d)

        def _set(k, v):
            store[k] = v

        tree = _make_tree(("a", "b", "c"))
        with patch("preferences.get", side_effect=_get), \
             patch("preferences.set", side_effect=_set):
            mt = ManagedTreeview(
                tree, view_id="saldobalanse",
                column_specs=_make_specs(),
                pref_prefix="ui",
                auto_bind=False,
                legacy_pref_keys={
                    "visible_cols": "saldobalanse.columns.visible",
                    "column_order": "saldobalanse.columns.order",
                },
            )
        # New keys were populated from legacy.
        assert store["ui.saldobalanse.visible_cols"] == ["a", "b"]
        assert store["ui.saldobalanse.column_order"] == ["b", "a", "c"]
        # Legacy keys still there.
        assert store["saldobalanse.columns.visible"] == ["a", "b"]
        # Column manager loaded the migrated values.
        assert mt.column_manager._visible == ["a", "b"]


# ---------------------------------------------------------------------------
# Bindings
# ---------------------------------------------------------------------------

class TestBindings:
    def test_auto_bind_false_skips_binding(self):
        from src.shared.ui.managed_treeview import ManagedTreeview
        tree = _make_tree()
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            ManagedTreeview(
                tree, view_id="t", column_specs=_make_specs(),
                auto_bind=False,
            )
        # Only enable_treeview_sorting may bind heading commands,
        # but Button-3 / ButtonPress etc. must not fire.
        bind_events_keys = [call.args[0] for call in tree.bind.call_args_list]
        assert "<Button-3>" not in bind_events_keys
        assert "<ButtonPress-1>" not in bind_events_keys

    def test_auto_bind_true_registers_events(self):
        from src.shared.ui.managed_treeview import ManagedTreeview
        tree = _make_tree()
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            ManagedTreeview(
                tree, view_id="t", column_specs=_make_specs(),
                auto_bind=True,
            )
        bind_events = [call.args[0] for call in tree.bind.call_args_list]
        assert "<Button-3>" in bind_events
        assert "<ButtonPress-1>" in bind_events
        assert "<B1-Motion>" in bind_events
        assert "<ButtonRelease-1>" in bind_events
        assert "<Escape>" in bind_events


# ---------------------------------------------------------------------------
# Dynamic column updates
# ---------------------------------------------------------------------------

class TestUpdateColumns:
    def test_update_columns_refreshes_column_manager_metadata(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview

        tree = _make_tree(("a", "b", "c"))
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree,
                view_id="dynamic",
                column_specs=_make_specs(),
                auto_bind=False,
            )

        mt.column_manager._visible = ["a", "c"]
        mt.column_manager._order = ["c", "a", "b"]
        new_specs = [
            ColumnSpec(id="a", heading="A2", visible_by_default=True),
            ColumnSpec(id="d", heading="D", visible_by_default=True),
        ]

        mt.update_columns(new_specs, default_visible=["a", "d"])

        assert mt.column_manager._all_cols == ["a", "d"]
        assert mt.column_manager._default_visible == ["a", "d"]
        assert mt.column_manager._visible == ["a", "d"]
        assert mt.column_manager._order == ["a", "d"]
        tree.__setitem__.assert_any_call("columns", ["a", "d"])


# ---------------------------------------------------------------------------
# Drag-reorder (ghost + drop indicator)
# ---------------------------------------------------------------------------

def _make_event(**overrides):
    """Minimal event stand-in with widget-relative and screen coords."""
    defaults = {"x": 10, "y": 5, "x_root": 110, "y_root": 105}
    defaults.update(overrides)
    evt = MagicMock()
    for k, v in defaults.items():
        setattr(evt, k, v)
    return evt


class TestDragReorder:
    def test_press_on_pinned_blocks_drag(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [
            ColumnSpec(id="a", pinned=True),
            ColumnSpec(id="b"),
            ColumnSpec(id="c"),
        ]
        tree.identify_region = MagicMock(return_value="heading")
        tree.identify_column = MagicMock(return_value="#1")  # col "a"
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        mt._on_left_press(_make_event())
        assert mt._drag_state is None  # pinned → no drag started

    def test_press_on_unpinned_starts_pending_drag(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [
            ColumnSpec(id="a", pinned=True),
            ColumnSpec(id="b"),
            ColumnSpec(id="c"),
        ]
        tree.identify_region = MagicMock(return_value="heading")
        tree.identify_column = MagicMock(return_value="#2")  # col "b"
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        mt._on_left_press(_make_event(x=100))
        assert isinstance(mt._drag_state, dict)
        assert mt._drag_state["source"] == "b"
        assert mt._drag_state["active"] is False  # not past threshold yet

    def test_is_valid_drop_rules(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [
            ColumnSpec(id="a", pinned=True),
            ColumnSpec(id="b"),
            ColumnSpec(id="c"),
        ]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        # Source pinned → never valid
        assert mt._is_valid_drop("a", "b", after=True) is False
        # Same column → not valid
        assert mt._is_valid_drop("b", "b", after=False) is False
        # Normal unpinned→unpinned → valid
        assert mt._is_valid_drop("b", "c", after=False) is True
        assert mt._is_valid_drop("c", "b", after=True) is True
        # Dropping BEFORE a pinned column → blocked (pinned must stay first)
        assert mt._is_valid_drop("b", "a", after=False) is False
        # Dropping AFTER a pinned column is fine
        assert mt._is_valid_drop("b", "a", after=True) is True

    def test_finish_drag_invalid_does_not_reorder(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [ColumnSpec(id=c) for c in ("a", "b", "c")]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        mt._drag_state = {
            "source": "b", "target": "b", "after": False, "valid": False,
            "active": True, "ghost": None, "indicator": None, "ghost_label": None,
            "start_x": 0,
        }
        original = list(mt.column_manager._order)
        mt._finish_drag(_make_event())
        assert list(mt.column_manager._order) == original

    def test_finish_drag_valid_reorders(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [ColumnSpec(id=c) for c in ("a", "b", "c")]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        assert list(mt.column_manager._order) == ["a", "b", "c"]
        mt._drag_state = {
            "source": "a", "target": "c", "after": True, "valid": True,
            "active": True, "ghost": None, "indicator": None, "ghost_label": None,
            "start_x": 0,
        }
        mt._finish_drag(_make_event())
        # "a" is not pinned here, so it can end up at the far right.
        assert list(mt.column_manager._order) == ["b", "c", "a"]

    def test_escape_cancels_active_drag(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [ColumnSpec(id=c) for c in ("a", "b", "c")]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        mt._drag_state = {
            "source": "a", "target": "c", "after": True, "valid": True,
            "active": True, "ghost": None, "indicator": None, "ghost_label": None,
            "start_x": 0,
        }
        original = list(mt.column_manager._order)
        mt._on_escape(_make_event())
        assert mt._drag_state is None
        # Escape must not trigger the reorder.
        assert list(mt.column_manager._order) == original

    def test_column_id_lookup_uses_displaycolumns_after_reorder(self):
        """Regression: tree.identify_column returns #N indexed into
        displaycolumns (the visible/ordered list), not the raw columns
        tuple. After a reorder, the two differ and the drag handler
        must resolve against displaycolumns.
        """
        from src.shared.ui.managed_treeview import _column_id_from_event
        tree = MagicMock()
        tree.identify_column = MagicMock(return_value="#2")
        # Original columns: a, b, c. User has reordered to: c, a, b.
        # displaycolumns reflects the reorder; columns is the raw tuple.
        tree.__getitem__ = MagicMock(
            side_effect=lambda k: {"displaycolumns": ("c", "a", "b"),
                                   "columns": ("a", "b", "c")}[k]
        )
        evt = MagicMock()
        evt.x = 120
        assert _column_id_from_event(tree, evt) == "a"  # #2 in displaycolumns

    def test_column_id_lookup_displaycolumns_all_fallback(self):
        """When displaycolumns is the sentinel '#all' we fall back to
        the raw columns tuple (legacy default for fresh trees)."""
        from src.shared.ui.managed_treeview import _column_id_from_event
        tree = MagicMock()
        tree.identify_column = MagicMock(return_value="#3")
        tree.__getitem__ = MagicMock(
            side_effect=lambda k: {"displaycolumns": ("#all",),
                                   "columns": ("a", "b", "c")}[k]
        )
        evt = MagicMock()
        evt.x = 120
        assert _column_id_from_event(tree, evt) == "c"

    def test_reorder_columns_after_flag_forwarded(self):
        from src.shared.ui.managed_treeview import ColumnSpec, ManagedTreeview
        tree = _make_tree(("a", "b", "c"))
        specs = [ColumnSpec(id=c) for c in ("a", "b", "c")]
        with patch("preferences.get", return_value=None), \
             patch("preferences.set"):
            mt = ManagedTreeview(
                tree, view_id="t", column_specs=specs, auto_bind=False,
            )
        # after=False: insert "c" BEFORE "a" → [c, a, b]
        assert mt.reorder_columns("c", "a", after=False) is True
        assert list(mt.column_manager._order) == ["c", "a", "b"]
        # after=True: insert "c" AFTER "b" (send it to the end) → [a, b, c]
        assert mt.reorder_columns("c", "b", after=True) is True
        assert list(mt.column_manager._order) == ["a", "b", "c"]
        # Re-running the same reorder is a no-op → returns False.
        assert mt.reorder_columns("c", "b", after=True) is False
