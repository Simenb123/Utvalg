from __future__ import annotations

from typing import Any

from document_engine.profiles import (
    apply_supplier_profile as engine_apply_supplier_profile,
    build_supplier_profile as engine_build_supplier_profile,
    match_supplier_profile as engine_match_supplier_profile,
    normalize_profile_name,
)


def build_supplier_profile(
    fields: dict[str, str],
    raw_text: str,
    *,
    existing_profile: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    profile = engine_build_supplier_profile(fields, raw_text, existing_profile=existing_profile)
    return profile.to_dict() if profile is not None else None


def apply_supplier_profile(profile: dict[str, Any] | None, raw_text: str) -> dict[str, str]:
    return engine_apply_supplier_profile(profile, raw_text)


def match_supplier_profile(
    profiles: dict[str, dict[str, Any]] | None,
    fields: dict[str, str],
    raw_text: str,
) -> tuple[dict[str, Any] | None, float]:
    profile, score = engine_match_supplier_profile(profiles, fields, raw_text)
    return (profile.to_dict() if profile is not None else None), score


__all__ = [
    "apply_supplier_profile",
    "build_supplier_profile",
    "match_supplier_profile",
    "normalize_profile_name",
]
