"""Readiness- og snapshot-kontroller for konsolidering."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Any

import pandas as pd

import regnskap_client_overrides
import session


BALANCE_TOLERANCE = 1.0


@dataclass(frozen=True)
class ReadinessIssue:
    severity: str
    category: str
    message: str
    action: str = ""
    company_id: str = ""
    company_name: str = ""
    action_target: str = ""


@dataclass
class ReadinessReport:
    issues: list[ReadinessIssue] = field(default_factory=list)
    input_digest: str = ""
    last_run_digest: str = ""

    @property
    def blockers(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "blocking")

    @property
    def warnings(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def infos(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "info")

    @property
    def is_stale(self) -> bool:
        return bool(self.input_digest) and self.input_digest != (self.last_run_digest or "")


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


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
                "currency_code": company.currency_code,
                "closing_rate": _safe_float(company.closing_rate),
                "average_rate": _safe_float(company.average_rate),
                "tb_digest": _df_digest(
                    effective_tbs.get(company.company_id),
                    columns=["konto", "kontonavn", "ib", "ub", "netto"],
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
        "eliminations": eliminations,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_col(df: pd.DataFrame, *candidates: str) -> str:
    normalized = {str(col).strip().lower(): col for col in df.columns}
    for candidate in candidates:
        key = candidate.strip().lower()
        if key in normalized:
            return str(normalized[key])
    return ""


def _build_unmapped_issues(page: Any, tbs: dict[str, pd.DataFrame]) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    if project is None:
        return issues
    unmapped = getattr(page, "_mapping_unmapped", {}) or {}
    for company in project.companies:
        missing = [str(k).strip() for k in unmapped.get(company.company_id, []) if str(k).strip()]
        if not missing:
            continue
        tb = tbs.get(company.company_id)
        if tb is None or tb.empty:
            continue
        konto_col = _find_col(tb, "konto")
        ub_col = _find_col(tb, "ub")
        if not konto_col or not ub_col:
            continue
        details: list[str] = []
        for _, row in tb.iterrows():
            konto = str(row.get(konto_col, "") or "").strip()
            if konto not in missing:
                continue
            ub = _safe_float(row.get(ub_col, 0.0))
            if abs(ub) <= 0.005:
                continue
            details.append(f"{konto} ({ub:,.0f})")
        if not details:
            continue
        preview = ", ".join(details[:3])
        suffix = f" +{len(details) - 3} til" if len(details) > 3 else ""
        issues.append(
            ReadinessIssue(
                severity="blocking",
                category="mapping",
                company_id=company.company_id,
                company_name=company.name,
                action="open_mapping",
                message=f"{company.name}: {len(details)} kontoer med verdi mangler regnskapslinje ({preview}{suffix})",
            )
        )
    return issues


def _build_mapping_review_issues(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    review_details = getattr(page, "_mapping_review_details", {}) or {}
    if project is None:
        return issues
    for company in project.companies:
        details = [str(v).strip() for v in review_details.get(company.company_id, []) if str(v).strip()]
        if not details:
            continue
        preview = ", ".join(details[:2])
        suffix = f" +{len(details) - 2} til" if len(details) > 2 else ""
        issues.append(
            ReadinessIssue(
                severity="blocking",
                category="mapping",
                company_id=company.company_id,
                company_name=company.name,
                action="open_mapping",
                message=f"{company.name}: {len(details)} kontoer har mistenkelig mapping ({preview}{suffix})",
            )
        )
    return issues



def _build_parent_mapping_deviation_issues(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    details = [
        str(v).strip()
        for v in getattr(page, "_parent_mapping_deviation_details", []) or []
        if str(v).strip()
    ]
    if project is None or not details:
        return issues
    preview = ", ".join(details[:2])
    suffix = f" +{len(details) - 2} til" if len(details) > 2 else ""
    issues.append(
        ReadinessIssue(
            severity="warning",
            category="mapping",
            company_id=project.parent_company_id or "",
            company_name="",
            action="open_mapping",
            message=(
                f"Mor har {len(details)} lokale konsoliderings-overstyringer som avviker fra Analyse "
                f"({preview}{suffix})"
            ),
        )
    )
    return issues

def _build_sumline_warnings(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    regnskapslinjer = getattr(page, "_regnskapslinjer", None)
    mapped_tbs = getattr(page, "_mapped_tbs", {}) or {}
    if project is None or regnskapslinjer is None or getattr(regnskapslinjer, "empty", True):
        return issues
    try:
        from regnskap_mapping import normalize_regnskapslinjer

        regn = normalize_regnskapslinjer(regnskapslinjer)
        sumlines = {
            int(row["regnr"]): str(row.get("regnskapslinje", "") or "")
            for _, row in regn.loc[regn["sumpost"]].iterrows()
            if pd.notna(row.get("regnr"))
        }
    except Exception:
        return issues
    for company in project.companies:
        mapped = mapped_tbs.get(company.company_id)
        if mapped is None or mapped.empty or "regnr" not in mapped.columns:
            continue
        work = mapped.copy()
        ub_col = _find_col(work, "ub")
        if ub_col:
            work[ub_col] = pd.to_numeric(work[ub_col], errors="coerce").fillna(0.0)
        else:
            work["_ub"] = 0.0
            ub_col = "_ub"
        for regnr, name in sumlines.items():
            rows = work.loc[work["regnr"].fillna(-1).astype(int) == regnr]
            amount = float(pd.to_numeric(rows.get(ub_col), errors="coerce").fillna(0.0).sum()) if not rows.empty else 0.0
            if abs(amount) <= 0.005:
                continue
            issues.append(
                ReadinessIssue(
                    severity="warning",
                    category="mapping",
                    company_id=company.company_id,
                    company_name=company.name,
                    action="open_mapping",
                    message=f"{company.name}: verdi mappet til sumpost {regnr} {name}",
                )
            )
            break
    return issues


def _build_balance_issues(page: Any, tbs: dict[str, pd.DataFrame]) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    if project is None:
        return issues
    for company in project.companies:
        tb = tbs.get(company.company_id)
        if tb is None or tb.empty:
            continue
        ub_col = _find_col(tb, "ub")
        if not ub_col:
            continue
        total = float(pd.to_numeric(tb[ub_col], errors="coerce").fillna(0.0).sum())
        if abs(total) <= BALANCE_TOLERANCE:
            continue
        issues.append(
            ReadinessIssue(
                severity="blocking",
                category="balance",
                company_id=company.company_id,
                company_name=company.name,
                action="open_grunnlag",
                message=f"{company.name}: saldobalanse er ikke i balanse (diff {total:,.2f})",
            )
        )
    return issues


def _build_fx_issues(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    if project is None:
        return issues
    reporting = (project.reporting_currency or "NOK").strip().upper() or "NOK"
    for company in project.companies:
        currency = (company.currency_code or reporting).strip().upper() or reporting
        if currency == reporting:
            continue
        closing = _safe_float(company.closing_rate)
        average = _safe_float(company.average_rate)
        if closing <= 0 or average <= 0:
            issues.append(
                ReadinessIssue(
                    severity="blocking",
                    category="fx",
                    company_id=company.company_id,
                    company_name=company.name,
                    action="open_valuta",
                    message=f"{company.name}: mangler gyldige valutakurser for {currency}",
                )
            )
    return issues


def _build_ao_issues(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    include_ao_var = getattr(page, "_include_ao_var", None)
    if project is None or include_ao_var is None:
        return issues
    try:
        include_ao = bool(include_ao_var.get())
    except Exception:
        include_ao = False
    client = getattr(session, "client", None) or ""
    year = getattr(session, "year", None) or ""
    if not client or not year:
        return issues
    entries = regnskap_client_overrides.load_supplementary_entries(client, str(year))
    if not entries:
        return issues
    total = sum(_safe_float(entry.get("belop", 0.0)) for entry in entries)
    if not include_ao:
        issues.append(
            ReadinessIssue(
                severity="warning",
                category="ao",
                company_id=project.parent_company_id or "",
                company_name="",
                action="open_grunnlag",
                message=(
                    f"AO finnes for mor ({len(entries)} posteringer, netto {total:,.2f}), "
                    "men Inkl. AO (mor) er av"
                ),
            )
        )
        return issues
    issues.append(
        ReadinessIssue(
            severity="info",
            category="ao",
            company_id=project.parent_company_id or "",
            company_name="",
            action="open_grunnlag",
            message=f"AO aktiv for mor: {len(entries)} posteringer (netto {total:,.2f})",
        )
    )
    return issues


def _build_elimination_issues(page: Any) -> list[ReadinessIssue]:
    issues: list[ReadinessIssue] = []
    project = getattr(page, "_project", None)
    if project is None:
        return issues
    for journal in project.eliminations:
        if journal.is_balanced:
            continue
        issues.append(
            ReadinessIssue(
                severity="warning",
                category="elimination",
                action="open_elimination",
                action_target=journal.journal_id,
                message=f"{journal.display_label}: elimineringsjournal er ikke balansert ({journal.net:,.2f})",
            )
        )
    return issues


def _build_report_balance_issue(page: Any) -> list[ReadinessIssue]:
    result_df = getattr(page, "_result_df", None)
    if result_df is None or not isinstance(result_df, pd.DataFrame) or result_df.empty:
        return []
    line_col = _find_col(result_df, "regnskapslinje")
    value_col = _find_col(result_df, "konsolidert")
    if not line_col or not value_col:
        return []
    work = result_df[[line_col, value_col]].copy()
    work[value_col] = pd.to_numeric(work[value_col], errors="coerce").fillna(0.0)
    normalized = work[line_col].fillna("").astype(str).str.strip().str.lower()
    assets = work.loc[normalized.eq("sum eiendeler"), value_col]
    eqdebt = work.loc[
        normalized.str.contains("sum egenkapital", regex=False)
        & normalized.str.contains("gjeld", regex=False),
        value_col,
    ]
    if assets.empty or eqdebt.empty:
        return [
            ReadinessIssue(
                severity="warning",
                category="balance",
                action="open_grunnlag",
                message="Oppstillingsbalanse kan ikke verifiseres mot Sum eiendeler og Sum egenkapital og gjeld",
            )
        ]
    diff = abs(abs(float(assets.iloc[0])) - abs(float(eqdebt.iloc[0])))
    if diff <= BALANCE_TOLERANCE:
        return []
    return [
        ReadinessIssue(
            severity="warning",
            category="balance",
            action="open_grunnlag",
            message=f"Oppstillingsbalanse avviker (diff {diff:,.2f})",
        )
    ]


def build_readiness_report(page: Any) -> ReadinessReport:
    project = getattr(page, "_project", None)
    if project is None:
        return ReadinessReport()

    try:
        tbs = page._get_effective_tbs()
    except Exception:
        tbs = {}
    current_digest = compute_input_digest(page)
    last_run = getattr(page, "_last_run_result", None)
    if last_run is None and getattr(project, "runs", None):
        try:
            last_run = project.runs[-1]
        except Exception:
            last_run = None
    last_digest = str(getattr(last_run, "input_digest", "") or "")

    issues: list[ReadinessIssue] = []
    issues.extend(_build_unmapped_issues(page, tbs))
    issues.extend(_build_mapping_review_issues(page))
    issues.extend(_build_parent_mapping_deviation_issues(page))
    issues.extend(_build_sumline_warnings(page))
    issues.extend(_build_balance_issues(page, tbs))
    issues.extend(_build_fx_issues(page))
    issues.extend(_build_ao_issues(page))
    issues.extend(_build_elimination_issues(page))
    issues.extend(_build_report_balance_issue(page))

    if not last_digest:
        issues.append(
            ReadinessIssue(
                severity="blocking",
                category="stale",
                action="rerun",
                message="Ingen gyldig konsolideringskjøring finnes ennå",
            )
        )
    elif current_digest and current_digest != last_digest:
        issues.append(
            ReadinessIssue(
                severity="blocking",
                category="stale",
                action="rerun",
                message="Resultatet er utdatert etter endringer i grunnlaget",
            )
        )

    return ReadinessReport(
        issues=issues,
        input_digest=current_digest,
        last_run_digest=last_digest,
    )


def summarize_report(report: ReadinessReport) -> str:
    if not report.issues:
        return "Kontroller: OK"
    parts: list[str] = []
    if report.blockers:
        parts.append(f"{report.blockers} blokk.")
    if report.warnings:
        parts.append(f"{report.warnings} advarsler")
    if report.infos:
        parts.append(f"{report.infos} info")
    if report.is_stale:
        parts.append("utdatert run")
    return "Kontroller: " + " | ".join(parts)
