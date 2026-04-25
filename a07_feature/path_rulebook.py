from __future__ import annotations

import json
import shutil
from pathlib import Path

import classification_config

from . import SuggestConfig
from .path_shared import MATCHER_SETTINGS_DEFAULTS


def default_global_rulebook_path() -> Path:
    return classification_config.resolve_rulebook_path()


def bundled_default_rulebook_path() -> Path | None:
    return None


def ensure_default_rulebook_exists() -> Path | None:
    target = default_global_rulebook_path()
    try:
        if target.exists():
            return target
    except Exception:
        pass

    source = bundled_default_rulebook_path()
    if source is None:
        return None

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def default_matcher_settings_path() -> Path:
    return classification_config.resolve_thresholds_path()


def resolve_rulebook_path(client: str | None, year: str | int | None) -> Path | None:
    _ = (client, year)
    try:
        return classification_config.resolve_rulebook_path()
    except Exception:
        return ensure_default_rulebook_exists()


def copy_rulebook_to_storage(source_path: str | Path) -> Path:
    source = Path(source_path)
    target = default_global_rulebook_path()
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        same = source.resolve() == target.resolve()
    except Exception:
        same = False

    if not same:
        shutil.copy2(source, target)

    return target


def _editor_list_items(text: object) -> list[str]:
    raw = str(text or "")
    parts = [
        part.strip()
        for line in raw.splitlines()
        for part in line.split(",")
        if part.strip()
    ]
    return parts


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
        keywords_raw = value.get("keywords") or value.get("name_keywords") or []
        if isinstance(keywords_raw, str):
            keywords = [part.strip() for part in keywords_raw.replace(";", "\n").replace(",", "\n").splitlines() if part.strip()]
        elif isinstance(keywords_raw, (list, tuple, set)):
            keywords = [str(part or "").strip() for part in keywords_raw if str(part or "").strip()]
        else:
            keywords = []
        basis = str(value.get("basis") or "").strip()
        weight = value.get("weight", 1.0)
        weight_text = str(weight).strip()
        parts = [account]
        if keywords:
            parts.append(", ".join(dict.fromkeys(keywords)))
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
        basis_values = {"ub", "ib", "endring", "debet", "kredit"}
        if len(parts) >= 4:
            keywords = [part.strip() for part in parts[1].replace(";", "\n").replace(",", "\n").splitlines() if part.strip()]
            basis = str(parts[2] or "").strip()
            weight_raw = str(parts[3] or "").strip()
        elif (
            len(parts) == 3
            and str(parts[1] or "").strip().casefold() not in basis_values
            and str(parts[2] or "").strip().casefold() in basis_values
        ):
            keywords = [part.strip() for part in parts[1].replace(";", "\n").replace(",", "\n").splitlines() if part.strip()]
            basis = str(parts[2] or "").strip()
            weight_raw = ""
        else:
            keywords = []
            basis = str(parts[1] or "").strip() if len(parts) >= 2 else ""
            weight_raw = str(parts[2] or "").strip() if len(parts) >= 3 else ""
        try:
            weight = float(weight_raw) if weight_raw else 1.0
        except Exception:
            weight = 1.0
        item: dict[str, object] = {"account": account}
        if keywords:
            item["keywords"] = list(dict.fromkeys(keywords))
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


def load_rulebook_document(path: str | Path | None) -> dict[str, object]:
    target = Path(path) if path else (ensure_default_rulebook_exists() or default_global_rulebook_path())
    try:
        exists = target.exists()
    except Exception:
        exists = False
    if not exists:
        return {"aliases": {}, "rules": {}}
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return {"aliases": {}, "rules": {}}
    if not isinstance(data, dict):
        return {"aliases": {}, "rules": {}}
    if not isinstance(data.get("aliases"), dict):
        data["aliases"] = {}
    if not isinstance(data.get("rules"), dict):
        data["rules"] = {}
    return data


