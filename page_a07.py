from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Sequence

import pandas as pd

import app_paths
import session
from a07_feature import (
    A07WorkspaceData,
    SuggestConfig,
    apply_suggestion_to_mapping,
    export_a07_workbook,
    from_trial_balance,
    load_mapping,
    mapping_to_assigned_df,
    parse_a07_json,
    reconcile_a07_vs_gl,
    save_mapping,
    suggest_mapping_candidates,
    unmapped_accounts_df,
)
from a07_feature.suggest.models import EXCLUDED_A07_CODES
from formatting import format_number_no
from trial_balance_reader import read_trial_balance

try:
    import client_store
except Exception:
    client_store = None


_A07_COLUMNS = (
    ("Kode", "Kode", 180, "w"),
    ("Navn", "Navn", 280, "w"),
    ("Belop", "Belop", 120, "e"),
    ("Status", "Status", 120, "w"),
    ("Kontoer", "Kontoer", 200, "w"),
)

_CONTROL_COLUMNS = (
    ("Kode", "Kode", 340, "w"),
    ("Belop", "Belop", 130, "e"),
    ("Status", "Arbeid", 90, "w"),
    ("Anbefalt", "Neste", 90, "w"),
)

_CONTROL_GL_COLUMNS = (
    ("Konto", "Konto", 80, "w"),
    ("Navn", "Navn", 220, "w"),
    ("IB", "IB", 95, "e"),
    ("Endring", "Endring", 95, "e"),
    ("UB", "UB", 95, "e"),
    ("Kode", "Kode", 120, "w"),
)

_CONTROL_SELECTED_ACCOUNT_COLUMNS = (
    ("Konto", "Konto", 90, "w"),
    ("Navn", "Navn", 260, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 110, "e"),
    ("UB", "UB", 110, "e"),
)

_CONTROL_SUGGESTION_COLUMNS = (
    ("ForslagKontoer", "ForslagKontoer", 180, "w"),
    ("GL_Sum", "GL_Sum", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("Score", "Score", 90, "e"),
    ("WithinTolerance", "Innenfor", 80, "center"),
)

_CONTROL_EXTRA_COLUMNS = ("Navn", "DagensMapping", "Arbeidsstatus", "NesteHandling")

_SUGGESTION_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("KodeNavn", "KodeNavn", 220, "w"),
    ("Basis", "Basis", 80, "w"),
    ("A07_Belop", "A07_Belop", 120, "e"),
    ("ForslagKontoer", "ForslagKontoer", 180, "w"),
    ("GL_Sum", "GL_Sum", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("Score", "Score", 90, "e"),
    ("WithinTolerance", "OK", 70, "center"),
)

_RECONCILE_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("A07_Belop", "A07_Belop", 120, "e"),
    ("GL_Belop", "GL_Belop", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("AntallKontoer", "AntallKontoer", 110, "e"),
    ("Kontoer", "Kontoer", 200, "w"),
    ("WithinTolerance", "OK", 70, "center"),
)

_MAPPING_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Navn", 260, "w"),
    ("Kode", "Kode", 180, "w"),
)

_UNMAPPED_COLUMNS = (
    ("Konto", "Konto", 110, "w"),
    ("Navn", "Navn", 260, "w"),
    ("GL_Belop", "GL_Belop", 120, "e"),
)

_HISTORY_COLUMNS = (
    ("Kode", "Kode", 140, "w"),
    ("Navn", "Navn", 220, "w"),
    ("AarKontoer", "I aar", 180, "w"),
    ("HistorikkKontoer", "Historikk", 180, "w"),
    ("Status", "Status", 160, "w"),
    ("KanBrukes", "Kan brukes", 90, "center"),
    ("Merknad", "Merknad", 320, "w"),
)

_A07_FILTER_LABELS = {
    "alle": "Alle",
    "uloste": "Uloste",
    "avvik": "Avvik",
    "ikke_mappet": "Ikke mappet",
    "ok": "OK",
    "ekskludert": "Ekskludert",
}

_CONTROL_VIEW_LABELS = {
    "neste": "Neste oppgaver",
    "vurdering": "Trenger vurdering",
    "manuell": "Manuell mapping",
    "ferdig": "Ferdig",
    "alle": "Alle",
}

_SUGGESTION_SCOPE_LABELS = {
    "valgt_kode": "Valgt kode",
    "uloste": "Uloste koder",
    "alle": "Alle forslag",
}

_CONTROL_DRAG_IDLE_HINT = "Velg konto til venstre og kode til hoyre, eller dra konto inn."

_NUMERIC_COLUMNS_ZERO_DECIMALS = {"AntallKontoer"}
_NUMERIC_COLUMNS_THREE_DECIMALS = {"Score"}
_NUMERIC_COLUMNS_TWO_DECIMALS = {
    "Belop",
    "Diff",
    "A07_Belop",
    "GL_Belop",
    "GL_Sum",
    "IB",
    "UB",
    "Endring",
    "GL_Belop",
}

_MATCHER_SETTINGS_DEFAULTS = {
    "tolerance_rel": 0.02,
    "tolerance_abs": 100.0,
    "max_combo": 2,
    "candidates_per_code": 20,
    "top_suggestions_per_code": 5,
    "historical_account_boost": 0.12,
    "historical_combo_boost": 0.10,
}


@dataclass(frozen=True)
class _PickerOption:
    key: str
    label: str
    search_text: str


def _empty_a07_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Kode", "Navn", "Belop", "Status", "Kontoer", "Diff"])


def _empty_control_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _CONTROL_COLUMNS] + list(_CONTROL_EXTRA_COLUMNS))


def _empty_gl_df() -> pd.DataFrame:
    return pd.DataFrame(columns=["Konto", "Navn", "IB", "UB", "Endring", "Belop"])


def _empty_suggestions_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _SUGGESTION_COLUMNS])


def _empty_reconcile_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _RECONCILE_COLUMNS])


def _empty_mapping_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _MAPPING_COLUMNS])


def _empty_unmapped_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _UNMAPPED_COLUMNS])


def _empty_history_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _HISTORY_COLUMNS])


def _path_name(value: str | Path | None, *, empty: str = "ikke valgt") -> str:
    if not value:
        return empty
    try:
        return Path(str(value)).name or str(value)
    except Exception:
        return str(value)


def _clean_context_value(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _format_picker_amount(value: object, *, decimals: int = 2) -> str:
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass

    if isinstance(value, Decimal):
        return format_number_no(value, decimals)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format_number_no(value, decimals)
    if isinstance(value, str):
        formatted = format_number_no(value, decimals)
        return formatted if formatted != value else value
    return str(value)


def build_source_overview_rows(
    *,
    a07_text: str,
    tb_text: str,
    mapping_text: str,
    rulebook_text: str,
    history_text: str,
) -> list[tuple[str, str]]:
    return [
        ("A07-kilde", a07_text),
        ("Saldobalanse", tb_text),
        ("Mapping", mapping_text),
        ("Rulebook", rulebook_text),
        ("Historikk", history_text),
    ]


def _numeric_decimals_for_column(column_id: str) -> int | None:
    if column_id in _NUMERIC_COLUMNS_ZERO_DECIMALS:
        return 0
    if column_id in _NUMERIC_COLUMNS_THREE_DECIMALS:
        return 3
    if column_id in _NUMERIC_COLUMNS_TWO_DECIMALS:
        return 2
    return None


def build_gl_picker_options(
    gl_df: pd.DataFrame,
    *,
    basis_col: str = "Endring",
) -> list[_PickerOption]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return []

    amount_col = basis_col if basis_col in gl_df.columns else "Belop"
    work = gl_df.copy()
    work["Konto"] = work["Konto"].astype(str).str.strip()
    work = work[work["Konto"] != ""].copy()
    work = work.drop_duplicates(subset=["Konto"], keep="first")
    work = work.sort_values(by=["Konto"], kind="stable")

    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        konto = str(row.get("Konto") or "").strip()
        if not konto:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get(amount_col))
        label_parts = [konto]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        label = " | ".join(label_parts)
        search_text = " ".join(part.lower() for part in label_parts if part)
        options.append(_PickerOption(key=konto, label=label, search_text=search_text))
    return options


def build_a07_picker_options(a07_df: pd.DataFrame) -> list[_PickerOption]:
    if a07_df is None or a07_df.empty or "Kode" not in a07_df.columns:
        return []

    work = a07_df.copy()
    work["Kode"] = work["Kode"].astype(str).str.strip()
    work = work[work["Kode"] != ""].copy()
    work = work.drop_duplicates(subset=["Kode"], keep="first")
    work = work.sort_values(by=["Kode"], kind="stable")

    options: list[_PickerOption] = []
    for _, row in work.iterrows():
        kode = str(row.get("Kode") or "").strip()
        if not kode:
            continue
        navn = str(row.get("Navn") or "").strip()
        belop = _format_picker_amount(row.get("Belop"))
        label_parts = [kode]
        if navn:
            label_parts.append(navn)
        if belop:
            label_parts.append(belop)
        label = " | ".join(label_parts)
        search_text = " ".join(part.lower() for part in label_parts if part)
        options.append(_PickerOption(key=kode, label=label, search_text=search_text))
    return options


def _filter_picker_options(options: Sequence[_PickerOption], query: str) -> list[_PickerOption]:
    query_s = str(query or "").strip().lower()
    if not query_s:
        return list(options)
    return [option for option in options if query_s in option.search_text]


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


def get_a07_workspace_dir(client: str | None, year: str | int | None) -> Path:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    if client_store is not None and client_s and year_s:
        return client_store.years_dir(client_s, year=str(year_s)) / "a07"

    return app_paths.data_dir() / "a07"


def default_a07_source_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_source.json"


def default_global_rulebook_path() -> Path:
    return app_paths.data_dir() / "a07" / "global_full_a07_rulebook.json"


def bundled_default_rulebook_path() -> Path | None:
    package_candidate = Path(__file__).resolve().parent / "a07_feature" / "defaults" / "global_full_a07_rulebook.json"
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
    return app_paths.data_dir() / "a07" / "matcher_settings.json"


def resolve_rulebook_path(client: str | None, year: str | int | None) -> Path | None:
    _ = (client, year)
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
        return get_a07_workspace_dir(client_s, year_s) / "a07_mapping.json"

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


def get_context_snapshot(
    client: str | None,
    year: str | int | None,
) -> tuple[
    tuple[str | None, int | None, int | None],
    tuple[str | None, int | None, int | None],
    tuple[str | None, int | None, int | None],
]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    source_path = None
    mapping_path = None
    if client_s and year_s:
        source_candidate = default_a07_source_path(client_s, year_s)
        if source_candidate.exists():
            source_path = source_candidate

        mapping_candidate = suggest_default_mapping_path(
            source_path,
            client=client_s,
            year=year_s,
        )
        if mapping_candidate.exists():
            mapping_path = mapping_candidate

    tb_path = get_active_trial_balance_path_for_context(client_s, year_s)
    return (
        _path_signature(tb_path),
        _path_signature(source_path),
        _path_signature(mapping_path),
    )


def load_active_trial_balance_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[pd.DataFrame, Path | None]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if client_store is None or not client_s or not year_s:
        return _empty_gl_df(), None

    path = get_active_trial_balance_path_for_context(client_s, year_s)
    if path is None:
        return _empty_gl_df(), None

    if not path.exists():
        return _empty_gl_df(), None

    try:
        tb_df = read_trial_balance(path)
        return from_trial_balance(tb_df), path
    except Exception:
        return _empty_gl_df(), path


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
    defaults = dict(_MATCHER_SETTINGS_DEFAULTS)
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
    target = Path(path) if path else default_matcher_settings_path()
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
    target = Path(path) if path else default_matcher_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_matcher_settings(data)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def build_suggest_config(rulebook_path: str | Path | None, matcher_settings: object) -> SuggestConfig:
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


def load_previous_year_mapping_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[dict[str, str], Path | None, str | None]:
    path, prior_year = find_previous_year_mapping_path(client, year)
    if path is None:
        return {}, None, None

    try:
        return load_mapping(path), path, prior_year
    except Exception:
        return {}, path, prior_year


def _count_nonempty_mapping(mapping: dict[str, str]) -> int:
    return sum(1 for value in (mapping or {}).values() if str(value).strip())


def _parse_konto_tokens(raw: object) -> list[str]:
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.replace(";", ",").split(",") if part.strip()]


def build_a07_overview_df(a07_df: pd.DataFrame, reconcile_df: pd.DataFrame) -> pd.DataFrame:
    if a07_df is None or a07_df.empty:
        return _empty_a07_df()

    reconcile_lookup: dict[str, pd.Series] = {}
    if reconcile_df is not None and not reconcile_df.empty and "Kode" in reconcile_df.columns:
        for _, row in reconcile_df.iterrows():
            code = str(row.get("Kode") or "").strip()
            if code:
                reconcile_lookup[code] = row

    rows: list[dict[str, object]] = []
    for _, row in a07_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        belop = row.get("Belop")
        status = "Ikke mappet"
        kontoer = ""

        if code.lower() in EXCLUDED_A07_CODES:
            status = "Ekskludert"
        elif code in reconcile_lookup:
            reconcile_row = reconcile_lookup[code]
            kontoer = str(reconcile_row.get("Kontoer") or "").strip()
            if bool(reconcile_row.get("WithinTolerance", False)):
                status = "OK"
            elif int(reconcile_row.get("AntallKontoer", 0) or 0) > 0:
                status = "Avvik"

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "Belop": belop,
                "Status": status,
                "Kontoer": kontoer,
            }
        )

    return pd.DataFrame(rows, columns=["Kode", "Navn", "Belop", "Status", "Kontoer"])


def count_unsolved_a07_codes(a07_overview_df: pd.DataFrame) -> int:
    if a07_overview_df is None or a07_overview_df.empty or "Status" not in a07_overview_df.columns:
        return 0
    statuses = a07_overview_df["Status"].astype(str).str.strip()
    return int(statuses.isin(["Ikke mappet", "Avvik"]).sum())


def filter_a07_overview_df(a07_overview_df: pd.DataFrame, filter_key: str | None) -> pd.DataFrame:
    if a07_overview_df is None:
        return _empty_a07_df()
    if a07_overview_df.empty:
        return a07_overview_df.reset_index(drop=True)

    filter_s = str(filter_key or "alle").strip().lower()
    if filter_s in {"", "alle"}:
        return a07_overview_df.reset_index(drop=True)

    if "Status" not in a07_overview_df.columns:
        return a07_overview_df.reset_index(drop=True)

    statuses = a07_overview_df["Status"].astype(str).str.strip()
    if filter_s == "uloste":
        mask = statuses.isin(["Ikke mappet", "Avvik"])
    elif filter_s == "avvik":
        mask = statuses == "Avvik"
    elif filter_s == "ikke_mappet":
        mask = statuses == "Ikke mappet"
    elif filter_s == "ok":
        mask = statuses == "OK"
    elif filter_s == "ekskludert":
        mask = statuses == "Ekskludert"
    else:
        return a07_overview_df.reset_index(drop=True)

    return a07_overview_df.loc[mask].reset_index(drop=True)


def accounts_for_code(mapping: dict[str, str], code: str | None) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    accounts = [
        str(account).strip()
        for account, mapped_code in (mapping or {}).items()
        if str(account).strip() and str(mapped_code).strip() == code_s
    ]
    return sorted(set(accounts), key=lambda value: (len(value), value))


def _gl_accounts(gl_df: pd.DataFrame) -> set[str]:
    if gl_df is None or gl_df.empty or "Konto" not in gl_df.columns:
        return set()
    return {
        str(account).strip()
        for account in gl_df["Konto"].astype(str).tolist()
        if str(account).strip()
    }


def safe_previous_accounts_for_code(
    code: str | None,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
) -> list[str]:
    code_s = str(code or "").strip()
    if not code_s:
        return []

    previous_accounts = accounts_for_code(mapping_previous, code_s)
    if not previous_accounts:
        return []

    if accounts_for_code(mapping_current, code_s):
        return []

    gl_accounts = _gl_accounts(gl_df)
    if any(account not in gl_accounts for account in previous_accounts):
        return []

    for account in previous_accounts:
        existing_code = str((mapping_current or {}).get(account) or "").strip()
        if existing_code and existing_code != code_s:
            return []

    return previous_accounts


def build_history_comparison_df(
    a07_df: pd.DataFrame,
    gl_df: pd.DataFrame,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
) -> pd.DataFrame:
    if a07_df is None or a07_df.empty:
        return _empty_history_df()

    gl_accounts = _gl_accounts(gl_df)
    rows: list[dict[str, object]] = []

    for _, row in a07_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        current_accounts = accounts_for_code(mapping_current, code)
        previous_accounts = accounts_for_code(mapping_previous, code)
        safe_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=mapping_current,
            mapping_previous=mapping_previous,
            gl_df=gl_df,
        )

        missing_accounts = [account for account in previous_accounts if account not in gl_accounts]
        conflict_accounts = [
            account
            for account in previous_accounts
            if str((mapping_current or {}).get(account) or "").strip()
            and str((mapping_current or {}).get(account) or "").strip() != code
        ]

        notes: list[str] = []
        if code.lower() in EXCLUDED_A07_CODES:
            status = "Ekskludert"
        elif current_accounts and previous_accounts and set(current_accounts) == set(previous_accounts):
            status = "Samme"
            notes.append("Lik fjorarets mapping.")
        elif safe_accounts:
            status = "Klar fra historikk"
            notes.append("Kan brukes direkte.")
        elif previous_accounts and not current_accounts:
            if conflict_accounts:
                status = "Konflikt"
            elif missing_accounts:
                status = "Mangler konto"
            else:
                status = "Historikk"
        elif current_accounts and previous_accounts:
            status = "Avviker"
        elif current_accounts:
            status = "Ny i aar"
        else:
            status = "Ingen historikk"

        if missing_accounts:
            notes.append("Mangler i SB: " + ", ".join(missing_accounts))
        if conflict_accounts:
            notes.append(
                "Konflikt: "
                + ", ".join(f"{account}->{str((mapping_current or {}).get(account) or '').strip()}" for account in conflict_accounts)
            )

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "AarKontoer": ",".join(current_accounts),
                "HistorikkKontoer": ",".join(previous_accounts),
                "Status": status,
                "KanBrukes": bool(safe_accounts),
                "Merknad": " | ".join(note for note in notes if note),
            }
        )

    return pd.DataFrame(rows, columns=[c[0] for c in _HISTORY_COLUMNS])


