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


def load_account_overrides(client: str | None, *, year: str | None = None) -> Dict[str, int]:
    """Last konto → regnr-overstyringer for klient.

    Strategi:
      - Hvis *year* er gitt, bruker vi årets overstyringer (``account_overrides_by_year[year]``).
      - Fallback til årsagnostisk ``account_overrides`` (bakoverkompatibilitet).
    """
    if not client:
        return {}

    raw = _read_payload(client)
    if not isinstance(raw, dict):
        return {}

    # År-spesifikke overrides har prioritet
    if year:
        by_year = raw.get("account_overrides_by_year", {})
        if isinstance(by_year, dict) and str(year) in by_year:
            mapping = by_year[str(year)]
            if isinstance(mapping, dict):
                return _clean_overrides_dict(mapping)

    # Fallback: årsagnostisk (gammel modell)
    mapping = raw.get("account_overrides", {})
    if not isinstance(mapping, dict):
        return {}
    return _clean_overrides_dict(mapping)


def save_account_overrides(client: str, overrides: Dict[str, int],
                           *, year: str | None = None) -> Path:
    """Lagre konto → regnr-overstyringer.

    Hvis *year* er gitt, lagres under ``account_overrides_by_year[year]``.
    Den årsagnostiske ``account_overrides`` oppdateres også for
    bakoverkompatibilitet.
    """
    clean = _clean_overrides_dict(overrides)

    payload = _read_payload(client)
    payload["client"] = str(client)

    # Alltid oppdater årsagnostisk kopi (bakoverkompatibilitet)
    payload["account_overrides"] = clean

    # Lagre per-år hvis year gitt
    if year:
        by_year = payload.get("account_overrides_by_year", {})
        if not isinstance(by_year, dict):
            by_year = {}
        by_year[str(year)] = clean
        payload["account_overrides_by_year"] = by_year

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def set_account_override(client: str, konto: str, regnr: int,
                         *, year: str | None = None) -> Path:
    current = load_account_overrides(client, year=year)
    current[str(konto).strip()] = int(regnr)
    return save_account_overrides(client, current, year=year)


def remove_account_override(client: str, konto: str,
                            *, year: str | None = None) -> Path:
    current = load_account_overrides(client, year=year)
    current.pop(str(konto).strip(), None)
    return save_account_overrides(client, current, year=year)


def _clean_overrides_dict(mapping: dict) -> Dict[str, int]:
    """Rens og valider et konto → regnr-dict."""
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


def load_prior_year_overrides(client: str | None, year: str | None) -> Dict[str, int]:
    """Last overstyringer for forrige år.

    Brukes for fjorårs-SB-aggregering. Returnerer forrige års
    egne overrides dersom de finnes, ellers tom dict.
    """
    if not client or not year:
        return {}
    try:
        prev_year = str(int(year) - 1)
    except (ValueError, TypeError):
        return {}
    return load_account_overrides(client, year=prev_year)


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


# ---------------------------------------------------------------------------
# Skatteetaten kontoutskrift (importert av MVA-fanen)
# ---------------------------------------------------------------------------

def save_skatteetaten_data(client: str, year: int | str, data: dict) -> Path:
    """Lagre parsed Skatteetaten-data per år per klient."""
    payload = _read_payload(client)
    payload["client"] = str(client)

    bucket = payload.get("skatteetaten_kontoutskrift")
    if not isinstance(bucket, dict):
        bucket = {}
    bucket[str(year)] = data if isinstance(data, dict) else {}
    payload["skatteetaten_kontoutskrift"] = bucket

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_skatteetaten_data(client: str | None, year: int | str) -> dict | None:
    """Last Skatteetaten-data for (klient, år). Returnerer None hvis ikke funnet."""
    if not client:
        return None
    raw = _read_payload(client)
    bucket = raw.get("skatteetaten_kontoutskrift") if isinstance(raw, dict) else None
    if not isinstance(bucket, dict):
        return None
    data = bucket.get(str(year))
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# MVA-melding (Altinn-import)
# ---------------------------------------------------------------------------

