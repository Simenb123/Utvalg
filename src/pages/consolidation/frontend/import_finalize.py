"""Finalize and persistence helpers for consolidation imports."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from ..backend.models import CompanyTB

if TYPE_CHECKING:
    from .page import ConsolidationPage


def ensure_line_import_config(page: "ConsolidationPage", *, messagebox_module) -> bool:
    if page._regnskapslinjer is not None:
        return True
    try:
        from ..backend.mapping import load_shared_config

        intervals, regnskapslinjer = load_shared_config()
        page._intervals = intervals
        page._regnskapslinjer = regnskapslinjer
        page._regnr_to_name = {
            int(row["regnr"]): str(row.get("regnskapslinje", ""))
            for _, row in regnskapslinjer.iterrows()
        }
        return True
    except Exception as exc:
        messagebox_module.showerror("Konfigurasjon mangler", str(exc))
        return False


def finalize_import(
    page: "ConsolidationPage",
    df: pd.DataFrame,
    name: str,
    source_path: Path,
    *,
    existing_company: CompanyTB | None = None,
    source_type: str | None = None,
    source_file: str | None = None,
    storage_module,
    tb_import_module,
    messagebox_module,
) -> CompanyTB:
    from ..backend.tb_import import _normalize_columns, validate_tb

    df = _normalize_columns(df)
    warnings = validate_tb(df)
    has_ib = bool((df["ib"].abs() > 0.005).any()) if "ib" in df.columns else False

    proj = page._ensure_project()
    resolved_source_type = source_type or (
        "excel" if source_path.suffix.lower() in (".xlsx", ".xlsm", ".xls") else "csv"
    )
    resolved_source_file = str(source_file or source_path.name)

    company = existing_company
    if company is None:
        company = CompanyTB(
            name=name,
            source_file=resolved_source_file,
            source_type=resolved_source_type,
            basis_type="tb",
            row_count=len(df),
            has_ib=has_ib,
        )
        proj.companies.append(company)
    else:
        company.name = name
        company.source_file = resolved_source_file
        company.source_type = resolved_source_type
        company.basis_type = "tb"
        company.row_count = len(df)
        company.has_ib = has_ib

    getattr(page, "_company_line_bases", {}).pop(company.company_id, None)
    storage_module.delete_company_line_basis(proj.client, proj.year, company.company_id)
    page._company_tbs[company.company_id] = df
    storage_module.save_company_tb(proj.client, proj.year, company.company_id, df)
    storage_module.save_project(proj)
    if hasattr(page, "_invalidate_run_cache"):
        try:
            page._invalidate_run_cache()
        except Exception:
            pass
    page._compute_mapping_status()
    page._refresh_company_tree()
    page._update_status()
    page._select_and_show_company(company.company_id)

    if warnings:
        messagebox_module.showwarning("Import-advarsler", "\n".join(warnings))
    return company


def finalize_line_basis_import(
    page: "ConsolidationPage",
    df: pd.DataFrame,
    name: str,
    source_path: Path,
    *,
    source_type: str,
    existing_company: CompanyTB | None = None,
    storage_module,
    messagebox_module,
) -> None:
    from ..backend.line_basis_import import validate_company_line_basis

    if not ensure_line_import_config(page, messagebox_module=messagebox_module):
        return
    assert page._regnskapslinjer is not None

    normalized, warnings = validate_company_line_basis(df, regnskapslinjer=page._regnskapslinjer)

    proj = page._ensure_project()
    company = existing_company
    if company is None:
        company = CompanyTB(
            name=name,
            source_file=source_path.name,
            source_type=source_type,
            basis_type="regnskapslinje",
            row_count=len(normalized),
            has_ib=False,
        )
        proj.companies.append(company)
    else:
        company.name = name
        company.source_file = source_path.name
        company.source_type = source_type
        company.basis_type = "regnskapslinje"
        company.row_count = len(normalized)
        company.has_ib = False

    page._company_line_bases[company.company_id] = normalized
    page._company_tbs.pop(company.company_id, None)
    proj.mapping_config.company_overrides.pop(company.company_id, None)
    storage_module.delete_company_tb(proj.client, proj.year, company.company_id)
    storage_module.save_company_line_basis(proj.client, proj.year, company.company_id, normalized)
    storage_module.save_project(proj)
    page._compute_mapping_status()
    page._refresh_company_tree()
    page._update_status()
    page._select_and_show_company(company.company_id)

    if warnings:
        messagebox_module.showwarning("Import-advarsler", "\n".join(warnings))