def select_safe_history_codes(history_compare_df: pd.DataFrame) -> list[str]:
    if history_compare_df is None or history_compare_df.empty:
        return []
    if "Kode" not in history_compare_df.columns or "KanBrukes" not in history_compare_df.columns:
        return []

    selected: list[str] = []
    seen_codes: set[str] = set()
    for _, row in history_compare_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code in seen_codes:
            continue
        if not bool(row.get("KanBrukes", False)):
            continue
        selected.append(code)
        seen_codes.add(code)
    return selected


def best_suggestion_row_for_code(suggestions_df: pd.DataFrame, code: str | None) -> pd.Series | None:
    code_s = str(code or "").strip()
    if not code_s or suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
        return None

    matches = suggestions_df.loc[suggestions_df["Kode"].astype(str).str.strip() == code_s]
    if matches.empty:
        return None
    return matches.iloc[0]


def build_control_suggestion_summary(code: str | None, suggestions_df: pd.DataFrame, selected_row: pd.Series | None) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg kode i hoyre liste for aa se forslag."
    if suggestions_df is None or suggestions_df.empty:
        return f"Ingen forslag funnet for {code_s}."

    count = int(len(suggestions_df))
    row = selected_row if selected_row is not None else suggestions_df.iloc[0]
    accounts = str(row.get("ForslagKontoer") or "").strip() or "-"
    diff = _format_picker_amount(row.get("Diff")) or "-"
    within = "innenfor" if bool(row.get("WithinTolerance", False)) else "sjekkes"
    return f"{count} forslag for {code_s}. Valgt forslag: {accounts} | diff {diff} | {within} toleranse."


def build_control_suggestion_effect_summary(
    code: str | None,
    current_accounts: Sequence[object],
    selected_row: pd.Series | None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg kode i hoyre liste for aa se hva valgt forslag vil gjøre."
    if selected_row is None:
        return f"Velg et forslag for aa se hva som vil bli mappet til {code_s}."

    suggested_accounts = _parse_konto_tokens(selected_row.get("ForslagKontoer"))
    if not suggested_accounts:
        return f"Valgt forslag for {code_s} mangler kontoer."

    current = [str(account).strip() for account in (current_accounts or []) if str(account).strip()]
    suggested = [str(account).strip() for account in suggested_accounts if str(account).strip()]
    current_text = ",".join(current) if current else "ingen mapping"
    suggested_text = ",".join(suggested)
    diff = _format_picker_amount(selected_row.get("Diff")) or "-"
    status_text = "Innenfor toleranse." if bool(selected_row.get("WithinTolerance", False)) else "Sjekk diff før bruk."

    if current and set(current) == set(suggested):
        return f"Valgt forslag matcher dagens mapping {suggested_text}. Diff {diff}. {status_text}"
    if not current:
        return f"Vil mappe {suggested_text} til {code_s}. Diff {diff}. {status_text}"
    return f"Vil erstatte mapping {current_text} med {suggested_text}. Diff {diff}. {status_text}"


def build_control_accounts_summary(accounts_df: pd.DataFrame, code: str | None) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg kode i hoyre liste for aa se mappede kontoer."
    if accounts_df is None or accounts_df.empty:
        return f"Ingen kontoer er mappet til {code_s} ennå."

    count = int(len(accounts_df))
    total_raw = accounts_df.get("Endring", pd.Series(dtype=object)).sum()
    try:
        total_endring = _format_picker_amount(float(total_raw)) or "-"
    except Exception:
        total_endring = _format_picker_amount(total_raw) or "-"
    kontoer = ", ".join(str(value).strip() for value in accounts_df["Konto"].tolist()[:3] if str(value).strip())
    if count > 3:
        kontoer = f"{kontoer}, ..."
    if not kontoer:
        kontoer = "-"
    suffix = "konto" if count == 1 else "kontoer"
    return f"{count} {suffix} mappet til {code_s}. Endring {total_endring}. Kontoer: {kontoer}."


def control_recommendation_label(
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    if has_history:
        return "Historikk"
    if best_suggestion is not None:
        if bool(best_suggestion.get("WithinTolerance", False)):
            return "Forslag"
        return "Sjekk"
    return "Manuell"


def control_next_action_label(
    status: str | None,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    status_s = str(status or "").strip()
    if status_s in {"OK", "Ekskludert"}:
        return "Ingen handling nødvendig."
    if has_history:
        return "Bruk historikk."
    if best_suggestion is not None and bool(best_suggestion.get("WithinTolerance", False)):
        return "Bruk beste forslag."
    return "Map manuelt."


def compact_control_next_action(next_action: object) -> str:
    action_s = str(next_action or "").strip()
    if action_s == "Bruk historikk.":
        return "Historikk"
    if action_s == "Bruk beste forslag.":
        return "Forslag"
    if action_s == "Map manuelt.":
        return "Manuell"
    if action_s == "Ingen handling nÃ¸dvendig.":
        return "Ingen"
    return action_s or "-"


def control_intro_text(
    work_label: object,
    *,
    has_history: bool,
    best_suggestion: pd.Series | None,
) -> str:
    work_s = str(work_label or "").strip()
    if work_s == "Ferdig":
        return "Ser ferdig ut. Kontroller kort og ga videre hvis du er enig."
    if has_history:
        return "Historikk finnes. Start gjerne med a vurdere historikk."
    if best_suggestion is not None and bool(best_suggestion.get("WithinTolerance", False)):
        return "Det finnes et trygt forslag. Start gjerne der."
    return "Ingen trygg automatikk funnet ennå. Bruk manuell mapping eller dra konto inn."


def unresolved_codes(a07_overview_df: pd.DataFrame) -> list[str]:
    if a07_overview_df is None or a07_overview_df.empty or "Kode" not in a07_overview_df.columns:
        return []

    filtered = filter_a07_overview_df(a07_overview_df, "uloste")
    return [
        str(code).strip()
        for code in filtered["Kode"].tolist()
        if str(code).strip()
    ]


def filter_suggestions_df(
    suggestions_df: pd.DataFrame,
    *,
    scope_key: str | None,
    selected_code: str | None = None,
    unresolved_code_values: Sequence[str] | None = None,
) -> pd.DataFrame:
    if suggestions_df is None or suggestions_df.empty:
        return _empty_suggestions_df()
    if "Kode" not in suggestions_df.columns:
        return suggestions_df.copy()

    scope_s = str(scope_key or "valgt_kode").strip().lower()
    work = suggestions_df.copy()
    codes = work["Kode"].astype(str).str.strip()

    if scope_s == "valgt_kode":
        code_s = str(selected_code or "").strip()
        if code_s:
            return work.loc[codes == code_s].copy()
        scope_s = "uloste"

    if scope_s == "uloste":
        unresolved_set = {str(code).strip() for code in (unresolved_code_values or []) if str(code).strip()}
        if unresolved_set:
            return work.loc[codes.isin(unresolved_set)].copy()
        return work.copy()

    return work.copy()


def filter_control_queue_df(control_df: pd.DataFrame, view_key: str | None) -> pd.DataFrame:
    if control_df is None:
        return _empty_control_df()
    if control_df.empty:
        return control_df.reset_index(drop=True)
    if "Arbeidsstatus" not in control_df.columns:
        return control_df.reset_index(drop=True)

    view_s = str(view_key or "neste").strip().lower()
    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    if view_s in {"", "neste"}:
        mask = statuses.isin(["Trenger vurdering", "Trenger manuell mapping"])
    elif view_s == "vurdering":
        mask = statuses == "Trenger vurdering"
    elif view_s == "manuell":
        mask = statuses == "Trenger manuell mapping"
    elif view_s == "ferdig":
        mask = statuses == "Ferdig"
    else:
        return control_df.reset_index(drop=True)
    return control_df.loc[mask].reset_index(drop=True)


def filter_control_search_df(control_df: pd.DataFrame, search_text: object = "") -> pd.DataFrame:
    if control_df is None:
        return _empty_control_df()
    if control_df.empty:
        return control_df.reset_index(drop=True)

    search_s = str(search_text or "").strip().casefold()
    if not search_s:
        return control_df.reset_index(drop=True)

    haystack = pd.Series("", index=control_df.index, dtype="object")
    for column in ("Kode", "Navn", "Anbefalt", "NesteHandling", "DagensMapping"):
        if column in control_df.columns:
            haystack = haystack.str.cat(control_df[column].fillna("").astype(str), sep=" ")
    return control_df.loc[haystack.str.casefold().str.contains(search_s, regex=False)].reset_index(drop=True)


def build_control_queue_df(
    a07_overview_df: pd.DataFrame,
    suggestions_df: pd.DataFrame,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    gl_df: pd.DataFrame,
) -> pd.DataFrame:
    if a07_overview_df is None or a07_overview_df.empty:
        return _empty_control_df()

    rows: list[dict[str, object]] = []
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        status = str(row.get("Status") or "").strip()
        current_accounts = accounts_for_code(mapping_current, code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=mapping_current,
            mapping_previous=mapping_previous,
            gl_df=gl_df,
        )
        best_row = best_suggestion_row_for_code(suggestions_df, code)
        next_action = control_next_action_label(
            status,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if status in {"OK", "Ekskludert"}:
            work_status = "Ferdig"
        elif next_action in {"Bruk historikk.", "Bruk beste forslag."}:
            work_status = "Trenger vurdering"
        else:
            work_status = "Trenger manuell mapping"
        if work_status == "Ferdig":
            display_status = "Ferdig"
        elif work_status == "Trenger vurdering":
            display_status = "Vurdering"
        else:
            display_status = "Manuell"

        recommended = control_recommendation_label(
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "Belop": row.get("Belop"),
                "Status": display_status,
                "DagensMapping": ", ".join(current_accounts),
                "Anbefalt": recommended,
                "NesteHandling": next_action,
                "Arbeidsstatus": work_status,
            }
        )

    return pd.DataFrame(rows, columns=[c[0] for c in _CONTROL_COLUMNS] + list(_CONTROL_EXTRA_COLUMNS))


def build_control_gl_df(gl_df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    if gl_df is None or gl_df.empty:
        return pd.DataFrame(columns=[c[0] for c in _CONTROL_GL_COLUMNS])

    mapping_clean = {str(account).strip(): str(code).strip() for account, code in (mapping or {}).items()}
    rows: list[dict[str, object]] = []
    for _, row in gl_df.iterrows():
        konto = str(row.get("Konto") or "").strip()
        if not konto:
            continue
        rows.append(
            {
                "Konto": konto,
                "Navn": row.get("Navn"),
                "IB": row.get("IB"),
                "Endring": row.get("Endring"),
                "UB": row.get("UB"),
                "Kode": mapping_clean.get(konto, ""),
            }
        )

    return pd.DataFrame(rows, columns=[c[0] for c in _CONTROL_GL_COLUMNS])


def build_control_selected_account_df(gl_df: pd.DataFrame, mapping: dict[str, str], code: str | None) -> pd.DataFrame:
    code_s = str(code or "").strip()
    if not code_s:
        return pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])

    control_gl_df = build_control_gl_df(gl_df, mapping)
    if control_gl_df.empty:
        return pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])

    selected = control_gl_df.loc[control_gl_df["Kode"].astype(str).str.strip() == code_s].copy()
    if selected.empty:
        return pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
    return selected[[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]].reset_index(drop=True)


def filter_control_gl_df(
    control_gl_df: pd.DataFrame,
    *,
    search_text: object = "",
    only_unmapped: bool = False,
) -> pd.DataFrame:
    if control_gl_df is None or control_gl_df.empty:
        return pd.DataFrame(columns=[c[0] for c in _CONTROL_GL_COLUMNS])

    filtered = control_gl_df.copy()
    if only_unmapped and "Kode" in filtered.columns:
        filtered = filtered.loc[filtered["Kode"].astype(str).str.strip() == ""].copy()

    search_s = str(search_text or "").strip().casefold()
    if search_s:
        haystack = pd.Series("", index=filtered.index, dtype="object")
        for column in ("Konto", "Navn", "Kode"):
            if column in filtered.columns:
                haystack = haystack.str.cat(filtered[column].fillna("").astype(str), sep=" ")
        filtered = filtered.loc[haystack.str.casefold().str.contains(search_s, regex=False)].copy()

    return filtered.reset_index(drop=True)


def build_control_bucket_summary(control_df: pd.DataFrame) -> str:
    if control_df is None or control_df.empty or "Arbeidsstatus" not in control_df.columns:
        return "Ferdig 0 | Vurdering 0 | Manuell 0"

    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    done = int((statuses == "Ferdig").sum())
    review = int((statuses == "Trenger vurdering").sum())
    manual = int((statuses == "Trenger manuell mapping").sum())
    return f"Ferdig {done} | Vurdering {review} | Manuell {manual}"


def control_tree_tag(work_status: object) -> str:
    status_s = str(work_status or "").strip()
    if status_s == "Ferdig":
        return "control_done"
    if status_s == "Trenger vurdering":
        return "control_review"
    if status_s == "Trenger manuell mapping":
        return "control_manual"
    return "control_default"


def control_gl_tree_tag(
    row: pd.Series,
    selected_code: str | None,
    suggested_accounts: Sequence[object] | None = None,
) -> str:
    konto = str(row.get("Konto") or "").strip()
    mapped_code = str(row.get("Kode") or "").strip()
    selected_code_s = str(selected_code or "").strip()
    suggested = {str(account).strip() for account in (suggested_accounts or ()) if str(account).strip()}
    if not mapped_code:
        if konto and konto in suggested:
            return "control_gl_suggestion"
        return "control_gl_unmapped"
    if selected_code_s and mapped_code == selected_code_s:
        return "control_gl_selected"
    if konto and konto in suggested:
        return "control_gl_suggestion"
    return "control_gl_mapped"


def suggestion_tree_tag(row: pd.Series) -> str:
    try:
        within = bool(row.get("WithinTolerance", False))
    except Exception:
        within = False
    try:
        score = float(row.get("Score") or 0.0)
    except Exception:
        score = 0.0

    if within:
        return "suggestion_ok"
    if score >= 0.85:
        return "suggestion_review"
    return "suggestion_default"


def reconcile_tree_tag(row: pd.Series) -> str:
    try:
        within = bool(row.get("WithinTolerance", False))
    except Exception:
        within = False
    return "reconcile_ok" if within else "reconcile_diff"


def control_action_style(work_label: object) -> str:
    label_s = str(work_label or "").strip()
    if label_s == "Ferdig":
        return "Ready.TLabel"
    if label_s in {"Vurdering", "Manuell"}:
        return "Warning.TLabel"
    return "Muted.TLabel"


def build_mapping_history_details(
    code: str | None,
    *,
    mapping_current: dict[str, str],
    mapping_previous: dict[str, str],
    previous_year: str | None = None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg en kode for aa se historikk."

    current_accounts = accounts_for_code(mapping_current, code_s)
    previous_accounts = accounts_for_code(mapping_previous, code_s)

    current_text = ", ".join(current_accounts) if current_accounts else "ingen mapping i aar"
    if previous_accounts:
        previous_text = ", ".join(previous_accounts)
    else:
        previous_text = "ingen tidligere mapping"

    if current_accounts and previous_accounts:
        relation = "Samme som historikk." if set(current_accounts) == set(previous_accounts) else "Avviker fra historikk."
    elif current_accounts:
        relation = "Ny mapping i aar."
    elif previous_accounts:
        relation = "Historikk finnes, men ikke mapping i aar."
    else:
        relation = "Ingen mapping ennÃ¥."

    history_label = previous_year or "tidligere aar"
    return f"{code_s} | I aar: {current_text} | {history_label}: {previous_text} | {relation}"


def select_batch_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    min_score: float = 0.85,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []

    mapping_nonempty = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_existing or {}).items()
        if str(account).strip() and str(code).strip()
    }

    selected_rows: list[int] = []
    seen_codes: set[str] = set()
    reserved_accounts: set[str] = set()

    for idx, row in suggestions_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code in seen_codes:
            continue

        if not bool(row.get("WithinTolerance", False)):
            continue

        try:
            score = float(row.get("Score") or 0.0)
        except Exception:
            score = 0.0
        if score < float(min_score):
            continue

        accounts = _parse_konto_tokens(row.get("ForslagKontoer"))
        if not accounts:
            continue

        conflict = False
        for account in accounts:
            existing_code = mapping_nonempty.get(account)
            if existing_code and existing_code != code:
                conflict = True
                break
            if account in reserved_accounts:
                conflict = True
                break

        if conflict:
            continue

        selected_rows.append(int(idx))
        seen_codes.add(code)
        reserved_accounts.update(accounts)

    return selected_rows


