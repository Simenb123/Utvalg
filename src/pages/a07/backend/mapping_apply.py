from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass

import pandas as pd

from a07_feature.control.data import select_batch_suggestion_rows, select_magic_wand_suggestion_rows
from a07_feature.control.matching import safe_previous_accounts_for_code, select_safe_history_codes
from a07_feature.suggest import apply_suggestion_to_mapping


@dataclass(frozen=True)
class ApplyMappingResult:
    applied_codes: int = 0
    applied_accounts: int = 0
    skipped_codes: int = 0
    focus_code: str = ""


def _clean_set(values: Iterable[object] | None) -> set[str]:
    return {str(value).strip() for value in (values or ()) if str(value).strip()}


def _mapping_snapshot(mapping: Mapping[object, object] | None) -> dict[str, str]:
    return {str(account).strip(): str(code).strip() for account, code in dict(mapping or {}).items()}


def _changed_mapped_accounts(
    before: Mapping[str, str],
    after: Mapping[object, object] | None,
) -> set[str]:
    changed: set[str] = set()
    for account, mapped_code in dict(after or {}).items():
        account_s = str(account).strip()
        code_s = str(mapped_code).strip()
        if account_s and code_s and before.get(account_s) != code_s:
            changed.add(account_s)
    return changed


def apply_safe_history_mappings_to_mapping(
    mapping: MutableMapping[str, str],
    *,
    history_compare_df: pd.DataFrame | None,
    effective_mapping: Mapping[str, str] | None,
    effective_previous_mapping: Mapping[str, str] | None,
    gl_df: pd.DataFrame | None,
    locked_codes: Iterable[object] | None = None,
) -> ApplyMappingResult:
    applied_codes = 0
    applied_accounts = 0
    locked = _clean_set(locked_codes)
    for code in select_safe_history_codes(history_compare_df):
        code_s = str(code).strip()
        if not code_s or code_s in locked:
            continue
        accounts = safe_previous_accounts_for_code(
            code_s,
            mapping_current=effective_mapping,
            mapping_previous=effective_previous_mapping,
            gl_df=gl_df,
        )
        if not accounts:
            continue
        before = _mapping_snapshot(mapping)
        apply_suggestion_to_mapping(mapping, {"Kode": code_s, "ForslagKontoer": ",".join(accounts)})
        after_accounts = _changed_mapped_accounts(before, mapping)
        if not after_accounts:
            continue
        applied_codes += 1
        applied_accounts += len(after_accounts)
    return ApplyMappingResult(applied_codes=applied_codes, applied_accounts=applied_accounts)


def apply_safe_suggestions_to_mapping(
    mapping: MutableMapping[str, str],
    *,
    suggestions_df: pd.DataFrame | None,
    effective_mapping: Mapping[str, str] | None,
    locked_codes: Iterable[object] | None = None,
    min_score: float = 0.85,
) -> ApplyMappingResult:
    applied_codes = 0
    applied_accounts = 0
    locked = _clean_set(locked_codes)
    row_indexes = select_batch_suggestion_rows(
        suggestions_df,
        effective_mapping,
        min_score=min_score,
        locked_codes=locked,
    )
    for idx in row_indexes:
        if suggestions_df is None:
            continue
        row = suggestions_df.iloc[int(idx)]
        code = str(row.get("Kode") or "").strip()
        if code in locked:
            continue
        before = _mapping_snapshot(mapping)
        apply_suggestion_to_mapping(mapping, row)
        after_accounts = _changed_mapped_accounts(before, mapping)
        if not after_accounts:
            continue
        applied_codes += 1
        applied_accounts += len(after_accounts)
    return ApplyMappingResult(applied_codes=applied_codes, applied_accounts=applied_accounts)


def apply_magic_wand_suggestions_to_mapping(
    mapping: MutableMapping[str, str],
    *,
    suggestions_df: pd.DataFrame | None,
    effective_mapping: Mapping[str, str] | None,
    unresolved_codes: Sequence[object] | None = None,
    locked_codes: Iterable[object] | None = None,
    amount_is_exact: Callable[[pd.Series], bool] | None = None,
) -> ApplyMappingResult:
    unresolved = [str(code).strip() for code in (unresolved_codes or ()) if str(code).strip()]
    locked = _clean_set(locked_codes)
    applied_codes = 0
    applied_accounts = 0
    applied_code_values: set[str] = set()
    row_indexes = select_magic_wand_suggestion_rows(
        suggestions_df,
        effective_mapping,
        unresolved_codes=unresolved,
        locked_codes=locked,
    )
    for idx in row_indexes:
        if suggestions_df is None:
            continue
        row = suggestions_df.iloc[int(idx)]
        code = str(row.get("Kode") or "").strip()
        if code in locked:
            continue
        try:
            exact = bool(amount_is_exact(row)) if amount_is_exact is not None else abs(float(row.get("Diff") or 0.0)) <= 0.01
        except Exception:
            exact = False
        if not exact:
            continue
        before = _mapping_snapshot(mapping)
        apply_suggestion_to_mapping(mapping, row)
        after_accounts = _changed_mapped_accounts(before, mapping)
        if not after_accounts:
            continue
        applied_codes += 1
        applied_accounts += len(after_accounts)
        if code:
            applied_code_values.add(code)

    skipped = max(0, len(set(unresolved)) - len(applied_code_values))
    return ApplyMappingResult(
        applied_codes=applied_codes,
        applied_accounts=applied_accounts,
        skipped_codes=skipped,
    )


def apply_residual_changes_to_mapping(
    mapping: MutableMapping[str, str],
    changes: Iterable[object] | None,
    *,
    locked_codes: Iterable[object] | None = None,
) -> ApplyMappingResult:
    locked = _clean_set(locked_codes)
    applied_accounts: set[str] = set()
    applied_codes: set[str] = set()
    for change in tuple(changes or ()):
        account = str(getattr(change, "account", "") or "").strip()
        code = str(getattr(change, "to_code", "") or "").strip()
        from_code = str(getattr(change, "from_code", "") or "").strip()
        if not account or not code or from_code:
            continue
        if code in locked:
            continue
        current = str(mapping.get(account) or "").strip()
        if current and current != code:
            continue
        mapping[account] = code
        applied_accounts.add(account)
        applied_codes.add(code)
    return ApplyMappingResult(
        applied_codes=len(applied_codes),
        applied_accounts=len(applied_accounts),
        focus_code=(sorted(applied_codes)[0] if applied_codes else ""),
    )


__all__ = [
    "ApplyMappingResult",
    "apply_magic_wand_suggestions_to_mapping",
    "apply_residual_changes_to_mapping",
    "apply_safe_history_mappings_to_mapping",
    "apply_safe_suggestions_to_mapping",
]
