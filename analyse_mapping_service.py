"""Felles mapping-/unmapped-service for Analyse-fanen."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from regnskap_mapping import apply_account_overrides, apply_interval_mapping, normalize_regnskapslinjer


@dataclass(frozen=True)
class UnmappedAccountIssue:
    konto: str
    kontonavn: str
    kilde: str
    belop: float
    regnr: int | None
    regnskapslinje: str
    mapping_status: str  # interval | override | unmapped | sumline

    @property
    def has_value(self) -> bool:
        return abs(float(self.belop or 0.0)) > 0.005


def _group_hb(df_hb: pd.DataFrame | None) -> pd.DataFrame:
    if df_hb is None or not isinstance(df_hb, pd.DataFrame) or df_hb.empty:
        return pd.DataFrame(columns=["konto", "kontonavn_hb", "hb_sum"])
    if "Konto" not in df_hb.columns:
        return pd.DataFrame(columns=["konto", "kontonavn_hb", "hb_sum"])
    work = pd.DataFrame({"konto": df_hb["Konto"].astype(str).str.strip()})
    if "Kontonavn" in df_hb.columns:
        work["kontonavn_hb"] = df_hb["Kontonavn"].fillna("").astype(str)
    else:
        work["kontonavn_hb"] = ""
    if "Beløp" in df_hb.columns:
        work["hb_sum"] = pd.to_numeric(df_hb["Beløp"], errors="coerce").fillna(0.0)
    else:
        work["hb_sum"] = 0.0
    return work.groupby("konto", as_index=False).agg(kontonavn_hb=("kontonavn_hb", "first"), hb_sum=("hb_sum", "sum"))


def _group_sb(sb_df: pd.DataFrame | None) -> pd.DataFrame:
    if sb_df is None or not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        return pd.DataFrame(columns=["konto", "kontonavn_sb", "sb_ub", "sb_ib", "exists_in_sb"])
    col_map: dict[str, str] = {}
    for c in sb_df.columns:
        cl = str(c).strip().lower()
        if cl == "konto":
            col_map["konto"] = c
        elif cl == "kontonavn":
            col_map["kontonavn"] = c
        elif cl == "ub":
            col_map["ub"] = c
        elif cl == "ib":
            col_map["ib"] = c
    konto_col = col_map.get("konto")
    if not konto_col:
        return pd.DataFrame(columns=["konto", "kontonavn_sb", "sb_ub", "sb_ib", "exists_in_sb"])
    work = pd.DataFrame({"konto": sb_df[konto_col].astype(str).str.strip()})
    work["kontonavn_sb"] = (
        sb_df[col_map["kontonavn"]].fillna("").astype(str)
        if "kontonavn" in col_map else ""
    )
    work["sb_ub"] = pd.to_numeric(sb_df[col_map["ub"]], errors="coerce").fillna(0.0) if "ub" in col_map else 0.0
    work["sb_ib"] = pd.to_numeric(sb_df[col_map["ib"]], errors="coerce").fillna(0.0) if "ib" in col_map else 0.0
    out = work.groupby("konto", as_index=False).agg(
        kontonavn_sb=("kontonavn_sb", "first"),
        sb_ub=("sb_ub", "sum"),
        sb_ib=("sb_ib", "sum"),
    )
    out["exists_in_sb"] = True
    return out


def build_mapping_issues(
    *,
    hb_df: pd.DataFrame | None,
    effective_sb_df: pd.DataFrame | None,
    intervals: pd.DataFrame | None,
    regnskapslinjer: pd.DataFrame | None,
    account_overrides: dict[str, int] | None = None,
    include_ao: bool = False,
) -> list[UnmappedAccountIssue]:
    """Returner standardiserte mapping-issues for Analyse."""
    hb_grouped = _group_hb(hb_df)
    sb_grouped = _group_sb(effective_sb_df)
    base = hb_grouped.merge(sb_grouped, how="outer", on="konto")
    if base.empty:
        return []

    for col in ("kontonavn_hb", "kontonavn_sb"):
        if col in base.columns:
            base[col] = base[col].fillna("").astype(str)
    for col in ("hb_sum", "sb_ub", "sb_ib"):
        if col in base.columns:
            base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0.0)
    if "exists_in_sb" not in base.columns:
        base["exists_in_sb"] = False
    base["exists_in_sb"] = base["exists_in_sb"].fillna(False).astype(bool)
    base["exists_in_hb"] = base["konto"].isin(set(hb_grouped["konto"].astype(str))) if not hb_grouped.empty else False
    base["kontonavn"] = base["kontonavn_hb"].where(base["kontonavn_hb"].str.strip() != "", base["kontonavn_sb"]).fillna("")
    base["belop"] = base["sb_ub"].where(base["exists_in_sb"], base["hb_sum"]).fillna(0.0)

    if intervals is None or regnskapslinjer is None or intervals.empty or regnskapslinjer.empty:
        return [
            UnmappedAccountIssue(
                konto=str(row["konto"]),
                kontonavn=str(row.get("kontonavn", "") or ""),
                kilde=("AO_ONLY" if include_ao and not bool(row.get("exists_in_hb", False)) and bool(row.get("exists_in_sb", False)) else ("HB" if bool(row.get("exists_in_hb", False)) else "SB")),
                belop=float(row.get("belop", 0.0) or 0.0),
                regnr=None,
                regnskapslinje="",
                mapping_status="unmapped",
            )
            for _, row in base.iterrows()
        ]

    probe = base[["konto"]].copy()
    mapped = apply_interval_mapping(probe, intervals, konto_col="konto").mapped
    mapped = apply_account_overrides(mapped, account_overrides, konto_col="konto")
    base = base.merge(mapped[["konto", "regnr"]], how="left", on="konto")

    regn = normalize_regnskapslinjer(regnskapslinjer)
    regn_names = {
        int(r["regnr"]): {
            "name": str(r.get("regnskapslinje", "") or ""),
            "sumpost": bool(r.get("sumpost", False)),
        }
        for _, r in regn.iterrows()
        if pd.notna(r.get("regnr"))
    }
    override_set = {str(k).strip() for k in (account_overrides or {}).keys() if str(k).strip()}

    issues: list[UnmappedAccountIssue] = []
    for _, row in base.iterrows():
        konto = str(row.get("konto", "") or "").strip()
        if not konto:
            continue
        regnr_val = row.get("regnr")
        regnr = int(regnr_val) if pd.notna(regnr_val) else None
        if bool(row.get("exists_in_hb", False)):
            kilde = "HB"
        elif include_ao and bool(row.get("exists_in_sb", False)):
            kilde = "AO_ONLY"
        else:
            kilde = "SB"

        if regnr is None:
            status = "unmapped"
            rl_name = ""
        else:
            meta = regn_names.get(regnr, {"name": "", "sumpost": False})
            rl_name = str(meta.get("name", "") or "")
            if bool(meta.get("sumpost", False)):
                status = "sumline"
            elif konto in override_set:
                status = "override"
            else:
                status = "interval"
        issues.append(
            UnmappedAccountIssue(
                konto=konto,
                kontonavn=str(row.get("kontonavn", "") or ""),
                kilde=kilde,
                belop=float(row.get("belop", 0.0) or 0.0),
                regnr=regnr,
                regnskapslinje=rl_name,
                mapping_status=status,
            )
        )
    return issues


def problem_mapping_issues(
    issues: list[UnmappedAccountIssue],
    *,
    include_zero: bool = False,
) -> list[UnmappedAccountIssue]:
    """Filtrer ut issues som krever brukeroppmerksomhet."""
    out: list[UnmappedAccountIssue] = []
    for issue in issues:
        if issue.mapping_status not in {"unmapped", "sumline"}:
            continue
        if include_zero or issue.has_value:
            out.append(issue)
    return out


def summarize_mapping_issues(
    issues: list[UnmappedAccountIssue],
    *,
    include_zero: bool = False,
) -> str:
    problems = problem_mapping_issues(issues, include_zero=include_zero)
    if not problems:
        return ""
    sample = ", ".join(issue.konto for issue in problems[:5])
    if len(problems) > 5:
        sample += ", ..."
    count = len(problems)
    noun = "konto" if count == 1 else "kontoer"
    return f"{count} {noun} mangler regnskapslinje eller er mappet til sumpost ({sample})"


def get_problem_accounts(issues: list[UnmappedAccountIssue]) -> list[str]:
    return [issue.konto for issue in problem_mapping_issues(issues, include_zero=False)]


def build_page_mapping_issues(page: Any, *, use_filtered_hb: bool = False) -> list[UnmappedAccountIssue]:
    """Convenience-wrapper for AnalysePage."""
    hb_df = getattr(page, "_df_filtered", None) if use_filtered_hb else getattr(page, "dataset", None)
    try:
        effective_sb = page._get_effective_sb_df()
    except Exception:
        effective_sb = getattr(page, "_rl_sb_df", None)
    try:
        include_ao = bool(page._include_ao_enabled())
    except Exception:
        include_ao = False
    try:
        import session as _session
        import regnskap_client_overrides
        client = getattr(_session, "client", None) or ""
        year = getattr(_session, "year", None) or ""
        overrides = regnskap_client_overrides.load_account_overrides(client, year=str(year) if year else None) if client else {}
    except Exception:
        overrides = {}
    return build_mapping_issues(
        hb_df=hb_df if isinstance(hb_df, pd.DataFrame) else None,
        effective_sb_df=effective_sb if isinstance(effective_sb, pd.DataFrame) else None,
        intervals=getattr(page, "_rl_intervals", None),
        regnskapslinjer=getattr(page, "_rl_regnskapslinjer", None),
        account_overrides=overrides,
        include_ao=include_ao,
    )
