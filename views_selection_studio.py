from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from selectionstudio_filters import filter_selectionstudio_dataframe
from selection_studio_helpers import (
    PopulationMetrics,
    build_population_summary_text,
    build_sample_summary_text,
    build_source_text,
    compute_population_metrics,
    confidence_factor,
    export_to_excel,
    fmt_amount_no,
    fmt_int_no,
    format_amount_input_no,
    format_interval_no,
    parse_amount,
    suggest_sample_size,
)
from stratifiering import stratify_bilag

try:
    # Preferred API in this codebase
    from selection_studio_drill import open_bilag_drill_dialog as _open_bilag_drill_dialog
except Exception:
    _open_bilag_drill_dialog = None


# ---------------------------------------------------------------------------
# Specific selection helpers (tolerable error threshold)
# ---------------------------------------------------------------------------


def split_specific_selection_by_tolerable_error(
    bilag_df: pd.DataFrame,
    tolerable_error: float | int,
    *,
    amount_col: str = "SumBeløp",
    use_abs: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split bilag dataframe into specific selection and remaining based on tolerable error.

    Rule:
      - specific: abs(SumBeløp) >= tolerable_error  (default abs)
      - remaining: abs(SumBeløp) < tolerable_error
    """

    if bilag_df is None or bilag_df.empty:
        return bilag_df.copy(), bilag_df.copy()

    tol = float(tolerable_error or 0.0)
    if tol < 0:
        tol = abs(tol)

    amounts = pd.to_numeric(bilag_df.get(amount_col, 0.0), errors="coerce").fillna(0.0)
    metric = amounts.abs() if use_abs else amounts
    mask = metric >= tol

    return bilag_df.loc[mask].copy(), bilag_df.loc[~mask].copy()


class SpecificSelectionRecommendation(dict):
    """Dict-like recommendation that also supports attribute access.

    This keeps backwards compatibility with tests that use both:
      - reco["n_specific"]
      - reco.specific_count
    """

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e

    def __setattr__(self, key: str, value: Any) -> None:
        self[key] = value


def compute_specific_selection_recommendation(
    bilag_df: pd.DataFrame | None = None,
    tolerable_error: float | int | None = None,
    *,
    bilag_values: Optional[Iterable[float]] = None,
    amount_column: str = "SumBeløp",
    threshold: float | int | None = None,
    use_abs: bool = True,
    sample_size: int | None = None,
    confidence_factor: float | None = None,
) -> SpecificSelectionRecommendation:
    """Compute counts and book values for specific selection based on tolerable error.

    Supports two input styles:

    1) bilag_df provided:
       Expected to be bilag-level with `amount_column` (default SumBeløp) and preferably `Bilag`.

    2) bilag_values provided (e.g. pd.Series of bilag sums):
       If bilag_values is a Series, its index is treated as bilag identifiers.

    Returns a dict-like object with stable keys used by tests and UI.
    """

    tol_raw = threshold if threshold is not None else tolerable_error
    tol = float(tol_raw or 0.0)
    if tol < 0:
        tol = abs(tol)

    # Build a series of amounts and bilag ids
    bilag_ids: list[Any]
    amounts: pd.Series

    specific_df = None
    remaining_df = None

    if bilag_values is not None:
        if isinstance(bilag_values, pd.Series):
            amounts = pd.to_numeric(bilag_values, errors="coerce").fillna(0.0)
            bilag_ids = list(amounts.index.tolist())
        else:
            seq = list(bilag_values)
            amounts = pd.to_numeric(pd.Series(seq), errors="coerce").fillna(0.0)
            bilag_ids = list(amounts.index.tolist())
    else:
        if bilag_df is None:
            bilag_df = pd.DataFrame(columns=["Bilag", amount_column])

        amounts = pd.to_numeric(bilag_df.get(amount_column, 0.0), errors="coerce").fillna(0.0)
        if "Bilag" in bilag_df.columns:
            bilag_ids = bilag_df["Bilag"].tolist()
        else:
            bilag_ids = list(bilag_df.index.tolist())

    metric = amounts.abs() if use_abs else amounts
    mask = metric >= tol

    # Identify bilag
    specific_bilag = [bilag_ids[i] for i, m in enumerate(mask.tolist()) if m]
    remaining_bilag = [bilag_ids[i] for i, m in enumerate(mask.tolist()) if not m]

    n_specific = len(specific_bilag)
    n_remaining = len(remaining_bilag)
    n_total = n_specific + n_remaining

    specific_value = float(metric[mask].sum()) if n_specific else 0.0
    remaining_value = float(metric[~mask].sum()) if n_remaining else 0.0
    total_value = float(metric.sum()) if n_total else 0.0

    # If dataframe exists, also return the split dfs
    if bilag_values is None and bilag_df is not None and not bilag_df.empty:
        specific_df = bilag_df.loc[mask].copy()
        remaining_df = bilag_df.loc[~mask].copy()

    # Optional: recommend additional_n using the simple ratio formula used by tests
    additional_n = None
    total_n = None
    if confidence_factor is not None and tol > 0:
        import math

        add_raw = int(math.ceil((remaining_value / tol) * float(confidence_factor)))
        add = max(0, min(add_raw, n_remaining))
        additional_n = add
        total_n = n_specific + add

    rec = SpecificSelectionRecommendation(
        tolerable_error=tol,
        threshold=tol,
        n_specific=n_specific,
        n_remaining=n_remaining,
        n_total=n_total,
        specific_book_value=specific_value,
        remaining_book_value=remaining_value,
        total_book_value=total_value,
        specific_bilag=specific_bilag,
        remaining_bilag=remaining_bilag,
        specific_count=n_specific,
        remaining_count=n_remaining,
        confidence_factor=confidence_factor,
        additional_n=additional_n,
        total_n=total_n,
        specific_df=specific_df,
        remaining_df=remaining_df,
    )

    if sample_size is not None:
        try:
            before = int(sample_size)
        except Exception:
            before = None
        if before is not None:
            rec["sample_size_before"] = before
            rec["sample_size_after"] = max(before - n_specific, 0)

    return rec


def stratify_bilag_sums(
    bilag_df: pd.DataFrame,
    *,
    method: str = "quantile",
    k: int = 3,
    sum_col: str = "SumBeløp",
    bilag_col: str = "Bilag",
    use_abs: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, str]]:
    """Adapter: stratify a bilag-level DF by their summed amount.

    The stratifier in this codebase expects a *transaction-like* dataframe
    containing columns (Bilag, Beløp). In SelectionStudio we already have a
    bilag-level DF with (Bilag, SumBeløp), so we adapt it here.

    Returns: (summary_df, bilag_out_df, interval_map)

    This function is intentionally pure (no Tk), so we can unit test it.
    """

    if bilag_df is None or bilag_df.empty:
        return pd.DataFrame(), pd.DataFrame(), {}

    if bilag_col not in bilag_df.columns or sum_col not in bilag_df.columns:
        raise KeyError(f"DataFrame må inneholde kolonnene '{bilag_col}' og '{sum_col}'.")

    mode = (method or "quantile").strip().lower()
    k = max(int(k or 1), 1)

    df_for_strata = bilag_df[[bilag_col, sum_col]].copy()
    df_for_strata = df_for_strata.rename(columns={bilag_col: "Bilag", sum_col: "Beløp"})
    df_for_strata["Beløp"] = pd.to_numeric(df_for_strata["Beløp"], errors="coerce").fillna(0.0)

    # Preferred API: stratify_bilag(df, k=..., method=..., abs_belop=...)
    try:
        summary, bilag_out, interval_map = stratify_bilag(df_for_strata, k=k, method=mode, abs_belop=use_abs)
        return summary, bilag_out, interval_map
    except TypeError:
        pass
    except KeyError:
        # This happens if stratify_bilag was called with wrong input type; fallback below.
        pass

    # Fallback: old/alternate API where stratify_bilag expects a Series and returns (groups, interval_map, stats_df)
    values = df_for_strata["Beløp"].abs() if use_abs else df_for_strata["Beløp"]
    groups, interval_map_old, stats_df = stratify_bilag(values, method=mode, k=k)

    # Build a bilag_out with __grp__ based on masks
    out_rows: list[dict[str, Any]] = []
    for grp_label, mask in groups:
        ids = df_for_strata.loc[mask, "Bilag"].tolist()
        vals = df_for_strata.loc[mask, "Beløp"].tolist()
        for b, v in zip(ids, vals):
            out_rows.append({"Bilag": b, "SumBeløp": abs(v) if use_abs else v, "__grp__": int(grp_label)})

    bilag_out = pd.DataFrame(out_rows)
    if bilag_out.empty:
        bilag_out = pd.DataFrame(columns=["Bilag", "SumBeløp", "__grp__"])

    # Normalize summary columns if they exist
    if isinstance(stats_df, pd.DataFrame) and not stats_df.empty:
        # Try to map to the newer summary format
        summary = stats_df.copy()
        if "Antall" in summary.columns and "Antall_bilag" not in summary.columns:
            summary = summary.rename(columns={"Antall": "Antall_bilag"})
        if "Sum" in summary.columns and "SumBeløp" not in summary.columns:
            summary = summary.rename(columns={"Sum": "SumBeløp"})
        if "Intervall" not in summary.columns and "Gruppe" in summary.columns:
            summary["Intervall"] = summary["Gruppe"].map(interval_map_old)
    else:
        summary = pd.DataFrame()

    # Convert interval_map to int-keyed dict if possible
    interval_map: dict[int, str] = {}
    for k0, v0 in (interval_map_old or {}).items():
        try:
            interval_map[int(k0)] = str(v0)
        except Exception:
            continue

    return summary, bilag_out, interval_map


# ---------------------------------------------------------------------------
# Selection studio UI widget
# ---------------------------------------------------------------------------


@dataclass
class _Recommendation:
    tolerable_error: float
    confidence_factor: float
    n_specific: int
    n_random: int
    n_total: int


class SelectionStudio(ttk.Frame):
    """SelectionStudio: UI + glue logic.

    This widget is embedded in UtvalgStrataPage and pushes samples to Resultat via callback.
    """

    def __init__(
        self,
        master: tk.Misc,
        df_base: Optional[pd.DataFrame] = None,
        df_all: Optional[pd.DataFrame] = None,
        on_commit_selection: Optional[Callable[[pd.DataFrame], None]] = None,
        on_commit_sample: Optional[Callable[[pd.DataFrame], None]] = None,
        on_commit: Optional[Callable[[pd.DataFrame], None]] = None,
        **kwargs: Any,
    ) -> None:
        # Prevent Tk from receiving custom args
        self._on_commit_selection = on_commit_selection or on_commit_sample or on_commit
        super().__init__(master)

        # Data
        self._df_all = df_all
        self._df_base = df_base
        self._df_filtered = pd.DataFrame()
        self._df_sample = pd.DataFrame()
        self._bilag_df = pd.DataFrame()

        # Random state (stable in tests)
        self._rng = random.Random(42)

        # UI vars
        self.var_direction = tk.StringVar(value="Alle")
        self.var_min_amount = tk.StringVar(value="")
        self.var_max_amount = tk.StringVar(value="")
        self.var_use_abs = tk.BooleanVar(value=True)

        self.var_risk = tk.StringVar(value="Middels")
        self.var_confidence = tk.StringVar(value="90%")
        self.var_tolerable_error = tk.StringVar(value="")
        self.var_method = tk.StringVar(value="quantile")
        self.var_k = tk.IntVar(value=3)
        self.var_sample_n = tk.IntVar(value=0)

        self.var_base_summary = tk.StringVar(value="")
        self.var_reco_text = tk.StringVar(value="")

        self._pending_refresh = None
        self._last_suggested_n: Optional[int] = None

        # Build UI
        self._build_ui()

        # Bind variable changes to recompute recommendation
        for v in (
            self.var_direction,
            self.var_min_amount,
            self.var_max_amount,
            self.var_use_abs,
            self.var_risk,
            self.var_confidence,
            self.var_tolerable_error,
            self.var_method,
            self.var_k,
        ):
            v.trace_add("write", lambda *_: self._schedule_refresh())

        # Pretty-format tolerable error on focus out
        self.ent_tol.bind("<FocusOut>", lambda *_: self._format_tolerable_error_entry())

        # Track manual changes to sample size (do not overwrite)
        self.spin_n.bind("<FocusOut>", lambda *_: self._sample_size_touched())
        self.spin_n.bind("<KeyRelease>", lambda *_: self._sample_size_touched())

        # Initial load
        self.load_data(df_base=df_base, df_all=df_all)

    # --- public API ---------------------------------------------------------------

    def load_data(self, df_base: Optional[pd.DataFrame] = None, df_all: Optional[pd.DataFrame] = None, *args: Any) -> None:
        """Load data into the studio.

        Backwards compatible signature:
          - load_data(df) uses same df for base+all
          - load_data(df_all, df_base)
        """
        # Accept positional variants for backward compatibility
        if args and df_base is None and df_all is None:
            # load_data(df)
            df_base = args[0]
            df_all = args[0]
        elif args and df_base is not None and df_all is None:
            # load_data(df_all, df_base) legacy pattern
            df_all = df_base
            df_base = args[0]
        elif len(args) == 2 and isinstance(args[0], pd.DataFrame) and isinstance(args[1], pd.DataFrame):
            # load_data(df_all, df_base)
            df_all = args[0]
            df_base = args[1]

        # If both provided, we can heuristically swap if needed (all should be superset)
        if isinstance(df_all, pd.DataFrame) and isinstance(df_base, pd.DataFrame):
            if len(df_all) < len(df_base):
                df_all, df_base = df_base, df_all

        self._df_all = df_all
        self._df_base = df_base

        self._schedule_refresh(immediate=True)

    # --- ui building --------------------------------------------------------------

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(2, weight=1)

        # Top summary
        lbl = ttk.Label(self, textvariable=self.var_base_summary, anchor="w")
        lbl.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))

        # Left controls frame
        left = ttk.Frame(self)
        left.grid(row=1, column=0, rowspan=2, sticky="nsw", padx=8, pady=4)
        left.columnconfigure(1, weight=1)

        # Filters
        lf_filters = ttk.LabelFrame(left, text="Filtre")
        lf_filters.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        lf_filters.columnconfigure(1, weight=1)

        ttk.Label(lf_filters, text="Retning").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        cb_dir = ttk.Combobox(
            lf_filters,
            textvariable=self.var_direction,
            values=["Alle", "Debet", "Kredit"],
            state="readonly",
            width=12,
        )
        cb_dir.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(lf_filters, text="Beløp fra/til").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.ent_min = ttk.Entry(lf_filters, textvariable=self.var_min_amount, width=12)
        self.ent_min.grid(row=1, column=1, sticky="w", padx=(6, 2), pady=4)
        ttk.Label(lf_filters, text="til").grid(row=1, column=1, sticky="w", padx=(110, 2), pady=4)
        self.ent_max = ttk.Entry(lf_filters, textvariable=self.var_max_amount, width=12)
        self.ent_max.grid(row=1, column=1, sticky="e", padx=(2, 6), pady=4)

        chk_abs = ttk.Checkbutton(lf_filters, text="Bruk absolutt beløp", variable=self.var_use_abs)
        chk_abs.grid(row=2, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        # Sampling / selection parameters (visible, not advanced)
        lf_select = ttk.LabelFrame(left, text="Utvalg")
        lf_select.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        lf_select.columnconfigure(1, weight=1)

        ttk.Label(lf_select, text="Risiko").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        cb_risk = ttk.Combobox(lf_select, textvariable=self.var_risk, values=["Lav", "Middels", "Høy"], state="readonly", width=12)
        cb_risk.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(lf_select, text="Sikkerhet").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        cb_conf = ttk.Combobox(lf_select, textvariable=self.var_confidence, values=["80%", "90%", "95%"], state="readonly", width=12)
        cb_conf.grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(lf_select, text="Tolererbar feil").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        self.ent_tol = ttk.Entry(lf_select, textvariable=self.var_tolerable_error, width=14)
        self.ent_tol.grid(row=2, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(lf_select, text="Metode").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        cb_method = ttk.Combobox(
            lf_select,
            textvariable=self.var_method,
            values=["quantile", "equal_width"],
            state="readonly",
            width=12,
        )
        cb_method.grid(row=3, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(lf_select, text="Antall grupper (k)").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        sp_k = ttk.Spinbox(lf_select, from_=1, to=10, textvariable=self.var_k, width=6)
        sp_k.grid(row=4, column=1, sticky="w", padx=6, pady=4)

        ttk.Label(lf_select, text="Utvalgsstørrelse").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        self.spin_n = ttk.Spinbox(lf_select, from_=0, to=999999, textvariable=self.var_sample_n, width=8)
        self.spin_n.grid(row=5, column=1, sticky="w", padx=6, pady=4)

        # Recommendation text
        ttk.Label(lf_select, textvariable=self.var_reco_text, justify="left").grid(
            row=6, column=0, columnspan=2, sticky="w", padx=6, pady=(2, 6)
        )

        # Buttons
        btn_run = ttk.Button(left, text="Kjør utvalg", command=self._run_selection)
        btn_run.grid(row=2, column=0, sticky="ew", pady=(0, 6))

        btn_commit = ttk.Button(left, text="Legg i utvalg", command=self._commit_selection)
        btn_commit.grid(row=3, column=0, sticky="ew", pady=(0, 6))

        btn_export = ttk.Button(left, text="Eksporter Excel", command=self._export_excel)
        btn_export.grid(row=4, column=0, sticky="ew", pady=(0, 6))

        # Right area: notebook with sample + groups
        self.nb = ttk.Notebook(self)
        self.nb.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=(0, 8), pady=4)

        # Sample tab
        tab_sample = ttk.Frame(self.nb)
        tab_sample.columnconfigure(0, weight=1)
        tab_sample.rowconfigure(1, weight=1)
        self.nb.add(tab_sample, text="Utvalg")

        # Top buttons row
        topbar = ttk.Frame(tab_sample)
        topbar.grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        topbar.columnconfigure(0, weight=1)

        ttk.Button(topbar, text="Vis kontorer", command=self._show_accounts).grid(row=0, column=1, padx=4)
        ttk.Button(topbar, text="Drilldown", command=self._open_drilldown).grid(row=0, column=2, padx=4)

        # Treeview
        self.tree = ttk.Treeview(
            tab_sample,
            columns=("Bilag", "Dato", "Tekst", "SumBeløp", "Gruppe", "Intervall"),
            show="headings",
        )
        self.tree.grid(row=1, column=0, sticky="nsew", padx=4, pady=(0, 4))
        for col, w, anchor in [
            ("Bilag", 80, "w"),
            ("Dato", 90, "w"),
            ("Tekst", 300, "w"),
            ("SumBeløp", 120, "e"),
            ("Gruppe", 80, "w"),
            ("Intervall", 160, "w"),
        ]:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, anchor=anchor)

        ys = ttk.Scrollbar(tab_sample, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=ys.set)
        ys.grid(row=1, column=1, sticky="ns")

        # Groups tab
        tab_groups = ttk.Frame(self.nb)
        tab_groups.columnconfigure(0, weight=1)
        tab_groups.rowconfigure(0, weight=1)
        self.nb.add(tab_groups, text="Grupper")

        self.tree_groups = ttk.Treeview(
            tab_groups,
            columns=("Gruppe", "Intervall", "Antall", "SumBeløp"),
            show="headings",
        )
        self.tree_groups.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        for col, w, anchor in [
            ("Gruppe", 80, "w"),
            ("Intervall", 200, "w"),
            ("Antall", 80, "e"),
            ("SumBeløp", 120, "e"),
        ]:
            self.tree_groups.heading(col, text=col)
            self.tree_groups.column(col, width=w, anchor=anchor)

        ys2 = ttk.Scrollbar(tab_groups, orient=tk.VERTICAL, command=self.tree_groups.yview)
        self.tree_groups.configure(yscrollcommand=ys2.set)
        ys2.grid(row=0, column=1, sticky="ns")

    # --- refresh logic ------------------------------------------------------------

    def _schedule_refresh(self, immediate: bool = False) -> None:
        if self._pending_refresh is not None:
            try:
                self.after_cancel(self._pending_refresh)
            except Exception:
                pass
            self._pending_refresh = None

        if immediate:
            self._refresh_all()
        else:
            self._pending_refresh = self.after(200, self._refresh_all)

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        direction = self.var_direction.get()
        min_v = parse_amount(self.var_min_amount.get())
        max_v = parse_amount(self.var_max_amount.get())
        use_abs = bool(self.var_use_abs.get())

        # Support both kw names via selectionstudio_filters wrapper
        return filter_selectionstudio_dataframe(
            df,
            direction=direction,
            min_amount=min_v,
            max_amount=max_v,
            use_abs=use_abs,
        )

    def _refresh_all(self) -> None:
        self._pending_refresh = None

        df_base = self._df_base
        df_all = self._df_all

        if df_base is None or not isinstance(df_base, pd.DataFrame) or df_base.empty:
            self._df_filtered = pd.DataFrame()
            self._df_sample = pd.DataFrame()
            self._bilag_df = pd.DataFrame()
            self.var_base_summary.set("Ingen data lastet.")
            self.var_reco_text.set("")
            self._populate_tree(pd.DataFrame())
            self._refresh_groups_table()
            return

        self._df_filtered = self._apply_filters(df_base)

        # Summary text (base + filtered)
        try:
            base_m = compute_population_metrics(df_base, abs_basis=bool(self.var_use_abs.get()))
            work_m = compute_population_metrics(self._df_filtered, abs_basis=bool(self.var_use_abs.get()))
            self.var_base_summary.set(build_population_summary_text(base_m, work_m, abs_basis=bool(self.var_use_abs.get())))
        except Exception:
            self.var_base_summary.set("Ingen data lastet.")

        # Recommendation
        rec = self._compute_recommendation()
        self._update_recommendation_text(rec)

        # Groups table
        self._refresh_groups_table()

    def _compute_recommendation(self) -> _Recommendation:
        # Build bilag df from filtered transactions
        self._bilag_df = self._build_bilag_df(self._df_filtered)

        tol = self._get_tolerable_error_value()
        use_abs = bool(self.var_use_abs.get())

        # Determine risk/confidence factor
        risk = (self.var_risk.get() or "Middels").strip().lower()
        conf = self._parse_confidence_percent(self.var_confidence.get())
        conf_factor = float(confidence_factor(risk, conf))

        spec_info = compute_specific_selection_recommendation(self._bilag_df, tol, use_abs=use_abs)
        n_specific = int(spec_info["n_specific"])
        remaining_df = spec_info["remaining_df"]
        remaining_value = float(spec_info["remaining_book_value"])

        # Suggested random sample size from remaining population
        n_random = 0
        if tol > 0 and remaining_value > 0:
            try:
                # Newer helper signature (preferred)
                n_random = int(
                    suggest_sample_size(
                        int(len(remaining_df)),
                        tolerable_error=tol,
                        expected_error=0.0,
                        risk_level=risk,
                        confidence_level=conf,
                        population_value=remaining_value,
                        min_size=1,
                        max_size=max(int(len(remaining_df)), 1),
                    )
                )
            except TypeError:
                # Older/legacy signature used in earlier iterations of the project
                n_random = int(
                    suggest_sample_size(
                        population_value=remaining_value,
                        tolerable_error=tol,
                        confidence_factor=conf_factor,
                        min_n=1,
                        max_n=max(int(len(remaining_df)), 1),
                    )
                )

        n_total = n_specific + n_random
        return _Recommendation(
            tolerable_error=tol,
            confidence_factor=conf_factor,
            n_specific=n_specific,
            n_random=n_random,
            n_total=n_total,
        )

    def _update_recommendation_text(self, rec: _Recommendation) -> None:
        tol_txt = fmt_amount_no(rec.tolerable_error, decimals=0) if rec.tolerable_error else "0"
        conf_txt = str(rec.confidence_factor).replace(".", ",")
        txt = (
            f"Tolererbar feil: {tol_txt}\n"
            f"Konfidensfaktor: {conf_txt}\n"
            f"Forslag utvalg: {rec.n_total} bilag"
        )
        if rec.n_specific:
            txt += f" (inkl. {rec.n_specific} spesifikk)"

        self.var_reco_text.set(txt)

        # Auto-set sample size if not manually touched or zero
        current = int(self.var_sample_n.get() or 0)
        if current == 0 or current == self._last_suggested_n:
            self.var_sample_n.set(int(rec.n_total))
            self._last_suggested_n = int(rec.n_total)

    def _refresh_groups_table(self) -> None:
        """Populate the Grupper tab with current strata + specific selection.

        Uses stratify_bilag_sums adapter to avoid KeyError('Beløp') when stratifier expects a DF.
        """

        for i in self.tree_groups.get_children():
            self.tree_groups.delete(i)

        bilag_df = self._bilag_df
        if bilag_df is None or bilag_df.empty:
            return

        tol = self._get_tolerable_error_value()
        use_abs = bool(self.var_use_abs.get())

        specific, remaining = split_specific_selection_by_tolerable_error(bilag_df, tol, use_abs=use_abs)

        # Add specific row (if any)
        if not specific.empty:
            spec_sum = float(pd.to_numeric(specific["SumBeløp"], errors="coerce").fillna(0.0).abs().sum() if use_abs else specific["SumBeløp"].sum())
            self.tree_groups.insert(
                "",
                "end",
                values=("Spesifikk", f">= {fmt_amount_no(float(tol), decimals=0)}", fmt_int_no(len(specific)), fmt_amount_no(spec_sum)),
            )

        if remaining.empty:
            return

        method = (self.var_method.get() or "quantile").strip().lower()
        k = max(int(self.var_k.get() or 3), 1)

        try:
            summary, _bilag_out, _interval_map = stratify_bilag_sums(
                remaining,
                method=method,
                k=k,
                sum_col="SumBeløp",
                bilag_col="Bilag",
                use_abs=use_abs,
            )
        except Exception:
            return

        if summary is None or summary.empty:
            return

        # Expected columns from stratifiering.py: Gruppe, Antall_bilag, SumBeløp, Intervall
        for _, row in summary.sort_values("Gruppe").iterrows():
            grp = row.get("Gruppe", "")
            interval = row.get("Intervall", "")
            cnt = row.get("Antall_bilag", row.get("Antall", 0))
            s = row.get("SumBeløp", row.get("Sum", 0.0))
            self.tree_groups.insert(
                "",
                "end",
                values=(str(grp), format_interval_no(str(interval)), fmt_int_no(int(cnt)), fmt_amount_no(float(s))),
            )

    # --- selection ----------------------------------------------------------------

    def _run_selection(self) -> None:
        try:
            if self._df_filtered is None or self._df_filtered.empty:
                messagebox.showinfo("Utvalg", "Ingen data i grunnlaget.")
                return

            bilag_df = self._bilag_df
            if bilag_df is None or bilag_df.empty:
                messagebox.showinfo("Utvalg", "Ingen bilag i grunnlaget.")
                return

            tol = self._get_tolerable_error_value()
            use_abs = bool(self.var_use_abs.get())

            # Split specific selection out
            spec_df, remaining = split_specific_selection_by_tolerable_error(bilag_df, tol, use_abs=use_abs)
            specific_ids = spec_df["Bilag"].tolist() if not spec_df.empty else []

            # Determine how many to draw from remaining
            try:
                n_total = int(self.var_sample_n.get() or 0)
            except Exception:
                n_total = 0

            n_total = max(n_total, 0)
            n_random = max(0, n_total - len(specific_ids))
            n_random = min(n_random, len(remaining))

            # Draw stratified random from remaining bilag IDs
            random_ids: list[Any] = []
            if n_random > 0 and not remaining.empty:
                random_ids = self._draw_stratified_sample(remaining, n_random)

            # Build sample bilag_df and mark group/interval
            chosen_ids = list(dict.fromkeys(specific_ids + random_ids))  # preserve order & unique
            sample_df = bilag_df[bilag_df["Bilag"].isin(chosen_ids)].copy()

            # Add group labels
            sample_df["Gruppe"] = ""
            sample_df["Intervall"] = ""

            if not spec_df.empty:
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Gruppe"] = "Spesifikk"
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Intervall"] = f">= {fmt_amount_no(float(tol), decimals=0)}"

            # Fill for random using stratification intervals (best effort)
            if random_ids:
                method = (self.var_method.get() or "quantile").strip().lower()
                k = max(int(self.var_k.get() or 3), 1)

                try:
                    _summary, bilag_out, interval_map = stratify_bilag_sums(
                        remaining,
                        method=method,
                        k=k,
                        sum_col="SumBeløp",
                        bilag_col="Bilag",
                        use_abs=use_abs,
                    )
                    bilag_to_grp = (
                        bilag_out.set_index("Bilag")["__grp__"].to_dict()
                        if isinstance(bilag_out, pd.DataFrame) and not bilag_out.empty and "__grp__" in bilag_out.columns
                        else {}
                    )
                    group_to_interval = {int(g): format_interval_no(str(iv)) for g, iv in (interval_map or {}).items()}

                    mask_random = sample_df["Bilag"].isin(random_ids) & ~sample_df["Bilag"].isin(specific_ids)
                    grp_series = sample_df.loc[mask_random, "Bilag"].map(bilag_to_grp)

                    sample_df.loc[mask_random, "Gruppe"] = grp_series.apply(
                        lambda g: str(int(g)) if pd.notna(g) else ""
                    )
                    sample_df.loc[mask_random, "Intervall"] = grp_series.apply(
                        lambda g: group_to_interval.get(int(g), "") if pd.notna(g) else ""
                    )
                except Exception:
                    # Best effort: hvis strata-feiler, la Gruppe/Intervall være tom
                    pass

            # Sort by abs sum amount desc
            amounts_sort = pd.to_numeric(sample_df["SumBeløp"], errors="coerce").fillna(0.0)
            sample_df = sample_df.assign(_abs_sort=amounts_sort.abs()).sort_values("_abs_sort", ascending=False).drop(
                columns=["_abs_sort"]
            )

            self._df_sample = sample_df
            self._populate_tree(sample_df)
            self.nb.select(0)

        except Exception as e:
            messagebox.showerror("Utvalg", f"Kunne ikke kjøre utvalg.\n\n{e}")

    def _draw_stratified_sample(self, remaining_bilag_df: pd.DataFrame, n: int) -> list[Any]:
        """Draw a stratified sample of bilag IDs from remaining_bilag_df.

        Viktig: stratifiering.stratify_bilag forventer en DF med kolonnene
        (Bilag, Beløp). Tidligere ble den kalt med en Series, som ga
        ``KeyError: 'Beløp'`` ved kjøring.
        """

        if n <= 0 or remaining_bilag_df.empty:
            return []

        n = min(int(n), int(len(remaining_bilag_df)))
        use_abs = bool(self.var_use_abs.get())

        method = (self.var_method.get() or "quantile").strip().lower()
        k = max(int(self.var_k.get() or 3), 1)

        try:
            _summary, bilag_with_grp, _interval_map = stratify_bilag_sums(
                remaining_bilag_df,
                method=method,
                k=k,
                sum_col="SumBeløp",
                bilag_col="Bilag",
                use_abs=use_abs,
            )
        except Exception:
            bilag_with_grp = pd.DataFrame()

        # Fallback: hvis strata ikke kunne beregnes, trekk tilfeldig fra hele remaining.
        if bilag_with_grp is None or bilag_with_grp.empty or "__grp__" not in bilag_with_grp.columns:
            ids = list(remaining_bilag_df["Bilag"].tolist())
            self._rng.shuffle(ids)
            return ids[:n]

        # Kandidater per gruppe
        groups = (
            bilag_with_grp.groupby("__grp__")["Bilag"].apply(list).to_dict()
            if "__grp__" in bilag_with_grp.columns
            else {}
        )

        if not groups:
            ids = list(remaining_bilag_df["Bilag"].tolist())
            self._rng.shuffle(ids)
            return ids[:n]

        # Proposjonal allokering (Hamilton / largest remainder)
        grp_keys = sorted(groups.keys())
        sizes = {g: len(groups[g]) for g in grp_keys}
        total = sum(sizes.values()) or 1

        import math

        quotas = {g: (n * sizes[g] / total) for g in grp_keys}
        alloc = {g: int(math.floor(quotas[g])) for g in grp_keys}
        remainder = n - sum(alloc.values())

        # Distribuer rester etter største desimalrest
        frac_order = sorted(grp_keys, key=lambda g: (quotas[g] - alloc[g]), reverse=True)
        for g in frac_order:
            if remainder <= 0:
                break
            alloc[g] += 1
            remainder -= 1

        chosen: list[Any] = []
        chosen_set: set[Any] = set()

        for g in grp_keys:
            take = max(0, min(int(alloc.get(g, 0)), sizes[g]))
            if take <= 0:
                continue
            candidates = list(groups[g])
            self._rng.shuffle(candidates)
            picked = candidates[:take]
            chosen.extend(picked)
            chosen_set.update(picked)

        # Fyll opp hvis vi fikk for få pga tomme/rare strata
        if len(chosen) < n:
            remaining_ids = [x for x in remaining_bilag_df["Bilag"].tolist() if x not in chosen_set]
            self._rng.shuffle(remaining_ids)
            chosen.extend(remaining_ids[: n - len(chosen)])

        return chosen[:n]


    def _populate_tree(self, df: pd.DataFrame) -> None:
        for i in self.tree.get_children():
            self.tree.delete(i)

        if df is None or df.empty:
            return

        for _, row in df.iterrows():
            bilag = row.get("Bilag", "")
            dato = row.get("Dato", "")
            tekst = row.get("Tekst", "")
            sum_belop = row.get("SumBeløp", 0.0)
            gruppe = row.get("Gruppe", "")
            intervall = row.get("Intervall", "")
            self.tree.insert(
                "",
                "end",
                values=(
                    bilag,
                    str(dato)[:10] if pd.notna(dato) else "",
                    tekst,
                    fmt_amount_no(float(sum_belop)),
                    gruppe,
                    intervall,
                ),
            )

    def _commit_selection(self) -> None:
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showinfo("Utvalg", "Ingen utvalg å legge til.")
            return

        if self._on_commit_selection is None:
            messagebox.showinfo("Utvalg", "Ingen mottaker for utvalg (on_commit).")
            return

        try:
            self._on_commit_selection(self._df_sample.copy())
        except Exception as e:
            messagebox.showerror("Utvalg", f"Kunne ikke legge utvalg til.\n\n{e}")

    def _export_excel(self) -> None:
        if self._df_sample is None or self._df_sample.empty:
            messagebox.showinfo("Eksporter", "Ingen utvalg å eksportere.")
            return

        path = filedialog.asksaveasfilename(
            title="Lagre Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
        )
        if not path:
            return

        try:
            export_to_excel(
                path,
                Utvalg=self._df_sample,
                Grunnlag=self._df_filtered,
            )
            messagebox.showinfo("Eksporter", "Eksportert.")
        except Exception as e:
            messagebox.showerror("Eksporter", f"Kunne ikke eksportere.\n\n{e}")

    def _show_accounts(self) -> None:
        """Vis en enkel kontosummering for nåværende (filtrerte) grunnlag."""

        df = self._df_filtered
        if df is None or df.empty:
            messagebox.showinfo("Kontorer", "Ingen data å vise.")
            return

        if "Konto" not in df.columns:
            messagebox.showinfo("Kontorer", "Datasettet mangler kolonnen 'Konto'.")
            return

        konto_col = "Konto"
        navn_col = "Kontonavn" if "Kontonavn" in df.columns else None

        gcols = [konto_col] + ([navn_col] if navn_col else [])
        agg = {
            "Rader": (konto_col, "size"),
            "Bilag": ("Bilag", "nunique") if "Bilag" in df.columns else (konto_col, "size"),
            "Sum": ("Beløp", "sum") if "Beløp" in df.columns else (konto_col, "size"),
        }

        try:
            summary = df.groupby(gcols, dropna=False).agg(**agg).reset_index()
        except Exception:
            # Fallback for older pandas versions
            summary = df.groupby(gcols, dropna=False).agg({
                konto_col: "size",
                "Bilag": "nunique" if "Bilag" in df.columns else "size",
                "Beløp": "sum" if "Beløp" in df.columns else "size",
            }).reset_index()
            # Normalize column names
            if konto_col in summary.columns:
                summary = summary.rename(columns={konto_col: "Rader"})
            if "Bilag" in df.columns and "Bilag" in summary.columns:
                summary = summary.rename(columns={"Bilag": "Bilag"})
            if "Beløp" in summary.columns:
                summary = summary.rename(columns={"Beløp": "Sum"})

        if "Sum" in summary.columns:
            summary = summary.reindex(summary["Sum"].abs().sort_values(ascending=False).index)

        win = tk.Toplevel(self)
        win.title("Kontosummering")
        win.geometry("700x400")

        cols = ["Konto"]
        if navn_col:
            cols.append("Kontonavn")
        cols += ["Rader", "Bilag", "Sum"]

        tree = ttk.Treeview(win, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=120, anchor=("w" if c in ("Konto", "Kontonavn") else "e"))
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ys = ttk.Scrollbar(win, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscrollcommand=ys.set)
        ys.pack(side=tk.RIGHT, fill=tk.Y)

        for _, row in summary.iterrows():
            konto = row.get(konto_col, "")
            navn = row.get(navn_col, "") if navn_col else ""
            rader = int(row.get("Rader", 0) or 0)
            bilag = int(row.get("Bilag", 0) or 0)
            s = float(row.get("Sum", 0.0) or 0.0)

            values: list[Any] = [konto]
            if navn_col:
                values.append(navn)
            values += [fmt_int_no(rader), fmt_int_no(bilag), fmt_amount_no(s, decimals=2)]
            tree.insert("", tk.END, values=values)

    def _open_drilldown(self) -> None:
        if _open_bilag_drill_dialog is None:
            messagebox.showinfo("Drilldown", "Drilldown er ikke tilgjengelig.")
            return
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Drilldown", "Velg et bilag i tabellen først.")
            return

        values = self.tree.item(selection[0], "values")
        if not values:
            return
        bilag = values[0]
        try:
            _open_bilag_drill_dialog(self, df_all=self._df_all, bilag_col="Bilag", preset_bilag=bilag)
        except Exception as e:
            messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")

    # --- helpers -----------------------------------------------------------------

    def _build_bilag_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["Bilag", "Dato", "Tekst", "SumBeløp"])  # stable columns

        # Ensure required columns exist
        if "Bilag" not in df.columns or "Beløp" not in df.columns:
            raise KeyError("DataFrame må inneholde kolonnene 'Bilag' og 'Beløp'.")

        # Aggregate
        gb = df.groupby("Bilag", as_index=False)
        bilag_df = gb.agg(
            {
                "Beløp": "sum",
                # Take first non-null for display columns
                "Dato": "first" if "Dato" in df.columns else "size",
                "Tekst": "first" if "Tekst" in df.columns else "size",
            }
        )
        bilag_df = bilag_df.rename(columns={"Beløp": "SumBeløp"})

        # When Dato/Tekst were missing we used 'size' above; replace with empty
        if "Dato" in bilag_df.columns and bilag_df["Dato"].dtype == "int64":
            bilag_df["Dato"] = ""
        if "Tekst" in bilag_df.columns and bilag_df["Tekst"].dtype == "int64":
            bilag_df["Tekst"] = ""

        return bilag_df

    def _parse_confidence_percent(self, s: str) -> float:
        s = (s or "90%").strip().replace("%", "")
        try:
            return float(s) / 100.0
        except Exception:
            return 0.90

    def _get_tolerable_error_value(self) -> float:
        return parse_amount(self.var_tolerable_error.get())

    def _format_tolerable_error_entry(self) -> None:
        raw = self.var_tolerable_error.get()
        if not (raw or "").strip():
            return
        try:
            n = parse_amount(raw)
        except Exception:
            return
        # Keep it as integer-like
        self.var_tolerable_error.set(format_amount_input_no(n))

    def _sample_size_touched(self) -> None:
        # If user manually sets an explicit number, stop auto-updating
        try:
            current = int(self.var_sample_n.get() or 0)
        except Exception:
            return
        if self._last_suggested_n is not None and current != 0 and current != self._last_suggested_n:
            # Keep user's choice; do not overwrite on refresh
            pass


__all__ = [
    # widget
    "SelectionStudio",
    # helper re-exports
    "compute_population_metrics",
    "PopulationMetrics",
    "build_sample_summary_text",
    "build_source_text",
    "build_population_summary_text",
    "suggest_sample_size",
    "confidence_factor",
    "fmt_amount_no",
    "fmt_int_no",
    "format_interval_no",
    "parse_amount",
    # legacy formatting aliases
    "format_amount_input_no",
    # new specific selection helpers
    "split_specific_selection_by_tolerable_error",
    "compute_specific_selection_recommendation",
    "SpecificSelectionRecommendation",
    "stratify_bilag_sums",
]
