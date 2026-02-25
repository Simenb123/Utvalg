"""Selection Studio widget: refresh/recommendation logic.

This module contains the "controller" logic that keeps the Selection Studio UI
in sync when the user changes filters or parameters.

The real Tkinter widget delegates to these functions.
"""

from __future__ import annotations

from typing import Any, Optional

import pandas as pd

from .helpers import (
    build_population_summary_text,
    build_sample_summary_text,
    compute_population_metrics,
    confidence_factor,
    fmt_amount_no,
    fmt_int_no,
)
from .ui_logic import no_break_spaces_in_numbers, split_specific_selection_by_tolerable_error, compute_net_basis_recommendation
from .ui_widget_models import Recommendation
from .ui_widget_filters import get_tolerable_error_value, parse_confidence_percent


def schedule_refresh(studio: Any, *, immediate: bool = False) -> None:
    """Debounced refresh.

    When running in headless/test mode (no Tk widget), we fall back to immediate.
    """

    if immediate or not hasattr(studio, "after"):
        refresh_all(studio)
        return

    after_id = getattr(studio, "_refresh_after_id", None)
    if after_id is not None and hasattr(studio, "after_cancel"):
        try:
            studio.after_cancel(after_id)
        except Exception:
            pass

    try:
        studio._refresh_after_id = studio.after(200, studio._refresh_all)
    except Exception:
        # Defensive: if Tk isn't running, just refresh now.
        refresh_all(studio)


def refresh_all(studio: Any) -> None:
    """Refresh both calculation state and visible UI text/tables."""

    # We keep two versions of the dataset:
    # - _df_calc: used for calculations/recommendations (amount filter must NOT apply)
    # - _df_filtered: used as drawing frame (amount filter DOES apply)
    studio._df_calc = studio._apply_filters(studio._df_base, apply_amount_filter=False)
    studio._df_filtered = studio._apply_filters(studio._df_base, apply_amount_filter=True)

    # Summary at top: show calculation population, and (if amount filter is set) the drawing frame
    base_metrics = compute_population_metrics(studio._df_base)
    calc_metrics = compute_population_metrics(studio._df_calc)
    draw_metrics = compute_population_metrics(studio._df_filtered)

    summary_text = build_population_summary_text(base_metrics, calc_metrics, abs_basis=False)

    min_raw = (studio.var_min_amount.get() or "").strip()
    max_raw = (studio.var_max_amount.get() or "").strip()
    if min_raw or max_raw:
        removed_rows = max(0, calc_metrics.n_rows - draw_metrics.n_rows)
        removed_bilag = max(0, calc_metrics.n_bilag - draw_metrics.n_bilag)
        removed_konto = max(0, calc_metrics.n_konto - draw_metrics.n_konto)

        parts = [
            f"Trekkgrunnlag (etter beløpsfilter): {fmt_int_no(draw_metrics.n_rows)} rader",
            f"{fmt_int_no(draw_metrics.n_bilag)} bilag",
            f"{fmt_int_no(draw_metrics.n_konto)} kontorer",
        ]
        extra = ""
        if removed_rows or removed_bilag or removed_konto:
            extra = (
                f" (fjernet {fmt_int_no(removed_rows)} rader | "
                f"{fmt_int_no(removed_bilag)} bilag | "
                f"{fmt_int_no(removed_konto)} kontorer)"
            )
        summary_text = summary_text + "\n" + " | ".join(parts) + extra

    studio.var_base_summary.set(summary_text)

    rec = compute_recommendation(studio)
    if rec:
        studio._var_sample_text.set(
            build_sample_summary_text(
                rec.n_total_recommended,
                rec.n_specific,
                rec.n_random_recommended,
                rec.population_value_remaining,
            )
        )
        studio._var_sample_n.set(int(rec.n_total_recommended))
    else:
        studio._var_sample_text.set(build_sample_summary_text(0, 0, 0, 0.0))
        studio._var_sample_n.set(0)

    update_recommendation_text(studio, rec)

    # Split text is based on the calculation population (not the amount-filtered drawing frame)
    split_text = build_bilag_split_text(
        studio._bilag_df_calc,
        tolerable_error=get_tolerable_error_value(studio),
    )

    # Add a note if amount filter reduces the available bilag for drawing
    if min_raw or max_raw:
        available = 0 if studio._bilag_df is None else int(len(studio._bilag_df))
        split_text += f"\n\nTrekkgrunnlag (bilag) etter beløpsfilter: {fmt_int_no(available)}"
        if rec:
            wanted = int(rec.n_total_recommended or 0)
            if available and available < wanted:
                split_text += f" (OBS: færre enn foreslått utvalg {fmt_int_no(wanted)})"

    studio.var_recommendation.set(studio.var_recommendation.get() + "\n\n" + split_text)

    refresh_groups_table(studio)


