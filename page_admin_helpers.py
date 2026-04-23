from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd

import classification_config
import regnskapslinje_suggest
import session
from saldobalanse_payload import _resolve_sb_views


def _client_year() -> tuple[str, int | None]:
    client = str(getattr(session, "client", "") or "").strip()
    raw_year = getattr(session, "year", None)
    try:
        year = int(str(raw_year).strip()) if str(raw_year).strip() else None
    except Exception:
        year = None
    return client, year


def _effective_sb_rows(analyse_page: Any) -> pd.DataFrame:
    if analyse_page is None:
        return pd.DataFrame(columns=["Konto", "Kontonavn", "IB", "Endring", "UB"])
    _base_sb, _adjusted_sb, effective_sb = _resolve_sb_views(analyse_page)
    if not isinstance(effective_sb, pd.DataFrame) or effective_sb.empty:
        return pd.DataFrame(columns=["Konto", "Kontonavn", "IB", "Endring", "UB"])
    columns = {str(col).strip().lower(): col for col in effective_sb.columns}
    konto_col = columns.get("konto")
    name_col = columns.get("kontonavn")
    ib_col = columns.get("ib")
    endring_col = columns.get("endring") or columns.get("netto")
    ub_col = columns.get("ub")
    if not konto_col:
        return pd.DataFrame(columns=["Konto", "Kontonavn", "IB", "Endring", "UB"])
    rows = pd.DataFrame({"Konto": effective_sb[konto_col].astype(str).str.strip()})
    rows["Kontonavn"] = effective_sb[name_col].fillna("").astype(str) if name_col else ""
    rows["IB"] = pd.to_numeric(effective_sb[ib_col], errors="coerce").fillna(0.0) if ib_col else 0.0
    rows["UB"] = pd.to_numeric(effective_sb[ub_col], errors="coerce").fillna(0.0) if ub_col else 0.0
    if endring_col:
        rows["Endring"] = pd.to_numeric(effective_sb[endring_col], errors="coerce").fillna(0.0)
    else:
        rows["Endring"] = rows["UB"] - rows["IB"]
    return rows[["Konto", "Kontonavn", "IB", "Endring", "UB"]].reset_index(drop=True)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _format_amount(value: object) -> str:
    try:
        amount = float(value or 0.0)
    except Exception:
        amount = 0.0
    return f"{amount:,.2f}".replace(",", " ").replace(".", ",")


def _string_list(values: object) -> list[str]:
    if isinstance(values, (list, tuple, set)):
        items = values
    elif _clean_text(values):
        items = str(values).replace(";", "\n").splitlines()
    else:
        items = ()
    out: list[str] = []
    for item in items:
        text = _clean_text(item)
        if text and text not in out:
            out.append(text)
    return out


def _inline_string_list(values: object) -> list[str]:
    if isinstance(values, str):
        values = values.replace(",", "\n")
    return _string_list(values)


def _int_list(values: object) -> list[int]:
    out: list[int] = []
    for item in _string_list(values):
        try:
            parsed = int(item)
        except Exception:
            continue
        if parsed not in out:
            out.append(parsed)
    return out


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return None
    text = _clean_text(value).casefold()
    if text in {"1", "true", "ja", "j", "yes", "y"}:
        return True
    if text in {"0", "false", "nei", "n", "no"}:
        return False
    return None


def _normalize_alias_document(document: Any) -> dict[str, Any]:
    base = dict(document) if isinstance(document, dict) else {}
    raw_concepts = base.get("concepts", {})
    concepts_out: dict[str, dict[str, Any]] = {}
    if isinstance(raw_concepts, dict):
        for key, payload in raw_concepts.items():
            concept_id = _clean_text(key)
            if not concept_id or not isinstance(payload, dict):
                continue
            concepts_out[concept_id] = {
                "aliases": _string_list(payload.get("aliases")),
                "exclude_aliases": _string_list(payload.get("exclude_aliases")),
                "account_ranges": _string_list(payload.get("account_ranges")),
                "boost_accounts": _int_list(payload.get("boost_accounts")),
            }
    base["concepts"] = concepts_out
    return base