def save_mva_melding(client: str, year: int | str, termin: int | str, data: dict) -> Path:
    """Lagre MVA-melding per (klient, år, termin)."""
    payload = _read_payload(client)
    payload["client"] = str(client)

    root = payload.get("mva_melding")
    if not isinstance(root, dict):
        root = {}
    year_key = str(year)
    year_bucket = root.get(year_key)
    if not isinstance(year_bucket, dict):
        year_bucket = {}
    year_bucket[str(termin)] = data if isinstance(data, dict) else {}
    root[year_key] = year_bucket
    payload["mva_melding"] = root

    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load_mva_melding(
    client: str | None,
    year: int | str,
    termin: int | str | None = None,
) -> dict | None:
    """Last MVA-melding.

    Hvis ``termin`` er None returneres hele termin-dict for året
    ({termin_str: data}), ellers returneres én termin-dict.
    """
    if not client:
        return None
    raw = _read_payload(client)
    root = raw.get("mva_melding") if isinstance(raw, dict) else None
    if not isinstance(root, dict):
        return None
    year_bucket = root.get(str(year))
    if not isinstance(year_bucket, dict):
        return None
    if termin is None:
        return year_bucket
    data = year_bucket.get(str(termin))
    return data if isinstance(data, dict) else None


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


# ---------------------------------------------------------------------------
# Strukturerte forventningsregler for motpostanalyse (v1)
# ---------------------------------------------------------------------------

def load_expected_motpost_rules(
    client: str | None,
    *,
    source_regnr: int,
    selected_direction: str | None = None,
) -> dict:
    """Last strukturert forventningsregelsett for én kilde-RL (rå dict)."""
    if not client:
        return {}
    raw = _read_payload(client)
    presets = raw.get("expected_motpost_rules_v1", {}) if isinstance(raw, dict) else {}
    if not isinstance(presets, dict):
        return {}
    key = _expected_scope_key([int(source_regnr)], selected_direction=selected_direction)
    payload = presets.get(key, {})
    return payload if isinstance(payload, dict) else {}


