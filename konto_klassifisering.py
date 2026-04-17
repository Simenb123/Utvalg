"""konto_klassifisering.py -- bakoverkompatibel konto->gruppe API.

Denne host-kopien sync'es inn i Utvalg-1. Modulen bruker den nye
kontoprofilmodellen som sannhet, men beholder legacy mapping i preferences som
shadow-data for bakoverkompatibilitet.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import app_paths
import classification_config
import preferences
from account_profile_legacy_api import (
    AccountProfileLegacyApi,
    all_groups_in_use as _all_groups_in_use,
    build_group_lookup,
    get_group,
    kontoer_for_group,
    legacy_pref_key,
)


def _pref_key(client: str) -> str:
    return legacy_pref_key(client)


def _profiles_base_dir() -> Path:
    return app_paths.data_dir() / "konto_klassifisering_profiles"


def _catalog_path() -> Path:
    return classification_config.resolve_catalog_path()


def _api() -> AccountProfileLegacyApi:
    return AccountProfileLegacyApi(
        base_dir=_profiles_base_dir(),
        catalog_path=_catalog_path(),
    )


DEFAULT_GROUPS: list[str] = _api().default_groups()


def load(client: str) -> dict[str, str]:
    return _api().load_mapping(
        client=client,
        getter=preferences.get,
    )


def save(client: str, mapping: dict[str, str]) -> None:
    cleaned = {
        str(account_no).strip(): str(group_name).strip()
        for account_no, group_name in (mapping or {}).items()
        if str(account_no).strip() and str(group_name).strip()
    }
    _api().save_mapping(
        client=client,
        mapping=cleaned,
        setter=preferences.set,
        getter=preferences.get,
        source="manual",
        confidence=1.0,
    )


def load_a07_mapping(client: str, *, year: int | None = None) -> dict[str, str]:
    return _api().load_a07_mapping(
        client=client,
        year=year,
        getter=preferences.get,
    )


def save_a07_mapping(client: str, mapping: dict[str, str], *, year: int | None = None) -> None:
    cleaned = {
        str(account_no).strip(): str(code).strip()
        for account_no, code in (mapping or {}).items()
        if str(account_no).strip() and str(code).strip()
    }
    _api().save_a07_mapping(
        client=client,
        year=year,
        mapping=cleaned,
        getter=preferences.get,
        source="manual",
        confidence=1.0,
    )


def load_a07_code_options(rulebook_path: str | Path | None = None) -> list[tuple[str, str]]:
    try:
        from a07_feature.suggest.rulebook import load_rulebook

        rulebook = load_rulebook(rulebook_path)
    except Exception:
        return []

    rows: list[tuple[str, str]] = []
    for code, meta in (rulebook or {}).items():
        code_text = str(code or "").strip()
        if not code_text:
            continue
        label = ""
        if isinstance(meta, dict):
            label = str(meta.get("label") or "").strip()
        else:
            label = str(getattr(meta, "label", "") or "").strip()
        rows.append((code_text, label))
    rows.sort(key=lambda item: (item[0].casefold(), item[1].casefold()))
    return rows


def all_groups_in_use(mapping: dict[str, str]) -> list[str]:
    return _all_groups_in_use(mapping)


def load_catalog() -> Any:
    return _api().load_catalog()


def load_document(client: str, *, year: int | None = None) -> Any:
    return _api().load_document(
        client=client,
        year=year,
        getter=preferences.get,
    )


def save_document(client: str, document: Any, *, year: int | None = None) -> Any:
    return _api().save_document(
        client=client,
        document=document,
        year=year,
        setter=preferences.set,
    )


def update_profiles(
    client: str,
    updates: dict[str, dict[str, object]],
    *,
    year: int | None = None,
    source: str = "manual",
    confidence: float | None = 1.0,
) -> Any:
    return _api().update_profiles(
        client=client,
        updates=updates,
        year=year,
        getter=preferences.get,
        setter=preferences.set,
        source=source,
        confidence=confidence,
    )


def default_group_entries(scope: str | None = "analyse") -> list[tuple[str, str]]:
    catalog = load_catalog()
    entries = catalog.active_groups_for(scope)
    ordered = sorted(
        entries,
        key=lambda entry: (entry.sort_order, entry.label.casefold(), entry.id.casefold()),
    )
    return [(entry.id, entry.label) for entry in ordered]


def group_label(group_id: str | None) -> str:
    return load_catalog().group_label(group_id, fallback="")


def tag_entries(scope: str | None = None) -> list[tuple[str, str]]:
    catalog = load_catalog()
    entries = catalog.active_tags_for(scope)
    ordered = sorted(
        entries,
        key=lambda entry: (entry.sort_order, entry.label.casefold(), entry.id.casefold()),
    )
    return [(entry.id, entry.label) for entry in ordered]


def tag_label(tag_id: str | None) -> str:
    return load_catalog().tag_label(tag_id, fallback="")


def group_label_map(scope: str | None = None) -> dict[str, str]:
    catalog = load_catalog()
    entries = catalog.active_groups_for(scope)
    return {entry.id: entry.label for entry in entries}


def build_profile_rows(
    client: str,
    kontoer: list[tuple[str, str]] | Any,
    *,
    year: int | None = None,
    suggestions: dict[str, object] | None = None,
) -> list[Any]:
    return _api().build_profile_rows(
        client=client,
        accounts=kontoer,
        year=year,
        suggestions=suggestions,
        getter=preferences.get,
    )


def build_control_statement_rows(
    client: str,
    gl_df: Any,
    *,
    year: int | None = None,
    include_unclassified: bool = False,
) -> list[Any]:
    return _api().build_control_statement_rows(
        client=client,
        gl_df=gl_df,
        year=year,
        getter=preferences.get,
        include_unclassified=include_unclassified,
    )
