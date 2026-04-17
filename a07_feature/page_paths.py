from __future__ import annotations

import json
import shutil
from pathlib import Path

import pandas as pd

import app_paths
import classification_config
from trial_balance_reader import read_trial_balance

from . import A07Group, SuggestConfig, from_trial_balance, load_mapping
from . import mapping_source

try:
    import client_store
except Exception:
    client_store = None

try:
    import konto_klassifisering as konto_klassifisering
except Exception:
    konto_klassifisering = None

try:
    import session as session_module
except Exception:
    session_module = None


_GROUP_DATA_COLUMNS = ("GroupId", "Navn", "Members", "Locked")

MATCHER_SETTINGS_DEFAULTS: dict[str, float | int] = {
    "tolerance_rel": 0.02,
    "tolerance_abs": 100.0,
    "max_combo": 2,
    "candidates_per_code": 20,
    "top_suggestions_per_code": 5,
    "historical_account_boost": 0.12,
    "historical_combo_boost": 0.10,
}


def _clean_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def get_a07_workspace_dir(client: str | None, year: str | int | None) -> Path:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    if client_store is not None and client_s and year_s:
        try:
            return client_store.years_dir(client_s, year=str(year_s)) / "a07"
        except Exception:
            pass

    try:
        return app_paths.data_dir() / "a07"
    except Exception:
        return Path("a07")


def default_a07_source_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_source.json"


def default_a07_mapping_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_mapping.json"


def default_a07_groups_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_groups.json"


def default_a07_locks_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_locks.json"


def default_a07_project_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_project.json"


def legacy_global_a07_source_path() -> Path:
    return app_paths.data_dir() / "a07" / "a07_source.json"


def legacy_global_a07_mapping_path() -> Path:
    return app_paths.data_dir() / "a07" / "a07_mapping.json"


def default_global_rulebook_path() -> Path:
    return classification_config.resolve_rulebook_path()


def bundled_default_rulebook_path() -> Path | None:
    project_candidate = Path(__file__).resolve().parent.parent / "a07_rulebook.json"
    if project_candidate.exists():
        return project_candidate

    package_candidate = Path(__file__).resolve().parent / "defaults" / "global_full_a07_rulebook.json"
    if package_candidate.exists():
        return package_candidate

    sibling_candidate = Path(__file__).resolve().parent.parent / "a07" / "global_full_a07_rulebook.json"
    if sibling_candidate.exists():
        return sibling_candidate

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


def default_a07_export_path(client: str | None, year: str | int | None) -> Path:
    year_s = _clean_context_value(year)
    file_name = f"a07_kontroll_{year_s}.xlsx" if year_s else "a07_kontroll.xlsx"
    return get_a07_workspace_dir(client, year) / file_name


def suggest_default_mapping_path(
    a07_path: str | Path | None,
    *,
    client: str | None = None,
    year: str | int | None = None,
) -> Path:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_s and year_s:
        return default_a07_mapping_path(client_s, year_s)

    if a07_path:
        source = Path(a07_path)
        return source.with_name(f"{source.stem}_mapping.json")

    return app_paths.data_dir() / "a07" / "a07_mapping.json"


def resolve_autosave_mapping_path(
    explicit_path: str | Path | None,
    *,
    a07_path: str | Path | None,
    client: str | None,
    year: str | int | None,
) -> Path | None:
    if explicit_path:
        return Path(explicit_path)

    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_s and year_s:
        return suggest_default_mapping_path(a07_path, client=client_s, year=year_s)

    return None


def _path_signature(path: str | Path | None) -> tuple[str | None, int | None, int | None]:
    if not path:
        return (None, None, None)

    file_path = Path(path)
    try:
        stat = file_path.stat()
        return (str(file_path), int(stat.st_mtime_ns), int(stat.st_size))
    except Exception:
        return (str(file_path), None, None)


