"""consolidation.export -- Excel export for consolidation."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from openpyxl import Workbook

from .export_company_sheets import (
    build_associate_sheets as _build_associate_sheets_impl,
    build_company_sheets as _build_company_sheets_impl,
    build_elimineringer as _build_elimineringer_impl,
)
from .export_control_sheets import (
    build_kontrollark as _build_kontrollark_impl,
    build_saldobalanse_alle as _build_saldobalanse_alle_impl,
    build_valutakontroll as _build_valutakontroll_impl,
)
from .export_main_sheet import (
    build_konsolidert_sb as _build_konsolidert_sb_impl,
    build_konsernoppstilling as _build_konsernoppstilling_impl,
)
from .models import AssociateCase, CompanyTB, EliminationJournal, RunResult

logger = logging.getLogger(__name__)


def _excel_col(idx: int) -> str:
    result = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def _safe_float(val: object) -> float:
    if val is None:
        return 0.0
    try:
        f = float(val)
        return 0.0 if pd.isna(f) else f
    except (ValueError, TypeError):
        return 0.0


def _build_konsernoppstilling(*args, **kwargs) -> None:
    _build_konsernoppstilling_impl(*args, **kwargs)


def _build_elimineringer(*args, **kwargs) -> None:
    _build_elimineringer_impl(*args, **kwargs)


def _build_company_sheets(*args, **kwargs) -> None:
    _build_company_sheets_impl(*args, **kwargs)


def _build_associate_sheets(*args, **kwargs) -> None:
    _build_associate_sheets_impl(*args, **kwargs)


def _build_valutakontroll(*args, **kwargs) -> None:
    _build_valutakontroll_impl(*args, **kwargs)


def _build_saldobalanse_alle(*args, **kwargs) -> None:
    _build_saldobalanse_alle_impl(*args, **kwargs)


def _build_konsolidert_sb(*args, **kwargs) -> None:
    _build_konsolidert_sb_impl(*args, **kwargs)


def _build_kontrollark(*args, **kwargs) -> None:
    _build_kontrollark_impl(*args, **kwargs)


def build_consolidation_workbook(
    result_df: pd.DataFrame,
    companies: list[CompanyTB],
    eliminations: list[EliminationJournal],
    mapped_tbs: dict[str, pd.DataFrame],
    run_result: RunResult,
    *,
    client: str | None = None,
    year: str | None = None,
    parent_company_id: str = "",
    regnr_to_name: dict[int, str] | None = None,
    hide_zero: bool = False,
    associate_cases: list[AssociateCase] | None = None,
) -> Workbook:
    """Build the complete consolidation workbook."""
    wb = Workbook()

    _build_konsernoppstilling(
        wb,
        result_df,
        client=client,
        year=year,
        companies=companies,
        parent_company_id=parent_company_id,
        hide_zero=hide_zero,
    )
    company_names = {c.company_id: c.name for c in companies}
    _build_elimineringer(wb, eliminations, company_names=company_names)
    companies_sorted = sorted(
        companies,
        key=lambda c: (0 if c.company_id == parent_company_id else 1, c.name),
    )
    _build_company_sheets(
        wb,
        companies_sorted,
        mapped_tbs,
        regnr_to_name=regnr_to_name,
        hide_zero=hide_zero,
    )
    _build_associate_sheets(
        wb,
        associate_cases or [],
        eliminations,
        company_names=company_names,
        regnr_to_name=regnr_to_name or {},
    )
    _build_valutakontroll(wb, run_result.currency_details)
    _build_saldobalanse_alle(wb, run_result.account_details)
    _build_konsolidert_sb(
        wb,
        result_df,
        companies=companies_sorted,
        parent_company_id=parent_company_id,
        eliminations=eliminations,
    )
    _build_kontrollark(wb, run_result, companies, eliminations, client=client, year=year)

    return wb


def save_consolidation_workbook(
    path: str | Path,
    *,
    result_df: pd.DataFrame,
    companies: list[CompanyTB],
    eliminations: list[EliminationJournal],
    mapped_tbs: dict[str, pd.DataFrame],
    run_result: RunResult,
    client: str | None = None,
    year: str | None = None,
    parent_company_id: str = "",
    regnr_to_name: dict[int, str] | None = None,
    hide_zero: bool = False,
    associate_cases: list[AssociateCase] | None = None,
) -> str:
    """Build and save the workbook. Returns the file path."""
    wb = build_consolidation_workbook(
        result_df,
        companies,
        eliminations,
        mapped_tbs,
        run_result,
        client=client,
        year=year,
        parent_company_id=parent_company_id,
        regnr_to_name=regnr_to_name,
        hide_zero=hide_zero,
        associate_cases=associate_cases,
    )
    p = Path(path)
    if p.suffix.lower() != ".xlsx":
        p = p.with_suffix(".xlsx")
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(p))
    logger.info("Saved consolidation workbook -> %s", p)
    return str(p)
