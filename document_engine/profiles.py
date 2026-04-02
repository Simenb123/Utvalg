from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .models import PROFILE_SCHEMA_VERSION, SupplierProfile


LEARNABLE_FIELDS = (
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal_amount",
    "vat_amount",
    "total_amount",
    "currency",
)
STATIC_FIELDS = ("supplier_name", "supplier_orgnr", "currency")


def normalize_profile_name(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    value = re.sub(r"[^a-z0-9æøå ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def profile_key_from_fields(fields: dict[str, str]) -> str | None:
    orgnr = _digits_only(fields.get("supplier_orgnr", ""))
    if len(orgnr) == 9:
        return f"orgnr:{orgnr}"

    supplier_name = normalize_profile_name(fields.get("supplier_name", ""))
    if supplier_name:
        return f"name:{supplier_name}"
    return None


def build_supplier_profile(
    fields: dict[str, str],
    raw_text: str,
    *,
    existing_profile: SupplierProfile | dict[str, Any] | None = None,
    source_app: str = "Utvalg-1",
) -> SupplierProfile | None:
    profile_key = profile_key_from_fields(fields)
    if not profile_key:
        return None

    profile = _coerce_profile(existing_profile) or SupplierProfile(profile_key=profile_key)
    profile.profile_key = profile_key
    profile.schema_version = PROFILE_SCHEMA_VERSION
    profile.source_app = profile.source_app or source_app
    profile.supplier_orgnr = _digits_only(fields.get("supplier_orgnr", "")) or profile.supplier_orgnr
    profile.supplier_name = fields.get("supplier_name", "").strip() or profile.supplier_name
    profile.sample_count = int(profile.sample_count or 0) + 1
    profile.updated_at = datetime.now(timezone.utc).isoformat()

    static_fields = dict(profile.static_fields or {})
    for field_name in STATIC_FIELDS:
        value = fields.get(field_name, "").strip()
        if value:
            static_fields[field_name] = value
    profile.static_fields = static_fields

    aliases = {alias for alias in profile.aliases if alias}
    if profile.supplier_name:
        aliases.add(normalize_profile_name(profile.supplier_name))
    if profile.supplier_orgnr:
        aliases.add(profile.supplier_orgnr)
    profile.aliases = sorted(aliases)

    inferred_hints = infer_field_hints(raw_text, fields)
    merged_hints = dict(profile.field_hints or {})
    for field_name, new_hints in inferred_hints.items():
        current = list(merged_hints.get(field_name, []) or [])
        merged_hints[field_name] = _merge_hint_entries(current, new_hints)
    profile.field_hints = merged_hints
    return profile


def match_supplier_profile(
    profiles: dict[str, SupplierProfile | dict[str, Any]] | None,
    fields: dict[str, str],
    raw_text: str,
) -> tuple[SupplierProfile | None, float]:
    if not profiles:
        return None, 0.0

    normalized_profiles = {}
    for key, profile in profiles.items():
        coerced = _coerce_profile(profile)
        if coerced is not None:
            normalized_profiles[key] = coerced

    orgnr = _digits_only(fields.get("supplier_orgnr", ""))
    supplier_name = normalize_profile_name(fields.get("supplier_name", ""))
    if len(orgnr) == 9:
        profile = normalized_profiles.get(f"orgnr:{orgnr}")
        if profile and not _profile_conflicts_with_extracted_supplier(profile, supplier_name, orgnr):
            return profile, 100.0

    if supplier_name:
        profile = normalized_profiles.get(f"name:{supplier_name}")
        if profile and not _profile_conflicts_with_extracted_supplier(profile, supplier_name, orgnr):
            return profile, 80.0

    text_norm = normalize_profile_name(raw_text[:4000])
    if not text_norm:
        return None, 0.0

    best_profile: SupplierProfile | None = None
    best_score = 0.0
    for profile in normalized_profiles.values():
        if _profile_conflicts_with_extracted_supplier(profile, supplier_name, orgnr):
            continue
        for alias in list(profile.aliases or []):
            alias_norm = normalize_profile_name(alias)
            if not alias_norm:
                continue
            if alias_norm.isdigit():
                score = 95.0 if alias_norm in text_norm.replace(" ", "") else 0.0
            else:
                score = 60.0 + min(len(alias_norm), 20) if alias_norm in text_norm else 0.0
            if score > best_score:
                best_score = score
                best_profile = profile

    if best_score >= 60.0:
        return best_profile, best_score
    return None, 0.0


def _profile_conflicts_with_extracted_supplier(profile: SupplierProfile, supplier_name: str, orgnr: str) -> bool:
    profile_orgnr = _digits_only(profile.supplier_orgnr)
    if supplier_name:
        profile_names = {normalize_profile_name(profile.supplier_name)}
        profile_names.update(
            normalize_profile_name(alias)
            for alias in list(profile.aliases or [])
            if not str(alias or "").isdigit()
        )
        profile_names = {name for name in profile_names if name}
        if profile_names and supplier_name not in profile_names:
            if not any(supplier_name in name or name in supplier_name for name in profile_names):
                return True

    if orgnr and profile_orgnr and orgnr != profile_orgnr and supplier_name:
        return True
    return False


def apply_supplier_profile(
    profile: SupplierProfile | dict[str, Any] | None,
    raw_text: str,
) -> dict[str, str]:
    coerced = _coerce_profile(profile)
    if coerced is None:
        return {}

    lines = _candidate_lines(raw_text)
    if not lines:
        return {}

    values: dict[str, str] = {}
    for field_name in STATIC_FIELDS:
        value = coerced.static_fields.get(field_name, "")
        if value:
            values[field_name] = value

    for field_name, hints in dict(coerced.field_hints or {}).items():
        extracted = _extract_field_from_hints(lines, field_name, list(hints or []))
        if extracted:
            values[field_name] = extracted
    return values


def export_profiles_payload(profiles: dict[str, SupplierProfile | dict[str, Any]]) -> dict[str, Any]:
    normalized: dict[str, dict[str, Any]] = {}
    for key, profile in profiles.items():
        coerced = _coerce_profile(profile)
        if coerced is not None:
            normalized[key] = coerced.to_dict()
    return {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "profiles": normalized,
    }


def import_profiles_payload(payload: dict[str, Any] | None) -> dict[str, SupplierProfile]:
    raw_profiles = dict((payload or {}).get("profiles", {}) or {})
    imported: dict[str, SupplierProfile] = {}
    for key, raw_profile in raw_profiles.items():
        profile = SupplierProfile.from_dict(raw_profile)
        if profile is None:
            continue
        if not profile.profile_key:
            profile.profile_key = str(key)
        if not profile.schema_version:
            profile.schema_version = PROFILE_SCHEMA_VERSION
        imported[profile.profile_key] = profile
    return imported


def infer_field_hints(raw_text: str, fields: dict[str, str]) -> dict[str, list[dict[str, Any]]]:
    lines = _candidate_lines(raw_text)
    hints: dict[str, list[dict[str, Any]]] = {}

    for field_name in LEARNABLE_FIELDS:
        value = (fields.get(field_name, "") or "").strip()
        if not value:
            continue

        line, marker = _find_line_with_value(lines, field_name, value)
        if not line or not marker:
            continue

        label = _extract_label_from_line(line, marker)
        if label:
            hints.setdefault(field_name, []).append({"label": label, "count": 1})
    return hints


def normalize_hint_label(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    value = value.strip(":.- ")
    value = re.sub(r"[^a-z0-9æøå /-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) < 2 or len(value) > 40:
        return ""
    if re.search(r"\d{4,}", value):
        return ""
    return value


def _candidate_lines(raw_text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in (raw_text or "").splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line:
            lines.append(line)
    return lines


def _find_line_with_value(lines: list[str], field_name: str, value: str) -> tuple[str, str]:
    markers = _value_markers(field_name, value)
    for line in lines[:80]:
        line_norm = line.lower()
        for marker in markers:
            if marker and marker.lower() in line_norm:
                return line, marker
    return "", ""


def _value_markers(field_name: str, value: str) -> list[str]:
    value = value.strip()
    if not value:
        return []

    markers = {value}
    if field_name.endswith("_amount"):
        compact = value.replace(" ", "")
        markers.add(compact)
        markers.add(compact.replace(".", ","))
        markers.add(_format_amount_marker(compact))
        markers.add(_format_amount_marker(compact.replace(".", ",")))
    elif field_name.endswith("_date"):
        markers.add(value.replace(".", "-"))
        markers.add(value.replace(".", "/"))
        parts = value.split(".")
        if len(parts) == 3:
            day, month, year = parts
            markers.add(f"{year}-{month}-{day}")
            markers.add(f"{year}.{month}.{day}")
    elif field_name == "supplier_orgnr":
        markers.add(_digits_only(value))
    return [marker for marker in markers if marker]


def _merge_hint_entries(existing: list[dict[str, Any]], new_entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in existing + new_entries:
        label = normalize_hint_label(str(entry.get("label", "")))
        if not label:
            continue
        if label not in merged:
            merged[label] = {"label": label, "count": 0}
        merged[label]["count"] += int(entry.get("count", 1) or 1)
    return sorted(merged.values(), key=lambda item: (-int(item.get("count", 0)), item["label"]))


def _extract_label_from_line(line: str, marker: str) -> str:
    idx = line.lower().find(marker.lower())
    if idx < 0:
        return ""
    prefix = line[:idx].strip(" :-\u00a0")
    if not prefix and ":" in line:
        prefix = line.split(":", 1)[0]
    return normalize_hint_label(prefix)


def _extract_field_from_hints(lines: list[str], field_name: str, hints: list[dict[str, Any]]) -> str:
    for hint in sorted(hints, key=lambda item: -int(item.get("count", 0) or 0)):
        label = normalize_hint_label(str(hint.get("label", "")))
        if not label:
            continue
        for index, line in enumerate(lines[:120]):
            line_norm = _normalize_line_for_hint_match(line)
            if label not in line_norm:
                continue

            value = _extract_value_after_label(line, label)
            if not value and index + 1 < len(lines):
                next_line = lines[index + 1]
                if len(next_line) <= 80:
                    value = next_line.strip()
            if value:
                return value
    return ""


def _extract_value_after_label(line: str, label: str) -> str:
    pattern = re.compile(re.escape(label), re.IGNORECASE)
    match = pattern.search(line)
    if not match:
        return ""
    return line[match.end():].strip(" :-\u00a0")[:120].strip()


def _format_amount_marker(value: str) -> str:
    digits = value.replace(",", ".")
    try:
        number = float(digits)
    except Exception:
        return value
    whole, decimals = f"{number:.2f}".split(".")
    grouped = _group_thousands(whole)
    return f"{grouped},{decimals}"


def _group_thousands(number_text: str) -> str:
    parts: list[str] = []
    while number_text:
        parts.append(number_text[-3:])
        number_text = number_text[:-3]
    return " ".join(reversed(parts))


def _digits_only(value: str) -> str:
    return re.sub(r"\D+", "", value or "")


def _normalize_line_for_hint_match(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip().lower()
    value = re.sub(r"[^a-z0-9æøå /:-]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _coerce_profile(profile: SupplierProfile | dict[str, Any] | None) -> SupplierProfile | None:
    if isinstance(profile, SupplierProfile):
        return profile
    if isinstance(profile, dict):
        return SupplierProfile.from_dict(profile)
    return None
