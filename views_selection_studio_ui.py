"""Utvalg.views_selection_studio

SelectionStudio is a reusable widget used by both the legacy Utvalg page
(`page_utvalg.py`) and the newer strata-based page (`page_utvalg_strata.py`).

This module intentionally keeps backward compatible entrypoints:

* The `SelectionStudio` constructor accepts multiple legacy signatures.
* Helper functions are re-exported from `selection_studio_helpers`.
* Legacy formatting helper names are kept as aliases.

Business rules
--------------
* **Tolererbar feil** is treated as the already calculated threshold
  (arbeidsvesentlighet - forventet feil).
* All bilag with ``abs(SumBeløp) >= tolererbar feil`` are always selected as
  **spesifikk utvelgelse**.
* The recommended sample size is computed on the *remaining* population after
  removing the specific selection (so the recommendation is reduced by the
  automatic picks).

Refactor note
-------------
This file is intentionally kept small. Most logic has been moved into the
`selection_studio.ui_widget_*` modules.
"""

from __future__ import annotations

import random
from typing import Any, Callable, Optional

import pandas as pd
import tkinter as tk
from tkinter import ttk

from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    compute_bilag_split_summary,
    build_sample_summary_text,
    build_source_text,
    confidence_factor,
    compute_population_metrics,
    fmt_amount_no,
    fmt_int_no,
    format_interval_no,
    parse_amount,
    suggest_sample_size,
)

try:
    # Preferred drilldown dialog for bilag
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:  # pragma: no cover
    _open_bilag_drill_dialog = None


# ---------------------------------------------------------------------------
# Helper-/beregningsfunksjoner som brukes av Selection Studio (og testene).
# Disse er flyttet ut for å holde UI-modulen mer lesbar.
from selection_studio_ui_logic import (
    format_amount_input_no,
    no_break_spaces_in_numbers,
    parse_custom_strata_bounds,
    format_custom_strata_bounds,
    stratify_values_custom_bounds,
    split_specific_selection_by_tolerable_error,
    compute_specific_selection_recommendation,
    recommend_random_sample_size_net_basis,
    compute_net_basis_recommendation,
    build_bilag_dataframe,
    stratify_bilag_sums,
)

from selection_studio_ui_builder import build_ui as _build_selection_studio_ui

# Refactor: extracted UI logic
from selection_studio import ui_widget_actions as _actions
from selection_studio import ui_widget_filters as _filters
from selection_studio import ui_widget_refresh as _refresh
from selection_studio import ui_widget_selection as _selection