def _parse_special_add_lines(value: object) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    raw_lines = _string_list(value)
    for raw_line in raw_lines:
        parts = [part.strip() for part in str(raw_line).split("|")]
        account = _clean_text(parts[0] if parts else "")
        if not account:
            continue
        row: dict[str, Any] = {"account": account}
        basis_values = {"ub", "ib", "endring", "debet", "kredit"}
        if len(parts) >= 4:
            keywords = _inline_string_list(parts[1])
            basis = _clean_text(parts[2])
            weight_text = _clean_text(parts[3])
        elif (
            len(parts) == 3
            and _clean_text(parts[1]).casefold() not in basis_values
            and _clean_text(parts[2]).casefold() in basis_values
        ):
            keywords = _inline_string_list(parts[1])
            basis = _clean_text(parts[2])
            weight_text = ""
        else:
            keywords = []
            basis = _clean_text(parts[1] if len(parts) > 1 else "")
            weight_text = _clean_text(parts[2] if len(parts) > 2 else "")
        if keywords:
            row["keywords"] = keywords
        if basis:
            row["basis"] = basis
        if weight_text:
            try:
                row["weight"] = float(weight_text.replace(",", "."))
            except Exception:
                pass
        rows.append(row)
    return rows


def _format_special_add_lines(values: object) -> str:
    if not isinstance(values, (list, tuple)):
        return ""
    lines: list[str] = []
    for entry in values:
        if not isinstance(entry, dict):
            continue
        account = _clean_text(entry.get("account"))
        if not account:
            continue
        keywords = _inline_string_list(entry.get("keywords") or entry.get("name_keywords"))
        basis = _clean_text(entry.get("basis"))
        weight = entry.get("weight")
        parts = [account]
        if keywords:
            parts.append(", ".join(keywords))
        if basis or weight not in (None, ""):
            parts.append(basis or "")
        if weight not in (None, ""):
            try:
                weight_text = str(float(weight))
            except Exception:
                weight_text = _clean_text(weight)
            parts.append(weight_text)
        lines.append(" | ".join(parts).rstrip())
    return "\n".join(lines)


def _normalize_rulebook_document(document: Any) -> dict[str, Any]:
    base = dict(document) if isinstance(document, dict) else {}
    base.pop("aliases", None)
    raw_rules = base.get("rules", {})
    rules_out: dict[str, dict[str, Any]] = {}
    if isinstance(raw_rules, dict):
        for key, payload in raw_rules.items():
            rule_id = _clean_text(key)
            if not rule_id or not isinstance(payload, dict):
                continue
            normalized: dict[str, Any] = {}
            label = _clean_text(payload.get("label"))
            if label:
                normalized["label"] = label
            category = _clean_text(payload.get("category"))
            if category:
                normalized["category"] = category
            rf1022_group = _clean_text(payload.get("rf1022_group"))
            if rf1022_group:
                normalized["rf1022_group"] = rf1022_group
            aga_pliktig = _optional_bool(payload.get("aga_pliktig"))
            if aga_pliktig is not None:
                normalized["aga_pliktig"] = aga_pliktig
            keywords = _string_list(payload.get("keywords"))
            if keywords:
                normalized["keywords"] = keywords
            exclude_keywords = _string_list(payload.get("exclude_keywords"))
            if exclude_keywords:
                normalized["exclude_keywords"] = exclude_keywords
            allowed_ranges = _string_list(payload.get("allowed_ranges"))
            if allowed_ranges:
                normalized["allowed_ranges"] = allowed_ranges
            boost_accounts = _int_list(payload.get("boost_accounts"))
            if boost_accounts:
                normalized["boost_accounts"] = boost_accounts
            basis = _clean_text(payload.get("basis"))
            if basis:
                normalized["basis"] = basis
            expected_sign = payload.get("expected_sign")
            if expected_sign not in (None, ""):
                try:
                    sign_value = int(expected_sign)
                except Exception:
                    sign_value = None
                if sign_value in (-1, 0, 1):
                    normalized["expected_sign"] = sign_value
            special_add = payload.get("special_add")
            if isinstance(special_add, (list, tuple)):
                normalized_special = _parse_special_add_lines(_format_special_add_lines(special_add))
                if normalized_special:
                    normalized["special_add"] = normalized_special
            rules_out[rule_id] = normalized
    base["rules"] = rules_out
    return base


