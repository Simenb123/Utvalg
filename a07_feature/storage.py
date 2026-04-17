from __future__ import annotations

import json
from pathlib import Path

import app_paths
import payroll_classification
from a07_feature import mapping_source


def _read_json_object(path: str | Path) -> dict[str, object]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _write_json_object(path: str | Path, payload: dict[str, object]) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _normalize_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_year(value: object) -> int | None:
    text = _normalize_context_value(value)
    if not text:
        return None
    try:
        return int(text)
    except Exception:
        return None


def _load_profile_seed_mapping(
    *,
    client: str | None,
    year: str | int | None,
) -> tuple[dict[str, str], bool]:
    client_s = _normalize_context_value(client)
    year_i = _normalize_year(year)
    if not client_s or year_i is None:
        return {}, False

    try:
        document = mapping_source.load_current_document(client_s, year=year_i)
    except Exception:
        return {}, False

    had_profile_document = bool(getattr(document, "profiles", None))
    filtered_mapping: dict[str, str] = {}
    for account_no, profile in getattr(document, "profiles", {}).items():
        account_s = str(account_no).strip()
        code_s = str(getattr(profile, "a07_code", "") or "").strip()
        if not account_s or not code_s:
            continue
        issue = payroll_classification.suspicious_saved_payroll_profile_issue(
            account_no=account_s,
            account_name=str(getattr(profile, "account_name", "") or ""),
            current_profile=profile,
        )
        if issue:
            continue
        filtered_mapping[account_s] = code_s
    return filtered_mapping, had_profile_document


def _load_mapping_json(path: str | Path) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Mapping file does not exist: {p}")

    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Mapping JSON must be an object with account->code pairs")

    out: dict[str, str] = {}
    for k, v in data.items():
        kk = str(k).strip()
        if not kk:
            continue
        vv = "" if v is None else str(v).strip()
        out[kk] = vv
    return out


def load_mapping(
    path: str | Path,
    *,
    client: str | None = None,
    year: str | int | None = None,
    prefer_profiles: bool = False,
) -> dict[str, str]:
    p = Path(path)
    if prefer_profiles:
        client_s = _normalize_context_value(client)
        year_i = _normalize_year(year)
        if client_s and year_i is not None:
            profile_path = mapping_source.current_document_path(client_s, year=year_i)
            if profile_path.exists():
                try:
                    profile_mapping, _ = _load_profile_seed_mapping(client=client_s, year=year_i)
                    return dict(profile_mapping)
                except Exception:
                    pass
    if p.exists():
        return _load_mapping_json(p)

    profile_mapping, had_profile_document = _load_profile_seed_mapping(client=client, year=year)
    if profile_mapping:
        return dict(profile_mapping)
    if had_profile_document:
        return {}
    raise FileNotFoundError(f"Mapping file does not exist: {p}")


def save_mapping(
    path: str | Path,
    mapping: dict[str, str],
    *,
    client: str | None = None,
    year: str | int | None = None,
    source: str = "manual",
    confidence: float | None = 1.0,
    shadow_to_profiles: bool = False,
) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        str(k): ("" if v is None else str(v))
        for k, v in sorted(mapping.items(), key=lambda kv: str(kv[0]))
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    client_s = _normalize_context_value(client)
    year_i = _normalize_year(year)
    if shadow_to_profiles and client_s and year_i is not None:
        base_document = mapping_source.load_current_document(client_s, year=year_i)
        updated_document = mapping_source.document_with_updated_mapping(
            base_document,
            payload,
            source=source,
            confidence=confidence,
        )
        mapping_source.save_current_document(client_s, year_i, updated_document)
    return p


def load_locks(path: str | Path) -> set[str]:
    raw = _read_json_object(path)
    values = raw.get("codes")
    if not isinstance(values, list):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


def save_locks(path: str | Path, locks: set[str]) -> Path:
    payload = {
        "codes": sorted({str(code).strip() for code in (locks or set()) if str(code).strip()}),
    }
    return _write_json_object(path, payload)


def load_project_state(path: str | Path) -> dict[str, object]:
    raw = _read_json_object(path)
    basis_col = str(raw.get("basis_col") or "").strip() or "Endring"
    selected_code = str(raw.get("selected_code") or "").strip() or None
    selected_group = str(raw.get("selected_group") or "").strip() or None
    return {
        "basis_col": basis_col,
        "selected_code": selected_code,
        "selected_group": selected_group,
    }


def save_project_state(path: str | Path, payload: dict[str, object]) -> Path:
    basis_col = str(payload.get("basis_col") or "").strip() or "Endring"
    selected_code = str(payload.get("selected_code") or "").strip()
    selected_group = str(payload.get("selected_group") or "").strip()
    out = {
        "basis_col": basis_col,
        "selected_code": selected_code or None,
        "selected_group": selected_group or None,
    }
    return _write_json_object(path, out)
