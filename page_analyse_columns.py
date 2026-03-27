"""page_analyse_columns.py

Kolonnehåndtering for Analyse-fanen: pivot-synlighet, TX-kolonnevalg,
auto-fit og breddepersistens.

Alle funksjoner tar ``page`` (AnalysePage-instans) som duck-typed objekt
og leser/skriver attributter direkte – samme mønster som de øvrige
page_analyse_*-modulene.
"""

from __future__ import annotations

from typing import Any, List, Optional

import analyse_columns
import analyse_treewidths
import preferences


# =====================================================================
# Pivot-kolonnesynlighet
# =====================================================================

# Kolonner som alltid skal strekke seg for å fylle ledig plass
PIVOT_STRETCH_COLS = ("Kontonavn",)
PIVOT_FILL_PRIORITY = ("Kontonavn", "Konto", "Sum")
PIVOT_FILL_WEIGHTS = {"Kontonavn": 7, "Konto": 2, "Sum": 1}
TX_HEADER_DRAG_THRESHOLD_PX = 10


def pivot_default_for_mode(*, page: Any) -> tuple[str, ...]:
    """Returner standard synlige pivot-kolonner for gjeldende aggregeringsmodus."""
    agg = ""
    try:
        agg = str(page._var_aggregering.get())
    except Exception:
        pass
    if agg == "Konto":
        return getattr(page, "PIVOT_COLS_DEFAULT_KONTO", page.PIVOT_COLS_DEFAULT_VISIBLE)
    if agg == "Regnskapslinje":
        return getattr(page, "PIVOT_COLS_DEFAULT_RL", page.PIVOT_COLS_DEFAULT_VISIBLE)
    return page.PIVOT_COLS_DEFAULT_VISIBLE


def load_pivot_visible_columns(*, page: Any) -> None:
    """Last lagret pivot-kolonnesynlighet fra preferences."""
    try:
        stored = preferences.get("analyse.pivot_cols.visible", None)
    except Exception:
        stored = None

    if isinstance(stored, list) and stored:
        valid = [c for c in stored if c in page.PIVOT_COLS]
        for p in page.PIVOT_COLS_PINNED:
            if p not in valid:
                valid.insert(0, p)
        page._pivot_visible_cols = valid
    else:
        page._pivot_visible_cols = list(page.PIVOT_COLS_DEFAULT_VISIBLE)


def persist_pivot_visible_columns(*, page: Any) -> None:
    try:
        preferences.set("analyse.pivot_cols.visible", list(page._pivot_visible_cols))
    except Exception:
        pass


