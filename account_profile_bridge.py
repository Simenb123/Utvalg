from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from account_profile import (
    AccountClassificationCatalog,
    AccountClassificationCatalogEntry,
    AccountProfile,
    AccountProfileDocument,
    AccountProfileSource,
    AccountProfileStore,
    migrate_legacy_group_mapping,
)

LEGACY_DEFAULT_GROUPS: tuple[str, ...] = (
    "Skyldig MVA",
    "Inngående MVA",
    "Utgående MVA",
    "Lønnskostnad",
    "Feriepenger",
    "Skyldig lønn",
    "Skyldig feriepenger",
    "Skyldig arbeidsgiveravgift",
    "Skyldig arbeidsgiveravgift av feriepenger",
    "Kostnadsført arbeidsgiveravgift",
    "Kostnadsført arbeidsgiveravgift av feriepenger",
    "Pensjonskostnad",
    "Skyldig pensjon",
    "Betalbar skatt",
    "Utsatt skatt",
    "Skattetrekk",
    "Driftskonto",
    "Skattetrekkskonto",
    "Sparekonto",
    "Kundefordringer",
    "Leverandørgjeld",
    "Mellomværende konsern",
    "Ansvarlig lån",
    "Maskiner og utstyr",
    "Inventar",
    "IT-utstyr",
    "Biler",
    "Gevinst-/tapskonto",
    "Egenkapital",
    "Utbytte",
)


def build_legacy_default_catalog() -> AccountClassificationCatalog:
    entries = tuple(
        AccountClassificationCatalogEntry(
            id=group_name,
            label=group_name,
            category="legacy_group",
            sort_order=index,
            applies_to=("analyse", "kontrolloppstilling"),
        )
        for index, group_name in enumerate(LEGACY_DEFAULT_GROUPS, start=1)
    )
    return AccountClassificationCatalog(groups=entries, tags=())


def legacy_group_mapping_from_document(document: AccountProfileDocument) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for account_no, profile in document.profiles.items():
        if profile.control_group:
            mapping[account_no] = profile.control_group
    return mapping


def a07_mapping_from_document(document: AccountProfileDocument) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for account_no, profile in document.profiles.items():
        if profile.a07_code:
            mapping[account_no] = profile.a07_code
    return mapping


def load_profiles_with_legacy_fallback(
    *,
    store_path: str | Path,
    client: str,
    year: int | None = None,
    legacy_mapping: dict[str, str] | None = None,
) -> AccountProfileDocument:
    store = AccountProfileStore(store_path)
    if Path(store_path).exists():
        return store.load(client=client, year=year)
    if legacy_mapping:
        return migrate_legacy_group_mapping(
            client=client,
            year=year,
            legacy_mapping=legacy_mapping,
        )
    return AccountProfileDocument(client=client, year=year)


def save_profiles_with_legacy_shadow(
    *,
    store_path: str | Path,
    document: AccountProfileDocument,
) -> tuple[Path, dict[str, str]]:
    store = AccountProfileStore(store_path)
    saved_path = store.save(document)
    return saved_path, legacy_group_mapping_from_document(document)


def apply_legacy_group_changes(
    document: AccountProfileDocument,
    updates: dict[str, str | None],
    *,
    source: AccountProfileSource = "manual",
    confidence: float | None = 1.0,
) -> AccountProfileDocument:
    updated_profiles = dict(document.profiles)
    for raw_account_no, raw_group in (updates or {}).items():
        account_no = str(raw_account_no).strip()
        if not account_no:
            continue
        group_name = None if raw_group is None else str(raw_group).strip()
        current = updated_profiles.get(account_no)
        current_group = str(current.control_group or "").strip() if current is not None else ""
        next_group = group_name or ""
        if not group_name:
            if current is None:
                continue
            if not current_group:
                continue
            stripped = current.with_updates(
                control_group="",
                source=source,
                confidence=confidence,
            )
            updated_profiles[account_no] = replace(stripped, control_tags=current.control_tags)
            continue
        base = current or AccountProfile(account_no=account_no)
        if current is not None and current_group == next_group:
            continue
        updated_profiles[account_no] = base.with_updates(
            control_group=group_name,
            source=source,
            confidence=confidence,
        )
    return AccountProfileDocument(
        client=document.client,
        year=document.year,
        schema_version=document.schema_version,
        profiles=updated_profiles,
    )


