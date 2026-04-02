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
    ) -> None:
        self.tree = tree
        self.view_id = str(view_id or "").strip()
        self.pref_prefix = pref_prefix
        self._on_body_right_click = on_body_right_click
        self._drag_state: dict[str, Any] | None = None
        self._stabilize_generation = 0
        self._width_pref_key = f"{pref_prefix}.{self.view_id}.column_widths"
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

    def reorder_columns(self, source: str, target: str) -> bool:
        changed = self.column_manager.reorder_columns(source, target)
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
        self._drag_state = {
            "source": col,
            "start_x": int(getattr(event, "x", 0) or 0),
            "active": False,
        }

    def _on_left_drag(self, event) -> None:
        if not isinstance(self._drag_state, dict):
            return
        if self._drag_state.get("active"):
            return
        try:
            region = str(self.tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region != "heading":
            return
        start_x = int(self._drag_state.get("start_x", 0) or 0)
        cur_x = int(getattr(event, "x", 0) or 0)
        if abs(cur_x - start_x) < HEADER_DRAG_THRESHOLD_PX:
            return
        self._drag_state["active"] = True
        try:
            self.tree._suppress_next_heading_sort = True  # type: ignore[attr-defined]
        except Exception:
            pass

    def _on_left_release(self, event) -> None:
        if self._finish_drag(event):
            return
        try:
            region = str(self.tree.identify_region(event.x, event.y))
        except Exception:
            region = ""
        if region in {"separator", "heading"}:
            self.remember_widths()

    def _finish_drag(self, event) -> bool:
        drag = self._drag_state
        self._drag_state = None
        if not isinstance(drag, dict) or not drag.get("active"):
            return False
        source = str(drag.get("source") or "").strip()
        target = _column_id_from_event(self.tree, event)
        if not source or not target or source == target:
            return False
        changed = self.reorder_columns(source, target)
        try:
            self.tree.after_idle(lambda: setattr(self.tree, "_suppress_next_heading_sort", False))
        except Exception:
            try:
                self.tree._suppress_next_heading_sort = False  # type: ignore[attr-defined]
            except Exception:
                pass
        return changed
