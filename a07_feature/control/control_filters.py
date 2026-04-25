from __future__ import annotations

from .queue_shared import *  # noqa: F403


def filter_suggestions_df(
    suggestions_df: pd.DataFrame,
    *,
    scope_key: str | None,
    selected_code: str | None = None,
    unresolved_code_values: Sequence[str] | None = None,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return _empty_suggestions_df()
    if "Kode" not in suggestions_df.columns:
        return suggestions_df.copy()

    scope_s = str(scope_key or "valgt_kode").strip().lower()
    work = suggestions_df.copy()
    codes = work["Kode"].astype(str).str.strip()

    if scope_s == "valgt_kode":
        code_s = str(selected_code or "").strip()
        if code_s:
            return work.loc[codes == code_s].copy()
        scope_s = "uloste"

    if scope_s == "uloste":
        unresolved_set = {str(code).strip() for code in (unresolved_code_values or []) if str(code).strip()}
        if unresolved_set:
            return work.loc[codes.isin(unresolved_set)].copy()
        return work.copy()

    return work.copy()

def filter_control_search_df(control_df: pd.DataFrame, search_text: object = "") -> pd.DataFrame:
    if control_df is None:
        return _empty_control_df()
    if control_df.empty:
        return control_df.reset_index(drop=True)

    search_s = str(search_text or "").strip().casefold()
    if not search_s:
        return control_df.reset_index(drop=True)

    haystack = pd.Series("", index=control_df.index, dtype="object")
    for column in (
        "A07Post",
        "Kode",
        "Navn",
        "Status",
        "Anbefalt",
        "NesteHandling",
        "DagensMapping",
        "Post",
        "Kontrollgruppe",
        "Omraade",
        "GroupId",
    ):
        if column in control_df.columns:
            haystack = haystack.str.cat(control_df[column].fillna("").astype(str), sep=" ")
    return control_df.loc[haystack.str.casefold().str.contains(search_s, regex=False)].reset_index(drop=True)

def filter_control_visible_codes_df(control_df: pd.DataFrame) -> pd.DataFrame:
    if control_df is None or control_df.empty:
        return _empty_control_df()
    if "Kode" not in control_df.columns:
        return control_df.reset_index(drop=True)
    hidden = {value.casefold() for value in _CONTROL_HIDDEN_CODES}
    codes = control_df["Kode"].fillna("").astype(str).str.strip().str.casefold()
    return control_df.loc[~codes.isin(hidden)].copy().reset_index(drop=True)

def _account_series_filter_digits(value: object) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set, frozenset)):
        raw_values = list(value)
    else:
        text = str(value or "").strip()
        if not text or text.casefold() == "alle":
            return set()
        raw_values = [
            part.strip()
            for part in text.replace(";", ",").replace("|", ",").split(",")
            if part.strip()
        ]
    digits: set[str] = set()
    for raw in raw_values:
        text = str(raw or "").strip().lower()
        if not text or text == "alle":
            continue
        first = text[0:1]
        if first.isdigit():
            digits.add(first)
    return digits

