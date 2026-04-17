from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from account_profile import (
    AccountClassificationCatalog,
    AccountClassificationCatalogEntry,
    AccountProfileDocument,
    AccountProfileSuggestion,
)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _number(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = _clean_text(value).replace("\u00a0", " ").replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except Exception:
        return 0.0


@dataclass(frozen=True)
class AccountProfileRow:
    account_no: str
    account_name: str
    a07_code: str | None
    control_group: str | None
    control_tags: tuple[str, ...]
    source: str | None
    confidence: float | None
    locked: bool
    suggested_a07_code: str | None = None
    suggested_control_group: str | None = None
    suggested_control_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ControlStatementRow:
    group_id: str
    label: str
    ib: float
    movement: float
    ub: float
    account_count: int
    accounts: tuple[str, ...]
    source_breakdown: tuple[str, ...] = ()


def _iter_accounts(accounts: Sequence[tuple[str, str]] | pd.DataFrame) -> list[tuple[str, str]]:
    if isinstance(accounts, pd.DataFrame):
        if "Konto" not in accounts.columns:
            return []
        names = accounts["Navn"] if "Navn" in accounts.columns else pd.Series([""] * len(accounts))
        return [
            (_clean_text(account_no), _clean_text(account_name))
            for account_no, account_name in zip(accounts["Konto"], names, strict=False)
            if _clean_text(account_no)
        ]
    return [(_clean_text(account_no), _clean_text(account_name)) for account_no, account_name in accounts if _clean_text(account_no)]


def build_account_profile_rows(
    accounts: Sequence[tuple[str, str]] | pd.DataFrame,
    document: AccountProfileDocument,
    *,
    suggestions: Mapping[str, object] | None = None,
) -> list[AccountProfileRow]:
    rows: list[AccountProfileRow] = []
    suggestion_lookup = dict(suggestions or {})
    for account_no, account_name in _iter_accounts(accounts):
        profile = document.get(account_no)
        raw_suggestions = suggestion_lookup.get(account_no)
        suggestion_map: dict[str, AccountProfileSuggestion] = {}
        if isinstance(raw_suggestions, AccountProfileSuggestion):
            suggestion_map[raw_suggestions.field_name] = raw_suggestions
        elif isinstance(raw_suggestions, Mapping):
            suggestion_map = {
                str(field_name): suggestion
                for field_name, suggestion in raw_suggestions.items()
                if isinstance(suggestion, AccountProfileSuggestion)
            }
        elif isinstance(raw_suggestions, Sequence) and not isinstance(raw_suggestions, (str, bytes)):
            suggestion_map = {
                suggestion.field_name: suggestion
                for suggestion in raw_suggestions
                if isinstance(suggestion, AccountProfileSuggestion)
            }
        rows.append(
            AccountProfileRow(
                account_no=account_no,
                account_name=account_name or (profile.account_name if profile else ""),
                a07_code=profile.a07_code if profile else None,
                control_group=profile.control_group if profile else None,
                control_tags=profile.control_tags if profile else (),
                source=profile.source if profile else None,
                confidence=profile.confidence if profile else None,
                locked=bool(profile.locked) if profile else False,
                suggested_a07_code=(
                    str(suggestion_map["a07_code"].value)
                    if "a07_code" in suggestion_map and isinstance(suggestion_map["a07_code"].value, str)
                    else None
                ),
                suggested_control_group=(
                    str(suggestion_map["control_group"].value)
                    if "control_group" in suggestion_map and isinstance(suggestion_map["control_group"].value, str)
                    else None
                ),
                suggested_control_tags=(
                    suggestion_map["control_tags"].value
                    if "control_tags" in suggestion_map and isinstance(suggestion_map["control_tags"].value, tuple)
                    else ()
                ),
            )
        )
    return rows


def _catalog_label(group_id: str, catalog: AccountClassificationCatalog | None) -> str:
    if not group_id:
        return ""
    if catalog is None:
        return group_id
    return catalog.group_label(group_id, fallback=group_id)


def _catalog_sort_key(
    group_id: str,
    catalog: AccountClassificationCatalog | None,
) -> tuple[int, int, str]:
    if group_id == "__unclassified__":
        return (2, 999999, group_id.lower())
    if catalog is None:
        return (1, 999999, group_id.lower())
    entry = catalog.group_by_id(group_id)
    if entry is None:
        return (1, 999999, group_id.lower())
    return (0, int(entry.sort_order), entry.label.lower() or group_id.lower())


def _build_control_group_entries(
    document: AccountProfileDocument,
    catalog: AccountClassificationCatalog | None,
) -> dict[str, AccountClassificationCatalogEntry | None]:
    used_groups = {
        profile.control_group
        for profile in document.profiles.values()
        if profile.control_group
    }
    entries: dict[str, AccountClassificationCatalogEntry | None] = {}
    for group_id in used_groups:
        if not group_id:
            continue
        entry = catalog.group_by_id(group_id) if catalog is not None else None
        if entry is not None and "kontrolloppstilling" not in entry.applies_to:
            continue
        if entry is not None and not entry.active:
            continue
        entries[group_id] = entry
    return entries


def build_control_statement_rows(
    gl_df: pd.DataFrame,
    document: AccountProfileDocument,
    *,
    catalog: AccountClassificationCatalog | None = None,
    include_unclassified: bool = False,
) -> list[ControlStatementRow]:
    if gl_df is None or len(gl_df) == 0 or "Konto" not in gl_df.columns:
        return []

    group_entries = _build_control_group_entries(document, catalog)
    grouped: dict[str, dict[str, object]] = {}

    for _, row in gl_df.iterrows():
        account_no = _clean_text(row.get("Konto"))
        if not account_no:
            continue
        profile = document.get(account_no)
        group_id = profile.control_group if profile else None
        if not group_id:
            if not include_unclassified:
                continue
            group_id = "__unclassified__"
        elif group_id not in group_entries and not include_unclassified:
            continue

        bucket = grouped.setdefault(
            group_id,
            {
                "ib": 0.0,
                "movement": 0.0,
                "ub": 0.0,
                "accounts": [],
                "sources": set(),
            },
        )
        bucket["ib"] = float(bucket["ib"]) + _number(row.get("IB"))
        bucket["movement"] = float(bucket["movement"]) + _number(row.get("Endring"))
        bucket["ub"] = float(bucket["ub"]) + _number(row.get("UB"))
        bucket["accounts"].append(account_no)
        if profile and profile.source:
            cast_sources = bucket["sources"]
            assert isinstance(cast_sources, set)
            cast_sources.add(profile.source)

    rows: list[ControlStatementRow] = []
    for group_id in sorted(grouped, key=lambda value: _catalog_sort_key(value, catalog)):
        bucket = grouped[group_id]
        accounts = sorted(set(bucket["accounts"]))  # type: ignore[arg-type]
        label = "Uklassifisert" if group_id == "__unclassified__" else _catalog_label(group_id, catalog)
        source_breakdown = tuple(sorted(bucket["sources"]))  # type: ignore[arg-type]
        rows.append(
            ControlStatementRow(
                group_id=group_id,
                label=label,
                ib=float(bucket["ib"]),
                movement=float(bucket["movement"]),
                ub=float(bucket["ub"]),
                account_count=len(accounts),
                accounts=tuple(accounts),
                source_breakdown=source_breakdown,
            )
        )
    return rows
