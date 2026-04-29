"""page_ar_chart.py — org-kart-funksjonalitet for ARPage.

Utskilt fra page_ar.py. Modulfunksjoner tar page som første argument.
ARPage beholder tynne delegator-metoder for bakoverkompatibilitet.

Modellbasert rendering:
- ``page._chart_node_centers`` holder LOGISKE koordinater (uavhengig av zoom).
- ``page._chart_zoom`` er kun en visningsfaktor; canvas-koordinater =
  logical * zoom.
- Zoom utløser re-render fra logisk modell (ingen ``canvas.scale``).
- Drag oppdaterer logiske koordinater, slik at lagring og zoom er konsistente.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

import tkinter as tk

from ..backend.formatters import (
    _fmt_optional_pct,
    _fmt_pct,
    _fmt_signed_thousand,
    _relation_accent,
    _relation_fill,
    _relation_label,
    _safe_text,
)

logger = logging.getLogger(__name__)


# ── Koordinat-hjelpere ──────────────────────────────────────────

def _logical_to_canvas(page, lx: float, ly: float) -> tuple[float, float]:
    z = getattr(page, "_chart_zoom", 1.0) or 1.0
    return lx * z, ly * z


def _canvas_to_logical(page, cx: float, cy: float) -> tuple[float, float]:
    z = getattr(page, "_chart_zoom", 1.0) or 1.0
    return cx / z, cy / z


# ── Tab/visibility ──────────────────────────────────────────────

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


# ── Tegning ─────────────────────────────────────────────────────

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
    accent: str = "#98A2B3",  # design-exception: chart-palette
    action_key: str | None = None,
    dashed: bool = False,
) -> None:
    left = x - width / 2
    top = y - height / 2
    right = x + width / 2
    bottom = y + height / 2
    tags: tuple[str, ...] = ("chart-node",)
    if action_key:
        tags = ("chart-node", action_key)
    canvas.create_rectangle(left + 2, top + 3, right + 2, bottom + 3, fill="#E4E7EC", outline="", tags=tags)  # design-exception: chart-fill-palette
    border_kwargs: dict[str, Any] = {"outline": "#D0D5DD", "width": 1, "tags": tags}  # design-exception: chart-palette
    if dashed:
        border_kwargs["dash"] = (3, 2)
    canvas.create_rectangle(left, top, right, bottom, fill=fill, **border_kwargs)
    canvas.create_rectangle(left, top, right, top + 4, fill=accent, outline=accent, tags=tags)
    canvas.create_text(x, y - 6, text=title, font=("Segoe UI", 9, "bold"), width=width - 16, tags=tags)
    canvas.create_text(x, y + 12, text=subtitle, font=("Segoe UI", 8), width=width - 16, fill="#475467", tags=tags)  # design-exception: chart-fill-palette


def chart_action_key_from_current(page) -> str:
    canvas = page._org_canvas
    for tag in canvas.gettags("current"):
        if tag.startswith("node:"):
            return tag
    return ""


# ── Mus-interaksjon ─────────────────────────────────────────────

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
        ak = page._chart_drag_node
        pos_key = page._chart_node_keys.get(ak, "")
        if not pos_key:
            return
        # Event → canvas-koord → logisk koord
        event_cx = canvas.canvasx(event.x)
        event_cy = canvas.canvasy(event.y)
        new_lx, new_ly = _canvas_to_logical(page, event_cx, event_cy)
        old_lx, old_ly = page._chart_node_centers.get(pos_key, (new_lx, new_ly))
        # Flytt selve canvas-elementene i canvas-koord
        z = getattr(page, "_chart_zoom", 1.0) or 1.0
        move_dx = (new_lx - old_lx) * z
        move_dy = (new_ly - old_ly) * z
        for item_id in canvas.find_withtag(ak):
            canvas.move(item_id, move_dx, move_dy)
        page._chart_node_centers[pos_key] = (new_lx, new_ly)
        page._redraw_edges_for_node(pos_key)
    elif not page._chart_drag_node:
        page._org_canvas.scan_dragto(event.x, event.y, gain=1)


def on_chart_release(page, _event) -> None:
    was_dragging = page._chart_dragging and page._chart_drag_node is not None
    if was_dragging:
        page._save_chart_positions()
        page._update_chart_scrollregion()
        page._chart_drag_node = None
        page._chart_pending_action = None
        page._chart_dragging = False
        # Hvis en overview-oppdatering kom mens brukeren dro, redraw nå.
        if page._chart_dirty and page._is_chart_tab_selected() and not page._overview_loading:
            page._refresh_org_chart()
        return
    action = page._chart_pending_action
    page._chart_pending_action = None
    page._chart_drag_node = None
    page._chart_dragging = False
    if not action:
        return
    page._execute_chart_action(action)


def on_chart_mousewheel(page, event) -> None:
    if event.delta == 0:
        return
    factor = 1.1 if event.delta > 0 else 1 / 1.1
    page._chart_apply_zoom(factor, event.x, event.y)


def on_chart_double_click(page, _event) -> None:
    canvas = page._org_canvas
    action_key = ""
    for tag in canvas.gettags("current"):
        if tag.startswith("node:"):
            action_key = tag
            break
    if not action_key:
        return
    action = page._chart_node_actions.get(action_key)
    if not action:
        return
    kind = (action.get("kind") or "").lower()
    if kind not in {"owner", "indirect_owner", "indirect_person"}:
        return
    opener = getattr(page, "_open_owner_drilldown", None)
    if not callable(opener):
        return
    opener(
        orgnr=_safe_text(action.get("shareholder_orgnr")),
        name=_safe_text(action.get("shareholder_name")),
        lookup_year=_safe_text(action.get("lookup_year")),
    )


def update_chart_zoom_label(page) -> None:
    page.var_chart_zoom.set(f"{int(round(page._chart_zoom * 100))} %")


def chart_apply_zoom(page, factor: float, x: float | None = None, y: float | None = None) -> None:
    """Endre visningsfaktor og re-render fra logisk modell.

    Bevarer det logiske punktet under markøren, slik at innholdet zoomes mot
    peker-posisjonen (ikke mot origo).
    """
    canvas = page._org_canvas
    old_zoom = page._chart_zoom or 1.0
    new_zoom = max(0.6, min(2.5, old_zoom * factor))
    if abs(new_zoom - old_zoom) < 0.001:
        return

    # Finn det logiske punktet under musa FØR vi endrer zoom.
    px = x if x is not None else canvas.winfo_width() / 2
    py = y if y is not None else canvas.winfo_height() / 2
    canvas_x = canvas.canvasx(px)
    canvas_y = canvas.canvasy(py)
    logical_x = canvas_x / old_zoom
    logical_y = canvas_y / old_zoom

    page._chart_zoom = new_zoom
    page._update_chart_zoom_label()
    # Re-render fra logisk modell — ingen canvas.scale.
    _render_from_model(page, suppress_auto_fit=True)

    # Hold det logiske punktet under samme skjerm-posisjon etter re-render.
    new_canvas_x = logical_x * new_zoom
    new_canvas_y = logical_y * new_zoom
    try:
        bbox = canvas.bbox("all")
        if bbox:
            total_w = max(1.0, bbox[2] - bbox[0])
            total_h = max(1.0, bbox[3] - bbox[1])
            canvas.xview_moveto(max(0.0, (new_canvas_x - px - bbox[0]) / total_w))
            canvas.yview_moveto(max(0.0, (new_canvas_y - py - bbox[1]) / total_h))
    except Exception:
        pass


def chart_reset_view(page) -> None:
    if page._overview_loading:
        return
    page._clear_chart_positions()
    # Tøm både lagret fil og in-memory posisjoner så default-layout brukes.
    page._chart_node_centers = {}
    page._chart_zoom = 1.0
    page._update_chart_zoom_label()
    page._refresh_org_chart()


def chart_fit_view(page) -> None:
    """Beregn zoom slik at hele innholdet passer i viewport, og re-render.

    Kaller ikke ``_refresh_org_chart`` rekursivt; endrer ``_chart_zoom`` og
    re-rendrer én gang via ``_render_from_model``.
    """
    if page._overview_loading:
        return
    canvas = page._org_canvas
    try:
        canvas.update_idletasks()
    except Exception:
        pass
    if not page._chart_node_centers:
        return
    # Beregn bbox fra logiske node-sentre.
    box_w, box_h = getattr(page, "_chart_box_size", (172, 56))
    xs = [lx for (lx, _ly) in page._chart_node_centers.values()]
    ys = [ly for (_lx, ly) in page._chart_node_centers.values()]
    if not xs or not ys:
        return
    logical_w = max(1.0, (max(xs) - min(xs)) + box_w + 16)
    logical_h = max(1.0, (max(ys) - min(ys)) + box_h + 30)
    viewport_w = max(1, canvas.winfo_width() - 40)
    viewport_h = max(1, canvas.winfo_height() - 40)
    if viewport_w <= 1 or viewport_h <= 1:
        return
    factor = min(viewport_w / logical_w, viewport_h / logical_h)
    factor = max(0.6, min(2.0, factor))
    if abs(factor - page._chart_zoom) < 0.01:
        return
    page._chart_zoom = factor
    page._update_chart_zoom_label()
    _render_from_model(page, suppress_auto_fit=True)


# ── Posisjonslagring ────────────────────────────────────────────

def chart_positions_path(page) -> Path | None:
    if not page._client or not page._year:
        return None
    import src.shared.client_store.store as client_store
    d = client_store.years_dir(page._client, year=page._year) / "aksjonaerregister"
    d.mkdir(parents=True, exist_ok=True)
    return d / "chart_positions.json"


def _validate_positions_payload(data: Any) -> dict[str, list[float]]:
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, list[float]] = {}
    for key, value in data.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            continue
        try:
            cleaned[key] = [float(value[0]), float(value[1])]
        except (TypeError, ValueError):
            continue
    return cleaned


def load_chart_positions(page) -> dict[str, list[float]]:
    p = page._chart_positions_path()
    if not p or not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Kunne ikke lese chart_positions.json (%s): %s", p, exc)
        return {}
    cleaned = _validate_positions_payload(data)
    if not cleaned and data:
        logger.warning("chart_positions.json hadde ugyldig struktur: %s", p)
    return cleaned


def save_chart_positions(page) -> None:
    p = page._chart_positions_path()
    if not p:
        return
    data = {k: [float(v[0]), float(v[1])] for k, v in page._chart_node_centers.items()}
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # Atomisk skriv: temp + replace, så vi ikke etterlater halvskrevet fil.
        fd, tmp_path = tempfile.mkstemp(
            prefix=p.name + ".", suffix=".tmp", dir=str(p.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp_path, p)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except OSError as exc:
        logger.warning("Kunne ikke lagre chart_positions.json (%s): %s", p, exc)


def clear_chart_positions(page) -> None:
    p = page._chart_positions_path()
    if p and p.exists():
        try:
            p.unlink()
        except OSError as exc:
            logger.warning("Kunne ikke slette chart_positions.json (%s): %s", p, exc)


# ── Kant-tegning ────────────────────────────────────────────────

def redraw_edges_for_node(page, pos_key: str) -> None:
    """Oppdater kanter knyttet til en node basert på logiske posisjoner."""
    canvas = page._org_canvas
    box_w, box_h = page._chart_box_size
    z = getattr(page, "_chart_zoom", 1.0) or 1.0
    for from_key, to_key, line_tag, lbl_tag in page._chart_edges:
        if from_key != pos_key and to_key != pos_key:
            continue
        flx, fly = page._chart_node_centers.get(from_key, (0, 0))
        tlx, tly = page._chart_node_centers.get(to_key, (0, 0))
        fx, fy = flx * z, fly * z
        tx, ty = tlx * z, tly * z
        half_h = (box_h * z) / 2
        if fy < ty:
            y1, y2 = fy + half_h, ty - half_h
        else:
            y1, y2 = fy - half_h, ty + half_h
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


# ── Rad-seleksjon fra kart-klikk ────────────────────────────────

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
    if kind in {"indirect_owner", "indirect_person"}:
        opener = getattr(page, "_open_owner_drilldown", None)
        if callable(opener):
            opener(
                orgnr=_safe_text(action.get("shareholder_orgnr")),
                name=_safe_text(action.get("shareholder_name")),
                lookup_year=_safe_text(action.get("lookup_year")),
            )
        return
    if kind == "root":
        page._nb.select(0)


# ── Default layout (logiske koordinater) ────────────────────────

_MAX_ROW_COLS = 6
_BOX_W_LOGICAL = 172
_BOX_H_LOGICAL = 56
_COL_GAP = 28
_ROW_GAP = 42

# Indirekte eierkjede: hvor mange ledd over direkte eier vi henter.
# 3 ledd over root holder kartet ryddig — Excel-kryssreferansen går dypere.
_CHART_INDIRECT_MAX_DEPTH = 3
# Smalere boks for indirekte ledd så flere får plass uten overlapp.
_INDIRECT_BOX_W = 152


def _sort_owners(owners: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple:
        return (
            -(float(row.get("ownership_pct") or 0.0)),
            _safe_text(row.get("shareholder_name")).casefold(),
            _safe_text(row.get("shareholder_orgnr")),
        )
    return sorted(owners, key=key)


def _sort_children(children: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(row: dict[str, Any]) -> tuple:
        return (
            _safe_text(row.get("relation_type")).casefold(),
            -(float(row.get("ownership_pct") or 0.0)),
            _safe_text(row.get("company_name")).casefold(),
            _safe_text(row.get("company_orgnr")),
        )
    return sorted(children, key=key)


def _distribute_rows(count: int, viewport_w_logical: float) -> tuple[int, list[int]]:
    """Returner (rad-antall, liste av kolonner-per-rad).

    Passer inntil ``_MAX_ROW_COLS`` per rad, men komprimerer når viewport er
    smalt (< ca. 6 kolonner får plass).
    """
    if count <= 0:
        return 0, []
    col_width = _BOX_W_LOGICAL + _COL_GAP
    max_fit = max(1, int(viewport_w_logical // col_width))
    per_row = max(1, min(_MAX_ROW_COLS, max_fit, count))
    rows = (count + per_row - 1) // per_row
    cols_per_row: list[int] = []
    remaining = count
    for _ in range(rows):
        take = min(per_row, remaining)
        cols_per_row.append(take)
        remaining -= take
    return rows, cols_per_row


def _compute_default_layout(
    root_pos_key: str,
    owner_pos_keys: list[str],
    child_pos_keys: list[str],
    viewport_w: float,
) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}

    viewport_w_logical = max(640.0, float(viewport_w) or 0.0)
    owner_rows, owner_cols = _distribute_rows(len(owner_pos_keys), viewport_w_logical)
    child_rows, child_cols = _distribute_rows(len(child_pos_keys), viewport_w_logical)

    row_pitch = _BOX_H_LOGICAL + _ROW_GAP
    col_pitch = _BOX_W_LOGICAL + _COL_GAP

    # Root midt — y=0 som referansepunkt.
    center_x = viewport_w_logical / 2
    root_y = 0.0
    positions[root_pos_key] = (center_x, root_y)

    # Eiere: plasseres over root.
    idx = 0
    for r_idx, cols in enumerate(owner_cols):
        # øverste rad lengst unna root
        row_offset = (owner_rows - r_idx) * row_pitch
        y = root_y - row_offset
        row_total_w = cols * col_pitch
        x0 = center_x - row_total_w / 2 + col_pitch / 2
        for c_idx in range(cols):
            if idx >= len(owner_pos_keys):
                break
            x = x0 + c_idx * col_pitch
            positions[owner_pos_keys[idx]] = (x, y)
            idx += 1

    # Eide selskaper: plasseres under root.
    idx = 0
    for r_idx, cols in enumerate(child_cols):
        row_offset = (r_idx + 1) * row_pitch
        y = root_y + row_offset
        row_total_w = cols * col_pitch
        x0 = center_x - row_total_w / 2 + col_pitch / 2
        for c_idx in range(cols):
            if idx >= len(child_pos_keys):
                break
            x = x0 + c_idx * col_pitch
            positions[child_pos_keys[idx]] = (x, y)
            idx += 1

    return positions


# ── Indirekte eierkjede ─────────────────────────────────────────

def _resolve_indirect_lookup_year(page) -> str:
    """Velg samme register-år som overview-bygget bruker for direkte eiere.

    Faller tilbake til klient-året hvis overview ikke har eksplisitt
    ``owners_year_used``.
    """
    overview = getattr(page, "_overview", {}) or {}
    return str(
        overview.get("owners_year_used")
        or getattr(page, "_year", "")
        or ""
    ).strip()


def _build_indirect_entries(
    page,
    direct_owners: list[dict[str, Any]],
    owner_entries: list[tuple[str, str, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[str], str]:
    """BFS oppover gjennom direkte holding-aksjonærer og bygg kart-noder.

    Returnerer ``(entries, breaks, lookup_year)``:
    - ``entries``: liste av dict per indirekte boks, med ``pos_key``,
      ``parent_pos_key``, ``action_key``, ``depth``, ``row`` og en
      ``is_break`` flagg for placeholder-bokser.
    - ``breaks``: orgnrs der kjeden brytes (sub_owners var tom).
    - ``lookup_year``: AR-året som ble brukt for oppslag.

    Returnerer tomme lister hvis ar_store ikke kan importeres, hvis det
    ikke finnes lookup_year, eller hvis det ikke finnes selskaps-eiere.
    """
    entries: list[dict[str, Any]] = []
    breaks: list[str] = []
    lookup_year = _resolve_indirect_lookup_year(page)
    if not lookup_year:
        return entries, breaks, ""

    try:
        from ..backend import store as ar_store
        from ..backend.ownership_chain import walk_indirect_chain
    except Exception:
        logger.debug("Indirekte eierkjede: ar_store/ar_ownership_chain ikke tilgjengelig", exc_info=True)
        return entries, breaks, lookup_year

    lookup_year_by_orgnr: dict[str, str] = {}

    def _fetch(orgnr: str) -> list[dict[str, Any]]:
        try:
            rows = list(ar_store.list_company_owners(orgnr, lookup_year) or [])
        except Exception:
            logger.debug("list_company_owners feilet for %s/%s", orgnr, lookup_year, exc_info=True)
            rows = []
        if rows:
            lookup_year_by_orgnr[orgnr] = lookup_year
            return rows

        fallback = getattr(ar_store, "list_company_owners_with_fallback", None)
        if fallback is None:
            return []
        try:
            used_year, fallback_rows = fallback(orgnr, lookup_year)
            rows = list(fallback_rows or [])
        except Exception:
            logger.debug(
                "list_company_owners_with_fallback feilet for %s/%s",
                orgnr, lookup_year, exc_info=True,
            )
            return []
        if rows:
            lookup_year_by_orgnr[orgnr] = str(used_year or lookup_year)
        return rows

    chain_nodes, breaks = walk_indirect_chain(direct_owners, _fetch, _CHART_INDIRECT_MAX_DEPTH)
    if not chain_nodes:
        return entries, breaks, lookup_year

    # orgnr → pos_key for direkte eiere (matcher pos_key i owner_entries).
    parent_lookup: dict[str, str] = {}
    for pos_key, _ak, row in owner_entries:
        orgnr = _safe_text(row.get("shareholder_orgnr"))
        if orgnr:
            parent_lookup[orgnr] = pos_key

    # Render sub_owners for hver chain_node. Sub_owners som er selskaper
    # blir også egne BFS-noder lenger opp; dele pos_key sikrer at
    # «forelder-koblingen» fra deres eiere stemmer overens.
    next_action_idx = 0
    for node in chain_nodes:
        depth = int(node.get("depth") or 1)
        n_orgnr = str(node.get("orgnr") or "")
        sub_owners = node.get("sub_owners") or []
        node_lookup_year = lookup_year_by_orgnr.get(n_orgnr, lookup_year)

        # Forelder-pos_key for denne BFS-nodens sub_owners-bokser.
        if depth == 1:
            n_box_pos = parent_lookup.get(n_orgnr, "")
            if not n_box_pos:
                # Direkte eier ble ikke registrert som boks (mangler orgnr i owner_entries).
                continue
        else:
            n_box_pos = f"chain:{n_orgnr}"

        if not sub_owners:
            # Kjede brutt — placeholder over forelder-boksen.
            next_action_idx += 1
            entries.append({
                "pos_key": f"chain_break:{n_orgnr or depth}",
                "parent_pos_key": n_box_pos,
                "action_key": f"node:indirect_break:{next_action_idx}",
                "depth": depth + 1,
                "row": {
                    "shareholder_name": "Ikke i AR for året",
                    "shareholder_orgnr": "",
                    "shareholder_kind": "break",
                    "ownership_pct": None,
                },
                "is_break": True,
                "lookup_year": lookup_year,
                "lookup_year_used": node_lookup_year,
            })
            continue

        for sub in sub_owners:
            s_orgnr = _safe_text(sub.get("shareholder_orgnr"))
            s_name = _safe_text(sub.get("shareholder_name"))
            s_kind = str(sub.get("shareholder_kind") or "").lower()
            next_action_idx += 1

            if s_kind not in {"person", "unknown"} and s_orgnr:
                pos_key = f"chain:{s_orgnr}"
                action_kind = "indirect_owner"
            else:
                # Personer eller ukjente uten orgnr — ikke videre rekursjon.
                pos_key = f"chain_leaf:{n_orgnr}:{s_orgnr or s_name or next_action_idx}"
                action_kind = "indirect_person"

            action_key = f"node:indirect:{depth + 1}:{next_action_idx}"
            entries.append({
                "pos_key": pos_key,
                "parent_pos_key": n_box_pos,
                "action_key": action_key,
                "depth": depth + 1,
                "row": dict(sub),
                "is_break": False,
                "lookup_year": lookup_year,
                "lookup_year_used": node_lookup_year,
                "action": {
                    "kind": action_kind,
                    "shareholder_name": s_name,
                    "shareholder_orgnr": s_orgnr,
                    "lookup_year": lookup_year,
                },
            })

            page._chart_node_keys[action_key] = pos_key
            page._chart_node_actions[action_key] = entries[-1]["action"] if not entries[-1]["is_break"] else {}

    return entries, breaks, lookup_year


def _layout_indirect_entries(
    page,
    indirect_entries: list[dict[str, Any]],
) -> None:
    """Plasser indirekte bokser over sine forelder-bokser.

    Sentrer barna horisontalt over forelder-boksen, med ``_INDIRECT_BOX_W +
    _COL_GAP`` som kolonne-pitch. Hvis flere indirekte noder deler samme
    forelder, fordeles de jevnt.

    Hvis pos_key allerede har en posisjon (samme orgnr på flere veier
    gjennom kjeden), beholdes første tildelte posisjon — det unngår at
    duplikat-noder springer rundt.
    """
    row_pitch = _BOX_H_LOGICAL + _ROW_GAP
    col_pitch = _INDIRECT_BOX_W + _COL_GAP

    # Grupper per forelder per dybde for å beregne søsken-layout.
    grouped: dict[tuple[str, int], list[str]] = {}
    for entry in indirect_entries:
        key = (entry["parent_pos_key"], entry["depth"])
        grouped.setdefault(key, []).append(entry["pos_key"])

    for (parent_pos_key, depth), pos_keys in grouped.items():
        if parent_pos_key not in page._chart_node_centers:
            continue
        px, py = page._chart_node_centers[parent_pos_key]
        n = len(pos_keys)
        row_total_w = n * col_pitch
        x0 = px - row_total_w / 2 + col_pitch / 2
        # Stack hver indirekte rad ett _ROW_GAP høyere enn forrige.
        # depth=2 (første indirekte rad) ligger ett ledd over forelder.
        y = py - row_pitch
        for i, pk in enumerate(pos_keys):
            # First-write-wins: hvis pk allerede er plassert, ikke overskriv.
            if pk in page._chart_node_centers:
                continue
            page._chart_node_centers[pk] = (x0 + i * col_pitch, y)


# ── Rendering ───────────────────────────────────────────────────

def refresh_org_chart(page) -> None:
    """Public entry: rydd modell, beregn default hvis mangler, og render."""
    # Ikke tegn på nytt midt i en aktiv drag — marker bare som skitten.
    if getattr(page, "_chart_dragging", False):
        page._chart_dirty = True
        return

    saved = page._load_chart_positions()
    _build_model(page, saved)
    _render_from_model(page, suppress_auto_fit=False)

    # Sirkulært eierskap er tungt; beregn lazy i egen worker første gang
    # kartet vises for denne overview-lasten. Tabellene er ikke berørt.
    overview = getattr(page, "_overview", None)
    if isinstance(overview, dict) and "circular_ownership_cycles" not in overview:
        starter = getattr(page, "_start_circular_worker", None)
        if callable(starter):
            starter()


def _build_model(page, saved: dict[str, list[float]]) -> None:
    """Bygg intern modell (noder, kanter, logiske posisjoner) fra overview."""
    page._chart_node_actions = {}
    page._chart_node_keys = {}
    page._chart_node_centers = {}
    page._chart_edges = []
    page._chart_box_size = (_BOX_W_LOGICAL, _BOX_H_LOGICAL)

    root_name = page._client or "Klient"
    root_orgnr = _safe_text(page._overview.get("client_orgnr"))
    owners_raw = page._overview.get("owners") or []
    children_raw = page._overview.get("owned_companies") or []
    owners = _sort_owners(list(owners_raw))
    children = _sort_children(list(children_raw))

    page._chart_model_meta = {
        "root_name": root_name,
        "root_orgnr": root_orgnr,
        "owners": owners,
        "children": children,
        "empty": not root_name or (not root_orgnr and not owners and not children),
    }
    if page._chart_model_meta["empty"]:
        return

    # Pos-keys
    root_pos_key = f"root:{root_orgnr or root_name}"
    root_action_key = "node:root"
    page._chart_node_keys[root_action_key] = root_pos_key
    page._chart_node_actions[root_action_key] = {"kind": "root"}

    owner_entries: list[tuple[str, str, dict[str, Any]]] = []
    for idx, row in enumerate(owners, start=1):
        orgnr = _safe_text(row.get("shareholder_orgnr"))
        name = _safe_text(row.get("shareholder_name"))
        pos_key = f"owner:{orgnr or name}"
        action_key = f"node:owner:{idx}"
        owner_entries.append((pos_key, action_key, row))
        page._chart_node_keys[action_key] = pos_key
        page._chart_node_actions[action_key] = {
            "kind": "owner",
            "shareholder_name": name,
            "shareholder_orgnr": orgnr,
        }

    child_entries: list[tuple[str, str, dict[str, Any]]] = []
    for idx, row in enumerate(children, start=1):
        orgnr = _safe_text(row.get("company_orgnr"))
        name = _safe_text(row.get("company_name"))
        pos_key = f"child:{orgnr or name}"
        action_key = f"node:owned:{idx}"
        child_entries.append((pos_key, action_key, row))
        page._chart_node_keys[action_key] = pos_key
        page._chart_node_actions[action_key] = {
            "kind": "owned",
            "company_name": name,
            "company_orgnr": orgnr,
        }

    # Indirekte eierkjede over direkte holding-aksjonærer.
    indirect_entries, indirect_breaks, indirect_lookup_year = _build_indirect_entries(
        page, owners, owner_entries,
    )

    try:
        viewport_w = page._org_canvas.winfo_width()
    except Exception:
        viewport_w = 0
    defaults = _compute_default_layout(
        root_pos_key,
        [pk for (pk, _ak, _row) in owner_entries],
        [pk for (pk, _ak, _row) in child_entries],
        viewport_w,
    )
    # Merge: saved vinner over default.
    for pos_key, (x, y) in defaults.items():
        page._chart_node_centers[pos_key] = (x, y)

    # Indirekte noder plasseres relativt til sine forelder-bokser.
    _layout_indirect_entries(page, indirect_entries)

    for pos_key, coords in saved.items():
        if pos_key in page._chart_node_centers or pos_key == root_pos_key or pos_key.startswith(("owner:", "child:", "chain:", "chain_leaf:", "chain_break:")):
            try:
                page._chart_node_centers[pos_key] = (float(coords[0]), float(coords[1]))
            except (TypeError, ValueError, IndexError):
                continue

    # Kant-metadata (keys only); tegnes i render.
    for pos_key, _ak, _row in owner_entries:
        line_tag = f"edge:line:{pos_key}"
        lbl_tag = f"edge:lbl:{pos_key}"
        page._chart_edges.append((pos_key, root_pos_key, line_tag, lbl_tag))
    for pos_key, _ak, _row in child_entries:
        line_tag = f"edge:line:{pos_key}"
        lbl_tag = f"edge:lbl:{pos_key}"
        page._chart_edges.append((root_pos_key, pos_key, line_tag, lbl_tag))
    for entry in indirect_entries:
        pos_key = entry["pos_key"]
        parent_pos_key = entry["parent_pos_key"]
        # Edge-tag inkluderer parent for å være unik selv ved «diamant-eierskap»
        # (samme orgnr som sub_owner av to forskjellige holdinger).
        line_tag = f"edge:line:{pos_key}:{parent_pos_key}"
        lbl_tag = f"edge:lbl:{pos_key}:{parent_pos_key}"
        page._chart_edges.append((pos_key, parent_pos_key, line_tag, lbl_tag))

    page._chart_model_meta["root_pos_key"] = root_pos_key
    page._chart_model_meta["root_action_key"] = root_action_key
    page._chart_model_meta["owner_entries"] = owner_entries
    page._chart_model_meta["child_entries"] = child_entries
    page._chart_model_meta["indirect_entries"] = indirect_entries
    page._chart_model_meta["indirect_breaks"] = indirect_breaks
    page._chart_model_meta["indirect_lookup_year"] = indirect_lookup_year
    page._chart_model_meta["saved"] = dict(saved)


def _render_from_model(page, *, suppress_auto_fit: bool) -> None:
    canvas = page._org_canvas
    canvas.delete("all")
    canvas.configure(background="#FAFAF8")  # design-exception: tailwind soft-bakgrunn
    page._update_chart_zoom_label()

    meta = getattr(page, "_chart_model_meta", None) or {}
    # "empty" betyr at overview ikke har gyldige eierdata — da viser vi
    # hjelpetekst, uavhengig av om _chart_node_centers fortsatt har noe
    # (gammel state fra forrige render).
    if meta.get("empty", True) or "root_pos_key" not in meta:
        canvas.create_text(320, 120, text="Ingen eierdata tilgjengelig ennå.", font=("Segoe UI", 10), fill="#667085")  # design-exception: chart-fill-palette
        canvas.configure(scrollregion=(0, 0, 640, 240))
        page._chart_dirty = False
        # Ny render-id slik at utestående auto-fit ignoreres.
        page._chart_render_id = getattr(page, "_chart_render_id", 0) + 1
        return

    z = page._chart_zoom or 1.0
    box_w = _BOX_W_LOGICAL * z
    box_h = _BOX_H_LOGICAL * z
    page._chart_box_size = (_BOX_W_LOGICAL, _BOX_H_LOGICAL)

    root_pos_key = meta["root_pos_key"]
    root_action_key = meta["root_action_key"]
    root_name = meta["root_name"]
    root_orgnr = meta["root_orgnr"]
    rlx, rly = page._chart_node_centers[root_pos_key]
    rx, ry = rlx * z, rly * z

    draw_box(
        page, canvas, rx, ry, box_w + 16 * z, box_h + 4 * z,
        title=root_name,
        subtitle=root_orgnr or page._year,
        fill="#E6F0FF", accent="#2952A3",  # design-exception: chart-fill-palette
        action_key=root_action_key,
    )

    self_ownership = page._overview.get("self_ownership") or {}
    if self_ownership:
        note = f"Egne aksjer: {_fmt_pct(self_ownership.get('ownership_pct'))}%"
        shares = int(self_ownership.get("shares") or 0)
        total = int(self_ownership.get("total_shares") or 0)
        if shares and total:
            note = f"{note} ({shares} av {total})"
        canvas.create_text(
            rx, ry + 46 * z, text=note,
            font=("Segoe UI", 8, "italic"), fill="#8A5A00",  # design-exception: chart-fill-palette
            tags=("chart-node", root_action_key),
        )

    # Eiere + kanter.
    for pos_key, action_key, row in meta.get("owner_entries", []):
        olx, oly = page._chart_node_centers[pos_key]
        ox, oy = olx * z, oly * z
        draw_box(
            page, canvas, ox, oy, box_w, box_h,
            title=_safe_text(row.get("shareholder_name")) or "Ukjent eier",
            subtitle=_safe_text(row.get("shareholder_orgnr"))
                     or _safe_text(row.get("shareholder_kind")) or "-",
            fill="#F8FAFC", accent="#667085",  # design-exception: chart-fill-palette
            action_key=action_key,
        )
        line_tag = f"edge:line:{pos_key}"
        lbl_tag = f"edge:lbl:{pos_key}"
        y1 = oy + box_h / 2
        y2 = ry - (box_h + 4 * z) / 2
        canvas.create_line(ox, y1, rx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))  # design-exception: chart-fill-palette
        canvas.create_text(
            (ox + rx) / 2, (y1 + y2) / 2,
            text=f"{_fmt_pct(row.get('ownership_pct'))}%",
            font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),  # design-exception: chart-fill-palette
        )

    # Eide selskaper + kanter.
    for pos_key, action_key, row in meta.get("child_entries", []):
        clx, cly = page._chart_node_centers[pos_key]
        cx, cy = clx * z, cly * z
        draw_box(
            page, canvas, cx, cy, box_w, box_h,
            title=_safe_text(row.get("company_name")) or "Ukjent selskap",
            subtitle=f"{_safe_text(row.get('company_orgnr')) or '-'} | {_relation_label(row.get('relation_type'))}",
            fill=_relation_fill(row.get("relation_type")),
            accent=_relation_accent(row.get("relation_type")),
            action_key=action_key,
        )
        line_tag = f"edge:line:{pos_key}"
        lbl_tag = f"edge:lbl:{pos_key}"
        y1 = ry + (box_h + 4 * z) / 2
        y2 = cy - box_h / 2
        canvas.create_line(rx, y1, cx, y2, fill="#B0B8C8", width=1, tags=(line_tag,))  # design-exception: chart-fill-palette
        canvas.create_text(
            (rx + cx) / 2, (y1 + y2) / 2,
            text=f"{_fmt_pct(row.get('ownership_pct'))}%",
            font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),  # design-exception: chart-fill-palette
        )

    # Indirekte eierkjede + kanter (over direkte eiere).
    # Tegn hver pos_key-boks kun én gang (en holding kan ha flere foreldre);
    # tegn alltid kanten fra (pos_key → parent_pos_key) per entry.
    indirect_box_w = _INDIRECT_BOX_W * z
    drawn_pos_keys: set[str] = set()
    for entry in meta.get("indirect_entries", []):
        pos_key = entry["pos_key"]
        if pos_key not in page._chart_node_centers:
            continue
        elx, ely = page._chart_node_centers[pos_key]
        ex, ey = elx * z, ely * z

        row = entry.get("row") or {}
        is_break = bool(entry.get("is_break"))
        action_key = entry["action_key"]

        if pos_key not in drawn_pos_keys:
            drawn_pos_keys.add(pos_key)
            if is_break:
                year_label = entry.get("lookup_year") or page._year or ""
                draw_box(
                    page, canvas, ex, ey, indirect_box_w, box_h,
                    title="Ikke i AR for året",
                    subtitle=f"Kjeden brytes ({year_label})",
                    fill="#FFF7E6", accent="#D08700",  # design-exception: chart-fill-palette
                    action_key=action_key,
                    dashed=True,
                )
            else:
                kind = (entry.get("action") or {}).get("kind", "indirect_owner")
                is_person = kind == "indirect_person"
                draw_box(
                    page, canvas, ex, ey, indirect_box_w, box_h,
                    title=_safe_text(row.get("shareholder_name")) or "Ukjent eier",
                    subtitle=_safe_text(row.get("shareholder_orgnr"))
                             or _safe_text(row.get("shareholder_kind")) or "-",
                    fill="#FAF5FF" if not is_person else "#F4F0FF",  # design-exception: chart-fill-palette
                    accent="#7E5BEF" if not is_person else "#9F7AEA",  # design-exception: chart-palette
                    action_key=action_key,
                    dashed=True,
                )

        parent_pos_key = entry["parent_pos_key"]
        if parent_pos_key in page._chart_node_centers:
            plx, ply = page._chart_node_centers[parent_pos_key]
            px, py = plx * z, ply * z
            line_tag = f"edge:line:{pos_key}:{parent_pos_key}"
            lbl_tag = f"edge:lbl:{pos_key}:{parent_pos_key}"
            y1 = ey + box_h / 2
            y2 = py - box_h / 2
            canvas.create_line(
                ex, y1, px, y2,
                fill="#B0B8C8", width=1, dash=(3, 2),  # design-exception: chart-fill-palette
                tags=(line_tag,),
            )
            pct = row.get("ownership_pct")
            if not is_break and pct is not None:
                canvas.create_text(
                    (ex + px) / 2, (y1 + y2) / 2,
                    text=f"{_fmt_pct(pct)}%",
                    font=("Segoe UI", 8), fill="#475467", tags=(lbl_tag,),  # design-exception: chart-fill-palette
                )

    # Sirkulært eierskap — les fra overview (beregnet i worker).
    cycles = page._overview.get("circular_ownership_cycles") or []
    if cycles:
        cycle_text = "Sirkulært eierskap: " + "; ".join(
            " \u2192 ".join(c) + " \u2192 " + c[0] for c in cycles[:3]
        )
        all_ys = [ly for (_lx, ly) in page._chart_node_centers.values()]
        warn_y_logical = (max(all_ys) + _BOX_H_LOGICAL / 2 + 30) if all_ys else 400
        canvas.create_text(
            rx, warn_y_logical * z, text=f"\u26a0 {cycle_text}",
            font=("Segoe UI", 9), fill="#856404",  # design-exception: chart-fill-palette
        )

    page._update_chart_scrollregion()
    try:
        canvas.update_idletasks()
    except Exception:
        pass
    page._chart_dirty = False

    # Bumper render-id etter hver fullstendig render — utdaterte auto-fit-kall
    # vil se en annen id og avbryte.
    page._chart_render_id = getattr(page, "_chart_render_id", 0) + 1
    saved = meta.get("saved") or {}
    if not saved and not suppress_auto_fit:
        render_id = page._chart_render_id
        page.after(50, lambda: _scheduled_fit_view(page, render_id))


def _scheduled_fit_view(page, render_id: int) -> None:
    if getattr(page, "_chart_render_id", 0) != render_id:
        return
    if getattr(page, "_chart_dragging", False):
        return
    chart_fit_view(page)