def select_magic_wand_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    unresolved_codes: Sequence[object] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []

    unresolved_set = {
        str(code).strip()
        for code in (unresolved_codes or ())
        if str(code).strip()
    }

    mapping_nonempty = {
        str(account).strip(): str(code).strip()
        for account, code in (mapping_existing or {}).items()
        if str(account).strip() and str(code).strip()
    }

    selected_rows: list[int] = []
    seen_codes: set[str] = set()
    reserved_accounts: set[str] = set()

    for idx, row in suggestions_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        if not code or code in seen_codes:
            continue
        if unresolved_set and code not in unresolved_set:
            continue
        if not bool(row.get("WithinTolerance", False)):
            continue

        accounts = _parse_konto_tokens(row.get("ForslagKontoer"))
        if not accounts:
            continue

        conflict = False
        for account in accounts:
            existing_code = mapping_nonempty.get(account)
            if existing_code and existing_code != code:
                conflict = True
                break
            if account in reserved_accounts:
                conflict = True
                break

        if conflict:
            continue

        selected_rows.append(int(idx))
        seen_codes.add(code)
        reserved_accounts.update(accounts)

    return selected_rows


def open_manual_mapping_dialog(
    parent: tk.Misc,
    *,
    account_options: Sequence[_PickerOption],
    code_options: Sequence[_PickerOption],
    initial_account: str | None = None,
    initial_code: str | None = None,
    title: str = "Ny eller rediger mapping",
) -> tuple[str, str] | None:
    if not account_options or not code_options:
        return None

    win = tk.Toplevel(parent)
    win.title(title)
    win.transient(parent)
    win.grab_set()
    win.resizable(True, True)
    win.geometry("1100x560")

    result: dict[str, tuple[str, str] | None] = {"value": None}
    selected_account = str(initial_account or "").strip() or None
    selected_code = str(initial_code or "").strip() or None
    filtered_accounts = list(account_options)
    filtered_codes = list(code_options)

    outer = ttk.Frame(win, padding=10)
    outer.pack(fill="both", expand=True)

    ttk.Label(
        outer,
        text="Velg konto og A07-kode. Skriv i sokefeltene for aa filtrere listene.",
    ).pack(anchor="w")

    columns = ttk.Frame(outer)
    columns.pack(fill="both", expand=True, pady=(8, 0))
    columns.columnconfigure(0, weight=1)
    columns.columnconfigure(1, weight=1)
    columns.rowconfigure(0, weight=1)

    status_var = tk.StringVar(value="")
    account_query = tk.StringVar(value="")
    code_query = tk.StringVar(value="")

    def _build_picker_column(parent_frame: ttk.Frame, title_text: str) -> tuple[ttk.Entry, tk.Listbox, ttk.Label]:
        ttk.Label(parent_frame, text=title_text).pack(anchor="w")
        entry = ttk.Entry(parent_frame)
        entry.pack(fill="x", pady=(4, 6))

        list_frame = ttk.Frame(parent_frame)
        list_frame.pack(fill="both", expand=True)

        ybar = ttk.Scrollbar(list_frame, orient="vertical")
        ybar.pack(side="right", fill="y")

        listbox = tk.Listbox(list_frame, activestyle="dotbox", exportselection=False, yscrollcommand=ybar.set)
        listbox.pack(side="left", fill="both", expand=True)
        ybar.config(command=listbox.yview)

        count_label = ttk.Label(parent_frame, text="")
        count_label.pack(anchor="w", pady=(6, 0))
        return entry, listbox, count_label

    account_frame = ttk.Frame(columns)
    account_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
    code_frame = ttk.Frame(columns)
    code_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

    account_entry, account_listbox, account_count = _build_picker_column(account_frame, "Konto")
    code_entry, code_listbox, code_count = _build_picker_column(code_frame, "A07-kode")

    account_entry.configure(textvariable=account_query)
    code_entry.configure(textvariable=code_query)

    def _selected_option(listbox: tk.Listbox, options: Sequence[_PickerOption]) -> _PickerOption | None:
        try:
            idx = int(listbox.curselection()[0])
        except Exception:
            return None
        if idx < 0 or idx >= len(options):
            return None
        return options[idx]

    def _fill_list(
        listbox: tk.Listbox,
        options: Sequence[_PickerOption],
        count_label: ttk.Label,
        total_count: int,
        selected_key: str | None,
    ) -> None:
        listbox.delete(0, tk.END)
        for option in options:
            listbox.insert(tk.END, option.label)

        count_label.configure(text=f"Viser {len(options)} av {total_count}")
        if not options:
            return

        idx = 0
        if selected_key:
            for pos, option in enumerate(options):
                if option.key == selected_key:
                    idx = pos
                    break

        listbox.selection_clear(0, tk.END)
        listbox.selection_set(idx)
        listbox.activate(idx)
        listbox.see(idx)

    def _update_status() -> None:
        account_text = selected_account or "-"
        code_text = selected_code or "-"
        status_var.set(f"Valg: {account_text} -> {code_text}")

    def _refresh_account_list() -> None:
        nonlocal filtered_accounts, selected_account
        filtered_accounts = _filter_picker_options(account_options, account_query.get())
        _fill_list(
            account_listbox,
            filtered_accounts,
            account_count,
            len(account_options),
            selected_account,
        )
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _refresh_code_list() -> None:
        nonlocal filtered_codes, selected_code
        filtered_codes = _filter_picker_options(code_options, code_query.get())
        _fill_list(
            code_listbox,
            filtered_codes,
            code_count,
            len(code_options),
            selected_code,
        )
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_account_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_account
        option = _selected_option(account_listbox, filtered_accounts)
        selected_account = option.key if option is not None else None
        _update_status()

    def _on_code_select(_event: tk.Event | None = None) -> None:
        nonlocal selected_code
        option = _selected_option(code_listbox, filtered_codes)
        selected_code = option.key if option is not None else None
        _update_status()

    def _on_ok() -> None:
        if not selected_account or not selected_code:
            messagebox.showinfo("A07", "Velg baade konto og A07-kode.", parent=win)
            return
        result["value"] = (selected_account, selected_code)
        win.destroy()

    def _on_cancel() -> None:
        result["value"] = None
        win.destroy()

    account_query.trace_add("write", lambda *_args: _refresh_account_list())
    code_query.trace_add("write", lambda *_args: _refresh_code_list())

    account_listbox.bind("<<ListboxSelect>>", _on_account_select)
    code_listbox.bind("<<ListboxSelect>>", _on_code_select)
    account_listbox.bind("<Double-Button-1>", lambda _event: code_entry.focus_set())
    code_listbox.bind("<Double-Button-1>", lambda _event: _on_ok())
    win.bind("<Return>", lambda *_args: _on_ok())
    win.bind("<Escape>", lambda *_args: _on_cancel())

    ttk.Label(outer, textvariable=status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))

    buttons = ttk.Frame(outer)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="Avbryt", command=_on_cancel).pack(side="right")
    ttk.Button(buttons, text="Bruk mapping", command=_on_ok).pack(side="right", padx=(0, 6))

    _refresh_account_list()
    _refresh_code_list()
    account_entry.focus_set()

    win.wait_window()
    return result["value"]


