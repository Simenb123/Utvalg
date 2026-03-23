"""Selection Studio widget: sampling/selection logic.

The functions in this module implement the "run selection" behaviour:
- Always include specific selection (|SumBeløp| >= tolerable error)
- Draw the remaining bilag stratified
- Populate the result tree

They are separated from the Tkinter view file so that we can keep the main
module small.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from tkinter import messagebox

from .helpers import fmt_amount_no
from .ui_logic import split_specific_selection_by_tolerable_error


def build_bilag_df(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transactions to bilag-level dataframe."""

    # Local import to avoid any potential import cycles.
    from .bilag import build_bilag_dataframe

    return build_bilag_dataframe(df)


def run_selection(studio: Any) -> None:
    """Execute selection based on current UI state and populate result."""

    try:
        # Force a synchronous refresh so the selection always uses the latest
        # values from the UI, even if the user clicks "Kjør utvalg" before the
        # debounced refresh has fired.
        if hasattr(studio, "_refresh_all"):
            studio._refresh_all()

        if studio._df_filtered is None or studio._df_filtered.empty:
            messagebox.showinfo("Utvalg", "Ingen data i grunnlaget. Velg konti/filtre først.")
            return

        bilag_df = studio._bilag_df
        if bilag_df is None or bilag_df.empty:
            messagebox.showinfo("Utvalg", "Ingen bilag i grunnlaget.")
            return

        tol = studio._get_tolerable_error_value()
        # Specific selection based on |SumBeløp| >= tolerable error
        spec, remaining = split_specific_selection_by_tolerable_error(bilag_df, tol, use_abs=True)

        # Determine desired total sample size
        desired_total = int(studio.var_sample_n.get() or 0)
        if desired_total <= 0:
            rec = studio._compute_recommendation()
            desired_total = rec.n_total_recommended

        # Always include specific
        specific_ids = list(spec["Bilag"].tolist()) if not spec.empty else []
        desired_total = max(desired_total, len(specific_ids))

        available_total = int(len(bilag_df))
        if desired_total > available_total:
            messagebox.showwarning(
                "Utvalg",
                f"Beløpsfilter/filtrering gir bare {available_total} bilag i trekkgrunnlaget, "
                f"men ønsket utvalg er {desired_total}. Programmet vil trekke maks {available_total} bilag.",
            )

        n_random = desired_total - len(specific_ids)
        random_ids: list[Any] = []

        if n_random > 0 and not remaining.empty:
            random_ids = studio._draw_stratified_sample(remaining, n_random)

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
            rem_values = pd.to_numeric(remaining["SumBeløp"], errors="coerce").fillna(0.0).abs()
            groups, interval_map, _stats = studio._stratify_remaining_values(rem_values)

            # Map remaining rows -> group label
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
        sample_df = (
            sample_df.assign(_abs_sort=amounts_sort.abs())
            .sort_values("_abs_sort", ascending=False)
            .drop(columns=["_abs_sort"])
        )

        studio._df_sample = sample_df
        studio._populate_tree(sample_df)
        studio.nb.select(0)

    except Exception as e:
        messagebox.showerror("Utvalg", f"Kunne ikke kjøre utvalg.\n\n{e}")


def draw_stratified_sample(studio: Any, remaining_bilag_df: pd.DataFrame, n: int) -> list[Any]:
    """Draw a stratified sample of bilag IDs from remaining_bilag_df."""

    if n <= 0 or remaining_bilag_df.empty:
        return []

    n = min(n, len(remaining_bilag_df))

    values = pd.to_numeric(remaining_bilag_df["SumBeløp"], errors="coerce").fillna(0.0).abs()
    groups, _interval_map, _stats = studio._stratify_remaining_values(values)

    # Allocate n proportionally by stratum size
    sizes = [int(mask.sum()) for _g, mask in groups]
    total = sum(sizes) or 1
    raw_alloc = [n * s / total for s in sizes]
    alloc = [int(round(x)) for x in raw_alloc]

    # Fix rounding drift
    diff = n - sum(alloc)
    while diff != 0:
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
        studio._rng.shuffle(idxs)
        chosen.extend(remaining_bilag_df.loc[idxs[:take], "Bilag"].tolist())

    # If we still have too few due to empty strata, fill randomly
    if len(chosen) < n:
        remaining_ids = [x for x in remaining_bilag_df["Bilag"].tolist() if x not in set(chosen)]
        studio._rng.shuffle(remaining_ids)
        chosen.extend(remaining_ids[: n - len(chosen)])

    return chosen[:n]


def populate_tree(studio: Any, df: pd.DataFrame) -> None:
    """Fill the sample Treeview."""

    for i in studio.tree.get_children():
        studio.tree.delete(i)

    if df is None or df.empty:
        return

    for _, row in df.iterrows():
        bilag = row.get("Bilag", "")
        dato = row.get("Dato", "")
        tekst = row.get("Tekst", "")
        sum_belop = row.get("SumBeløp", 0.0)
        gruppe = row.get("Gruppe", "")
        intervall = row.get("Intervall", "")

        # Robust numeric value + tag for negative amount (credit)
        try:
            sum_val = float(pd.to_numeric(sum_belop, errors="coerce"))
        except Exception:
            sum_val = 0.0
        if pd.isna(sum_val):
            sum_val = 0.0

        tags: tuple[str, ...] = ()
        if sum_val < 0:
            tags = ("neg",)

        studio.tree.insert(
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