def _safe_exists(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists()
    except Exception:
        return False


def resolve_context_source_path(
    client: str | None,
    year: str | int | None,
) -> Path | None:
    default_path = default_a07_source_path(client, year)
    if _safe_exists(default_path):
        return default_path

    legacy_path = legacy_global_a07_source_path()
    if _safe_exists(legacy_path):
        return legacy_path

    return None


def resolve_context_mapping_path(
    a07_path: str | Path | None,
    *,
    client: str | None,
    year: str | int | None,
) -> Path | None:
    default_path = suggest_default_mapping_path(a07_path, client=client, year=year)
    if _safe_exists(default_path):
        return default_path

    legacy_path = legacy_global_a07_mapping_path()
    if _safe_exists(legacy_path):
        return legacy_path

    return default_path


def get_active_trial_balance_path_for_context(
    client: str | None,
    year: str | int | None,
) -> Path | None:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return None

    try:
        version = client_store.get_active_version(client_s, year=str(year_s), dtype="sb")
    except Exception:
        version = None

    if version is None:
        return None

    try:
        return Path(str(version.path))
    except Exception:
        return None


def get_context_snapshot_with_paths(
    client: str | None,
    year: str | int | None,
    *,
    tb_path: str | Path | None = None,
    source_path: str | Path | None = None,
    mapping_path: str | Path | None = None,
    groups_path: str | Path | None = None,
    locks_path: str | Path | None = None,
    project_path: str | Path | None = None,
) -> tuple[tuple[str | None, int | None, int | None], ...]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    source_candidate: Path | None = Path(source_path) if source_path else None
    mapping_candidate: Path | None = Path(mapping_path) if mapping_path else None
    groups_candidate: Path | None = Path(groups_path) if groups_path else None
    locks_candidate: Path | None = Path(locks_path) if locks_path else None
    project_candidate: Path | None = Path(project_path) if project_path else None
    tb_candidate: Path | None = Path(tb_path) if tb_path else None

    if client_s and year_s:
        if source_candidate is None:
            source_candidate = resolve_context_source_path(client_s, year_s)
        if mapping_candidate is None:
            mapping_candidate = resolve_context_mapping_path(
                source_candidate,
                client=client_s,
                year=year_s,
            )
        if groups_candidate is None:
            groups_guess = default_a07_groups_path(client_s, year_s)
            if _safe_exists(groups_guess):
                groups_candidate = groups_guess
        if locks_candidate is None:
            locks_guess = default_a07_locks_path(client_s, year_s)
            if _safe_exists(locks_guess):
                locks_candidate = locks_guess
        if project_candidate is None:
            project_guess = default_a07_project_path(client_s, year_s)
            if _safe_exists(project_guess):
                project_candidate = project_guess

    return (
        _path_signature(tb_candidate),
        _path_signature(source_candidate),
        _path_signature(mapping_candidate),
        _path_signature(groups_candidate),
        _path_signature(locks_candidate),
        _path_signature(project_candidate),
    )


def get_context_snapshot(
    client: str | None,
    year: str | int | None,
) -> tuple[tuple[str | None, int | None, int | None], ...]:
    tb_path = get_active_trial_balance_path_for_context(client, year)
    return get_context_snapshot_with_paths(client, year, tb_path=tb_path)


def build_groups_df(groups: dict[str, A07Group], *, locked_codes: set[str] | None = None) -> pd.DataFrame:
    if not groups:
        return pd.DataFrame(columns=list(_GROUP_DATA_COLUMNS))

    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    rows: list[dict[str, object]] = []
    for group_id, group in sorted(groups.items(), key=lambda item: item[0]):
        members = [str(code).strip() for code in (group.member_codes or []) if str(code).strip()]
        rows.append(
            {
                "GroupId": str(group_id),
                "Navn": str(group.group_name or group_id).strip() or str(group_id),
                "Members": ", ".join(members),
                "Locked": str(group_id).strip() in locked,
            }
        )

    return pd.DataFrame(rows, columns=list(_GROUP_DATA_COLUMNS))


def build_default_group_name(
    codes: list[object] | tuple[object, ...],
    *,
    code_names: dict[str, str] | None = None,
) -> str:
    tokens = [str(code).strip() for code in (codes or ()) if str(code).strip()]
    if not tokens:
        return "Ny gruppe"

    names = {
        str(key).strip(): str(value).strip()
        for key, value in (code_names or {}).items()
        if str(key).strip()
    }
    labels: list[str] = []
    for code in tokens[:3]:
        label = names.get(code) or code
        labels.append(label.strip() or code)

    default_name = " + ".join(labels)
    if len(tokens) > 3:
        default_name += " + ..."
    return default_name or "Ny gruppe"


def load_active_trial_balance_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[pd.DataFrame, Path | None]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if not client_s or not year_s:
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), None

    path = get_active_trial_balance_path_for_context(client_s, year_s)
    if path is None or not _safe_exists(path):
        tb_df = getattr(session_module, "tb_df", None) if session_module is not None else None
        if isinstance(tb_df, pd.DataFrame) and not tb_df.empty:
            return from_trial_balance(tb_df), None
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), path

    try:
        tb_df = read_trial_balance(path)
        return from_trial_balance(tb_df), path
    except Exception:
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), path


