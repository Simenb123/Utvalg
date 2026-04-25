from __future__ import annotations

from typing import Mapping

import pandas as pd

from .data import _MAPPING_AUDIT_STATUS_PRIORITY


def sort_mapping_rows_by_audit_status(mapping_df: pd.DataFrame | None) -> pd.DataFrame:
    if mapping_df is None:
        return pd.DataFrame()
    work = mapping_df.copy()
    if work.empty:
        return work.reset_index(drop=True)
    status_column = (
        "Status"
        if "Status" in work.columns
        else "MappingAuditStatus"
        if "MappingAuditStatus" in work.columns
        else "Kontroll"
        if "Kontroll" in work.columns
        else ""
    )
    if not status_column:
        return work.reset_index(drop=True)
    status_values = work[status_column].fillna("").astype(str).str.strip()
    work["_audit_status_order"] = status_values.map(_MAPPING_AUDIT_STATUS_PRIORITY).fillna(4).astype(int)
    work["_audit_original_order"] = range(len(work.index))
    work = work.sort_values(by=["_audit_status_order", "_audit_original_order"], kind="stable")
    return work.drop(columns=["_audit_status_order", "_audit_original_order"], errors="ignore").reset_index(drop=True)


def filter_mapping_rows_by_audit_status(
    mapping_df: pd.DataFrame | None,
    filter_key: object,
) -> pd.DataFrame:
    if mapping_df is None:
        return pd.DataFrame()
    work = sort_mapping_rows_by_audit_status(mapping_df)
    key = str(filter_key or "alle").strip().casefold()
    label_aliases = {
        "kritisk": "kritiske",
        "critical": "kritiske",
        "alle": "alle",
        "all": "alle",
        "feil": "feil",
        "error": "feil",
        "mistenkelig": "mistenkelige",
        "mistenkelige": "mistenkelige",
        "suspicious": "mistenkelige",
        "uavklart": "uavklarte",
        "uavklarte": "uavklarte",
        "trygg": "trygge",
        "trygge": "trygge",
        "safe": "trygge",
    }
    key = label_aliases.get(key, key)
    status_sets = {
        "kritiske": {"Feil", "Mistenkelig"},
        "alle": None,
        "feil": {"Feil"},
        "mistenkelige": {"Mistenkelig"},
        "uavklarte": {"Uavklart"},
        "trygge": {"Trygg"},
    }
    wanted = status_sets.get(key)
    status_column = mapping_review_status_column(work)
    if wanted is None or not status_column:
        return work.reset_index(drop=True)
    statuses = work[status_column].fillna("").astype(str).str.strip()
    return work.loc[statuses.isin(wanted)].reset_index(drop=True)


def mapping_review_text(row: pd.Series | Mapping[str, object], column: str) -> str:
    try:
        value = row.get(column, "")
    except Exception:
        value = ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value or "").strip()


def mapping_review_status_column(mapping_df: pd.DataFrame | None) -> str:
    if mapping_df is None:
        return ""
    for column in ("Kontroll", "Status", "MappingAuditStatus"):
        if column in mapping_df.columns:
            return column
    return ""
