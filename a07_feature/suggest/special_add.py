from __future__ import annotations

import re
from typing import Any, Optional, Set

import pandas as pd

from .helpers import _get_series, _konto_in_ranges, _tokenize
from .models import BASIS_UB
from .rulebook import RulebookRule


def _special_add_total(
    gl_df: pd.DataFrame,
    *,
    rule: Optional[RulebookRule],
    selected_basis: str,
    include_accounts: Optional[Set[str]] = None,
    exclude_accounts: Optional[Set[str]] = None,
) -> float:
    total, _accounts = _special_add_details(
        gl_df,
        rule=rule,
        selected_basis=selected_basis,
        include_accounts=include_accounts,
        exclude_accounts=exclude_accounts,
    )
    return total


def _special_add_ranges(account_expr: str) -> tuple[tuple[int, int], ...]:
    ranges: list[tuple[int, int]] = []
    for part in re.split(r"[|;,\n]+", str(account_expr or "")):
        text = part.strip()
        if not text:
            continue
        range_match = re.match(r"^(\d+)\s*-\s*(\d+)$", text)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            ranges.append((min(start, end), max(start, end)))
            continue
        single_match = re.match(r"^(\d+)$", text)
        if single_match:
            value = int(single_match.group(1))
            ranges.append((value, value))
    return tuple(ranges)


def _special_add_matches_row(item: Any, row: pd.Series) -> bool:
    account_expr = str(getattr(item, "account", "") or "").strip()
    if not account_expr:
        return False
    ranges = _special_add_ranges(account_expr)
    if not ranges or not _konto_in_ranges(row.get("Konto"), ranges):
        return False

    keywords = tuple(str(value or "").strip() for value in getattr(item, "keywords", ()) if str(value or "").strip())
    if not keywords:
        return True
    keyword_tokens: set[str] = set()
    for keyword in keywords:
        keyword_tokens |= _tokenize(keyword)
    if not keyword_tokens:
        return True
    name_tokens = row.get("__tokens")
    if not isinstance(name_tokens, set):
        name_tokens = _tokenize(str(row.get("Navn") or ""))
    return bool(keyword_tokens & set(name_tokens))


def _special_add_details(
    gl_df: pd.DataFrame,
    *,
    rule: Optional[RulebookRule],
    selected_basis: str,
    include_accounts: Optional[Set[str]] = None,
    exclude_accounts: Optional[Set[str]] = None,
) -> tuple[float, tuple[str, ...]]:
    include = (
        None
        if include_accounts is None
        else {str(account).strip() for account in include_accounts if str(account).strip()}
    )
    exclude = {str(account).strip() for account in (exclude_accounts or set()) if str(account).strip()}
    if rule is None or not rule.special_add or gl_df is None or gl_df.empty:
        return 0.0, ()

    gl_lookup = gl_df.copy()
    gl_lookup["Konto"] = gl_lookup["Konto"].astype(str).str.strip()
    total = 0.0
    accounts: list[str] = []
    if "__tokens" not in gl_lookup.columns:
        gl_lookup["__tokens"] = (
            gl_lookup["Navn"].map(_tokenize)
            if "Navn" in gl_lookup.columns
            else [set()] * len(gl_lookup)
        )

    for item in rule.special_add:
        basis_name = str(item.basis or selected_basis or BASIS_UB).strip() or BASIS_UB
        series = _get_series(gl_lookup, basis_name)
        mask = gl_lookup.apply(lambda gl_row: _special_add_matches_row(item, gl_row), axis=1)
        if include is not None:
            mask = mask & gl_lookup["Konto"].isin(include)
        if exclude:
            mask = mask & ~gl_lookup["Konto"].isin(exclude)
        if accounts:
            mask = mask & ~gl_lookup["Konto"].isin(accounts)
        if not bool(mask.any()):
            continue
        matched = gl_lookup.loc[mask, ["Konto"]].copy()
        matched["__amount"] = series.loc[mask]
        for account, group in matched.groupby("Konto", sort=False):
            account_s = str(account).strip()
            if not account_s or account_s in accounts:
                continue
            try:
                subtotal = float(group["__amount"].sum())
            except Exception:
                subtotal = 0.0
            if abs(subtotal) <= 0.000001:
                continue
            total += float(item.weight) * subtotal
            accounts.append(account_s)
    return float(total), tuple(accounts)


__all__ = [
    "_special_add_details",
    "_special_add_matches_row",
    "_special_add_ranges",
    "_special_add_total",
]
