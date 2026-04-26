from __future__ import annotations

import logging

import pandas as pd

from formatting import format_number_no

from .data import (
    _CONTROL_GL_DATA_COLUMNS,
    _empty_control_statement_df,
    _empty_rf1022_overview_df,
    _parse_konto_tokens,
    _safe_float,
    a07_code_rf1022_group,
    rf1022_group_label,
    rf1022_post_for_group,
    work_family_for_rf1022_group,
)
from .statement_model import (
    CONTROL_STATEMENT_VIEW_PAYROLL,
    filter_control_statement_df,
    normalize_control_statement_df,
)


_LOG = logging.getLogger(__name__)


def build_control_statement_export_df(
    *,
    client: str | None,
    year: str | int | None,
    gl_df: pd.DataFrame | None,
    reconcile_df: pd.DataFrame | None = None,
    mapping_current: dict[str, str] | None = None,
    include_unclassified: bool = False,
    warning_collector: list[dict[str, str]] | None = None,
) -> pd.DataFrame:
    client_s = str(client or "").strip()
    if not client_s or gl_df is None or gl_df.empty:
        return _empty_control_statement_df()

    year_i: int | None = None
    year_s = str(year or "").strip()
    if year_s:
        try:
            year_i = int(year_s)
        except Exception:
            year_i = None

    mapping_clean = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_current or {}).items()
        if str(account).strip()
    }
    reconcile_lookup: dict[str, pd.Series] = {}
    if reconcile_df is not None and not reconcile_df.empty and "Kode" in reconcile_df.columns:
        for _, row in reconcile_df.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                reconcile_lookup[code] = row

    try:
        from . import data as control_data

        rows = control_data.build_current_control_statement_rows(
            client_s,
            year_i,
            gl_df,
            include_unclassified=bool(include_unclassified),
        )
    except Exception as exc:
        _LOG.exception("A07 control statement rows could not be built")
        if warning_collector is not None:
            warning_collector.append(
                {
                    "scope": "control_statement",
                    "message": "Kontrolloppstilling kunne ikke bygges.",
                    "detail": str(exc),
                }
            )
        return _empty_control_statement_df()

    export_rows: list[dict[str, object]] = []
    for row in rows:
        accounts = [str(account).strip() for account in row.accounts if str(account).strip()]
        mapped_codes: list[str] = []
        has_unmapped_accounts = False
        for account in accounts:
            mapped_code = str(mapping_clean.get(account) or "").strip()
            if mapped_code:
                mapped_codes.append(mapped_code)
            else:
                has_unmapped_accounts = True

        matched_rows: list[pd.Series] = []
        seen_codes: set[str] = set()
        for raw_code in mapped_codes:
            code = str(raw_code or "").strip()
            if not code or code in seen_codes:
                continue
            match = reconcile_lookup.get(code)
            if match is None:
                continue
            matched_rows.append(match)
            seen_codes.add(code)

        a07_total: float | None = None
        diff_total: float | None = None
        if matched_rows:
            a07_values = [_safe_float(match.get("A07_Belop")) for match in matched_rows]
            diff_values = [_safe_float(match.get("Diff")) for match in matched_rows]
            a07_total = sum(value for value in a07_values if value is not None)
            diff_total = sum(value for value in diff_values if value is not None)

        if not mapped_codes:
            status = "Uløst"
        elif has_unmapped_accounts or not matched_rows:
            status = "Manuell"
        else:
            within_flags = [bool(match.get("WithinTolerance", False)) for match in matched_rows]
            status = "Ferdig" if within_flags and all(within_flags) else "Manuell"

        export_rows.append(
            {
                "Gruppe": row.group_id,
                "Navn": row.label,
                "IB": row.ib,
                "Endring": row.movement,
                "UB": row.ub,
                "A07": a07_total,
                "Diff": diff_total,
                "Status": status,
                "AntallKontoer": row.account_count,
                "Kontoer": ", ".join(accounts),
                "Kilder": ", ".join(row.source_breakdown),
            }
        )

    rows_df = pd.DataFrame(export_rows)
    if rows_df.empty:
        return _empty_control_statement_df()
    return normalize_control_statement_df(rows_df)


