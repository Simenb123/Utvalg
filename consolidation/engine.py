"""consolidation.engine -- Deterministisk konsolideringsmotor.

Tar et ConsolidationProject + raa TBer og produserer en komplett
konsolidert regnskapsoppstilling med elimineringer.
"""

from __future__ import annotations

import hashlib
import json
import logging

import pandas as pd

from consolidation.elimination import aggregate_eliminations_by_regnr
from consolidation.mapping import load_shared_config, map_company_tb
from consolidation.models import ConsolidationProject, CurrencyDetail, RunResult

logger = logging.getLogger(__name__)


def run_consolidation(
    project: ConsolidationProject,
    company_tbs: dict[str, pd.DataFrame],
    *,
    effective_overrides: dict[str, dict[str, int]] | None = None,
) -> tuple[pd.DataFrame, RunResult]:
    """Kjoer en fullstendig konsolideringsrun.

    Args:
        project: Prosjektet med selskaper, mapping_config og elimineringer.
        company_tbs: Dict[company_id -> normalisert TB DataFrame].
        effective_overrides: Valgfri: ferdigberegnede overstyringer per selskap
            (inkl. Analyse-overrides for parent). Hvis None brukes
            project.mapping_config.company_overrides direkte.

    Returns:
        (result_df, run_result)

    Raises:
        ConfigNotLoadedError: Hvis regnskap-konfigurasjon mangler.
        ValueError: Hvis ingen selskaper er med.
    """
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
    companies_by_id = {c.company_id: c for c in companies_sorted}

    # regnr -> regnskapslinje name lookup
    regnr_to_name: dict[int, str] = {}
    for _, rl_row in regnskapslinjer.iterrows():
        regnr_to_name[int(rl_row["regnr"])] = str(rl_row.get("regnskapslinje", ""))

    # --- 2. Map + aggreger hvert selskaps TB ---
    per_company_regnr: dict[str, dict[int, float]] = {}
    currency_details: list[CurrencyDetail] = []
    account_detail_frames: list[pd.DataFrame] = []

    for company in companies_sorted:
        cid = company.company_id
        tb = company_tbs.get(cid)
        if tb is None or tb.empty:
            warnings.append(
                f"Ingen TB lastet for {company.name} ({cid}) — hoppet over."
            )
            continue

        company_ids_used.append(cid)
        company_names[cid] = company.name

        if effective_overrides is not None:
            overrides = effective_overrides.get(cid)
        else:
            overrides = project.mapping_config.company_overrides.get(cid)
        mapped_df, unmapped = map_company_tb(
            tb,
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

        # Aggreger ub per regnr, med eventuell valutakonvertering
        valid = mapped_df.dropna(subset=["regnr"]).copy()
        valid["regnr"] = valid["regnr"].astype(int)

        # Save original UB before currency conversion
        valid["ub_original"] = valid["ub"].copy()

        # Aggregate original amounts per regnr (before currency conversion)
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

        # Build per-account detail rows for flat export (all accounts, incl. unmapped)
        all_acct = mapped_df.copy()
        all_acct["ub_original"] = all_acct["ub"].copy()
        # Apply currency conversion to mapped rows only
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

        def _rl_name(r):
            if pd.isna(r):
                return ""
            return regnr_to_name.get(int(r), "")
        acct["regnskapslinje"] = acct["regnr"].map(_rl_name)

        def _kursregel(r):
            if pd.isna(r):
                return ""
            return "Snittkurs" if int(r) < 500 else "Sluttkurs"
        acct["kursregel"] = acct["regnr"].map(_kursregel)

        def _kurs(r):
            if pd.isna(r):
                return 1.0
            return (average if int(r) < 500 else closing) if needs_conversion else 1.0
        acct["kurs"] = acct["regnr"].map(_kurs)

        # For unmapped rows: no conversion, ub stays = ub_original
        account_detail_frames.append(acct)

        # Build currency control rows for this company (regnr-level)
        for regnr_val, amount_before in agg_before.items():
            regnr_int = int(regnr_val)
            is_result = regnr_int < 500
            rate_used = average if is_result else closing
            if not needs_conversion:
                rate_used = 1.0
            amount_after = float(agg.get(regnr_val, 0.0))
            currency_details.append(CurrencyDetail(
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
            ))

    if not company_ids_used:
        raise ValueError("Ingen gyldige TB-er funnet for noen selskaper.")

    # --- 3. Bygg skeleton fra regnskapslinjer ---
    skeleton = regnskapslinjer[["regnr", "regnskapslinje", "sumpost", "formel"]].copy()
    skeleton["regnr"] = skeleton["regnr"].astype(int)
    result = skeleton.copy()

    # --- 4. Fyll selskapsverdier (kun leaf-linjer) ---
    leaf_mask = ~result["sumpost"]

    for cid in company_ids_used:
        col_name = company_names[cid]
        regnr_vals = per_company_regnr[cid]
        result[col_name] = result["regnr"].map(
            lambda r, rv=regnr_vals: rv.get(int(r), 0.0)
        )
        result.loc[result["sumpost"], col_name] = 0.0

    company_col_names = [company_names[cid] for cid in company_ids_used]

    # --- 5. Mor / Doetre aggregering ---
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

    # sum_foer_elim (kept for backwards compat / export)
    result["sum_foer_elim"] = 0.0
    result.loc[leaf_mask, "sum_foer_elim"] = result.loc[
        leaf_mask, company_col_names
    ].sum(axis=1)

    # --- 6. Elimineringer ---
    elim_by_regnr = aggregate_eliminations_by_regnr(project.eliminations)
    result["eliminering"] = result["regnr"].map(
        lambda r: elim_by_regnr.get(int(r), 0.0)
    )
    result.loc[result["sumpost"], "eliminering"] = 0.0

    # Advarsel for ubalanserte journaler
    for j in project.eliminations:
        if not j.is_balanced:
            warnings.append(
                f"Elimineringsjournal '{j.name}' er ikke balansert (netto {j.net:.2f})."
            )

    # --- 7. Konsolidert ---
    result["konsolidert"] = 0.0
    result.loc[leaf_mask, "konsolidert"] = (
        result.loc[leaf_mask, "sum_foer_elim"]
        + result.loc[leaf_mask, "eliminering"]
    )

    # --- 8. Beregn sumlinjer for alle numeriske kolonner ---
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

    # --- 9. Sorter ---
    result = result.sort_values("regnr").reset_index(drop=True)

    # --- 10. Hash ---
    result_hash = _compute_result_hash(result, company_ids_used)

    # --- 11. Build flat account details ---
    if account_detail_frames:
        account_details = pd.concat(account_detail_frames, ignore_index=True)
    else:
        account_details = None

    # --- 12. RunResult ---
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
    """SHA256 over resultatet for reproduserbarheitsverifisering."""
    h = hashlib.sha256()
    h.update(json.dumps(company_ids, sort_keys=True).encode("utf-8"))
    csv_bytes = result_df.to_csv(index=False).encode("utf-8")
    h.update(csv_bytes)
    return h.hexdigest()
