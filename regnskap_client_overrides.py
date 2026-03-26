from __future__ import annotations

"""Klientspesifikke konto -> regnskapslinje-overstyringer."""

import json
import re
from pathlib import Path
from typing import Dict, Sequence

import app_paths


def overrides_dir() -> Path:
    path = app_paths.data_dir() / "config" / "regnskap" / "client_overrides"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _client_slug(client: str) -> str:
    text = str(client or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text or "unknown_client"


def overrides_path(client: str) -> Path:
    return overrides_dir() / f"{_client_slug(client)}.json"


def load_account_overrides(client: str | None) -> Dict[str, int]:
    if not client:
        return {}

    raw = _read_payload(client)
    mapping = raw.get("account_overrides", {}) if isinstance(raw, dict) else {}
    if not isinstance(mapping, dict):
        return {}

    clean: Dict[str, int] = {}
    for konto, regnr in mapping.items():
        konto_s = str(konto or "").strip()
        if not konto_s:
            continue
        try:
            clean[konto_s] = int(regnr)
        except Exception:
            continue
    return clean


def save_account_overrides(client: str, overrides: Dict[str, int]) -> Path:
    clean: Dict[str, int] = {}
    for konto, regnr in overrides.items():
        konto_s = str(konto or "").strip()
        if not konto_s:
            continue
        clean[konto_s] = int(regnr)

    payload = _read_payload(client)
    payload["client"] = str(client)
    payload["account_overrides"] = clean

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def set_account_override(client: str, konto: str, regnr: int) -> Path:
    current = load_account_overrides(client)
    current[str(konto).strip()] = int(regnr)
    return save_account_overrides(client, current)


def remove_account_override(client: str, konto: str) -> Path:
    current = load_account_overrides(client)
    current.pop(str(konto).strip(), None)
    return save_account_overrides(client, current)


def load_expected_regnskapslinjer(
    client: str | None,
    *,
    scope_regnr: Sequence[int],
    selected_direction: str | None = None,
) -> list[int]:
    if not client:
        return []

    raw = _read_payload(client)
    presets = raw.get("expected_regnskapslinjer_presets", {}) if isinstance(raw, dict) else {}
    if not isinstance(presets, dict):
        return []

    key = _expected_scope_key(scope_regnr, selected_direction=selected_direction)
    values = presets.get(key, [])
    if not isinstance(values, list):
        return []

    clean: list[int] = []
    for value in values:
        try:
            clean.append(int(value))
        except Exception:
            continue
    return clean


def load_expected_regnskapslinje_rule(
    client: str | None,
    *,
    scope_regnr: Sequence[int],
    selected_direction: str | None = None,
) -> dict[str, float | bool | list[int]]:
    if not client:
        return {"require_netting": False, "tolerance": 1.0, "selected_regnr": []}

    raw = _read_payload(client)
    presets = raw.get("expected_regnskapslinje_rule_presets", {}) if isinstance(raw, dict) else {}
    if not isinstance(presets, dict):
        return {"require_netting": False, "tolerance": 1.0, "selected_regnr": []}

    key = _expected_scope_key(scope_regnr, selected_direction=selected_direction)
    payload = presets.get(key, {})
    if not isinstance(payload, dict):
        return {"require_netting": False, "tolerance": 1.0, "selected_regnr": []}

    require_netting = bool(payload.get("require_netting", False))
    try:
        tolerance = float(payload.get("tolerance", 1.0) or 0.0)
    except Exception:
        tolerance = 1.0
    selected_regnr: list[int] = []
    for value in payload.get("selected_regnr", []) or []:
        try:
            regnr = int(value)
        except Exception:
            continue
        if regnr not in selected_regnr:
            selected_regnr.append(regnr)
    return {"require_netting": require_netting, "tolerance": max(tolerance, 0.0), "selected_regnr": selected_regnr}


def save_expected_regnskapslinje_rule(
    client: str,
    *,
    scope_regnr: Sequence[int],
    require_netting: bool,
    tolerance: float,
    selected_regnr: Sequence[int] = (),
    selected_direction: str | None = None,
) -> Path:
    payload = _read_payload(client)
    payload["client"] = str(client)

    presets = payload.get("expected_regnskapslinje_rule_presets", {})
    if not isinstance(presets, dict):
        presets = {}

    key = _expected_scope_key(scope_regnr, selected_direction=selected_direction)
    try:
        tolerance_value = max(float(tolerance or 0.0), 0.0)
    except Exception:
        tolerance_value = 1.0
    clean_selected: list[int] = []
    for value in selected_regnr:
        try:
            regnr = int(value)
        except Exception:
            continue
        if regnr not in clean_selected:
            clean_selected.append(regnr)

    presets[key] = {
        "require_netting": bool(require_netting),
        "tolerance": tolerance_value,
        "selected_regnr": clean_selected,
    }
    payload["expected_regnskapslinje_rule_presets"] = presets

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def save_expected_regnskapslinjer(
    client: str,
    *,
    scope_regnr: Sequence[int],
    expected_regnr: Sequence[int],
    selected_direction: str | None = None,
) -> Path:
    payload = _read_payload(client)
    payload["client"] = str(client)

    presets = payload.get("expected_regnskapslinjer_presets", {})
    if not isinstance(presets, dict):
        presets = {}

    key = _expected_scope_key(scope_regnr, selected_direction=selected_direction)
    clean_expected: list[int] = []
    for value in expected_regnr:
        try:
            regnr = int(value)
        except Exception:
            continue
        if regnr not in clean_expected:
            clean_expected.append(regnr)

    if clean_expected:
        presets[key] = clean_expected
    else:
        presets.pop(key, None)

    payload["expected_regnskapslinjer_presets"] = presets

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def remove_expected_regnskapslinjer(
    client: str,
    *,
    scope_regnr: Sequence[int],
    selected_direction: str | None = None,
) -> Path:
    return save_expected_regnskapslinjer(
        client,
        scope_regnr=scope_regnr,
        expected_regnr=[],
        selected_direction=selected_direction,
    )


def load_column_mapping(client: str | None) -> Dict[str, str]:
    """Last lagret kolonne-mapping for klienten (canonical → source header)."""
    if not client:
        return {}

    raw = _read_payload(client)
    mapping = raw.get("column_mapping", {}) if isinstance(raw, dict) else {}
    if not isinstance(mapping, dict):
        return {}

    clean: Dict[str, str] = {}
    for canon, src in mapping.items():
        canon_s = str(canon or "").strip()
        src_s = str(src or "").strip()
        if canon_s and src_s:
            clean[canon_s] = src_s
    return clean


def save_column_mapping(client: str, mapping: Dict[str, str]) -> Path:
    """Lagre kolonne-mapping per klient."""
    clean: Dict[str, str] = {}
    for canon, src in mapping.items():
        canon_s = str(canon or "").strip()
        src_s = str(src or "").strip()
        if canon_s and src_s:
            clean[canon_s] = src_s

    payload = _read_payload(client)
    payload["client"] = str(client)
    payload["column_mapping"] = clean

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_accounting_system(client: str | None) -> str:
    """Last lagret regnskapssystem for klienten (tom streng om ikke satt)."""
    if not client:
        return ""
    raw = _read_payload(client)
    value = raw.get("accounting_system", "") if isinstance(raw, dict) else ""
    return str(value or "").strip()


def save_accounting_system(client: str, system: str) -> Path:
    """Lagre valgt regnskapssystem for klienten."""
    payload = _read_payload(client)
    payload["client"] = str(client)
    payload["accounting_system"] = str(system or "").strip()

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_mva_code_mapping(client: str | None) -> Dict[str, str]:
    """Last lagret MVA-kode-mapping for klienten.

    Returnerer {klient_kode: saft_standard_kode}.
    """
    if not client:
        return {}

    raw = _read_payload(client)
    mapping = raw.get("mva_code_mapping", {}) if isinstance(raw, dict) else {}
    if not isinstance(mapping, dict):
        return {}

    clean: Dict[str, str] = {}
    for client_code, saft_code in mapping.items():
        client_s = str(client_code or "").strip()
        saft_s = str(saft_code or "").strip()
        if client_s and saft_s:
            clean[client_s] = saft_s
    return clean


def save_mva_code_mapping(client: str, mapping: Dict[str, str]) -> Path:
    """Lagre MVA-kode-mapping per klient."""
    clean: Dict[str, str] = {}
    for client_code, saft_code in mapping.items():
        client_s = str(client_code or "").strip()
        saft_s = str(saft_code or "").strip()
        if client_s and saft_s:
            clean[client_s] = saft_s

    payload = _read_payload(client)
    payload["client"] = str(client)
    payload["mva_code_mapping"] = clean

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_mapping_review_state(client: str | None) -> Dict[str, dict]:
    """Last vurderingsstatus for semantiske mappingforslag per konto."""
    if not client:
        return {}

    raw = _read_payload(client)
    payload = raw.get("mapping_review_state", {}) if isinstance(raw, dict) else {}
    if not isinstance(payload, dict):
        return {}

    clean: Dict[str, dict] = {}
    for konto, state in payload.items():
        konto_s = str(konto or "").strip()
        if not konto_s or not isinstance(state, dict):
            continue
        clean[konto_s] = {
            "status": str(state.get("status") or "").strip(),
            "suggested_regnr": state.get("suggested_regnr"),
            "note": str(state.get("note") or "").strip(),
        }
    return clean


def save_mapping_review_state(client: str, state: Dict[str, dict]) -> Path:
    payload = _read_payload(client)
    payload["client"] = str(client)

    clean: Dict[str, dict] = {}
    for konto, item in state.items():
        konto_s = str(konto or "").strip()
        if not konto_s or not isinstance(item, dict):
            continue
        suggested_regnr = item.get("suggested_regnr")
        try:
            suggested_regnr = int(suggested_regnr) if suggested_regnr is not None and str(suggested_regnr).strip() != "" else None
        except Exception:
            suggested_regnr = None
        clean[konto_s] = {
            "status": str(item.get("status") or "").strip(),
            "suggested_regnr": suggested_regnr,
            "note": str(item.get("note") or "").strip(),
        }

    payload["mapping_review_state"] = clean

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def set_mapping_review_state(
    client: str,
    konto: str,
    *,
    status: str,
    suggested_regnr: int | None = None,
    note: str = "",
) -> Path:
    current = load_mapping_review_state(client)
    konto_s = str(konto or "").strip()
    if not konto_s:
        return save_mapping_review_state(client, current)
    current[konto_s] = {
        "status": str(status or "").strip(),
        "suggested_regnr": int(suggested_regnr) if suggested_regnr is not None else None,
        "note": str(note or "").strip(),
    }
    return save_mapping_review_state(client, current)


def remove_mapping_review_state(client: str, konto: str) -> Path:
    current = load_mapping_review_state(client)
    current.pop(str(konto or "").strip(), None)
    return save_mapping_review_state(client, current)


def load_expected_flow_presets(client: str | None) -> Dict[str, dict]:
    """Last klientspesifikke forventningsregler for transaksjonsflyt."""
    if not client:
        return {}

    raw = _read_payload(client)
    payload = raw.get("expected_flow_presets", {}) if isinstance(raw, dict) else {}
    if not isinstance(payload, dict):
        return {}

    clean: Dict[str, dict] = {}
    for key, item in payload.items():
        key_s = str(key or "").strip()
        if key_s and isinstance(item, dict):
            clean[key_s] = dict(item)
    return clean


def save_expected_flow_preset(client: str, key: str, preset: dict) -> Path:
    payload = _read_payload(client)
    payload["client"] = str(client)

    presets = payload.get("expected_flow_presets", {})
    if not isinstance(presets, dict):
        presets = {}

    key_s = str(key or "").strip()
    if key_s and isinstance(preset, dict):
        presets[key_s] = dict(preset)
    elif key_s:
        presets.pop(key_s, None)

    payload["expected_flow_presets"] = presets

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_kontoutskrift_path(client: str | None) -> str:
    """Last lagret sti til Skatteetatens kontoutskrift for klienten."""
    if not client:
        return ""
    raw = _read_payload(client)
    value = raw.get("kontoutskrift_path", "") if isinstance(raw, dict) else ""
    return str(value or "").strip()


def save_kontoutskrift_path(client: str, path: str) -> Path:
    """Lagre sti til Skatteetatens kontoutskrift for klienten."""
    payload = _read_payload(client)
    payload["client"] = str(client)
    payload["kontoutskrift_path"] = str(path or "").strip()

    out = overrides_path(client)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(out)
    return out


def _read_payload(client: str | None) -> dict:
    if not client:
        return {}
    path = overrides_path(client)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


# ---------------------------------------------------------------------------
# Kommentarer (per konto og per regnskapslinje)
# ---------------------------------------------------------------------------

def load_comments(client: str | None) -> dict[str, dict[str, str]]:
    """Last kommentarer for klient.

    Returnerer {"accounts": {"1801": "Sjekket OK", ...},
                "rl": {"550": "Følg opp", ...}}.
    """
    if not client:
        return {"accounts": {}, "rl": {}}
    raw = _read_payload(client)
    comments = raw.get("comments", {})
    if not isinstance(comments, dict):
        comments = {}
    return {
        "accounts": {str(k): str(v) for k, v in comments.get("accounts", {}).items() if v},
        "rl": {str(k): str(v) for k, v in comments.get("rl", {}).items() if v},
    }


def save_comment(client: str, *, kind: str, key: str, text: str) -> None:
    """Lagre eller fjern en kommentar.

    kind: "accounts" eller "rl"
    key: kontonummer eller regnr (som streng)
    text: kommentar-tekst (tom streng = fjern)
    """
    payload = _read_payload(client)
    comments = payload.setdefault("comments", {})
    if not isinstance(comments, dict):
        comments = {}
        payload["comments"] = comments
    bucket = comments.setdefault(kind, {})
    if not isinstance(bucket, dict):
        bucket = {}
        comments[kind] = bucket

    key = str(key).strip()
    text = str(text).strip()
    if text:
        bucket[key] = text
    else:
        bucket.pop(key, None)

    payload["client"] = str(client)
    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# Tilleggsposteringer (per klient, per år)
# ---------------------------------------------------------------------------

def load_supplementary_entries(client: str | None, year: str | None) -> list[dict]:
    """Last tilleggsposteringer for klient og år.

    Hver entry: {"bilag": str, "konto": str, "belop": float, "beskrivelse": str}
    """
    if not client or not year:
        return []
    raw = _read_payload(client)
    all_entries = raw.get("supplementary_entries", {})
    if not isinstance(all_entries, dict):
        return []
    year_entries = all_entries.get(str(year), [])
    if not isinstance(year_entries, list):
        return []

    clean: list[dict] = []
    for e in year_entries:
        if not isinstance(e, dict):
            continue
        try:
            clean.append({
                "bilag": str(e.get("bilag", "")).strip(),
                "konto": str(e.get("konto", "")).strip(),
                "belop": float(e.get("belop", 0.0)),
                "beskrivelse": str(e.get("beskrivelse", "")).strip(),
            })
        except Exception:
            continue
    return clean


def save_supplementary_entries(client: str, year: str,
                                entries: list[dict]) -> None:
    """Lagre tilleggsposteringer for klient og år."""
    clean: list[dict] = []
    for e in entries:
        try:
            belop = float(e.get("belop", 0.0))
            if abs(belop) < 0.005:
                continue
            clean.append({
                "bilag": str(e.get("bilag", "")).strip(),
                "konto": str(e.get("konto", "")).strip(),
                "belop": belop,
                "beskrivelse": str(e.get("beskrivelse", "")).strip(),
            })
        except Exception:
            continue

    payload = _read_payload(client)
    payload["client"] = str(client)
    all_entries = payload.setdefault("supplementary_entries", {})
    if not isinstance(all_entries, dict):
        all_entries = {}
        payload["supplementary_entries"] = all_entries
    all_entries[str(year)] = clean

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _expected_scope_key(scope_regnr: Sequence[int], *, selected_direction: str | None = None) -> str:
    clean_scope: list[int] = []
    for value in scope_regnr:
        try:
            regnr = int(value)
        except Exception:
            continue
        if regnr not in clean_scope:
            clean_scope.append(regnr)
    clean_scope.sort()
    direction = str(selected_direction or "alle").strip().lower() or "alle"
    if direction.startswith("deb"):
        direction = "debet"
    elif direction.startswith("kre") or direction.startswith("cre"):
        direction = "kredit"
    else:
        direction = "alle"
    scope_part = ",".join(str(v) for v in clean_scope)
    return f"{direction}|{scope_part}"