def save_rulebook_document(path: str | Path, document: dict[str, object]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def normalize_matcher_settings(data: object) -> dict[str, float | int]:
    defaults = dict(MATCHER_SETTINGS_DEFAULTS)
    if not isinstance(data, dict):
        return defaults

    out: dict[str, float | int] = dict(defaults)

    def _read_float(name: str) -> float:
        try:
            return float(data.get(name, defaults[name]))
        except Exception:
            return float(defaults[name])

    def _read_int(name: str) -> int:
        try:
            value = int(float(data.get(name, defaults[name])))
        except Exception:
            value = int(defaults[name])
        return max(1, value)

    out["tolerance_rel"] = max(0.0, _read_float("tolerance_rel"))
    out["tolerance_abs"] = max(0.0, _read_float("tolerance_abs"))
    out["historical_account_boost"] = max(0.0, _read_float("historical_account_boost"))
    out["historical_combo_boost"] = max(0.0, _read_float("historical_combo_boost"))
    out["max_combo"] = _read_int("max_combo")
    out["candidates_per_code"] = _read_int("candidates_per_code")
    out["top_suggestions_per_code"] = _read_int("top_suggestions_per_code")
    return out


def load_matcher_settings(path: str | Path | None = None) -> dict[str, float | int]:
    target = Path(path) if path else classification_config.resolve_thresholds_path()
    try:
        exists = target.exists()
    except Exception:
        exists = False
    if not exists:
        return normalize_matcher_settings({})
    try:
        with open(target, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return normalize_matcher_settings({})
    return normalize_matcher_settings(data)


def save_matcher_settings(data: object, path: str | Path | None = None) -> Path:
    target = Path(path) if path else classification_config.repo_thresholds_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_matcher_settings(data)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def build_suggest_config(
    rulebook_path: str | Path | None,
    matcher_settings: object,
    *,
    basis_col: str | None = None,
) -> SuggestConfig:
    settings = normalize_matcher_settings(matcher_settings)
    return SuggestConfig(
        rulebook_path=str(rulebook_path) if rulebook_path else None,
        tolerance_rel=float(settings["tolerance_rel"]),
        tolerance_abs=float(settings["tolerance_abs"]),
        max_combo=int(settings["max_combo"]),
        candidates_per_code=int(settings["candidates_per_code"]),
        top_suggestions_per_code=int(settings["top_suggestions_per_code"]),
        historical_account_boost=float(settings["historical_account_boost"]),
        historical_combo_boost=float(settings["historical_combo_boost"]),
        basis_strategy="per_code",
        basis=str(basis_col or "Endring"),
    )


def build_rule_form_values(code: str, raw_rule: object) -> dict[str, str]:
    rule = raw_rule if isinstance(raw_rule, dict) else {}
    basis = str(rule.get("basis") or "").strip()
    expected_sign = rule.get("expected_sign")
    return {
        "code": str(code or "").strip(),
        "label": str(rule.get("label") or "").strip(),
        "category": str(rule.get("category") or "").strip(),
        "allowed_ranges": _format_editor_ranges(rule.get("allowed_ranges", [])),
        "keywords": _format_editor_list(rule.get("keywords", [])),
        "exclude_keywords": _format_editor_list(rule.get("exclude_keywords", [])),
        "boost_accounts": _format_editor_list(rule.get("boost_accounts", [])),
        "basis": basis,
        "expected_sign": "" if expected_sign in (None, "") else str(expected_sign),
        "special_add": _format_special_add_editor(rule.get("special_add", [])),
    }


def build_rule_payload(
    form_values: dict[str, object],
    *,
    existing_rule: object = None,
) -> tuple[str, dict[str, object]]:
    code = str(form_values.get("code") or "").strip()
    if not code:
        raise ValueError("Kode maa fylles ut.")

    raw = dict(existing_rule) if isinstance(existing_rule, dict) else {}

    def _set_or_remove(name: str, value: object) -> None:
        empty = value in (None, "", [], ())
        if empty:
            raw.pop(name, None)
        else:
            raw[name] = value

    _set_or_remove("label", str(form_values.get("label") or "").strip())
    _set_or_remove("category", str(form_values.get("category") or "").strip())
    _set_or_remove("allowed_ranges", _editor_list_items(form_values.get("allowed_ranges")))
    _set_or_remove("keywords", _editor_list_items(form_values.get("keywords")))
    _set_or_remove("exclude_keywords", _editor_list_items(form_values.get("exclude_keywords")))
    _set_or_remove("boost_accounts", _parse_editor_ints(form_values.get("boost_accounts")))
    _set_or_remove("special_add", _parse_special_add_editor(form_values.get("special_add")))

    basis = str(form_values.get("basis") or "").strip()
    _set_or_remove("basis", basis if basis in {"UB", "IB", "Endring", "Debet", "Kredit"} else "")

    expected_sign_raw = str(form_values.get("expected_sign") or "").strip()
    if expected_sign_raw in {"-1", "0", "1"}:
        raw["expected_sign"] = int(expected_sign_raw)
    else:
        raw.pop("expected_sign", None)

    return code, raw