class A07Page(ttk.Frame):
    def __init__(self, parent: tk.Misc, *args, **kwargs) -> None:
        super().__init__(parent, *args, **kwargs)

        self.workspace = A07WorkspaceData(
            a07_df=_empty_a07_df(),
            gl_df=_empty_gl_df(),
            mapping={},
            suggestions=None,
        )
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.control_gl_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_GL_COLUMNS])
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.previous_mapping: dict[str, str] = {}
        self.matcher_settings = load_matcher_settings()

        self.a07_path: Path | None = None
        self.tb_path: Path | None = None
        self.mapping_path: Path | None = None
        self.rulebook_path: Path | None = None
        self.previous_mapping_path: Path | None = None
        self.previous_mapping_year: str | None = None
        self._context_key: tuple[str | None, str | None] = (None, None)
        self._context_snapshot = get_context_snapshot(None, None)
        self._matcher_admin_window: tk.Toplevel | None = None
        self._matcher_admin_state: dict[str, object] | None = None
        self._source_overview_window: tk.Toplevel | None = None
        self._drag_unmapped_account: str | None = None
        self._drag_control_accounts: list[str] = []
        self._control_details_auto_revealed = False

        self.summary_var = tk.StringVar(value="Ingen A07-data lastet ennå.")
        self.status_var = tk.StringVar(value="Last A07 JSON for aa starte.")
        self.details_var = tk.StringVar(value="Bruk Kilder... for filoversikt.")
        self.a07_path_var = tk.StringVar(value="A07: ikke valgt")
        self.tb_path_var = tk.StringVar(value="Saldobalanse: ingen aktiv SB-versjon")
        self.mapping_path_var = tk.StringVar(value="Mapping: ikke valgt")
        self.rulebook_path_var = tk.StringVar(value="Rulebook: standard heuristikk")
        self.history_path_var = tk.StringVar(value="Historikk: ingen tidligere A07-mapping")
        self.suggestion_details_var = tk.StringVar(value="Velg et forslag for aa se hvorfor det scorer hoeyt.")
        self.control_suggestion_summary_var = tk.StringVar(value="Velg kode i hoyre liste for aa se forslag.")
        self.control_suggestion_effect_var = tk.StringVar(value="Velg kode i hoyre liste for aa se hva valgt forslag vil gjøre.")
        self.history_details_var = tk.StringVar(value="Velg en kode for aa se historikk.")
        self.control_summary_var = tk.StringVar(value="Velg en A07-kode for aa starte arbeidet.")
        self.control_intro_var = tk.StringVar(value="Velg kode i høyre liste.")
        self.control_meta_var = tk.StringVar(value="")
        self.control_match_var = tk.StringVar(value="")
        self.control_mapping_var = tk.StringVar(value="")
        self.control_history_var = tk.StringVar(value="")
        self.control_best_var = tk.StringVar(value="")
        self.control_next_var = tk.StringVar(value="Velg kode for aa starte.")
        self.control_accounts_summary_var = tk.StringVar(value="Velg kode i hoyre liste for aa se mappede kontoer.")
        self.control_drag_var = tk.StringVar(value=_CONTROL_DRAG_IDLE_HINT)
        self.control_bucket_var = tk.StringVar(value="Ferdig 0 | Vurdering 0 | Manuell 0")
        self.a07_filter_var = tk.StringVar(value="neste")
        self.a07_filter_label_var = tk.StringVar(value=_CONTROL_VIEW_LABELS["neste"])
        self.control_code_filter_var = tk.StringVar(value="")
        self.control_gl_filter_var = tk.StringVar(value="")
        self.control_gl_unmapped_only_var = tk.BooleanVar(value=False)
        self.suggestion_scope_var = tk.StringVar(value="valgt_kode")
        self.suggestion_scope_label_var = tk.StringVar(value=_SUGGESTION_SCOPE_LABELS["valgt_kode"])

        self._build_ui()
        self.bind("<Visibility>", self._on_visible, add="+")
        try:
            parent.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed, add="+")
        except Exception:
            pass
        self.refresh_from_session()

    def refresh_from_session(self, session_module=session) -> None:
        context = self._session_context(session_module)
        snapshot = get_context_snapshot(*context)
        if context != self._context_key or snapshot != self._context_snapshot:
            self._context_key = context
            self._context_snapshot = snapshot
            self._restore_context_state(*context)
            return
        self._update_summary()

    def _on_visible(self, _event: tk.Event | None = None) -> None:
        self.refresh_from_session()

    def _on_notebook_tab_changed(self, event: tk.Event | None = None) -> None:
        if event is None:
            return
        try:
            notebook = event.widget
            selected = notebook.nametowidget(notebook.select())
        except Exception:
            return
        if selected is self:
            self.refresh_from_session()

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Last A07", command=self._load_a07_clicked).pack(side="left")
        ttk.Button(toolbar, text="Oppdater", command=self._refresh_clicked).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Tryllestav", command=self._magic_match_clicked).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Eksporter", command=self._export_clicked).pack(side="left", padx=(6, 0))

        tools_btn = ttk.Menubutton(toolbar, text="Mer...")
        tools_menu = tk.Menu(tools_btn, tearoff=0)
        tools_menu.add_command(label="Avansert mapping", command=self._open_manual_mapping_clicked)
        tools_menu.add_command(label="Kilder...", command=self._open_source_overview)
        tools_menu.add_separator()
        tools_menu.add_command(label="Bruk aktiv saldobalanse", command=self._sync_active_tb_clicked)
        tools_menu.add_separator()
        tools_menu.add_command(label="Last mapping", command=self._load_mapping_clicked)
        tools_menu.add_command(label="Lagre mapping", command=self._save_mapping_clicked)
        tools_menu.add_command(label="Vis mappinger", command=self._open_mapping_overview)
        tools_menu.add_command(label="Last rulebook", command=self._load_rulebook_clicked)
        tools_menu.add_command(label="Matcher-admin", command=self._open_matcher_admin)
        tools_menu.add_separator()
        tools_menu.add_command(label="Bruk valgt forslag", command=self._apply_selected_suggestion)
        tools_menu.add_command(label="Bruk sikre forslag", command=self._apply_batch_suggestions_clicked)
        tools_menu.add_command(label="Bruk sikre historikkmappinger", command=self._apply_batch_history_mappings)
        tools_btn["menu"] = tools_menu
        tools_btn.pack(side="left", padx=(12, 0))

        info = ttk.Frame(self, padding=(8, 0, 8, 8))
        info.pack(fill="x")
        info.columnconfigure(0, weight=1)

        ttk.Label(info, textvariable=self.summary_var).grid(row=0, column=0, sticky="w")

        self.nb = ttk.Notebook(self)
        workspace_host = ttk.Frame(self, padding=(8, 0, 8, 8))
        workspace_host.pack(fill="both", expand=True)

        tab_control = ttk.Frame(workspace_host)
        tab_control.pack(fill="both", expand=True)
        support_host = ttk.Frame(self)
        tab_history = ttk.Frame(support_host)
        tab_suggestions = ttk.Frame(support_host)
        tab_reconcile = ttk.Frame(support_host)
        tab_unmapped = ttk.Frame(support_host)
        tab_mapping = ttk.Frame(support_host)
        self.tab_control = tab_control
        self.tab_history = tab_history
        self.tab_suggestions = tab_suggestions
        self.tab_unmapped = tab_unmapped
        self.tab_mapping = tab_mapping

        a07_actions = ttk.Frame(tab_control, padding=(0, 8, 0, 0))
        a07_actions.pack(fill="x")
        ttk.Label(a07_actions, text="Vis:").pack(side="left")
        a07_filter = ttk.Combobox(
            a07_actions,
            state="readonly",
            width=16,
            values=[_CONTROL_VIEW_LABELS[key] for key in _CONTROL_VIEW_LABELS],
            textvariable=self.a07_filter_label_var,
        )
        a07_filter.pack(side="left", padx=(6, 0))
        self.a07_filter_widget = a07_filter
        a07_filter.set(_CONTROL_VIEW_LABELS["neste"])
        a07_filter.bind("<<ComboboxSelected>>", lambda _event: self._on_a07_filter_changed())
        ttk.Label(a07_actions, text="Sok:").pack(side="left", padx=(12, 0))
        self.entry_control_code_filter = ttk.Entry(
            a07_actions,
            textvariable=self.control_code_filter_var,
            width=18,
        )
        self.entry_control_code_filter.pack(side="left", padx=(6, 0))
        self.entry_control_code_filter.bind("<KeyRelease>", lambda _event: self._on_control_code_filter_changed())
        self.btn_control_toggle_details = ttk.Button(
            a07_actions,
            text="Vis detaljer",
            command=self._toggle_control_details,
        )
        self.btn_control_toggle_details.pack(side="right")
        ttk.Label(
            a07_actions,
            textvariable=self.control_bucket_var,
            style="Muted.TLabel",
            justify="right",
        ).pack(side="right", padx=(0, 10))

        control_workspace = ttk.Frame(tab_control)
        control_workspace.pack(fill="both", expand=True, pady=(8, 0))
        self.control_workspace = control_workspace

        control_top = ttk.Panedwindow(control_workspace, orient="horizontal")
        control_top.pack(fill="both", expand=True)

        control_gl_panel = ttk.LabelFrame(control_top, text="GL-kontoer", padding=(8, 8))
        control_assign_panel = ttk.Frame(control_top, padding=(2, 22, 2, 0))
        control_a07_panel = ttk.LabelFrame(control_top, text="A07-koder", padding=(8, 8))
        control_top.add(control_gl_panel, weight=3)
        control_top.add(control_assign_panel, weight=0)
        control_top.add(control_a07_panel, weight=4)

        control_gl_filters = ttk.Frame(control_gl_panel)
        control_gl_filters.pack(fill="x", pady=(0, 6))
        ttk.Label(control_gl_filters, text="Filter:").pack(side="left")
        self.entry_control_gl_filter = ttk.Entry(
            control_gl_filters,
            textvariable=self.control_gl_filter_var,
            width=24,
        )
        self.entry_control_gl_filter.pack(side="left", padx=(6, 8))
        self.entry_control_gl_filter.bind("<KeyRelease>", lambda _event: self._on_control_gl_filter_changed())
        ttk.Checkbutton(
            control_gl_filters,
            text="Kun umappede",
            variable=self.control_gl_unmapped_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left")
        self.tree_control_gl = self._build_tree_tab(control_gl_panel, _CONTROL_GL_COLUMNS)
        try:
            self.tree_control_gl.tag_configure("control_gl_unmapped", background="#FFF3CD", foreground="#7A5B00")
            self.tree_control_gl.tag_configure("control_gl_mapped", background="#FFFFFF", foreground="#1F2430")
            self.tree_control_gl.tag_configure("control_gl_selected", background="#D9ECFF", foreground="#0B4F8A")
            self.tree_control_gl.tag_configure("control_gl_suggestion", background="#E8F6EA", foreground="#256D5A")
        except Exception:
            pass

        self.tree_a07 = self._build_tree_tab(control_a07_panel, _CONTROL_COLUMNS)
        try:
            self.tree_a07.tag_configure("control_done", background="#E2F1EB", foreground="#256D5A")
            self.tree_a07.tag_configure("control_review", background="#FCEBD9", foreground="#9F5B2E")
            self.tree_a07.tag_configure("control_manual", background="#FCE4D6", foreground="#8A3B12")
            self.tree_a07.tag_configure("control_default", background="#FFFFFF", foreground="#1F2430")
        except Exception:
            pass

        self.btn_control_assign = ttk.Button(
            control_assign_panel,
            text="Tildel",
            command=self._assign_selected_control_mapping,
        )
        self.btn_control_assign.pack(fill="x")
        self.btn_control_clear = ttk.Button(
            control_assign_panel,
            text="Fjern",
            command=self._clear_selected_control_mapping,
        )
        self.btn_control_clear.pack(fill="x", pady=(8, 0))
        for button in (self.btn_control_assign, self.btn_control_clear):
            button.state(["disabled"])

        control_lower = ttk.Frame(control_workspace)
        control_lower.pack(fill="x", pady=(8, 0))
        self.control_lower_panel = control_lower

        control_status = ttk.LabelFrame(control_lower, text="Valgt kode", padding=(8, 5))
        control_status.pack(fill="x")
        self.control_panel = control_status
        control_status.columnconfigure(0, weight=1)
        control_status.columnconfigure(1, weight=0)

        control_status_left = ttk.Frame(control_status)
        control_status_left.grid(row=0, column=0, sticky="ew")
        ttk.Label(
            control_status_left,
            textvariable=self.control_summary_var,
            style="Section.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(
            control_status_left,
            textvariable=self.control_meta_var,
            style="Muted.TLabel",
            wraplength=900,
            justify="left",
        ).pack(anchor="w", pady=(2, 0))

        control_actions = ttk.Frame(control_status)
        control_actions.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        self.btn_control_best = ttk.Button(
            control_actions,
            text="Bruk forslag",
            command=self._apply_best_suggestion_for_selected_code,
        )
        self.btn_control_best.pack(side="left")
        self.btn_control_history = ttk.Button(
            control_actions,
            text="Bruk historikk",
            command=self._apply_history_for_selected_code,
        )
        self.btn_control_history.pack(side="left", padx=(6, 0))
        for button in (self.btn_control_best, self.btn_control_history):
            button.state(["disabled"])

        ttk.Label(
            control_status,
            textvariable=self.control_match_var,
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.lbl_control_drag = ttk.Label(
            control_status,
            textvariable=self.control_drag_var,
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        )

        control_detail_panes = ttk.Panedwindow(control_lower, orient="vertical")
        control_detail_panes.pack(fill="both", expand=True, pady=(6, 0))
        self.control_detail_panes = control_detail_panes

        control_suggest_panel = ttk.LabelFrame(control_detail_panes, text="Forslag for valgt kode", padding=(8, 8))
        control_detail_panes.add(control_suggest_panel, weight=3)
        control_suggest_actions = ttk.Frame(control_suggest_panel)
        control_suggest_actions.pack(fill="x", pady=(0, 8))
        ttk.Button(control_suggest_actions, text="Tryllestav", command=self._run_selected_control_action).pack(
            side="right",
            padx=(0, 0),
        )
        ttk.Button(control_suggest_actions, text="Bruk forslag", command=self._apply_selected_suggestion).pack(
            side="right",
            padx=(0, 6),
        )
        ttk.Label(
            control_suggest_panel,
            textvariable=self.control_suggestion_summary_var,
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(
            control_suggest_panel,
            textvariable=self.control_suggestion_effect_var,
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        self.tree_control_suggestions = self._build_tree_tab(control_suggest_panel, _CONTROL_SUGGESTION_COLUMNS)
        try:
            self.tree_control_suggestions.tag_configure("suggestion_ok", background="#E2F1EB", foreground="#256D5A")
            self.tree_control_suggestions.tag_configure(
                "suggestion_review", background="#FCEBD9", foreground="#9F5B2E"
            )
            self.tree_control_suggestions.tag_configure(
                "suggestion_default", background="#FFFFFF", foreground="#1F2430"
            )
        except Exception:
            pass

        control_accounts_panel = ttk.LabelFrame(
            control_detail_panes,
            text="Kontoer mappet til valgt kode",
            padding=(8, 8),
        )
        control_detail_panes.add(control_accounts_panel, weight=2)
        control_accounts_actions = ttk.Frame(control_accounts_panel)
        control_accounts_actions.pack(fill="x", pady=(0, 8))
        ttk.Label(
            control_accounts_actions,
            textvariable=self.control_accounts_summary_var,
            style="Muted.TLabel",
            wraplength=920,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            control_accounts_actions,
            text="Vis i GL",
            command=self._focus_selected_control_account_in_gl,
        ).pack(side="right")
        ttk.Button(
            control_accounts_actions,
            text="Fjern valgt",
            command=self._remove_selected_control_accounts,
        ).pack(side="right", padx=(0, 6))
        self.tree_control_accounts = self._build_tree_tab(
            control_accounts_panel,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
        )

        self.tree_history = self._build_tree_tab(tab_history, _HISTORY_COLUMNS)
        self.tree_suggestions = self._build_tree_tab(tab_suggestions, _SUGGESTION_COLUMNS)
        try:
            self.tree_suggestions.tag_configure("suggestion_ok", background="#E2F1EB", foreground="#256D5A")
            self.tree_suggestions.tag_configure("suggestion_review", background="#FCEBD9", foreground="#9F5B2E")
            self.tree_suggestions.tag_configure("suggestion_default", background="#FFFFFF", foreground="#1F2430")
        except Exception:
            pass
        self.tree_reconcile = self._build_tree_tab(tab_reconcile, _RECONCILE_COLUMNS)
        try:
            self.tree_reconcile.tag_configure("reconcile_ok", background="#E2F1EB", foreground="#256D5A")
            self.tree_reconcile.tag_configure("reconcile_diff", background="#FCE4D6", foreground="#8A3B12")
        except Exception:
            pass
        self.tree_unmapped = self._build_tree_tab(tab_unmapped, _UNMAPPED_COLUMNS)
        self.tree_mapping = self._build_tree_tab(tab_mapping, _MAPPING_COLUMNS)

        self.tree_control_gl.bind("<<TreeviewSelect>>", lambda _event: self._on_control_gl_selection_changed())
        self.tree_control_gl.bind("<Double-1>", lambda _event: self._run_selected_control_gl_action())
        self.tree_control_gl.bind("<Return>", lambda _event: self._assign_selected_control_mapping())
        self.tree_control_gl.bind("<Delete>", lambda _event: self._clear_selected_control_mapping())
        self.tree_control_gl.bind("<B1-Motion>", self._start_control_gl_drag, add="+")
        self.tree_a07.bind("<<TreeviewSelect>>", lambda _event: self._on_control_selection_changed())
        self.tree_a07.bind("<Double-1>", lambda _event: self._run_selected_control_action())
        self.tree_a07.bind("<Motion>", self._track_unmapped_drop_target, add="+")
        self.tree_a07.bind("<ButtonRelease-1>", self._drop_unmapped_on_control, add="+")
        self.tree_history.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_history.bind("<Double-1>", lambda _event: self._apply_selected_history_mapping())
        self.tree_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_control_suggestions.bind("<Double-1>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<Return>", lambda _event: self._apply_selected_suggestion())
        self.tree_control_suggestions.bind("<<TreeviewSelect>>", lambda _event: self._on_suggestion_selected())
        self.tree_control_accounts.bind("<<TreeviewSelect>>", lambda _event: self._focus_selected_control_account_in_gl())
        self.tree_control_accounts.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_control_accounts.bind("<Delete>", lambda _event: self._remove_selected_control_accounts())
        self.tree_reconcile.bind("<<TreeviewSelect>>", lambda _event: self._update_history_details_from_selection())
        self.tree_unmapped.bind("<B1-Motion>", self._start_unmapped_drag, add="+")
        self.tree_unmapped.bind("<Double-1>", lambda _event: self._map_selected_unmapped())
        self.tree_mapping.bind("<Double-1>", lambda _event: self._open_manual_mapping_clicked())
        self.tree_mapping.bind("<Delete>", lambda _event: self._remove_selected_mapping())

        suggestion_details = ttk.Frame(tab_suggestions, padding=(0, 8, 0, 0))
        suggestion_details.pack(fill="x")
        suggestion_scope_row = ttk.Frame(suggestion_details)
        suggestion_scope_row.pack(fill="x", pady=(0, 8))
        ttk.Label(suggestion_scope_row, text="Vis forslag for:").pack(side="left")
        suggestion_scope = ttk.Combobox(
            suggestion_scope_row,
            state="readonly",
            width=18,
            values=[_SUGGESTION_SCOPE_LABELS[key] for key in _SUGGESTION_SCOPE_LABELS],
            textvariable=self.suggestion_scope_label_var,
        )
        suggestion_scope.pack(side="left", padx=(6, 0))
        suggestion_scope.bind("<<ComboboxSelected>>", lambda _event: self._on_suggestion_scope_changed())
        self.suggestion_scope_widget = suggestion_scope
        suggestion_scope.set(_SUGGESTION_SCOPE_LABELS["valgt_kode"])
        ttk.Button(
            suggestion_details,
            text="Bruk sikre forslag",
            command=self._apply_batch_suggestions_clicked,
        ).pack(anchor="w", pady=(0, 8))
        ttk.Label(suggestion_details, text="Forslagsforklaring").pack(anchor="w")
        ttk.Label(
            suggestion_details,
            textvariable=self.suggestion_details_var,
            style="Muted.TLabel",
            wraplength=1100,
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        self._set_control_details_visible(False)

        ttk.Label(
            self,
            textvariable=self.status_var,
            style="Muted.TLabel",
            anchor="w",
            justify="left",
            padding=(10, 0, 10, 8),
        ).pack(fill="x")

    def _build_tree_tab(self, parent: ttk.Frame, columns: Sequence[tuple[str, str, int, str]]) -> ttk.Treeview:
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)

        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings")
        for column_id, heading, width, anchor in columns:
            tree.heading(column_id, text=heading)
            tree.column(column_id, width=width, anchor=anchor)

        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)

        tree.pack(side="left", fill="both", expand=True)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        return tree

    def _session_context(self, session_module=session) -> tuple[str | None, str | None]:
        client = _clean_context_value(getattr(session_module, "client", None))
        year = _clean_context_value(getattr(session_module, "year", None))
        return client, year

    def _selected_tree_values(self, tree: ttk.Treeview) -> tuple[str, ...]:
        selection = tree.selection()
        if not selection:
            return ()
        values = tree.item(selection[0], "values")
        return tuple(str(value) for value in (values or ()))

    def _selected_suggestion_row_from_tree(self, tree: ttk.Treeview) -> pd.Series | None:
        selection = tree.selection()
        if not selection or self.workspace.suggestions is None or self.workspace.suggestions.empty:
            return None

        selected_id = str(selection[0]).strip()
        if not selected_id:
            return None

        try:
            idx = int(selected_id)
        except Exception:
            return None

        try:
            return self.workspace.suggestions.loc[idx]
        except Exception:
            try:
                return self.workspace.suggestions.iloc[idx]
            except Exception:
                return None

    def _tree_iid_from_event(self, tree: ttk.Treeview, event: tk.Event | None = None) -> str | None:
        if event is not None:
            identify_row = getattr(tree, "identify_row", None)
            if callable(identify_row):
                try:
                    iid = str(identify_row(getattr(event, "y", 0)) or "").strip()
                except Exception:
                    iid = ""
                if iid:
                    return iid

        selection = tree.selection()
        if not selection:
            return None
        iid = str(selection[0]).strip()
        return iid or None

    def _manual_mapping_defaults(self) -> tuple[str | None, str | None]:
        konto = None
        kode = None

        control_gl_values = self._selected_tree_values(self.tree_control_gl)
        if control_gl_values:
            konto = str(control_gl_values[0]).strip() or None
            if len(control_gl_values) >= 6:
                kode = str(control_gl_values[5]).strip() or None

        unmapped_values = self._selected_tree_values(self.tree_unmapped)
        if unmapped_values:
            if konto is None:
                konto = str(unmapped_values[0]).strip() or None

        mapping_values = self._selected_tree_values(self.tree_mapping)
        if mapping_values:
            if konto is None:
                konto = str(mapping_values[0]).strip() or None
            if kode is None and len(mapping_values) >= 3:
                kode = str(mapping_values[2]).strip() or None

        control_account_values = self._selected_tree_values(self.tree_control_accounts)
        if control_account_values and konto is None:
            konto = str(control_account_values[0]).strip() or None

        if kode is None:
            for tree in (self.tree_a07, self.tree_control_suggestions, self.tree_suggestions, self.tree_reconcile):
                values = self._selected_tree_values(tree)
                if values:
                    kode = str(values[0]).strip() or None
                    if kode:
                        break

        return konto, kode

    def _focus_mapping_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            self.tree_mapping.selection_set(konto_s)
            self.tree_mapping.focus(konto_s)
            self.tree_mapping.see(konto_s)
        except Exception:
            pass
        try:
            children = self.tree_control_gl.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            try:
                changed = False
                if bool(self.control_gl_unmapped_only_var.get()):
                    self.control_gl_unmapped_only_var.set(False)
                    changed = True
                if str(self.control_gl_filter_var.get() or "").strip():
                    self.control_gl_filter_var.set("")
                    changed = True
                if changed:
                    self._refresh_control_gl_tree()
            except Exception:
                pass
        try:
            self.tree_control_gl.selection_set(konto_s)
            self.tree_control_gl.focus(konto_s)
            self.tree_control_gl.see(konto_s)
        except Exception:
            return
        self._sync_control_account_selection(konto_s)

    def _focus_control_code(self, code: str | None) -> None:
        code_s = str(code or "").strip()
        if not code_s:
            return
        try:
            children = self.tree_a07.get_children()
        except Exception:
            children = ()
        if code_s not in children:
            try:
                self.a07_filter_var.set("alle")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["alle"])
            except Exception:
                pass
            self._refresh_a07_tree()
            try:
                children = self.tree_a07.get_children()
            except Exception:
                children = ()
        if code_s not in children:
            return
        try:
            self.tree_a07.selection_set(code_s)
            self.tree_a07.focus(code_s)
            self.tree_a07.see(code_s)
        except Exception:
            return
        self._on_control_selection_changed()

    def _selected_control_account_ids(self) -> list[str]:
        try:
            selection = self.tree_control_accounts.selection()
        except Exception:
            selection = ()

        accounts: list[str] = []
        seen: set[str] = set()
        for iid in selection:
            konto = str(iid).strip()
            if not konto or konto in seen:
                continue
            accounts.append(konto)
            seen.add(konto)
        return accounts

    def _sync_control_account_selection(self, konto: str | None) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            children = self.tree_control_accounts.get_children()
        except Exception:
            children = ()
        if konto_s not in children:
            return
        try:
            self.tree_control_accounts.selection_set(konto_s)
            self.tree_control_accounts.focus(konto_s)
            self.tree_control_accounts.see(konto_s)
        except Exception:
            return

    def _focus_selected_control_account_in_gl(self) -> None:
        accounts = self._selected_control_account_ids()
        if not accounts:
            return
        self._focus_mapping_account(accounts[0])

    def _remove_selected_control_accounts(self) -> None:
        accounts = self._selected_control_account_ids()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere mappede kontoer nederst forst.",
                focus_widget=self.tree_control_accounts,
            )
            return

        removed = remove_mapping_accounts(self.workspace.mapping, accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen kode aa fjerne.",
                focus_widget=self.tree_control_accounts,
            )
            return

        try:
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"Fjernet mapping fra {count} konto(er).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fjerne mapping fra konto:\n{exc}")

    def _focus_unmapped_account(self, konto: str) -> None:
        konto_s = str(konto or "").strip()
        if not konto_s:
            return
        try:
            self.tree_unmapped.selection_set(konto_s)
            self.tree_unmapped.focus(konto_s)
            self.tree_unmapped.see(konto_s)
        except Exception:
            return

    def _start_unmapped_drag(self, event: tk.Event | None = None) -> None:
        account = self._tree_iid_from_event(self.tree_unmapped, event)
        self._drag_unmapped_account = account
        self._drag_control_accounts = []
        self.control_drag_var.set(f"Dra konto {account} til kode i arbeidslisten." if account else "")
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel" if account else "Muted.TLabel")
        except Exception:
            pass

    def _start_control_gl_drag(self, event: tk.Event | None = None) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            account = self._tree_iid_from_event(self.tree_control_gl, event)
            if account:
                try:
                    self.tree_control_gl.selection_set(account)
                    self.tree_control_gl.focus(account)
                    self.tree_control_gl.see(account)
                except Exception:
                    pass
                accounts = [account]
        self._drag_control_accounts = [str(account).strip() for account in accounts if str(account).strip()]
        self._drag_unmapped_account = None
        if not self._drag_control_accounts:
            self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
            try:
                self.lbl_control_drag.configure(style="Muted.TLabel")
            except Exception:
                pass
            return
        if len(self._drag_control_accounts) == 1:
            hint = f"Dra konto {self._drag_control_accounts[0]} til kode til hoyre."
        else:
            hint = f"Dra {len(self._drag_control_accounts)} kontoer til kode til hoyre."
        self.control_drag_var.set(hint)
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel")
        except Exception:
            pass

    def _current_drag_accounts(self) -> list[str]:
        if self._drag_control_accounts:
            return [str(account).strip() for account in self._drag_control_accounts if str(account).strip()]
        account = str(self._drag_unmapped_account or "").strip()
        return [account] if account else []

    def _clear_control_drag_state(self) -> None:
        self._drag_unmapped_account = None
        self._drag_control_accounts = []
        self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
        try:
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass

    def _track_unmapped_drop_target(self, event: tk.Event | None = None) -> None:
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            return
        code = self._tree_iid_from_event(self.tree_a07, event)
        if not code:
            return
        try:
            self.tree_a07.selection_set(code)
            self.tree_a07.focus(code)
            self.tree_a07.see(code)
        except Exception:
            pass
        if len(accounts) == 1:
            hint = f"Slipp konto {accounts[0]} paa kode {code}."
        else:
            hint = f"Slipp {len(accounts)} kontoer paa kode {code}."
        self.control_drag_var.set(hint)
        try:
            self.lbl_control_drag.configure(style="Warning.TLabel")
        except Exception:
            pass

    def _apply_account_code_mapping(
        self,
        konto: str | None,
        kode: str | None,
        *,
        source_label: str = "Mapping satt",
    ) -> None:
        konto_s, kode_s = apply_manual_mapping_choice(self.workspace.mapping, konto, kode)
        autosaved = self._autosave_mapping()
        self._refresh_all()
        self._focus_control_code(kode_s)
        self._focus_mapping_account(konto_s)

        if autosaved:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s} og lagret i klientmappen.")
        else:
            self.status_var.set(f"{source_label}: {konto_s} -> {kode_s}.")
        self._select_primary_tab()

    def _assign_selected_control_mapping(self) -> None:
        accounts = self._selected_control_gl_accounts()
        code = self._selected_control_code()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return

        try:
            assigned = apply_manual_mapping_choices(self.workspace.mapping, accounts, code)
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(assigned[0])
            count = len(assigned)
            if autosaved:
                self.status_var.set(f"Tildelte {count} konto(er) til {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Tildelte {count} konto(er) til {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke tildele konto til kode:\n{exc}")

    def _run_selected_control_gl_action(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            return
        if self._selected_control_code():
            self._assign_selected_control_mapping()
            return
        try:
            self.tree_a07.focus_set()
        except Exception:
            pass
        self.status_var.set("Velg en A07-kode til hoyre for du tildeler kontoer fra GL-listen.")

    def _clear_selected_control_mapping(self) -> None:
        accounts = self._selected_control_gl_accounts()
        if not accounts:
            self._notify_inline(
                "Velg en eller flere GL-kontoer til venstre forst.",
                focus_widget=self.tree_control_gl,
            )
            return

        removed = remove_mapping_accounts(self.workspace.mapping, accounts)
        if not removed:
            self._notify_inline(
                "Valgte kontoer har ingen kode aa fjerne.",
                focus_widget=self.tree_control_gl,
            )
            return

        try:
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(removed[0])
            count = len(removed)
            if autosaved:
                self.status_var.set(f"Fjernet kode fra {count} konto(er) og lagret endringen.")
            else:
                self.status_var.set(f"Fjernet kode fra {count} konto(er).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fjerne kode fra konto:\n{exc}")

    def _drop_unmapped_on_control(self, event: tk.Event | None = None) -> None:
        try:
            accounts = self._current_drag_accounts()
        except Exception:
            account = str(getattr(self, "_drag_unmapped_account", "") or "").strip()
            accounts = [account] if account else []
        if not accounts:
            return

        try:
            code = self._tree_iid_from_event(self.tree_a07, event)
            if not code:
                return
            self.tree_a07.selection_set(code)
            self.tree_a07.focus(code)
            self.tree_a07.see(code)
            if len(accounts) == 1:
                self._apply_account_code_mapping(accounts[0], code, source_label="Drag-and-drop")
            else:
                assigned = apply_manual_mapping_choices(self.workspace.mapping, accounts, code)
                autosaved = self._autosave_mapping()
                self._refresh_all()
                self._focus_control_code(code)
                self._focus_mapping_account(assigned[0])
                if autosaved:
                    self.status_var.set(
                        f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code} og lagret i klientmappen."
                    )
                else:
                    self.status_var.set(f"Drag-and-drop: tildelte {len(assigned)} kontoer til {code}.")
                self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke fullfore drag-and-drop-mapping:\n{exc}")
        finally:
            self._clear_control_drag_state()

    def _update_selected_suggestion_details(self) -> None:
        row = self._selected_suggestion_row()
        if row is None:
            self.suggestion_details_var.set("Velg et forslag for aa se hvorfor det scorer hoeyt.")
            return

        explain = str(row.get("Explain") or "").strip()
        hit_tokens = str(row.get("HitTokens") or "").strip()
        history_accounts = str(row.get("HistoryAccounts") or "").strip()
        basis = str(row.get("Basis") or "").strip()

        parts = []
        if basis:
            parts.append(f"Basis: {basis}")
        if hit_tokens:
            parts.append(f"Navnetreff: {hit_tokens}")
        if history_accounts:
            parts.append(f"Historikk: {history_accounts}")
        if explain:
            parts.append(explain)

        self.suggestion_details_var.set(" | ".join(parts) if parts else "Ingen detaljforklaring tilgjengelig.")

    def _selected_code_from_tree(self, tree: ttk.Treeview) -> str | None:
        values = self._selected_tree_values(tree)
        if not values:
            return None
        code = str(values[0]).strip()
        return code or None

    def _selected_suggestion_row(self) -> pd.Series | None:
        try:
            current_tab = self.nb.nametowidget(self.nb.select())
        except Exception:
            current_tab = None

        focused = None
        try:
            focused = self.focus_get()
        except Exception:
            focused = None

        if focused is self.tree_control_suggestions:
            row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
            if row is not None:
                return row
        if focused is self.tree_suggestions:
            row = self._selected_suggestion_row_from_tree(self.tree_suggestions)
            if row is not None:
                return row
        if current_tab is self.tab_control:
            row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
            if row is not None:
                return row
        if current_tab is self.tab_suggestions:
            row = self._selected_suggestion_row_from_tree(self.tree_suggestions)
            if row is not None:
                return row

        row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
        if row is not None:
            return row
        return self._selected_suggestion_row_from_tree(self.tree_suggestions)

    def _selected_control_gl_account(self) -> str | None:
        values = self._selected_tree_values(self.tree_control_gl)
        if not values:
            return None
        konto = str(values[0]).strip()
        return konto or None

    def _selected_control_gl_accounts(self) -> list[str]:
        try:
            selection = self.tree_control_gl.selection()
        except Exception:
            selection = ()

        accounts: list[str] = []
        seen: set[str] = set()
        for iid in selection:
            konto = str(iid).strip()
            if not konto or konto in seen:
                continue
            accounts.append(konto)
            seen.add(konto)
        return accounts

    def _selected_control_suggestion_accounts(self) -> list[str]:
        row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
        if row is None:
            return []
        return _parse_konto_tokens(row.get("ForslagKontoer"))

    def _set_control_details_visible(self, visible: bool) -> None:
        self._control_details_visible = bool(visible)
        detail_panes = getattr(self, "control_detail_panes", None)
        toggle_button = getattr(self, "btn_control_toggle_details", None)
        if detail_panes is not None:
            try:
                if self._control_details_visible:
                    if not detail_panes.winfo_manager():
                        detail_panes.pack(fill="both", expand=True, pady=(6, 0))
                else:
                    if detail_panes.winfo_manager():
                        detail_panes.pack_forget()
            except Exception:
                pass
        if toggle_button is not None:
            try:
                toggle_button.configure(text="Skjul detaljer" if self._control_details_visible else "Vis detaljer")
            except Exception:
                pass

    def _toggle_control_details(self) -> None:
        self._set_control_details_visible(not bool(getattr(self, "_control_details_visible", True)))

    def _update_control_transfer_buttons(self) -> None:
        assign_button = getattr(self, "btn_control_assign", None)
        clear_button = getattr(self, "btn_control_clear", None)
        if assign_button is None and clear_button is None:
            return

        accounts = self._selected_control_gl_accounts()
        code = self._selected_control_code()
        has_mapped_account = any(str(self.workspace.mapping.get(account) or "").strip() for account in accounts)

        try:
            if assign_button is not None:
                if accounts and code:
                    assign_button.state(["!disabled"])
                else:
                    assign_button.state(["disabled"])
            if clear_button is not None:
                if has_mapped_account:
                    clear_button.state(["!disabled"])
                else:
                    clear_button.state(["disabled"])
        except Exception:
            return

    def _selected_a07_filter(self) -> str:
        try:
            label = str(self.a07_filter_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _CONTROL_VIEW_LABELS.items():
            if value == label:
                return key

        fallback = str(self.a07_filter_var.get() or "").strip().lower()
        return fallback or "neste"

    def _selected_suggestion_scope(self) -> str:
        try:
            label = str(self.suggestion_scope_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _SUGGESTION_SCOPE_LABELS.items():
            if value == label:
                return key

        fallback = str(self.suggestion_scope_var.get() or "").strip().lower()
        return fallback or "valgt_kode"

    def _notify_inline(self, message: str, *, focus_widget: object | None = None) -> None:
        self.status_var.set(str(message or "").strip())
        if focus_widget is None:
            return
        try:
            focus_widget.focus_set()
        except Exception:
            return

    def _control_gl_filter_state(self) -> tuple[str, bool]:
        try:
            search_text = str(self.control_gl_filter_var.get() or "")
        except Exception:
            search_text = ""
        try:
            only_unmapped = bool(self.control_gl_unmapped_only_var.get())
        except Exception:
            only_unmapped = False
        return search_text, only_unmapped

    def _refresh_a07_tree(self) -> None:
        selected_code = self._selected_code_from_tree(self.tree_a07)
        filtered = filter_control_queue_df(self.control_df, self._selected_a07_filter())
        filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
        if (
            filtered.empty
            and self._selected_a07_filter() == "neste"
            and self.control_df is not None
            and not self.control_df.empty
            and count_unsolved_a07_codes(self.a07_overview_df) == 0
        ):
            self.a07_filter_var.set("ferdig")
            self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["ferdig"])
            try:
                self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["ferdig"])
            except Exception:
                pass
            filtered = filter_control_queue_df(self.control_df, "ferdig")
            filtered = filter_control_search_df(filtered, self.control_code_filter_var.get())
        for item in self.tree_a07.get_children():
            self.tree_a07.delete(item)

        if filtered is not None and not filtered.empty:
            for idx, row in filtered.iterrows():
                values = [self._format_value(row.get(column_id), column_id) for column_id, *_rest in _CONTROL_COLUMNS]
                iid = str(row.get("Kode") or "").strip() or str(idx)
                self.tree_a07.insert(
                    "",
                    "end",
                    iid=iid,
                    values=values,
                    tags=(control_tree_tag(row.get("Arbeidsstatus")),),
                )

        children = self.tree_a07.get_children()
        if not children:
            return

        target = selected_code if selected_code and selected_code in children else children[0]
        try:
            self.tree_a07.selection_set(target)
            self.tree_a07.focus(target)
            self.tree_a07.see(target)
        except Exception:
            return

    def _refresh_control_gl_tree(self) -> None:
        selected_account = self._selected_control_gl_account()
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        search_text, only_unmapped = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
        )
        self._fill_tree(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
        )

        children = self.tree_control_gl.get_children()
        if not children:
            return

        target = selected_account if selected_account and selected_account in children else children[0]
        try:
            self.tree_control_gl.selection_set(target)
            self.tree_control_gl.focus(target)
            self.tree_control_gl.see(target)
        except Exception:
            return

    def _on_control_gl_filter_changed(self) -> None:
        self._refresh_control_gl_tree()
        self._update_control_transfer_buttons()

    def _on_control_code_filter_changed(self) -> None:
        self._refresh_a07_tree()
        self._on_control_selection_changed()

    def _refresh_suggestions_tree(self) -> None:
        current_selection = self.tree_suggestions.selection()
        selected_id = str(current_selection[0]).strip() if current_selection else ""
        selected_code = self._selected_code_from_tree(self.tree_a07)
        filtered = filter_suggestions_df(
            self.workspace.suggestions if self.workspace.suggestions is not None else _empty_suggestions_df(),
            scope_key=self._selected_suggestion_scope(),
            selected_code=selected_code,
            unresolved_code_values=unresolved_codes(self.a07_overview_df),
        )
        self._fill_tree(self.tree_suggestions, filtered, _SUGGESTION_COLUMNS, row_tag_fn=suggestion_tree_tag)

        children = self.tree_suggestions.get_children()
        if not children:
            self.suggestion_details_var.set("Ingen forslag i valgt visning.")
            return

        target = selected_id if selected_id and selected_id in children else children[0]
        try:
            self.tree_suggestions.selection_set(target)
            self.tree_suggestions.focus(target)
            self.tree_suggestions.see(target)
        except Exception:
            return

    def _refresh_control_support_trees(self) -> None:
        selected_code = self._selected_code_from_tree(self.tree_a07)
        selected_account = None
        try:
            current_accounts = self.tree_control_accounts.selection()
            if current_accounts:
                selected_account = str(current_accounts[0]).strip() or None
        except Exception:
            selected_account = None
        control_suggestions = filter_suggestions_df(
            self.workspace.suggestions if self.workspace.suggestions is not None else _empty_suggestions_df(),
            scope_key="valgt_kode",
            selected_code=selected_code,
            unresolved_code_values=unresolved_codes(self.a07_overview_df),
        )
        current_selection = self.tree_control_suggestions.selection()
        selected_id = str(current_selection[0]).strip() if current_selection else ""
        self._fill_tree(
            self.tree_control_suggestions,
            control_suggestions,
            _CONTROL_SUGGESTION_COLUMNS,
            row_tag_fn=suggestion_tree_tag,
        )
        children = self.tree_control_suggestions.get_children()
        if children:
            target = selected_id if selected_id and selected_id in children else children[0]
            try:
                self.tree_control_suggestions.selection_set(target)
                self.tree_control_suggestions.focus(target)
                self.tree_control_suggestions.see(target)
            except Exception:
                pass
        selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
        self.control_suggestion_summary_var.set(
            build_control_suggestion_summary(selected_code, control_suggestions, selected_row)
        )
        self.control_suggestion_effect_var.set(
            build_control_suggestion_effect_summary(
                selected_code,
                accounts_for_code(self.workspace.mapping, selected_code),
                selected_row,
            )
        )

        self.control_selected_accounts_df = build_control_selected_account_df(
            self.workspace.gl_df,
            self.workspace.mapping,
            selected_code,
        )
        self.control_accounts_summary_var.set(
            build_control_accounts_summary(self.control_selected_accounts_df, selected_code)
        )
        self._fill_tree(
            self.tree_control_accounts,
            self.control_selected_accounts_df,
            _CONTROL_SELECTED_ACCOUNT_COLUMNS,
            iid_column="Konto",
        )
        children = self.tree_control_accounts.get_children()
        target_account = (
            selected_account
            or self._selected_control_gl_account()
        )
        if target_account and target_account in children:
            try:
                self.tree_control_accounts.selection_set(target_account)
                self.tree_control_accounts.focus(target_account)
                self.tree_control_accounts.see(target_account)
            except Exception:
                pass

    def _update_history_details(self, code: str | None) -> None:
        self.history_details_var.set(
            build_mapping_history_details(
                code,
                mapping_current=self.workspace.mapping,
                mapping_previous=self.previous_mapping,
                previous_year=self.previous_mapping_year,
            )
        )

    def _update_history_details_from_selection(self) -> None:
        code = (
            self._selected_code_from_tree(self.tree_a07)
            or self._selected_code_from_tree(self.tree_history)
            or self._selected_code_from_tree(self.tree_suggestions)
            or self._selected_code_from_tree(self.tree_reconcile)
        )
        self._update_history_details(code)

    def _update_control_panel(self) -> None:
        code = self._selected_code_from_tree(self.tree_a07)
        if not code:
            self.control_intro_var.set("Velg kode i høyre liste.")
            self.control_summary_var.set("Velg en A07-kode for aa starte arbeidet.")
            self.control_meta_var.set("")
            self.control_match_var.set("")
            self.control_mapping_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            self.control_next_var.set("Velg kode for aa starte.")
            self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
            self.control_suggestion_effect_var.set("Velg kode i hoyre liste for aa se hva valgt forslag vil gjøre.")
            try:
                self.control_panel.configure(text="Valgt kode")
                self.btn_control_best.state(["disabled"])
                self.btn_control_history.state(["disabled"])
                self.lbl_control_drag.configure(style="Muted.TLabel")
            except Exception:
                pass
            self._update_control_transfer_buttons()
            return

        overview_row = None
        if self.a07_overview_df is not None and not self.a07_overview_df.empty:
            matches = self.a07_overview_df.loc[self.a07_overview_df["Kode"].astype(str).str.strip() == code]
            if not matches.empty:
                overview_row = matches.iloc[0]
        control_row = None
        if self.control_df is not None and not self.control_df.empty:
            control_matches = self.control_df.loc[self.control_df["Kode"].astype(str).str.strip() == code]
            if not control_matches.empty:
                control_row = control_matches.iloc[0]
        reconcile_row = None
        if self.reconcile_df is not None and not self.reconcile_df.empty and "Kode" in self.reconcile_df.columns:
            reconcile_matches = self.reconcile_df.loc[self.reconcile_df["Kode"].astype(str).str.strip() == code]
            if not reconcile_matches.empty:
                reconcile_row = reconcile_matches.iloc[0]

        status = str((overview_row.get("Status") if overview_row is not None else "") or "").strip() or "Ukjent"
        navn = str((overview_row.get("Navn") if overview_row is not None else "") or "").strip() or code
        belop = self._format_value(overview_row.get("Belop") if overview_row is not None else None, "Belop")
        current_accounts = accounts_for_code(self.workspace.mapping, code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
            gl_df=self.workspace.gl_df,
        )
        best_row = best_suggestion_row_for_code(self.workspace.suggestions, code)

        summary_parts = [code]
        if navn and navn.casefold() != code.casefold():
            summary_parts.append(navn)
        work_label = str((control_row.get("Status") if control_row is not None else "") or "").strip() or status
        self.control_intro_var.set(
            control_intro_text(
                work_label,
                has_history=bool(history_accounts),
                best_suggestion=best_row,
            )
        )
        next_action = control_next_action_label(
            status,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        self.control_summary_var.set(" | ".join(summary_parts))
        self.control_meta_var.set(
            f"{work_label} | Belop {belop or '-'} | Neste {compact_control_next_action(next_action)}"
        )
        if reconcile_row is not None:
            gl_belop = self._format_value(reconcile_row.get("GL_Belop"), "GL_Belop")
            diff_belop = self._format_value(reconcile_row.get("Diff"), "Diff")
            count_accounts = self._format_value(reconcile_row.get("AntallKontoer"), "AntallKontoer")
            self.control_match_var.set(
                f"GL {gl_belop or '-'} | Diff {diff_belop or '-'} | Kontoer {count_accounts or '0'}"
            )
        else:
            self.control_match_var.set("Ingen detaljkontroll ennå.")
        mapping_text = ", ".join(current_accounts) if current_accounts else "ingen mapping"
        history_text = ", ".join(history_accounts) if history_accounts else "ingen"
        self.control_mapping_var.set(f"Mapping: {mapping_text} | Historikk: {history_text}")
        self.control_history_var.set(f"Historikk: {history_text}")

        if best_row is None:
            recommended = str((control_row.get("Anbefalt") if control_row is not None else "") or "").strip()
            self.control_best_var.set(f"Forslag: {recommended}" if recommended else "Forslag: ingen forslag")
        else:
            diff = self._format_value(best_row.get("Diff"), "Diff")
            score = self._format_value(best_row.get("Score"), "Score")
            accounts_text = str(best_row.get("ForslagKontoer") or "").strip() or "-"
            ok_text = "innenfor toleranse" if bool(best_row.get("WithinTolerance", False)) else "utenfor toleranse"
            self.control_best_var.set(
                f"Forslag: {accounts_text} | diff {diff or '-'} | score {score or '-'} | {ok_text}"
            )

        self.control_next_var.set(f"Neste: {next_action}")

        try:
            self.control_panel.configure(text="Valgt kode")
            if best_row is not None and bool(best_row.get("WithinTolerance", False)):
                self.btn_control_best.state(["!disabled"])
            else:
                self.btn_control_best.state(["disabled"])
            if history_accounts:
                self.btn_control_history.state(["!disabled"])
            else:
                self.btn_control_history.state(["disabled"])
            if not self._current_drag_accounts():
                self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
                self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        self._update_control_transfer_buttons()

    def _on_control_selection_changed(self) -> None:
        code = self._selected_control_code()
        if code and not bool(getattr(self, "_control_details_visible", False)) and not self._control_details_auto_revealed:
            self._set_control_details_visible(True)
            self._control_details_auto_revealed = True
        self._update_history_details_from_selection()
        if self._selected_suggestion_scope() == "valgt_kode":
            self._refresh_suggestions_tree()
        self._refresh_control_support_trees()
        self._refresh_control_gl_tree()
        self._update_control_panel()
        self._update_control_transfer_buttons()

    def _selected_control_code(self) -> str | None:
        return self._selected_code_from_tree(self.tree_a07)

    def _on_control_gl_selection_changed(self) -> None:
        account = self._selected_control_gl_account()
        if not account or self.control_gl_df is None or self.control_gl_df.empty:
            self._update_control_transfer_buttons()
            return
        matches = self.control_gl_df.loc[self.control_gl_df["Konto"].astype(str).str.strip() == account]
        if matches.empty:
            self._update_control_transfer_buttons()
            return
        code = str(matches.iloc[0].get("Kode") or "").strip()
        if not code:
            self._update_control_transfer_buttons()
            return
        try:
            if code not in self.tree_a07.get_children():
                self.a07_filter_var.set("alle")
                self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["alle"])
                try:
                    self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["alle"])
                except Exception:
                    pass
                self._refresh_a07_tree()
            if code in self.tree_a07.get_children():
                self.tree_a07.selection_set(code)
                self.tree_a07.focus(code)
                self.tree_a07.see(code)
                self._on_control_selection_changed()
        except Exception:
            return
        finally:
            self._sync_control_account_selection(account)
            self._update_control_transfer_buttons()

    def _on_suggestion_scope_changed(self) -> None:
        self.suggestion_scope_var.set(self._selected_suggestion_scope())
        self._refresh_suggestions_tree()
        self._update_selected_suggestion_details()

    def _apply_best_suggestion_for_selected_code(self) -> None:
        code = self._selected_control_code()
        best_row = best_suggestion_row_for_code(self.workspace.suggestions, code)
        if code is None or best_row is None:
            self._notify_inline("Fant ikke et forslag for valgt kode.", focus_widget=self.tree_a07)
            return
        if not bool(best_row.get("WithinTolerance", False)):
            self._notify_inline(
                "Beste forslag er utenfor toleranse. Kontroller detaljene eller map manuelt.",
                focus_widget=self.tree_control_suggestions,
            )
            return

        try:
            apply_suggestion_to_mapping(self.workspace.mapping, best_row)
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Beste forslag brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Beste forslag brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke beste forslag:\n{exc}")

    def _apply_history_for_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en A07-kode til hoyre forst.", focus_widget=self.tree_a07)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
            gl_df=self.workspace.gl_df,
        )
        if not accounts:
            self._notify_inline("Fant ingen trygg historikk aa bruke for valgt kode.", focus_widget=self.tree_a07)
            return
        if not code or not accounts:
            messagebox.showinfo("A07", "Fant ingen trygg historikk å bruke for valgt kode.")
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set(f"Historikk brukt for {code} og lagret i klientmappen.")
            else:
                self.status_var.set(f"Historikk brukt for {code}.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke historikk for valgt kode:\n{exc}")

    def _run_selected_control_action(self) -> None:
        code = self._selected_control_code()
        if not code:
            return

        overview_row = None
        if self.a07_overview_df is not None and not self.a07_overview_df.empty:
            matches = self.a07_overview_df.loc[self.a07_overview_df["Kode"].astype(str).str.strip() == code]
            if not matches.empty:
                overview_row = matches.iloc[0]

        status = str((overview_row.get("Status") if overview_row is not None else "") or "").strip()
        if status in {"OK", "Ekskludert"}:
            return

        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
            gl_df=self.workspace.gl_df,
        )
        if history_accounts:
            self._apply_history_for_selected_code()
            return

        best_row = best_suggestion_row_for_code(self.workspace.suggestions, code)
        if best_row is not None and bool(best_row.get("WithinTolerance", False)):
            self._apply_best_suggestion_for_selected_code()
            return

        try:
            self.entry_control_gl_filter.focus_set()
        except Exception:
            pass
        self.status_var.set(
            f"Ingen trygg automatikk for {code}. Velg konto(er) til venstre og bruk Tildel, eller bruk Avansert mapping under Mer."
        )

    def _on_suggestion_selected(self) -> None:
        self._update_selected_suggestion_details()
        self._refresh_control_gl_tree()
        if getattr(self, "tree_control_suggestions", None) is not None:
            selected_code = self._selected_code_from_tree(self.tree_a07)
            selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
            suggestions_df = filter_suggestions_df(
                self.workspace.suggestions if self.workspace.suggestions is not None else _empty_suggestions_df(),
                scope_key="valgt_kode",
                selected_code=selected_code,
                unresolved_code_values=unresolved_codes(self.a07_overview_df),
            )
            self.control_suggestion_summary_var.set(
                build_control_suggestion_summary(selected_code, suggestions_df, selected_row)
            )
            self.control_suggestion_effect_var.set(
                build_control_suggestion_effect_summary(
                    selected_code,
                    accounts_for_code(self.workspace.mapping, selected_code),
                    selected_row,
                )
            )
        self._update_history_details_from_selection()

    def _on_a07_filter_changed(self) -> None:
        self.a07_filter_var.set(self._selected_a07_filter())
        self._refresh_a07_tree()
        self._on_control_selection_changed()

    def _select_primary_tab(self) -> None:
        return

    def _restore_context_state(self, client: str | None, year: str | None) -> None:
        self.workspace.a07_df = _empty_a07_df()
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.control_gl_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_GL_COLUMNS])
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.workspace.mapping = {}
        self.workspace.suggestions = _empty_suggestions_df()
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.a07_path = None
        self.mapping_path = None
        self.rulebook_path = resolve_rulebook_path(client, year)
        self.previous_mapping = {}
        self.previous_mapping_path = None
        self.previous_mapping_year = None
        self.history_details_var.set("Velg en kode for aa se historikk.")
        self.control_summary_var.set("Velg en A07-kode for aa starte arbeidet.")
        self.control_intro_var.set("Velg kode i høyre liste.")
        self.control_meta_var.set("")
        self.control_match_var.set("")
        self.control_mapping_var.set("")
        self.control_history_var.set("")
        self.control_best_var.set("")
        self.control_suggestion_summary_var.set("Velg kode i hoyre liste for aa se forslag.")
        self.control_suggestion_effect_var.set("Velg kode i hoyre liste for aa se hva valgt forslag vil gjøre.")
        self.control_next_var.set("Velg kode for aa starte.")
        self.control_drag_var.set(_CONTROL_DRAG_IDLE_HINT)
        self.control_bucket_var.set("Ferdig 0 | Vurdering 0 | Manuell 0")
        self.control_code_filter_var.set("")
        self._control_details_auto_revealed = False
        try:
            self.control_panel.configure(text="Valgt kode")
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        self.a07_filter_var.set("neste")
        self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["neste"])
        self.suggestion_scope_var.set("valgt_kode")
        self.suggestion_scope_label_var.set(_SUGGESTION_SCOPE_LABELS["valgt_kode"])
        try:
            self.a07_filter_widget.set(_CONTROL_VIEW_LABELS["neste"])
        except Exception:
            pass
        try:
            self.suggestion_scope_widget.set(_SUGGESTION_SCOPE_LABELS["valgt_kode"])
        except Exception:
            pass

        self.workspace.gl_df, self.tb_path = load_active_trial_balance_for_context(client, year)

        source_path = default_a07_source_path(client, year)
        if source_path.exists():
            try:
                self.workspace.a07_df = parse_a07_json(source_path)
                self.a07_path = source_path
            except Exception:
                self.workspace.a07_df = _empty_a07_df()
                self.a07_path = None

        mapping_path = suggest_default_mapping_path(
            self.a07_path,
            client=client,
            year=year,
        )
        if mapping_path.exists():
            try:
                self.workspace.mapping = load_mapping(mapping_path)
                self.mapping_path = mapping_path
            except Exception:
                self.workspace.mapping = {}
                self.mapping_path = None

        (
            self.previous_mapping,
            self.previous_mapping_path,
            self.previous_mapping_year,
        ) = load_previous_year_mapping_for_context(client, year)

        self._refresh_all()
        self._context_snapshot = get_context_snapshot(client, year)

        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        if client_s and year_s and self.tb_path is None:
            self.status_var.set(
                "Ingen aktiv saldobalanse for valgt klient/aar. Bruk Versjoner i Dataset-fanen."
            )
        elif client_s and year_s:
            self.status_var.set("A07-kontekst er oppdatert fra klient/aar i Utvalg.")
        else:
            self.status_var.set(
                "Velg klient og aar i Dataset-fanen for aa bruke aktiv saldobalanse og klientlagret mapping."
            )

    def _sync_active_tb_clicked(self) -> None:
        ok = self._sync_active_trial_balance(refresh=True)
        if ok and self.tb_path is not None:
            self.status_var.set(f"Bruker aktiv saldobalanse fra {self.tb_path.name}.")
            return
        self._notify_inline(
            "Fant ingen aktiv saldobalanse for valgt klient/aar. Velg eller opprett den via Dataset -> Versjoner.",
            focus_widget=self,
        )

    def _sync_active_trial_balance(self, *, refresh: bool) -> bool:
        client, year = self._session_context(session)
        self.workspace.gl_df, self.tb_path = load_active_trial_balance_for_context(client, year)
        if refresh:
            self._refresh_all()
        return not self.workspace.gl_df.empty

    def _autosave_mapping(self) -> bool:
        client, year = self._session_context(session)
        save_path = resolve_autosave_mapping_path(
            self.mapping_path,
            a07_path=self.a07_path,
            client=client,
            year=year,
        )
        if save_path is None:
            return False

        saved = save_mapping(save_path, self.workspace.mapping)
        self.mapping_path = Path(saved)
        self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
        return True

    def _load_a07_clicked(self) -> None:
        client, year = self._session_context(session)
        initialdir = str(get_a07_workspace_dir(client, year))
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 JSON",
            initialdir=initialdir,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_a07_source_to_workspace(path, client=client, year=year)
            self.workspace.a07_df = parse_a07_json(stored_path)
            self.a07_path = Path(stored_path)
            self.a07_path_var.set(f"A07: {self.a07_path}")
            self._refresh_all()

            if stored_path != Path(path):
                self.status_var.set(
                    f"Lastet A07 fra {Path(path).name} og lagret kopi i klientmappen."
                )
            else:
                self.status_var.set(f"Lastet A07 fra {self.a07_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese A07-filen:\n{exc}")

    def _load_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        default_path = suggest_default_mapping_path(self.a07_path, client=client, year=year)

        if default_path.exists():
            path = default_path
        else:
            path_str = filedialog.askopenfilename(
                parent=self,
                title="Velg mapping JSON",
                initialdir=str(default_path.parent),
                initialfile=default_path.name,
                filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
            )
            if not path_str:
                return
            path = Path(path_str)

        try:
            self.workspace.mapping = load_mapping(path)
            self.mapping_path = Path(path)
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self._refresh_all()
            self.status_var.set(f"Lastet mapping fra {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese mapping-filen:\n{exc}")

    def _save_mapping_clicked(self) -> None:
        client, year = self._session_context(session)
        default_path = suggest_default_mapping_path(self.a07_path, client=client, year=year)

        out_path: Path
        if _clean_context_value(client) and _clean_context_value(year):
            out_path = default_path
        else:
            out_path_str = filedialog.asksaveasfilename(
                parent=self,
                title="Lagre mapping",
                defaultextension=".json",
                initialdir=str(default_path.parent),
                initialfile=default_path.name,
                filetypes=[("JSON", "*.json")],
            )
            if not out_path_str:
                return
            out_path = Path(out_path_str)

        try:
            saved = save_mapping(out_path, self.workspace.mapping)
            self.mapping_path = Path(saved)
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")
            self.status_var.set(f"Lagret mapping til {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mapping:\n{exc}")

    def _export_clicked(self) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du eksporterer.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og sÃ¸rg for at valgt klient/aar har en aktiv saldobalanse i Utvalg for du eksporterer.",
            )
            return

        client, year = self._session_context(session)
        default_path = default_a07_export_path(client, year)
        out_path_str = filedialog.asksaveasfilename(
            parent=self,
            title="Eksporter A07-kontroll",
            defaultextension=".xlsx",
            initialdir=str(default_path.parent),
            initialfile=default_path.name,
            filetypes=[("Excel", "*.xlsx")],
        )
        if not out_path_str:
            return

        try:
            exported = export_a07_workbook(
                out_path_str,
                overview_df=self.a07_overview_df,
                reconcile_df=self.reconcile_df,
                mapping_df=self.mapping_df,
                suggestions_df=self.workspace.suggestions,
                unmapped_df=self.unmapped_df,
            )
            self.status_var.set(f"Eksporterte A07-kontroll til {Path(exported).name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke eksportere A07-kontroll:\n{exc}")

    def _open_source_overview(self) -> None:
        existing = self._source_overview_window
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("A07-kilder")
        win.geometry("760x320")
        self._source_overview_window = win

        body = ttk.Frame(win, padding=10)
        body.pack(fill="both", expand=True)

        ttk.Label(
            body,
            text="Kildeinfo for valgt klient/aar. Dette er bare referanseinfo, ikke en egen arbeidsflate.",
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).pack(anchor="w")

        grid = ttk.Frame(body)
        grid.pack(fill="both", expand=True, pady=(12, 0))
        grid.columnconfigure(1, weight=1)

        for row_idx, (label_text, value_text) in enumerate(
            build_source_overview_rows(
                a07_text=self.a07_path_var.get(),
                tb_text=self.tb_path_var.get(),
                mapping_text=self.mapping_path_var.get(),
                rulebook_text=self.rulebook_path_var.get(),
                history_text=self.history_path_var.get(),
            )
        ):
            ttk.Label(grid, text=f"{label_text}:", style="Section.TLabel").grid(
                row=row_idx,
                column=0,
                sticky="nw",
                padx=(0, 10),
                pady=(0, 8),
            )
            ttk.Label(
                grid,
                text=value_text,
                style="Muted.TLabel",
                wraplength=540,
                justify="left",
            ).grid(row=row_idx, column=1, sticky="nw", pady=(0, 8))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

        def _on_close() -> None:
            try:
                win.destroy()
            finally:
                self._source_overview_window = None

        win.protocol("WM_DELETE_WINDOW", _on_close)

    def _open_mapping_overview(self) -> None:
        existing = getattr(self, "_mapping_window", None)
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.focus_force()
                    return
            except Exception:
                pass

        win = tk.Toplevel(self)
        win.title("A07-mappinger")
        win.geometry("760x520")
        self._mapping_window = win

        header = ttk.Frame(win, padding=10)
        header.pack(fill="x")
        ttk.Label(
            header,
            text="Lagrede mappinger for valgt klient/aar. Bruk dette vinduet ved behov, ikke som hovedarbeidsflate.",
            style="Muted.TLabel",
            wraplength=700,
            justify="left",
        ).pack(anchor="w")

        summary_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=summary_var, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))

        body = ttk.Frame(win, padding=(10, 0, 10, 10))
        body.pack(fill="both", expand=True)
        tree = self._build_tree_tab(body, _MAPPING_COLUMNS)

        def _refresh_window_tree() -> None:
            self._fill_tree(tree, self.mapping_df, _MAPPING_COLUMNS, iid_column="Konto")
            summary_var.set(f"Antall mappinger: {len(self.mapping_df)}")

        def _selected_account() -> str | None:
            selection = tree.selection()
            if not selection:
                return None
            return str(selection[0]).strip() or None

        def _sync_hidden_selection() -> bool:
            account = _selected_account()
            if not account:
                messagebox.showinfo("A07", "Velg en mappingrad forst.", parent=win)
                return False
            try:
                self.tree_mapping.selection_set(account)
                self.tree_mapping.focus(account)
                self.tree_mapping.see(account)
            except Exception:
                pass
            return True

        actions = ttk.Frame(win, padding=(10, 0, 10, 10))
        actions.pack(fill="x")
        ttk.Button(
            actions,
            text="Rediger valgt",
            command=lambda: (_sync_hidden_selection() and self._open_manual_mapping_clicked(), _refresh_window_tree()),
        ).pack(side="left")
        ttk.Button(
            actions,
            text="Fjern valgt",
            command=lambda: (_sync_hidden_selection() and self._remove_selected_mapping(), _refresh_window_tree()),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(actions, text="Lukk", command=win.destroy).pack(side="right")

        def _on_close() -> None:
            try:
                win.destroy()
            finally:
                self._mapping_window = None

        win.protocol("WM_DELETE_WINDOW", _on_close)
        _refresh_window_tree()

    def _open_matcher_admin(self) -> None:
        existing = self._matcher_admin_window
        if existing is not None:
            try:
                if existing.winfo_exists():
                    existing.focus_force()
                    return
            except Exception:
                pass

        rulebook_path = self.rulebook_path or default_global_rulebook_path()
        document = load_rulebook_document(rulebook_path)
        settings = load_matcher_settings()

        win = tk.Toplevel(self)
        win.title("Matcher-admin")
        win.geometry("1100x760")
        self._matcher_admin_window = win

        notebook = ttk.Notebook(win)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        tab_rules = ttk.Frame(notebook)
        tab_settings = ttk.Frame(notebook)
        notebook.add(tab_rules, text="Rulebook")
        notebook.add(tab_settings, text="Innstillinger")

        status_var = tk.StringVar(
            value="Rediger regler og innstillinger her. Lagre deretter og oppdater A07-forslag."
        )

        header = ttk.Frame(tab_rules, padding=(0, 0, 0, 8))
        header.pack(fill="x")
        ttk.Label(
            header,
            text=f"Global rulebook: {rulebook_path}",
            style="Muted.TLabel",
            wraplength=1000,
            justify="left",
        ).pack(anchor="w")

        split = ttk.Panedwindow(tab_rules, orient="horizontal")
        split.pack(fill="both", expand=True)

        left = ttk.Frame(split, padding=(0, 0, 8, 0))
        right = ttk.Frame(split)
        split.add(left, weight=1)
        split.add(right, weight=3)

        code_tree = ttk.Treeview(left, columns=("Kode", "Status", "Label"), show="headings", height=20)
        for column_id, heading, width in (
            ("Kode", "Kode", 180),
            ("Status", "Status", 90),
            ("Label", "Label", 180),
        ):
            code_tree.heading(column_id, text=heading)
            code_tree.column(column_id, width=width, anchor="w")
        code_tree.pack(fill="both", expand=True)

        left_buttons = ttk.Frame(left, padding=(0, 8, 0, 0))
        left_buttons.pack(fill="x")

        form = ttk.Frame(right)
        form.pack(fill="both", expand=True)
        for idx in range(2):
            form.columnconfigure(idx, weight=1 if idx == 1 else 0)

        code_var = tk.StringVar(value="")
        label_var = tk.StringVar(value="")
        category_var = tk.StringVar(value="")
        boost_var = tk.StringVar(value="")
        basis_var = tk.StringVar(value="")
        expected_sign_var = tk.StringVar(value="")

        ttk.Label(form, text="Kode").grid(row=0, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(form, textvariable=code_var, width=30).grid(row=0, column=1, sticky="ew", pady=(0, 4))
        ttk.Label(form, text="Label").grid(row=1, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(form, textvariable=label_var).grid(row=1, column=1, sticky="ew", pady=(0, 4))
        ttk.Label(form, text="Kategori").grid(row=2, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(form, textvariable=category_var).grid(row=2, column=1, sticky="ew", pady=(0, 4))
        ttk.Label(form, text="Boost-kontoer").grid(row=3, column=0, sticky="w", pady=(0, 4))
        ttk.Entry(form, textvariable=boost_var).grid(row=3, column=1, sticky="ew", pady=(0, 4))
        ttk.Label(form, text="Basis").grid(row=4, column=0, sticky="w", pady=(0, 4))
        ttk.Combobox(
            form,
            textvariable=basis_var,
            state="readonly",
            values=["", "UB", "IB", "Endring", "Debet", "Kredit"],
            width=18,
        ).grid(row=4, column=1, sticky="w", pady=(0, 4))
        ttk.Label(form, text="Forventet fortegn").grid(row=5, column=0, sticky="w", pady=(0, 4))
        ttk.Combobox(
            form,
            textvariable=expected_sign_var,
            state="readonly",
            values=["", "-1", "0", "1"],
            width=10,
        ).grid(row=5, column=1, sticky="w", pady=(0, 4))

        ttk.Label(
            form,
            text="Tillatte konto-intervaller\nEtt intervall per linje, f.eks. 5000-5999 eller 5210",
        ).grid(row=6, column=0, sticky="nw", pady=(8, 4))
        allowed_text = tk.Text(form, height=5, width=60)
        allowed_text.grid(row=6, column=1, sticky="ew", pady=(8, 4))

        ttk.Label(
            form,
            text="Nokkelord\nKomma eller én per linje",
        ).grid(row=7, column=0, sticky="nw", pady=(0, 4))
        keywords_text = tk.Text(form, height=5, width=60)
        keywords_text.grid(row=7, column=1, sticky="ew", pady=(0, 4))

        ttk.Label(
            form,
            text="Special add\nFormat: konto | basis | weight",
        ).grid(row=8, column=0, sticky="nw", pady=(0, 4))
        special_text = tk.Text(form, height=5, width=60)
        special_text.grid(row=8, column=1, sticky="ew", pady=(0, 4))

        ttk.Label(
            form,
            text="Aliaser\nFormat: noekkel = alias1, alias2",
        ).grid(row=9, column=0, sticky="nw", pady=(8, 4))
        aliases_text = tk.Text(form, height=8, width=60)
        aliases_text.grid(row=9, column=1, sticky="nsew", pady=(8, 4))
        form.rowconfigure(9, weight=1)

        settings_form = ttk.Frame(tab_settings, padding=10)
        settings_form.pack(fill="both", expand=True)
        for idx in range(2):
            settings_form.columnconfigure(idx, weight=1 if idx == 1 else 0)

        settings_vars = {
            name: tk.StringVar(value=str(settings[name]))
            for name in _MATCHER_SETTINGS_DEFAULTS
        }
        settings_rows = (
            ("tolerance_rel", "Relativ toleranse"),
            ("tolerance_abs", "Absolutt toleranse"),
            ("max_combo", "Maks konto-kombinasjon"),
            ("candidates_per_code", "Kandidater per kode"),
            ("top_suggestions_per_code", "Viste forslag per kode"),
            ("historical_account_boost", "Historikkboost konto"),
            ("historical_combo_boost", "Historikkboost kombinasjon"),
        )
        for row_idx, (name, label) in enumerate(settings_rows):
            ttk.Label(settings_form, text=label).grid(row=row_idx, column=0, sticky="w", pady=4)
            ttk.Entry(settings_form, textvariable=settings_vars[name], width=18).grid(
                row=row_idx, column=1, sticky="w", pady=4
            )

        ttk.Label(
            settings_form,
            text="Disse innstillingene styrer solverens toleranser, kombinasjonsdybde og historikkprior.",
            style="Muted.TLabel",
            wraplength=760,
            justify="left",
        ).grid(row=len(settings_rows), column=0, columnspan=2, sticky="w", pady=(10, 0))

        footer = ttk.Frame(win, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        ttk.Label(footer, textvariable=status_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        action_row = ttk.Frame(footer)
        action_row.pack(fill="x")

        state: dict[str, object] = {
            "document": document,
            "rulebook_path": rulebook_path,
            "status_var": status_var,
        }
        self._matcher_admin_state = state

        def _rules() -> dict[str, dict[str, object]]:
            raw_rules = document.setdefault("rules", {})
            if not isinstance(raw_rules, dict):
                document["rules"] = {}
                raw_rules = document["rules"]
            return raw_rules  # type: ignore[return-value]

        def _available_codes() -> list[str]:
            codes = {
                str(code).strip()
                for code in _rules().keys()
                if str(code).strip()
            }
            if self.workspace.a07_df is not None and not self.workspace.a07_df.empty and "Kode" in self.workspace.a07_df.columns:
                codes.update(
                    str(code).strip()
                    for code in self.workspace.a07_df["Kode"].astype(str).tolist()
                    if str(code).strip()
                )
            return sorted(codes, key=lambda value: (value.lower(), value))

        def _read_text(widget: tk.Text) -> str:
            return widget.get("1.0", "end").strip()

        def _write_text(widget: tk.Text, value: str) -> None:
            widget.delete("1.0", "end")
            if value:
                widget.insert("1.0", value)

        def _selected_code() -> str | None:
            selection = code_tree.selection()
            if not selection:
                return None
            return str(selection[0]).strip() or None

        def _load_rule_to_form(code: str | None) -> None:
            code_s = str(code or "").strip()
            raw = _rules().get(code_s, {}) if code_s else {}
            values = build_rule_form_values(code_s, raw)
            code_var.set(values["code"])
            label_var.set(values["label"])
            category_var.set(values["category"])
            boost_var.set(values["boost_accounts"])
            basis_var.set(values["basis"])
            expected_sign_var.set(values["expected_sign"])
            _write_text(allowed_text, values["allowed_ranges"])
            _write_text(keywords_text, values["keywords"])
            _write_text(special_text, values["special_add"])
            status_var.set(f"Redigerer regel for {code_s or 'ny kode'}.")

        def _clear_form(prefill_code: str | None = None) -> None:
            _load_rule_to_form(prefill_code)

        def _refresh_code_tree(selected_code: str | None = None) -> None:
            current = selected_code or _selected_code()
            for item in code_tree.get_children():
                code_tree.delete(item)

            for code in _available_codes():
                raw = _rules().get(code)
                has_rule = isinstance(raw, dict) and bool(raw)
                label = str((raw or {}).get("label") or "").strip() if isinstance(raw, dict) else ""
                code_tree.insert(
                    "",
                    "end",
                    iid=code,
                    values=(code, "Regel" if has_rule else "Ingen regel", label),
                )

            children = code_tree.get_children()
            if not children:
                _clear_form(self._selected_control_code())
                return

            target = current if current and current in children else children[0]
            code_tree.selection_set(target)
            code_tree.focus(target)
            code_tree.see(target)
            _load_rule_to_form(target)

        def _save_rule() -> str | None:
            existing_code = _selected_code()
            existing_rule = _rules().get(existing_code or "", {})
            try:
                code, payload = build_rule_payload(
                    {
                        "code": code_var.get(),
                        "label": label_var.get(),
                        "category": category_var.get(),
                        "allowed_ranges": _read_text(allowed_text),
                        "keywords": _read_text(keywords_text),
                        "boost_accounts": boost_var.get(),
                        "basis": basis_var.get(),
                        "expected_sign": expected_sign_var.get(),
                        "special_add": _read_text(special_text),
                    },
                    existing_rule=existing_rule,
                )
            except Exception as exc:
                messagebox.showerror("Matcher-admin", str(exc), parent=win)
                return None

            if existing_code and existing_code != code:
                _rules().pop(existing_code, None)
            _rules()[code] = payload
            _refresh_code_tree(code)
            status_var.set(f"Regel lagret i admin-vinduet for {code}.")
            return code

        def _delete_rule() -> None:
            code = _selected_code() or str(code_var.get() or "").strip()
            if not code or code not in _rules():
                messagebox.showinfo("Matcher-admin", "Velg en regel som finnes først.", parent=win)
                return
            if not messagebox.askyesno(
                "Matcher-admin",
                f"Vil du slette regelen for {code} fra global rulebook?",
                parent=win,
            ):
                return
            _rules().pop(code, None)
            _refresh_code_tree()
            status_var.set(f"Regel slettet for {code}.")

        def _save_admin(refresh_after: bool) -> None:
            current_code = str(code_var.get() or "").strip()
            form_has_content = any(
                [
                    str(label_var.get() or "").strip(),
                    str(category_var.get() or "").strip(),
                    str(boost_var.get() or "").strip(),
                    str(basis_var.get() or "").strip(),
                    str(expected_sign_var.get() or "").strip(),
                    _read_text(allowed_text),
                    _read_text(keywords_text),
                    _read_text(special_text),
                ]
            )
            if form_has_content or current_code in _rules():
                if _save_rule() is None:
                    return

            document["aliases"] = _parse_aliases_editor(_read_text(aliases_text))
            document["rules"] = _rules()
            try:
                saved_rulebook = save_rulebook_document(rulebook_path, document)
                saved_settings = save_matcher_settings({name: var.get() for name, var in settings_vars.items()})
                self.rulebook_path = saved_rulebook
                self.matcher_settings = load_matcher_settings(saved_settings)
                self.rulebook_path_var.set(f"Rulebook: {saved_rulebook}")
                if refresh_after:
                    self._refresh_all()
                    self.status_var.set("Matcher-admin lagret og A07-forslag oppdatert.")
                else:
                    self.status_var.set("Matcher-admin lagret.")
                status_var.set(
                    f"Lagret global rulebook og matcher-innstillinger til {saved_rulebook.parent}."
                )
            except Exception as exc:
                messagebox.showerror("Matcher-admin", f"Kunne ikke lagre matcher-admin:\n{exc}", parent=win)

        ttk.Button(
            left_buttons,
            text="Ny regel",
            command=lambda: _clear_form(self._selected_control_code()),
        ).pack(side="left")
        ttk.Button(left_buttons, text="Slett regel", command=_delete_rule).pack(side="left", padx=(6, 0))

        code_tree.bind("<<TreeviewSelect>>", lambda _event: _load_rule_to_form(_selected_code()))

        _write_text(aliases_text, _format_aliases_editor(document.get("aliases", {})))

        ttk.Button(action_row, text="Lagre regel", command=_save_rule).pack(side="left")
        ttk.Button(action_row, text="Lagre admin", command=lambda: _save_admin(False)).pack(side="left", padx=(6, 0))
        ttk.Button(
            action_row,
            text="Lagre og oppdater A07",
            command=lambda: _save_admin(True),
        ).pack(side="left", padx=(6, 0))
        ttk.Button(action_row, text="Lukk", command=win.destroy).pack(side="right")

        def _on_close() -> None:
            try:
                win.destroy()
            finally:
                self._matcher_admin_window = None
                self._matcher_admin_state = None

        win.protocol("WM_DELETE_WINDOW", _on_close)
        _refresh_code_tree(self._selected_control_code())

    def _load_rulebook_clicked(self) -> None:
        client, year = self._session_context(session)
        current_path = resolve_rulebook_path(client, year) or default_global_rulebook_path()
        path = filedialog.askopenfilename(
            parent=self,
            title="Velg A07 rulebook",
            initialdir=str(current_path.parent),
            initialfile=current_path.name,
            filetypes=[("JSON", "*.json"), ("Alle filer", "*.*")],
        )
        if not path:
            return

        try:
            stored_path = copy_rulebook_to_storage(path)
            self.rulebook_path = stored_path
            self.rulebook_path_var.set(f"Rulebook: {stored_path}")
            self._refresh_all()
            self.status_var.set(f"Rulebook lastet og lagret til {stored_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lese rulebook:\n{exc}")

    def _refresh_clicked(self) -> None:
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du oppdaterer.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og sørg for at valgt klient/aar har en aktiv saldobalanse i Utvalg.",
            )
            return

        try:
            selected_code = self._selected_control_code()
            self._refresh_all()
            self._focus_control_code(selected_code)
            self.status_var.set("A07-kontroll og forslag er oppdatert.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-visningen:\n{exc}")

    def _apply_safe_history_mappings(self) -> tuple[int, int]:
        applied_codes = 0
        applied_accounts = 0
        codes = select_safe_history_codes(self.history_compare_df)
        for code in codes:
            accounts = safe_previous_accounts_for_code(
                code,
                mapping_current=self.workspace.mapping,
                mapping_previous=self.previous_mapping,
                gl_df=self.workspace.gl_df,
            )
            if not accounts:
                continue

            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            after_accounts = {
                account
                for account, mapped_code in self.workspace.mapping.items()
                if str(mapped_code).strip() and before.get(str(account).strip()) != str(mapped_code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)

        return applied_codes, applied_accounts

    def _apply_safe_suggestions(self) -> tuple[int, int]:
        applied_codes = 0
        applied_accounts = 0
        row_indexes = select_batch_suggestion_rows(
            self.workspace.suggestions,
            self.workspace.mapping,
            min_score=0.85,
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            after_accounts = {
                account
                for account, code in self.workspace.mapping.items()
                if str(code).strip() and before.get(str(account).strip()) != str(code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)
        return applied_codes, applied_accounts

    def _apply_magic_wand_suggestions(
        self,
        unresolved_code_values: Sequence[object] | None = None,
    ) -> tuple[int, int, int]:
        unresolved_codes_list = [
            str(code).strip()
            for code in (unresolved_code_values or ())
            if str(code).strip()
        ]
        applied_codes = 0
        applied_accounts = 0
        applied_code_values: set[str] = set()
        row_indexes = select_magic_wand_suggestion_rows(
            self.workspace.suggestions,
            self.workspace.mapping,
            unresolved_codes=unresolved_codes_list,
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            code = str(row.get("Kode") or "").strip()
            before = {str(k): str(v) for k, v in self.workspace.mapping.items()}
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            after_accounts = {
                account
                for account, mapped_code in self.workspace.mapping.items()
                if str(mapped_code).strip() and before.get(str(account).strip()) != str(mapped_code).strip()
            }
            if not after_accounts:
                continue
            applied_codes += 1
            applied_accounts += len(after_accounts)
            if code:
                applied_code_values.add(code)

        skipped_codes = max(0, len(set(unresolved_codes_list)) - len(applied_code_values))
        return applied_codes, applied_accounts, skipped_codes

    def _magic_match_clicked(self) -> None:
        if self.workspace.gl_df.empty:
            self._sync_active_trial_balance(refresh=False)

        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du kjorer Tryllestav.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og sørg for at valgt klient/år har en aktiv saldobalanse i Utvalg.",
            )
            return

        try:
            selected_code = self._selected_control_code()
            self._refresh_all()
            unresolved_before = unresolved_codes(self.a07_overview_df)
            hist_codes, hist_accounts = self._apply_safe_history_mappings()
            if hist_codes:
                self._refresh_all()
            unresolved_after_history = unresolved_codes(self.a07_overview_df)
            suggestion_codes, suggestion_accounts, skipped_codes = self._apply_magic_wand_suggestions(
                unresolved_after_history
            )

            total_codes = hist_codes + suggestion_codes
            total_accounts = hist_accounts + suggestion_accounts
            if total_codes == 0:
                skipped_total = len(unresolved_before)
                self._notify_inline(
                    f"Tryllestav fant ingen trygge forslag. Skippet {skipped_total} uloste koder.",
                    focus_widget=self.tree_a07,
                )
                return
                self.status_var.set(
                    f"Tryllestav fant ingen trygge forslag. Skippet {skipped_total} uloste koder."
                )
                messagebox.showinfo(
                    "A07",
                    f"Tryllestav fant ingen trygge forslag. Skippet {skipped_total} uloste koder.",
                )
                return
                messagebox.showinfo(
                    "A07",
                    "Tryllestav fant ingen trygge historikk- eller solverforslag å bruke automatisk.",
                )
                return

            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_control_code(selected_code)
            skipped_total = max(skipped_codes, max(0, len(unresolved_before) - total_codes))
            if autosaved:
                self.status_var.set(
                    f"Tryllestav brukte {total_codes} mappinger ({total_accounts} kontoer), skippet {skipped_total} koder uten trygg auto-match og lagret endringen."
                )
            else:
                self.status_var.set(
                    f"Tryllestav brukte {total_codes} mappinger ({total_accounts} kontoer) og skippet {skipped_total} koder uten trygg auto-match."
                )
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Tryllestav kunne ikke fullføre:\n{exc}")

    def _open_manual_mapping_clicked(self) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for aa lage mapping.",
                focus_widget=self,
            )
            return
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            messagebox.showinfo(
                "A07",
                "Last A07 JSON og bruk aktiv saldobalanse for valgt klient/aar for aa lage mapping.",
            )
            return

        account_options = build_gl_picker_options(self.workspace.gl_df, basis_col="Endring")
        code_options = build_a07_picker_options(self.workspace.a07_df)
        if not account_options or not code_options:
            self._notify_inline("Fant ikke nok data til aa bygge avansert mapping.", focus_widget=self)
            return

        initial_account, initial_code = self._manual_mapping_defaults()
        choice = open_manual_mapping_dialog(
            self,
            account_options=account_options,
            code_options=code_options,
            initial_account=initial_account,
            initial_code=initial_code,
            title="Ny eller rediger A07-mapping",
        )
        if choice is None:
            return

        try:
            self._apply_account_code_mapping(choice[0], choice[1], source_label="Mapping satt")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mappingen:\n{exc}")

    def _map_selected_unmapped(self) -> None:
        selection = self.tree_unmapped.selection()
        if not selection:
            self._notify_inline("Velg en umappet konto forst.", focus_widget=self.tree_unmapped)
            return

        self._open_manual_mapping_clicked()

    def _apply_selected_suggestion(self) -> None:
        row = self._selected_suggestion_row()
        if row is None:
            if self.workspace.suggestions is None or self.workspace.suggestions.empty:
                self._notify_inline("Det finnes ingen forslag aa bruke.", focus_widget=self.tree_a07)
            else:
                self._notify_inline("Velg et forslag forst.", focus_widget=self.tree_control_suggestions)
            return
        if self.workspace.suggestions is None or self.workspace.suggestions.empty:
            self._notify_inline("Det finnes ingen forslag aa bruke.", focus_widget=self.tree_a07)
            return

        try:
            code = str(row.get("Kode") or "").strip() or self._selected_control_code()
            apply_suggestion_to_mapping(self.workspace.mapping, row)
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_control_code(code)
            if autosaved:
                self.status_var.set("Valgt forslag er brukt i mappingen og lagret i klientmappen.")
            else:
                self.status_var.set("Valgt forslag er brukt i mappingen.")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt forslag:\n{exc}")

    def _apply_selected_history_mapping(self) -> None:
        selection = self.tree_history.selection()
        if not selection:
            self._notify_inline("Velg en historikkrad forst.", focus_widget=self.tree_history)
            return

        code = self._selected_code_from_tree(self.tree_history)
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
            gl_df=self.workspace.gl_df,
        )
        if not code or not accounts:
            self._notify_inline(
                "Valgt historikk kan ikke brukes direkte. Kontoene maa finnes i aar og ikke kollidere med annen mapping.",
                focus_widget=self.tree_history,
            )
            return

        try:
            apply_suggestion_to_mapping(
                self.workspace.mapping,
                {"Kode": code, "ForslagKontoer": ",".join(accounts)},
            )
            autosaved = self._autosave_mapping()
            self._refresh_all()
            self._focus_mapping_account(accounts[0])
            if autosaved:
                self.status_var.set(
                    f"Historisk mapping brukt for {code} ({', '.join(accounts)}) og lagret i klientmappen."
                )
            else:
                self.status_var.set(f"Historisk mapping brukt for {code} ({', '.join(accounts)}).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke valgt historikk:\n{exc}")

    def _apply_batch_history_mappings(self) -> None:
        if self.history_compare_df is None or self.history_compare_df.empty:
            self._notify_inline("Det finnes ingen historikk aa bruke.", focus_widget=self.tree_a07)
            return

        codes = select_safe_history_codes(self.history_compare_df)
        if not codes:
            self._notify_inline(
                "Fant ingen sikre historikkmappinger. Kontoene maa finnes i aar og ikke kollidere med annen mapping.",
                focus_widget=self.tree_a07,
            )
            return

        try:
            applied_codes, applied_accounts = self._apply_safe_history_mappings()

            if applied_codes == 0:
                self._notify_inline(
                    "Ingen historikkmappinger kunne brukes etter konfliktkontroll mot dagens mapping.",
                    focus_widget=self.tree_a07,
                )
                return

            autosaved = self._autosave_mapping()
            self._refresh_all()
            if autosaved:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer) og lagret endringen."
                )
            else:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre historikkmappinger ({applied_accounts} kontoer)."
                )
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke sikre historikkmappinger:\n{exc}")

    def _apply_batch_suggestions_clicked(self) -> None:
        if self.workspace.suggestions is None or self.workspace.suggestions.empty:
            self._notify_inline("Det finnes ingen forslag aa bruke.", focus_widget=self.tree_a07)
            return

        row_indexes = select_batch_suggestion_rows(
            self.workspace.suggestions,
            self.workspace.mapping,
            min_score=0.85,
        )
        if not row_indexes:
            self._notify_inline(
                "Fant ingen sikre forslag. Batch-bruk krever treff innen toleranse og ingen konflikter.",
                focus_widget=self.tree_control_suggestions,
            )
            return

        try:
            applied_codes, applied_accounts = self._apply_safe_suggestions()

            autosaved = self._autosave_mapping()
            self._refresh_all()
            if autosaved:
                self.status_var.set(
                    f"Brukte {applied_codes} sikre forslag ({applied_accounts} kontoer) og lagret endringen."
                )
            else:
                self.status_var.set(f"Brukte {applied_codes} sikre forslag ({applied_accounts} kontoer).")
            self._select_primary_tab()
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke bruke sikre forslag:\n{exc}")

    def _remove_selected_mapping(self) -> None:
        selection = self.tree_mapping.selection()
        if not selection:
            self._notify_inline("Velg en eller flere mapping-rader forst.", focus_widget=self.tree_mapping)
            return

        removed = 0
        for konto in selection:
            if konto in self.workspace.mapping:
                self.workspace.mapping.pop(konto, None)
                removed += 1

        if removed == 0:
            self._notify_inline("Fant ingen mappinger aa fjerne.", focus_widget=self.tree_mapping)
            return

        try:
            autosaved = self._autosave_mapping()
            self._refresh_all()
            if autosaved:
                self.status_var.set(f"Fjernet {removed} mapping(er) og lagret endringen.")
            else:
                self.status_var.set(f"Fjernet {removed} mapping(er).")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere etter sletting:\n{exc}")

    def _refresh_all(self) -> None:
        a07_df = self.workspace.a07_df.copy()
        gl_df = self.workspace.gl_df.copy()
        client, year = self._session_context(session)
        self.rulebook_path = resolve_rulebook_path(client, year)
        self.matcher_settings = load_matcher_settings()
        (
            self.previous_mapping,
            self.previous_mapping_path,
            self.previous_mapping_year,
        ) = load_previous_year_mapping_for_context(client, year)

        self.workspace.suggestions = _empty_suggestions_df()
        self.reconcile_df = _empty_reconcile_df()
        self.unmapped_df = _empty_unmapped_df()

        if not a07_df.empty and not gl_df.empty:
            self.workspace.suggestions = suggest_mapping_candidates(
                a07_df=a07_df,
                gl_df=gl_df,
                mapping_existing=self.workspace.mapping,
                config=build_suggest_config(self.rulebook_path, self.matcher_settings),
                mapping_prior=self.previous_mapping,
            ).reset_index(drop=True)
            self.reconcile_df = reconcile_a07_vs_gl(
                a07_df=a07_df,
                gl_df=gl_df,
                mapping=self.workspace.mapping,
                basis_col="Endring",
            ).reset_index(drop=True)
            self.unmapped_df = unmapped_accounts_df(
                gl_df=gl_df,
                mapping=self.workspace.mapping,
                basis_col="Endring",
            ).reset_index(drop=True)

        self.mapping_df = mapping_to_assigned_df(
            mapping=self.workspace.mapping,
            gl_df=gl_df,
            include_empty=False,
        ).reset_index(drop=True)
        self.control_gl_df = build_control_gl_df(gl_df, self.workspace.mapping).reset_index(drop=True)
        self.a07_overview_df = build_a07_overview_df(a07_df, self.reconcile_df)
        self.control_df = build_control_queue_df(
            self.a07_overview_df,
            self.workspace.suggestions if self.workspace.suggestions is not None else _empty_suggestions_df(),
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
            gl_df=gl_df,
        ).reset_index(drop=True)
        self.history_compare_df = build_history_comparison_df(
            a07_df,
            gl_df,
            mapping_current=self.workspace.mapping,
            mapping_previous=self.previous_mapping,
        ).reset_index(drop=True)

        self._refresh_control_gl_tree()
        self._refresh_a07_tree()
        self._fill_tree(self.tree_history, self.history_compare_df, _HISTORY_COLUMNS, iid_column="Kode")
        self._refresh_suggestions_tree()
        self._refresh_control_support_trees()
        self._fill_tree(self.tree_reconcile, self.reconcile_df, _RECONCILE_COLUMNS, row_tag_fn=reconcile_tree_tag)
        self._fill_tree(self.tree_unmapped, self.unmapped_df, _UNMAPPED_COLUMNS, iid_column="Konto")
        self._fill_tree(self.tree_mapping, self.mapping_df, _MAPPING_COLUMNS, iid_column="Konto")
        self._update_selected_suggestion_details()
        self._on_control_selection_changed()
        self._update_summary()

    def _fill_tree(
        self,
        tree: ttk.Treeview,
        df: pd.DataFrame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        iid_column: str | None = None,
        row_tag_fn: Callable[[pd.Series], str | None] | None = None,
    ) -> None:
        for item in tree.get_children():
            tree.delete(item)

        if df is None or df.empty:
            return

        for idx, row in df.iterrows():
            values = [self._format_value(row.get(column_id), column_id) for column_id, *_rest in columns]
            iid = str(row.get(iid_column)).strip() if iid_column and str(row.get(iid_column, "")).strip() else str(idx)
            tags: tuple[str, ...] = ()
            if row_tag_fn is not None:
                try:
                    tag = row_tag_fn(row)
                except Exception:
                    tag = None
                if tag:
                    tags = (str(tag),)
            tree.insert("", "end", iid=iid, values=values, tags=tags)

    def _update_summary(self) -> None:
        client, year = self._session_context(session)
        ctx_parts = [x for x in (client, year) if x]
        context_text = " / ".join(ctx_parts) if ctx_parts else "ingen klientkontekst"

        suggestion_count = 0 if self.workspace.suggestions is None else int(len(self.workspace.suggestions))
        unsolved_count = count_unsolved_a07_codes(self.a07_overview_df)
        self.summary_var.set(
            " | ".join(
                [
                    f"Kontekst {context_text}",
                    f"Koder {len(self.workspace.a07_df)}",
                    f"Uløste {unsolved_count}",
                    f"Umappede {len(self.unmapped_df)}",
                    f"Forslag {suggestion_count}",
                ]
            )
        )

        if self.a07_path is None:
            if client and year:
                self.a07_path_var.set(
                    f"A07: ingen lagret A07-kilde i {default_a07_source_path(client, year)}"
                )
            else:
                self.a07_path_var.set("A07: ikke valgt")
        else:
            self.a07_path_var.set(f"A07: {self.a07_path}")

        if self.tb_path is None:
            if client and year:
                self.tb_path_var.set("Saldobalanse: ingen aktiv SB-versjon for klient/aar")
            else:
                self.tb_path_var.set("Saldobalanse: klient/aar ikke valgt")
        else:
            self.tb_path_var.set(f"Saldobalanse: aktiv versjon {self.tb_path}")

        if self.mapping_path is None:
            if client and year:
                self.mapping_path_var.set(
                    f"Mapping: ikke lagret ennå ({suggest_default_mapping_path(self.a07_path, client=client, year=year)})"
                )
            else:
                self.mapping_path_var.set("Mapping: ikke valgt")
        else:
            self.mapping_path_var.set(f"Mapping: {self.mapping_path}")

        if self.rulebook_path is None:
            self.rulebook_path_var.set(f"Rulebook: standard heuristikk ({default_global_rulebook_path()})")
        else:
            self.rulebook_path_var.set(f"Rulebook: {self.rulebook_path}")

        if self.previous_mapping_path is None or self.previous_mapping_year is None:
            self.history_path_var.set("Historikk: ingen tidligere A07-mapping funnet")
        else:
            self.history_path_var.set(
                f"Historikk: bruker prior fra {self.previous_mapping_year} ({self.previous_mapping_path})"
            )

        self.control_bucket_var.set(build_control_bucket_summary(self.control_df))
        self.details_var.set("Bruk Kilder... for filoversikt.")

    def _format_value(self, value: object, column_id: str) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "Ja" if value else "Nei"
        try:
            if pd.isna(value):
                return ""
        except Exception:
            pass

        decimals = _numeric_decimals_for_column(column_id)
        if decimals is not None:
            if isinstance(value, Decimal):
                return format_number_no(value, decimals)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return format_number_no(value, decimals)
            if isinstance(value, str):
                formatted = format_number_no(value, decimals)
                return formatted if formatted != value else value

        return str(value)
