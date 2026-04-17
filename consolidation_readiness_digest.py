"""Digest helpers for consolidation readiness checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd


BALANCE_TOLERANCE = 1.0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _normalize_entity_name(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _df_digest(df: pd.DataFrame | None, columns: list[str] | None = None) -> str:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return ""
    work = df.copy()
    if columns:
        keep = [c for c in columns if c in work.columns]
        if keep:
            work = work[keep].copy()
    for col in work.columns:
        work[col] = work[col].map(lambda v: "" if pd.isna(v) else str(v))
    work = work.sort_values(list(work.columns), kind="mergesort", ignore_index=True)
    raw = work.to_json(orient="split", force_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_input_digest(page: Any) -> str:
    project = getattr(page, "_project", None)
    if project is None:
        return ""

    try:
        effective_tbs = page._get_effective_tbs()
    except Exception:
        effective_tbs = {}

    companies = []
    for company in sorted(project.companies, key=lambda c: c.company_id):
        try:
            eff_overrides = page._get_effective_company_overrides(company.company_id)
        except Exception:
            eff_overrides = {}
        companies.append(
            {
                "company_id": company.company_id,
                "name": company.name,
                "basis_type": getattr(company, "basis_type", "tb"),
                "currency_code": company.currency_code,
                "closing_rate": _safe_float(company.closing_rate),
                "average_rate": _safe_float(company.average_rate),
                "tb_digest": _df_digest(
                    effective_tbs.get(company.company_id),
                    columns=["konto", "kontonavn", "ib", "ub", "netto"],
                ),
                "line_basis_digest": _df_digest(
                    getattr(page, "_company_line_bases", {}).get(company.company_id),
                    columns=[
                        "regnr",
                        "regnskapslinje",
                        "ub",
                        "source_regnskapslinje",
                        "source_page",
                        "source_text",
                        "confidence",
                        "review_status",
                    ],
                ),
                "overrides": sorted(
                    [(str(k), int(v)) for k, v in (eff_overrides or {}).items()],
                    key=lambda item: item[0],
                ),
            }
        )

    eliminations = []
    for journal in sorted(project.eliminations, key=lambda j: j.journal_id):
        eliminations.append(
            {
                "journal_id": journal.journal_id,
                "voucher_no": int(journal.voucher_no or 0),
                "label": journal.display_label,
                "name": journal.name,
                "status": journal.status,
                "kind": journal.kind,
                "locked": bool(getattr(journal, "locked", False)),
                "source_associate_case_id": str(getattr(journal, "source_associate_case_id", "") or ""),
                "generation_hash": str(getattr(journal, "generation_hash", "") or ""),
                "lines": [
                    {
                        "regnr": int(line.regnr),
                        "company_id": line.company_id,
                        "amount": _safe_float(line.amount),
                        "description": line.description,
                    }
                    for line in journal.lines
                ],
            }
        )

    associate_cases = []
    for case in sorted(getattr(project, "associate_cases", []) or [], key=lambda item: item.case_id):
        associate_cases.append(
            {
                "case_id": case.case_id,
                "name": case.name,
                "investor_company_id": case.investor_company_id,
                "ownership_pct": _safe_float(case.ownership_pct),
                "status": case.status,
                "source_mode": case.source_mode,
                "line_mapping": {
                    str(k): int(v)
                    for k, v in dict(case.line_mapping or {}).items()
                    if str(k).strip()
                },
                "journal_id": case.journal_id,
                "generation_hash": case.generation_hash,
                "last_generated_at": _safe_float(case.last_generated_at),
                "acquisition_date": case.acquisition_date,
                "opening_carrying_amount": _safe_float(case.opening_carrying_amount),
                "share_of_result": _safe_float(case.share_of_result),
                "share_of_other_equity": _safe_float(case.share_of_other_equity),
                "dividends": _safe_float(case.dividends),
                "impairment": _safe_float(case.impairment),
                "excess_value_amortization": _safe_float(case.excess_value_amortization),
                "manual_adjustment_rows": [
                    {
                        "row_id": row.row_id,
                        "label": row.label,
                        "amount": _safe_float(row.amount),
                        "offset_regnr": int(row.offset_regnr or 0),
                        "description": row.description,
                    }
                    for row in getattr(case, "manual_adjustment_rows", []) or []
                ],
            }
        )

    payload = {
        "project_id": project.project_id,
        "client": project.client,
        "year": project.year,
        "parent_company_id": project.parent_company_id,
        "reporting_currency": project.reporting_currency,
        "match_tolerance_nok": _safe_float(project.match_tolerance_nok),
        "include_ao": bool(getattr(page, "_include_ao_var", None).get()) if getattr(page, "_include_ao_var", None) is not None else False,
        "intervals_digest": _df_digest(getattr(page, "_intervals", None), columns=["fra", "til", "regnr"]),
        "regnskapslinjer_digest": _df_digest(
            getattr(page, "_regnskapslinjer", None),
            columns=["regnr", "regnskapslinje", "sumpost", "formel", "delsumnr", "sumnr", "sumnr2", "sluttsumnr"],
        ),
        "companies": companies,
        "associate_cases": associate_cases,
        "eliminations": eliminations,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
