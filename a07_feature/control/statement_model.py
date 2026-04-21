from __future__ import annotations

import pandas as pd


CONTROL_STATEMENT_COLUMNS = (
    "Gruppe",
    "Navn",
    "IB",
    "Endring",
    "UB",
    "A07",
    "Diff",
    "Status",
    "AntallKontoer",
    "Kontoer",
    "Kilder",
)

CONTROL_STATEMENT_VIEW_ALL = "all"
CONTROL_STATEMENT_VIEW_PAYROLL = "payroll"
CONTROL_STATEMENT_VIEW_LEGACY = "legacy"
CONTROL_STATEMENT_VIEW_UNCLASSIFIED = "unclassified"
CONTROL_STATEMENT_VIEW_LABELS = {
    CONTROL_STATEMENT_VIEW_PAYROLL: "Payroll",
    CONTROL_STATEMENT_VIEW_ALL: "Alle",
    CONTROL_STATEMENT_VIEW_LEGACY: "Legacy analyse",
    CONTROL_STATEMENT_VIEW_UNCLASSIFIED: "Uklassifisert",
}

CONTROL_STATEMENT_PAYROLL_ORDER = (
    "100_loenn_ol",
    "100_refusjon",
    "111_naturalytelser",
    "112_pensjon",
    "Lønnskostnad",
    "Feriepenger",
    "Skattetrekk",
    "Kostnadsført arbeidsgiveravgift",
    "Kostnadsført arbeidsgiveravgift av feriepenger",
    "Skyldig lønn",
    "Skyldig feriepenger",
    "Skyldig arbeidsgiveravgift",
    "Skyldig arbeidsgiveravgift av feriepenger",
    "Pensjonskostnad",
    "Skyldig pensjon",
)
CONTROL_STATEMENT_PAYROLL_SET = set(CONTROL_STATEMENT_PAYROLL_ORDER)


def empty_control_statement_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(CONTROL_STATEMENT_COLUMNS))


def _stringify(value: object) -> str:
    return str(value or "").strip()


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([None] * len(frame), index=frame.index, dtype="object")
    return pd.to_numeric(frame[column], errors="coerce")


def normalize_control_statement_view(view: object) -> str:
    view_s = _stringify(view).casefold()
    if view_s in {
        CONTROL_STATEMENT_VIEW_ALL,
        CONTROL_STATEMENT_VIEW_PAYROLL,
        CONTROL_STATEMENT_VIEW_LEGACY,
        CONTROL_STATEMENT_VIEW_UNCLASSIFIED,
    }:
        return view_s
    for key, label in CONTROL_STATEMENT_VIEW_LABELS.items():
        if view_s == _stringify(label).casefold():
            return key
    return CONTROL_STATEMENT_VIEW_PAYROLL


def control_statement_view_requires_unclassified(view: object) -> bool:
    normalized = normalize_control_statement_view(view)
    return normalized in {CONTROL_STATEMENT_VIEW_ALL, CONTROL_STATEMENT_VIEW_UNCLASSIFIED}


def normalize_control_statement_df(control_statement_df: pd.DataFrame | None) -> pd.DataFrame:
    if control_statement_df is None or control_statement_df.empty:
        return empty_control_statement_df()

    work = control_statement_df.copy()
    for column in CONTROL_STATEMENT_COLUMNS:
        if column not in work.columns:
            work[column] = ""

    work = work.reindex(columns=list(CONTROL_STATEMENT_COLUMNS), fill_value="")
    for column in ("Gruppe", "Navn", "Status", "Kontoer", "Kilder"):
        work[column] = work[column].map(_stringify)

    missing_names = work["Navn"].eq("")
    if missing_names.any():
        work.loc[missing_names, "Navn"] = work.loc[missing_names, "Gruppe"].replace({"__unclassified__": "Uklassifisert"})

    for column in ("IB", "Endring", "UB", "A07", "Diff"):
        numeric = _numeric_series(work, column)
        work[column] = numeric.where(numeric.notna(), None)

    account_counts = _numeric_series(work, "AntallKontoer").fillna(0).astype(int)
    work["AntallKontoer"] = account_counts
    return work.reset_index(drop=True)


def _sort_rank_for_group(group_id: str, *, view: str) -> tuple[int, int, str]:
    group_s = _stringify(group_id)
    if view == CONTROL_STATEMENT_VIEW_PAYROLL:
        if group_s == "__unclassified__":
            return (2, 999998, "uklassifisert")
        if group_s in CONTROL_STATEMENT_PAYROLL_SET:
            return (0, CONTROL_STATEMENT_PAYROLL_ORDER.index(group_s), group_s.casefold())
        return (1, 999999, group_s.casefold())
    if group_s == "__unclassified__":
        return (1, 999999, "uklassifisert")
    return (0, 999998, group_s.casefold())


def filter_control_statement_df(
    control_statement_df: pd.DataFrame | None,
    *,
    view: str = CONTROL_STATEMENT_VIEW_PAYROLL,
) -> pd.DataFrame:
    work = normalize_control_statement_df(control_statement_df)
    if work.empty:
        return work

    view_s = normalize_control_statement_view(view)
    groups = work["Gruppe"].astype(str).str.strip()

    if view_s == CONTROL_STATEMENT_VIEW_ALL:
        filtered = work
    elif view_s == CONTROL_STATEMENT_VIEW_LEGACY:
        filtered = work.loc[(~groups.isin(CONTROL_STATEMENT_PAYROLL_SET)) & groups.ne("__unclassified__")].copy()
    elif view_s == CONTROL_STATEMENT_VIEW_UNCLASSIFIED:
        filtered = work.loc[groups.eq("__unclassified__")].copy()
    else:
        filtered = work.loc[groups.isin(CONTROL_STATEMENT_PAYROLL_SET) | groups.eq("__unclassified__")].copy()
        if filtered.empty:
            filtered = work.copy()

    filtered["_group_sort"] = filtered["Gruppe"].astype(str).map(
        lambda value: _sort_rank_for_group(value, view=view_s)
    )
    filtered = filtered.sort_values(by=["_group_sort", "Navn", "Gruppe"], kind="stable")
    return filtered.drop(columns=["_group_sort"], errors="ignore").reset_index(drop=True)
