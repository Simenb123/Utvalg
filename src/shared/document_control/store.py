from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import app_paths
from document_engine.models import PROFILE_SCHEMA_VERSION, SupplierProfile
from document_engine.ports import ProfileRepository
from document_engine.profiles import (
    GLOBAL_PROFILE_KEY,
    build_global_profile,
    build_supplier_profile,
    export_profiles_payload,
    import_profiles_payload,
    profile_key_from_fields,
)


StorePathProvider = Callable[[], Path]


class LocalJsonProfileRepository(ProfileRepository):
    def __init__(self, path_provider: StorePathProvider | None = None, *, source_app: str = "Utvalg-1") -> None:
        self._path_provider = path_provider or _store_path
        self._source_app = source_app

    def load_profiles(self) -> dict[str, SupplierProfile]:
        store = load_document_store(path_provider=self._path_provider)
        raw_profiles = dict(store.get("profiles", {}) or {})
        profiles: dict[str, SupplierProfile] = {}
        for key, payload in raw_profiles.items():
            profile = SupplierProfile.from_dict(payload)
            if profile is None:
                profile = SupplierProfile(profile_key=str(key))
            if not profile.profile_key:
                profile.profile_key = str(key)
            if not profile.schema_version:
                profile.schema_version = PROFILE_SCHEMA_VERSION
            if not profile.source_app:
                profile.source_app = self._source_app
            profiles[profile.profile_key] = profile
        return profiles

    def save_profile(self, profile: SupplierProfile) -> SupplierProfile:
        if not profile.profile_key:
            raise ValueError("Supplier profile mangler profile_key.")

        store = load_document_store(path_provider=self._path_provider)
        profiles = store.setdefault("profiles", {})
        payload = profile.to_dict()
        payload["schema_version"] = int(payload.get("schema_version", PROFILE_SCHEMA_VERSION) or PROFILE_SCHEMA_VERSION)
        if not payload.get("source_app"):
            payload["source_app"] = self._source_app
        profiles[profile.profile_key] = payload

        # Regenerate global profile from all supplier profiles
        if profile.profile_key != GLOBAL_PROFILE_KEY:
            global_profile = build_global_profile(profiles)
            if global_profile is not None:
                profiles[GLOBAL_PROFILE_KEY] = global_profile.to_dict()

        _write_store(store, path_provider=self._path_provider)
        return SupplierProfile.from_dict(profiles[profile.profile_key]) or profile

    def upsert_from_document(self, fields: dict[str, str], raw_text: str) -> SupplierProfile | None:
        profile_key = profile_key_from_fields(fields)
        if not profile_key:
            return None
        existing = self.load_profiles().get(profile_key)
        profile = build_supplier_profile(fields, raw_text, existing_profile=existing, source_app=self._source_app)
        if profile is None:
            return None
        return self.save_profile(profile)


def record_key(client: str | None, year: str | None, bilag: str | None) -> str:
    client_key = (client or "ukjent-klient").strip() or "ukjent-klient"
    year_key = (year or "ukjent-år").strip() or "ukjent-år"
    bilag_key = (bilag or "ukjent-bilag").strip() or "ukjent-bilag"
    return f"{client_key}::{year_key}::{bilag_key}"


def load_document_store(*, path_provider: StorePathProvider | None = None) -> dict[str, Any]:
    path = (path_provider or _store_path)()
    if not path.exists():
        return {"records": {}, "profiles": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("records", {})
        data.setdefault("profiles", {})
        return data
    except Exception:
        return {"records": {}, "profiles": {}}


def load_document_record(
    client: str | None,
    year: str | None,
    bilag: str | None,
    *,
    path_provider: StorePathProvider | None = None,
) -> dict[str, Any] | None:
    store = load_document_store(path_provider=path_provider)
    return store.get("records", {}).get(record_key(client, year, bilag))


def save_document_record(
    client: str | None,
    year: str | None,
    bilag: str | None,
    payload: dict[str, Any],
    *,
    path_provider: StorePathProvider | None = None,
) -> dict[str, Any]:
    store = load_document_store(path_provider=path_provider)
    records = store.setdefault("records", {})

    entry = dict(payload or {})
    entry["client"] = client
    entry["year"] = year
    entry["bilag"] = bilag
    entry["updated_at"] = datetime.now(timezone.utc).isoformat()

    records[record_key(client, year, bilag)] = entry
    _write_store(store, path_provider=path_provider)
    return entry


def load_supplier_profiles(*, path_provider: StorePathProvider | None = None) -> dict[str, dict[str, Any]]:
    repository = LocalJsonProfileRepository(path_provider=path_provider)
    return {key: profile.to_dict() for key, profile in repository.load_profiles().items()}


def load_supplier_profile(profile_key: str | None, *, path_provider: StorePathProvider | None = None) -> dict[str, Any] | None:
    if not profile_key:
        return None
    profiles = load_supplier_profiles(path_provider=path_provider)
    return profiles.get(profile_key)


def save_supplier_profile(profile: dict[str, Any], *, path_provider: StorePathProvider | None = None) -> dict[str, Any]:
    repository = LocalJsonProfileRepository(path_provider=path_provider)
    saved = repository.save_profile(SupplierProfile.from_dict(profile) or SupplierProfile(profile_key=""))
    return saved.to_dict()


def upsert_supplier_profile_from_document(
    fields: dict[str, str],
    raw_text: str,
    *,
    path_provider: StorePathProvider | None = None,
) -> dict[str, Any] | None:
    repository = LocalJsonProfileRepository(path_provider=path_provider)
    profile = repository.upsert_from_document(fields, raw_text)
    return profile.to_dict() if profile is not None else None


def export_supplier_profiles(
    export_path: str | Path,
    *,
    path_provider: StorePathProvider | None = None,
) -> dict[str, Any]:
    repository = LocalJsonProfileRepository(path_provider=path_provider)
    payload = export_profiles_payload(repository.load_profiles())
    target = Path(export_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "path": str(target),
        "profile_count": len(payload.get("profiles", {})),
        "schema_version": payload.get("schema_version", PROFILE_SCHEMA_VERSION),
    }


def import_supplier_profiles(
    import_path: str | Path,
    *,
    merge: bool = True,
    path_provider: StorePathProvider | None = None,
) -> dict[str, Any]:
    source = Path(import_path).expanduser()
    payload = json.loads(source.read_text(encoding="utf-8"))
    imported = import_profiles_payload(payload)
    repository = LocalJsonProfileRepository(path_provider=path_provider)
    existing = repository.load_profiles() if merge else {}

    for key, profile in imported.items():
        current = existing.get(key)
        if current is not None and merge:
            merged_payload = current.to_dict()
            merged_payload.update(profile.to_dict())
            profile = SupplierProfile.from_dict(merged_payload) or profile
        repository.save_profile(profile)

    return {
        "path": str(source),
        "profile_count": len(imported),
        "schema_version": int(payload.get("schema_version", PROFILE_SCHEMA_VERSION) or PROFILE_SCHEMA_VERSION),
    }


def _store_path() -> Path:
    return app_paths.data_file("document_control_store.json", subdir="document_control")


def _write_store(store: dict[str, Any], *, path_provider: StorePathProvider | None = None) -> None:
    path = (path_provider or _store_path)()
    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