def _normalize_catalog_document(document: Any) -> dict[str, Any]:
    base = dict(document) if isinstance(document, dict) else {}
    for collection_name in ("groups", "tags"):
        normalized_entries: list[dict[str, Any]] = []
        raw_entries = base.get(collection_name, [])
        if isinstance(raw_entries, (list, tuple)):
            for raw_entry in raw_entries:
                if not isinstance(raw_entry, dict):
                    continue
                entry_id = _clean_text(raw_entry.get("id"))
                label = _clean_text(raw_entry.get("label"))
                if not entry_id or not label:
                    continue
                entry: dict[str, Any] = {
                    "id": entry_id,
                    "label": label,
                    "active": bool(raw_entry.get("active", True)),
                    "sort_order": int(raw_entry.get("sort_order", 0) or 0),
                    "applies_to": _string_list(raw_entry.get("applies_to")),
                    "aliases": _string_list(raw_entry.get("aliases")),
                    "exclude_aliases": _string_list(raw_entry.get("exclude_aliases")),
                }
                category = _clean_text(raw_entry.get("category"))
                if category:
                    entry["category"] = category
                normalized_entries.append(entry)
        base[collection_name] = normalized_entries
    return base


_CATALOG_AREA_PAYROLL_TAGS = "Payroll-flagg"
_CATALOG_AREA_LEGACY_GROUPS = "Legacy analysegrupper"


def _catalog_area_options() -> tuple[str, ...]:
    return (
        _CATALOG_AREA_PAYROLL_TAGS,
        _CATALOG_AREA_LEGACY_GROUPS,
    )


def _catalog_area_config(area: object) -> dict[str, Any]:
    area_text = _clean_text(area)
    mapping: dict[str, dict[str, Any]] = {
        _CATALOG_AREA_PAYROLL_TAGS: {
            "bucket": "tags",
            "categories": ("payroll_tag",),
            "default_category": "payroll_tag",
            "description": "Vedlikehold payroll-flagg her. Endringene påvirker katalog og forslag, ikke lagrede klientprofiler.",
        },
        _CATALOG_AREA_LEGACY_GROUPS: {
            "bucket": "groups",
            "categories": ("legacy_group",),
            "default_category": "legacy_group",
            "description": "Vedlikehold legacy analysegrupper her. Endringene påvirker katalog og forslag, ikke lagrede klientprofiler.",
        },
    }
    return dict(mapping.get(area_text, mapping[_CATALOG_AREA_PAYROLL_TAGS]))


def _catalog_area_matches(entry: object, allowed_categories: tuple[str, ...]) -> bool:
    payload = entry if isinstance(entry, dict) else {}
    category = _clean_text(payload.get("category"))
    if not allowed_categories:
        return True
    return category in allowed_categories


def _normalize_threshold_document(document: Any) -> dict[str, float | int]:
    from a07_feature.page_paths import normalize_matcher_settings

    return normalize_matcher_settings(document if isinstance(document, dict) else {})


def _normalize_regnskapslinje_rulebook_document(document: Any) -> dict[str, Any]:
    return regnskapslinje_suggest.normalize_rulebook_document(document)


def _alias_preview_text(values: object, *, limit: int = 3) -> str:
    aliases = _string_list(values)
    if not aliases:
        return ""
    preview = ", ".join(aliases[:limit])
    remaining = len(aliases) - limit
    if remaining > 0:
        return f"{preview} (+{remaining})"
    return preview


def _alias_concept_preview_text(concept_id: object, payload: object) -> str:
    concept_text = _clean_text(concept_id) or "-"
    data = payload if isinstance(payload, dict) else {}
    aliases = _string_list(data.get("aliases"))
    excludes = _string_list(data.get("exclude_aliases"))
    ranges = _string_list(data.get("account_ranges"))
    boosts = [str(value) for value in _int_list(data.get("boost_accounts"))]

    def _line(label: str, values: list[str], *, max_items: int = 6) -> str:
        if not values:
            return f"{label}: -"
        preview = ", ".join(values[:max_items])
        if len(values) > max_items:
            preview = f"{preview} (+{len(values) - max_items})"
        return f"{label} ({len(values)}): {preview}"

    return "\n".join(
        [
            f"Konsept: {concept_text}",
            _line("Aliaser", aliases),
            _line("Ekskluder", excludes),
            _line("Intervall", ranges, max_items=4),
            _line("Boost", boosts, max_items=6),
        ]
    )


def _saved_status_text(saved_path: object, *, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    return f"Lagret {timestamp} til {saved_path}."


def _multiline_text(values: object) -> str:
    if isinstance(values, (list, tuple, set)):
        return "\n".join(_string_list(values))
    return _clean_text(values)
