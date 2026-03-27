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
from consolidation.models import ConsolidationProject, RunResult

logger = logging.getLogger(__name__)


def run_consolidation(
    project: ConsolidationProject,
    company_tbs: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, RunResult]:
    """Kjoer en fullstendig konsolideringsrun.

    Args:
        project: Prosjektet med selskaper, mapping_config og elimineringer.
        company_tbs: Dict[company_id -> normalisert TB DataFrame].

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

    # --- 2. Map + aggreger hvert selskaps TB ---
    per_company_regnr: dict[str, dict[int, float]] = {}

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

        # Aggreger ub per regnr
        valid = mapped_df.dropna(subset=["regnr"]).copy()
        valid["regnr"] = valid["regnr"].astype(int)
        agg = valid.groupby("regnr")["ub"].sum()
        per_company_regnr[cid] = agg.to_dict()

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

    # --- 5. sum_foer_elim ---
    company_col_names = [company_names[cid] for cid in company_ids_used]
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
    numeric_cols = company_col_names + ["sum_foer_elim", "eliminering", "konsolidert"]
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

    # --- 11. RunResult ---
    run_result = RunResult(
        company_ids=company_ids_used,
        elimination_ids=[e.journal_id for e in project.eliminations],
        warnings=warnings,
        result_hash=result_hash,
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
