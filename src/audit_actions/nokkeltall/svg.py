"""nokkeltall_svg.py — Ren-Python SVG-chartgenerering (null dependencies).

Genererer inline SVG-strenger for bruk i HTML-rapport.
"""

from __future__ import annotations

import math
from typing import Sequence


# ---------------------------------------------------------------------------
# Fargepaletter
# ---------------------------------------------------------------------------

PALETTE = ["#4472C4", "#ED7D31", "#A5A5A5", "#FFC000", "#5B9BD5", "#70AD47"]
PALETTE_SOFT = ["#6C9BD2", "#F4A460", "#BCBCBC", "#FFD54F", "#81B9E8", "#8FBF6C"]
GREEN = "#27AE60"
RED = "#E74C3C"
GREY = "#95A5A6"


# ---------------------------------------------------------------------------
# Kakediagram (donut)
# ---------------------------------------------------------------------------

def svg_donut(
    items: Sequence[dict],
    *,
    width: int = 280,
    height: int = 280,
    inner_radius: float = 0.55,
    label_key: str = "label",
    value_key: str = "value",
) -> str:
    """Generer SVG donut chart.

    items: [{"label": "Varekostnad", "value": 1000}, ...]
    """
    if not items:
        return ""

    total = sum(abs(float(d.get(value_key, 0) or 0)) for d in items)
    if total < 1e-9:
        return ""

    cx, cy = width / 2, height / 2 - 10
    r_outer = min(cx, cy) - 5
    r_inner = r_outer * inner_radius

    parts: list[str] = []
    angle = -90  # start at top

    for i, item in enumerate(items):
        val = abs(float(item.get(value_key, 0) or 0))
        if val < 1e-9:
            continue
        pct = val / total
        sweep = pct * 360

        a1 = math.radians(angle)
        a2 = math.radians(angle + sweep)

        x1_o = cx + r_outer * math.cos(a1)
        y1_o = cy + r_outer * math.sin(a1)
        x2_o = cx + r_outer * math.cos(a2)
        y2_o = cy + r_outer * math.sin(a2)

        x1_i = cx + r_inner * math.cos(a2)
        y1_i = cy + r_inner * math.sin(a2)
        x2_i = cx + r_inner * math.cos(a1)
        y2_i = cy + r_inner * math.sin(a1)

        large = 1 if sweep > 180 else 0
        color = PALETTE[i % len(PALETTE)]

        path = (
            f"M {x1_o:.1f} {y1_o:.1f} "
            f"A {r_outer:.1f} {r_outer:.1f} 0 {large} 1 {x2_o:.1f} {y2_o:.1f} "
            f"L {x1_i:.1f} {y1_i:.1f} "
            f"A {r_inner:.1f} {r_inner:.1f} 0 {large} 0 {x2_i:.1f} {y2_i:.1f} Z"
        )
        parts.append(f'<path d="{path}" fill="{color}" stroke="white" stroke-width="2"/>')

        angle += sweep

    # Legend under chart
    legend_y = height - 20
    legend_items: list[str] = []
    cols = min(len(items), 2)
    col_w = width / cols
    for i, item in enumerate(items):
        val = abs(float(item.get(value_key, 0) or 0))
        pct = (val / total * 100) if total > 1e-9 else 0
        label = str(item.get(label_key, ""))
        color = PALETTE[i % len(PALETTE)]
        col = i % cols
        row = i // cols
        lx = col * col_w + 5
        ly = legend_y + row * 18
        legend_items.append(
            f'<rect x="{lx:.0f}" y="{ly:.0f}" width="10" height="10" rx="2" fill="{color}"/>'
            f'<text x="{lx + 14:.0f}" y="{ly + 9:.0f}" font-size="11" fill="#333">'
            f'{label} ({pct:.0f}%)</text>'
        )

    total_h = height + (len(items) // cols) * 18
    return (
        f'<svg width="{width}" height="{total_h}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "".join(legend_items)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Horisontal bar chart
# ---------------------------------------------------------------------------

def svg_hbar(
    items: Sequence[dict],
    *,
    width: int = 500,
    bar_height: int = 28,
    gap: int = 6,
    label_key: str = "name",
    value_key: str = "value",
    formatted_key: str | None = "formatted",
    change_key: str | None = "change_pct",
    show_change: bool = True,
) -> str:
    """Generer horisontalt søylediagram med valgfri %-endring."""
    if not items:
        return ""

    max_val = max(abs(float(d.get(value_key, 0) or 0)) for d in items)
    if max_val < 1e-9:
        return ""

    label_w = 180
    bar_area_w = width - label_w - 100
    height = len(items) * (bar_height + gap) + 10

    parts: list[str] = []
    for i, item in enumerate(items):
        val = abs(float(item.get(value_key, 0) or 0))
        label = str(item.get(label_key, ""))
        if len(label) > 28:
            label = label[:26] + "..."

        bar_w = max(2, (val / max_val) * bar_area_w) if max_val > 1e-9 else 2
        y = i * (bar_height + gap) + 5
        color = PALETTE[i % len(PALETTE)]

        # Label
        parts.append(
            f'<text x="{label_w - 8}" y="{y + bar_height / 2 + 4:.0f}" '
            f'font-size="12" fill="#333" text-anchor="end">{_escape(label)}</text>'
        )

        # Bar
        parts.append(
            f'<rect x="{label_w}" y="{y}" width="{bar_w:.1f}" height="{bar_height}" '
            f'rx="3" fill="{color}" opacity="0.85"/>'
        )

        # Value
        disp = str(item.get(formatted_key, "")) if formatted_key else _fmt_compact(val)
        parts.append(
            f'<text x="{label_w + bar_w + 6:.0f}" y="{y + bar_height / 2 + 4:.0f}" '
            f'font-size="11" fill="#555">{_escape(disp)}</text>'
        )

        # Change badge
        if show_change and change_key:
            change = item.get(change_key)
            if change is not None:
                try:
                    ch = float(change)
                    ch_color = GREEN if ch >= 0 else RED
                    ch_text = f"+{ch:.0f}%" if ch >= 0 else f"{ch:.0f}%"
                    parts.append(
                        f'<text x="{width - 10}" y="{y + bar_height / 2 + 4:.0f}" '
                        f'font-size="10" fill="{ch_color}" text-anchor="end" '
                        f'font-weight="600">{ch_text}</text>'
                    )
                except (ValueError, TypeError):
                    pass

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# Vertikal bar chart (for resultat/balanse)
# ---------------------------------------------------------------------------

def svg_vbar(
    items: Sequence[dict],
    *,
    width: int = 500,
    height: int = 250,
    label_key: str = "name",
    value_key: str = "value",
    prev_key: str | None = "prev",
) -> str:
    """Vertikal søylediagram med optional forrige-år-sammenligning."""
    if not items:
        return ""

    has_prev = prev_key and any(d.get(prev_key) is not None for d in items)
    all_vals = [abs(float(d.get(value_key, 0) or 0)) for d in items]
    if has_prev:
        all_vals += [abs(float(d.get(prev_key, 0) or 0)) for d in items if d.get(prev_key) is not None]
    max_val = max(all_vals) if all_vals else 1
    if max_val < 1e-9:
        return ""

    n = len(items)
    margin_bottom = 75
    margin_top = 20
    margin_left = 30
    margin_right = 10
    chart_h = height - margin_bottom - margin_top
    chart_w = width - margin_left - margin_right

    group_w = chart_w / n
    bar_w = group_w * (0.35 if has_prev else 0.55)

    parts: list[str] = []
    baseline_y = margin_top + chart_h

    for i, item in enumerate(items):
        val = float(item.get(value_key, 0) or 0)
        label = str(item.get(label_key, ""))
        if len(label) > 20:
            label = label[:18] + "..."

        x_center = margin_left + group_w * i + group_w / 2
        bar_h = (abs(val) / max_val) * chart_h if max_val > 1e-9 else 0
        y = baseline_y - bar_h

        if has_prev:
            # Current year bar (right)
            x = x_center
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'rx="2" fill="{PALETTE[0]}" opacity="0.85"/>'
            )

            # Previous year bar (left)
            prev_val = float(item.get(prev_key, 0) or 0) if item.get(prev_key) is not None else None
            if prev_val is not None:
                prev_h = (abs(prev_val) / max_val) * chart_h
                prev_y = baseline_y - prev_h
                x_prev = x_center - bar_w - 2
                parts.append(
                    f'<rect x="{x_prev:.1f}" y="{prev_y:.1f}" width="{bar_w:.1f}" height="{prev_h:.1f}" '
                    f'rx="2" fill="{PALETTE_SOFT[0]}" opacity="0.5"/>'
                )
        else:
            x = x_center - bar_w / 2
            color = PALETTE[0] if val >= 0 else RED
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" '
                f'rx="2" fill="{color}" opacity="0.85"/>'
            )

        # Label (rotated)
        parts.append(
            f'<text x="{x_center:.0f}" y="{baseline_y + 14}" font-size="9" fill="#555" '
            f'text-anchor="end" transform="rotate(-40 {x_center:.0f} {baseline_y + 14})">'
            f'{_escape(label)}</text>'
        )

    # Baseline
    parts.append(
        f'<line x1="{margin_left}" y1="{baseline_y}" x2="{width - margin_right}" y2="{baseline_y}" '
        f'stroke="#ddd" stroke-width="1"/>'
    )

    return (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts)
        + "</svg>"
    )


# ---------------------------------------------------------------------------
# KPI-kort (mini SVG cards)
# ---------------------------------------------------------------------------

def svg_kpi_card(label: str, value: str, change_pct: float | None = None) -> str:
    """Generer et enkelt KPI-kort som HTML (ikke SVG — bruker CSS)."""
    change_html = ""
    if change_pct is not None:
        color = GREEN if change_pct >= 0 else RED
        arrow = "\u25B2" if change_pct >= 0 else "\u25BC"
        sign = "+" if change_pct >= 0 else ""
        change_html = (
            f'<span style="color:{color};font-size:12px;font-weight:600">'
            f'{arrow} {sign}{change_pct:.1f}%</span>'
        )

    return (
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{_escape(label)}</div>'
        f'<div class="kpi-value">{_escape(value)}</div>'
        f'{change_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Utils
# ---------------------------------------------------------------------------

def _escape(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _fmt_compact(val: float) -> str:
    if abs(val) >= 1e6:
        return f"{val / 1e6:.1f}M"
    if abs(val) >= 1e3:
        return f"{val / 1e3:.0f}k"
    return f"{val:.0f}"
