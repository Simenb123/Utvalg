"""page_analyse_columns_widths.py

Kolonne-bredder, auto-fit, drag-to-reorder og sortering for Analyse-fanen.

Utskilt fra page_analyse_columns.py for å redusere filstørrelse. Eksportert
via page_analyse_columns som fasade for bakoverkompatibilitet.
"""

from __future__ import annotations

from typing import Any, List, Optional

import analyse_columns
import analyse_treewidths
import preferences


# =====================================================================
# Konstanter — bredde/drag
# =====================================================================

# Tom — ingen kolonne skal stretches automatisk. Tidligere stretchet
# Kontonavn, men det overstyrer brukerens manuelle resize ved hver
# auto-fit-runde (samme bug-mønster som TX/SB/Oversikt — se
# doc/TREEVIEW_PLAYBOOK.md).
PIVOT_STRETCH_COLS: tuple[str, ...] = ()
PIVOT_FILL_PRIORITY = ("Kontonavn", "Konto")
PIVOT_FILL_WEIGHTS = {"Kontonavn": 9, "Konto": 1}
TX_HEADER_DRAG_THRESHOLD_PX = 10
_PIVOT_DRAG_THRESHOLD_PX = 10


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


def tree_rows_for_width_estimate(tree: Any, columns: List[str], *, limit: int = 200) -> List[dict]:
    """Hent radverdier for breddeestimering, korrekt indeksert per kolonnenavn.

    tree.item(item).get("values") returnerer verdier for ALLE kolonner i tree["columns"]
    rekkefølge, uavhengig av hvilke kolonner som er synlige (displaycolumns). Vi mapper
    derfor eksplisitt kolonnenavn → verdi fremfor å bruke posisjonell indeks, slik at
    skjulte kolonner ikke forskyver indeksene for synlige kolonner.
    """
    try:
        all_cols = list(tree["columns"])
    except Exception:
        all_cols = list(columns)

    col_index = {col: i for i, col in enumerate(all_cols)}

    try:
        children = list(tree.get_children(""))[:limit]
    except Exception:
        return []

    rows: List[dict] = []
    for item in children:
        try:
            values = list(tree.item(item).get("values") or [])
        except Exception:
            continue
        if not values:
            continue
        row: dict = {}
        for col in columns:
            idx = col_index.get(col)
            row[col] = values[idx] if idx is not None and idx < len(values) else ""
        rows.append(row)
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

    for col in columns:
        if target_col and col != target_col:
            continue
        if only_missing and col in stored_widths:
            continue

        values = [row.get(col, "") for row in rows]
        width = analyse_treewidths.suggest_column_width(col, values)
        try:
            tree.column(
                col,
                width=width,
                minwidth=analyse_treewidths.column_minwidth(col),
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


def remember_sb_column_widths(*, page: Any) -> None:
    tree = getattr(page, "_sb_tree", None)
    if tree is None:
        return
    widths = snapshot_tree_widths(tree, tree_display_columns(tree))
    if not widths:
        return
    if not hasattr(page, "_sb_col_widths") or page._sb_col_widths is None:
        page._sb_col_widths = {}
    page._sb_col_widths.update(widths)
    persist_saved_column_widths("analyse.sb_cols.widths", page._sb_col_widths)


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

    # Lazy import for å unngå sirkularitet med page_analyse_columns-fasaden.
    from page_analyse_columns import apply_tx_column_config, get_all_tx_columns_for_chooser

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
    if _finish_pivot_header_drag(page=page, event=event):
        return
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region in {"separator", "heading"}:
        remember_pivot_column_widths(page=page)


# =====================================================================
# Pivot-tree kolonne drag-to-reorder
# =====================================================================

def on_pivot_tree_mouse_press(*, page: Any, event: Any) -> None:
    """Registrer start av mulig kolonndrag på pivot-treet."""
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None:
        setattr(page, "_pivot_header_drag", None)
        return
    try:
        region = str(tree.identify_region(event.x, event.y))
    except Exception:
        region = ""
    if region != "heading":
        setattr(page, "_pivot_header_drag", None)
        return
    col = column_id_from_event(tree, event)
    if not col:
        setattr(page, "_pivot_header_drag", None)
        return
    # Pinned kolonner kan ikke flyttes
    pinned = set(getattr(page, "PIVOT_COLS_PINNED", ("Konto", "Kontonavn")))
    if col in pinned:
        setattr(page, "_pivot_header_drag", None)
        return
    setattr(page, "_pivot_header_drag", {
        "source": col, "start_x": event.x, "active": False,
    })


def on_pivot_tree_mouse_drag(*, page: Any, event: Any) -> None:
    """Aktiver drag-modus når muspekeren har beveget seg nok."""
    drag = getattr(page, "_pivot_header_drag", None)
    tree = getattr(page, "_pivot_tree", None)
    if tree is None or event is None or not isinstance(drag, dict):
        return
    if drag.get("active"):
        return
    if abs(event.x - int(drag.get("start_x", 0) or 0)) >= _PIVOT_DRAG_THRESHOLD_PX:
        drag["active"] = True
        setattr(page, "_pivot_header_drag", drag)
        try:
            tree.configure(cursor="fleur")
        except Exception:
            pass


def _finish_pivot_header_drag(*, page: Any, event: Any) -> bool:
    """Fullfør pivot kolonndrag — flytt kolonne til ny posisjon."""
    tree = getattr(page, "_pivot_tree", None)
    drag = getattr(page, "_pivot_header_drag", None)
    setattr(page, "_pivot_header_drag", None)
    try:
        tree.configure(cursor="")
    except Exception:
        pass
    if tree is None or event is None or not isinstance(drag, dict):
        return False
    if not drag.get("active"):
        return False

    source = str(drag.get("source") or "").strip()
    target = column_id_from_event(tree, event) or ""
    if not source or not target or source == target:
        return False

    visible = list(getattr(page, "_pivot_visible_cols", []))
    pinned  = list(getattr(page, "PIVOT_COLS_PINNED", ("Konto", "Kontonavn")))

    if source not in visible or target not in visible:
        return False
    if target in pinned:
        return False  # kan ikke dra inn i pinned-sonen

    # Flytt source til target-posisjon
    visible.remove(source)
    try:
        target_idx = visible.index(target)
    except ValueError:
        target_idx = len(visible)
    visible.insert(target_idx, source)

    page._pivot_visible_cols = visible

    # Lazy import for å unngå sirkularitet med page_analyse_columns-fasaden.
    from page_analyse_columns import apply_pivot_visible_columns, persist_pivot_visible_columns

    apply_pivot_visible_columns(page=page)
    persist_pivot_visible_columns(page=page)

    # Hindre at sortering trigges etter drag
    try:
        setattr(tree, "_suppress_next_heading_sort", True)
        after_fn = getattr(page, "after_idle", None) or getattr(tree, "after_idle", None)
        if callable(after_fn):
            after_fn(lambda: setattr(tree, "_suppress_next_heading_sort", False))
    except Exception:
        pass
    return True


# =====================================================================
# Pivot-sortering: modus-avhengig aktiver/deaktiver
# =====================================================================

def refresh_pivot_sorting(*, page: Any, enable_fn: Any) -> None:
    """Slå sortering av/på i pivot-treet basert på aggregeringsmodus.

    Konto-moduser (SB-konto, HB-konto) → sortering aktivert
        (radene er uavhengige kontoer).
    RL-modus → sortering deaktivert (rekkefølge er semantisk, med summer).
    """
    tree = getattr(page, "_pivot_tree", None)
    if tree is None:
        return

    cols = tuple(getattr(page, "PIVOT_COLS", ()))

    # Lazy import for å unngå sirkularitet med page_analyse_columns-fasaden.
    from page_analyse_columns import _read_agg_mode

    agg = _read_agg_mode(page)

    if agg in ("SB-konto", "HB-konto") and enable_fn is not None:
        try:
            enable_fn(tree, columns=cols)
        except Exception:
            pass
    else:
        # Deaktiver: erstatt kommando med no-op
        for col in cols:
            try:
                tree.heading(col, command=lambda: None)
            except Exception:
                pass


# =====================================================================
# Reset kolonnebredder
# =====================================================================

def reset_pivot_column_widths(*, page: Any) -> None:
    """Slett lagrede bredder og bruk standardverdier igjen."""
    try:
        import preferences as _prefs
        _prefs.set("analyse.pivot.widths", {})
    except Exception:
        pass
    if hasattr(page, "_pivot_col_widths"):
        page._pivot_col_widths = {}
    # Kjør heading-oppdatering for å trigge default-bredder
    from page_analyse_columns import _read_agg_mode
    agg = _read_agg_mode(page) or "Regnskapslinje"
    try:
        import page_analyse_rl as _rl
        _rl.update_pivot_headings(page=page, mode=agg)
    except Exception:
        pass


def reset_tx_column_widths(*, page: Any) -> None:
    """Slett lagrede TX-kolonnebredder."""
    try:
        import preferences as _prefs
        _prefs.set("analyse.tx_cols.widths", {})
    except Exception:
        pass
    if hasattr(page, "_tx_col_widths"):
        page._tx_col_widths = {}


# =====================================================================
# TX-tree kolonnekonfigurasjon og sortering
# =====================================================================

def configure_tx_tree_columns(*, page: Any) -> None:
    if not getattr(page, "_tk_ok", False):
        return

    tree = getattr(page, "_tx_tree", None)
    if tree is None:
        return

    # ManagedTreeview owns column state after migration — sync via its
    # update_columns API instead of hand-rolling tree.configure() which
    # would tear down the manager's display/order tracking.
    managed = getattr(page, "_tx_managed", None)
    if managed is not None:
        try:
            from page_analyse_columns_presets import build_tx_column_specs
            # Send HELE kolonnesettet (TX_COLS_DEFAULT), ikke bare det
            # synlige (TX_COLS). Da vet ManagedTreeview om alle tilgjengelige
            # kolonner, og høyreklikk-velgeren kan vise tilbake skjulte.
            # Brukerens vis/skjul-valg per kolonne håndteres av ManagedTreeview
            # selv via sin _visible-state (preserved av update_columns-fix).
            all_cols = tuple(getattr(page, "TX_COLS_DEFAULT", page.TX_COLS_DEFAULT))
            managed.update_columns(
                build_tx_column_specs(
                    tx_cols_default=all_cols,
                    pinned_cols=getattr(page, "PINNED_TX_COLS", ("Konto", "Kontonavn")),
                    optional_cols=getattr(page, "OPTIONAL_TX_COLS", ()),
                )
            )
        except Exception:
            pass
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
                minwidth=analyse_treewidths.column_minwidth(c),
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
