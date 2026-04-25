"""Run/export helpers for the consolidation page."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

try:
    from tkinter import filedialog, messagebox
except Exception:  # pragma: no cover
    filedialog = None  # type: ignore
    messagebox = None  # type: ignore

from consolidation import storage
from .common import fmt_no, is_line_basis_company

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)


def on_ao_toggled(page: "ConsolidationPage") -> None:
    page._invalidate_run_cache()
    page._compute_mapping_status()
    page._refresh_company_tree()
    cid = getattr(page, "_current_detail_cid", None)
    if cid:
        page._show_company_detail(cid)


def invalidate_run_cache(page: "ConsolidationPage") -> None:
    page._result_df = None
    page._consolidated_result_df = None
    page._company_result_df = None
    page._preview_result_df = None
    page._last_run_result = None
    try:
        page._refresh_readiness()
    except Exception:
        pass


def rerun_consolidation(page: "ConsolidationPage") -> None:
    page._invalidate_run_cache()
    if page._project is not None and page._project.companies and page._company_tbs:
        page._on_run()


def on_run(page: "ConsolidationPage") -> None:
    if page._project is None:
        messagebox.showwarning("Konsolidering", "Ingen prosjekt. Importer minst ett selskap.")
        return
    if len(page._project.companies) < 1:
        messagebox.showwarning("Konsolidering", "Importer minst ett selskap foerst.")
        return

    page._compute_mapping_status()

    from ..backend import readiness as consolidation_readiness
    from consolidation.engine import run_consolidation
    from consolidation.mapping import ConfigNotLoadedError

    try:
        preflight = consolidation_readiness.build_readiness_report(page)
    except Exception:
        preflight = None
    if preflight is not None:
        blockers = [
            issue
            for issue in getattr(preflight, "issues", []) or []
            if str(getattr(issue, "severity", "") or "") == "blocking"
            and str(getattr(issue, "category", "") or "") != "stale"
        ]
        if blockers:
            preview = "\n".join(f"- {getattr(issue, 'message', '')}" for issue in blockers[:5])
            if len(blockers) > 5:
                preview += f"\n... og {len(blockers) - 5} til"
            proceed = messagebox.askyesno(
                "Konsolideringskontroller",
                "Det finnes blokkere i grunnlaget som kan gi ufullstendig eller feil konsolidering:\n\n"
                f"{preview}\n\nVil du kjoere likevel?",
            )
            if not proceed:
                page._select_left_tab(1, "_left_tab_controls")
                return

    tbs = page._prepare_tbs_for_run()
    eff_overrides = {company.company_id: page._get_effective_company_overrides(company.company_id) for company in page._project.companies}
    try:
        result_df, run_result = run_consolidation(page._project, tbs, effective_overrides=eff_overrides)
    except ConfigNotLoadedError as exc:
        messagebox.showerror("Konfigurasjon mangler", str(exc))
        return
    except ValueError as exc:
        messagebox.showerror("Feil", str(exc))
        return
    except Exception as exc:
        logger.exception("Konsolidering feilet")
        messagebox.showerror("Feil", f"Konsolidering feilet:\n{exc}")
        return

    try:
        run_result.input_digest = consolidation_readiness.compute_input_digest(page)
    except Exception:
        run_result.input_digest = ""

    page._result_df = result_df
    page._last_run_result = run_result
    page._project.runs.append(run_result)
    storage.save_project(page._project)

    warnings = list(run_result.warnings) + build_unmapped_warnings(page, tbs)
    if warnings:
        messagebox.showwarning("Advarsler", "\n".join(warnings))
    page._show_result(result_df)
    page._update_status()


def build_unmapped_warnings(page: "ConsolidationPage", tbs: dict[str, pd.DataFrame]) -> list[str]:
    warnings: list[str] = []
    if page._project is None:
        return warnings
    for company in page._project.companies:
        if is_line_basis_company(company):
            continue
        unmapped_kontos = page._mapping_unmapped.get(company.company_id, [])
        if not unmapped_kontos:
            continue
        tb = tbs.get(company.company_id)
        if tb is None or tb.empty:
            continue
        col_konto = next((col for col in tb.columns if col.lower() == "konto"), None)
        col_ub = next((col for col in tb.columns if col.lower() == "ub"), None)
        if col_konto is None or col_ub is None:
            continue
        parts: list[str] = []
        total_missing = 0.0
        unmapped_set = {str(konto) for konto in unmapped_kontos}
        for _, row in tb.iterrows():
            konto = str(row.get(col_konto, "")).strip()
            if konto not in unmapped_set:
                continue
            try:
                ub = float(row.get(col_ub, 0.0) or 0.0)
            except (TypeError, ValueError):
                ub = 0.0
            if abs(ub) > 0.005:
                parts.append(f"{konto} ({fmt_no(ub, 0)})")
                total_missing += ub
        if parts:
            preview = ", ".join(parts[:5])
            suffix = f" +{len(parts) - 5} til" if len(parts) > 5 else ""
            warnings.append(
                f"{company.name}: {len(parts)} umappede kontoer med beloep (sum {fmt_no(total_missing, 0)}): {preview}{suffix}"
            )
    return warnings


def prepare_tbs_for_run(page: "ConsolidationPage") -> dict[str, pd.DataFrame]:
    return page._get_effective_tbs()


def on_export(page: "ConsolidationPage") -> None:
    if page._result_df is None or page._project is None:
        messagebox.showwarning("Eksport", "Kjoer konsolidering foerst.")
        return

    stale = False
    try:
        from ..backend import readiness as consolidation_readiness
        stale = consolidation_readiness.build_readiness_report(page).is_stale
    except Exception:
        stale = page._consolidated_result_df is None

    if stale:
        ans = messagebox.askyesno(
            "Utdatert resultat",
            "Data har endret seg siden siste konsolidering.\nVil du kjoere konsolidering paa nytt foer eksport?",
        )
        if not ans:
            return
        page._rerun_consolidation()
        try:
            from ..backend import readiness as consolidation_readiness
            stale = consolidation_readiness.build_readiness_report(page).is_stale
        except Exception:
            stale = page._result_df is None
        if page._result_df is None or stale:
            return

    from consolidation.export import save_consolidation_workbook

    path = filedialog.asksaveasfilename(
        title="Eksporter konsolidering",
        defaultextension=".xlsx",
        filetypes=[("Excel", "*.xlsx")],
        initialfile=f"konsolidering_{page._project.client}_{page._project.year}.xlsx",
    )
    if not path:
        return

    run_result = getattr(page, "_last_run_result", None)
    if run_result is None and page._project.runs:
        run_result = page._project.runs[-1]
    if run_result is None:
        return

    try:
        out = save_consolidation_workbook(
            path,
            result_df=page._result_df,
            companies=page._project.companies,
            eliminations=page._project.eliminations,
            mapped_tbs=page._mapped_tbs,
            run_result=run_result,
            client=page._project.client,
            year=page._project.year,
            parent_company_id=page._project.parent_company_id or "",
            regnr_to_name=page._regnr_to_name,
            hide_zero=page._hide_zero_var.get(),
            associate_cases=getattr(page._project, "associate_cases", []),
        )
        messagebox.showinfo("Eksport", f"Lagret til:\n{out}")
    except Exception as exc:
        logger.exception("Export failed")
        messagebox.showerror("Eksportfeil", str(exc))
