"""Helpers for synthetic control rows in consolidation views/export."""

from __future__ import annotations

from typing import Iterable

import pandas as pd

META_COLS = {"regnr", "regnskapslinje", "sumpost", "formel"}
KURS_COLS = {"Kurs"}

_CONTROL_SPECS = (
    (
        9010,
        "Kontroll eiendeler / EK + Gjeld",
        665,
        850,
    ),
    (
        9020,
        "Kontroll Årsresultat / Sum overføringer",
        280,
        350,
    ),
)


def amount_columns(df: pd.DataFrame, extra_excludes: Iterable[str] = ()) -> list[str]:
    """Return numeric-ish amount columns, excluding metadata and rate columns."""
    excludes = set(extra_excludes) | META_COLS | KURS_COLS
    return [c for c in df.columns if c not in excludes]


def append_control_rows(
    result_df: pd.DataFrame | None,
    *,
    amount_cols: Iterable[str] | None = None,
) -> pd.DataFrame | None:
    """Append balance/disposition control rows to a result DataFrame.

    The helper is intentionally display/export-oriented and leaves the original
    frame untouched. Control rows are added at the bottom using synthetic
    `regnr` values so they never collide with ordinary regnskapslinjer.
    """
    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return result_df
    if "regnr" not in result_df.columns or "regnskapslinje" not in result_df.columns:
        return result_df

    work = result_df.copy()
    cols = list(amount_cols) if amount_cols is not None else amount_columns(work)
    if not cols:
        return work

    numeric = work.copy()
    for col in cols:
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce").fillna(0.0)

    by_regnr = {
        int(regnr): row
        for _, row in numeric.iterrows()
        if pd.notna(row.get("regnr"))
        for regnr in [int(row["regnr"])]
    }

    control_rows: list[dict[str, object]] = []
    for synthetic_regnr, label, regnr_a, regnr_b in _CONTROL_SPECS:
        row_a = by_regnr.get(regnr_a)
        row_b = by_regnr.get(regnr_b)
        if row_a is None or row_b is None:
            continue
        row: dict[str, object] = {
            "regnr": synthetic_regnr,
            "regnskapslinje": label,
            "sumpost": True,
            "formel": "",
        }
        for col in cols:
            row[col] = float(row_a.get(col, 0.0) or 0.0) + float(row_b.get(col, 0.0) or 0.0)
        control_rows.append(row)

    if len(control_rows) == 2:
        sum_row: dict[str, object] = {
            "regnr": 9030,
            "regnskapslinje": "Sumkontroll",
            "sumpost": True,
            "formel": "",
        }
        for col in cols:
            sum_row[col] = float(control_rows[0].get(col, 0.0) or 0.0) + float(
                control_rows[1].get(col, 0.0) or 0.0
            )
        control_rows.append(sum_row)

    if not control_rows:
        return work

    control_df = pd.DataFrame(control_rows)
    for col in work.columns:
        if col not in control_df.columns:
            control_df[col] = None
    control_df = control_df[work.columns]
    return pd.concat([work, control_df], ignore_index=True)
