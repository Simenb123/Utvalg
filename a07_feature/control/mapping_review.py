from __future__ import annotations

import pandas as pd

from .data import _MAPPING_REVIEW_COLUMNS, _MAPPING_REVIEW_CRITICAL_STATUSES
from .mapping_audit_status import (
    mapping_review_status_column,
    mapping_review_text,
    sort_mapping_rows_by_audit_status,
)


def _mapping_review_action(status: str, reason: str, alias_status: str) -> str:
    status_s = str(status or "").strip()
    reason_s = str(reason or "").strip()
    alias_s = str(alias_status or "").strip()
    reason_cf = reason_s.casefold()
    if status_s == "Feil":
        if "utenfor" in reason_cf or "out-of-scope" in reason_cf:
            return "Fjern mapping og ekskluder navn"
        if alias_s == "Ekskludert":
            return "Fjern mapping eller endre A07-kode"
        return "Rydd mapping"
    if status_s == "Mistenkelig":
        if alias_s == "Ekskludert":
            return "Fjern mapping eller oppdater regel"
        return "Vurder manuelt"
    if status_s == "Uavklart":
        return "Avklar A07/RF-1022"
    if status_s == "Trygg":
        return "Ingen handling"
    return "Vurder"


def _mapping_review_normalized_rows(mapping_df: pd.DataFrame | None) -> list[dict[str, object]]:
    if mapping_df is None or mapping_df.empty:
        return []
    status_column = mapping_review_status_column(mapping_df)
    reason_column = "Hvorfor" if "Hvorfor" in mapping_df.columns else "Reason" if "Reason" in mapping_df.columns else "MappingAuditReason"
    rows: list[dict[str, object]] = []
    for _, row in mapping_df.iterrows():
        status = mapping_review_text(row, status_column)
        reason = mapping_review_text(row, reason_column)
        alias_status = mapping_review_text(row, "AliasStatus")
        if alias_status == "Ekskludert" and status == "Trygg":
            status = "Mistenkelig"
            reason = (
                f"{reason} Kontonavn er ekskludert for A07-koden."
                if reason
                else "Kontonavn er ekskludert for A07-koden."
            )
        code = mapping_review_text(row, "Kode") or mapping_review_text(row, "CurrentA07Code")
        rf_group = mapping_review_text(row, "Rf1022GroupId") or mapping_review_text(row, "CurrentRf1022GroupId")
        rows.append(
            {
                "Konto": mapping_review_text(row, "Konto"),
                "Navn": mapping_review_text(row, "Navn"),
                "Kode": code,
                "Rf1022GroupId": rf_group,
                "ExpectedRf1022GroupId": mapping_review_text(row, "ExpectedRf1022GroupId"),
                "AliasStatus": alias_status,
                "Kol": mapping_review_text(row, "Kol"),
                "Belop": row.get("Belop", row.get("BelopAktiv", "")) if hasattr(row, "get") else "",
                "Kontroll": status,
                "Hvorfor": reason,
                "Evidence": mapping_review_text(row, "Evidence"),
                "AnbefaltHandling": _mapping_review_action(status, reason, alias_status),
            }
        )
    return rows


def build_mapping_review_df(
    mapping_audit_df: pd.DataFrame | None,
    control_gl_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    rows = _mapping_review_normalized_rows(mapping_audit_df)
    if control_gl_df is not None and not control_gl_df.empty and rows:
        gl_work = control_gl_df.copy()
        if "Konto" in gl_work.columns:
            gl_work["Konto"] = gl_work["Konto"].fillna("").astype(str).str.strip()
            gl_lookup = gl_work.drop_duplicates(subset=["Konto"]).set_index("Konto", drop=False)
            for review_row in rows:
                account = str(review_row.get("Konto") or "").strip()
                if not account or account not in gl_lookup.index:
                    continue
                gl_row = gl_lookup.loc[account]
                for column in ("Navn", "Kol", "AliasStatus"):
                    if not str(review_row.get(column) or "").strip():
                        review_row[column] = gl_row.get(column, "")
                if not str(review_row.get("Belop") or "").strip():
                    value_column = str(review_row.get("Kol") or "").strip()
                    if value_column and value_column in gl_row.index:
                        review_row["Belop"] = gl_row.get(value_column, "")
    if not rows:
        return pd.DataFrame(columns=list(_MAPPING_REVIEW_COLUMNS))
    return sort_mapping_rows_by_audit_status(
        pd.DataFrame(rows, columns=list(_MAPPING_REVIEW_COLUMNS))
    ).reset_index(drop=True)


def build_mapping_review_summary(mapping_review_df: pd.DataFrame | None) -> dict[str, int]:
    if mapping_review_df is None or mapping_review_df.empty:
        return {"total": 0, "kritiske": 0, "feil": 0, "mistenkelige": 0, "uavklarte": 0, "trygge": 0}
    status_column = mapping_review_status_column(mapping_review_df)
    if not status_column:
        return {"total": int(len(mapping_review_df.index)), "kritiske": 0, "feil": 0, "mistenkelige": 0, "uavklarte": 0, "trygge": 0}
    statuses = mapping_review_df[status_column].fillna("").astype(str).str.strip()
    feil = int((statuses == "Feil").sum())
    mistenkelige = int((statuses == "Mistenkelig").sum())
    uavklarte = int((statuses == "Uavklart").sum())
    trygge = int((statuses == "Trygg").sum())
    return {
        "total": int(len(mapping_review_df.index)),
        "kritiske": feil + mistenkelige,
        "feil": feil,
        "mistenkelige": mistenkelige,
        "uavklarte": uavklarte,
        "trygge": trygge,
    }


def build_mapping_review_summary_text(mapping_review_df: pd.DataFrame | None) -> str:
    summary = build_mapping_review_summary(mapping_review_df)
    if not summary["total"]:
        return "Ingen koblinger i visningen."
    parts = [f"{summary['total']} koblinger"]
    if summary["feil"]:
        parts.append(f"{summary['feil']} feil")
    if summary["mistenkelige"]:
        parts.append(f"{summary['mistenkelige']} mistenkelige")
    if summary["uavklarte"]:
        parts.append(f"{summary['uavklarte']} uavklarte")
    if summary["trygge"]:
        parts.append(f"{summary['trygge']} trygge")
    return " | ".join(parts)


def next_mapping_review_problem_account(
    mapping_review_df: pd.DataFrame | None,
    current_account: object | None = None,
) -> str:
    if mapping_review_df is None or mapping_review_df.empty or "Konto" not in mapping_review_df.columns:
        return ""
    status_column = mapping_review_status_column(mapping_review_df)
    if not status_column:
        return ""
    work = sort_mapping_rows_by_audit_status(mapping_review_df)
    statuses = work[status_column].fillna("").astype(str).str.strip()
    problems = work.loc[statuses.isin(_MAPPING_REVIEW_CRITICAL_STATUSES)].copy()
    if problems.empty:
        return ""
    accounts = [str(account or "").strip() for account in problems["Konto"].tolist()]
    accounts = [account for account in accounts if account]
    if not accounts:
        return ""
    current = str(current_account or "").strip()
    if current in accounts:
        return accounts[(accounts.index(current) + 1) % len(accounts)]
    return accounts[0]