def save_expected_motpost_rules(
    client: str,
    *,
    source_regnr: int,
    selected_direction: str | None = None,
    payload: dict,
) -> Path:
    """Lagre strukturert forventningsregelsett for én kilde-RL."""
    stored = _read_payload(client)
    stored["client"] = str(client)
    presets = stored.get("expected_motpost_rules_v1", {})
    if not isinstance(presets, dict):
        presets = {}
    key = _expected_scope_key([int(source_regnr)], selected_direction=selected_direction)
    presets[key] = dict(payload or {})
    stored["expected_motpost_rules_v1"] = presets
    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def remove_expected_motpost_rules(
    client: str,
    *,
    source_regnr: int,
    selected_direction: str | None = None,
) -> Path:
    """Fjern strukturert forventningsregelsett for én kilde-RL."""
    stored = _read_payload(client)
    stored["client"] = str(client)
    presets = stored.get("expected_motpost_rules_v1", {})
    if not isinstance(presets, dict):
        presets = {}
    key = _expected_scope_key([int(source_regnr)], selected_direction=selected_direction)
    presets.pop(key, None)
    stored["expected_motpost_rules_v1"] = presets
    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(stored, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


# ---------------------------------------------------------------------------
# Kontogjennomgang per år (OK-markering + vedlegg)
# ---------------------------------------------------------------------------

def _write_payload(client: str, payload: dict) -> Path:
    payload["client"] = str(client)
    path = overrides_path(client)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def _norm_attachment_path(path: str) -> str:
    p = str(path or "").strip()
    if not p:
        return ""
    try:
        return str(Path(p).resolve())
    except Exception:
        return p


_UB_EVIDENCE_STATUSES = {"match", "mismatch", "unchecked"}


def _clean_ub_evidence(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    attachment_path = str(raw.get("attachment_path", "") or "").strip()
    if not attachment_path:
        return None

    page_raw = raw.get("page")
    try:
        page = int(page_raw) if page_raw is not None else 1
    except Exception:
        page = 1
    if page < 1:
        page = 1

    bbox_raw = raw.get("bbox")
    bbox: tuple[float, float, float, float] | None = None
    if isinstance(bbox_raw, (list, tuple)) and len(bbox_raw) == 4:
        try:
            bbox = tuple(float(x) for x in bbox_raw)  # type: ignore[assignment]
        except Exception:
            bbox = None

    normalized_raw = raw.get("normalized_value")
    normalized: float | None
    if normalized_raw is None or normalized_raw == "":
        normalized = None
    else:
        try:
            normalized = float(normalized_raw)
        except Exception:
            normalized = None

    status = str(raw.get("status", "") or "").strip().lower()
    if status not in _UB_EVIDENCE_STATUSES:
        status = "unchecked"

    source = str(raw.get("source", "") or "").strip().lower() or "manual"

    cleaned = {
        "attachment_path": attachment_path,
        "attachment_label": str(raw.get("attachment_label", "") or Path(attachment_path).name).strip()
            or Path(attachment_path).name,
        "page": page,
        "raw_value": str(raw.get("raw_value", "") or "").strip(),
        "normalized_value": normalized,
        "status": status,
        "source": source,
        "updated_at": str(raw.get("updated_at", "") or "").strip(),
        "note": str(raw.get("note", "") or "").strip(),
    }
    if bbox is not None:
        cleaned["bbox"] = list(bbox)
    return cleaned


def _clean_review_entry(raw: object) -> dict:
    entry = raw if isinstance(raw, dict) else {}
    ok = bool(entry.get("ok", False))
    atts_raw = entry.get("attachments", [])
    atts: list[dict] = []
    if isinstance(atts_raw, list):
        for a in atts_raw:
            if not isinstance(a, dict):
                continue
            path = str(a.get("path", "")).strip()
            if not path:
                continue
            storage = str(a.get("storage", "") or "").strip().lower()
            if storage not in {"managed", "external"}:
                storage = "external"
            cleaned = {
                "path": path,
                "label": str(a.get("label", "") or Path(path).name).strip() or Path(path).name,
                "added_at": str(a.get("added_at", "") or "").strip(),
                "storage": storage,
            }
            src = str(a.get("source_path", "") or "").strip()
            if src:
                cleaned["source_path"] = src
            rsnap = a.get("regnr_snapshot")
            if isinstance(rsnap, (int, float)) or (isinstance(rsnap, str) and rsnap.strip()):
                try:
                    cleaned["regnr_snapshot"] = int(rsnap)
                except Exception:
                    pass
            rlsnap = str(a.get("regnskapslinje_snapshot", "") or "").strip()
            if rlsnap:
                cleaned["regnskapslinje_snapshot"] = rlsnap
            atts.append(cleaned)
    out: dict = {"ok": ok, "attachments": atts}
    ok_by = str(entry.get("ok_by", "") or "").strip()
    if ok_by:
        out["ok_by"] = ok_by
    ok_at = str(entry.get("ok_at", "") or "").strip()
    if ok_at:
        out["ok_at"] = ok_at
    ub = _clean_ub_evidence(entry.get("ub_evidence"))
    if ub is not None:
        out["ub_evidence"] = ub
    return out


_SLUG_RE = re.compile(r"[^A-Za-z0-9]+")


def _slugify_regnskapslinje(name: str) -> str:
    """Enkel slug for regnskapslinje-navn brukt i mappenavn."""
    text = str(name or "").strip()
    text = (text
            .replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
            .replace("Æ", "Ae").replace("Ø", "Oe").replace("Å", "Aa"))
    slug = _SLUG_RE.sub("_", text).strip("_")
    return slug or "ukjent"


def account_attachment_dir(
    client: str,
    year: str,
    *,
    regnr: int,
    regnskapslinje: str,
    konto: str,
) -> Path:
    """Returner (og opprett) katalog for vedlegg for en konto under Utvalg-lager.

    Struktur: ``clients/<klient>/years/<år>/attachments/regnskapslinjer/<regnr>_<slug>/konto_<konto>/``
    """
    import client_store as _cs
    base = _cs.years_dir(str(client), year=str(year))
    slug = _slugify_regnskapslinje(regnskapslinje)
    path = base / "attachments" / "regnskapslinjer" / f"{int(regnr)}_{slug}" / f"konto_{str(konto).strip()}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _copy_to_managed_storage(src_path: str, target_dir: Path) -> Path:
    """Kopier kilde-fil inn i target_dir. Unngå kollisjoner med suffiks _2, _3, ..."""
    import shutil
    src = Path(str(src_path))
    if not src.exists():
        raise FileNotFoundError(str(src))
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = src.stem
    suffix = src.suffix
    candidate = target_dir / src.name
    n = 2
    while candidate.exists():
        try:
            if candidate.resolve() == src.resolve():
                return candidate
        except Exception:
            pass
        candidate = target_dir / f"{stem}_{n}{suffix}"
        n += 1
    shutil.copy2(str(src), str(candidate))
    return candidate


def load_account_review(client: str | None, year: str | None) -> dict[str, dict]:
    """Last kontogjennomgang (OK + vedlegg) for klient/år.

    Returnerer ``{konto: {"ok": bool, "attachments": [...]}}``. Kun kontoer
    med enten ``ok=True`` eller minst ett vedlegg inkluderes.
    """
    if not client or not year:
        return {}
    raw = _read_payload(client)
    by_year = raw.get("account_review_by_year", {})
    if not isinstance(by_year, dict):
        return {}
    year_map = by_year.get(str(year), {})
    if not isinstance(year_map, dict):
        return {}
    out: dict[str, dict] = {}
    for konto, entry in year_map.items():
        clean = _clean_review_entry(entry)
        if clean["ok"] or clean["attachments"] or clean.get("ub_evidence"):
            out[str(konto)] = clean
    return out


def _mutate_account_review(client: str, year: str) -> tuple[dict, dict]:
    """Les payload og returner (payload, year_map) for mutasjon."""
    payload = _read_payload(client)
    by_year = payload.setdefault("account_review_by_year", {})
    if not isinstance(by_year, dict):
        by_year = {}
        payload["account_review_by_year"] = by_year
    year_map = by_year.setdefault(str(year), {})
    if not isinstance(year_map, dict):
        year_map = {}
        by_year[str(year)] = year_map
    return payload, year_map


def _prune_entry_if_empty(year_map: dict, konto: str) -> None:
    entry = year_map.get(konto)
    if not isinstance(entry, dict):
        return
    if (
        not entry.get("ok")
        and not entry.get("attachments")
        and not entry.get("ub_evidence")
    ):
        year_map.pop(konto, None)


def _current_user_stamp() -> str:
    """Returner bruker-stempel for revisjonslogg: 'Visena-initialer' eller Windows-bruker."""
    try:
        import team_config as _tc
        user = _tc.current_user()
        if user is not None:
            initials = (user.visena_initials or "").strip()
            if initials:
                return initials.upper()
            full = (user.full_name or "").strip()
            if full:
                return full
            win = (user.windows_user or "").strip()
            if win:
                return win
    except Exception:
        pass
    try:
        import getpass as _getpass
        return (_getpass.getuser() or "").strip() or "ukjent"
    except Exception:
        return "ukjent"


def set_accounts_ok(client: str, year: str, kontoer: Sequence[str], ok: bool) -> Path:
    """Sett eller fjern OK-markering for én eller flere kontoer.

    Når ok=True stemples `ok_by` (bruker) og `ok_at` (ISO-tidsstempel) for
    sporbarhet. Når ok=False fjernes sporet.
    """
    if not client or not year:
        return overrides_path(client or "")

    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    user_stamp = _current_user_stamp()

    payload, year_map = _mutate_account_review(client, year)
    for raw in kontoer:
        konto = str(raw or "").strip()
        if not konto:
            continue
        entry = year_map.get(konto)
        if not isinstance(entry, dict):
            entry = {"ok": False, "attachments": []}
            year_map[konto] = entry
        entry["ok"] = bool(ok)
        if ok:
            entry["ok_by"] = user_stamp
            entry["ok_at"] = now
        else:
            entry.pop("ok_by", None)
            entry.pop("ok_at", None)
        if not isinstance(entry.get("attachments"), list):
            entry["attachments"] = []
        _prune_entry_if_empty(year_map, konto)
    return _write_payload(client, payload)


def add_account_attachments(
    client: str,
    year: str,
    kontoer: Sequence[str],
    paths: Sequence[str],
    *,
    label: str | None = None,
    regnr_by_konto: dict[str, tuple[int, str]] | None = None,
    storage: str = "managed",
) -> Path:
    """Legg til vedlegg for én eller flere kontoer. Dedup per normalisert sti per konto.

    Default (``storage="managed"``) kopierer filene inn i Utvalg-lager under
    ``clients/<klient>/years/<år>/attachments/regnskapslinjer/...`` — dette
    krever at ``regnr_by_konto`` inneholder ``(regnr, regnskapslinje)`` for
    hver konto. Hvis info mangler for en konto, faller den kontoen tilbake
    til ekstern referanse. ``storage="external"`` tvinger ekstern referanse.
    """
    if not client or not year:
        return overrides_path(client or "")

    from datetime import datetime

    payload, year_map = _mutate_account_review(client, year)
    now = datetime.now().isoformat(timespec="seconds")
    rbk = dict(regnr_by_konto or {})

    for raw_konto in kontoer:
        konto = str(raw_konto or "").strip()
        if not konto:
            continue
        entry = year_map.get(konto)
        if not isinstance(entry, dict):
            entry = {"ok": False, "attachments": []}
            year_map[konto] = entry
        atts = entry.setdefault("attachments", [])
        if not isinstance(atts, list):
            atts = []
            entry["attachments"] = atts

        existing_paths = {_norm_attachment_path(a.get("path", "")) for a in atts if isinstance(a, dict)}
        existing_sources = {
            _norm_attachment_path(a.get("source_path", ""))
            for a in atts
            if isinstance(a, dict) and str(a.get("storage", "")).lower() == "managed"
        }

        rl_info = rbk.get(konto) if storage == "managed" else None
        can_manage = bool(rl_info) and storage == "managed"

        for raw_path in paths:
            src_path = str(raw_path or "").strip()
            if not src_path:
                continue
            src_norm = _norm_attachment_path(src_path)

            if can_manage:
                # Dedup: samme kildefil er allerede kopiert inn for denne kontoen
                if src_norm in existing_sources:
                    continue
                try:
                    regnr, regnskapslinje = int(rl_info[0]), str(rl_info[1])  # type: ignore[index]
                    target_dir = account_attachment_dir(
                        client, year, regnr=regnr,
                        regnskapslinje=regnskapslinje, konto=konto,
                    )
                    copied = _copy_to_managed_storage(src_path, target_dir)
                    atts.append({
                        "path": str(copied),
                        "label": (str(label).strip() if label else copied.name),
                        "added_at": now,
                        "storage": "managed",
                        "source_path": src_path,
                        "regnr_snapshot": regnr,
                        "regnskapslinje_snapshot": regnskapslinje,
                    })
                    existing_paths.add(_norm_attachment_path(str(copied)))
                    existing_sources.add(src_norm)
                    continue
                except Exception:
                    # Fall-through til ekstern referanse ved feil
                    pass

            if src_norm in existing_paths:
                continue
            atts.append({
                "path": src_path,
                "label": (str(label).strip() if label else Path(src_path).name),
                "added_at": now,
                "storage": "external",
            })
            existing_paths.add(src_norm)
    return _write_payload(client, payload)


def migrate_attachment_to_managed(
    client: str,
    year: str,
    konto: str,
    path: str,
    *,
    regnr: int,
    regnskapslinje: str,
) -> Path:
    """Migrer en ekstern vedleggsreferanse til Utvalg-lager.

    Finner vedleggs-entryen (matchet på normalisert sti), kopierer kildefilen
    inn i managed-mappen, og oppdaterer entryen in-place. Sletter ikke
    original-fil. No-op hvis entry allerede er ``managed`` eller mangler.
    """
    if not client or not year or not konto:
        return overrides_path(client or "")

    payload, year_map = _mutate_account_review(client, year)
    entry = year_map.get(str(konto))
    if not isinstance(entry, dict):
        return _write_payload(client, payload)
    atts = entry.get("attachments")
    if not isinstance(atts, list):
        return _write_payload(client, payload)

    target_norm = _norm_attachment_path(path)
    for a in atts:
        if not isinstance(a, dict):
            continue
        if _norm_attachment_path(a.get("path", "")) != target_norm:
            continue
        if str(a.get("storage", "external")).lower() == "managed":
            return _write_payload(client, payload)
        src_path = str(a.get("path", "") or "").strip()
        if not src_path or not Path(src_path).exists():
            return _write_payload(client, payload)
        target_dir = account_attachment_dir(
            client, year, regnr=int(regnr),
            regnskapslinje=str(regnskapslinje), konto=str(konto),
        )
        copied = _copy_to_managed_storage(src_path, target_dir)
        a["path"] = str(copied)
        a["storage"] = "managed"
        a["source_path"] = src_path
        a["regnr_snapshot"] = int(regnr)
        a["regnskapslinje_snapshot"] = str(regnskapslinje)
        if not str(a.get("label", "")).strip():
            a["label"] = copied.name

        ub = entry.get("ub_evidence")
        if isinstance(ub, dict):
            ub_norm = _norm_attachment_path(ub.get("attachment_path", ""))
            if ub_norm == target_norm:
                ub["attachment_path"] = str(copied)
        break
    return _write_payload(client, payload)


def remove_account_attachment(client: str, year: str, konto: str, path: str) -> Path:
    """Fjern én vedleggsreferanse (matchet på normalisert sti) for en konto."""
    if not client or not year or not konto:
        return overrides_path(client or "")

    payload, year_map = _mutate_account_review(client, year)
    entry = year_map.get(str(konto))
    if not isinstance(entry, dict):
        return _write_payload(client, payload)
    atts = entry.get("attachments", [])
    if not isinstance(atts, list):
        entry["attachments"] = []
        _prune_entry_if_empty(year_map, str(konto))
        return _write_payload(client, payload)

    target = _norm_attachment_path(path)
    entry["attachments"] = [
        a for a in atts
        if not (isinstance(a, dict) and _norm_attachment_path(a.get("path", "")) == target)
    ]
    ub = entry.get("ub_evidence")
    if isinstance(ub, dict):
        ub_norm = _norm_attachment_path(ub.get("attachment_path", ""))
        if ub_norm == target:
            entry.pop("ub_evidence", None)
    _prune_entry_if_empty(year_map, str(konto))
    return _write_payload(client, payload)


def list_account_attachments(client: str | None, year: str | None, konto: str) -> list[dict]:
    """Returner vedleggsliste for én konto."""
    review = load_account_review(client, year)
    entry = review.get(str(konto))
    if not entry:
        return []
    return list(entry.get("attachments") or [])


def load_ub_evidence(client: str | None, year: str | None, konto: str) -> dict | None:
    """Returner primært UB-bevis for én konto, eller None."""
    review = load_account_review(client, year)
    entry = review.get(str(konto))
    if not entry:
        return None
    ev = entry.get("ub_evidence")
    return dict(ev) if isinstance(ev, dict) else None


def save_ub_evidence(
    client: str,
    year: str,
    konto: str,
    evidence: dict,
) -> Path:
    """Lagre (eller overskriv) primært UB-bevis for én konto.

    ``evidence`` forventes å inneholde minst ``attachment_path``. Verdien
    normaliseres via ``_clean_ub_evidence`` før lagring; ukjente felt droppes.
    Oppdaterer ``updated_at`` hvis det ikke allerede er satt.
    """
    if not client or not year or not konto:
        return overrides_path(client or "")
    cleaned = _clean_ub_evidence(evidence)
    if cleaned is None:
        return overrides_path(client)
    if not cleaned.get("updated_at"):
        from datetime import datetime
        cleaned["updated_at"] = datetime.now().isoformat(timespec="seconds")

    payload, year_map = _mutate_account_review(client, year)
    entry = year_map.get(str(konto))
    if not isinstance(entry, dict):
        entry = {"ok": False, "attachments": []}
        year_map[str(konto)] = entry
    if not isinstance(entry.get("attachments"), list):
        entry["attachments"] = []
    entry["ub_evidence"] = cleaned
    return _write_payload(client, payload)


def clear_ub_evidence(client: str, year: str, konto: str) -> Path:
    """Fjern primært UB-bevis for én konto."""
    if not client or not year or not konto:
        return overrides_path(client or "")
    payload, year_map = _mutate_account_review(client, year)
    entry = year_map.get(str(konto))
    if isinstance(entry, dict) and "ub_evidence" in entry:
        entry.pop("ub_evidence", None)
        _prune_entry_if_empty(year_map, str(konto))
    return _write_payload(client, payload)


# ---------------------------------------------------------------------------
# Handlingskobling (konto/regnr ↔ revisjonshandling)
# ---------------------------------------------------------------------------

def _clean_action_link(raw: object) -> dict | None:
    """Normaliser én handlingskobling. Returner None hvis action_id mangler."""
    if not isinstance(raw, dict):
        return None
    try:
        aid = int(raw.get("action_id") or 0)
    except (TypeError, ValueError):
        return None
    if aid <= 0:
        return None
    out: dict = {"action_id": aid}
    for key in ("linked_by", "linked_at", "procedure_name", "area_name", "action_type", "assigned_to"):
        val = raw.get(key)
        if val not in (None, ""):
            out[key] = str(val)
    return out


def _load_links_map(client: str | None, year: str | None, key: str) -> dict[str, list[dict]]:
    if not client or not year:
        return {}
    raw = _read_payload(client)
    by_year = raw.get(key, {})
    if not isinstance(by_year, dict):
        return {}
    year_map = by_year.get(str(year), {})
    if not isinstance(year_map, dict):
        return {}
    out: dict[str, list[dict]] = {}
    for entity, links in year_map.items():
        if not isinstance(links, list):
            continue
        cleaned = [lnk for lnk in (_clean_action_link(x) for x in links) if lnk]
        if cleaned:
            out[str(entity)] = cleaned
    return out


def _set_links_for_entity(
    client: str,
    year: str,
    key: str,
    entity: str,
    action_metadata: Sequence[dict],
) -> Path:
    """Overskriv koblinger for én konto/regnr. Tom liste fjerner alt."""
    if not client or not year or not entity:
        return overrides_path(client or "")
    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    user_stamp = _current_user_stamp()

    payload = _read_payload(client)
    by_year = payload.setdefault(key, {})
    if not isinstance(by_year, dict):
        by_year = {}
        payload[key] = by_year
    year_map = by_year.setdefault(str(year), {})
    if not isinstance(year_map, dict):
        year_map = {}
        by_year[str(year)] = year_map

    existing = year_map.get(str(entity), [])
    if not isinstance(existing, list):
        existing = []
    existing_by_id: dict[int, dict] = {}
    for lnk in existing:
        clean = _clean_action_link(lnk)
        if clean:
            existing_by_id[clean["action_id"]] = clean

    new_list: list[dict] = []
    seen: set[int] = set()
    for meta in action_metadata:
        if not isinstance(meta, dict):
            continue
        try:
            aid = int(meta.get("action_id") or 0)
        except (TypeError, ValueError):
            continue
        if aid <= 0 or aid in seen:
            continue
        seen.add(aid)
        prev = existing_by_id.get(aid, {})
        entry: dict = {"action_id": aid}
        for field_name in ("procedure_name", "area_name", "action_type"):
            val = meta.get(field_name)
            if val not in (None, ""):
                entry[field_name] = str(val)
        entry["linked_by"] = prev.get("linked_by") or user_stamp
        entry["linked_at"] = prev.get("linked_at") or now
        if aid not in existing_by_id:
            entry["linked_by"] = user_stamp
            entry["linked_at"] = now
        # assigned_to: prefer explicit value from meta, else preserve prior
        if "assigned_to" in meta:
            assigned = str(meta.get("assigned_to") or "").strip()
            if assigned:
                entry["assigned_to"] = assigned
        elif prev.get("assigned_to"):
            entry["assigned_to"] = str(prev.get("assigned_to"))
        new_list.append(entry)

    if new_list:
        year_map[str(entity)] = new_list
    else:
        year_map.pop(str(entity), None)
    return _write_payload(client, payload)


def load_account_action_links(client: str | None, year: str | None) -> dict[str, list[dict]]:
    """Last handlingskoblinger per konto for klient/år."""
    return _load_links_map(client, year, "account_actions_by_year")


def load_rl_action_links(client: str | None, year: str | None) -> dict[str, list[dict]]:
    """Last handlingskoblinger per regnskapslinje for klient/år."""
    return _load_links_map(client, year, "rl_actions_by_year")


def set_account_action_links(
    client: str,
    year: str,
    konto: str,
    actions: Sequence[dict],
) -> Path:
    """Overskriv handlingskoblinger for én konto. Tom liste fjerner alle."""
    return _set_links_for_entity(client, year, "account_actions_by_year", str(konto), actions)


def set_rl_action_links(
    client: str,
    year: str,
    regnr: str,
    actions: Sequence[dict],
) -> Path:
    """Overskriv handlingskoblinger for én regnskapslinje. Tom liste fjerner alle."""
    return _set_links_for_entity(client, year, "rl_actions_by_year", str(regnr), actions)