def filter_control_gl_df(
    control_gl_df: pd.DataFrame,
    *,
    search_text: object = "",
    mapping_filter: object = "alle",
    account_series: object = "alle",
    only_unmapped: bool = False,
    active_only: bool = False,
) -> pd.DataFrame:
    if control_gl_df is None or control_gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    filtered = control_gl_df.copy()
    if active_only:
        numeric_cols = [column for column in ("IB", "Endring", "UB") if column in filtered.columns]
        if numeric_cols:
            numeric = filtered[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            has_activity = numeric.ne(0).any(axis=1)
        else:
            has_activity = pd.Series(False, index=filtered.index)
        if "Kode" in filtered.columns:
            has_mapping = filtered["Kode"].fillna("").astype(str).str.strip() != ""
            filtered = filtered.loc[has_activity | has_mapping].copy()
        else:
            filtered = filtered.loc[has_activity].copy()
    if only_unmapped and "Kode" in filtered.columns:
        filtered = filtered.loc[filtered["Kode"].astype(str).str.strip() == ""].copy()
    mapping_filter_s = str(mapping_filter or "alle").strip().casefold()
    if mapping_filter_s == "mappede" and "Kode" in filtered.columns:
        filtered = filtered.loc[filtered["Kode"].astype(str).str.strip() != ""].copy()
    elif mapping_filter_s == "umappede" and "Kode" in filtered.columns:
        filtered = filtered.loc[filtered["Kode"].astype(str).str.strip() == ""].copy()

    account_series_digits = _account_series_filter_digits(account_series)
    if account_series_digits and "Konto" in filtered.columns:
        filtered = filtered.loc[
            filtered["Konto"].fillna("").astype(str).str.strip().str[:1].isin(account_series_digits)
        ].copy()

    search_s = str(search_text or "").strip().casefold()
    if search_s:
        haystack = pd.Series("", index=filtered.index, dtype="object")
        for column in ("Konto", "Navn", "Kode", "AliasStatus", "MappingAuditStatus", "MappingAuditReason"):
            if column in filtered.columns:
                haystack = haystack.str.cat(filtered[column].fillna("").astype(str), sep=" ")
        filtered = filtered.loc[haystack.str.casefold().str.contains(search_s, regex=False)].copy()

    return filtered.reset_index(drop=True)

def filter_control_queue_by_rf1022_group(
    control_df: pd.DataFrame,
    group_id: object | None,
) -> pd.DataFrame:
    if control_df is None or control_df.empty:
        return _empty_control_df()
    group_s = str(group_id or "").strip()
    if not group_s:
        return control_df.reset_index(drop=True)
    if "Rf1022GroupId" not in control_df.columns:
        return control_df.reset_index(drop=True)
    mask = control_df["Rf1022GroupId"].fillna("").astype(str).str.strip() == group_s
    return control_df.loc[mask].reset_index(drop=True)

def filter_suggestions_for_rf1022_group(
    suggestions_df: pd.DataFrame,
    group_id: object | None,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return _empty_suggestions_df()
    group_s = str(group_id or "").strip()
    if not group_s or "Kode" not in suggestions_df.columns:
        return suggestions_df.reset_index(drop=True)
    allowed_codes = set(rf1022_group_a07_codes(group_s))
    if not allowed_codes:
        return _empty_suggestions_df()
    codes = suggestions_df["Kode"].fillna("").astype(str).str.strip()
    mask = codes.apply(lambda code: a07_code_rf1022_group(code) == group_s)
    return suggestions_df.loc[mask].reset_index(drop=True)

def preferred_rf1022_overview_group(
    rf1022_df: pd.DataFrame | None,
    available_groups: Sequence[object] | None = None,
    *,
    preferred_group: object | None = None,
) -> str | None:
    available_list = [
        str(group_id or "").strip()
        for group_id in (available_groups or [])
        if str(group_id or "").strip()
    ]
    available = set(available_list)
    preferred = str(preferred_group or "").strip()
    if preferred and (not available or preferred in available):
        return preferred
    if rf1022_df is None or rf1022_df.empty or "GroupId" not in rf1022_df.columns:
        return available_list[0] if available_list else None

    work = rf1022_df.copy()
    work["GroupId"] = work["GroupId"].fillna("").astype(str).str.strip()
    if available:
        work = work.loc[work["GroupId"].isin(available)].copy()
    if work.empty:
        return available_list[0] if available_list else None

    unknown_rows = work.loc[work["GroupId"] == RF1022_UNKNOWN_GROUP].copy()
    if not unknown_rows.empty:
        amount_series = pd.Series(0.0, index=unknown_rows.index)
        for column in ("A07", "A07_Belop", "Diff", "GL_Belop"):
            if column in unknown_rows.columns:
                amount_series = amount_series.combine(
                    pd.to_numeric(unknown_rows[column], errors="coerce").fillna(0.0).abs(),
                    max,
                )
        if bool((amount_series > 0.005).any()):
            return RF1022_UNKNOWN_GROUP

    if "Diff" in work.columns:
        diff_abs = pd.to_numeric(work["Diff"], errors="coerce").fillna(0.0).abs()
        if bool((diff_abs > 0.005).any()):
            return str(work.loc[diff_abs.idxmax(), "GroupId"] or "").strip() or None

    for _, row in work.iterrows():
        group_id = str(row.get("GroupId") or "").strip()
        if group_id:
            return group_id
    return available_list[0] if available_list else None

