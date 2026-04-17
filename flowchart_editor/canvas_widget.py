"""canvas_widget.py — FlowchartCanvas: en gjenbrukbar Tk-canvas for flowcharts.

API:
    canvas = FlowchartCanvas(parent)
    canvas.set_diagram(diagram)
    canvas.on_selection_changed = lambda sel: ...   # sel er Node|Edge|Subgraph|None
    canvas.on_node_moved = lambda node: ...         # etter drag-release

Tag-konvensjon:
    "node:<id>"       — alle canvas-items som tilhører en node
    "edge:<i>"        — alle items for kant nr i
    "subgraph:<id>"   — alle items for en subgraph
    "chart-item"      — alle items (for bulk-operasjoner)

Interaksjoner:
    - Venstre-klikk tom flate: dra for å panorere
    - Venstre-klikk node: velg og start drag
    - Musehjul: zoom (ankret til muspeker)
    - Dobbeltklikk: triggrer on_node_double_click callback
"""

from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional, Union

from . import style
from .model import Diagram, Edge, Node, Subgraph


Selection = Union[Node, Edge, Subgraph, None]


class FlowchartCanvas(ttk.Frame):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            self,
            background=style.CANVAS_BG,
            highlightthickness=1,
            highlightbackground=style.CANVAS_BORDER,
        )
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self._canvas.xview)
        yscroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self._canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")

        # Tilstand
        self._diagram: Diagram = Diagram()
        self._zoom: float = 1.0
        self._selection: Selection = None
        # Kart fra node_id til canvas-items og senterposisjon
        self._node_items: dict[str, list[int]] = {}
        self._edge_items: dict[int, list[int]] = {}
        self._subgraph_items: dict[str, list[int]] = {}
        # Drag-state
        self._press_xy: tuple[int, int] = (0, 0)
        self._dragging: bool = False
        self._drag_target: tuple[str, str] | None = None  # (kind, id)
        self._pending_select: tuple[str, str] | None = None

        # Callbacks (settes av eier)
        self.on_selection_changed: Optional[Callable[[Selection], None]] = None
        self.on_node_moved: Optional[Callable[[Node], None]] = None
        self.on_node_double_click: Optional[Callable[[Node], None]] = None
        self.on_canvas_click: Optional[Callable[[float, float], bool]] = None
        # on_canvas_click returnerer True hvis event er "konsumert"
        # (brukes av "legg til node"-modus i app.py)

        self._bind_events()

    # ── Public API ──────────────────────────────────────────────────────

    def set_diagram(self, diagram: Diagram) -> None:
        self._diagram = diagram
        self._selection = None
        self.refresh()

    def get_diagram(self) -> Diagram:
        return self._diagram

    def refresh(self) -> None:
        """Full re-render av alle items."""
        self._canvas.delete("chart-item")
        self._node_items.clear()
        self._edge_items.clear()
        self._subgraph_items.clear()
        self._draw_subgraphs()
        self._draw_edges()
        self._draw_nodes()
        self._apply_selection_style()
        self._update_scrollregion()

    def set_selection(self, selection: Selection) -> None:
        if selection is not self._selection:
            self._selection = selection
            self._apply_selection_style()
            if self.on_selection_changed:
                self.on_selection_changed(selection)

    def get_selection(self) -> Selection:
        return self._selection

    def zoom_in(self) -> None:
        self._apply_zoom(style.ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(1.0 / style.ZOOM_STEP)

    def zoom_reset(self) -> None:
        factor = 1.0 / self._zoom
        self._zoom = 1.0
        self._canvas.scale("all", 0, 0, factor, factor)
        self._update_scrollregion()

    def fit_to_content(self) -> None:
        self._canvas.update_idletasks()
        bbox = self._canvas.bbox("all")
        if not bbox:
            return
        content_w = max(1, bbox[2] - bbox[0])
        content_h = max(1, bbox[3] - bbox[1])
        view_w = max(1, self._canvas.winfo_width() - 40)
        view_h = max(1, self._canvas.winfo_height() - 40)
        factor = min(view_w / content_w, view_h / content_h, 1.5)
        factor = max(0.5, min(2.0, factor))
        self.zoom_reset()
        if abs(factor - 1.0) > 0.01:
            self._apply_zoom(factor)

    def get_zoom(self) -> float:
        return self._zoom

    # ── Drawing ────────────────────────────────────────────────────────

    def _draw_subgraphs(self) -> None:
        if not self._diagram.subgraphs:
            return
        for sid, sg in self._diagram.subgraphs.items():
            bbox = self._subgraph_bbox(sid)
            if bbox is None:
                continue
            x1, y1, x2, y2 = bbox
            tag_sg = f"subgraph:{sid}"
            items: list[int] = []
            # Ytre ramme
            items.append(self._canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=sg.fill, outline=sg.stroke, width=1,
                tags=("chart-item", "subgraph", tag_sg),
            ))
            # Headerbar øverst
            header_bottom = y1 + style.SUBGRAPH_HEADER_HEIGHT
            items.append(self._canvas.create_rectangle(
                x1, y1, x2, header_bottom,
                fill=style.SUBGRAPH_HEADER_FILL, outline=sg.stroke, width=1,
                tags=("chart-item", "subgraph", tag_sg, f"{tag_sg}:header"),
            ))
            # Label sentrert i headerbaren
            items.append(self._canvas.create_text(
                (x1 + x2) / 2, y1 + style.SUBGRAPH_HEADER_HEIGHT / 2,
                text=sg.label or sg.id,
                anchor="center",
                font=style.FONT_SUBGRAPH,
                fill=style.SUBGRAPH_LABEL,
                tags=("chart-item", "subgraph", tag_sg),
            ))
            self._subgraph_items[sid] = items

    def _subgraph_bbox(self, subgraph_id: str) -> tuple[float, float, float, float] | None:
        members = [n for n in self._diagram.nodes.values() if n.subgraph_id == subgraph_id]
        if not members:
            return None
        pad = style.SUBGRAPH_PADDING
        x1 = min(n.x - n.width / 2 for n in members) - pad
        y1 = min(n.y - n.height / 2 for n in members) - pad - style.SUBGRAPH_HEADER_HEIGHT
        x2 = max(n.x + n.width / 2 for n in members) + pad
        y2 = max(n.y + n.height / 2 for n in members) + pad
        return (x1, y1, x2, y2)

    def _draw_edges(self) -> None:
        for idx, edge in enumerate(self._diagram.edges):
            self._draw_edge(idx, edge)

    def _draw_edge(self, idx: int, edge: Edge) -> None:
        src = self._diagram.nodes.get(edge.from_id)
        dst = self._diagram.nodes.get(edge.to_id)
        if not src or not dst:
            return
        tag = f"edge:{idx}"
        direction = getattr(self._diagram, "direction", "TB") or "TB"
        points = _orthogonal_path(src, dst, direction)
        dash: tuple | None = None
        width = 1.5
        arrow = tk.LAST
        if edge.arrow == "---":
            arrow = tk.NONE
        elif edge.arrow == "-.->":
            dash = (4, 3)
        elif edge.arrow == "==>":
            width = 3.0
        items: list[int] = []
        flat: list[float] = [c for p in points for c in p]
        line_kwargs: dict = dict(
            fill=style.EDGE_COLOR,
            arrow=arrow,
            arrowshape=(style.ARROW_SIZE, style.ARROW_SIZE + 2, style.ARROW_SIZE // 2 + 1),
            width=width,
            joinstyle="miter",
            tags=("chart-item", "edge", tag),
        )
        if dash is not None:
            line_kwargs["dash"] = dash
        items.append(self._canvas.create_line(*flat, **line_kwargs))
        if edge.label:
            mx, my = _longest_segment_midpoint(points)
            items.append(self._canvas.create_rectangle(
                mx - len(edge.label) * 3 - 4, my - 8,
                mx + len(edge.label) * 3 + 4, my + 8,
                fill=style.EDGE_LABEL_BG, outline="",
                tags=("chart-item", "edge", tag),
            ))
            items.append(self._canvas.create_text(
                mx, my, text=edge.label,
                font=style.FONT_EDGE, fill=style.EDGE_LABEL_FG,
                tags=("chart-item", "edge", tag),
            ))
        self._edge_items[idx] = items

    def _draw_nodes(self) -> None:
        for node in self._diagram.nodes.values():
            self._draw_node(node)

    def _draw_node(self, node: Node) -> None:
        tag = f"node:{node.id}"
        items: list[int] = []
        left = node.x - node.width / 2
        top = node.y - node.height / 2
        right = node.x + node.width / 2
        bottom = node.y + node.height / 2

        # Skygge
        items.append(self._canvas.create_rectangle(
            left + 2, top + 3, right + 2, bottom + 3,
            fill=style.NODE_SHADOW, outline="",
            tags=("chart-item", "node", tag, f"{tag}:shadow"),
        ))

        # Hovedform
        shape = node.shape
        if shape == "rect":
            items.append(self._canvas.create_rectangle(
                left, top, right, bottom,
                fill=node.fill, outline=node.stroke, width=1,
                tags=("chart-item", "node", tag, f"{tag}:body"),
            ))
        elif shape == "round":
            items.extend(_draw_rounded_rect(
                self._canvas, left, top, right, bottom,
                radius=style.NODE_CORNER_RADIUS,
                fill=node.fill, outline=node.stroke,
                tags=("chart-item", "node", tag, f"{tag}:body"),
            ))
        elif shape == "rhombus":
            mx, my = node.x, node.y
            items.append(self._canvas.create_polygon(
                mx, top, right, my, mx, bottom, left, my,
                fill=node.fill, outline=node.stroke, width=1,
                tags=("chart-item", "node", tag, f"{tag}:body"),
            ))
        elif shape == "subroutine":
            items.append(self._canvas.create_rectangle(
                left, top, right, bottom,
                fill=node.fill, outline=node.stroke, width=1,
                tags=("chart-item", "node", tag, f"{tag}:body"),
            ))
            items.append(self._canvas.create_line(
                left + 10, top, left + 10, bottom,
                fill=node.stroke, tags=("chart-item", "node", tag, f"{tag}:body"),
            ))
            items.append(self._canvas.create_line(
                right - 10, top, right - 10, bottom,
                fill=node.stroke, tags=("chart-item", "node", tag, f"{tag}:body"),
            ))

        # Tekst
        items.append(self._canvas.create_text(
            node.x, node.y,
            text=node.label or node.id,
            font=style.FONT_BODY,
            fill=node.text_color,
            width=max(40, node.width - 16),
            justify="center",
            tags=("chart-item", "node", tag, f"{tag}:label"),
        ))

        self._node_items[node.id] = items

    # ── Selection styling ─────────────────────────────────────────────

    _OUTLINE_TYPES = {"rectangle", "oval", "polygon", "arc"}

    def _apply_selection_style(self) -> None:
        # Nullstill alle
        for nid in list(self._node_items.keys()):
            node = self._diagram.nodes.get(nid)
            if not node:
                continue
            for item in self._canvas.find_withtag(f"node:{nid}:body"):
                if self._canvas.type(item) in self._OUTLINE_TYPES:
                    self._canvas.itemconfigure(item, outline=node.stroke, width=1)
        for idx in list(self._edge_items.keys()):
            for item in self._canvas.find_withtag(f"edge:{idx}"):
                if self._canvas.type(item) == "line":
                    self._canvas.itemconfigure(item, fill=style.EDGE_COLOR)
        for sid in list(self._subgraph_items.keys()):
            sg = self._diagram.subgraphs.get(sid)
            if not sg:
                continue
            for item in self._canvas.find_withtag(f"subgraph:{sid}"):
                if self._canvas.type(item) == "rectangle":
                    self._canvas.itemconfigure(item, outline=sg.stroke, width=1)

        sel = self._selection
        if isinstance(sel, Node):
            for item in self._canvas.find_withtag(f"node:{sel.id}:body"):
                if self._canvas.type(item) in self._OUTLINE_TYPES:
                    self._canvas.itemconfigure(
                        item, outline=style.SELECTION_STROKE, width=style.SELECTION_WIDTH
                    )
        elif isinstance(sel, Edge):
            idx = self._edge_index(sel)
            if idx is not None:
                for item in self._canvas.find_withtag(f"edge:{idx}"):
                    if self._canvas.type(item) == "line":
                        self._canvas.itemconfigure(item, fill=style.SELECTION_STROKE)
        elif isinstance(sel, Subgraph):
            for item in self._canvas.find_withtag(f"subgraph:{sel.id}"):
                if self._canvas.type(item) == "rectangle":
                    self._canvas.itemconfigure(
                        item, outline=style.SELECTION_STROKE, width=style.SELECTION_WIDTH
                    )

    def _edge_index(self, edge: Edge) -> int | None:
        for idx, e in enumerate(self._diagram.edges):
            if e is edge:
                return idx
        return None

    # ── Events ────────────────────────────────────────────────────────

    def _bind_events(self) -> None:
        c = self._canvas
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_drag)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Double-Button-1>", self._on_double_click)
        c.bind("<MouseWheel>", self._on_mousewheel)

    def _hit_kind_and_id(self) -> tuple[str, str] | None:
        """Finn ut hva som er under musepekeren: node/edge/subgraph + id."""
        for tag in self._canvas.gettags("current"):
            if tag.startswith("node:") and tag.count(":") == 1:
                return ("node", tag.split(":", 1)[1])
            if tag.startswith("edge:") and tag.count(":") == 1:
                return ("edge", tag.split(":", 1)[1])
            if tag.startswith("subgraph:") and tag.count(":") == 1:
                return ("subgraph", tag.split(":", 1)[1])
        return None

    def _on_press(self, event: tk.Event) -> None:
        self._press_xy = (int(event.x), int(event.y))
        self._dragging = False
        self._drag_target = None
        self._pending_select = self._hit_kind_and_id()

        # Canvas-klikk-callback (for "legg til node"-modus)
        if self._pending_select is None and self.on_canvas_click:
            cx = self._canvas.canvasx(event.x) / self._zoom
            cy = self._canvas.canvasy(event.y) / self._zoom
            if self.on_canvas_click(cx, cy):
                self._pending_select = None
                return

        if self._pending_select and self._pending_select[0] == "node":
            self._drag_target = self._pending_select
        else:
            # Pan
            self._canvas.scan_mark(event.x, event.y)

    def _on_drag(self, event: tk.Event) -> None:
        dx = abs(int(event.x) - self._press_xy[0])
        dy = abs(int(event.y) - self._press_xy[1])
        if dx > 3 or dy > 3:
            self._dragging = True
        if self._drag_target and self._dragging:
            kind, nid = self._drag_target
            if kind != "node":
                return
            node = self._diagram.nodes.get(nid)
            if not node:
                return
            cx = self._canvas.canvasx(event.x) / self._zoom
            cy = self._canvas.canvasy(event.y) / self._zoom
            old_x, old_y = node.x, node.y
            node.x = cx
            node.y = cy
            # Re-render full (enkel, trygg) — kunne optimaliseres
            self.refresh()
            self._selection = node
            self._apply_selection_style()
        elif not self._drag_target:
            self._canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, _event: tk.Event) -> None:
        if self._dragging and self._drag_target and self._drag_target[0] == "node":
            nid = self._drag_target[1]
            node = self._diagram.nodes.get(nid)
            if node and self.on_node_moved:
                self.on_node_moved(node)
            self._drag_target = None
            self._dragging = False
            return
        pending = self._pending_select
        self._pending_select = None
        self._drag_target = None
        if self._dragging:
            self._dragging = False
            return
        # Klikk uten drag = select
        if pending is None:
            self.set_selection(None)
            return
        kind, oid = pending
        if kind == "node":
            self.set_selection(self._diagram.nodes.get(oid))
        elif kind == "edge":
            try:
                idx = int(oid)
                self.set_selection(self._diagram.edges[idx])
            except (ValueError, IndexError):
                self.set_selection(None)
        elif kind == "subgraph":
            self.set_selection(self._diagram.subgraphs.get(oid))

    def _on_double_click(self, _event: tk.Event) -> None:
        hit = self._hit_kind_and_id()
        if hit and hit[0] == "node":
            node = self._diagram.nodes.get(hit[1])
            if node and self.on_node_double_click:
                self.on_node_double_click(node)

    def _on_mousewheel(self, event: tk.Event) -> None:
        if getattr(event, "delta", 0) == 0:
            return
        factor = style.ZOOM_STEP if event.delta > 0 else 1.0 / style.ZOOM_STEP
        self._apply_zoom(factor, event.x, event.y)

    def _apply_zoom(self, factor: float, x: int | None = None, y: int | None = None) -> None:
        new_zoom = max(style.ZOOM_MIN, min(style.ZOOM_MAX, self._zoom * factor))
        factor = new_zoom / self._zoom
        if abs(factor - 1.0) < 0.001:
            return
        cx = self._canvas.canvasx(x if x is not None else self._canvas.winfo_width() / 2)
        cy = self._canvas.canvasy(y if y is not None else self._canvas.winfo_height() / 2)
        self._zoom = new_zoom
        self._canvas.scale("all", cx, cy, factor, factor)
        self._update_scrollregion()

    def _update_scrollregion(self) -> None:
        bbox = self._canvas.bbox("all")
        if bbox:
            pad = 40
            self._canvas.configure(
                scrollregion=(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad)
            )


