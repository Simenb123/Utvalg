"""page_consolidation_view.py - thin detail/result view facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

import page_consolidation_detail as _detail_ctx
import page_consolidation_result as _result_ctx

if TYPE_CHECKING:
    from page_consolidation import ConsolidationPage


def populate_grunnlag(
    page: "ConsolidationPage",
    regnr: int,
    *,
    is_sumpost: bool = False,
    fmt_no,
) -> None:
    return _detail_ctx.populate_grunnlag(page, regnr, is_sumpost=is_sumpost, fmt_no=fmt_no)


def configure_detail_tree_columns(
    page: "ConsolidationPage",
    *,
    line_basis: bool,
    detail_tb_column_specs,
    detail_line_column_specs,
) -> None:
    return _detail_ctx.configure_detail_tree_columns(
        page,
        line_basis=line_basis,
        detail_tb_column_specs=detail_tb_column_specs,
        detail_line_column_specs=detail_line_column_specs,
    )


def show_company_detail(
    page: "ConsolidationPage",
    company_id: str,
    *,
    build_detail_meta_text,
) -> None:
    return _detail_ctx.show_company_detail(
        page,
        company_id,
        build_detail_meta_text=build_detail_meta_text,
    )


def populate_detail_tree(
    page: "ConsolidationPage",
    tb: pd.DataFrame,
    company_id: str,
    *,
    fmt_no,
    format_count_label,
    format_filtered_count_label,
) -> None:
    return _detail_ctx.populate_detail_tree(
        page,
        tb,
        company_id,
        fmt_no=fmt_no,
        format_count_label=format_count_label,
        format_filtered_count_label=format_filtered_count_label,
    )


def populate_line_basis_detail_tree(
    page: "ConsolidationPage",
    basis: pd.DataFrame,
    *,
    fmt_no,
    format_count_label,
    format_filtered_count_label,
) -> None:
    return _detail_ctx.populate_line_basis_detail_tree(
        page,
        basis,
        fmt_no=fmt_no,
        format_count_label=format_count_label,
        format_filtered_count_label=format_filtered_count_label,
    )


def on_detail_filter_changed(page: "ConsolidationPage") -> None:
    return _detail_ctx.on_detail_filter_changed(page)


def build_company_result(page: "ConsolidationPage", company_id: str) -> None:
    return _result_ctx.build_company_result(page, company_id)


def on_result_mode_changed(page: "ConsolidationPage") -> None:
    return _result_ctx.on_result_mode_changed(page)


def fx_cols_active(page: "ConsolidationPage") -> tuple[bool, bool, bool]:
    return _result_ctx.fx_cols_active(page)


def refresh_result_view(page: "ConsolidationPage") -> None:
    return _result_ctx.refresh_result_view(page)


def ensure_consolidated_fx_cols(
    page: "ConsolidationPage",
    *,
    show_before: bool,
    show_effect: bool,
) -> pd.DataFrame:
    return _result_ctx.ensure_consolidated_fx_cols(
        page,
        show_before=show_before,
        show_effect=show_effect,
    )


def get_per_company_columns(
    page: "ConsolidationPage",
    df: pd.DataFrame | None = None,
) -> list[str]:
    return _result_ctx.get_per_company_columns(page, df)


def show_empty_result(page: "ConsolidationPage", message: str = "") -> None:
    return _result_ctx.show_empty_result(page, message)


def reset_result_tree_display_state(page: "ConsolidationPage") -> None:
    return _result_ctx.reset_result_tree_display_state(page)


def populate_result_tree(
    page: "ConsolidationPage",
    result_df: pd.DataFrame,
    *,
    data_cols: list[str] | None = None,
    fmt_no,
    append_control_rows_fn,
    enable_treeview_sorting_fn,
    kurs_cols,
) -> None:
    return _result_ctx.populate_result_tree(
        page,
        result_df,
        data_cols=data_cols,
        fmt_no=fmt_no,
        append_control_rows_fn=append_control_rows_fn,
        enable_treeview_sorting_fn=enable_treeview_sorting_fn,
        kurs_cols=kurs_cols,
    )


def show_result(page: "ConsolidationPage", result_df: pd.DataFrame) -> None:
    return _result_ctx.show_result(page, result_df)


def ensure_consolidated_result(page: "ConsolidationPage") -> bool:
    return _result_ctx.ensure_consolidated_result(page)


def on_show_unmapped(page: "ConsolidationPage") -> None:
    return _result_ctx.on_show_unmapped(page)