class SelectionStudio(ttk.Frame):
    """GUI for stratified voucher selection.

    Backward compatible constructor
    ------------------------------
    The project has historically called SelectionStudio in a few different ways.
    This class accepts all of the following:

    * ``SelectionStudio(master, df_base, on_commit, df_all)`` (legacy)
    * ``SelectionStudio(master, df_base, on_commit=..., df_all=...)``
    * ``SelectionStudio(master, df_base=pd.DataFrame(), on_commit_selection=...)``
    * ``SelectionStudio(master, on_commit_selection=...)`` (data loaded later)
    """

    def __init__(self, master: tk.Misc, *args: Any, **kwargs: Any) -> None:
        # Parse legacy positional arguments
        df_base: Optional[pd.DataFrame] = None
        df_all: Optional[pd.DataFrame] = None
        on_commit: Optional[Callable[[pd.DataFrame], None]] = None

        if len(args) >= 1 and isinstance(args[0], pd.DataFrame):
            df_base = args[0]
        if len(args) >= 2 and callable(args[1]):
            on_commit = args[1]
        if len(args) >= 3 and isinstance(args[2], pd.DataFrame):
            df_all = args[2]

        # Keyword overrides / aliases
        df_base = kwargs.pop("df_base", df_base)
        df_all = kwargs.pop("df_all", df_all)

        # Callback aliases (også for gamle navn brukt i ui_main)
        on_commit_kw = kwargs.pop("on_commit", None)
        on_commit_selection_kw = kwargs.pop("on_commit_selection", None)
        on_commit_sample_kw = kwargs.pop("on_commit_sample", None)
        on_commit_selection_kw2 = kwargs.pop("on_commitSample", None)  # defensive
        cb = (
            on_commit_selection_kw
            or on_commit_sample_kw
            or on_commit_kw
            or on_commit_selection_kw2
            or on_commit
        )

        super().__init__(master, **kwargs)

        self._on_commit_selection: Optional[Callable[[pd.DataFrame], None]] = cb

        # Data
        self._df_base: pd.DataFrame = pd.DataFrame()
        self._df_all: pd.DataFrame = pd.DataFrame()

        # NOTE:
        # - _df_calc is the population used for *calculations* (recommendation/sample size).
        #   Amount filter (min/max) must NOT affect this.
        # - _df_filtered is the drawing frame used for *selection* (which bilag can be picked).
        #   Amount filter (min/max) DOES affect this.
        self._df_calc: pd.DataFrame = pd.DataFrame()
        self._df_filtered: pd.DataFrame = pd.DataFrame()

        # Bilag-level aggregates
        self._bilag_df_calc: pd.DataFrame = pd.DataFrame()
        self._bilag_df: pd.DataFrame = pd.DataFrame()

        self._df_sample: pd.DataFrame = pd.DataFrame()

        # Internal state
        self._last_suggested_n: Optional[int] = None
        self._rng = random.Random(42)  # deterministic for repeatability

        # --- UI vars ----------------------------------------------------------
        self.var_only_debit = tk.BooleanVar(value=False)
        self.var_only_credit = tk.BooleanVar(value=False)

        # Backwards compatible: behold var_direction for eldre kode/tester som leser den.
        self.var_direction = tk.StringVar(value="Alle")

        self.var_min_amount = tk.StringVar(value="")
        self.var_max_amount = tk.StringVar(value="")

        # Kandidat til fjerning – ubrukt i UI (beholdes for bakoverkompatibilitet)
        self.var_use_abs = tk.BooleanVar(value=False)

        # Intern guard for å unngå rekursjon når vi synkroniserer checkbokser -> var_direction
        self._dir_sync_guard = False
        self.var_only_debit.trace_add("write", lambda *_: self._on_direction_checkbox_changed("debit"))
        self.var_only_credit.trace_add("write", lambda *_: self._on_direction_checkbox_changed("credit"))

        self.var_risk = tk.StringVar(value="Middels")
        self.var_confidence = tk.StringVar(value="90%")
        self.var_tolerable_error = tk.StringVar(value="")
        self.var_method = tk.StringVar(value="quantile")
        self.var_k = tk.IntVar(value=1)

        # Manuelle strata-grenser (brukes kun når metode = 'custom')
        self.var_custom_bounds = tk.StringVar(value="")
        self.var_custom_bounds_hint = tk.StringVar(value="")
        self._custom_bounds_sync_guard = False

        self.var_sample_n = tk.IntVar(value=0)  # 0 = auto

        self.var_recommendation = tk.StringVar(value="")
        self.var_base_summary = tk.StringVar(value="Ingen data lastet.")

        # Alias for older/newer code paths (avoids runtime AttributeError)
        self._var_base_summary = self.var_base_summary
        # Backwards compatible aliases (older code/tests used underscored var names)
        self._var_recommendation = self.var_recommendation
        self._var_sample_text = self.var_recommendation
        self._var_sample_n = self.var_sample_n

        # Build UI (delegated)
        self._build_ui()

        # Custom strata controls (future-proof; UI builder may or may not include these widgets)
        self.var_method.trace_add("write", lambda *_: self._update_method_controls())
        self.var_custom_bounds.trace_add("write", lambda *_: self._update_method_controls())
        self._update_method_controls()

        # Bindings to keep recommendation up to date
        for v in (
            self.var_direction,
            self.var_min_amount,
            self.var_max_amount,
            self.var_risk,
            self.var_confidence,
            self.var_tolerable_error,
            self.var_method,
            self.var_k,
            self.var_custom_bounds,
        ):
            v.trace_add("write", lambda *_: self._schedule_refresh())

        # Load initial data if provided
        if df_base is not None and not df_base.empty:
            self.load_data(df_base=df_base, df_all=df_all)
        elif df_all is not None and not df_all.empty:
            # Some callers provide only df_all
            self.load_data(df_base=df_all, df_all=df_all)

    # --- public API -------------------------------------------------------------

    def load_data(self, *args: Any, **kwargs: Any) -> None:
        """Load/replace the dataset used for selection.

        Backwards compatible with multiple call styles:

        * ``load_data(df_base, df_all=df_all)``
        * ``load_data(df_all, df_base=df_base)``
        * ``load_data(df_base, df_all)`` or ``load_data(df_all, df_base)``
        """

        df_base = kwargs.pop("df_base", None)
        df_all = kwargs.pop("df_all", None)

        # Positional fallbacks
        if len(args) == 1 and isinstance(args[0], pd.DataFrame):
            if df_base is None and df_all is None:
                df_base = args[0]
        elif len(args) == 2 and all(isinstance(a, pd.DataFrame) for a in args):
            a0, a1 = args
            # Infer which is the "all" dataframe by size (rows)
            if df_base is None and df_all is None:
                if len(a0) >= len(a1):
                    df_all = a0
                    df_base = a1
                else:
                    df_all = a1
                    df_base = a0
            else:
                df_base = df_base or a0
                df_all = df_all or a1

        if df_base is None:
            df_base = pd.DataFrame()
        if df_all is None:
            df_all = df_base

        self._df_base = df_base.copy()
        self._df_all = df_all.copy()
        self._df_sample = pd.DataFrame()

        # Sensible default tolerable error if empty: 5% of population book value (rounded).
        if not (self.var_tolerable_error.get() or "").strip() and not self._df_base.empty:
            try:
                metrics = compute_population_metrics(self._df_base)

                # Netto is standard; if net is ~0, fall back to absolute sum.
                base_value = abs(float(getattr(metrics, "sum_net", 0.0) or 0.0))
                if base_value <= 0.0:
                    base_value = float(getattr(metrics, "sum_abs", 0.0) or 0.0)

                default_tol = max(int(round(base_value * 0.05)), 0)
                if default_tol > 0:
                    self.var_tolerable_error.set(format_amount_input_no(default_tol))
            except Exception:
                pass

        self._schedule_refresh(immediate=True)

    # --- UI --------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Bygger GUI-elementer (delegert til selection_studio_ui_builder)."""

        _build_selection_studio_ui(self)

    # --- thin wrappers: keep names stable --------------------------------------

    def _on_direction_checkbox_changed(self, changed: str) -> None:
        _filters.on_direction_checkbox_changed(self, changed)

    def _update_method_controls(self) -> None:
        _filters.update_method_controls(self)

    def _format_custom_bounds_entry(self) -> None:
        _filters.format_custom_bounds_entry(self)

    def _get_custom_bounds(self) -> list[float]:
        return _filters.get_custom_bounds(self)

    def _stratify_remaining_values(self, values: pd.Series):
        return _filters.stratify_remaining_values(self, values)

    def _schedule_refresh(self, immediate: bool = False) -> None:
        _refresh.schedule_refresh(self, immediate=immediate)

    def _refresh_all(self) -> None:
        _refresh.refresh_all(self)

    def _apply_filters(self, df: pd.DataFrame, *, apply_amount_filter: bool = True) -> pd.DataFrame:
        return _filters.apply_filters(self, df, apply_amount_filter=apply_amount_filter)

    def _build_bilag_split_text(self, bilag_df: pd.DataFrame, *, tolerable_error: float) -> str:
        return _refresh.build_bilag_split_text(bilag_df, tolerable_error=tolerable_error)

    def _compute_recommendation(self):
        return _refresh.compute_recommendation(self)

    def _update_recommendation_text(self, rec) -> None:
        return _refresh.update_recommendation_text(self, rec)

    def _refresh_groups_table(self) -> None:
        return _refresh.refresh_groups_table(self)

    def _run_selection(self) -> None:
        _selection.run_selection(self)

    def _draw_stratified_sample(self, remaining_bilag_df: pd.DataFrame, n: int):
        return _selection.draw_stratified_sample(self, remaining_bilag_df, n)

    def _populate_tree(self, df: pd.DataFrame) -> None:
        _selection.populate_tree(self, df)

    def _commit_selection(self) -> None:
        _actions.commit_selection(self)

    def _export_excel(self) -> None:
        _actions.export_excel(self)

    def _show_accounts(self) -> None:
        _actions.show_accounts(self)

    def _open_document_control(self) -> None:
        _actions.open_document_control(self)

    def _open_drilldown(self) -> None:
        _actions.open_drilldown(self, open_dialog=_open_bilag_drill_dialog)

    def _build_bilag_df(self, df: pd.DataFrame) -> pd.DataFrame:
        return _selection.build_bilag_df(df)

    def _parse_confidence_percent(self, s: str) -> float:
        return _filters.parse_confidence_percent(s)

    def _get_tolerable_error_value(self) -> float:
        return _filters.get_tolerable_error_value(self)

    def _format_tolerable_error_entry(self) -> None:
        _filters.format_tolerable_error_entry(self)

    def _sample_size_touched(self) -> None:
        _actions.sample_size_touched(self)


__all__ = [
    "SelectionStudio",
    # helpers re-exported for tests and other modules
    "PopulationMetrics",
    "compute_population_metrics",
    "build_population_summary_text",
    "build_sample_summary_text",
    "build_source_text",
    "compute_bilag_split_summary",
    "confidence_factor",
    "suggest_sample_size",
    "fmt_amount_no",
    "fmt_int_no",
    "format_interval_no",
    "parse_amount",
    # selection_studio_ui_logic exports
    "format_amount_input_no",
    "no_break_spaces_in_numbers",
    "parse_custom_strata_bounds",
    "format_custom_strata_bounds",
    "stratify_values_custom_bounds",
    "split_specific_selection_by_tolerable_error",
    "compute_specific_selection_recommendation",
    "recommend_random_sample_size_net_basis",
    "compute_net_basis_recommendation",
    "build_bilag_dataframe",
    "stratify_bilag_sums",
]

# Ensure these names exist at module-level (some older code/tests import them from here).
from selection_studio_bilag import build_bilag_dataframe, stratify_bilag_sums  # noqa: E402,F401
