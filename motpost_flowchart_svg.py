"""motpost_flowchart_svg.py — Render motpost-tre som SVG flytdiagram.

Tegner bokser med piler mellom, der boks-størrelse reflekterer beløp
og pilbredde reflekterer flytandel.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from motpost_flowchart_engine import MotpostEdge, MotpostNode, MotpostTree


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

COLORS = [
    "#4472C4",   # Blå (root)
    "#ED7D31",   # Oransje (ledd 1)
    "#70AD47",   # Grønn (ledd 2)
    "#FFC000",   # Gul (ledd 3)
    "#5B9BD5",   # Lys blå
]

BG_COLORS = [
    "#E8EEF7",   # Lys blå bg
    "#FDF0E5",   # Lys oransje bg
    "#EFF6EA",   # Lys grønn bg
    "#FFF8E1",   # Lys gul bg
    "#EBF3FA",   # Lys blå bg
]

ARROW_COLOR = "#95A5A6"
TEXT_COLOR = "#2C3E50"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return html.escape(str(text))


def _format_amount(val: float) -> str:
    if abs(val) >= 1e6:
        return f"{val / 1e6:,.1f} M".replace(",", " ")
    if abs(val) >= 1e3:
        return f"{val / 1e3:,.0f} k".replace(",", " ")
    return f"{val:,.0f}".replace(",", " ")


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


# ---------------------------------------------------------------------------
# Layout calculations
# ---------------------------------------------------------------------------

BOX_W = 160
BOX_H = 60
BOX_MIN_H = 50
BOX_MAX_H = 80
COL_GAP = 120
ROW_GAP = 16
ARROW_HEAD = 8


def _calc_box_height(amount: float, max_amount: float) -> float:
    """Beregn bokshøyde proporsjonal med beløp."""
    if max_amount < 1e-9:
        return BOX_H
    ratio = amount / max_amount
    return _clamp(BOX_MIN_H + ratio * (BOX_MAX_H - BOX_MIN_H), BOX_MIN_H, BOX_MAX_H)


def _draw_box(
    x: float, y: float, w: float, h: float,
    konto: str, name: str, amount: float,
    color_idx: int,
    pct: float | None = None,
) -> str:
    """Tegn en konto-boks med avrundede hjørner."""
    border = COLORS[color_idx % len(COLORS)]
    bg = BG_COLORS[color_idx % len(BG_COLORS)]

    # Trunkér langt kontonavn
    display_name = name
    if len(display_name) > 20:
        display_name = display_name[:18] + "…"

    pct_text = f" ({pct:.0f}%)" if pct is not None else ""
    amount_text = _format_amount(amount)

    return (
        f'<rect x="{x:.0f}" y="{y:.0f}" width="{w}" height="{h:.0f}" '
        f'rx="6" fill="{bg}" stroke="{border}" stroke-width="2"/>'
        f'<text x="{x + w/2:.0f}" y="{y + 18:.0f}" text-anchor="middle" '
        f'font-size="11" font-weight="700" fill="{border}">'
        f'{_esc(konto)}{_esc(pct_text)}</text>'
        f'<text x="{x + w/2:.0f}" y="{y + 33:.0f}" text-anchor="middle" '
        f'font-size="9" fill="{TEXT_COLOR}">{_esc(display_name)}</text>'
        f'<text x="{x + w/2:.0f}" y="{y + 48:.0f}" text-anchor="middle" '
        f'font-size="12" font-weight="600" fill="{TEXT_COLOR}">{_esc(amount_text)}</text>'
    )


def _draw_arrow(
    x1: float, y1: float, x2: float, y2: float,
    width: float = 1.5,
    label: str = "",
) -> str:
    """Tegn pil fra (x1,y1) til (x2,y2) med valgfri label."""
    # Bezier kurve for jevn pil
    cx1 = x1 + (x2 - x1) * 0.4
    cx2 = x1 + (x2 - x1) * 0.6

    parts = [
        f'<path d="M {x1:.0f} {y1:.0f} C {cx1:.0f} {y1:.0f}, {cx2:.0f} {y2:.0f}, {x2:.0f} {y2:.0f}" '
        f'fill="none" stroke="{ARROW_COLOR}" stroke-width="{width:.1f}" '
        f'marker-end="url(#arrowhead)"/>',
    ]

    if label:
        mx = (x1 + x2) / 2
        my = (y1 + y2) / 2 - 6
        parts.append(
            f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" '
            f'font-size="9" fill="#7F8C8D">{_esc(label)}</text>'
        )

    return "".join(parts)


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

def render_motpost_flowchart(tree: "MotpostTree") -> str:
    """Render komplett motpost-tre som SVG."""
    if not tree.root_nodes:
        return ""

    # Samle alle noder i kolonner etter dybde
    columns: dict[int, list[dict]] = {}  # depth -> list of {node, edges, pct}

    for root in tree.root_nodes:
        columns.setdefault(0, []).append({
            "node": root, "pct": None,
        })
        for edge in root.edges:
            child_node = getattr(edge, "_child_node", None)
            columns.setdefault(1, []).append({
                "node_info": edge,
                "child_node": child_node,
                "parent_konto": root.konto,
                "pct": edge.pct,
            })
            if child_node:
                for edge2 in child_node.edges:
                    columns.setdefault(2, []).append({
                        "node_info": edge2,
                        "parent_konto": child_node.konto,
                        "pct": edge2.pct,
                    })

    # Beregn max beløp for proporsjonal størrelse
    all_amounts: list[float] = []
    for root in tree.root_nodes:
        all_amounts.append(root.total_amount)
        for edge in root.edges:
            all_amounts.append(edge.amount)
    max_amount = max(all_amounts) if all_amounts else 1.0

    # Layout: beregn posisjoner
    margin_x = 30
    margin_y = 30
    parts: list[str] = []

    # Tracking av boks-posisjoner for piler
    box_positions: dict[str, tuple[float, float, float, float]] = {}
    # key = "depth:konto" -> (x, y, w, h)

    total_h = margin_y
    col_tops: dict[int, float] = {}

    # Beregn høyder per kolonne
    for depth in sorted(columns.keys()):
        col = columns[depth]
        col_top = margin_y
        x = margin_x + depth * (BOX_W + COL_GAP)

        for item in col:
            if depth == 0:
                node = item["node"]
                h = _calc_box_height(node.total_amount, max_amount)
                parts.append(_draw_box(
                    x, col_top, BOX_W, h,
                    node.konto, node.konto_name, node.total_amount,
                    color_idx=0,
                ))
                box_positions[f"0:{node.konto}"] = (x, col_top, BOX_W, h)
                col_top += h + ROW_GAP
            else:
                edge_info = item["node_info"]
                h = _calc_box_height(edge_info.amount, max_amount)
                parts.append(_draw_box(
                    x, col_top, BOX_W, h,
                    edge_info.target, edge_info.target_name, edge_info.amount,
                    color_idx=depth,
                    pct=edge_info.pct,
                ))
                key = f"{depth}:{edge_info.target}"
                box_positions[key] = (x, col_top, BOX_W, h)
                col_top += h + ROW_GAP

        col_tops[depth] = col_top
        total_h = max(total_h, col_top)

    # Tegn piler
    arrow_parts: list[str] = []
    for root in tree.root_nodes:
        src_key = f"0:{root.konto}"
        if src_key not in box_positions:
            continue
        sx, sy, sw, sh = box_positions[src_key]

        for edge in root.edges:
            tgt_key = f"1:{edge.target}"
            if tgt_key not in box_positions:
                continue
            tx, ty, tw, th = box_positions[tgt_key]

            arrow_w = _clamp(edge.pct / 20, 1.0, 4.0)
            arrow_parts.append(_draw_arrow(
                sx + sw, sy + sh / 2,
                tx, ty + th / 2,
                width=arrow_w,
                label=f"{edge.pct:.0f}%",
            ))

            # Ledd 2 piler
            child_node = getattr(edge, "_child_node", None)
            if child_node:
                for edge2 in child_node.edges:
                    tgt_key2 = f"2:{edge2.target}"
                    if tgt_key2 not in box_positions:
                        continue
                    tx2, ty2, tw2, th2 = box_positions[tgt_key2]
                    arrow_w2 = _clamp(edge2.pct / 20, 1.0, 4.0)
                    arrow_parts.append(_draw_arrow(
                        tx + tw, ty + th / 2,
                        tx2, ty2 + th2 / 2,
                        width=arrow_w2,
                        label=f"{edge2.pct:.0f}%",
                    ))

    total_w = margin_x + (len(columns)) * (BOX_W + COL_GAP)
    total_h += margin_y

    # Bygge SVG
    defs = (
        '<defs>'
        f'<marker id="arrowhead" markerWidth="{ARROW_HEAD}" markerHeight="{ARROW_HEAD}" '
        f'refX="{ARROW_HEAD}" refY="{ARROW_HEAD // 2}" orient="auto">'
        f'<polygon points="0 0, {ARROW_HEAD} {ARROW_HEAD // 2}, 0 {ARROW_HEAD}" '
        f'fill="{ARROW_COLOR}"/>'
        '</marker>'
        '</defs>'
    )

    svg = (
        f'<svg width="{total_w:.0f}" height="{total_h:.0f}" '
        f'xmlns="http://www.w3.org/2000/svg" '
        f'style="font-family: Segoe UI, system-ui, sans-serif">'
        f'{defs}'
        + "".join(arrow_parts)
        + "".join(parts)
        + '</svg>'
    )

    return svg