def apply_pivot_visible_columns(*, page: Any) -> None:
    """Oppdater pivot-tree displaycolumns basert på _pivot_visible_cols."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    all_cols = list(tree["columns"])
    visible = [c for c in page._pivot_visible_cols if c in all_cols]
    if not visible:
        visible = list(page.PIVOT_COLS_DEFAULT_VISIBLE)
    try:
        tree["displaycolumns"] = visible
    except Exception:
        pass


def toggle_pivot_column(*, page: Any, col: str) -> None:
    """Slå av/på en kolonne i pivot-visningen."""
    if col in page.PIVOT_COLS_PINNED:
        return
    if col in page._pivot_visible_cols:
        page._pivot_visible_cols.remove(col)
    else:
        pos = 0
        for pc in page.PIVOT_COLS:
            if pc == col:
                break
            if pc in page._pivot_visible_cols:
                pos += 1
        page._pivot_visible_cols.insert(pos, col)
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def show_pivot_column_menu(*, page: Any, event: Any) -> None:
    """Vis høyreklikkmeny for å vise/skjule pivot-kolonner."""
    if not getattr(page, "_tk_ok", False) or event is None:
        return
    try:
        import tkinter as tk
    except Exception:
        return

    tree = getattr(page, "_pivot_tree", None)
    menu = tk.Menu(page, tearoff=0)
    for col in page.PIVOT_COLS:
        if col in page.PIVOT_COLS_PINNED:
            continue
        display_name = col
        if tree is not None:
            try:
                heading_text = tree.heading(col, "text")
                if heading_text and heading_text.strip():
                    display_name = heading_text.strip()
                else:
                    continue  # Ikke relevant i nåværende modus
            except Exception:
                pass
        is_visible = col in page._pivot_visible_cols
        label = f"{'✓  ' if is_visible else '    '}{display_name}"
        menu.add_command(
            label=label,
            command=lambda c=col: toggle_pivot_column(page=page, col=c),
        )
    menu.add_separator()
    menu.add_command(label="Standard", command=lambda: reset_pivot_columns(page=page))

    # Kommentar-alternativ for RL- og Konto-modus
    agg_mode = ""
    try:
        agg_mode = str(page._var_aggregering.get()) if page._var_aggregering else ""
    except Exception:
        pass

    if tree is not None:
        try:
            item = tree.identify_row(event.y)
            if item:
                vals = tree.item(item, "values")
                if vals:
                    first_col = str(vals[0]).strip()
                    second_col = str(vals[1]).strip() if len(vals) > 1 else ""
                    if first_col and not first_col.startswith("\u03a3"):
                        menu.add_separator()
                        if agg_mode == "Regnskapslinje":
                            menu.add_command(
                                label=f"Kommentar for {first_col} {second_col}\u2026",
                                command=lambda: _open_rl_comment(page=page, regnr=first_col, rl_name=second_col),
                            )
                        elif agg_mode in ("Konto", ""):
                            menu.add_command(
                                label=f"Kommentar for {first_col} {second_col}\u2026",
                                command=lambda: _open_account_comment(page=page, konto=first_col, kontonavn=second_col),
                            )
        except Exception:
            pass

    try:
        menu.tk_popup(event.x_root, event.y_root)
    except Exception:
        pass


def _open_rl_comment(*, page: Any, regnr: str, rl_name: str) -> None:
    """Åpne kommentar-dialog for en regnskapslinje."""
    try:
        import page_analyse_sb
        page_analyse_sb._edit_comment(
            page=page, kind="rl", key=regnr, label=f"{regnr} {rl_name}",
        )
    except Exception:
        pass


def _open_account_comment(*, page: Any, konto: str, kontonavn: str) -> None:
    """Åpne kommentar-dialog for en konto i konto-pivot."""
    try:
        import page_analyse_sb
        page_analyse_sb._edit_comment(
            page=page, kind="accounts", key=konto, label=f"{konto} {kontonavn}",
        )
    except Exception:
        pass


def reset_pivot_columns(*, page: Any) -> None:
    page._pivot_visible_cols = list(pivot_default_for_mode(page=page))
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


def adapt_pivot_columns_for_mode(*, page: Any) -> None:
    """Tilpass synlige kolonner når aggregeringsmodus endres."""
    defaults = pivot_default_for_mode(page=page)
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    relevant: set[str] = set(page.PIVOT_COLS_PINNED)
    for col_id in page.PIVOT_COLS:
        try:
            heading_text = tree.heading(col_id, "text")
        except Exception:
            heading_text = ""
        if heading_text and heading_text.strip():
            relevant.add(col_id)
    new_visible = list(defaults)
    for col in page._pivot_visible_cols:
        if col not in new_visible and col in relevant:
            new_visible.append(col)
    new_visible = [c for c in new_visible if c in relevant]
    if not new_visible:
        new_visible = list(defaults)
    page._pivot_visible_cols = new_visible
    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)


# =====================================================================
# TX-kolonnepreferanser
# =====================================================================

def load_tx_columns_from_preferences(*, page: Any) -> None:
    """Last inn kolonneoppsett for transaksjonslisten fra preferences."""
    try:
        stored_order = preferences.get("analyse.tx_cols.order", None)
        stored_visible = preferences.get("analyse.tx_cols.visible", None)
    except Exception:
        stored_order = None
        stored_visible = None

    order = stored_order if isinstance(stored_order, list) else list(page.TX_COLS_DEFAULT)
    visible = stored_visible if isinstance(stored_visible, list) else list(page.TX_COLS_DEFAULT)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=None,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)


def persist_tx_columns_to_preferences(*, page: Any) -> None:
    try:
        preferences.set("analyse.tx_cols.order", list(page._tx_cols_order))
        preferences.set("analyse.tx_cols.visible", list(page.TX_COLS))
    except Exception:
        pass


def get_all_tx_columns_for_chooser(*, page: Any) -> List[str]:
    import pandas as pd
    cols: List[str] = []
    cols.extend(getattr(page, "_tx_cols_order", []))
    cols.extend(list(page.TX_COLS_DEFAULT))

    df = page._df_filtered if isinstance(page._df_filtered, pd.DataFrame) else page.dataset
    if isinstance(df, pd.DataFrame):
        for c in df.columns:
            try:
                name = str(c)
            except Exception:
                continue
            if not name or name.startswith("_"):
                continue
            cols.append(name)

    return analyse_columns.unique_preserve(cols, canonicalize=True)


def apply_tx_column_config(*, page: Any, order: List[str], visible: List[str],
                           all_cols: Optional[List[str]] = None) -> None:
    all_cols = all_cols or get_all_tx_columns_for_chooser(page=page)

    order_clean, visible_order = analyse_columns.normalize_tx_column_config(
        order=order,
        visible=visible,
        all_cols=all_cols,
        pinned=page.PINNED_TX_COLS,
        required=page.REQUIRED_TX_COLS,
    )

    page._tx_cols_order = list(order_clean)
    page._tx_cols_visible = list(visible_order)
    page.TX_COLS = tuple(visible_order)

    persist_tx_columns_to_preferences(page=page)

    configure_tx_tree_columns(page=page)
    page._refresh_transactions_view()


def open_tx_column_chooser(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    try:
        from views_column_chooser import open_column_chooser
    except Exception:
        return

    all_cols = get_all_tx_columns_for_chooser(page=page)
    current_visible = list(getattr(page, "TX_COLS", page.TX_COLS_DEFAULT))
    initial_order = list(getattr(page, "_tx_cols_order", all_cols))

    res = open_column_chooser(
        page,
        all_cols=all_cols,
        visible_cols=current_visible,
        initial_order=initial_order,
        default_visible_cols=list(page.TX_COLS_DEFAULT),
        default_order=list(page.TX_COLS_DEFAULT),
    )
    if not res:
        return

    order, visible = res
    if not isinstance(order, list) or not isinstance(visible, list):
        return

    apply_tx_column_config(page=page, order=order, visible=visible, all_cols=all_cols)


def reset_tx_columns_to_default(*, page: Any) -> None:
    apply_tx_column_config(
        page=page,
        order=list(page.TX_COLS_DEFAULT),
        visible=list(page.TX_COLS_DEFAULT),
    )


# =====================================================================
# Bredde-persistens & auto-fit
# =====================================================================

def load_saved_column_widths(pref_key: str) -> dict[str, int]:
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
        if 40 <= width <= 1200:
            widths[name] = width
    return widths


def persist_saved_column_widths(pref_key: str, widths: dict[str, int]) -> None:
    clean: dict[str, int] = {}
    for key, value in widths.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            width = int(value)
        except Exception:
            continue
        if 40 <= width <= 1200:
            clean[name] = width
    try:
        preferences.set(pref_key, clean)
    except Exception:
        pass


def tree_display_columns(tree: Any) -> List[str]:
    try:
        display = tree["displaycolumns"]
    except Exception:
        display = ()
    if display in ("#all", ("#all",)):
        try:
            return list(tree["columns"])
        except Exception:
            return []
    return [str(c) for c in (display or ()) if str(c).strip()]


def safe_tree_column_width(tree: Any, col: str) -> Optional[int]:
    try:
        return int(tree.column(col, option="width"))
    except Exception:
        try:
            cfg = tree.column(col)
        except Exception:
            return None
        if isinstance(cfg, dict):
            try:
                return int(cfg.get("width"))
            except Exception:
                return None
    return None


def snapshot_tree_widths(tree: Any, columns: List[str]) -> dict[str, int]:
    widths: dict[str, int] = {}
    for col in columns:
        width = safe_tree_column_width(tree, col)
        if width is not None and 40 <= width <= 1200:
            widths[col] = width
    return widths


def tree_rows_for_width_estimate(tree: Any, columns: List[str], *, limit: int = 200) -> List[List[Any]]:
    try:
        children = list(tree.get_children(""))[:limit]
    except Exception:
        return []

    rows: List[List[Any]] = []
    for item in children:
        try:
            values = list(tree.item(item).get("values") or [])
        except Exception:
            continue
        if not values:
            continue
        if len(values) < len(columns):
            values = values + [""] * (len(columns) - len(values))
        rows.append(values[: len(columns)])
    return rows


def column_id_from_event(tree: Any, event: Any) -> Optional[str]:
    try:
        token = str(tree.identify_column(event.x))
    except Exception:
        return None
    if not token.startswith("#"):
        return None
    try:
        index = int(token[1:]) - 1
    except Exception:
        return None

    columns = tree_display_columns(tree)
    if 0 <= index < len(columns):
        return columns[index]
    return None


def auto_fit_tree_columns(
    *,
    tree: Any,
    columns: List[str],
    stored_widths: dict[str, int],
    pref_key: str,
    only_missing: bool = False,
    target_col: Optional[str] = None,
    persist: bool = False,
    stretch_cols: set[str] | None = None,
) -> None:
    """Auto-fit kolonnbredder basert på innhold.

    ``stretch_cols`` angir kolonner som beholder ``stretch=True``
    (f.eks. ``{"Kontonavn"}``). Alle andre settes til ``stretch=False``.
    """
    rows = tree_rows_for_width_estimate(tree, columns)
    if not rows and target_col is None:
        return

    updated = dict(stored_widths)
    stretch_cols = stretch_cols or set()

    for idx, col in enumerate(columns):
        if target_col and col != target_col:
            continue
        if only_missing and col in stored_widths:
            continue

        values = [row[idx] for row in rows if idx < len(row)]
        width = analyse_treewidths.suggest_column_width(col, values)
        try:
            tree.column(
                col,
                width=width,
                minwidth=max(40, min(width, 80)),
                anchor=analyse_treewidths.column_anchor(col),
                stretch=col in stretch_cols,
            )
        except Exception:
            continue

        if persist:
            updated[col] = width

    if persist:
        stored_widths.clear()
        stored_widths.update(updated)
        persist_saved_column_widths(pref_key, stored_widths)


def rebalance_tree_columns_to_available_width(
    *,
    tree: Any,
    columns: List[str],
    preferred_cols: List[str],
    weights: dict[str, int] | None = None,
) -> None:
    """Fordel ledig Treeview-bredde til prioriterte kolonner.

    Eksisterende kolonnebredder brukes som base. Dersom treeviewen er bredere
    enn summen av kolonnene, fordeles overskytende plass til prioriterte
    kolonner slik at vi unngar store ubrukt hvite flater.
    """
    try:
        available = int(tree.winfo_width())
    except Exception:
        return
    if available <= 80:
        return

    widths = {
        col: safe_tree_column_width(tree, col) or analyse_treewidths.default_column_width(col)
        for col in columns
    }
    total = sum(widths.values())
    extra = available - total - 6
    if extra <= 8:
        return

    targets = [col for col in preferred_cols if col in columns]
    if not targets:
        targets = [col for col in columns if analyse_treewidths.column_anchor(col) == "w"]
    if not targets and columns:
        targets = [columns[-1]]
    if not targets:
        return

    weight_map = weights or {}
    total_weight = sum(max(1, int(weight_map.get(col, 1))) for col in targets)
    if total_weight <= 0:
        return

    remaining = extra
    for idx, col in enumerate(targets):
        if idx == len(targets) - 1:
            share = remaining
        else:
            share = max(0, int(extra * max(1, int(weight_map.get(col, 1))) / total_weight))
            remaining -= share
        try:
            tree.column(
                col,
                width=widths[col] + share,
                anchor=analyse_treewidths.column_anchor(col),
            )
        except Exception:
            continue


def sample_tx_values_for_width(*, page: Any, display_col: str, limit: int = 200) -> List[Any]:
    import pandas as pd
    df = page._df_filtered if isinstance(page._df_filtered, pd.DataFrame) else page.dataset
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []

    for source_col in analyse_columns.candidate_source_columns(display_col):
        if source_col in df.columns:
            try:
                return df[source_col].head(limit).tolist()
            except Exception:
                return []
    return []


# =====================================================================
# Hjelpere for TX/Pivot auto-fit + resize events
# =====================================================================

def remember_tx_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    page._tx_col_widths.update(widths)
    persist_saved_column_widths("analyse.tx_cols.widths", page._tx_col_widths)


def remember_pivot_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    page._pivot_col_widths.update(widths)
    persist_saved_column_widths("analyse.pivot.widths", page._pivot_col_widths)


def maybe_auto_fit_tx_tree(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    force = getattr(page, "_tx_first_load", False)
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        only_missing=not force,
        persist=force,
    )
    if force:
        page._tx_first_load = False


def maybe_auto_fit_pivot_tree(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    force = getattr(page, "_pivot_first_load", False)
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        only_missing=not force,
        persist=force,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    rebalance_pivot_tree_columns(page=page)
    if force:
        page._pivot_first_load = False


def auto_fit_tx_columns(*, page: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        persist=True,
    )


def auto_fit_pivot_columns(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        persist=True,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    rebalance_pivot_tree_columns(page=page)


def auto_fit_analyse_columns(*, page: Any) -> None:
    auto_fit_pivot_columns(page=page)
    auto_fit_tx_columns(page=page)


def rebalance_pivot_tree_columns(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    rebalance_tree_columns_to_available_width(
        tree=tree,
        columns=tree_display_columns(tree),
        preferred_cols=list(PIVOT_FILL_PRIORITY),
        weights=dict(PIVOT_FILL_WEIGHTS),
    )


def schedule_balance_pivot_tree(*, page: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return
    try:
        after_id = getattr(page, "_pivot_balance_after_id", None)
        if after_id:
            page.after_cancel(after_id)
    except Exception:
        pass

    def _run() -> None:
        try:
            page._pivot_balance_after_id = None
        except Exception:
            pass
        rebalance_pivot_tree_columns(page=page)

    try:
        page._pivot_balance_after_id = page.after_idle(_run)
    except Exception:
        rebalance_pivot_tree_columns(page=page)


# =====================================================================
# Dobbelt-klikk og mouse-release events
# =====================================================================

def on_tx_tree_double_click(*, page: Any, event: Any) -> Optional[str]:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return None
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        return None
    if region != "separator":
        return None

    col = column_id_from_event(tree, event)
    if not col:
        return "break"

    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._tx_col_widths,
        pref_key="analyse.tx_cols.widths",
        target_col=col,
        persist=True,
    )
    return "break"


def on_tx_tree_mouse_press(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        setattr(page, "_tx_header_drag", None)
        return

    col = column_id_from_event(tree, event)
    if not col:
        setattr(page, "_tx_header_drag", None)
        return

    setattr(
        page,
        "_tx_header_drag",
        {
            "source": col,
            "start_x": int(getattr(event, "x", 0) or 0),
            "active": False,
        },
    )


def on_tx_tree_mouse_drag(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    drag = getattr(page, "_tx_header_drag", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return

    if drag.get("active"):
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        return

    start_x = int(drag.get("start_x", 0) or 0)
    cur_x = int(getattr(event, "x", 0) or 0)
    if abs(cur_x - start_x) < TX_HEADER_DRAG_THRESHOLD_PX:
        return

    drag["active"] = True
    setattr(page, "_tx_header_drag", drag)
    try:
        tree._suppress_next_heading_sort = True  # type: ignore[attr-defined]
    except Exception:
        pass


def _finish_tx_header_drag(*, page: Any, event: Any) -> bool:
    tree = getattr(page, "_tx_tree", None)
    drag = getattr(page, "_tx_header_drag", None)
    setattr(page, "_tx_header_drag", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return False

    if not drag.get("active"):
        return False

    source = str(drag.get("source") or "").strip()
    target = column_id_from_event(tree, event) or ""
    if not source or not target or source == target:
        return False

    order = analyse_columns.reorder_tx_column(
        getattr(page, "_tx_cols_order", ()),
        source=source,
        target=target,
        all_cols=get_all_tx_columns_for_chooser(page=page),
        pinned=getattr(page, "PINNED_TX_COLS", ("Konto", "Kontonavn")),
        required=getattr(page, "REQUIRED_TX_COLS", ("Konto", "Kontonavn", "Bilag")),
    )
    current_visible = list(getattr(page, "TX_COLS", ()))
    apply_tx_column_config(page=page, order=order, visible=current_visible)
    try:
        after_idle = getattr(tree, "after_idle", None)
        if callable(after_idle):
            after_idle(lambda: setattr(tree, "_suppress_next_heading_sort", False))
    except Exception:
        pass
    return True


def on_pivot_tree_double_click(*, page: Any, event: Any) -> Optional[str]:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        return None
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        return None
    if region != "separator":
        return None

    col = column_id_from_event(tree, event)
    if not col:
        return "break"

    auto_fit_tree_columns(
        tree=tree,
        columns=tree_display_columns(tree),
        stored_widths=page._pivot_col_widths,
        pref_key="analyse.pivot.widths",
        target_col=col,
        persist=True,
        stretch_cols=set(PIVOT_STRETCH_COLS),
    )
    return "break"


def on_tx_tree_mouse_release(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_tx_tree", None)
    if tree is None or event is None:
        return

    if _finish_tx_header_drag(page=page, event=event):
        return

    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region in {"separator", "heading"}:
        remember_tx_column_widths(page=page)


def on_pivot_tree_mouse_release(*, page: Any, event: Any) -> None:
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        return
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region in {"separator", "heading"}:
        remember_pivot_column_widths(page=page)


# =====================================================================
# TX-tree kolonnekonfigurasjon og sortering
# =====================================================================

def configure_tx_tree_columns(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return

    cols = tuple(getattr(page, "TX_COLS", page.TX_COLS_DEFAULT))

    try:
        tree.configure(columns=cols)
        tree["displaycolumns"] = cols
    except Exception:
        return

    for c in cols:
        try:
            tree.heading(c, text=c)
        except Exception:
            pass

        width = int(
            page._tx_col_widths.get(
                c,
                analyse_treewidths.suggest_column_width(
                    c, sample_tx_values_for_width(page=page, display_col=c)
                ),
            )
        )
        anchor = analyse_treewidths.column_anchor(c)
        try:
            tree.column(
                c,
                width=width,
                minwidth=max(40, min(width, 80)),
                anchor=anchor,
                stretch=False,
            )
        except Exception:
            pass

    enable_tx_sorting(page=page)


def enable_tx_sorting(*, page: Any, enable_fn: Any = None) -> None:
    """Aktiver klikk-for-sortering på transaksjonslisten.

    ``enable_fn`` kan sendes inn for testbarhet (monkeypatching).
    Hvis None, importeres fra ui_treeview_sort.
    """
    if not getattr(page, "_tk_ok", False):
        return
    if getattr(page, "_tx_tree", None) is None:
        return
    if enable_fn is None:
        try:
            from ui_treeview_sort import enable_treeview_sorting
            enable_fn = enable_treeview_sorting
        except Exception:
            return
    try:
        enable_fn(page._tx_tree, columns=page.TX_COLS)
    except Exception:
        pass