def build_rf1022_statement_df(
    control_statement_df: pd.DataFrame | None,
    *,
    basis_col: str = "Endring",
    a07_overview_df: pd.DataFrame | None = None,
    control_df: pd.DataFrame | None = None,
    control_gl_df: pd.DataFrame | None = None,
    profile_document: object | None = None,
) -> pd.DataFrame:
    control_statement_df = normalize_control_statement_df(control_statement_df)
    a07_totals = _rf1022_a07_totals_from_overview(a07_overview_df)
    a07_aga_totals = _rf1022_a07_aga_totals_from_overview(a07_overview_df)
    if not a07_aga_totals:
        a07_aga_totals = _rf1022_a07_aga_totals_from_overview(control_df)
    if control_statement_df.empty and not a07_totals:
        return _empty_rf1022_overview_df()

    gl_col = basis_col if basis_col in control_statement_df.columns else "Endring"
    detail_totals = _rf1022_group_detail_totals(
        control_gl_df,
        control_statement_df,
        basis_col=basis_col,
        profile_document=profile_document,
    )
    rows_by_group: dict[str, dict[str, object]] = {}

    def _rf1022_display_values(group_key: str, label_text: str, post_no: int, post_label: str) -> tuple[str, str, str]:
        if str(group_key).strip() == "uavklart_rf1022":
            return "", "Må fordeles", "A07 uten RF-1022-post"
        return str(post_no), post_label, label_text

    for _, row in control_statement_df.iterrows():
        group_id = str(row.get("Gruppe") or "").strip()
        label = str(row.get("Navn") or "").strip() or group_id
        if not group_id and not label:
            continue
        post_no, post_label = rf1022_post_for_group(group_id, label)
        key = group_id or label
        display_post, display_area, display_label = _rf1022_display_values(key, label, post_no, post_label)
        gl_amount = _safe_float(row.get(gl_col)) or 0.0
        group_detail_totals = detail_totals.get(key, {})
        taxable_amount = group_detail_totals.get("SamledeYtelser")
        if taxable_amount is None:
            taxable_amount = gl_amount
        aga_basis = group_detail_totals.get("AgaGrunnlag")
        a07_amount = a07_totals.get(key)
        if a07_amount is None:
            a07_amount = _safe_float(row.get("A07"))
        a07_aga_amount = a07_aga_totals.get(key)
        diff_amount = (float(a07_amount) - float(taxable_amount or 0.0)) if a07_amount is not None else row.get("Diff")
        aga_diff_amount = (
            float(a07_aga_amount) - float(aga_basis or 0.0)
            if a07_aga_amount is not None and aga_basis is not None
            else None
        )
        rows_by_group[key] = {
            "GroupId": key,
            "Post": display_post,
            "Omraade": display_area,
            "Kontrollgruppe": display_label,
            "GL_Belop": gl_amount,
            "SamledeYtelser": taxable_amount,
            "A07": a07_amount,
            "Diff": diff_amount,
            "AgaGrunnlag": aga_basis,
            "A07Aga": a07_aga_amount,
            "AgaDiff": aga_diff_amount,
            "Status": row.get("Status"),
            "AntallKontoer": row.get("AntallKontoer"),
            "WorkFamily": work_family_for_rf1022_group(key),
            "_post_sort": post_no,
        }

    for group_id, a07_amount in a07_totals.items():
        if group_id in rows_by_group:
            continue
        post_no, post_label = rf1022_post_for_group(group_id, rf1022_group_label(group_id))
        label = rf1022_group_label(group_id) or group_id
        display_post, display_area, display_label = _rf1022_display_values(group_id, label, post_no, post_label)
        rows_by_group[group_id] = {
            "GroupId": group_id,
            "Post": display_post,
            "Omraade": display_area,
            "Kontrollgruppe": display_label,
            "GL_Belop": 0.0,
            "SamledeYtelser": 0.0,
            "A07": a07_amount,
            "Diff": a07_amount,
            "AgaGrunnlag": 0.0,
            "A07Aga": a07_aga_totals.get(group_id),
            "AgaDiff": a07_aga_totals.get(group_id),
            "Status": "Mangler SB",
            "AntallKontoer": 0,
            "WorkFamily": work_family_for_rf1022_group(group_id),
            "_post_sort": post_no,
        }

    if not rows_by_group:
        return _empty_rf1022_overview_df()

    view_df = pd.DataFrame(rows_by_group.values())
    view_df = view_df.sort_values(by=["_post_sort", "Kontrollgruppe", "GroupId"], kind="stable")
    return view_df.drop(columns=["_post_sort"], errors="ignore").reset_index(drop=True)


def _rf1022_a07_totals_from_overview(a07_overview_df: pd.DataFrame | None) -> dict[str, float]:
    if a07_overview_df is None or a07_overview_df.empty:
        return {}
    if "Kode" not in a07_overview_df.columns:
        return {}
    value_col = "Belop" if "Belop" in a07_overview_df.columns else "A07_Belop"
    if value_col not in a07_overview_df.columns:
        return {}

    totals: dict[str, float] = {}
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code:
            continue
        group_id = a07_code_rf1022_group(code)
        if not group_id:
            continue
        amount = _safe_float(row.get(value_col))
        if amount is None:
            continue
        totals[group_id] = totals.get(group_id, 0.0) + float(amount)
    return {group_id: amount for group_id, amount in totals.items() if abs(float(amount)) > 0.005}


def _a07_row_is_aga_pliktig(row: pd.Series) -> bool:
    raw = row.get("AgaPliktig")
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().casefold()
    return text in {"ja", "true", "1", "yes", "y"}


