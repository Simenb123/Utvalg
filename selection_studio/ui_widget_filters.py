"""Selection Studio widget: filters and input helpers.

This module holds small, testable helper functions that operate on a
SelectionStudio-like object (the real Tkinter widget passes itself).

We keep these functions outside of `views_selection_studio_ui.py` to keep the
UI facade under ~400 lines.
"""

from __future__ import annotations

import math

from typing import Any, Tuple

import pandas as pd

from .filters import filter_selectionstudio_dataframe
from .helpers import fmt_amount_no, parse_amount
from .ui_logic import (
    format_amount_input_no,
    format_custom_strata_bounds,
    no_break_spaces_in_numbers,
    parse_custom_strata_bounds,
    stratify_values_custom_bounds,
)
from .bilag import stratify_bilag_sums


def on_direction_checkbox_changed(studio: Any, changed: str) -> None:
    """Synchronise direction checkboxes to `var_direction`.

    Behaviour:
      - None selected  -> "Alle"
      - Only debit     -> "Debet"
      - Only credit    -> "Kredit"

    The checkboxes are treated as mutually exclusive to avoid ambiguity.
    """

    if getattr(studio, "_dir_sync_guard", False):
        return

    studio._dir_sync_guard = True
    try:
        only_debit = bool(studio.var_only_debit.get())
        only_credit = bool(studio.var_only_credit.get())

        # If user turns on one, turn off the other
        if changed == "debit" and only_debit:
            if only_credit:
                studio.var_only_credit.set(False)
            studio.var_direction.set("Debet")
            return

        if changed == "credit" and only_credit:
            if only_debit:
                studio.var_only_debit.set(False)
            studio.var_direction.set("Kredit")
            return

        # If a box was turned off: set direction based on current state
        only_debit = bool(studio.var_only_debit.get())
        only_credit = bool(studio.var_only_credit.get())

        if only_debit:
            studio.var_direction.set("Debet")
        elif only_credit:
            studio.var_direction.set("Kredit")
        else:
            studio.var_direction.set("Alle")
    finally:
        studio._dir_sync_guard = False


def apply_filters(studio: Any, df: pd.DataFrame, *, apply_amount_filter: bool = True) -> pd.DataFrame:
    """Apply UI filters to a dataframe and return filtered frame.

    Important: amount filter can be disabled for calculation purposes
    (recommendations should not change when the user narrows the drawing frame).
    """

    if df is None or df.empty:
        return pd.DataFrame()

    direction = (studio.var_direction.get() or "Alle").strip()
    min_value = studio.var_min_amount.get() if apply_amount_filter else ""
    max_value = studio.var_max_amount.get() if apply_amount_filter else ""

    # Beløp fra/til: when direction=Alle it's most intuitive to filter on abs(netto).
    df_filtered, _summary = filter_selectionstudio_dataframe(
        df,
        direction=direction,
        min_value=min_value,
        max_value=max_value,
        use_abs=(direction == "Alle"),
    )
    return df_filtered


def parse_confidence_percent(s: str) -> float:
    """Parse GUI confidence value like '90%' into 0.9."""

    txt = (s or "90%").strip().replace("%", "")
    try:
        return float(txt) / 100.0
    except Exception:
        return 0.90


def get_tolerable_error_value(studio: Any) -> float:
    """Return tolerable error as a number (0.0 if empty/invalid)."""

    try:
        v = parse_amount(studio.var_tolerable_error.get())
    except Exception:
        return 0.0
    return float(v) if v is not None else 0.0


def format_tolerable_error_entry(studio: Any) -> None:
    """Normalise tolerable error input when the Entry loses focus."""

    raw = studio.var_tolerable_error.get()
    if not (raw or "").strip():
        return
    try:
        n = parse_amount(raw)
    except Exception:
        return

    # Keep it as integer-like
    studio.var_tolerable_error.set(format_amount_input_no(n))


# --- custom strata boundaries (manual) -----------------------------------------


def update_method_controls(studio: Any) -> None:
    """Show/hide custom-bound controls and enable/disable k."""

    method = (studio.var_method.get() or "quantile").strip().lower()
    is_custom = method == "custom"

    # Show/hide frame
    if hasattr(studio, "frm_custom_bounds"):
        try:
            if is_custom:
                studio.frm_custom_bounds.grid()
            else:
                studio.frm_custom_bounds.grid_remove()
        except Exception:
            pass

    # Enable/disable k spinbox
    spn = getattr(studio, "_spn_k", None)
    if spn is not None:
        try:
            spn.configure(state="disabled" if is_custom else "normal")
        except Exception:
            pass

    # Update hint text
    if not hasattr(studio, "var_custom_bounds_hint"):
        return

    if not is_custom:
        studio.var_custom_bounds_hint.set("")
        return

    raw = (studio.var_custom_bounds.get() or "").strip()
    if not raw:
        studio.var_custom_bounds_hint.set("Bruk ';' mellom grenser, f.eks. 100 000; 500 000")
        return

    bounds = parse_custom_strata_bounds(raw)
    if not bounds:
        studio.var_custom_bounds_hint.set(
            "Kunne ikke tolke grenser. Bruk ';' mellom tall, f.eks. 100 000; 500 000"
        )
        return

    studio.var_custom_bounds_hint.set(
        no_break_spaces_in_numbers(f"{len(bounds)} grenser → {len(bounds) + 1} grupper")
    )


def format_custom_bounds_entry(studio: Any) -> None:
    """Normalise custom bounds input (sort, remove duplicates)."""

    if getattr(studio, "_custom_bounds_sync_guard", False):
        return

    raw = (studio.var_custom_bounds.get() or "").strip()
    if not raw:
        return

    bounds = parse_custom_strata_bounds(raw)
    if not bounds:
        return

    normalized = format_custom_strata_bounds(bounds)
    if normalized and normalized != raw:
        try:
            studio._custom_bounds_sync_guard = True
            studio.var_custom_bounds.set(normalized)
        finally:
            studio._custom_bounds_sync_guard = False


def get_custom_bounds(studio: Any) -> list[float]:
    """Read custom strata bounds from UI."""

    return parse_custom_strata_bounds(studio.var_custom_bounds.get())


def stratify_remaining_values(
    studio: Any, values: pd.Series
) -> Tuple[list[tuple[Any, pd.Series]], dict[str, str], pd.DataFrame]:
    """Stratify remaining population values according to selected method."""

    method = (studio.var_method.get() or "quantile").strip().lower()
    if method == "custom":
        bounds = get_custom_bounds(studio)
        return stratify_values_custom_bounds(values, bounds=bounds)

    k = int(studio.var_k.get() or 1)
    return stratify_bilag_sums(values, method=method, k=k, use_abs=False)