# ── Helpers ───────────────────────────────────────────────────────────


_ORTHO_TOLERANCE = 4.0
_BACK_MARGIN = 40.0


def _orthogonal_path(
    src: Node, dst: Node, direction: str = "TB"
) -> list[tuple[float, float]]:
    """Returner punkter som beskriver en ortogonal polyline fra src til dst.

    Reglene er orientert rundt hoved-aksen for diagrammet:
        - TB/BT: hoved-akse er Y, kryss-akse er X
        - LR/RL: hoved-akse er X, kryss-akse er Y
    """
    horizontal = direction in ("LR", "RL")
    reverse = direction in ("BT", "RL")

    # Kantsentrene i de fire retningene
    src_top = (src.x, src.y - src.height / 2)
    src_bot = (src.x, src.y + src.height / 2)
    src_left = (src.x - src.width / 2, src.y)
    src_right = (src.x + src.width / 2, src.y)
    dst_top = (dst.x, dst.y - dst.height / 2)
    dst_bot = (dst.x, dst.y + dst.height / 2)
    dst_left = (dst.x - dst.width / 2, dst.y)
    dst_right = (dst.x + dst.width / 2, dst.y)

    if not horizontal:
        forward = (src.y < dst.y) if not reverse else (src.y > dst.y)
        if forward:
            if abs(src.x - dst.x) < _ORTHO_TOLERANCE:
                return [src_bot if not reverse else src_top,
                        dst_top if not reverse else dst_bot]
            start = src_bot if not reverse else src_top
            end = dst_top if not reverse else dst_bot
            mid_y = (start[1] + end[1]) / 2
            return [start, (start[0], mid_y), (end[0], mid_y), end]
        # Tilbake-kant: gå ut til siden, rundt og inn på toppen
        start = src_right
        end = dst_top if not reverse else dst_bot
        side_x = max(src.x + src.width / 2, dst.x + dst.width / 2) + _BACK_MARGIN
        approach_y = end[1] - _BACK_MARGIN if not reverse else end[1] + _BACK_MARGIN
        return [start, (side_x, start[1]), (side_x, approach_y),
                (end[0], approach_y), end]
    else:
        forward = (src.x < dst.x) if not reverse else (src.x > dst.x)
        if forward:
            if abs(src.y - dst.y) < _ORTHO_TOLERANCE:
                return [src_right if not reverse else src_left,
                        dst_left if not reverse else dst_right]
            start = src_right if not reverse else src_left
            end = dst_left if not reverse else dst_right
            mid_x = (start[0] + end[0]) / 2
            return [start, (mid_x, start[1]), (mid_x, end[1]), end]
        start = src_bot
        end = dst_left if not reverse else dst_right
        side_y = max(src.y + src.height / 2, dst.y + dst.height / 2) + _BACK_MARGIN
        approach_x = end[0] - _BACK_MARGIN if not reverse else end[0] + _BACK_MARGIN
        return [start, (start[0], side_y), (approach_x, side_y),
                (approach_x, end[1]), end]