def build_bilag_split_text(bilag_df: pd.DataFrame, *, tolerable_error: float) -> str:
    """Build compact text: population vs specific selection vs remaining."""

    if bilag_df is None or bilag_df.empty or "SumBeløp" not in bilag_df.columns:
        return ""

    tol = abs(float(tolerable_error or 0.0))
    amounts = pd.to_numeric(bilag_df["SumBeløp"], errors="coerce").fillna(0.0)

    n_total = int(len(bilag_df))
    net_total = float(amounts.sum())
    abs_total = float(amounts.abs().sum())

    if tol > 0.0:
        mask_spec = amounts.abs() >= tol
    else:
        mask_spec = pd.Series([False] * len(bilag_df), index=bilag_df.index)

    amounts_spec = amounts.loc[mask_spec]
    amounts_rem = amounts.loc[~mask_spec]

    n_spec = int(mask_spec.sum())
    n_rem = int(n_total - n_spec)

    net_spec = float(amounts_spec.sum()) if n_spec else 0.0
    abs_spec = float(amounts_spec.abs().sum()) if n_spec else 0.0

    net_rem = float(amounts_rem.sum()) if n_rem else 0.0
    abs_rem = float(amounts_rem.abs().sum()) if n_rem else 0.0

    tol_txt = fmt_amount_no(tol, decimals=0) if tol > 0 else "0"

    return (
        f"Populasjon (bilag): {fmt_int_no(n_total)} | Netto: {fmt_amount_no(net_total, decimals=0)} | Abs: {fmt_amount_no(abs_total, decimals=0)}\n"
        f"Spesifikk (|beløp| >= {tol_txt}): {fmt_int_no(n_spec)} | Netto: {fmt_amount_no(net_spec, decimals=0)} | Abs: {fmt_amount_no(abs_spec, decimals=0)}\n"
        f"Restpopulasjon: {fmt_int_no(n_rem)} | Netto: {fmt_amount_no(net_rem, decimals=0)} | Abs: {fmt_amount_no(abs_rem, decimals=0)}\n"
        f"Beregning tilfeldig trekk bruker |netto rest|: {fmt_amount_no(abs(net_rem), decimals=0)}"
    )


def compute_recommendation(studio: Any) -> Recommendation | None:
    """Compute recommended sample size and update internal bilag frames."""

    # Build bilag-level df for drawing frame (used for grouping + selection)
    if studio._df_filtered is None or studio._df_filtered.empty:
        studio._bilag_df = pd.DataFrame()
    else:
        studio._bilag_df = studio._build_bilag_df(studio._df_filtered)

    # Build bilag-level df for calculations (amount filter must NOT affect this)
    if studio._df_calc is None or studio._df_calc.empty:
        studio._bilag_df_calc = pd.DataFrame()
        return None

    studio._bilag_df_calc = studio._build_bilag_df(studio._df_calc)
    if studio._bilag_df_calc is None or studio._bilag_df_calc.empty:
        return None

    tol = get_tolerable_error_value(studio)

    # Confidence factor (risk + confidence)
    risk_level = (studio.var_risk.get() or "Middels").strip().lower()
    conf_level = parse_confidence_percent(studio.var_confidence.get())
    conf_factor = confidence_factor(risk_level=risk_level, confidence_level=conf_level)

    rec_dict = compute_net_basis_recommendation(
        studio._bilag_df_calc,
        tolerable_error=tol,
        confidence_factor=float(conf_factor),
        amount_col="SumBeløp",
    )
    n_specific = int(rec_dict["n_specific"])
    n_random = int(rec_dict["n_random"])
    n_total = int(rec_dict["n_total"])
    remaining_net = float(rec_dict["remaining_net"])

    # Update the sample size spinbox default behaviour
    current_n = int(studio.var_sample_n.get() or 0)
    last_suggested = getattr(studio, "_last_suggested_n", None)
    if current_n == 0 or (last_suggested is not None and current_n == last_suggested):
        studio.var_sample_n.set(n_total)
    studio._last_suggested_n = n_total

    return Recommendation(
        conf_factor=float(conf_factor),
        n_specific=n_specific,
        n_random_recommended=int(n_random),
        n_total_recommended=int(n_total),
        population_value_remaining=float(remaining_net),
    )


def update_recommendation_text(studio: Any, rec: Optional[Recommendation]) -> None:
    """Update the top recommendation label text."""

    tol = get_tolerable_error_value(studio)

    parts: list[str] = []

    if tol > 0:
        parts.append(f"Tolererbar feil: {fmt_amount_no(tol, decimals=0)}")

    if rec is None:
        studio.var_recommendation.set(no_break_spaces_in_numbers("\n".join(parts)))
        return

    if rec.conf_factor:
        parts.append(f"Konfidensfaktor: {str(rec.conf_factor).replace('.', ',')}")

    parts.append(
        f"Forslag utvalg: {fmt_int_no(rec.n_total_recommended)} bilag"
        + (f" (inkl. {fmt_int_no(rec.n_specific)} spesifikk)" if rec.n_specific else "")
    )

    studio.var_recommendation.set(no_break_spaces_in_numbers("\n".join(parts)))


def refresh_groups_table(studio: Any) -> None:
    """Populate group summary table based on current drawing-frame bilag."""

    for i in studio.tree_groups.get_children():
        studio.tree_groups.delete(i)

    if studio._bilag_df is None or studio._bilag_df.empty:
        return

    tol = get_tolerable_error_value(studio)
    # Specific selection is always based on |SumBeløp| >= tolerable error
    spec, remaining = split_specific_selection_by_tolerable_error(studio._bilag_df, tol, use_abs=True)
    if remaining.empty:
        # Only specific
        if not spec.empty:
            sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
            studio.tree_groups.insert(
                "",
                "end",
                values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)),
            )
        return

    # Stratify on absolute amount (nice positive intervals)
    values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
    try:
        groups, interval_map, stats_df = studio._stratify_remaining_values(values)
    except Exception:
        return

    # Insert optional specific group first
    if not spec.empty:
        sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
        studio.tree_groups.insert(
            "",
            "end",
            values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)),
        )

    # Stats per group: stats_df columns: Gruppe, Antall, Sum, Min, Max
    for _, row in stats_df.iterrows():
        grp = row.get("Gruppe")
        interval = interval_map.get(str(grp), "")
        studio.tree_groups.insert(
            "",
            "end",
            values=(
                str(grp),
                interval,
                int(row.get("Antall", 0)),
                fmt_amount_no(float(row.get("Sum", 0.0))),
            ),
        )
