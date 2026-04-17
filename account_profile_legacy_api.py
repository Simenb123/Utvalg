from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import pandas as pd

from account_profile import (
    AccountProfileDocument,
    AccountProfileSource,
    AccountProfileStore,
)
from account_profile_bridge import (
    apply_profile_field_updates,
    a07_mapping_from_document,
    legacy_group_mapping_from_document,
    load_profiles_with_legacy_fallback,
    replace_a07_codes_from_mapping,
    replace_control_groups_from_legacy_mapping,
    save_profiles_with_legacy_shadow,
)
from account_profile_catalog import load_account_classification_catalog
from account_profile_reporting import (
    AccountProfileRow,
    ControlStatementRow,
    build_account_profile_rows,
    build_control_statement_rows,
)
import payroll_classification

PreferenceGetter = Callable[[str], Any]
PreferenceSetter = Callable[[str, Any], None]


def safe_client_slug(client: str) -> str:
    raw = str(client or "default")
    cleaned = "".join(char if char.isalnum() else "_" for char in raw)
    return cleaned or "default"


def legacy_pref_key(client: str) -> str:
    return f"konto_klassifisering.{safe_client_slug(client)}.mapping"


def account_profile_store_path(
    base_dir: str | Path,
    *,
    client: str,
    year: int | None = None,
) -> Path:
    root = Path(base_dir)
    if year is None:
        return root / safe_client_slug(client) / "account_profiles.json"
    return root / safe_client_slug(client) / str(int(year)) / "account_profiles.json"


def load_legacy_preferences_mapping(*, client: str, getter: PreferenceGetter | None) -> dict[str, str]:
    if getter is None:
        return {}
    raw = getter(legacy_pref_key(client))
    if not isinstance(raw, dict):
        return {}
    return {
        str(account_no).strip(): str(group_name).strip()
        for account_no, group_name in raw.items()
        if str(account_no).strip() and str(group_name).strip()
    }


def save_legacy_preferences_mapping(
    *,
    client: str,
    mapping: dict[str, str],
    setter: PreferenceSetter | None,
) -> None:
    if setter is None:
        return
    setter(
        legacy_pref_key(client),
        {
            str(account_no).strip(): str(group_name).strip()
            for account_no, group_name in mapping.items()
            if str(account_no).strip() and str(group_name).strip()
        },
    )


def get_group(mapping: dict[str, str], konto: str | int) -> str:
    return mapping.get(str(konto).strip(), "")


def all_groups_in_use(mapping: dict[str, str]) -> list[str]:
    return sorted({str(group_name).strip() for group_name in mapping.values() if str(group_name).strip()})


def kontoer_for_group(mapping: dict[str, str], group: str) -> list[str]:
    target = str(group).strip()
    return sorted(account_no for account_no, group_name in mapping.items() if str(group_name).strip() == target)


def build_group_lookup(mapping: dict[str, str], kontoer: list[str]) -> dict[str, str]:
    return {
        str(account_no): mapping[str(account_no)]
        for account_no in kontoer
        if str(account_no) in mapping
    }


def default_groups(catalog_path: str | Path | None = None) -> list[str]:
    catalog = load_account_classification_catalog(catalog_path)
    entries = sorted(
        catalog.active_groups(),
        key=lambda entry: (entry.sort_order, entry.label.casefold()),
    )
    return [entry.label for entry in entries]


DEFAULT_GROUPS = default_groups()


