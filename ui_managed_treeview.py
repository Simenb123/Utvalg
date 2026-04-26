"""ui_managed_treeview.py -- liten felles Treeview-plattform.

Bygger paa eksisterende helpers:
- treeview_column_manager.py  (synlighet / rekkefolge / chooser / prefs)
- ui_treeview_sort.py         (klikk-for-sortering)

Denne controlleren samler det meste som ellers ma kobles opp manuelt:
- kolonnedefinisjoner
- persisted bredder
- header right-click
- header drag for kolonnerekkefolge
- separator-release for breddepersistens
- en liten after_idle-stabilisering for first-paint
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Sequence

try:
    import tkinter as tk
    from tkinter import ttk
except Exception:  # pragma: no cover
    tk = None  # type: ignore
    ttk = None  # type: ignore

import preferences
from treeview_column_manager import TreeviewColumnManager

try:
    from ui_treeview_sort import enable_treeview_sorting
except Exception:  # pragma: no cover
    enable_treeview_sorting = None  # type: ignore


HEADER_DRAG_THRESHOLD_PX = 10


@dataclass(frozen=True)
class ColumnSpec:
    """Liten kolonnekontrakt for managed Treeviews."""

    id: str
    heading: str | None = None
    width: int = 100
    minwidth: int = 40
    anchor: str = "w"
    stretch: bool = False
    visible_by_default: bool = True
    pinned: bool = False
    sortable: bool = True


def _column_id_from_event(tree: Any, event: Any) -> str:
    """Resolve the column id under ``event.x``.

    ``tree.identify_column(x)`` returns a token like ``"#3"`` where the
    index refers to *displaycolumns* (the visible/ordered list), not the
    raw ``tree["columns"]`` tuple. Mapping the index against
    ``tree["columns"]`` breaks as soon as the user reorders columns or
    hides any of them — which is exactly what ManagedTreeview lets them
    do. Always resolve against displaycolumns, falling back to columns
    when displaycolumns is the sentinel ``"#all"``.
    """
    try:
        token = str(tree.identify_column(int(getattr(event, "x", 0) or 0)))
    except Exception:
        return ""
    if not token.startswith("#"):
        return ""
    try:
        index = int(token[1:]) - 1
    except Exception:
        return ""
    if index < 0:
        return ""
    try:
        display = list(tree["displaycolumns"])
    except Exception:
        display = []
    if display and str(display[0]) != "#all":
        if index < len(display):
            return str(display[index])
        return ""
    # displaycolumns == "#all" — fall back to raw columns tuple.
    try:
        cols = list(tree["columns"])
    except Exception:
        cols = []
    if 0 <= index < len(cols):
        return str(cols[index])
    return ""


def _load_widths(pref_key: str) -> dict[str, int]:
    try:
        raw = preferences.get(pref_key, {})
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        return {}
    widths: dict[str, int] = {}
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            width = int(value)
        except Exception:
            continue
        if 40 <= width <= 1600:
            widths[name] = width
    return widths


def _save_widths(pref_key: str, widths: dict[str, int]) -> None:
    clean: dict[str, int] = {}
    for key, value in widths.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            width = int(value)
        except Exception:
            continue
        if 40 <= width <= 1600:
            clean[name] = width
    try:
        preferences.set(pref_key, clean)
    except Exception:
        pass


# Mapping from logical aspect name to the suffix the new key uses.
# Callers pass a dict like {"visible_cols": "legacy.x", "column_order": "legacy.y"}
# using the same logical names — which must match these suffixes.
_NEW_KEY_SUFFIXES = ("visible_cols", "column_order", "column_widths")


def _migrate_legacy_pref_keys(
    *,
    view_id: str,
    pref_prefix: str,
    legacy: dict[str, str],
) -> None:
    """Copy values from legacy pref keys to the standard new-key scheme.

    For each entry ``{aspect: legacy_key}`` in *legacy*: if the new key
    (``{pref_prefix}.{view_id}.{aspect}``) is missing but the legacy key
    exists, read the legacy value and write it to the new key. Legacy
    key is left untouched (so rolling back a deploy still works). After
    the first migration, the new key exists and this function becomes a
    no-op on subsequent starts.
    """
    for aspect, legacy_key in legacy.items():
        if aspect not in _NEW_KEY_SUFFIXES:
            continue
        new_key = f"{pref_prefix}.{view_id}.{aspect}"
        try:
            existing_new = preferences.get(new_key, None)
        except Exception:
            existing_new = None
        if existing_new is not None:
            continue  # new key already populated — nothing to do
        try:
            legacy_value = preferences.get(legacy_key, None)
        except Exception:
            legacy_value = None
        if legacy_value is None:
            continue
        try:
            preferences.set(new_key, legacy_value)
        except Exception:
            pass


class ManagedTreeview:
    """Samlet controller for Treeview-kolonner og header-interaksjon."""

    def __init__(
        self,
        tree: ttk.Treeview,
        *,
        view_id: str,
        column_specs: Sequence[ColumnSpec | str],
        pref_prefix: str = "ui",
        default_visible: Sequence[str] | None = None,
        pinned_cols: Sequence[str] | None = None,
        on_body_right_click: Callable[[Any], Any] | None = None,
        auto_bind: bool = True,
        legacy_pref_keys: dict[str, str] | None = None,
    ) -> None:
        self.tree = tree
        self.view_id = str(view_id or "").strip()
        self.pref_prefix = pref_prefix
        self._on_body_right_click = on_body_right_click
        self._drag_state: dict[str, Any] | None = None
        self._stabilize_generation = 0
        self._width_pref_key = f"{pref_prefix}.{self.view_id}.column_widths"
        # Auto-migrate legacy preference keys BEFORE any reading happens,
        # so TreeviewColumnManager.load_from_preferences() and
        # _load_widths() see the migrated values under the new names.
        if legacy_pref_keys:
            _migrate_legacy_pref_keys(
                view_id=self.view_id,
                pref_prefix=pref_prefix,
                legacy=legacy_pref_keys,
            )
        self._widths = _load_widths(self._width_pref_key)

        self._specs: list[ColumnSpec] = self._normalize_specs(column_specs)
        all_cols = [spec.id for spec in self._specs]
        self._pinned = tuple(pinned_cols or [spec.id for spec in self._specs if spec.pinned])
        visible = list(default_visible or [spec.id for spec in self._specs if spec.visible_by_default])
        if not visible:
            visible = list(all_cols)

        self.column_manager = TreeviewColumnManager(
            tree,
            view_id=view_id,
            all_cols=all_cols,
            default_visible=visible,
            pinned_cols=self._pinned,
            pref_prefix=pref_prefix,
        )
        # _apply_specs sets heading + column configs (width comes from
        # self._widths), so the subsequent _apply_saved_widths call that
        # used to live here was fully redundant — 34+ duplicated Tcl
        # round-trips per init on a full Saldobalanse page.
        self._apply_specs()
        sortable_cols = [spec.id for spec in self._specs if spec.sortable]
        if enable_treeview_sorting is not None and sortable_cols:
            enable_treeview_sorting(tree, columns=sortable_cols)
        if auto_bind:
            self.bind_events()

    @staticmethod
    def _normalize_specs(column_specs: Sequence[ColumnSpec | str]) -> list[ColumnSpec]:
        specs: list[ColumnSpec] = []
        for item in column_specs:
            if isinstance(item, ColumnSpec):
                specs.append(item)
            else:
                cid = str(item or "").strip()
                if cid:
                    specs.append(ColumnSpec(id=cid, heading=cid, visible_by_default=True))
        return specs

    def _apply_specs(self) -> None:
        target_columns = [spec.id for spec in self._specs]
        try:
            current_columns = [str(c) for c in self.tree["columns"]]
        except Exception:
            current_columns = []
        if current_columns != target_columns:
            # Only reassign when it actually differs — setting tree["columns"]
            # tears down heading/column state and resets displaycolumns, which
            # is expensive and makes the subsequent apply_visible() necessary.
            try:
                self.tree["columns"] = target_columns
            except Exception:
                pass
        for spec in self._specs:
            try:
                self.tree.heading(spec.id, text=spec.heading or spec.id)
            except Exception:
                pass
            try:
                self.tree.column(
                    spec.id,
                    width=int(self._widths.get(spec.id, spec.width)),
                    minwidth=int(spec.minwidth),
                    anchor=spec.anchor,
                    stretch=bool(spec.stretch),
                )
            except Exception:
                pass
        # Re-apply visibility — assigning tree["columns"] resets
        # displaycolumns. Call apply_visible() directly rather than
        # update_columns(), which also clobbers _default_visible and forces
        # the "Standard" reset menu item to pick *all* columns instead of
        # the caller's intended default set.
        self.column_manager.apply_visible()

    def _apply_saved_widths(self) -> None:
        for spec in self._specs:
            width = int(self._widths.get(spec.id, spec.width))
            try:
                self.tree.column(spec.id, width=width, minwidth=int(spec.minwidth), anchor=spec.anchor, stretch=bool(spec.stretch))
            except Exception:
                continue

    def bind_events(self) -> None:
        self.tree.bind("<Button-3>", self._on_right_click, add="+")
        self.tree.bind("<ButtonPress-1>", self._on_left_press, add="+")
        self.tree.bind("<B1-Motion>", self._on_left_drag, add="+")
        self.tree.bind("<ButtonRelease-1>", self._on_left_release, add="+")
        self.tree.bind("<Escape>", self._on_escape, add="+")

    def stabilize_layout(self) -> None:
        """Queue an idle-time re-apply of visibility + saved widths.

        Used after runtime changes (reorder, column chooser) where Tk may
        briefly lay out columns with stretched widths before our saved
        widths are honored. Not called from ``__init__`` — a freshly-built
        tree is already in the right state after ``_apply_specs`` and the
        extra idle pass was adding visible lag on big pages.
        """
        self._stabilize_generation += 1
        generation = self._stabilize_generation
        try:
            self.tree.after_idle(lambda: self._stabilize_once(generation))
        except Exception:
            self._stabilize_once(generation)

    def _stabilize_once(self, generation: int) -> None:
        if generation != self._stabilize_generation:
            return
        self.column_manager.apply_visible()
        self._apply_saved_widths()
        try:
            self.tree.update_idletasks()
        except Exception:
            pass

    def update_columns(self, column_specs: Sequence[ColumnSpec | str], *, default_visible: Sequence[str] | None = None) -> None:
        self._specs = self._normalize_specs(column_specs)
        all_cols = [spec.id for spec in self._specs]
        visible = list(default_visible or [spec.id for spec in self._specs if spec.visible_by_default] or all_cols)
        self.column_manager._all_cols = list(all_cols)
        self.column_manager._default_visible = visible
        current_visible = [col for col in self.column_manager._visible if col in all_cols]
        for col in visible:
            if col in all_cols and col not in current_visible:
                current_visible.append(col)
        self.column_manager._visible = current_visible or list(visible)
        order = [col for col in self.column_manager._order if col in all_cols]
        for col in all_cols:
            if col not in order:
                order.append(col)
        self.column_manager._order = order
        self.column_manager._normalize_order()
        self._apply_specs()
        self.stabilize_layout()

    def remember_widths(self) -> None:
        widths: dict[str, int] = {}
        try:
            columns: Iterable[str] = list(self.tree["displaycolumns"])
        except Exception:
            columns = [spec.id for spec in self._specs]
        for col in columns:
            if str(col).strip() == "#all":
                columns = [spec.id for spec in self._specs]
                break
        for col in columns:
            try:
                width = int(self.tree.column(col, option="width"))
            except Exception:
                try:
                    width = int((self.tree.column(col) or {}).get("width", 0))
                except Exception:
                    width = 0
            if width >= 40:
                widths[str(col)] = width
        if widths:
            self._widths.update(widths)
            _save_widths(self._width_pref_key, self._widths)

    def reorder_columns(self, source: str, target: str, *, after: bool = False) -> bool:
        changed = self.column_manager.reorder_columns(source, target, after=after)
        if changed:
            self.stabilize_layout()
        return changed

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_right_click(self, event) -> str | None:
        handled = self.column_manager.on_right_click(event)
        if handled == "break":
            return handled
        if callable(self._on_body_right_click):
            return self._on_body_right_click(event)
        return None

    def _on_left_press(self, event) -> None:
        region = ""
        try:
            region = str(self.tree.identify_region(event.x, event.y))
        except Exception:
            pass
        if region != "heading":
            self._drag_state = None
            return
        col = _column_id_from_event(self.tree, event)
        if not col:
            self._drag_state = None
            return
        # Pinned columns are never draggable — don't even start a drag state.
        if col in self._pinned:
            self._drag_state = None
            return
        self._drag_state = {
            "source": col,
            "start_x": int(getattr(event, "x", 0) or 0),
            "active": False,
            "ghost": None,
            "ghost_label": None,
            "indicator": None,
            "target": "",
            "after": False,
            "valid": False,
        }

    def _on_left_drag(self, event) -> None:
        if not isinstance(self._drag_state, dict):
            return
        if not self._drag_state.get("active"):
            start_x = int(self._drag_state.get("start_x", 0) or 0)
            cur_x = int(getattr(event, "x", 0) or 0)
            if abs(cur_x - start_x) < HEADER_DRAG_THRESHOLD_PX:
                return
            self._drag_state["active"] = True
            try:
                self.tree._suppress_next_heading_sort = True  # type: ignore[attr-defined]
            except Exception:
                pass
            self._spawn_drag_visuals()
            try:
                self.tree.focus_set()
            except Exception:
                pass
        self._update_drag_visuals(event)

    def _on_left_release(self, event) -> None:
        if self._finish_drag(event):
            return
        try:
            region = str(self.tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region in {"separator", "heading"}:
            self.remember_widths()

    def _on_escape(self, event) -> None:
        if isinstance(self._drag_state, dict) and self._drag_state.get("active"):
            self._teardown_drag_visuals()
            self._drag_state = None
            try:
                self.tree.after_idle(
                    lambda: setattr(self.tree, "_suppress_next_heading_sort", False)
                )
            except Exception:
                pass

    def _finish_drag(self, event) -> bool:
        drag = self._drag_state
        self._drag_state = None
        if not isinstance(drag, dict) or not drag.get("active"):
            self._teardown_drag_visuals_state(drag)
            return False
        self._teardown_drag_visuals_state(drag)
        source = str(drag.get("source") or "").strip()
        target = str(drag.get("target") or "").strip()
        after = bool(drag.get("after"))
        valid = bool(drag.get("valid"))
        try:
            self.tree.after_idle(
                lambda: setattr(self.tree, "_suppress_next_heading_sort", False)
            )
        except Exception:
            try:
                self.tree._suppress_next_heading_sort = False  # type: ignore[attr-defined]
            except Exception:
                pass
        if not valid or not source or not target or source == target:
            return False
        return self.reorder_columns(source, target, after=after)

    # ------------------------------------------------------------------
    # Drag visuals (ghost label + drop indicator)
    # ------------------------------------------------------------------

    def _spawn_drag_visuals(self) -> None:
        if tk is None or not isinstance(self._drag_state, dict):
            return
        source = str(self._drag_state.get("source") or "")
        text = source
        try:
            heading_text = self.tree.heading(source, "text")
            if heading_text:
                text = str(heading_text).strip() or source
        except Exception:
            pass

        try:
            ghost = tk.Toplevel(self.tree)
            ghost.wm_overrideredirect(True)
            ghost.wm_attributes("-topmost", True)
            outer = tk.Frame(ghost, background="#1F6FEB", bd=0)
            outer.pack(padx=0, pady=0)
            label = tk.Label(
                outer,
                text=f"☰  {text}",
                background="#FFFFFF",
                foreground="#1F6FEB",
                font=("Segoe UI", 9, "bold"),
                padx=10,
                pady=4,
                bd=0,
            )
            label.pack(padx=1, pady=1)
            # Position offscreen before showing to avoid first-paint flicker.
            ghost.wm_geometry("+-2000+-2000")
            self._drag_state["ghost"] = ghost
            self._drag_state["ghost_label"] = label
            self._drag_state["ghost_frame"] = outer
        except Exception:
            self._drag_state["ghost"] = None
            self._drag_state["ghost_label"] = None
            self._drag_state["ghost_frame"] = None

        try:
            indicator = tk.Toplevel(self.tree)
            indicator.wm_overrideredirect(True)
            indicator.wm_attributes("-topmost", True)
            body_h = max(int(self.tree.winfo_height()), 24)
            y_indicator = int(self.tree.winfo_rooty())
            inner = tk.Frame(indicator, background="#1F6FEB", width=3, height=body_h)
            inner.pack(fill="both", expand=True)
            indicator.wm_geometry(f"3x{body_h}+-2000+{y_indicator}")
            indicator.lift()
            self._drag_state["indicator"] = indicator
            self._drag_state["indicator_frame"] = inner
            self._drag_state["indicator_height"] = body_h
            self._drag_state["indicator_y"] = y_indicator
        except Exception:
            self._drag_state["indicator"] = None
            self._drag_state["indicator_frame"] = None

        # Motion-hot-path caches — updated only on real transitions, so
        # most motion events become a few cheap integer comparisons.
        self._drag_state["last_drop_x"] = None
        self._drag_state["last_valid"] = None
        self._drag_state["last_ghost_pos"] = None
        self._drag_state["last_target_col"] = None

        try:
            self.tree.configure(cursor="fleur")
        except Exception:
            pass

    def _column_bbox_screen_cached(
        self, drag: dict[str, Any], col: str
    ) -> tuple[int, int] | None:
        """Same as ``_column_bbox_screen`` but memoizes the result per
        target column for the lifetime of the current drag.

        A single horizontal drag sweeps across at most a handful of
        columns; caching avoids N calls to ``tree.bbox`` and
        ``tree.column`` per motion event when the user hovers inside the
        same column for multiple frames.
        """
        cache = drag.get("bbox_cache")
        if not isinstance(cache, dict):
            cache = {}
            drag["bbox_cache"] = cache
        if col in cache:
            return cache[col]
        bbox = self._column_bbox_screen(col)
        cache[col] = bbox
        return bbox

    def _teardown_drag_visuals(self) -> None:
        self._teardown_drag_visuals_state(self._drag_state)

    def _teardown_drag_visuals_state(self, drag: Any) -> None:
        if not isinstance(drag, dict):
            return
        for key in ("ghost", "indicator"):
            win = drag.get(key)
            if win is not None:
                try:
                    win.destroy()
                except Exception:
                    pass
            drag[key] = None
        try:
            self.tree.configure(cursor="")
        except Exception:
            pass

    def _update_drag_visuals(self, event) -> None:
        if not isinstance(self._drag_state, dict):
            return
        drag = self._drag_state
        ghost = drag.get("ghost")
        indicator = drag.get("indicator")
        source = str(drag.get("source") or "")

        try:
            x_root = int(getattr(event, "x_root", 0) or 0)
            y_root = int(getattr(event, "y_root", 0) or 0)
        except Exception:
            x_root = y_root = 0

        # Ghost follows cursor — skip the wm_geometry call when it moved
        # less than 2px (avoids hammering the WM with micro-updates).
        if ghost is not None:
            last_pos = drag.get("last_ghost_pos") or (-9999, -9999)
            gx = x_root + 14
            gy = y_root + 12
            if abs(gx - last_pos[0]) >= 2 or abs(gy - last_pos[1]) >= 2:
                try:
                    ghost.wm_geometry(f"+{gx}+{gy}")
                except Exception:
                    pass
                drag["last_ghost_pos"] = (gx, gy)

        # Decide target + validity. identify_column works for any y inside
        # the tree (header AND body rows), so we intentionally don't gate
        # on identify_region — the user can drop a column anywhere
        # horizontally over its column, not only on the header strip.
        target = _column_id_from_event(self.tree, event)

        after = False
        valid = False
        drop_x: int | None = None
        if target:
            bbox = self._column_bbox_screen_cached(drag, target)
            if bbox is not None:
                left, right = bbox
                mid = (left + right) // 2
                after = x_root >= mid
                drop_x = right if after else left
                valid = self._is_valid_drop(source, target, after)
            else:
                target = ""

        drag["target"] = target
        drag["after"] = after
        drag["valid"] = valid

        # Only touch the indicator Toplevel when its position or color
        # needs to change. Tk's Toplevel repositioning on Windows is the
        # main source of drag lag when unthrottled.
        if indicator is not None:
            last_drop_x = drag.get("last_drop_x")
            last_valid = drag.get("last_valid")
            if drop_x is None:
                if last_drop_x is not None:
                    try:
                        indicator.wm_geometry(
                            f"3x{drag.get('indicator_height', 24)}+-2000+"
                            f"{drag.get('indicator_y', 0)}"
                        )
                    except Exception:
                        pass
                    drag["last_drop_x"] = None
            else:
                if last_drop_x != drop_x:
                    try:
                        indicator.wm_geometry(
                            f"3x{drag.get('indicator_height', 24)}+"
                            f"{drop_x - 1}+{drag.get('indicator_y', 0)}"
                        )
                    except Exception:
                        pass
                    drag["last_drop_x"] = drop_x
                if last_valid != valid:
                    fill = "#1F6FEB" if valid else "#D92D20"
                    frame = drag.get("indicator_frame")
                    if frame is not None:
                        try:
                            frame.configure(background=fill)
                        except Exception:
                            pass

        # Cursor + ghost-border — only change on validity transition.
        if drag.get("last_valid") != valid:
            cursor = "fleur" if valid or drop_x is None else "X_cursor"
            try:
                self.tree.configure(cursor=cursor)
            except Exception:
                pass
            ghost_frame = drag.get("ghost_frame")
            if ghost_frame is not None:
                try:
                    ghost_frame.configure(
                        background="#1F6FEB" if valid or drop_x is None else "#D92D20"
                    )
                except Exception:
                    pass
            drag["last_valid"] = valid

    # ------------------------------------------------------------------
    # Drop-validation + geometry helpers
    # ------------------------------------------------------------------

    def _is_valid_drop(self, source: str, target: str, after: bool) -> bool:
        if not source or not target or source == target:
            return False
        if source in self._pinned:
            return False
        # Dropping before a pinned column would be normalized away by
        # TreeviewColumnManager._normalize_order (pinned stays first).
        # Block it here too so the indicator tells the user upfront.
        if target in self._pinned and not after:
            return False
        # Dropping after source's current left neighbour-pair where the
        # result equals current order is a no-op — we let it through as
        # "valid" visually but reorder_columns returns False, which is fine.
        return True

    def _column_bbox_screen(self, col: str) -> tuple[int, int] | None:
        """Return (screen_x_left, screen_x_right) for a column's display
        range, or None when the column isn't currently renderable.

        Tries up to a handful of children in case the first few are
        scrolled out of the viewport — this lets the drag work even when
        the user has scrolled vertically before starting the drag.
        """
        if not col:
            return None
        tree = self.tree
        try:
            root_x = int(tree.winfo_rootx())
        except Exception:
            return None
        try:
            children = tree.get_children("")
        except Exception:
            children = ()
        for iid in list(children)[:8]:
            try:
                bbox = tree.bbox(iid, col)
            except Exception:
                bbox = None
            if not bbox:
                continue
            try:
                x, _, w, _ = bbox
                return (root_x + int(x), root_x + int(x) + int(w))
            except Exception:
                continue
        # Fallback: accumulate displaycolumn widths from tree origin.
        # Not scroll-aware, but this branch only triggers when either the
        # tree is empty or every rendered row failed bbox — both cases
        # correlate with zero horizontal scroll.
        try:
            cols = list(tree["displaycolumns"])
        except Exception:
            cols = []
        if not cols or (cols and str(cols[0]) == "#all"):
            cols = [spec.id for spec in self._specs]
        if col not in cols:
            return None
        left = root_x
        for c in cols:
            try:
                w = int(tree.column(c, option="width"))
            except Exception:
                w = 0
            if c == col:
                return (left, left + w)
            left += w
        return None

    def _estimate_header_height(self) -> int:
        try:
            style = ttk.Style()
            rowheight = int(style.lookup("Treeview", "rowheight") or 0)
            if rowheight > 0:
                return rowheight + 6
        except Exception:
            pass
        return 24
