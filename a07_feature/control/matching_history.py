from __future__ import annotations

import pandas as pd


def accounts_for_code(mapping: dict[str, str], code: str | None) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    accounts = [
        str(account).strip()
        for account, mapped_code in (mapping or {}).items()
        if str(account).strip() and str(mapped_code).strip() == code_s
    ]
    return sorted(set(accounts), key=lambda value: (len(value), value))


def _gl_accounts(gl_df: pd.DataFrame) -> set[str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return set()
    return {
        str(account).strip()
        for account in gl_df["Konto"].astype(str).tolist()
        if str(account).strip()
    }


def safe_previous_accounts_for_code(
    code: str | None,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    previous_accounts = accounts_for_code(mapping_previous, code_s)
    if not previous_accounts:
        return []

    if accounts_for_code(mapping_current, code_s):
        return []

    gl_accounts = _gl_accounts(gl_df)
    if any(account not in gl_accounts for account in previous_accounts):
        return []

    for account in previous_accounts:
        existing_code = str((mapping_current or {}).get(account) or "").strip()
        if existing_code and existing_code != code_s:
            return []

    return previous_accounts


def select_safe_history_codes(history_compare_df: pd.DataFrame) -> list[str]:
    if history_compare_df is None or history_compare_df.empty:
        return []
    if "Kode" not in history_compare_df.columns or "KanBrukes" not in history_compare_df.columns:
        return []

    selected: list[str] = []
    seen_codes: set[str] = set()
    for _, row in history_compare_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code in seen_codes:
            continue
        if not bool(row.get("KanBrukes", False)):
            continue
        selected.append(code)
        seen_codes.add(code)
    return selected


__all__ = [
    "_gl_accounts",
    "accounts_for_code",
    "safe_previous_accounts_for_code",
    "select_safe_history_codes",
]