def replace_control_groups_from_legacy_mapping(
    document: AccountProfileDocument,
    mapping: dict[str, str],
    *,
    source: AccountProfileSource = "manual",
    confidence: float | None = 1.0,
) -> AccountProfileDocument:
    target_mapping = {
        str(account_no).strip(): str(group_name).strip()
        for account_no, group_name in (mapping or {}).items()
        if str(account_no).strip()
    }
    updates: dict[str, str | None] = {}
    for account_no, profile in document.profiles.items():
        updates[account_no] = target_mapping.get(account_no)
        if not profile.control_group and account_no not in target_mapping:
            updates.pop(account_no, None)
    for account_no, group_name in target_mapping.items():
        updates[account_no] = group_name
    return apply_legacy_group_changes(
        document,
        updates,
        source=source,
        confidence=confidence,
    )


def replace_a07_codes_from_mapping(
    document: AccountProfileDocument,
    mapping: dict[str, str],
    *,
    source: AccountProfileSource = "manual",
    confidence: float | None = 1.0,
) -> AccountProfileDocument:
    target_mapping = {
        str(account_no).strip(): str(code).strip()
        for account_no, code in (mapping or {}).items()
        if str(account_no).strip()
    }
    updated_profiles = dict(document.profiles)
    for account_no in set(updated_profiles) | set(target_mapping):
        code = target_mapping.get(account_no, "")
        current = updated_profiles.get(account_no)
        if current is None:
            if not code:
                continue
            updated_profiles[account_no] = AccountProfile(
                account_no=account_no,
                a07_code=code,
                source=source,
                confidence=confidence,
            )
            continue
        current_code = str(current.a07_code or "").strip()
        if current_code == code:
            continue
        updated_profiles[account_no] = current.with_updates(
            a07_code=code,
            source=source,
            confidence=confidence,
        )
    return AccountProfileDocument(
        client=document.client,
        year=document.year,
        schema_version=document.schema_version,
        profiles=updated_profiles,
    )


def apply_profile_field_updates(
    document: AccountProfileDocument,
    updates: dict[str, dict[str, object]],
    *,
    source: AccountProfileSource = "manual",
    confidence: float | None = 1.0,
) -> AccountProfileDocument:
    updated_profiles = dict(document.profiles)
    for raw_account_no, raw_fields in (updates or {}).items():
        account_no = str(raw_account_no or "").strip()
        if not account_no or not isinstance(raw_fields, dict):
            continue

        current = updated_profiles.get(account_no) or AccountProfile(account_no=account_no)
        kwargs: dict[str, object] = {
            "source": source,
            "confidence": confidence,
        }
        if "account_name" in raw_fields:
            kwargs["account_name"] = str(raw_fields.get("account_name") or "").strip()
        if "a07_code" in raw_fields:
            kwargs["a07_code"] = str(raw_fields.get("a07_code") or "").strip()
        if "control_group" in raw_fields:
            kwargs["control_group"] = str(raw_fields.get("control_group") or "").strip()
        if "control_tags" in raw_fields:
            raw_tags = raw_fields.get("control_tags")
            if isinstance(raw_tags, (list, tuple, set)):
                kwargs["control_tags"] = tuple(str(tag or "").strip() for tag in raw_tags if str(tag or "").strip())
            else:
                kwargs["control_tags"] = ()
        if "detail_class_id" in raw_fields:
            kwargs["detail_class_id"] = str(raw_fields.get("detail_class_id") or "").strip()
        if "owned_company_orgnr" in raw_fields:
            kwargs["owned_company_orgnr"] = str(raw_fields.get("owned_company_orgnr") or "").strip()
        if "locked" in raw_fields:
            kwargs["locked"] = bool(raw_fields.get("locked"))

        updated_profiles[account_no] = current.with_updates(**kwargs)

    return AccountProfileDocument(
        client=document.client,
        year=document.year,
        schema_version=document.schema_version,
        profiles=updated_profiles,
    )