def _rf1022_a07_aga_totals_from_overview(a07_overview_df: pd.DataFrame | None) -> dict[str, float]:
    if a07_overview_df is None or a07_overview_df.empty:
        return {}
    if "Kode" not in a07_overview_df.columns or "AgaPliktig" not in a07_overview_df.columns:
        return {}
    value_col = "Belop" if "Belop" in a07_overview_df.columns else "A07_Belop"
    if value_col not in a07_overview_df.columns:
        return {}

    totals: dict[str, float] = {}
    for _, row in a07_overview_df.iterrows():
        if not _a07_row_is_aga_pliktig(row):
            continue
        code = str(row.get("Kode") or "").strip()
        if not code:
            continue
        group_id = a07_code_rf1022_group(code)
        if not group_id:
            continue
        amount = _safe_float(row.get(value_col))
        if amount is None:
            continue
        totals[group_id] = totals.get(group_id, 0.0) + float(amount)
    return {group_id: amount for group_id, amount in totals.items() if abs(float(amount)) > 0.005}


def _sum_numeric_column(df: pd.DataFrame, column_id: str) -> float | None:
    if df is None or df.empty or column_id not in df.columns:
        return None
    series = pd.to_numeric(df[column_id], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.sum())


def _rf1022_group_detail_totals(
    control_gl_df: pd.DataFrame | None,
    control_statement_df: pd.DataFrame | None,
    *,
    basis_col: str,
    profile_document: object | None,
) -> dict[str, dict[str, float | None]]:
    if control_gl_df is None or control_gl_df.empty:
        return {}
    if control_statement_df is None or control_statement_df.empty or "Gruppe" not in control_statement_df.columns:
        return {}

    totals: dict[str, dict[str, float | None]] = {}
    for raw_group in control_statement_df["Gruppe"].astype(str).dropna().tolist():
        group_id = str(raw_group or "").strip()
        if not group_id or group_id in totals:
            continue
        accounts_df = build_rf1022_accounts_df(
            control_gl_df,
            control_statement_df,
            group_id,
            basis_col=basis_col,
            profile_document=profile_document,
        )
        if accounts_df is None or accounts_df.empty:
            continue
        totals[group_id] = {
            "SamledeYtelser": _sum_numeric_column(accounts_df, "SamledeYtelser"),
            "AgaGrunnlag": _sum_numeric_column(accounts_df, "AgaGrunnlag"),
        }
    return totals


def build_rf1022_statement_summary(
    rf1022_df: pd.DataFrame | None,
    *,
    tag_totals: dict[str, float] | None = None,
) -> str:
    if rf1022_df is None or rf1022_df.empty:
        return "Ingen poster i kontrolloppstillingen."

    def _sum_col(column_id: str) -> str:
        if column_id not in rf1022_df.columns:
            return "-"
        series = pd.to_numeric(rf1022_df[column_id], errors="coerce").fillna(0.0)
        return format_number_no(float(series.sum()), 2)

    parts = [
        f"Poster {len(rf1022_df)}",
        f"Opplysningspliktig: SB {_sum_col('SamledeYtelser')} / A07 {_sum_col('A07')} / diff {_sum_col('Diff')}",
        f"AGA-pliktig: SB {_sum_col('AgaGrunnlag')} / A07 {_sum_col('A07Aga')} / diff {_sum_col('AgaDiff')}",
    ]
    totals = dict(tag_totals or {})
    if totals:
        parts.extend(
            [
                f"Opplysningspliktig {format_number_no(float(totals.get('opplysningspliktig', 0.0)), 2)}",
                f"AGA-pliktig {format_number_no(float(totals.get('aga_pliktig', 0.0)), 2)}",
                f"Finansskatt {format_number_no(float(totals.get('finansskatt_pliktig', 0.0)), 2)}",
            ]
        )
    return " | ".join(parts)


def build_control_statement_accounts_df(
    gl_df: pd.DataFrame,
    control_statement_df: pd.DataFrame,
    group_id: str | None,
) -> pd.DataFrame:
    group_s = str(group_id or "").strip()
    if not group_s:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
    control_statement_df = normalize_control_statement_df(control_statement_df)
    if gl_df is None or gl_df.empty or control_statement_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    matches = control_statement_df.loc[control_statement_df["Gruppe"].astype(str).str.strip() == group_s]
    if matches.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    row = matches.iloc[0]
    accounts = _parse_konto_tokens(row.get("Kontoer"))
    if not accounts:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    selected = gl_df.loc[gl_df["Konto"].astype(str).str.strip().isin(accounts)].copy()
    if selected.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    order = {account: idx for idx, account in enumerate(accounts)}
    selected["Konto"] = selected["Konto"].astype(str).str.strip()
    selected["_order"] = selected["Konto"].map(order).fillna(len(order))
    selected = selected.sort_values(by=["_order", "Konto"], kind="stable")
    if "BelopAktiv" not in selected.columns:
        selected["BelopAktiv"] = selected.get("Endring")
    if "Kol" not in selected.columns:
        selected["Kol"] = "Endring"
    selected = selected.reindex(columns=list(_CONTROL_GL_DATA_COLUMNS), fill_value="")
    return selected.reset_index(drop=True)


from .rf1022_accounts import build_rf1022_accounts_df


__all__ = [
    "build_control_statement_accounts_df",
    "build_control_statement_export_df",
    "build_rf1022_accounts_df",
    "build_rf1022_statement_df",
    "build_rf1022_statement_summary",
]
