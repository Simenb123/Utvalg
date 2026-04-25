from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import pandas as pd

from a07_feature.control.data import build_control_statement_export_df, filter_control_statement_df
from a07_feature.control.statement_model import normalize_control_statement_view
from a07_feature.page_a07_constants import CONTROL_STATEMENT_VIEW_PAYROLL, control_statement_view_requires_unclassified
from a07_feature.page_a07_frames import _empty_control_statement_df


BuildExportFn = Callable[..., pd.DataFrame]
FilterStatementFn = Callable[..., pd.DataFrame]


def build_rf1022_source_df(
    *,
    view: object | None,
    control_statement_base_df: pd.DataFrame | None,
    gl_df: pd.DataFrame | None,
    client: object,
    year: object,
    reconcile_df: pd.DataFrame | None,
    mapping_current: Mapping[str, str] | None,
    build_export_df: BuildExportFn = build_control_statement_export_df,
    filter_statement_df: FilterStatementFn = filter_control_statement_df,
) -> pd.DataFrame:
    """Build the RF-1022 source frame without touching Tk/page state."""
    view_key = normalize_control_statement_view(view or CONTROL_STATEMENT_VIEW_PAYROLL)
    if isinstance(control_statement_base_df, pd.DataFrame) and not control_statement_base_df.empty:
        return filter_statement_df(control_statement_base_df, view=view_key)
    if gl_df is None or gl_df.empty:
        return _empty_control_statement_df()

    client_s = str(client or "").strip()
    if not client_s:
        return _empty_control_statement_df()

    include_flag = control_statement_view_requires_unclassified(view_key)
    exported = build_export_df(
        client=client_s,
        year=year,
        gl_df=gl_df,
        reconcile_df=reconcile_df,
        mapping_current=dict(mapping_current or {}),
        include_unclassified=include_flag,
    )
    return filter_statement_df(exported, view=view_key)


__all__ = ["build_rf1022_source_df"]
