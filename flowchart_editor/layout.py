"""layout.py — Kompakt grid-layout for importerte Mermaid-diagrammer.

Strategi:
    1) Auto-tilpass høyde på hver node basert på antall label-linjer.
    2) For hver subgraph: topologisk sortering av medlemmene, plasser i
       et grid med maks ``GRID_COLS_MAX`` kolonner.
    3) Plasser subgraphs i et ytre 2-kolonners grid.
    4) Frie noder (uten subgraph) legges i eget grid under subgraphene.

Hensikten er *ikke* en visuell perfekt Graphviz-erstatning, men å lande
importerte diagrammer på et kompakt utgangspunkt som brukeren kan
finjustere manuelt.
"""

from __future__ import annotations

import math
from collections import defaultdict

from . import style
from .model import Diagram, Edge, Node


# ── Offentlig API ─────────────────────────────────────────────────────────


def auto_layout(diagram: Diagram) -> None:
    """Setter x/y (og height) for alle noder. Modifiserer diagram in-place."""
    if not diagram.nodes:
        return

    for node in diagram.nodes.values():
        fit_node_height(node)

    # Grupper per subgraph
    groups: dict[str | None, list[str]] = defaultdict(list)
    for nid, node in diagram.nodes.items():
        groups[node.subgraph_id].append(nid)

    # Topologisk ordnet per gruppe
    ordered: dict[str | None, list[str]] = {}
    for sid, ids in groups.items():
        ordered[sid] = _topological_order(ids, diagram.edges)

    # Layout hver subgraph internt (origo = 0,0), registrer utstrekning
    extents: dict[str, tuple[float, float]] = {}
    for sid in list(diagram.subgraphs.keys()):
        ids = ordered.get(sid, [])
        if not ids:
            continue
        w, h = _layout_grid(diagram, ids, origin=(0.0, 0.0))
        extents[sid] = (w, h)

    # Plasser subgraphs i et ytre grid
    _place_subgraphs(diagram, groups, extents)

    # Plasser frie noder etter subgraphene
    free_nodes = ordered.get(None, [])
    if free_nodes:
        offset_y = _extent_bottom(diagram, extents) + style.SUBGRAPH_OUTER_GAP
        _layout_grid(diagram, free_nodes, origin=(0.0, offset_y))


def fit_node_height(
    node: Node,
    *,
    min_height: float = style.DEFAULT_NODE_HEIGHT,
    line_height: float = style.NODE_LINE_HEIGHT,
    padding: float = style.NODE_PADDING,
) -> None:
    """Beregn node-høyde ut fra antall linjer i label."""
    label = node.label or node.id or ""
    line_count = max(1, label.count("\n") + 1)
    node.height = max(min_height, line_count * line_height + padding)


# ── Grid-layout ───────────────────────────────────────────────────────────