def _longest_segment_midpoint(
    points: list[tuple[float, float]]
) -> tuple[float, float]:
    if len(points) < 2:
        return points[0] if points else (0.0, 0.0)
    best = 0
    best_len = -1.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        length = abs(x2 - x1) + abs(y2 - y1)
        if length > best_len:
            best_len = length
            best = i
    x1, y1 = points[best]
    x2, y2 = points[best + 1]
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _line_between_boxes(src: Node, dst: Node) -> tuple[float, float, float, float]:
    """Finn linje fra kant-av-boks til kant-av-boks mellom to noder."""
    x1, y1 = src.x, src.y
    x2, y2 = dst.x, dst.y
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return (x1, y1, x2, y2)
    # Retten fra src.center til dst.center, klipp mot dst-boks for å finne tuppspiss
    dst_clip = _clip_line_to_box(x1, y1, x2, y2, dst)
    src_clip = _clip_line_to_box(x2, y2, x1, y1, src)
    return (src_clip[0], src_clip[1], dst_clip[0], dst_clip[1])


def _clip_line_to_box(x1: float, y1: float, x2: float, y2: float, box: Node) -> tuple[float, float]:
    """Finn der linjen fra (x1,y1) mot (x2,y2) krysser kanten av box (sentrert i x2,y2)."""
    left = box.x - box.width / 2
    right = box.x + box.width / 2
    top = box.y - box.height / 2
    bottom = box.y + box.height / 2
    dx = x1 - x2
    dy = y1 - y2
    if dx == 0 and dy == 0:
        return (x2, y2)
    # Parametrisk: punkt = (x2 + t*dx, y2 + t*dy), finn t hvor vi krysser boksen
    candidates: list[tuple[float, float, float]] = []
    if dx != 0:
        t_left = (left - x2) / dx
        yl = y2 + t_left * dy
        if t_left >= 0 and top <= yl <= bottom:
            candidates.append((t_left, left, yl))
        t_right = (right - x2) / dx
        yr = y2 + t_right * dy
        if t_right >= 0 and top <= yr <= bottom:
            candidates.append((t_right, right, yr))
    if dy != 0:
        t_top = (top - y2) / dy
        xt = x2 + t_top * dx
        if t_top >= 0 and left <= xt <= right:
            candidates.append((t_top, xt, top))
        t_bottom = (bottom - y2) / dy
        xb = x2 + t_bottom * dx
        if t_bottom >= 0 and left <= xb <= right:
            candidates.append((t_bottom, xb, bottom))
    if not candidates:
        return (x2, y2)
    # Ta den minste positive t (nærmest boksens senter)
    candidates.sort(key=lambda c: c[0])
    return (candidates[0][1], candidates[0][2])


