from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Iterable, Literal

ACCOUNT_PROFILE_SCHEMA_VERSION = 1
AccountProfileSource = Literal["heuristic", "history", "manual", "legacy", "unknown"]


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _repair_label_text(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return cleaned
    if "Ã" not in cleaned and "Â" not in cleaned:
        return cleaned
    try:
        repaired = cleaned.encode("latin-1").decode("utf-8")
    except Exception:
        return cleaned
    return _clean_text(repaired) or cleaned


def _clean_account_no(value: str | int) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError("account_no must not be empty")
    return cleaned


def normalize_profile_year(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def _clean_tags(values: Iterable[str] | None) -> tuple[str, ...]:
    if not values:
        return ()
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in values:
        tag = _clean_text(raw)
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    return tuple(cleaned)


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class AccountProfileSuggestion:
    field_name: str
    value: str | tuple[str, ...] | None
    source: AccountProfileSource = "heuristic"
    confidence: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: str | list[str] | None
        if isinstance(self.value, tuple):
            value = list(self.value)
        else:
            value = self.value
        return {
            "field_name": self.field_name,
            "value": value,
            "source": self.source,
            "confidence": self.confidence,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountProfileSuggestion":
        raw_value = data.get("value")
        if isinstance(raw_value, list):
            value: str | tuple[str, ...] | None = _clean_tags(raw_value)
        else:
            value = _clean_text(raw_value)
        return cls(
            field_name=str(data.get("field_name", "")).strip(),
            value=value,
            source=str(data.get("source", "heuristic") or "heuristic"),  # type: ignore[arg-type]
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            reason=_clean_text(data.get("reason")),
        )


def _clean_orgnr(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if cleaned is None:
        return None
    digits = "".join(ch for ch in cleaned if ch.isdigit())
    return digits or None


@dataclass(frozen=True)
class AccountProfile:
    account_no: str
    account_name: str = ""
    a07_code: str | None = None
    control_group: str | None = None
    control_tags: tuple[str, ...] = ()
    detail_class_id: str | None = None
    owned_company_orgnr: str | None = None
    source: AccountProfileSource = "unknown"
    confidence: float | None = None
    locked: bool = False
    last_updated: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "account_no", _clean_account_no(self.account_no))
        object.__setattr__(self, "account_name", str(self.account_name or "").strip())
        object.__setattr__(self, "a07_code", _clean_text(self.a07_code))
        object.__setattr__(self, "control_group", _clean_text(self.control_group))
        object.__setattr__(self, "control_tags", _clean_tags(self.control_tags))
        object.__setattr__(self, "detail_class_id", _clean_text(self.detail_class_id))
        object.__setattr__(self, "owned_company_orgnr", _clean_orgnr(self.owned_company_orgnr))
        object.__setattr__(self, "last_updated", _clean_text(self.last_updated) or _utc_now_iso())
        if self.confidence is not None:
            conf = max(0.0, min(1.0, float(self.confidence)))
            object.__setattr__(self, "confidence", conf)

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_no": self.account_no,
            "account_name": self.account_name,
            "a07_code": self.a07_code,
            "control_group": self.control_group,
            "control_tags": list(self.control_tags),
            "detail_class_id": self.detail_class_id,
            "owned_company_orgnr": self.owned_company_orgnr,
            "source": self.source,
            "confidence": self.confidence,
            "locked": self.locked,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountProfile":
        return cls(
            account_no=data.get("account_no", ""),
            account_name=str(data.get("account_name", "") or ""),
            a07_code=data.get("a07_code"),
            control_group=data.get("control_group"),
            control_tags=_clean_tags(data.get("control_tags")),
            detail_class_id=data.get("detail_class_id"),
            owned_company_orgnr=data.get("owned_company_orgnr"),
            source=str(data.get("source", "unknown") or "unknown"),  # type: ignore[arg-type]
            confidence=float(data["confidence"]) if data.get("confidence") is not None else None,
            locked=bool(data.get("locked", False)),
            last_updated=data.get("last_updated"),
        )

    def with_updates(
        self,
        *,
        account_name: str | None = None,
        a07_code: str | None = None,
        control_group: str | None = None,
        control_tags: Iterable[str] | None = None,
        detail_class_id: str | None = None,
        owned_company_orgnr: str | None = None,
        source: AccountProfileSource | None = None,
        confidence: float | None = None,
        locked: bool | None = None,
    ) -> "AccountProfile":
        return AccountProfile(
            account_no=self.account_no,
            account_name=self.account_name if account_name is None else account_name,
            a07_code=self.a07_code if a07_code is None else a07_code,
            control_group=self.control_group if control_group is None else control_group,
            control_tags=self.control_tags if control_tags is None else tuple(control_tags),
            detail_class_id=self.detail_class_id if detail_class_id is None else detail_class_id,
            owned_company_orgnr=(
                self.owned_company_orgnr if owned_company_orgnr is None else owned_company_orgnr
            ),
            source=self.source if source is None else source,
            confidence=self.confidence if confidence is None else confidence,
            locked=self.locked if locked is None else locked,
            last_updated=_utc_now_iso(),
        )


@dataclass(frozen=True)
class AccountClassificationCatalogEntry:
    id: str
    label: str
    category: str = ""
    active: bool = True
    sort_order: int = 0
    applies_to: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    exclude_aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        cleaned_id = _clean_text(self.id)
        cleaned_label = _repair_label_text(self.label)
        if not cleaned_id:
            raise ValueError("catalog entry id must not be empty")
        if not cleaned_label:
            raise ValueError("catalog entry label must not be empty")
        object.__setattr__(self, "id", cleaned_id)
        object.__setattr__(self, "label", cleaned_label)
        object.__setattr__(self, "category", str(self.category or "").strip())
        object.__setattr__(self, "applies_to", _clean_tags(self.applies_to))
        object.__setattr__(
            self,
            "aliases",
            tuple(alias for alias in (_repair_label_text(alias) for alias in self.aliases) if alias),
        )
        object.__setattr__(
            self,
            "exclude_aliases",
            tuple(alias for alias in (_repair_label_text(alias) for alias in self.exclude_aliases) if alias),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "category": self.category,
            "active": self.active,
            "sort_order": self.sort_order,
            "applies_to": list(self.applies_to),
            "aliases": list(self.aliases),
            "exclude_aliases": list(self.exclude_aliases),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountClassificationCatalogEntry":
        return cls(
            id=data.get("id", ""),
            label=data.get("label", ""),
            category=str(data.get("category", "") or ""),
            active=bool(data.get("active", True)),
            sort_order=int(data.get("sort_order", 0) or 0),
            applies_to=_clean_tags(data.get("applies_to")),
            aliases=_clean_tags(data.get("aliases")),
            exclude_aliases=_clean_tags(data.get("exclude_aliases")),
        )


@dataclass(frozen=True)
class AccountClassificationCatalog:
    groups: tuple[AccountClassificationCatalogEntry, ...] = ()
    tags: tuple[AccountClassificationCatalogEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "groups": [entry.to_dict() for entry in self.groups],
            "tags": [entry.to_dict() for entry in self.tags],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountClassificationCatalog":
        return cls(
            groups=tuple(
                AccountClassificationCatalogEntry.from_dict(entry)
                for entry in data.get("groups", [])
                if isinstance(entry, dict)
            ),
            tags=tuple(
                AccountClassificationCatalogEntry.from_dict(entry)
                for entry in data.get("tags", [])
                if isinstance(entry, dict)
            ),
        )

    def active_groups(self) -> tuple[AccountClassificationCatalogEntry, ...]:
        return tuple(entry for entry in self.groups if entry.active)

    def active_tags(self) -> tuple[AccountClassificationCatalogEntry, ...]:
        return tuple(entry for entry in self.tags if entry.active)

    def group_by_id(self, group_id: str | None) -> AccountClassificationCatalogEntry | None:
        target = _clean_text(group_id)
        if not target:
            return None
        return next((entry for entry in self.groups if entry.id == target), None)

    def tag_by_id(self, tag_id: str | None) -> AccountClassificationCatalogEntry | None:
        target = _clean_text(tag_id)
        if not target:
            return None
        return next((entry for entry in self.tags if entry.id == target), None)

    def active_groups_for(self, scope: str | None = None) -> tuple[AccountClassificationCatalogEntry, ...]:
        scope_name = _clean_text(scope)
        groups = self.active_groups()
        if not scope_name:
            return groups
        return tuple(
            entry
            for entry in groups
            if not entry.applies_to or scope_name in entry.applies_to
        )

    def active_tags_for(self, scope: str | None = None) -> tuple[AccountClassificationCatalogEntry, ...]:
        scope_name = _clean_text(scope)
        tags = self.active_tags()
        if not scope_name:
            return tags
        return tuple(
            entry
            for entry in tags
            if not entry.applies_to or scope_name in entry.applies_to
        )

    def group_label(self, group_id: str | None, *, fallback: str = "") -> str:
        target = _clean_text(group_id)
        if not target:
            return fallback
        entry = self.group_by_id(target)
        if entry is None:
            return target
        return entry.label or target

    def tag_label(self, tag_id: str | None, *, fallback: str = "") -> str:
        target = _clean_text(tag_id)
        if not target:
            return fallback
        entry = self.tag_by_id(target)
        if entry is None:
            return target
        return entry.label or target


@dataclass(frozen=True)
class AccountProfileDocument:
    client: str
    year: int | None = None
    schema_version: int = ACCOUNT_PROFILE_SCHEMA_VERSION
    profiles: dict[str, AccountProfile] = field(default_factory=dict)

    def __post_init__(self) -> None:
        client = _clean_text(self.client)
        if not client:
            raise ValueError("client must not be empty")
        normalized: dict[str, AccountProfile] = {}
        for account_no, profile in (self.profiles or {}).items():
            if isinstance(profile, AccountProfile):
                candidate = profile
            elif isinstance(profile, dict):
                candidate = AccountProfile.from_dict(profile)
            else:
                raise TypeError("profiles values must be AccountProfile or dict")
            normalized[_clean_account_no(account_no)] = candidate
        object.__setattr__(self, "client", client)
        object.__setattr__(self, "year", normalize_profile_year(self.year))
        object.__setattr__(self, "profiles", normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "client": self.client,
            "year": self.year,
            "profiles": {
                account_no: profile.to_dict()
                for account_no, profile in sorted(self.profiles.items(), key=lambda item: item[0])
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AccountProfileDocument":
        raw_profiles = data.get("profiles", {})
        profiles: dict[str, AccountProfile | dict[str, Any]] = {}
        if isinstance(raw_profiles, dict):
            profiles = {
                str(account_no).strip(): value
                for account_no, value in raw_profiles.items()
                if str(account_no).strip()
            }
        return cls(
            client=str(data.get("client", "") or ""),
            year=normalize_profile_year(data.get("year")),
            schema_version=int(data.get("schema_version", ACCOUNT_PROFILE_SCHEMA_VERSION) or ACCOUNT_PROFILE_SCHEMA_VERSION),
            profiles=profiles,
        )

    def get(self, account_no: str | int) -> AccountProfile | None:
        return self.profiles.get(_clean_account_no(account_no))

    def upsert(self, profile: AccountProfile) -> "AccountProfileDocument":
        updated = dict(self.profiles)
        updated[profile.account_no] = profile
        return AccountProfileDocument(
            client=self.client,
            year=self.year,
            schema_version=self.schema_version,
            profiles=updated,
        )


class AccountProfileStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self, *, client: str | None = None, year: int | None = None) -> AccountProfileDocument:
        normalized_year = normalize_profile_year(year)
        if not self.path.exists():
            if client is None:
                raise FileNotFoundError(f"Account profile file does not exist: {self.path}")
            return AccountProfileDocument(client=client, year=normalized_year)
        with open(self.path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict):
            raise ValueError("Account profile document must be a JSON object")
        document = AccountProfileDocument.from_dict(payload)
        if client is not None and document.client != client:
            raise ValueError(f"Expected account profile client '{client}', got '{document.client}'")
        if normalized_year is not None and document.year != normalized_year:
            raise ValueError(f"Expected account profile year '{normalized_year}', got '{document.year}'")
        return document

    def save(self, document: AccountProfileDocument) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(self.path.parent), suffix=".tmp") as tmp:
            json.dump(document.to_dict(), tmp, ensure_ascii=False, indent=2, sort_keys=False)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self.path)
        return self.path.resolve()


def migrate_legacy_group_mapping(
    *,
    client: str,
    legacy_mapping: dict[str, str],
    year: int | None = None,
) -> AccountProfileDocument:
    profiles: dict[str, AccountProfile] = {}
    for account_no, group_name in (legacy_mapping or {}).items():
        cleaned_account_no = _clean_text(account_no)
        cleaned_group = _clean_text(group_name)
        if not cleaned_account_no or not cleaned_group:
            continue
        profile = AccountProfile(
            account_no=cleaned_account_no,
            control_group=cleaned_group,
            source="legacy",
            confidence=1.0,
            locked=False,
        )
        profiles[profile.account_no] = profile
    return AccountProfileDocument(
        client=client,
        year=normalize_profile_year(year),
        profiles=profiles,
    )
