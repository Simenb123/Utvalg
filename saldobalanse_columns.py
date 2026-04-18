"""saldobalanse_columns.py — Kolonne-valg og presets for Saldobalanse-fanen.

Modulfunksjonene tar `page` (en SaldobalansePage-instans) som første argument
og leser/skriver direkte på side-attributtene `_column_order`, `_visible_cols`,
`_tree`, `_var_preset`, `_var_work_mode`. Klassen [page_saldobalanse.py](page_saldobalanse.py)
beholder tynne metode-delegater som kaller inn hit, slik at eksisterende
`command=`-bindings og tester (som kaller f.eks. `page._on_preset_changed()`)
fortsetter å virke.
"""

from __future__ import annotations

import preferences

from saldobalanse_payload import (
    ALL_COLUMNS,
    COLUMN_PRESETS,
    DEFAULT_COLUMN_ORDER,
    DEFAULT_VISIBLE_COLUMNS,
    WORK_MODE_PAYROLL,
    WORK_MODE_STANDARD,
    _ordered_columns_for_visible,
    _preset_name_for_visible_columns,
)


def load_column_preferences(page) -> None:
    try:
        order = preferences.get("saldobalanse.columns.order", None)
        visible = preferences.get("saldobalanse.columns.visible", None)
    except Exception:
        order = None
        visible = None

    if isinstance(order, list):
        cleaned = [col for col in order if col in ALL_COLUMNS]
        for col in ALL_COLUMNS:
            if col not in cleaned:
                cleaned.append(col)
        if cleaned:
            page._column_order = cleaned

    if isinstance(visible, list):
        cleaned_visible = [col for col in visible if col in ALL_COLUMNS]
        if cleaned_visible:
            page._visible_cols = cleaned_visible


def persist_column_preferences(page) -> None:
    try:
        preferences.set("saldobalanse.columns.order", list(page._column_order))
        preferences.set("saldobalanse.columns.visible", list(page._visible_cols))
    except Exception:
        pass


def apply_visible_columns(page) -> None:
    if page._tree is None:
        return
    visible = [col for col in page._column_order if col in page._visible_cols]
    if not visible:
        visible = list(DEFAULT_VISIBLE_COLUMNS)
    try:
        page._tree["displaycolumns"] = visible
    except Exception:
        pass


def sync_preset_var(page) -> None:
    if page._var_preset is None:
        return
    try:
        page._var_preset.set(_preset_name_for_visible_columns(page._visible_cols))
    except Exception:
        pass


def on_preset_changed(page) -> None:
    if page._var_preset is None:
        return
    preset_name = str(page._var_preset.get() or "").strip()
    preset_cols = COLUMN_PRESETS.get(preset_name)
    if not preset_cols:
        return
    if page._var_work_mode is not None:
        try:
            if preset_name in {"Lønnsklassifisering", "Lønn/A07"}:
                page._var_work_mode.set(WORK_MODE_PAYROLL)
            elif page._is_payroll_mode():
                page._var_work_mode.set(WORK_MODE_STANDARD)
        except Exception:
            pass
    page._visible_cols = list(preset_cols)
    page._column_order = _ordered_columns_for_visible(list(preset_cols))
    page._apply_visible_columns()
    page._persist_column_preferences()
    page._sync_mode_ui()
    page.refresh()


def open_column_chooser(page) -> None:
    try:
        from views_column_chooser import open_column_chooser as _open
    except Exception:
        return

    res = _open(
        page,
        all_cols=list(ALL_COLUMNS),
        visible_cols=list(page._visible_cols),
        initial_order=list(page._column_order),
        default_visible_cols=list(DEFAULT_VISIBLE_COLUMNS),
        default_order=list(DEFAULT_COLUMN_ORDER),
    )
    if not res:
        return

    order, visible = res
    page._column_order = [col for col in order if col in ALL_COLUMNS]
    for col in ALL_COLUMNS:
        if col not in page._column_order:
            page._column_order.append(col)
    page._visible_cols = [col for col in visible if col in ALL_COLUMNS]
    page._apply_visible_columns()
    page._persist_column_preferences()
    page._sync_preset_var()
    page.refresh()