def _draw_rounded_rect(
    canvas: tk.Canvas,
    x1: float, y1: float, x2: float, y2: float,
    *, radius: float, fill: str, outline: str, tags: tuple,
) -> list[int]:
    """Tegn en "avrundet" rektangel ved å kombinere polygon + circle overlays.

    Tk har ingen native avrundet rektangel. Dette er en enkel tilnærming som
    gir "round"-inntrykket uten å være matematisk perfekt.
    """
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2)
    items: list[int] = []
    # Hovedform (rektangel uten outline)
    items.append(canvas.create_rectangle(
        x1 + r, y1, x2 - r, y2,
        fill=fill, outline="", tags=tags,
    ))
    items.append(canvas.create_rectangle(
        x1, y1 + r, x2, y2 - r,
        fill=fill, outline="", tags=tags,
    ))
    # Hjørner
    items.append(canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, fill=fill, outline="", tags=tags))
    items.append(canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, fill=fill, outline="", tags=tags))
    items.append(canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, fill=fill, outline="", tags=tags))
    items.append(canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, fill=fill, outline="", tags=tags))
    # Outline (approksimert med 4 linjer + 4 bueomriss)
    items.append(canvas.create_line(x1 + r, y1, x2 - r, y1, fill=outline, tags=tags))
    items.append(canvas.create_line(x1 + r, y2, x2 - r, y2, fill=outline, tags=tags))
    items.append(canvas.create_line(x1, y1 + r, x1, y2 - r, fill=outline, tags=tags))
    items.append(canvas.create_line(x2, y1 + r, x2, y2 - r, fill=outline, tags=tags))
    items.append(canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="arc", outline=outline, tags=tags))
    items.append(canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="arc", outline=outline, tags=tags))
    items.append(canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="arc", outline=outline, tags=tags))
    items.append(canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="arc", outline=outline, tags=tags))
    return items
