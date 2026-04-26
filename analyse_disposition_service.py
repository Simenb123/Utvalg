"""Hjelpere for enkel disponering via ÅO på enkeltselskapsnivå.

Målet er å gi en trygg og sporbar førstegangsopplevelse:
- brukeren ser disponeringsstatus på regnskapslinjenivå
- brukeren fører fortsatt konto-baserte ÅO-linjer
- vi kan beregne "rest å disponere" uten å innføre en ny journalmodell
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from src.shared.regnskap.mapping import (
    aggregate_by_regnskapslinje,
    apply_account_overrides,
    apply_interval_mapping,
    expand_regnskapslinje_selection,
    normalize_regnskapslinjer,
)


@dataclass(frozen=True)
class DispositionSummary:
    arsresultat: float
    sum_overforinger: float
    rest_a_disponere: float
    line_295: float
    line_320: float
    line_350_leafs: tuple[int, ...]


@dataclass(frozen=True)
class DraftLineProjection:
    konto: str
    kontonavn: str
    belop: float
    regnr: int | None
    regnskapslinje: str
    mapping_status: str  # interval | override | unmapped | sumline


@dataclass(frozen=True)
class DraftSummary:
    debet: float
    kredit: float
    diff: float
    transfer_effect: float
    rest_etter_utkast: float
    has_invalid_lines: bool


def build_disposition_summary(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
) -> DispositionSummary:
    """Bygg disponeringsstatus fra samme mappinggrunnlag som Analyse bruker."""
    if intervals is None or regnskapslinjer is None:
        return DispositionSummary(0.0, 0.0, 0.0, 0.0, 0.0, ())

    regn = normalize_regnskapslinjer(regnskapslinjer)
    values = _build_rl_values(
        hb_df=hb_df,
        effective_sb_df=effective_sb_df,
        intervals=intervals,
        regnskapslinjer=regn,
        account_overrides=account_overrides,
    )

    arsresultat = float(values.get(280, 0.0))
    sum_overforinger = float(values.get(350, 0.0))
    line_295 = float(values.get(295, 0.0))
    line_320 = float(values.get(320, 0.0))
    try:
        leafs = tuple(
            expand_regnskapslinje_selection(
                regnskapslinjer=regn,
                selected_regnr=[350],
            )
        )
    except Exception:
        leafs = ()

    return DispositionSummary(
        arsresultat=arsresultat,
        sum_overforinger=sum_overforinger,
        rest_a_disponere=arsresultat + sum_overforinger,
        line_295=line_295,
        line_320=line_320,
        line_350_leafs=leafs,
    )


def build_account_name_lookup(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
) -> dict[str, str]:
    """Best-effort navnlookup for kontoer."""
    lookup: dict[str, str] = {}

    if isinstance(effective_sb_df, pd.DataFrame) and not effective_sb_df.empty:
        konto_col = _find_col(effective_sb_df, "konto")
        navn_col = _find_col(effective_sb_df, "kontonavn")
        if konto_col:
            for _, row in effective_sb_df.iterrows():
                konto = str(row.get(konto_col, "") or "").strip()
                if not konto:
                    continue
                navn = str(row.get(navn_col, "") or "").strip() if navn_col else ""
                if navn and konto not in lookup:
                    lookup[konto] = navn

    if isinstance(hb_df, pd.DataFrame) and not hb_df.empty and "Konto" in hb_df.columns:
        for _, row in hb_df.iterrows():
            konto = str(row.get("Konto", "") or "").strip()
            if not konto:
                continue
            navn = str(row.get("Kontonavn", "") or "").strip()
            if navn and konto not in lookup:
                lookup[konto] = navn

    return lookup


def project_draft_line(
    *,
    konto: str,
    belop: float,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
    account_name_lookup: dict[str, str] | None = None,
) -> DraftLineProjection:
    konto_clean = str(konto or "").strip()
    belop_value = float(belop or 0.0)
    kontonavn = ""
    if account_name_lookup:
        kontonavn = str(account_name_lookup.get(konto_clean, "") or "").strip()

    if not konto_clean or intervals is None or regnskapslinjer is None:
        return DraftLineProjection(
            konto=konto_clean,
            kontonavn=kontonavn,
            belop=belop_value,
            regnr=None,
            regnskapslinje="",
            mapping_status="unmapped",
        )

    probe = pd.DataFrame({"konto": [konto_clean], "ub": [belop_value]})
    mapped = apply_interval_mapping(probe, intervals, konto_col="konto").mapped
    mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")

    regnr_val = mapped.iloc[0]["regnr"] if not mapped.empty else pd.NA
    regnr = int(regnr_val) if pd.notna(regnr_val) else None

    regn = normalize_regnskapslinjer(regnskapslinjer)
    regn_meta = {
        int(r["regnr"]): (
            str(r.get("regnskapslinje", "") or ""),
            bool(r.get("sumpost", False)),
        )
        for _, r in regn.iterrows()
        if pd.notna(r.get("regnr"))
    }
    override_set = {str(k).strip() for k in (account_overrides or {}).keys() if str(k).strip()}

    if regnr is None:
        status = "unmapped"
        rl_name = ""
    else:
        rl_name, sumpost = regn_meta.get(regnr, ("", False))
        if sumpost:
            status = "sumline"
        elif konto_clean in override_set:
            status = "override"
        else:
            status = "interval"

    return DraftLineProjection(
        konto=konto_clean,
        kontonavn=kontonavn,
        belop=belop_value,
        regnr=regnr,
        regnskapslinje=rl_name,
        mapping_status=status,
    )


def summarize_draft(
    entries: Iterable[dict],
    *,
    disposition_summary: DispositionSummary,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
    account_name_lookup: dict[str, str] | None = None,
) -> DraftSummary:
    debet = 0.0
    kredit = 0.0
    transfer_effect = 0.0
    has_invalid = False

    transfer_leafs = set(disposition_summary.line_350_leafs)
    for entry in entries:
        projection = project_draft_line(
            konto=str(entry.get("konto", "") or ""),
            belop=float(entry.get("belop", 0.0) or 0.0),
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
            account_name_lookup=account_name_lookup,
        )
        belop = projection.belop
        if belop > 0:
            debet += belop
        elif belop < 0:
            kredit += abs(belop)

        if projection.mapping_status in {"unmapped", "sumline"}:
            has_invalid = True
        if projection.regnr is not None and projection.regnr in transfer_leafs:
            transfer_effect += belop

    diff = debet - kredit
    return DraftSummary(
        debet=debet,
        kredit=kredit,
        diff=diff,
        transfer_effect=transfer_effect,
        rest_etter_utkast=disposition_summary.rest_a_disponere + transfer_effect,
        has_invalid_lines=has_invalid,
    )


def _build_rl_values(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    account_overrides: dict[str, int] | None = None,
) -> dict[int, float]:
    try:
        from page_analyse_rl import build_rl_pivot
    except Exception:
        build_rl_pivot = None

    pivot_df: pd.DataFrame | None = None
    if (
        build_rl_pivot is not None
        and isinstance(hb_df, pd.DataFrame)
        and not hb_df.empty
        and "Konto" in hb_df.columns
    ):
        try:
            pivot_df = build_rl_pivot(
                hb_df,
                intervals,
                regnskapslinjer,
                sb_df=effective_sb_df,
                account_overrides=account_overrides,
            )
        except Exception:
            pivot_df = None

    if pivot_df is None:
        pivot_df = _build_rl_from_sb_only(
            effective_sb_df=effective_sb_df,
            intervals=intervals,
            regnskapslinjer=regnskapslinjer,
            account_overrides=account_overrides,
        )

    if pivot_df is None or pivot_df.empty:
        return {}

    values: dict[int, float] = {}
    regnr_col = "regnr" if "regnr" in pivot_df.columns else "Nr"
    ub_col = "UB" if "UB" in pivot_df.columns else "belop"
    for _, row in pivot_df.iterrows():
        try:
            regnr = int(row.get(regnr_col))
            ub = float(row.get(ub_col, 0.0) or 0.0)
        except Exception:
            continue
        values[regnr] = ub
    return values


def _build_rl_from_sb_only(
    *,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    account_overrides: dict[str, int] | None = None,
) -> pd.DataFrame:
    if effective_sb_df is None or not isinstance(effective_sb_df, pd.DataFrame) or effective_sb_df.empty:
        return pd.DataFrame(columns=["regnr", "regnskapslinje", "belop", "sumpost", "formel"])

    if "konto" not in effective_sb_df.columns or "ub" not in effective_sb_df.columns:
        lower_map = {str(c).strip().lower(): c for c in effective_sb_df.columns}
        konto_col = lower_map.get("konto")
        ub_col = lower_map.get("ub")
        if not konto_col or not ub_col:
            return pd.DataFrame(columns=["regnr", "regnskapslinje", "belop", "sumpost", "formel"])
        work = pd.DataFrame({
            "konto": effective_sb_df[konto_col].astype(str),
            "ub": pd.to_numeric(effective_sb_df[ub_col], errors="coerce").fillna(0.0),
        })
    else:
        work = effective_sb_df[["konto", "ub"]].copy()
        work["konto"] = work["konto"].astype(str)
        work["ub"] = pd.to_numeric(work["ub"], errors="coerce").fillna(0.0)

    mapped = apply_interval_mapping(work, intervals, konto_col="konto").mapped
    mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
    return aggregate_by_regnskapslinje(
        mapped,
        regnskapslinjer,
        amount_col="ub",
        include_sum_lines=True,
    )


def _find_col(df: pd.DataFrame, name: str) -> str | None:
    needle = str(name).strip().lower()
    for column in df.columns:
        if str(column).strip().lower() == needle:
            return str(column)
    return None