def copy_a07_source_to_workspace(
    source_path: str | Path,
    *,
    client: str | None,
    year: str | int | None,
) -> Path:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    source = Path(source_path)

    if not client_s or not year_s:
        return source

    target = default_a07_source_path(client_s, year_s)
    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        same = source.resolve() == target.resolve()
    except Exception:
        same = False

    if not same:
        shutil.copy2(source, target)

    return target


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
        basis_strategy="fixed" if basis_col else "per_code",
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


def find_previous_year_mapping_path(
    client: str | None,
    year: str | int | None,
) -> tuple[Path | None, str | None]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return None, None

    try:
        current_year = int(str(year_s))
    except Exception:
        return None, None

    try:
        years_root = client_store.years_dir(client_s, year=str(year_s)).parent
    except Exception:
        return None, None

    candidates: list[tuple[int, Path]] = []
    try:
        for child in years_root.iterdir():
            if not child.is_dir():
                continue
            try:
                child_year = int(child.name)
            except Exception:
                continue
            if child_year >= current_year:
                continue
            mapping_path = child / "a07" / "a07_mapping.json"
            if mapping_path.exists():
                candidates.append((child_year, mapping_path))
    except Exception:
        return None, None

    if not candidates:
        return None, None

    prior_year, prior_path = max(candidates, key=lambda item: item[0])
    return prior_path, str(prior_year)


def find_previous_year_context(
    client: str | None,
    year: str | int | None,
) -> str | None:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return None

    try:
        current_year = int(str(year_s))
    except Exception:
        return None

    try:
        years_root = client_store.years_dir(client_s, year=str(year_s)).parent
    except Exception:
        return None

    prior_years: list[int] = []
    try:
        for child in years_root.iterdir():
            if not child.is_dir():
                continue
            try:
                child_year = int(child.name)
            except Exception:
                continue
            if child_year < current_year:
                prior_years.append(child_year)
    except Exception:
        return None

    if not prior_years:
        return None
    return str(max(prior_years))


def load_previous_year_mapping_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[dict[str, str], Path | None, str | None]:
    """Resolve nearest prior-year mapping from union of legacy JSON and profile
    documents. Within the chosen year, profile document wins over legacy JSON.
    """
    legacy_path, legacy_year = find_previous_year_mapping_path(client, year)
    try:
        legacy_year_i = int(legacy_year) if legacy_year else None
    except Exception:
        legacy_year_i = None

    current_year_i: int | None = None
    year_s = _clean_context_value(year)
    if year_s:
        try:
            current_year_i = int(year_s)
        except Exception:
            current_year_i = None

    doc = None
    doc_year_i: int | None = None
    if current_year_i is not None:
        try:
            doc, doc_year_i = mapping_source.load_nearest_prior_document(
                client or "", current_year_i
            )
        except Exception:
            doc, doc_year_i = None, None

    candidate_years = [y for y in (legacy_year_i, doc_year_i) if y is not None]
    if not candidate_years:
        context_year = find_previous_year_context(client, year)
        return {}, None, context_year

    chosen_year = max(candidate_years)
    chosen_year_s = str(chosen_year)

    if doc is not None and doc_year_i == chosen_year:
        mapping = mapping_source.mapping_from_document(doc)
        if mapping:
            return mapping, None, chosen_year_s
        return {}, None, chosen_year_s

    if legacy_path is not None and legacy_year_i == chosen_year:
        try:
            mapping = load_mapping(legacy_path, client=client, year=chosen_year_s)
        except Exception:
            mapping = {}
        if mapping:
            return mapping, legacy_path, chosen_year_s
        return {}, legacy_path, chosen_year_s

    return {}, None, chosen_year_s