@dataclass(frozen=True)
class AccountProfileLegacyApi:
    base_dir: Path
    catalog_path: Path | None = None

    def store_path(self, *, client: str, year: int | None = None) -> Path:
        return account_profile_store_path(self.base_dir, client=client, year=year)

    def load_catalog(self):
        return load_account_classification_catalog(self.catalog_path)

    def default_groups(self) -> list[str]:
        return default_groups(self.catalog_path)

    def load_document(
        self,
        *,
        client: str,
        year: int | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
    ) -> AccountProfileDocument:
        fallback = legacy_mapping
        if fallback is None:
            fallback = load_legacy_preferences_mapping(client=client, getter=getter)
        return load_profiles_with_legacy_fallback(
            store_path=self.store_path(client=client, year=year),
            client=client,
            year=year,
            legacy_mapping=fallback,
        )

    def load_mapping(
        self,
        *,
        client: str,
        year: int | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
    ) -> dict[str, str]:
        document = self.load_document(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
            getter=getter,
        )
        return legacy_group_mapping_from_document(document)

    def save_document(
        self,
        *,
        client: str,
        document: AccountProfileDocument,
        year: int | None = None,
        setter: PreferenceSetter | None = None,
    ) -> tuple[AccountProfileDocument, Path, dict[str, str]]:
        store = AccountProfileStore(self.store_path(client=client, year=year))
        saved_path = store.save(document)
        shadow_mapping = legacy_group_mapping_from_document(document)
        save_legacy_preferences_mapping(
            client=client,
            mapping=shadow_mapping,
            setter=setter,
        )
        return document, saved_path, shadow_mapping

    def load_a07_mapping(
        self,
        *,
        client: str,
        year: int | None = None,
        getter: PreferenceGetter | None = None,
    ) -> dict[str, str]:
        document = self.load_document(
            client=client,
            year=year,
            getter=getter,
        )
        raw_mapping = a07_mapping_from_document(document)
        filtered: dict[str, str] = {}
        for account_no, code in raw_mapping.items():
            account_s = str(account_no).strip()
            code_s = str(code).strip()
            if not account_s or not code_s:
                continue
            profile = document.get(account_s)
            issue = payroll_classification.suspicious_saved_payroll_profile_issue(
                account_no=account_s,
                account_name=str(getattr(profile, "account_name", "") or ""),
                current_profile=profile,
            )
            if issue:
                continue
            filtered[account_s] = code_s
        return filtered

    def save_mapping(
        self,
        *,
        client: str,
        mapping: dict[str, str],
        year: int | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
        setter: PreferenceSetter | None = None,
        source: AccountProfileSource = "manual",
        confidence: float | None = 1.0,
    ) -> tuple[AccountProfileDocument, Path, dict[str, str]]:
        base_document = self.load_document(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
            getter=getter,
        )
        updated_document = replace_control_groups_from_legacy_mapping(
            base_document,
            mapping,
            source=source,
            confidence=confidence,
        )
        saved_path, shadow_mapping = save_profiles_with_legacy_shadow(
            store_path=self.store_path(client=client, year=year),
            document=updated_document,
        )
        save_legacy_preferences_mapping(
            client=client,
            mapping=shadow_mapping,
            setter=setter,
        )
        return updated_document, saved_path, shadow_mapping

    def save_a07_mapping(
        self,
        *,
        client: str,
        mapping: dict[str, str],
        year: int | None = None,
        getter: PreferenceGetter | None = None,
        source: AccountProfileSource = "manual",
        confidence: float | None = 1.0,
    ) -> tuple[AccountProfileDocument, Path, dict[str, str]]:
        base_document = self.load_document(
            client=client,
            year=year,
            getter=getter,
        )
        updated_document = replace_a07_codes_from_mapping(
            base_document,
            mapping,
            source=source,
            confidence=confidence,
        )
        store = AccountProfileStore(self.store_path(client=client, year=year))
        saved_path = store.save(updated_document)
        return updated_document, saved_path, a07_mapping_from_document(updated_document)

    def update_profiles(
        self,
        *,
        client: str,
        updates: dict[str, dict[str, object]],
        year: int | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
        setter: PreferenceSetter | None = None,
        source: AccountProfileSource = "manual",
        confidence: float | None = 1.0,
    ) -> tuple[AccountProfileDocument, Path, dict[str, str]]:
        base_document = self.load_document(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
            getter=getter,
        )
        updated_document = apply_profile_field_updates(
            base_document,
            updates,
            source=source,
            confidence=confidence,
        )
        return self.save_document(
            client=client,
            document=updated_document,
            year=year,
            setter=setter,
        )

    def load_store(self, *, client: str, year: int | None = None) -> AccountProfileStore:
        return AccountProfileStore(self.store_path(client=client, year=year))

    def build_profile_rows(
        self,
        *,
        client: str,
        accounts: Sequence[tuple[str, str]] | pd.DataFrame,
        year: int | None = None,
        suggestions: Mapping[str, object] | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
    ) -> list[AccountProfileRow]:
        document = self.load_document(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
            getter=getter,
        )
        return build_account_profile_rows(
            accounts,
            document,
            suggestions=suggestions,
        )

    def build_control_statement_rows(
        self,
        *,
        client: str,
        gl_df: pd.DataFrame,
        year: int | None = None,
        legacy_mapping: dict[str, str] | None = None,
        getter: PreferenceGetter | None = None,
        include_unclassified: bool = False,
    ) -> list[ControlStatementRow]:
        document = self.load_document(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
            getter=getter,
        )
        return build_control_statement_rows(
            gl_df,
            document,
            catalog=self.load_catalog(),
            include_unclassified=include_unclassified,
        )
