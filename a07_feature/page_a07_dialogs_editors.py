from __future__ import annotations

from typing import Sequence


def apply_manual_mapping_choice(
    mapping: dict[str, str],
    konto: str | None,
    kode: str | None,
) -> tuple[str, str]:
    konto_s = str(konto or "").strip()
    kode_s = str(kode or "").strip()
    if not konto_s:
        raise ValueError("Mangler konto for mapping.")
    if not kode_s:
        raise ValueError("Mangler A07-kode for mapping.")
    mapping[konto_s] = kode_s
    return konto_s, kode_s


def apply_manual_mapping_choices(
    mapping: dict[str, str],
    accounts: Sequence[object],
    kode: str | None,
) -> list[str]:
    kode_s = str(kode or "").strip()
    if not kode_s:
        raise ValueError("Mangler A07-kode for mapping.")
    assigned: list[str] = []
    seen: set[str] = set()
    for account in accounts or ():
        konto_s = str(account or "").strip()
        if not konto_s or konto_s in seen:
            continue
        apply_manual_mapping_choice(mapping, konto_s, kode_s)
        assigned.append(konto_s)
        seen.add(konto_s)
    if not assigned:
        raise ValueError("Mangler konto for mapping.")
    return assigned


def remove_mapping_accounts(mapping: dict[str, str], accounts: Sequence[object]) -> list[str]:
    removed: list[str] = []
    seen: set[str] = set()
    for account in accounts or ():
        konto_s = str(account or "").strip()
        if not konto_s or konto_s in seen:
            continue
        seen.add(konto_s)
        if konto_s in mapping:
            mapping.pop(konto_s, None)
            removed.append(konto_s)
    return removed


def _editor_list_items(text: object) -> list[str]:
    raw = str(text or "")
    return [
        part.strip()
        for line in raw.splitlines()
        for part in line.split(",")
        if part.strip()
    ]


def _format_editor_list(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return ", ".join(out)


def _format_editor_ranges(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    out: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            start = str(value[0]).strip()
            end = str(value[1]).strip()
            if start and end:
                out.append(f"{start}-{end}" if start != end else start)
                continue
        text = str(value or "").strip()
        if text:
            out.append(text)
    return "\n".join(out)


def _parse_editor_ints(text: object) -> list[int]:
    out: list[int] = []
    for item in _editor_list_items(text):
        digits = "".join(ch for ch in item if ch.isdigit())
        if digits:
            out.append(int(digits))
    return out


def _format_special_add_editor(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    lines: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        account = str(value.get("account") or "").strip()
        if not account:
            continue
        basis = str(value.get("basis") or "").strip()
        weight = value.get("weight", 1.0)
        weight_text = str(weight).strip()
        parts = [account]
        if basis or weight_text:
            parts.append(basis)
        if weight_text:
            parts.append(weight_text)
        lines.append(" | ".join(parts))
    return "\n".join(lines)


def _parse_special_add_editor(text: object) -> list[dict[str, object]]:
    lines = str(text or "").splitlines()
    out: list[dict[str, object]] = []
    for raw_line in lines:
        line = str(raw_line).strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if not parts:
            continue
        account = str(parts[0] or "").strip()
        if not account:
            continue
        basis = str(parts[1] or "").strip() if len(parts) >= 2 else ""
        weight_raw = str(parts[2] or "").strip() if len(parts) >= 3 else ""
        try:
            weight = float(weight_raw) if weight_raw else 1.0
        except Exception:
            weight = 1.0
        item: dict[str, object] = {"account": account}
        if basis:
            item["basis"] = basis
        if weight != 1.0:
            item["weight"] = weight
        out.append(item)
    return out


def _format_aliases_editor(aliases: object) -> str:
    if not isinstance(aliases, dict):
        return ""
    lines: list[str] = []
    for raw_key in sorted(aliases, key=lambda value: str(value).lower()):
        key = str(raw_key or "").strip()
        raw_values = aliases.get(raw_key)
        if not key or not isinstance(raw_values, (list, tuple)):
            continue
        values = [str(value).strip() for value in raw_values if str(value).strip()]
        lines.append(f"{key} = {', '.join(values)}" if values else key)
    return "\n".join(lines)


def _parse_aliases_editor(text: object) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for raw_line in str(text or "").splitlines():
        line = str(raw_line).strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key_raw, values_raw = line.split("=", 1)
        else:
            key_raw, values_raw = line, ""
        key = str(key_raw or "").strip()
        if not key:
            continue
        out[key] = _editor_list_items(values_raw)
    return out
