"""consolidation.engine -- Deterministisk konsolideringsmotor.

Tar et ConsolidationProject + selskapsgrunnlag og produserer en komplett
konsolidert regnskapsoppstilling med elimineringer.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pandas as pd

from .elimination import aggregate_eliminations_by_konto, aggregate_eliminations_by_regnr
from .line_basis_import import validate_company_line_basis
from .mapping import load_shared_config, map_company_tb
from .models import ConsolidationProject, CurrencyDetail, RunResult

logger = logging.getLogger(__name__)


def run_consolidation(
    project: ConsolidationProject,
    company_tbs: dict[str, pd.DataFrame],
    *,
    effective_overrides: dict[str, dict[str, int]] | None = None,
) -> tuple[pd.DataFrame, RunResult]:
    """Kjor en fullstendig konsolideringsrun."""
    from regnskap_mapping import compute_sumlinjer

    warnings: list[str] = []

    # --- 0. Last config en gang ---
    intervals, regnskapslinjer = load_shared_config()

    # --- 1. Sorter selskaper for determinisme ---
    companies_sorted = sorted(project.companies, key=lambda c: c.company_id)
    if not companies_sorted:
        raise ValueError("Prosjektet har ingen selskaper.")

    company_ids_used: list[str] = []
    company_names: dict[str, str] = {}

    regnr_to_name: dict[int, str] = {}
    for _, rl_row in regnskapslinjer.iterrows():
        regnr_to_name[int(rl_row["regnr"])] = str(rl_row.get("regnskapslinje", ""))

    per_company_regnr: dict[str, dict[int, float]] = {}
    currency_details: list[CurrencyDetail] = []
    account_detail_frames: list[pd.DataFrame] = []
    konto_to_regnr: dict[str, int] = {}  # for konto-nivå elimineringer

    for company in companies_sorted:
        cid = company.company_id
        basis_df = company_tbs.get(cid)
        if basis_df is None or basis_df.empty:
            warnings.append(f"Ingen grunnlagsdata lastet for {company.name} ({cid}) - hoppet over.")
            continue

        company_ids_used.append(cid)
        company_names[cid] = company.name

        if company.is_line_basis:
            mapped_df, line_warnings = validate_company_line_basis(
                basis_df,
                regnskapslinjer=regnskapslinjer,
            )
            for warning in line_warnings:
                warnings.append(f"{company.name}: {warning}")
        else:
            if effective_overrides is not None:
                overrides = effective_overrides.get(cid)
            else:
                overrides = project.mapping_config.company_overrides.get(cid)
            mapped_df, unmapped = map_company_tb(
                basis_df,
                overrides,
                intervals=intervals,
                regnskapslinjer=regnskapslinjer,
            )
            if unmapped:
                preview = ", ".join(unmapped[:10])
                suffix = "..." if len(unmapped) > 10 else ""
                warnings.append(
                    f"{company.name}: {len(unmapped)} umappede kontoer: {preview}{suffix}"
                )

        valid = mapped_df.dropna(subset=["regnr"]).copy()
        valid["regnr"] = valid["regnr"].astype(int)
        valid["ub_original"] = valid["ub"].copy()

        agg_before = valid.groupby("regnr")["ub"].sum()

        reporting = (project.reporting_currency or "NOK").upper()
        ccur = (company.currency_code or "").upper() or reporting
        needs_conversion = ccur != reporting and (company.closing_rate or company.average_rate)
        closing = company.closing_rate or 1.0
        average = company.average_rate or closing

        if needs_conversion:
            valid["ub"] = valid.apply(
                lambda row: row["ub"] * (average if row["regnr"] < 500 else closing),
                axis=1,
            )
            warnings.append(
                f"{company.name}: omregnet fra {ccur} "
                f"(snitt {average}, slutt {closing})"
            )

        agg = valid.groupby("regnr")["ub"].sum()
        per_company_regnr[cid] = agg.to_dict()

        # Collect konto → regnr mapping for konto-level eliminations
        if "konto" in valid.columns:
            for _, row in valid[["konto", "regnr"]].drop_duplicates().iterrows():
                k = str(row.get("konto") or "").strip()
                r = row.get("regnr")
                if k and pd.notna(r):
                    konto_to_regnr[k] = int(r)

        if company.is_line_basis:
            acct = valid.copy()
            acct["konto"] = ""
            acct["kontonavn"] = acct["source_regnskapslinje"].where(
                acct["source_regnskapslinje"].astype(str).str.strip().ne(""),
                acct["regnskapslinje"],
            )
            acct["ib"] = 0.0
            acct["netto"] = 0.0
            if needs_conversion:
                acct["ub"] = acct.apply(
                    lambda row: row["ub_original"] * (average if int(row["regnr"]) < 500 else closing),
                    axis=1,
                )
            acct["selskap"] = company.name
            acct["valuta"] = ccur
            acct["kursregel"] = acct["regnr"].map(
                lambda r: "Snittkurs" if int(r) < 500 else "Sluttkurs"
            )
            acct["kurs"] = acct["regnr"].map(
                lambda r: (average if int(r) < 500 else closing) if needs_conversion else 1.0
            )
            acct_cols = [
                "konto",
                "kontonavn",
                "regnr",
                "regnskapslinje",
                "ib",
                "netto",
                "ub_original",
                "ub",
                "selskap",
                "valuta",
                "kursregel",
                "kurs",
                "source_regnskapslinje",
                "source_page",
                "source_text",
                "confidence",
                "review_status",
            ]
            account_detail_frames.append(
                acct[[c for c in acct_cols if c in acct.columns]].copy()
            )
        else:
            all_acct = mapped_df.copy()
            all_acct["ub_original"] = all_acct["ub"].copy()
            has_regnr = all_acct["regnr"].notna()
            if needs_conversion:
                all_acct.loc[has_regnr, "ub"] = all_acct.loc[has_regnr].apply(
                    lambda row: row["ub_original"] * (average if int(row["regnr"]) < 500 else closing),
                    axis=1,
                )
            acct_cols = ["konto", "kontonavn", "regnr", "ib", "netto", "ub_original", "ub"]
            acct = all_acct[[c for c in acct_cols if c in all_acct.columns]].copy()
            acct["selskap"] = company.name
            acct["valuta"] = ccur
            acct["regnskapslinje"] = acct["regnr"].map(
                lambda r: "" if pd.isna(r) else regnr_to_name.get(int(r), "")
            )
            acct["kursregel"] = acct["regnr"].map(
                lambda r: "" if pd.isna(r) else ("Snittkurs" if int(r) < 500 else "Sluttkurs")
            )
            acct["kurs"] = acct["regnr"].map(
                lambda r: 1.0 if pd.isna(r) else ((average if int(r) < 500 else closing) if needs_conversion else 1.0)
            )
            account_detail_frames.append(acct)

        for regnr_val, amount_before in agg_before.items():
            regnr_int = int(regnr_val)
            is_result = regnr_int < 500
            rate_used = average if is_result else closing
            if not needs_conversion:
                rate_used = 1.0
            amount_after = float(agg.get(regnr_val, 0.0))
            currency_details.append(
                CurrencyDetail(
                    company_id=cid,
                    company_name=company.name,
                    currency=ccur,
                    regnr=regnr_int,
                    regnskapslinje=regnr_to_name.get(regnr_int, ""),
                    line_type="Resultat" if is_result else "Balanse",
                    amount_before=float(amount_before),
                    rate=rate_used,
                    rate_rule="Snittkurs" if is_result else "Sluttkurs",
                    amount_after=amount_after,
                )
            )

    if not company_ids_used:
        raise ValueError("Ingen gyldige TB-er eller regnskapslinjer funnet for noen selskaper.")

    skeleton = regnskapslinjer[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    skeleton["regnr"] = skeleton["regnr"].astype(int)
    result = skeleton.copy()

    leaf_mask = ~result["sumpost"]

    for cid in company_ids_used:
        col_name = company_names[cid]
        regnr_vals = per_company_regnr[cid]
        result[col_name] = result["regnr"].map(
            lambda r, rv=regnr_vals: rv.get(int(r), 0.0)
        )
        result.loc[result["sumpost"], col_name] = 0.0

    company_col_names = [company_names[cid] for cid in company_ids_used]

    parent_id = project.parent_company_id or ""
    parent_col = company_names.get(parent_id, "")
    child_cols = [cn for cid, cn in company_names.items() if cid != parent_id]

    if parent_col:
        result["Mor"] = result[parent_col]
    else:
        result["Mor"] = 0.0

    result["Doetre"] = 0.0
    if child_cols:
        result.loc[leaf_mask, "Doetre"] = result.loc[leaf_mask, child_cols].sum(axis=1)

    result["sum_foer_elim"] = 0.0
    result.loc[leaf_mask, "sum_foer_elim"] = result.loc[
        leaf_mask, company_col_names
    ].sum(axis=1)

    elim_by_regnr = aggregate_eliminations_by_regnr(project.eliminations)

    # Aggregate konto-level eliminations up to regnr level
    elim_by_konto = aggregate_eliminations_by_konto(project.eliminations)
    if elim_by_konto:
        for konto, amount in elim_by_konto.items():
            regnr_mapped = konto_to_regnr.get(konto)
            if regnr_mapped is not None:
                elim_by_regnr[regnr_mapped] = elim_by_regnr.get(regnr_mapped, 0.0) + amount
            else:
                warnings.append(
                    f"Konto-eliminering for konto {konto} ({amount:.2f}) har ingen regnr-mapping."
                )

    result["eliminering"] = result["regnr"].map(
        lambda r: elim_by_regnr.get(int(r), 0.0)
    )
    result.loc[result["sumpost"], "eliminering"] = 0.0

    for j in project.eliminations:
        if not j.is_balanced:
            warnings.append(
                f"Elimineringsjournal '{j.display_label}' er ikke balansert (netto {j.net:.2f})."
            )

    result["konsolidert"] = 0.0
    result.loc[leaf_mask, "konsolidert"] = (
        result.loc[leaf_mask, "sum_foer_elim"]
        + result.loc[leaf_mask, "eliminering"]
    )

    numeric_cols = company_col_names + ["Mor", "Doetre", "sum_foer_elim", "eliminering", "konsolidert"]
    for col in numeric_cols:
        base_values = {
            int(r): float(v)
            for r, v in zip(
                result.loc[leaf_mask, "regnr"],
                result.loc[leaf_mask, col],
            )
        }
        all_values = compute_sumlinjer(
            base_values=base_values,
            regnskapslinjer=regnskapslinjer,
        )
        sum_mask = result["sumpost"]
        result.loc[sum_mask, col] = result.loc[sum_mask, "regnr"].map(
            lambda r, av=all_values: float(av.get(int(r), 0.0))
        )

    result = result.sort_values("regnr").reset_index(drop=True)
    result_hash = _compute_result_hash(result, company_ids_used)

    if account_detail_frames:
        account_details = pd.concat(account_detail_frames, ignore_index=True)
    else:
        account_details = None

    run_result = RunResult(
        company_ids=company_ids_used,
        elimination_ids=[e.journal_id for e in project.eliminations],
        warnings=warnings,
        result_hash=result_hash,
        currency_details=currency_details,
        account_details=account_details,
    )

    logger.info(
        "Consolidation run %s: %d companies, %d eliminations, hash=%s",
        run_result.run_id,
        len(company_ids_used),
        len(project.eliminations),
        result_hash[:16],
    )

    return result, run_result


def _compute_result_hash(
    result_df: pd.DataFrame,
    company_ids: list[str],
) -> str:
    """SHA256 over resultatet for reproduserbarhetsverifisering."""
    h = hashlib.sha256()
    h.update(json.dumps(company_ids, sort_keys=True).encode("utf-8"))
    csv_bytes = result_df.to_csv(index=False).encode("utf-8")
    h.update(csv_bytes)
    return h.hexdigest()
