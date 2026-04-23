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
        self._apply_specs()
        self._apply_saved_widths()
        sortable_cols = [spec.id for spec in self._specs if spec.sortable]
        if enable_treeview_sorting is not None and sortable_cols:
            enable_treeview_sorting(tree, columns=sortable_cols)
        if auto_bind:
            self.bind_events()
        self.stabilize_layout()

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
        try:
            self.tree["columns"] = [spec.id for spec in self._specs]
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
        self.column_manager.update_columns([spec.id for spec in self._specs])

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
        self._stabilize_generation += 1
        generation = self._stabilize_generation
        try:
            self.tree.after_idle(lambda: self._stabilize_once(generation, second_pass=False))
        except Exception:
            self._stabilize_once(generation, second_pass=False)

    def _stabilize_once(self, generation: int, *, second_pass: bool) -> None:
        if generation != self._stabilize_generation:
            return
        self.column_manager.apply_visible()
        self._apply_saved_widths()
        try:
            self.tree.update_idletasks()
        except Exception:
            pass
        # Some Treeview layouts briefly paint body/header with stale geometry on
        # first render. One extra idle pass stabilizes widths/displaycolumns
        # without changing data or interaction semantics.
        if not second_pass and generation == self._stabilize_generation:
            try:
                self.tree.after_idle(lambda: self._stabilize_once(generation, second_pass=True))
            except Exception:
                pass

    def update_columns(self, column_specs: Sequence[ColumnSpec | str], *, default_visible: Sequence[str] | None = None) -> None:
        self._specs = self._normalize_specs(column_specs)
        all_cols = [spec.id for spec in self._specs]
        self.column_manager._default_visible = list(default_visible or [spec.id for spec in self._specs if spec.visible_by_default] or all_cols)
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
            try:
                ghost.wm_attributes("-alpha", 0.92)
            except Exception:
                pass
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
            self._drag_state["ghost"] = ghost
            self._drag_state["ghost_label"] = label
        except Exception:
            self._drag_state["ghost"] = None
            self._drag_state["ghost_label"] = None

        try:
            indicator = tk.Toplevel(self.tree)
            indicator.wm_overrideredirect(True)
            indicator.wm_attributes("-topmost", True)
            tk.Frame(indicator, background="#1F6FEB", width=3, height=24).pack(
                fill="both", expand=True
            )
            indicator.withdraw()
            self._drag_state["indicator"] = indicator
        except Exception:
            self._drag_state["indicator"] = None

        try:
            self.tree.configure(cursor="fleur")
        except Exception:
            pass

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
        label = drag.get("ghost_label")
        source = str(drag.get("source") or "")

        # Move the ghost to follow the cursor regardless of whether we're
        # over a valid target.
        try:
            x_root = int(getattr(event, "x_root", 0) or 0)
            y_root = int(getattr(event, "y_root", 0) or 0)
        except Exception:
            x_root = y_root = 0
        if ghost is not None:
            try:
                ghost.wm_geometry(f"+{x_root + 14}+{y_root + 12}")
            except Exception:
                pass

        # Decide target + validity based on header region.
        target = ""
        after = False
        valid = False
        try:
            region = str(self.tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region == "heading":
            target = _column_id_from_event(self.tree, event)
            bbox = self._column_bbox_screen(target) if target else None
            if bbox is not None:
                left, right = bbox
                mid = (left + right) // 2
                after = x_root >= mid
                valid = self._is_valid_drop(source, target, after)
                drop_x = right if after else left
                if indicator is not None:
                    try:
                        header_h = self._estimate_header_height()
                        body_h = max(int(self.tree.winfo_height()), header_h + 12)
                        y_indicator = self.tree.winfo_rooty()
                        indicator.wm_geometry(
                            f"3x{body_h}+{drop_x - 1}+{y_indicator}"
                        )
                        fill_color = "#1F6FEB" if valid else "#D92D20"
                        try:
                            for child in indicator.winfo_children():
                                child.configure(background=fill_color)
                        except Exception:
                            pass
                        indicator.deiconify()
                        indicator.lift()
                    except Exception:
                        pass
            else:
                if indicator is not None:
                    try:
                        indicator.withdraw()
                    except Exception:
                        pass
        else:
            if indicator is not None:
                try:
                    indicator.withdraw()
                except Exception:
                    pass

        drag["target"] = target
        drag["after"] = after
        drag["valid"] = valid

        # Cursor feedback.
        try:
            self.tree.configure(cursor="fleur" if valid else "X_cursor")
        except Exception:
            pass

        # Ghost label tint — subtle red border when invalid.
        if label is not None:
            try:
                label.configure(foreground="#1F6FEB" if valid else "#D92D20")
                parent = label.master
                parent.configure(background="#1F6FEB" if valid else "#D92D20")
            except Exception:
                pass

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
        if not col:
            return None
        tree = self.tree
        try:
            children = tree.get_children("")
        except Exception:
            children = ()
        if children:
            try:
                bbox = tree.bbox(children[0], col)
            except Exception:
                bbox = None
            if bbox:
                try:
                    x, _, w, _ = bbox
                    root_x = int(tree.winfo_rootx())
                    return (root_x + int(x), root_x + int(x) + int(w))
                except Exception:
                    pass
        # Fallback: accumulate displaycolumn widths from tree origin.
        try:
            cols = list(tree["displaycolumns"])
        except Exception:
            cols = []
        if not cols or (cols and str(cols[0]) == "#all"):
            cols = [spec.id for spec in self._specs]
        if col not in cols:
            return None
        try:
            left = int(tree.winfo_rootx())
        except Exception:
            return None
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
