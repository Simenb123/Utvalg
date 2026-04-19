"""page_ar_chart.py — org-kart-funksjonalitet for ARPage.

Utskilt fra page_ar.py. Modulfunksjoner tar page som første argument.
ARPage beholder tynne delegator-metoder for bakoverkompatibilitet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tkinter as tk

from page_ar_formatters import (
    _fmt_optional_pct,
    _fmt_pct,
    _fmt_signed_thousand,
    _relation_accent,
    _relation_fill,
    _relation_label,
    _safe_text,
)


def is_chart_tab_selected(page) -> bool:
    try:
        return str(page._nb.select()) == str(page._frm_chart)
    except Exception:
        return False

def on_tab_changed(page, event=None) -> None:
    if event is not None and getattr(event, "widget", None) is not page._nb:
        return
    if page._chart_dirty and not page._overview_loading and page._is_chart_tab_selected():
        page._refresh_org_chart()


def draw_box(
    page,
    canvas: tk.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    title: str,
    subtitle: str,
    fill: str,
    accent: str = "#98A2B3",
    action_key: str | None = None,
) -> None:
    left = x - width / 2
    top = y - height / 2
    right = x + width / 2
    bottom = y + height / 2
    tags = ("chart-node",)
    if action_key:
        tags = ("chart-node", action_key)
    canvas.create_rectangle(left + 2, top + 3, right + 2, bottom + 3, fill="#E4E7EC", outline="", tags=tags)
    canvas.create_rectangle(left, top, right, bottom, fill=fill, outline="#D0D5DD", width=1, tags=tags)
    canvas.create_rectangle(left, top, right, top + 4, fill=accent, outline=accent, tags=tags)
    canvas.create_text(x, y - 6, text=title, font=("Segoe UI", 9, "bold"), width=width - 16, tags=tags)
    canvas.create_text(x, y + 12, text=subtitle, font=("Segoe UI", 8), width=width - 16, fill="#475467", tags=tags)

def chart_action_key_from_current(page) -> str:
    canvas = page._org_canvas
    for tag in canvas.gettags("current"):
        if tag.startswith("node:"):
            return tag
    return ""

def on_chart_press(page, event) -> None:
    page._chart_dragging = False
    page._chart_drag_node = None
    page._chart_press_xy = (int(event.x), int(event.y))
    action_key = page._chart_action_key_from_current()
    page._chart_pending_action = page._chart_node_actions.get(action_key)
    if action_key:
        page._chart_drag_node = action_key
    else:
        page._org_canvas.scan_mark(event.x, event.y)

def on_chart_drag(page, event) -> None:
    dx = abs(int(event.x) - page._chart_press_xy[0])
    dy = abs(int(event.y) - page._chart_press_xy[1])
    if dx > 4 or dy > 4:
        page._chart_dragging = True
    if page._chart_drag_node and page._chart_dragging:
        canvas = page._org_canvas
        # Convert to canvas coords
        cx = canvas.canvasx(event.x)
        cy = canvas.canvasy(event.y)
        # Move all items with this action_key tag
        ak = page._chart_drag_node
        pos_key = page._chart_node_keys.get(ak, "")
        if not pos_key:
            return
        old_x, old_y = page._chart_node_centers.get(pos_key, (cx, cy))
        move_dx = cx - old_x
        move_dy = cy - old_y
        for item_id in canvas.find_withtag(ak):
            canvas.move(item_id, move_dx, move_dy)
        page._chart_node_centers[pos_key] = (cx, cy)
        page._redraw_edges_for_node(pos_key)
    elif not page._chart_drag_node:
        page._org_canvas.scan_dragto(event.x, event.y, gain=1)

def on_chart_release(page, _event) -> None:
    if page._chart_dragging and page._chart_drag_node:
        page._save_chart_positions()
        page._update_chart_scrollregion()
        page._chart_drag_node = None
        page._chart_pending_action = None
        return
    action = page._chart_pending_action
    page._chart_pending_action = None
    page._chart_drag_node = None
    if page._chart_dragging or not action:
        return
    page._execute_chart_action(action)

def on_chart_mousewheel(page, event) -> None:
    if event.delta == 0:
        return
    factor = 1.1 if event.delta > 0 else 1 / 1.1
    page._chart_apply_zoom(factor, event.x, event.y)

def update_chart_zoom_label(page) -> None:
    page.var_chart_zoom.set(f"{int(round(page._chart_zoom * 100))} %")

def chart_apply_zoom(page, factor: float, x: float | None = None, y: float | None = None) -> None:
    canvas = page._org_canvas
    new_zoom = max(0.6, min(2.5, page._chart_zoom * factor))
    factor = new_zoom / page._chart_zoom
    if abs(factor - 1.0) < 0.001:
        return
    cx = canvas.canvasx(x if x is not None else canvas.winfo_width() / 2)
    cy = canvas.canvasy(y if y is not None else canvas.winfo_height() / 2)
    page._chart_zoom = new_zoom
    page._update_chart_zoom_label()
    canvas.scale("all", cx, cy, factor, factor)
    bbox = canvas.bbox("all")
    if bbox:
        canvas.configure(scrollregion=(bbox[0] - 40, bbox[1] - 40, bbox[2] + 40, bbox[3] + 40))

def chart_reset_view(page) -> None:
    if page._overview_loading:
        return
    page._clear_chart_positions()
    page._refresh_org_chart()

def chart_fit_view(page) -> None:
    if page._overview_loading:
        return
    canvas = page._org_canvas
    canvas.update_idletasks()
    bbox = canvas.bbox("all")
    if not bbox:
        return
    content_w = max(1, bbox[2] - bbox[0])
    content_h = max(1, bbox[3] - bbox[1])
    viewport_w = max(1, canvas.winfo_width() - 40)
    viewport_h = max(1, canvas.winfo_height() - 40)
    factor = min(viewport_w / content_w, viewport_h / content_h, 1.5)
    factor = max(0.5, min(2.0, factor))
    page._chart_zoom = 1.0
    page._refresh_org_chart()
    if abs(factor - 1.0) > 0.01:
        page._chart_apply_zoom(factor)

# ── Chart position persistence ──────────────────────────────────

def chart_positions_path(page) -> Path | None:
    if not page._client or not page._year:
        return None
    import client_store
    d = client_store.years_dir(page._client, year=page._year) / "aksjonaerregister"
    d.mkdir(parents=True, exist_ok=True)
    return d / "chart_positions.json"

def load_chart_positions(page) -> dict[str, list[float]]:
    p = page._chart_positions_path()
    if not p or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def save_chart_positions(page) -> None:
    p = page._chart_positions_path()
    if not p:
        return
    data = {k: list(v) for k, v in page._chart_node_centers.items()}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass

def clear_chart_positions(page) -> None:
    p = page._chart_positions_path()
    if p and p.exists():
        try:
            p.unlink()
        except Exception:
            pass

# ── Edge redrawing ──────────────────────────────────────────────

def redraw_edges_for_node(page, pos_key: str) -> None:
    canvas = page._org_canvas
    bw, bh = page._chart_box_size
    for from_key, to_key, line_tag, lbl_tag in page._chart_edges:
        if from_key != pos_key and to_key != pos_key:
            continue
        fx, fy = page._chart_node_centers.get(from_key, (0, 0))
        tx, ty = page._chart_node_centers.get(to_key, (0, 0))
        # Line: from bottom of upper node to top of lower node
        if fy < ty:
            y1, y2 = fy + bh / 2, ty - bh / 2
        else:
            y1, y2 = fy - bh / 2, ty + bh / 2
        for item in canvas.find_withtag(line_tag):
            canvas.coords(item, fx, y1, tx, y2)
        for item in canvas.find_withtag(lbl_tag):
            canvas.coords(item, (fx + tx) / 2, (y1 + y2) / 2)

def update_chart_scrollregion(page) -> None:
    canvas = page._org_canvas
    bbox = canvas.bbox("all")
    if bbox:
        pad = 30
        canvas.configure(scrollregion=(bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad))

def select_owned_row(page, *, company_orgnr: str = "", company_name: str = "") -> None:
    page._nb.select(0)
    target_orgnr = _safe_text(company_orgnr)
    target_name = _safe_text(company_name).casefold()
    for iid, row in page._owned_rows_by_iid.items():
        if target_orgnr and _safe_text(row.get("company_orgnr")) == target_orgnr:
            page._tree_owned.selection_set((iid,))
            page._tree_owned.focus(iid)
            page._tree_owned.see(iid)
            page._on_owned_selected()
            return
        if target_name and _safe_text(row.get("company_name")).casefold() == target_name:
            page._tree_owned.selection_set((iid,))
            page._tree_owned.focus(iid)
            page._tree_owned.see(iid)
            page._on_owned_selected()
            return

def select_owner_row(page, *, owner_orgnr: str = "", owner_name: str = "") -> None:
    page._nb.select(1)
    target_orgnr = _safe_text(owner_orgnr)
    target_name = _safe_text(owner_name).casefold()
    for iid, row in page._owners_rows_by_iid.items():
        if target_orgnr and _safe_text(row.get("shareholder_orgnr")) == target_orgnr:
            page._tree_owners.selection_set((iid,))
            page._tree_owners.focus(iid)
            page._tree_owners.see(iid)
            return
        if target_name and _safe_text(row.get("shareholder_name")).casefold() == target_name:
            page._tree_owners.selection_set((iid,))
            page._tree_owners.focus(iid)
            page._tree_owners.see(iid)
            return

def execute_chart_action(page, action: dict[str, Any]) -> None:
    kind = _safe_text(action.get("kind"))
    if kind == "owned":
        page._select_owned_row(
            company_orgnr=_safe_text(action.get("company_orgnr")),
            company_name=_safe_text(action.get("company_name")),
        )
        return
    if kind == "owner":
        page._select_owner_row(
            owner_orgnr=_safe_text(action.get("shareholder_orgnr")),
            owner_name=_safe_text(action.get("shareholder_name")),
        )
        return
    if kind == "root":
        page._nb.select(0)

def refresh_org_chart(page) -> None:
    canvas = page._org_canvas
    canvas.delete("all")
    canvas.configure(background="#FAFAF8")
    page._chart_node_actions = {}
    page._chart_node_keys = {}
    page._chart_node_centers = {}
    page._chart_edges = []
    page._chart_zoom = 1.0
    page._update_chart_zoom_label()

    root_name = page._client or "Klient"
    root_orgnr = _safe_text(page._overview.get("client_orgnr"))
    owners = page._overview.get("owners") or []
    children = page._overview.get("owned_companies") or []

    if not root_name or (not root_orgnr and not owners and not children):
        canvas.create_text(320, 120, text="Ingen eierdata tilgjengelig ennå.", font=("Segoe UI", 10), fill="#667085")
        canvas.configure(scrollregion=(0, 0, 640, 240))
        page._chart_dirty = False
        return

    box_w, box_h = 172, 56
    page._chart_box_size = (box_w, box_h)

    # Load saved positions
    saved = page._load_chart_positions()

    # Compute default positions
    node_count = max(len(owners), len(children), 1)
    total_w = max(800, node_count * 200)
    center_x = total_w / 2
    owner_y_default = 60
    root_y_default = 200
    child_y_default = 340

    # ── Root node ───────────────────────────────────────────────
    root_pos_key = f"root:{root_orgnr or root_name}"
    root_action_key = "node:root"
    rx, ry = saved.get(root_pos_key, [center_x, root_y_default])
    page._chart_node_keys[root_action_key] = root_pos_key
    page._chart_node_centers[root_pos_key] = (rx, ry)
    page._chart_node_actions[root_action_key] = {"kind": "root"}
    page._draw_box(
        canvas, rx, ry, box_w + 16, box_h + 4,
        title=root_name,
        subtitle=root_orgnr or page._year,
        fill="#E6F0FF", accent="#2952A3",
        action_key=root_action_key,
    )

    # Self-ownership note (attached to root)
    self_ownership = page._overview.get("self_ownership") or {}
    if self_ownership:
        note = f"Egne aksjer: {_fmt_pct(self_ownership.get('ownership_pct'))}%"
        shares = int(self_ownership.get("shares") or 0)
        total = int(self_ownership.get("total_shares") or 0)
        if shares and total:
            note = f"{note} ({shares} av {total})"
        canvas.create_text(
            rx, ry + 46, text=note,
            font=("Segoe UI", 8, "italic"), fill="#8A5A00",
            tags=("chart-node", root_action_key),
        )

    # ── Owner nodes ─────────────────────────────────────────────
    if owners:
        owner_gap = total_w / (len(owners) + 1)
        for idx, row in enumerate(owners, start=1):
            orgnr = _safe_text(row.get("shareholder_orgnr"))
            name = _safe_text(row.get("shareholder_name"))
            pos_key = f"owner:{orgnr or name}"
            action_key = f"node:owner:{idx}"
            default_x = owner_gap * idx
            ox, oy = saved.get(pos_key, [default_x, owner_y_default])
            page._chart_node_keys[action_key] = pos_key
            page._chart_node_centers[pos_key] = (ox, oy)
            page._chart_node_actions[action_key] = {
                "kind": "owner",
                "shareholder_name": name,
                "shareholder_orgnr": orgnr,
            }
            page._draw_box(
                canvas, ox, oy, box_w, box_h,
                title=name or "Ukjent eier",
                subtitle=orgnr or _safe_text(row.get("shareholder_kind")) or "-",
                fill="#F8FAFC", accent="#667085",
                action_key=action_key,
            )
            # Edge: owner → root
            line_tag = f"edge:line:{pos_key}"
            lbl_tag = f"edge:lbl:{pos_key}"
            y1 = oy + box_h / 2
            y2 = ry - (box_h + 4) / 2
            canvas.create_line(ox, y1, rx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))
            canvas.create_text(
                (ox + rx) / 2, (y1 + y2) / 2,
                text=f"{_fmt_pct(row.get('ownership_pct'))}%",
                font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),
            )
            page._chart_edges.append((pos_key, root_pos_key, line_tag, lbl_tag))

    # ── Child nodes ─────────────────────────────────────────────
    if children:
        child_gap = total_w / (len(children) + 1)
        for idx, row in enumerate(children, start=1):
            orgnr = _safe_text(row.get("company_orgnr"))
            name = _safe_text(row.get("company_name"))
            pos_key = f"child:{orgnr or name}"
            action_key = f"node:owned:{idx}"
            default_x = child_gap * idx
            cx, cy = saved.get(pos_key, [default_x, child_y_default])
            page._chart_node_keys[action_key] = pos_key
            page._chart_node_centers[pos_key] = (cx, cy)
            page._chart_node_actions[action_key] = {
                "kind": "owned",
                "company_name": name,
                "company_orgnr": orgnr,
            }
            page._draw_box(
                canvas, cx, cy, box_w, box_h,
                title=name or "Ukjent selskap",
                subtitle=f"{orgnr or '-'} | {_relation_label(row.get('relation_type'))}",
                fill=_relation_fill(row.get("relation_type")),
                accent=_relation_accent(row.get("relation_type")),
                action_key=action_key,
            )
            # Edge: root → child
            line_tag = f"edge:line:{pos_key}"
            lbl_tag = f"edge:lbl:{pos_key}"
            y1 = ry + (box_h + 4) / 2
            y2 = cy - box_h / 2
            canvas.create_line(rx, y1, cx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))
            canvas.create_text(
                (rx + cx) / 2, (y1 + y2) / 2,
                text=f"{_fmt_pct(row.get('ownership_pct'))}%",
                font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),
            )
            page._chart_edges.append((root_pos_key, pos_key, line_tag, lbl_tag))

    # Circular ownership warning
    if page._year:
        try:
            from ar_store import detect_circular_ownership
            cycles = detect_circular_ownership(page._year)
            if cycles:
                cycle_text = "Sirkulært eierskap: " + "; ".join(
                    " \u2192 ".join(c) + " \u2192 " + c[0] for c in cycles[:3]
                )
                all_ys = [v[1] for v in page._chart_node_centers.values()]
                warn_y = max(all_ys) + box_h / 2 + 30 if all_ys else 400
                canvas.create_text(
                    center_x, warn_y, text=f"\u26a0 {cycle_text}",
                    font=("Segoe UI", 9), fill="#856404",
                )
        except Exception:
            pass

    # Set scrollregion and auto-fit
    page._update_chart_scrollregion()
    canvas.update_idletasks()
    page._chart_dirty = False

    # Auto-fit to viewport on first draw
    if not saved:
        page.after(50, page._chart_fit_view)