def _layout_grid(
    diagram: Diagram, node_ids: list[str], *, origin: tuple[float, float]
) -> tuple[float, float]:
    """Plasser noder i et kompakt grid med origo i øvre venstre hjørne.

    Returnerer (bredde, høyde) for gruppen.
    """
    if not node_ids:
        return (0.0, 0.0)

    n = len(node_ids)
    cols = max(2, min(style.GRID_COLS_MAX, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)

    # Forbered rad- og kolonnedimensjoner
    col_widths = [0.0] * cols
    row_heights = [0.0] * rows
    for idx, nid in enumerate(node_ids):
        r, c = divmod(idx, cols)
        node = diagram.nodes[nid]
        col_widths[c] = max(col_widths[c], node.width)
        row_heights[r] = max(row_heights[r], node.height)

    ox, oy = origin
    # Kumulative x/y-sentre per kolonne/rad
    col_centers: list[float] = []
    x_cursor = ox
    for w in col_widths:
        col_centers.append(x_cursor + w / 2)
        x_cursor += w + style.GRID_GAP_X
    total_w = x_cursor - style.GRID_GAP_X - ox

    row_centers: list[float] = []
    y_cursor = oy
    for h in row_heights:
        row_centers.append(y_cursor + h / 2)
        y_cursor += h + style.GRID_GAP_Y
    total_h = y_cursor - style.GRID_GAP_Y - oy

    for idx, nid in enumerate(node_ids):
        r, c = divmod(idx, cols)
        node = diagram.nodes[nid]
        node.x = col_centers[c]
        node.y = row_centers[r]

    return (total_w, total_h)


def _place_subgraphs(
    diagram: Diagram,
    groups: dict[str | None, list[str]],
    extents: dict[str, tuple[float, float]],
) -> None:
    """Plasser subgraphs i et ytre grid ved å translere medlemmene."""
    sg_ids = [sid for sid in diagram.subgraphs.keys() if sid in extents]
    if not sg_ids:
        return

    cols = max(1, min(style.SUBGRAPH_OUTER_COLS, len(sg_ids)))
    # Kolonne-bredde og rad-høyde i det ytre gridet
    col_w = [0.0] * cols
    rows = math.ceil(len(sg_ids) / cols)
    row_h = [0.0] * rows
    for i, sid in enumerate(sg_ids):
        r, c = divmod(i, cols)
        w, h = extents[sid]
        # Legg til headerbar-høyde + padding for rammen rundt
        frame_w = w + 2 * style.SUBGRAPH_PADDING
        frame_h = h + style.SUBGRAPH_HEADER_HEIGHT + 2 * style.SUBGRAPH_PADDING
        col_w[c] = max(col_w[c], frame_w)
        row_h[r] = max(row_h[r], frame_h)

    # Kumulative origin per kolonne/rad
    col_x: list[float] = []
    x = 0.0
    for w in col_w:
        col_x.append(x)
        x += w + style.SUBGRAPH_OUTER_GAP
    row_y: list[float] = []
    y = 0.0
    for h in row_h:
        row_y.append(y)
        y += h + style.SUBGRAPH_OUTER_GAP

    for i, sid in enumerate(sg_ids):
        r, c = divmod(i, cols)
        # Offset til øvre venstre "innhold-origo" inne i rammen
        ox = col_x[c] + style.SUBGRAPH_PADDING
        oy = row_y[r] + style.SUBGRAPH_HEADER_HEIGHT + style.SUBGRAPH_PADDING
        _translate_group(diagram, groups[sid], ox, oy)


def _translate_group(
    diagram: Diagram, node_ids: list[str], dx: float, dy: float
) -> None:
    for nid in node_ids:
        node = diagram.nodes[nid]
        node.x += dx
        node.y += dy


def _extent_bottom(
    diagram: Diagram, extents: dict[str, tuple[float, float]]
) -> float:
    if not extents:
        return 0.0
    max_y = 0.0
    for sid in extents:
        members = [n for n in diagram.nodes.values() if n.subgraph_id == sid]
        for n in members:
            max_y = max(max_y, n.y + n.height / 2)
    return max_y + style.SUBGRAPH_PADDING


# ── Topologisk sortering ──────────────────────────────────────────────────


def _topological_order(node_ids: list[str], edges: list[Edge]) -> list[str]:
    """Kahn-aktig sortering av node_ids basert på interne kanter.

    Sykler eller umatchede noder legges på slutten i opprinnelig rekkefølge.
    """
    id_set = set(node_ids)
    incoming: dict[str, set[str]] = {nid: set() for nid in node_ids}
    outgoing: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for e in edges:
        if e.from_id in id_set and e.to_id in id_set and e.from_id != e.to_id:
            incoming[e.to_id].add(e.from_id)
            outgoing[e.from_id].add(e.to_id)

    # Bevar opprinnelig rekkefølge for deterministisk output
    order_index = {nid: i for i, nid in enumerate(node_ids)}
    ready = sorted(
        (nid for nid in node_ids if not incoming[nid]),
        key=lambda n: order_index[n],
    )
    result: list[str] = []
    seen: set[str] = set()
    while ready:
        nid = ready.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        result.append(nid)
        children = sorted(outgoing[nid], key=lambda n: order_index[n])
        for child in children:
            incoming[child].discard(nid)
            if not incoming[child] and child not in seen:
                ready.append(child)

    # Legg til uplasserte (sykler) i opprinnelig rekkefølge
    for nid in node_ids:
        if nid not in seen:
            result.append(nid)

    return result
