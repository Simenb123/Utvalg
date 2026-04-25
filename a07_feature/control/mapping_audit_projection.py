from __future__ import annotations

import pandas as pd

from .data import _CONTROL_GL_DATA_COLUMNS
from .mapping_audit_status import sort_mapping_rows_by_audit_status


_AUDIT_PROBLEM_STATUSES = {"Feil", "Mistenkelig", "Uavklart"}


def _zero_diff_codes(a07_overview_df: pd.DataFrame | None) -> dict[str, object]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return {}
    work = a07_overview_df.copy()
    if "Diff" not in work.columns:
        return {}
    work["Kode"] = work["Kode"].fillna("").astype(str).str.strip()
    work = work.loc[work["Kode"].ne("")]
    if work.empty:
        return {}
    return dict(zip(work["Kode"], work["Diff"]))


def _display_audit_status(raw_status: object, diff_value: object) -> str:
    status = str(raw_status or "").strip()
    if status not in _AUDIT_PROBLEM_STATUSES:
        return status
    try:
        diff = pd.to_numeric(pd.Series([diff_value]), errors="coerce").iloc[0]
    except Exception:
        diff = None
    if pd.notna(diff) and abs(float(diff)) <= 0.005:
        return "Avstemt"
    return status


def apply_mapping_audit_to_control_gl_df(
    control_gl_df: pd.DataFrame | None,
    mapping_audit_df: pd.DataFrame | None,
    *,
    a07_overview_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if control_gl_df is None:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
    work = control_gl_df.copy()
    if work.empty or mapping_audit_df is None or mapping_audit_df.empty or "Konto" not in work.columns:
        for column in (
            "AliasStatus",
            "MappingAuditStatus",
            "MappingAuditReason",
            "MappingAuditRawStatus",
            "MappingAuditRawReason",
            "A07CodeDiff",
        ):
            if column not in work.columns:
                work[column] = ""
        return work.reindex(columns=list(_CONTROL_GL_DATA_COLUMNS), fill_value="")
    audit = mapping_audit_df.copy()
    audit["Konto"] = audit["Konto"].fillna("").astype(str).str.strip()
    audit = audit.drop_duplicates(subset=["Konto"])
    for column in ("AliasStatus", "Status", "Reason"):
        if column not in audit.columns:
            audit[column] = ""
    audit_lookup = audit.set_index("Konto", drop=False)
    work["Konto"] = work["Konto"].fillna("").astype(str).str.strip()
    work["AliasStatus"] = work["Konto"].map(audit_lookup["AliasStatus"]).fillna("")
    raw_status = work["Konto"].map(audit_lookup["Status"]).fillna("")
    raw_reason = work["Konto"].map(audit_lookup["Reason"]).fillna("")
    diff_lookup = _zero_diff_codes(a07_overview_df)
    if "Kode" in work.columns:
        work["A07CodeDiff"] = work["Kode"].fillna("").astype(str).str.strip().map(diff_lookup).fillna("")
    else:
        work["A07CodeDiff"] = ""
    work["MappingAuditRawStatus"] = raw_status
    work["MappingAuditRawReason"] = raw_reason
    work["MappingAuditStatus"] = [
        _display_audit_status(status, diff)
        for status, diff in zip(raw_status.tolist(), work["A07CodeDiff"].tolist())
    ]
    work["MappingAuditReason"] = raw_reason
    return work.reindex(columns=list(_CONTROL_GL_DATA_COLUMNS), fill_value="")


def apply_mapping_audit_to_mapping_df(
    mapping_df: pd.DataFrame | None,
    mapping_audit_df: pd.DataFrame | None,
) -> pd.DataFrame:
    if mapping_df is None:
        return pd.DataFrame(columns=["Konto", "Navn", "Kode", "Rf1022GroupId", "AliasStatus", "Kol", "Status", "Reason"])
    work = mapping_df.copy()
    for column in ("Rf1022GroupId", "AliasStatus", "Kol", "Status", "Reason"):
        if column not in work.columns:
            work[column] = ""
    if work.empty or mapping_audit_df is None or mapping_audit_df.empty or "Konto" not in work.columns:
        return work
    audit = mapping_audit_df.copy()
    audit["Konto"] = audit["Konto"].fillna("").astype(str).str.strip()
    audit = audit.drop_duplicates(subset=["Konto"])
    for column in ("CurrentRf1022GroupId", "AliasStatus", "Kol", "Status", "Reason"):
        if column not in audit.columns:
            audit[column] = ""
    audit_lookup = audit.set_index("Konto", drop=False)
    work["Konto"] = work["Konto"].fillna("").astype(str).str.strip()
    work["Rf1022GroupId"] = work["Konto"].map(audit_lookup["CurrentRf1022GroupId"]).fillna("")
    work["AliasStatus"] = work["Konto"].map(audit_lookup["AliasStatus"]).fillna("")
    work["Kol"] = work["Konto"].map(audit_lookup["Kol"]).fillna("")
    work["Status"] = work["Konto"].map(audit_lookup["Status"]).fillna("")
    work["Reason"] = work["Konto"].map(audit_lookup["Reason"]).fillna("")
    return sort_mapping_rows_by_audit_status(work)
