"""page_consolidation_mapping_state.py - mapping and basis helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from .session import _is_line_basis_company

if TYPE_CHECKING:
    from .page import ConsolidationPage

logger = logging.getLogger(__name__)

_MAPPING_REVIEW_KEYWORDS = (
    "dispon",
    "disposition",
    "dividend",
    "udbytte",
    "utbytte",
    "egenkap",
    "equity",
    "Ã¥rets resultat",
    "aarets resultat",
    "arets resultat",
)


def _normalize_mapping_text(value: object) -> str:
    text = str(value or "").strip().lower()
    return (
        text.replace("Ã¦", "ae")
        .replace("Ã¸", "oe")
        .replace("Ã¥", "aa")
        .replace("Ã£Â¦", "ae")
        .replace("Ã£Â¸", "oe")
        .replace("Ã£Â¥", "aa")
    )


def _detect_mapping_review_accounts(
    mapped_df: pd.DataFrame,
    regnr_to_name: dict[int, str],
) -> tuple[set[str], list[str]]:
    review_accounts: set[str] = set()
    review_details: list[str] = []
    if mapped_df is None or mapped_df.empty:
        return review_accounts, review_details

    for _, row in mapped_df.iterrows():
        regnr_raw = row.get("regnr")
        try:
            regnr = int(regnr_raw) if pd.notna(regnr_raw) and str(regnr_raw).strip() not in ("", "nan") else None
        except (ValueError, TypeError):
            regnr = None
        if regnr is None or regnr >= 295:
            continue

        konto = str(row.get("konto", "") or "").strip()
        kontonavn = str(row.get("kontonavn", "") or "").strip()
        if not konto:
            continue

        ib = pd.to_numeric(pd.Series([row.get("ib", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        ub = pd.to_numeric(pd.Series([row.get("ub", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        netto = pd.to_numeric(pd.Series([row.get("netto", 0.0)]), errors="coerce").fillna(0.0).iloc[0]
        if abs(float(ib)) <= 0.005 and abs(float(ub)) <= 0.005 and abs(float(netto)) <= 0.005:
            continue

        name_norm = _normalize_mapping_text(kontonavn)
        if not any(keyword in name_norm for keyword in _MAPPING_REVIEW_KEYWORDS):
            continue

        review_accounts.add(konto)
        rl_name = str(row.get("regnskapslinje", "") or regnr_to_name.get(regnr, "") or "")
        review_details.append(f"{konto} {kontonavn} -> {regnr} {rl_name}".strip())

    return review_accounts, review_details


def load_analyse_parent_overrides(page: "ConsolidationPage") -> dict[str, int]:
    if page._project is None:
        return {}
    try:
        import regnskap_client_overrides

        return regnskap_client_overrides.load_account_overrides(
            page._project.client,
            year=page._project.year,
        )
    except Exception:
        return {}


def get_parent_override_deviation_details(page: "ConsolidationPage") -> list[str]:
    if page._project is None:
        return []

    parent_id = page._project.parent_company_id or ""
    if not parent_id:
        return []

    analyse = page._load_analyse_parent_overrides()
    local_parent = page._project.mapping_config.company_overrides.get(parent_id, {}) or {}
    details: list[str] = []
    for konto, local_regnr in sorted(local_parent.items(), key=lambda item: str(item[0])):
        analyse_regnr = analyse.get(str(konto))
        if analyse_regnr == local_regnr:
            continue
        analyse_label = str(analyse_regnr) if analyse_regnr is not None else "Analyse: ingen"
        details.append(f"{konto}: {analyse_label} / Konsolidering {local_regnr}")
    return details


def get_effective_company_overrides(page: "ConsolidationPage", company_id: str) -> dict[str, int]:
    if page._project is None:
        return {}

    if company_id == page._project.parent_company_id:
        return dict(page._load_analyse_parent_overrides())

    return dict(page._project.mapping_config.company_overrides.get(company_id, {}))


def get_effective_company_tb(page: "ConsolidationPage", company_id: str) -> pd.DataFrame | None:
    tb = getattr(page, "_company_tbs", {}).get(company_id)
    if isinstance(tb, pd.DataFrame):
        columns = {str(col).strip() for col in tb.columns}
        if not {"konto", "kontonavn", "ib", "ub", "netto"}.issubset(columns):
            try:
                from ..backend.tb_import import _normalize_columns

                tb = _normalize_columns(tb.copy())
            except Exception:
                pass
    if tb is None or page._project is None:
        return tb

    if not page._include_ao_var.get():
        return tb
    if company_id != page._project.parent_company_id:
        return tb

    try:
        import regnskap_client_overrides
        import tilleggsposteringer

        ao_entries = regnskap_client_overrides.load_supplementary_entries(
            page._project.client,
            page._project.year,
        )
        if not ao_entries:
            return tb
        adjusted = tilleggsposteringer.apply_to_sb(tb.copy(), ao_entries)
        logger.info("Applied %d AO entries to parent %s", len(ao_entries), company_id)
        return adjusted
    except Exception:
        logger.exception("Failed to apply AO entries for %s", company_id)
        return tb


def get_effective_company_basis(page: "ConsolidationPage", company_id: str) -> pd.DataFrame | None:
    if page._project is None:
        if company_id in getattr(page, "_company_line_bases", {}):
            return getattr(page, "_company_line_bases", {}).get(company_id)
        return page._get_effective_company_tb(company_id)

    company = page._project.find_company(company_id)
    if company is None:
        return None
    if _is_line_basis_company(company):
        return getattr(page, "_company_line_bases", {}).get(company_id)
    return page._get_effective_company_tb(company_id)


def get_effective_tbs(page: "ConsolidationPage") -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    project = getattr(page, "_project", None)
    if project is None:
        return result

    companies = getattr(project, "companies", None)
    if isinstance(companies, (list, tuple)):
        for company in companies:
            effective_basis = page._get_effective_company_basis(company.company_id)
            if effective_basis is not None:
                result[company.company_id] = effective_basis
        return result

    fallback_ids = list(
        dict.fromkeys(
            [
                *getattr(page, "_company_tbs", {}).keys(),
                *getattr(page, "_company_line_bases", {}).keys(),
            ]
        )
    )
    for company_id in fallback_ids:
        effective_basis = page._get_effective_company_basis(company_id)
        if effective_basis is None:
            if company_id in getattr(page, "_company_line_bases", {}):
                effective_basis = getattr(page, "_company_line_bases", {}).get(company_id)
            else:
                effective_basis = page._get_effective_company_tb(company_id)
        if effective_basis is not None:
            result[company_id] = effective_basis
    return result


def compute_mapping_status(page: "ConsolidationPage") -> None:
    if not hasattr(page, "_mapping_review_accounts") or page._mapping_review_accounts is None:
        page._mapping_review_accounts = {}
    if not hasattr(page, "_mapping_review_details") or page._mapping_review_details is None:
        page._mapping_review_details = {}
    if not hasattr(page, "_mapping_unmapped") or page._mapping_unmapped is None:
        page._mapping_unmapped = {}
    if not hasattr(page, "_mapping_pct") or page._mapping_pct is None:
        page._mapping_pct = {}
    if not hasattr(page, "_mapped_tbs") or page._mapped_tbs is None:
        page._mapped_tbs = {}

    page._mapped_tbs.clear()
    page._mapping_pct = {}
    page._mapping_unmapped = {}
    page._mapping_review_accounts.clear()
    page._mapping_review_details.clear()
    page._parent_mapping_deviation_details = []

    if page._project is None:
        return

    try:
        from ..backend.mapping import load_shared_config, map_company_tb

        intervals, regnskapslinjer = load_shared_config()
        page._intervals = intervals
        page._regnskapslinjer = regnskapslinjer
        page._regnr_to_name = {
            int(row["regnr"]): str(row.get("regnskapslinje", ""))
            for _, row in regnskapslinjer.iterrows()
        }
    except Exception:
        for company in page._project.companies:
            page._mapping_pct[company.company_id] = -1
        return

    page._parent_mapping_deviation_details = page._get_parent_override_deviation_details()

    for company in page._project.companies:
        try:
            if _is_line_basis_company(company):
                from ..backend.line_basis_import import validate_company_line_basis

                basis = getattr(page, "_company_line_bases", {}).get(company.company_id)
                if basis is None or basis.empty:
                    page._mapping_pct[company.company_id] = -1
                    continue
                mapped_df, _warnings = validate_company_line_basis(
                    basis,
                    regnskapslinjer=regnskapslinjer,
                )
                page._mapped_tbs[company.company_id] = mapped_df
                page._mapping_unmapped[company.company_id] = []
                page._mapping_review_accounts[company.company_id] = set()
                page._mapping_review_details[company.company_id] = []
                page._mapping_pct[company.company_id] = 100 if not mapped_df.empty else 0
                continue

            tb = page._get_effective_company_tb(company.company_id)
            if tb is None or tb.empty:
                page._mapping_pct[company.company_id] = -1
                continue
            overrides = page._get_effective_company_overrides(company.company_id)
            mapped_df, unmapped = map_company_tb(
                tb,
                overrides,
                intervals=intervals,
                regnskapslinjer=regnskapslinjer,
            )
            page._mapped_tbs[company.company_id] = mapped_df
            page._mapping_unmapped[company.company_id] = unmapped
            review_accounts, review_details = _detect_mapping_review_accounts(
                mapped_df,
                page._regnr_to_name,
            )
            page._mapping_review_accounts[company.company_id] = review_accounts
            page._mapping_review_details[company.company_id] = review_details
            if "konto" in mapped_df.columns:
                konto_series = mapped_df["konto"].astype(str).str.strip()
                total = int(konto_series.replace("", pd.NA).dropna().nunique())
                ok_kontos = set(
                    konto_series.loc[mapped_df["regnr"].notna()].replace("", pd.NA).dropna().tolist()
                )
                if review_accounts:
                    ok_kontos -= set(review_accounts)
                mapped_count = len(ok_kontos)
            else:
                total = len(mapped_df)
                ok_mask = mapped_df["regnr"].notna()
                mapped_count = int(ok_mask.sum()) if total > 0 else 0
            page._mapping_pct[company.company_id] = int(mapped_count * 100 / total) if total > 0 else 0
        except Exception:
            page._mapping_pct[company.company_id] = -1

    if page._tk_ok and hasattr(page, "_elim_cb_rl"):
        page._populate_elim_combos()
        page._refresh_simple_elim_tree()
    try:
        page._refresh_readiness()
    except Exception:
        pass


def split_unmapped_counts(page: "ConsolidationPage", company_id: str) -> tuple[int, int]:
    if page._project is not None:
        company = page._project.find_company(company_id)
        if company is not None and _is_line_basis_company(company):
            return 0, 0

    missing = {
        str(konto).strip()
        for konto in page._mapping_unmapped.get(company_id, []) or []
        if str(konto).strip()
    }
    if not missing:
        return 0, 0

    tb = page._get_effective_company_tb(company_id)
    if tb is None or tb.empty or "konto" not in tb.columns:
        return len(missing), 0

    value_cols = [col for col in ("ib", "netto", "ub") if col in tb.columns]
    if not value_cols:
        return len(missing), 0

    has_value: dict[str, bool] = {konto: False for konto in missing}
    for _, row in tb.iterrows():
        konto = str(row.get("konto", "") or "").strip()
        if konto not in has_value:
            continue
        valued = False
        for col in value_cols:
            try:
                if abs(float(row.get(col, 0) or 0)) > 0.005:
                    valued = True
                    break
            except (ValueError, TypeError):
                continue
        if valued:
            has_value[konto] = True

    valued_count = sum(1 for flagged in has_value.values() if flagged)
    zero_count = len(has_value) - valued_count
    return valued_count, zero_count
