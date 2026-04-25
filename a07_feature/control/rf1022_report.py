from __future__ import annotations

import pandas as pd

from formatting import format_number_no

from .rf1022_bridge import RF1022_UNKNOWN_GROUP
from .rf1022_contract import RF1022_OVERVIEW_COLUMNS


RF1022_TOTAL_ROW_ID = "__rf1022_total__"


def _to_number(value: object) -> float:
    try:
        numeric = pd.to_numeric(value, errors="coerce")
    except Exception:
        return 0.0
    try:
        if pd.isna(numeric):
            return 0.0
    except Exception:
        return 0.0
    return float(numeric)


def _sum_col(df: pd.DataFrame, column_id: str) -> float:
    if df is None or df.empty or column_id not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column_id], errors="coerce").fillna(0.0).sum())


def _without_total_row(rf1022_df: pd.DataFrame | None) -> pd.DataFrame:
    if rf1022_df is None or rf1022_df.empty:
        return pd.DataFrame(columns=list(RF1022_OVERVIEW_COLUMNS))
    if "GroupId" not in rf1022_df.columns:
        return rf1022_df.copy()
    return rf1022_df.loc[rf1022_df["GroupId"].astype(str) != RF1022_TOTAL_ROW_ID].copy()


def append_rf1022_total_row(rf1022_df: pd.DataFrame | None) -> pd.DataFrame:
    """Return RF-1022 overview rows with a report-style SUM row appended."""
    data_df = _without_total_row(rf1022_df)
    if data_df.empty:
        return pd.DataFrame(columns=list(RF1022_OVERVIEW_COLUMNS))

    total_row: dict[str, object] = {column_id: "" for column_id in RF1022_OVERVIEW_COLUMNS}
    total_row.update(
        {
            "GroupId": RF1022_TOTAL_ROW_ID,
            "Kontrollgruppe": "SUM",
            "GL_Belop": _sum_col(data_df, "GL_Belop"),
            "SamledeYtelser": _sum_col(data_df, "SamledeYtelser"),
            "A07": _sum_col(data_df, "A07"),
            "Diff": _sum_col(data_df, "Diff"),
            "AgaGrunnlag": _sum_col(data_df, "AgaGrunnlag"),
            "A07Aga": _sum_col(data_df, "A07Aga"),
            "AgaDiff": _sum_col(data_df, "AgaDiff"),
            "Status": "Sum",
            "AntallKontoer": _sum_col(data_df, "AntallKontoer"),
        }
    )
    return pd.concat([data_df, pd.DataFrame([total_row])], ignore_index=True).reindex(
        columns=list(RF1022_OVERVIEW_COLUMNS),
        fill_value="",
    )


def _card(key: str, title: str, value: str, detail: str, status: str) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "value": value,
        "detail": detail,
        "status": status,
    }


def build_rf1022_summary_cards(rf1022_df: pd.DataFrame | None) -> list[dict[str, str]]:
    """Build compact report summary cards for the RF-1022 reconciliation view."""
    data_df = _without_total_row(rf1022_df)
    if data_df.empty:
        return [
            _card("opplysning", "Opplysningspliktig", "-", "Ingen poster", "neutral"),
            _card("aga", "AGA-pliktig", "-", "Ingen poster", "neutral"),
            _card("uavklart", "Uavklart RF-1022", "-", "Ingen poster", "neutral"),
            _card("status", "Status", "-", "Ingen poster", "neutral"),
        ]

    opplys_gl = _sum_col(data_df, "SamledeYtelser")
    opplys_a07 = _sum_col(data_df, "A07")
    opplys_diff = _sum_col(data_df, "Diff")
    aga_gl = _sum_col(data_df, "AgaGrunnlag")
    aga_a07 = _sum_col(data_df, "A07Aga")
    aga_diff = _sum_col(data_df, "AgaDiff")
    if "GroupId" in data_df.columns:
        group_series = data_df["GroupId"].astype(str)
    else:
        group_series = pd.Series([""] * len(data_df.index), index=data_df.index)
    unresolved_df = data_df.loc[group_series == RF1022_UNKNOWN_GROUP]
    unresolved_amount = _sum_col(unresolved_df, "A07")
    unresolved_count = int(len(unresolved_df.index))
    open_rows = sum(
        1
        for _, row in data_df.iterrows()
        if abs(_to_number(row.get("Diff"))) > 0.005
        or abs(_to_number(row.get("AgaDiff"))) > 0.005
        or str(row.get("GroupId") or "").strip() == RF1022_UNKNOWN_GROUP
    )
    done_rows = max(int(len(data_df.index)) - int(open_rows), 0)

    return [
        _card(
            "opplysning",
            "Opplysningspliktig",
            f"Diff {format_number_no(opplys_diff, 2)}",
            f"GL {format_number_no(opplys_gl, 2)} | A07 {format_number_no(opplys_a07, 2)}",
            "ok" if abs(opplys_diff) <= 0.005 else "review",
        ),
        _card(
            "aga",
            "AGA-pliktig",
            f"Diff {format_number_no(aga_diff, 2)}",
            f"GL {format_number_no(aga_gl, 2)} | A07 {format_number_no(aga_a07, 2)}",
            "ok" if abs(aga_diff) <= 0.005 else "review",
        ),
        _card(
            "uavklart",
            "Uavklart RF-1022",
            format_number_no(unresolved_amount, 2),
            f"{unresolved_count} poster uten standardpost",
            "warning" if unresolved_count or abs(unresolved_amount) > 0.005 else "ok",
        ),
        _card(
            "status",
            "Status",
            f"{done_rows}/{len(data_df.index)} avstemt",
            f"{open_rows} poster maa vurderes" if open_rows else "Alle poster gaar i null",
            "ok" if open_rows == 0 else "review",
        ),
    ]


__all__ = [
    "RF1022_TOTAL_ROW_ID",
    "append_rf1022_total_row",
    "build_rf1022_summary_cards",
]
