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
"""

from __future__ import annotations

import math
import re
import inspect
import os
from datetime import datetime

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

import random

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from controller_export import export_to_excel
from selectionstudio_filters import filter_selectionstudio_dataframe

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

@dataclass
class _Recommendation:
    conf_factor: float
    n_specific: int
    n_random_recommended: int
    n_total_recommended: int
    population_value_remaining: float


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

    # --- constructor / public API -------------------------------------------------

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
        self._df_filtered: pd.DataFrame = pd.DataFrame()
        self._bilag_df: pd.DataFrame = pd.DataFrame()
        self._df_sample: pd.DataFrame = pd.DataFrame()

        # Internal state
        self._last_suggested_n: Optional[int] = None
        self._rng = random.Random(42)  # deterministic for repeatability

        # UI vars
        # Retning: i revisjon er "Alle" (netto) default. Vi tilbyr to enkle
        # av/på-filter i stedet for en rullgardin, for å redusere risiko for feilvalg.
        self.var_only_debit = tk.BooleanVar(value=False)
        self.var_only_credit = tk.BooleanVar(value=False)

        # Backwards compatible: behold var_direction for eldre kode/tester som leser den.
        self.var_direction = tk.StringVar(value="Alle")

        self.var_min_amount = tk.StringVar(value="")
        self.var_max_amount = tk.StringVar(value="")

        # Bruk absolutt beløp var tidligere en bruker-toggle. I revisjon er netto
        # standard, og vi skjuler derfor denne fra UI. Den beholdes kun for
        # bakoverkompatibilitet, men brukes ikke i filter-/beregningslogikk.
        self.var_use_abs = tk.BooleanVar(value=False)  # Kandidat til fjerning – ubrukt i UI

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

        self._build_ui()

        # Vis/skjul kontroller for manuelle strata-grenser
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
        # I praksis er tolererbar feil en input fra revisjonsplanleggingen, men dette gir
        # et "ikke-null" forslag når brukeren ikke har fylt inn noe.
        if not (self.var_tolerable_error.get() or "").strip() and not self._df_base.empty:
            try:
                metrics = compute_population_metrics(self._df_base)

                # Netto er standard i revisjon, men dersom netto summerer til ~0 (f.eks. clearing),
                # faller vi tilbake til absolutt-sum for å unngå et tomt forslag.
                base_value = abs(float(getattr(metrics, "sum_net", 0.0) or 0.0))
                if base_value <= 0.0:
                    base_value = float(getattr(metrics, "sum_abs", 0.0) or 0.0)

                default_tol = max(int(round(base_value * 0.05)), 0)
                if default_tol > 0:
                    self.var_tolerable_error.set(format_amount_input_no(default_tol))
            except Exception:
                pass

        self._schedule_refresh(immediate=True)

    # --- UI ----------------------------------------------------------------------

    def _build_ui(self) -> None:
        """Bygger GUI-elementer (delegert til selection_studio_ui_builder)."""
        _build_selection_studio_ui(self)

    def _on_direction_checkbox_changed(self, changed: str) -> None:
        """Synkroniser checkbokser (Kun debet/kun kredit) til var_direction.

        * Ingen valgt  -> "Alle"
        * Kun debet    -> "Debet"
        * Kun kredit   -> "Kredit"

        Boksene er gjensidig utelukkende for å unngå tvetydig filtrering.
        """

        if getattr(self, "_dir_sync_guard", False):
            return

        self._dir_sync_guard = True
        try:
            only_debit = bool(self.var_only_debit.get())
            only_credit = bool(self.var_only_credit.get())

            # Hvis bruker slår på én, slår vi av den andre
            if changed == "debit" and only_debit:
                if only_credit:
                    self.var_only_credit.set(False)
                self.var_direction.set("Debet")
                return

            if changed == "credit" and only_credit:
                if only_debit:
                    self.var_only_debit.set(False)
                self.var_direction.set("Kredit")
                return

            # Hvis en boks ble slått av: sett retning basert på gjeldende state
            only_debit = bool(self.var_only_debit.get())
            only_credit = bool(self.var_only_credit.get())

            if only_debit:
                self.var_direction.set("Debet")
            elif only_credit:
                self.var_direction.set("Kredit")
            else:
                self.var_direction.set("Alle")
        finally:
            self._dir_sync_guard = False

    # --- custom strata (manuelle grenser) --------------------------------------

    def _update_method_controls(self) -> None:
        """Vis/skjul felt for manuelle strata-grenser og aktiver/deaktiver k."""
        method = (self.var_method.get() or "quantile").strip().lower()
        is_custom = method == "custom"

        # Vis/skjul frame
        if hasattr(self, "frm_custom_bounds"):
            try:
                if is_custom:
                    self.frm_custom_bounds.grid()
                else:
                    self.frm_custom_bounds.grid_remove()
            except Exception:
                pass

        # Aktiver/deaktiver k
        if hasattr(self, "_spn_k") and self._spn_k is not None:
            try:
                self._spn_k.configure(state="disabled" if is_custom else "normal")
            except Exception:
                pass

        # Oppdater hint
        if not hasattr(self, "var_custom_bounds_hint"):
            return

        if not is_custom:
            self.var_custom_bounds_hint.set("")
            return

        raw = (self.var_custom_bounds.get() or "").strip()
        if not raw:
            self.var_custom_bounds_hint.set("Bruk ';' mellom grenser, f.eks. 100 000; 500 000")
            return

        bounds = parse_custom_strata_bounds(raw)
        if not bounds:
            self.var_custom_bounds_hint.set("Kunne ikke tolke grenser. Bruk ';' mellom tall, f.eks. 100 000; 500 000")
            return

        self.var_custom_bounds_hint.set(
            no_break_spaces_in_numbers(f"{len(bounds)} grenser → {len(bounds) + 1} grupper")
        )

    def _format_custom_bounds_entry(self) -> None:
        """Normaliser input (sorter, fjern duplikater) når feltet mister fokus."""
        if getattr(self, "_custom_bounds_sync_guard", False):
            return

        raw = (self.var_custom_bounds.get() or "").strip()
        if not raw:
            return

        bounds = parse_custom_strata_bounds(raw)
        if not bounds:
            return

        normalized = format_custom_strata_bounds(bounds)
        if normalized and normalized != raw:
            try:
                self._custom_bounds_sync_guard = True
                self.var_custom_bounds.set(normalized)
            finally:
                self._custom_bounds_sync_guard = False

    def _get_custom_bounds(self) -> list[float]:
        """Hent manuelle strata-grenser fra UI."""
        bounds = parse_custom_strata_bounds(self.var_custom_bounds.get())
        return bounds

    def _stratify_remaining_values(self, values: pd.Series) -> tuple[list[tuple[Any, pd.Series]], dict[str, str], pd.DataFrame]:
        """Stratifiserer restpopulasjonen basert på valgt metode."""
        method = (self.var_method.get() or "quantile").strip().lower()
        if method == "custom":
            bounds = self._get_custom_bounds()
            return stratify_values_custom_bounds(values, bounds=bounds)

        k = int(self.var_k.get() or 1)
        return stratify_bilag_sums(values, method=method, k=k, use_abs=False)


    # --- refresh / recommendation -------------------------------------------------

    def _schedule_refresh(self, immediate: bool = False) -> None:
        if immediate:
            self._refresh_all()
            return

        # debounce
        if hasattr(self, "_refresh_after_id") and self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except Exception:
                pass
        self._refresh_after_id = self.after(200, self._refresh_all)

    def _refresh_all(self) -> None:
        # Apply filters and update base summary + recommendation
        self._df_filtered = self._apply_filters(self._df_base)

        try:
            base_metrics = compute_population_metrics(self._df_base)
            work_metrics = compute_population_metrics(self._df_filtered)
            text = build_population_summary_text(base_metrics, work_metrics, abs_basis=False)
        except Exception:
            text = "Ingen data lastet."
        self.var_base_summary.set(text)

        rec = self._compute_recommendation()
        self._update_recommendation_text(rec)
        # Vis en liten "spesifikk/rest" oppsummering under anbefalingen.
        # Viktig: Spesifikk utvelgelse baseres på |SumBeløp| >= tolererbar feil,
        # mens nettobeløp brukes som standard for populasjonsverdi.
        try:
            tol_abs = self._get_tolerable_error_value()
            if getattr(self, "_bilag_df", None) is not None and not self._bilag_df.empty:
                split_text = self._build_bilag_split_text(self._bilag_df, tolerable_error=tol_abs)
                if split_text:
                    current = self.var_recommendation.get()
                    self.var_recommendation.set(no_break_spaces_in_numbers((current + "\n\n" + split_text).strip()))
        except Exception:
            pass

        self._refresh_groups_table()

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bruk filter-parametre fra UI og returner filtrert DataFrame."""
        if df is None or df.empty:
            return pd.DataFrame()

        direction = (self.var_direction.get() or "Alle").strip()
        min_value = self.var_min_amount.get()
        max_value = self.var_max_amount.get()

        # Beløp fra/til: når retning=Alle er det mest intuitivt å filtrere på abs(netto).
        # For Kun debet/kredit bruker vi signert filter, siden retning allerede avgrenser fortegn.
        df_filtered, _summary = filter_selectionstudio_dataframe(
            df,
            direction=direction,
            min_value=min_value,
            max_value=max_value,
            use_abs=(direction == "Alle"),
        )
        return df_filtered

    def _build_bilag_split_text(self, bilag_df: pd.DataFrame, *, tolerable_error: float) -> str:
        """Bygg en kompakt tekst som viser populasjon/spesifikk/rest på bilag-nivå.

        Viktige prinsipper:
        - Spesifikk utvelgelse: |SumBeløp| >= tolererbar feil (alltid absolutt for terskel).
        - Populasjonsverdi: netto (signert) er standard i revisjon.
        - Utvalgsberegningen for tilfeldig trekk bruker |netto restpopulasjon|.
        """

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

    def _compute_recommendation(self) -> _Recommendation:
        # Compute bilag-level df
        self._bilag_df = self._build_bilag_df(self._df_filtered)

        tol = self._get_tolerable_error_value()

        # Confidence factor (risk + confidence)
        risk_level = (self.var_risk.get() or "Middels").strip().lower()
        conf_level = self._parse_confidence_percent(self.var_confidence.get())
        conf_factor = confidence_factor(risk_level=risk_level, confidence_level=conf_level)

        rec_dict = compute_net_basis_recommendation(
            self._bilag_df,
            tolerable_error=tol,
            confidence_factor=float(conf_factor),
            amount_col="SumBeløp",
        )
        n_specific = int(rec_dict["n_specific"])
        n_random = int(rec_dict["n_random"])
        n_total = int(rec_dict["n_total"])
        remaining_net = float(rec_dict["remaining_net"])

        # Update the sample size spinbox default behavior
        current_n = int(self.var_sample_n.get() or 0)
        if current_n == 0 or (self._last_suggested_n is not None and current_n == self._last_suggested_n):
            self.var_sample_n.set(n_total)
        self._last_suggested_n = n_total

        return _Recommendation(
            conf_factor=float(conf_factor),
            n_specific=n_specific,
            n_random_recommended=int(n_random),
            n_total_recommended=int(n_total),
            population_value_remaining=float(remaining_net),
        )

    def _update_recommendation_text(self, rec: _Recommendation) -> None:
        tol = self._get_tolerable_error_value()
        parts: list[str] = []
        if tol > 0:
            parts.append(f"Tolererbar feil: {fmt_amount_no(tol, decimals=0)}")
        if rec.conf_factor:
            parts.append(f"Konfidensfaktor: {str(rec.conf_factor).replace('.', ',')}")
        parts.append(
            f"Forslag utvalg: {fmt_int_no(rec.n_total_recommended)} bilag"
            + (f" (inkl. {fmt_int_no(rec.n_specific)} spesifikk)" if rec.n_specific else "")
        )
        self.var_recommendation.set(no_break_spaces_in_numbers("\n".join(parts)))

    def _refresh_groups_table(self) -> None:
        # Groups are shown for the remaining bilag (excluding specific)
        for i in self.tree_groups.get_children():
            self.tree_groups.delete(i)

        if self._bilag_df is None or self._bilag_df.empty:
            return

        tol = self._get_tolerable_error_value()
        # Spesifikk utvelgelse baseres alltid på |SumBeløp| >= tolererbar feil.
        spec, remaining = split_specific_selection_by_tolerable_error(self._bilag_df, tol, use_abs=True)
        if remaining.empty:
            # Only specific
            if not spec.empty:
                sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
                self.tree_groups.insert("", "end", values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)))
            return

        # Stratifisering gjøres på absolutt beløp (gir pene, positive intervaller)
        values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
        try:
            groups, interval_map, stats_df = self._stratify_remaining_values(values)
        except Exception:
            return

        # Insert optional specific group first
        if not spec.empty:
            sum_spec = float(pd.to_numeric(spec["SumBeløp"], errors="coerce").fillna(0.0).abs().sum())
            self.tree_groups.insert(
                "",
                "end",
                values=("Spesifikk", f">= {fmt_amount_no(tol, 0)}", len(spec), fmt_amount_no(sum_spec)),
            )

        # Stats per group
        # stats_df columns: Gruppe, Antall, Sum, Min, Max
        for _, row in stats_df.iterrows():
            grp = row.get("Gruppe")
            interval = interval_map.get(str(grp), "")
            self.tree_groups.insert(
                "",
                "end",
                values=(
                    str(grp),
                    interval,
                    int(row.get("Antall", 0)),
                    fmt_amount_no(float(row.get("Sum", 0.0))),
                ),
            )

    # --- selection ----------------------------------------------------------------

    def _run_selection(self) -> None:
        try:
            if self._df_filtered is None or self._df_filtered.empty:
                messagebox.showinfo("Utvalg", "Ingen data i grunnlaget. Velg konti/filtre først.")
                return

            bilag_df = self._bilag_df
            if bilag_df is None or bilag_df.empty:
                messagebox.showinfo("Utvalg", "Ingen bilag i grunnlaget.")
                return

            tol = self._get_tolerable_error_value()
            # Spesifikk utvelgelse baseres alltid på |SumBeløp| >= tolererbar feil.
            spec, remaining = split_specific_selection_by_tolerable_error(bilag_df, tol, use_abs=True)

            # Determine desired total sample size
            desired_total = int(self.var_sample_n.get() or 0)
            if desired_total <= 0:
                rec = self._compute_recommendation()
                desired_total = rec.n_total_recommended

            # Always include specific
            specific_ids = list(spec["Bilag"].tolist()) if not spec.empty else []
            desired_total = max(desired_total, len(specific_ids))

            n_random = desired_total - len(specific_ids)
            random_ids: list[Any] = []

            if n_random > 0 and not remaining.empty:
                random_ids = self._draw_stratified_sample(remaining, n_random)

            sample_ids_set = set(specific_ids) | set(random_ids)
            sample_df = bilag_df[bilag_df["Bilag"].isin(sample_ids_set)].copy()

            # Annotate sample with group/interval
            sample_df["Gruppe"] = ""
            sample_df["Intervall"] = ""
            if tol > 0 and not spec.empty:
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Gruppe"] = "Spesifikk"
                sample_df.loc[sample_df["Bilag"].isin(specific_ids), "Intervall"] = f">= {fmt_amount_no(tol, 0)}"

            # Fill for random using stratification intervals
            if random_ids:
                # Stratifisering gjøres på absolutt beløp (pene, positive intervaller)
                rem_values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
                groups, interval_map, _stats = self._stratify_remaining_values(rem_values)
                # Map bilag -> group
                group_by_idx = pd.Series(index=remaining.index, dtype=object)
                for grp_label, mask in groups:
                    group_by_idx.loc[mask[mask].index] = grp_label
                # Apply to sample
                for idx, grp_label in group_by_idx.items():
                    bilag_id = remaining.loc[idx, "Bilag"]
                    if bilag_id in sample_ids_set and bilag_id not in specific_ids:
                        sample_df.loc[sample_df["Bilag"] == bilag_id, "Gruppe"] = str(grp_label)
                        sample_df.loc[sample_df["Bilag"] == bilag_id, "Intervall"] = interval_map.get(str(grp_label), "")

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
        """Draw a stratified sample of bilag IDs from remaining_bilag_df."""

        if n <= 0 or remaining_bilag_df.empty:
            return []

        n = min(n, len(remaining_bilag_df))

        # Stratifisering gjøres på absolutt beløp (pene, positive intervaller)
        values = pd.to_numeric(remaining_bilag_df["SumBeløp"], errors="coerce").fillna(0.0).abs()

        groups, _interval_map, _stats = self._stratify_remaining_values(values)

        # Allocate n proportionally by stratum size
        sizes = [int(mask.sum()) for _g, mask in groups]
        total = sum(sizes) or 1
        raw_alloc = [n * s / total for s in sizes]
        alloc = [int(round(x)) for x in raw_alloc]

        # Fix rounding drift
        diff = n - sum(alloc)
        while diff != 0:
            # Adjust the largest strata first
            idx = max(range(len(alloc)), key=lambda i: sizes[i])
            if diff > 0:
                alloc[idx] += 1
                diff -= 1
            else:
                if alloc[idx] > 0:
                    alloc[idx] -= 1
                    diff += 1
                else:
                    break

        chosen: list[Any] = []
        for (grp_label, mask), take in zip(groups, alloc):
            if take <= 0:
                continue
            idxs = list(mask[mask].index)
            self._rng.shuffle(idxs)
            chosen.extend(remaining_bilag_df.loc[idxs[:take], "Bilag"].tolist())
        # If we still have too few due to empty strata, fill randomly
        if len(chosen) < n:
            remaining_ids = [x for x in remaining_bilag_df["Bilag"].tolist() if x not in set(chosen)]
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

            # Robust numerisk verdi + tag for negative beløp (kredit)
            try:
                sum_val = float(pd.to_numeric(sum_belop, errors="coerce"))
            except Exception:
                sum_val = 0.0
            if pd.isna(sum_val):
                sum_val = 0.0

            tags: tuple[str, ...] = ()
            if sum_val < 0:
                tags = ("neg",)

            self.tree.insert(
                "",
                "end",
                values=(
                    bilag,
                    str(dato)[:10] if pd.notna(dato) else "",
                    tekst,
                    fmt_amount_no(sum_val),
                    gruppe,
                    intervall,
                ),
                tags=tags,
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

        # Fyll inn et fornuftig standard filnavn så brukeren slipper å skrive det selv.
        default_name = f"Utvalg_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.xlsx"
        initialdir = getattr(self, "_last_export_dir", "") or ""

        path = filedialog.asksaveasfilename(
            title="Lagre Excel",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=default_name,
            initialdir=initialdir,
        )
        if not path:
            return

        # Husk sist brukte mappe (for neste eksport).
        try:
            self._last_export_dir = os.path.dirname(path)
        except Exception:
            pass

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

            values: List[Any] = [konto]
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

        # Bakoverkompatibilitet: vi prøver å sende med et "forhåndsvalg" hvis API-et støtter det,
        # men faller tilbake uten ekstra kwargs hvis signaturen ikke matcher.
        try:
            kwargs: dict[str, Any] = {
                "df_all": self._df_all,
                "bilag_col": "Bilag",
            }

            try:
                params = inspect.signature(_open_bilag_drill_dialog).parameters
                if "preset_bilag" in params:
                    kwargs["preset_bilag"] = bilag
                elif "bilag" in params:
                    kwargs["bilag"] = bilag
                elif "bilag_id" in params:
                    kwargs["bilag_id"] = bilag
                elif "selected_bilag" in params:
                    kwargs["selected_bilag"] = bilag
            except Exception:
                # Klarte ikke å inspisere signaturen; kjør uten forhåndsvalg.
                pass

            _open_bilag_drill_dialog(self, **kwargs)
        except TypeError:
            # Typisk: "unexpected keyword argument ..." – prøv uten forhåndsvalg.
            try:
                _open_bilag_drill_dialog(self, df_all=self._df_all, bilag_col="Bilag")
            except Exception as e:
                messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")
        except Exception as e:
            messagebox.showerror("Drilldown", f"Kunne ikke åpne drilldown.\n\n{e}")

    def _build_bilag_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Aggreger transaksjoner til bilag-nivå.

        Dette er et tynt wrapper rundt `build_bilag_dataframe`, men gjør det enklere
        å teste logikken separat.
        """
        return build_bilag_dataframe(df)
    def _parse_confidence_percent(self, s: str) -> float:
        s = (s or "90%").strip().replace("%", "")
        try:
            return float(s) / 100.0
        except Exception:
            return 0.90

    def _get_tolerable_error_value(self) -> float:
        """Return tolerable error as a number.

        parse_amount(...) kan returnere None (f.eks. tom streng). GUI-logikken
        forventer likevel et tall slik at vi kan sammenligne (>, <) uten å
        kræsje.
        """

        try:
            v = parse_amount(self.var_tolerable_error.get())
        except Exception:
            return 0.0
        return float(v) if v is not None else 0.0

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
    "no_break_spaces_in_numbers",
    # manual strata helpers
    "parse_custom_strata_bounds",
    "format_custom_strata_bounds",
    "stratify_values_custom_bounds",
    # legacy formatting aliases
    "format_amount_input_no",
    # new specific selection helpers
    "split_specific_selection_by_tolerable_error",
    "compute_specific_selection_recommendation",
    "recommend_random_sample_size_net_basis",
    "compute_net_basis_recommendation",
    "build_bilag_dataframe",
    "stratify_bilag_sums",
]


# --- extracted logic overrides (keep at end of module) ---
from selection_studio_bilag import build_bilag_dataframe, stratify_bilag_sums  # noqa: E402,F401
