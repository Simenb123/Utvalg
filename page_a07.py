from __future__ import annotations

import copy
import json
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Callable, Sequence

import pandas as pd

import app_paths
import session
from a07_feature import (
    A07Group,
    A07WorkspaceData,
    SuggestConfig,
    UiSuggestionRow,
    apply_groups_to_mapping,
    apply_suggestion_to_mapping,
    build_grouped_a07_df,
    derive_groups_path,
    export_a07_workbook,
    from_trial_balance,
    load_a07_groups,
    load_locks,
    load_mapping,
    load_project_state,
    mapping_to_assigned_df,
    parse_a07_json,
    reconcile_a07_vs_gl,
    save_a07_groups,
    save_locks,
    save_mapping,
    save_project_state,
    select_batch_suggestions,
    select_best_suggestion_for_code,
    select_magic_wand_suggestions,
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


_A07_DIAGNOSTICS_ENABLED = False
_A07_DIAGNOSTICS_LOG = Path(tempfile.gettempdir()) / "utvalg_a07_debug.log"


_A07_COLUMNS = (
    ("Kode", "Kode", 180, "w"),
    ("Navn", "Navn", 280, "w"),
    ("Belop", "Belop", 120, "e"),
    ("Status", "Status", 120, "w"),
    ("Kontoer", "Kontoer", 200, "w"),
)

_CONTROL_COLUMNS = (
    ("Kode", "Kode", 220, "w"),
    ("Navn", "Navn", 220, "w"),
    ("A07_Belop", "A07", 120, "e"),
    ("GL_Belop", "GL", 120, "e"),
    ("Diff", "Diff", 120, "e"),
    ("AntallKontoer", "Antall", 90, "e"),
    ("Status", "Status", 90, "w"),
    ("Anbefalt", "Neste", 110, "w"),
)

_CONTROL_GL_COLUMNS = (
    ("Konto", "Konto", 80, "w"),
    ("Navn", "Navn", 260, "w"),
    ("IB", "IB", 100, "e"),
    ("Endring", "Endring", 110, "e"),
    ("UB", "UB", 100, "e"),
    ("Kode", "Kode", 160, "w"),
)

_CONTROL_GL_DATA_COLUMNS = ("Konto", "Navn", "IB", "Endring", "UB", "Kode")

_CONTROL_SELECTED_ACCOUNT_COLUMNS = (
    ("Konto", "Konto", 90, "w"),
    ("Navn", "Navn", 250, "w"),
    ("IB", "IB", 110, "e"),
    ("Endring", "Endring", 120, "e"),
    ("UB", "UB", 110, "e"),
)

_CONTROL_SUGGESTION_COLUMNS = (
    ("ForslagKontoer", "Forslag", 220, "w"),
    ("Diff", "Diff", 120, "e"),
    ("Score", "Score", 90, "e"),
    ("WithinTolerance", "Innenfor", 80, "center"),
)

_CONTROL_EXTRA_COLUMNS = (
    "DagensMapping",
    "Arbeidsstatus",
    "ReconcileStatus",
    "NesteHandling",
    "Locked",
)

_GROUP_COLUMNS = (
    ("GroupId", "Gruppe", 180, "w"),
    ("Navn", "Navn", 220, "w"),
    ("Members", "Medlemmer", 280, "w"),
    ("Locked", "Låst", 70, "center"),
)

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

_BASIS_LABELS = {
    "Endring": "Endring",
    "UB": "UB",
    "IB": "IB",
}

_CONTROL_DRAG_IDLE_HINT = "Velg kode og konto, eller dra konto inn."

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


def _empty_groups_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _GROUP_COLUMNS])


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


def default_a07_mapping_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_mapping.json"


def default_a07_groups_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_groups.json"


def default_a07_locks_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_locks.json"


def default_a07_project_path(client: str | None, year: str | int | None) -> Path:
    return get_a07_workspace_dir(client, year) / "a07_project.json"


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
) -> tuple[tuple[str | None, int | None, int | None], ...]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    source_path = None
    mapping_path = None
    groups_path = None
    locks_path = None
    project_path = None
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

        groups_candidate = default_a07_groups_path(client_s, year_s)
        if groups_candidate.exists():
            groups_path = groups_candidate

        locks_candidate = default_a07_locks_path(client_s, year_s)
        if locks_candidate.exists():
            locks_path = locks_candidate

        project_candidate = default_a07_project_path(client_s, year_s)
        if project_candidate.exists():
            project_path = project_candidate

    tb_path = get_active_trial_balance_path_for_context(client_s, year_s)
    return (
        _path_signature(tb_path),
        _path_signature(source_path),
        _path_signature(mapping_path),
        _path_signature(groups_path),
        _path_signature(locks_path),
        _path_signature(project_path),
    )


def build_groups_df(groups: dict[str, A07Group], *, locked_codes: set[str] | None = None) -> pd.DataFrame:
    if not groups:
        return _empty_groups_df()

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

    return pd.DataFrame(rows, columns=[c[0] for c in _GROUP_COLUMNS])


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
        gl_belop = None
        diff = None
        account_count = 0

        if code.lower() in EXCLUDED_A07_CODES:
            status = "Ekskludert"
        elif code in reconcile_lookup:
            reconcile_row = reconcile_lookup[code]
            kontoer = str(reconcile_row.get("Kontoer") or "").strip()
            gl_belop = reconcile_row.get("GL_Belop")
            diff = reconcile_row.get("Diff")
            account_count = int(reconcile_row.get("AntallKontoer", 0) or 0)
            if bool(reconcile_row.get("WithinTolerance", False)):
                status = "OK"
            elif account_count > 0:
                status = "Avvik"

        rows.append(
            {
                "Kode": code,
                "Navn": navn,
                "Belop": belop,
                "GL_Belop": gl_belop,
                "Diff": diff,
                "AntallKontoer": account_count,
                "Status": status,
                "Kontoer": kontoer,
            }
        )

    return pd.DataFrame(
        rows,
        columns=["Kode", "Navn", "Belop", "GL_Belop", "Diff", "AntallKontoer", "Status", "Kontoer"],
    )


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


def _ui_suggestion_row_from_series(row: pd.Series) -> UiSuggestionRow:
    accounts = _parse_konto_tokens(row.get("ForslagKontoer"))
    try:
        a07_belop = float(row.get("A07_Belop") or 0.0)
    except Exception:
        a07_belop = 0.0
    try:
        gl_sum = float(row.get("GL_Sum") or 0.0)
    except Exception:
        gl_sum = 0.0
    try:
        diff = float(row.get("Diff") or 0.0)
    except Exception:
        diff = 0.0
    try:
        score = float(row.get("Score") or 0.0)
    except Exception:
        score = 0.0
    try:
        combo_size = int(row.get("ComboSize") or len(accounts) or 1)
    except Exception:
        combo_size = max(len(accounts), 1)
    hit_raw = row.get("HitTokens")
    if isinstance(hit_raw, (list, tuple, set)):
        hit_tokens = [str(value).strip() for value in hit_raw if str(value).strip()]
    else:
        hit_tokens = [token.strip() for token in str(hit_raw or "").replace(";", ",").split(",") if token.strip()]
    return UiSuggestionRow(
        kode=str(row.get("Kode") or "").strip(),
        kode_navn=str(row.get("KodeNavn") or row.get("Navn") or row.get("Kode") or "").strip(),
        a07_belop=a07_belop,
        gl_kontoer=accounts,
        gl_sum=gl_sum,
        diff=diff,
        score=score,
        combo_size=combo_size,
        within_tolerance=bool(row.get("WithinTolerance", False)),
        hit_tokens=hit_tokens,
        source_index=int(row.name) if isinstance(row.name, (int, float)) else None,
    )


def best_suggestion_row_for_code(
    suggestions_df: pd.DataFrame,
    code: str | None,
    *,
    locked_codes: set[str] | None = None,
) -> pd.Series | None:
    code_s = str(code or "").strip()
    if not code_s or suggestions_df is None or suggestions_df.empty or "Kode" not in suggestions_df.columns:
        return None

    matches = suggestions_df.loc[suggestions_df["Kode"].astype(str).str.strip() == code_s].copy()
    if matches.empty:
        return None

    ui_rows = [_ui_suggestion_row_from_series(row) for _, row in matches.iterrows()]
    best_ui = select_best_suggestion_for_code(ui_rows, code_s, locked_codes=locked_codes)
    if best_ui is None:
        return None

    if best_ui.source_index is not None and best_ui.source_index in matches.index:
        try:
            return matches.loc[best_ui.source_index]
        except Exception:
            pass

    for _, row in matches.iterrows():
        ui_row = _ui_suggestion_row_from_series(row)
        if (
            ui_row.kode == best_ui.kode
            and ui_row.gl_kontoer == best_ui.gl_kontoer
            and abs(ui_row.diff - best_ui.diff) < 1e-9
            and abs((ui_row.score or 0.0) - (best_ui.score or 0.0)) < 1e-9
        ):
            return row
    return None


# Compact control summaries keep the workspace readable in the pilot UI.
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
    status = "OK" if bool(row.get("WithinTolerance", False)) else "Sjekk"
    return f"Forslag {count} | Valgt {accounts} | Diff {diff} | {status}"


def build_control_suggestion_effect_summary(
    code: str | None,
    current_accounts: Sequence[object],
    selected_row: pd.Series | None,
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg kode i hoyre liste for aa se hva valgt forslag vil gjore."
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
    status_text = "OK" if bool(selected_row.get("WithinTolerance", False)) else "Sjekk"

    if current and set(current) == set(suggested):
        return f"Matcher dagens mapping {suggested_text} | Diff {diff} | {status_text}"
    if not current:
        return f"Mapper {suggested_text} til {code_s} | Diff {diff} | {status_text}"
    return f"Erstatter {current_text} med {suggested_text} | Diff {diff} | {status_text}"


def build_control_accounts_summary(
    accounts_df: pd.DataFrame,
    code: str | None,
    *,
    basis_col: str = "Endring",
) -> str:
    code_s = str(code or "").strip()
    if not code_s:
        return "Velg kode i hoyre liste for aa se mappede kontoer."
    if accounts_df is None or accounts_df.empty:
        return f"Ingen kontoer er mappet til {code_s} enna."

    count = int(len(accounts_df))
    value_column = str(basis_col or "Endring").strip()
    if value_column not in accounts_df.columns:
        value_column = "Endring"
    total_raw = accounts_df.get(value_column, pd.Series(dtype=object)).sum()
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
    return f"{count} {suffix} | {value_column} {total_endring} | {kontoer}"


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
    if action_s == "Ingen handling nødvendig.":
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
        mask = statuses.isin(["Ferdig", "Låst"])
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
    locked_codes: set[str] | None = None,
) -> pd.DataFrame:
    if a07_overview_df is None or a07_overview_df.empty:
        return _empty_control_df()

    locked = {str(code).strip() for code in (locked_codes or set()) if str(code).strip()}
    rows: list[dict[str, object]] = []
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode") or "").strip()
        navn = str(row.get("Navn") or "").strip()
        reconcile_status = str(row.get("Status") or "").strip()
        current_accounts = accounts_for_code(mapping_current, code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=mapping_current,
            mapping_previous=mapping_previous,
            gl_df=gl_df,
        )
        best_row = best_suggestion_row_for_code(suggestions_df, code, locked_codes=locked)
        next_action = control_next_action_label(
            reconcile_status,
            has_history=bool(history_accounts),
            best_suggestion=best_row,
        )
        if code in locked:
            work_status = "Låst"
        elif reconcile_status in {"OK", "Ekskludert"}:
            work_status = "Ferdig"
        elif next_action in {"Bruk historikk.", "Bruk beste forslag."}:
            work_status = "Trenger vurdering"
        else:
            work_status = "Trenger manuell mapping"
        if work_status == "Låst":
            display_status = "Låst"
        elif work_status == "Ferdig":
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
                "A07_Belop": row.get("Belop"),
                "GL_Belop": row.get("GL_Belop"),
                "Diff": row.get("Diff"),
                "AntallKontoer": row.get("AntallKontoer"),
                "Status": display_status,
                "DagensMapping": ", ".join(current_accounts),
                "Anbefalt": recommended,
                "NesteHandling": next_action,
                "Arbeidsstatus": work_status,
                "ReconcileStatus": reconcile_status,
                "Locked": code in locked,
            }
        )

    out = pd.DataFrame(rows, columns=[c[0] for c in _CONTROL_COLUMNS] + list(_CONTROL_EXTRA_COLUMNS))
    if out.empty:
        return out

    status_priority = {
        "Låst": 0,
        "Trenger manuell mapping": 0,
        "Trenger vurdering": 1,
        "Ferdig": 2,
    }
    work_status = out.get("Arbeidsstatus", pd.Series(index=out.index, dtype="object")).fillna("").astype(str)
    diff_abs = pd.to_numeric(out.get("Diff"), errors="coerce").abs()
    a07_abs = pd.to_numeric(out.get("A07_Belop"), errors="coerce").abs()
    belop_abs = diff_abs.where(diff_abs.notna() & diff_abs.ne(0), a07_abs).fillna(0)
    sort_df = out.assign(
        _status_priority=work_status.map(status_priority).fillna(9),
        _belop_abs=belop_abs,
    )
    sort_df = sort_df.sort_values(
        by=["_status_priority", "_belop_abs", "Kode"],
        ascending=[True, False, True],
        kind="stable",
    )
    return sort_df.drop(columns=["_status_priority", "_belop_abs"], errors="ignore").reset_index(drop=True)


def build_control_gl_df(gl_df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    if gl_df is None or gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

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

    return pd.DataFrame(rows, columns=list(_CONTROL_GL_DATA_COLUMNS))


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
    active_only: bool = False,
) -> pd.DataFrame:
    if control_gl_df is None or control_gl_df.empty:
        return pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))

    filtered = control_gl_df.copy()
    if active_only:
        numeric_cols = [column for column in ("IB", "Endring", "UB") if column in filtered.columns]
        if numeric_cols:
            numeric = filtered[numeric_cols].apply(pd.to_numeric, errors="coerce").fillna(0)
            has_activity = numeric.ne(0).any(axis=1)
        else:
            has_activity = pd.Series(False, index=filtered.index)
        if "Kode" in filtered.columns:
            has_mapping = filtered["Kode"].fillna("").astype(str).str.strip() != ""
            filtered = filtered.loc[has_activity | has_mapping].copy()
        else:
            filtered = filtered.loc[has_activity].copy()
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
        return "Låste 0 | Ferdig 0 | Vurdering 0 | Manuell 0"

    statuses = control_df["Arbeidsstatus"].astype(str).str.strip()
    locked = int((statuses == "Låst").sum())
    done = int((statuses == "Ferdig").sum())
    review = int((statuses == "Trenger vurdering").sum())
    manual = int((statuses == "Trenger manuell mapping").sum())
    return f"Låste {locked} | Ferdig {done} | Vurdering {review} | Manuell {manual}"


def control_tree_tag(work_status: object) -> str:
    status_s = str(work_status or "").strip()
    if status_s == "Låst":
        return "control_done"
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
        relation = "Ingen mapping ennå."

    history_label = previous_year or "tidligere aar"
    return f"{code_s} | I aar: {current_text} | {history_label}: {previous_text} | {relation}"


def select_batch_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    min_score: float = 0.85,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []

    selected_rows = select_batch_suggestions(
        [_ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        min_score=min_score,
        locked_codes=locked_codes,
    )
    return [
        int(row.source_index)
        for row in selected_rows
        if row.source_index is not None
    ]


def select_magic_wand_suggestion_rows(
    suggestions_df: pd.DataFrame,
    mapping_existing: dict[str, str],
    *,
    unresolved_codes: Sequence[object] | None = None,
    locked_codes: set[str] | None = None,
) -> list[int]:
    if suggestions_df is None or suggestions_df.empty:
        return []

    selected_rows = select_magic_wand_suggestions(
        [_ui_suggestion_row_from_series(row) for _, row in suggestions_df.iterrows()],
        mapping_existing,
        unresolved_codes=unresolved_codes,
        locked_codes=locked_codes,
    )
    return [
        int(row.source_index)
        for row in selected_rows
        if row.source_index is not None
    ]


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
            source_a07_df=_empty_a07_df(),
            mapping={},
            suggestions=None,
        )
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.control_gl_df = pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.groups_df = _empty_groups_df()
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.previous_mapping: dict[str, str] = {}
        self.matcher_settings = load_matcher_settings()

        self.a07_path: Path | None = None
        self.tb_path: Path | None = None
        self.mapping_path: Path | None = None
        self.groups_path: Path | None = None
        self.locks_path: Path | None = None
        self.project_path: Path | None = None
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
        self._session_refresh_job: str | None = None
        self._support_refresh_job: str | None = None
        self._refresh_in_progress = False
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_views_ready = False
        self._support_views_dirty = True
        self._support_requested = False
        self._refresh_generation = 0
        self._restore_thread: threading.Thread | None = None
        self._restore_result: dict[str, object] | None = None
        self._core_refresh_thread: threading.Thread | None = None
        self._core_refresh_result: dict[str, object] | None = None
        self._support_refresh_thread: threading.Thread | None = None
        self._support_refresh_result: dict[str, object] | None = None
        self._loaded_support_tabs: set[str] = set()
        self._pending_focus_code: str | None = None
        self._suspend_selection_sync = False
        self._suppressed_tree_select_keys: set[str] = set()
        self._tree_fill_jobs: dict[str, str] = {}
        self._tree_fill_tokens: dict[str, int] = {}
        self._control_gl_refresh_job: str | None = None
        self._a07_refresh_job: str | None = None
        self._control_selection_followup_job: str | None = None
        self._skip_initial_control_followup = False
        self._refresh_watchdog_job: str | None = None

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
        self.control_suggestion_effect_var = tk.StringVar(value="Velg forslag for aa se effekt.")
        self.history_details_var = tk.StringVar(value="Velg en kode for aa se historikk.")
        self.control_summary_var = tk.StringVar(value="Slik jobber du")
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
        self.basis_var = tk.StringVar(value=_BASIS_LABELS["Endring"])
        self.a07_filter_var = tk.StringVar(value="neste")
        self.a07_filter_label_var = tk.StringVar(value=_CONTROL_VIEW_LABELS["neste"])
        self.control_code_filter_var = tk.StringVar(value="")
        self.control_gl_filter_var = tk.StringVar(value="")
        self.control_gl_active_only_var = tk.BooleanVar(value=True)
        self.control_gl_unmapped_only_var = tk.BooleanVar(value=False)
        self.suggestion_scope_var = tk.StringVar(value="valgt_kode")
        self.suggestion_scope_label_var = tk.StringVar(value=_SUGGESTION_SCOPE_LABELS["valgt_kode"])

        self._build_ui()
        self.bind("<Visibility>", self._on_visible, add="+")
        try:
            parent.bind("<<NotebookTabChanged>>", self._on_notebook_tab_changed, add="+")
        except Exception:
            pass
        self._diag("init complete")
        self._schedule_session_refresh()

    def _diag(self, message: str) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        try:
            stamp = time.strftime("%H:%M:%S")
            with _A07_DIAGNOSTICS_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"[{stamp}] {message}\n")
        except Exception:
            pass

    def _tree_debug_name(self, tree: ttk.Treeview | None) -> str:
        if tree is None:
            return "<none>"
        try:
            return str(tree.winfo_name() or tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _cancel_refresh_watchdog(self) -> None:
        job = getattr(self, "_refresh_watchdog_job", None)
        if not job:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass
        self._refresh_watchdog_job = None

    def _schedule_refresh_watchdog(self, label: str, token: int) -> None:
        if not _A07_DIAGNOSTICS_ENABLED:
            return
        self._cancel_refresh_watchdog()

        def _run() -> None:
            self._refresh_watchdog_job = None
            if not bool(getattr(self, "_refresh_in_progress", False)):
                return
            active_token = int(getattr(self, "_refresh_generation", 0))
            stack_dump = ""
            try:
                current_frames = sys._current_frames()
                thread_frames: list[str] = []
                for thread in threading.enumerate():
                    ident = getattr(thread, "ident", None)
                    if ident is None:
                        continue
                    frame = current_frames.get(ident)
                    if frame is None:
                        continue
                    rendered = "".join(traceback.format_stack(frame, limit=20))
                    thread_frames.append(
                        f"--- thread={thread.name} ident={ident} alive={thread.is_alive()} ---\n{rendered}"
                    )
                stack_dump = "\n".join(thread_frames).strip()
            except Exception:
                stack_dump = ""
            self._diag(
                "watchdog "
                f"{label} token={token} active_token={active_token} "
                f"pending_session={self._pending_session_refresh} "
                f"pending_support={self._pending_support_refresh} "
                f"support_ready={self._support_views_ready} "
                f"support_dirty={self._support_views_dirty} "
                f"restore_alive={bool(self._restore_thread and self._restore_thread.is_alive())} "
                f"core_alive={bool(self._core_refresh_thread and self._core_refresh_thread.is_alive())} "
                f"support_alive={bool(self._support_refresh_thread and self._support_refresh_thread.is_alive())}"
            )
            if stack_dump:
                self._diag(f"watchdog-stack {label} token={token}\n{stack_dump}")
            try:
                self._refresh_watchdog_job = self.after(2000, _run)
            except Exception:
                self._refresh_watchdog_job = None

        try:
            self._refresh_watchdog_job = self.after(2000, _run)
        except Exception:
            self._refresh_watchdog_job = None

    def refresh_from_session(self, session_module=session) -> None:
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        context = self._session_context(session_module)
        snapshot = get_context_snapshot(*context)
        if context != self._context_key or snapshot != self._context_snapshot:
            self._context_key = context
            self._context_snapshot = snapshot
            self._restore_context_state(*context)
            return
        self._update_summary()

    def _schedule_session_refresh(self, delay_ms: int = 1) -> None:
        if self._session_refresh_job is not None:
            try:
                self.after_cancel(self._session_refresh_job)
            except Exception:
                pass
            self._session_refresh_job = None

        def _run() -> None:
            self._session_refresh_job = None
            self.refresh_from_session()

        try:
            self._session_refresh_job = self.after(delay_ms, _run)
        except Exception:
            self.refresh_from_session()

    def _cancel_scheduled_job(self, attr_name: str) -> None:
        job = getattr(self, attr_name, None)
        if not job:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass
        setattr(self, attr_name, None)

    def _schedule_control_gl_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_control_gl_refresh_job")

        def _run() -> None:
            self._control_gl_refresh_job = None
            self._refresh_control_gl_tree_chunked(on_complete=on_complete)

        try:
            self._control_gl_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_a07_refresh(
        self,
        delay_ms: int = 75,
        *,
        on_complete: Callable[[], None] | None = None,
    ) -> None:
        self._cancel_scheduled_job("_a07_refresh_job")

        def _run() -> None:
            self._a07_refresh_job = None
            self._refresh_a07_tree_chunked(on_complete=on_complete)

        try:
            self._a07_refresh_job = self.after(delay_ms, _run)
        except Exception:
            _run()

    def _schedule_control_selection_followup(self) -> None:
        self._cancel_scheduled_job("_control_selection_followup_job")

        def _run() -> None:
            self._control_selection_followup_job = None
            if bool(getattr(self, "_skip_initial_control_followup", False)):
                self._skip_initial_control_followup = False
                self._diag("skip initial control selection followup")
                self._update_control_transfer_buttons()
                return
            support_requested = bool(getattr(self, "_support_requested", True))
            if (
                bool(getattr(self, "_control_details_visible", False))
                and support_requested
                and self._support_views_ready
                and self._active_support_tab_key() == "suggestions"
            ):
                self._refresh_suggestions_tree()
            if bool(getattr(self, "_control_details_visible", False)) and support_requested:
                if self._support_views_ready:
                    self._refresh_control_support_trees()
                else:
                    self._schedule_support_refresh()
            if bool(getattr(self, "_control_details_visible", False)) and not self._retag_control_gl_tree():
                self._schedule_control_gl_refresh(delay_ms=1)
            else:
                self._update_control_transfer_buttons()

        try:
            self._control_selection_followup_job = self.after(40, _run)
        except Exception:
            _run()

    def _cancel_support_refresh(self) -> None:
        if self._support_refresh_job is None:
            return
        try:
            self.after_cancel(self._support_refresh_job)
        except Exception:
            pass
        self._support_refresh_job = None

    def _schedule_support_refresh(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if self._support_views_ready and not self._support_views_dirty:
            if self._active_support_tab_key() in self._loaded_support_tabs:
                self._render_active_support_tab(force=True)
            return
        self._cancel_support_refresh()

        def _run() -> None:
            self._support_refresh_job = None
            self._refresh_support_views()

        try:
            self._support_refresh_job = self.after(60, _run)
        except Exception:
            self._refresh_support_views()

    def _cancel_core_refresh_jobs(self) -> None:
        for attr_name in (
            "_session_refresh_job",
            "_control_gl_refresh_job",
            "_a07_refresh_job",
            "_control_selection_followup_job",
        ):
            self._cancel_scheduled_job(attr_name)

        for tree_name in ("tree_control_gl", "tree_a07"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            try:
                self._cancel_tree_fill(tree)
            except Exception:
                pass
            key = self._tree_fill_key(tree)
            try:
                self._tree_fill_tokens[key] = int(self._tree_fill_tokens.get(key, 0)) + 1
            except Exception:
                pass

    def _next_refresh_generation(self) -> int:
        self._refresh_generation += 1
        return self._refresh_generation

    def _start_context_restore(self, client: str | None, year: str | None) -> None:
        token = self._next_refresh_generation()
        self._diag(f"start_context_restore token={token} client={client!r} year={year!r}")
        self._schedule_refresh_watchdog("context-restore", token)
        self._support_requested = False
        self.status_var.set("Laster A07-kontekst...")
        self.details_var.set("Laster saldobalanse, mapping og prosjektoppsett i bakgrunnen...")
        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                gl_df, tb_path = load_active_trial_balance_for_context(client, year)
                source_a07_df = _empty_a07_df()
                a07_df = _empty_a07_df()
                a07_path: Path | None = None
                source_path = default_a07_source_path(client, year)
                if source_path.exists():
                    try:
                        source_a07_df = parse_a07_json(source_path)
                        a07_df = source_a07_df.copy()
                        a07_path = source_path
                    except Exception:
                        source_a07_df = _empty_a07_df()
                        a07_df = _empty_a07_df()
                        a07_path = None

                mapping: dict[str, str] = {}
                mapping_path: Path | None = None
                mapping_candidate = suggest_default_mapping_path(a07_path, client=client, year=year)
                if mapping_candidate.exists():
                    try:
                        mapping = load_mapping(mapping_candidate)
                        mapping_path = mapping_candidate
                    except Exception:
                        mapping = {}
                        mapping_path = None

                groups: dict[str, A07Group] = {}
                groups_path: Path | None = None
                locks: set[str] = set()
                locks_path: Path | None = None
                project_meta: dict[str, object] = {}
                project_path: Path | None = None
                if client and year:
                    try:
                        groups_path = default_a07_groups_path(client, year)
                        groups = load_a07_groups(groups_path)
                    except Exception:
                        groups = {}
                        groups_path = None
                    try:
                        locks_path = default_a07_locks_path(client, year)
                        locks = load_locks(locks_path)
                    except Exception:
                        locks = set()
                        locks_path = None
                    try:
                        project_path = default_a07_project_path(client, year)
                        project_meta = load_project_state(project_path)
                    except Exception:
                        project_meta = {}
                        project_path = None

                basis_col = str(project_meta.get("basis_col") or "Endring").strip()
                if basis_col not in _BASIS_LABELS:
                    basis_col = "Endring"

                (
                    previous_mapping,
                    previous_mapping_path,
                    previous_mapping_year,
                ) = load_previous_year_mapping_for_context(client, year)

                result_box["payload"] = {
                    "gl_df": gl_df,
                    "tb_path": tb_path,
                    "source_a07_df": source_a07_df,
                    "a07_df": a07_df,
                    "a07_path": a07_path,
                    "mapping": mapping,
                    "mapping_path": mapping_path,
                    "groups": groups,
                    "groups_path": groups_path,
                    "locks": locks,
                    "locks_path": locks_path,
                    "project_meta": project_meta,
                    "project_path": project_path,
                    "basis_col": basis_col,
                    "previous_mapping": previous_mapping,
                    "previous_mapping_path": previous_mapping_path,
                    "previous_mapping_year": previous_mapping_year,
                    "rulebook_path": resolve_rulebook_path(client, year),
                    "pending_focus_code": str(project_meta.get("selected_code") or "").strip() or None,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07ContextRestore-{token}", daemon=True)
        self._restore_thread = thread
        self._restore_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_context_restore(token))

    def _poll_context_restore(self, token: int) -> None:
        if token != self._refresh_generation:
            self._diag(f"poll_context_restore stale token={token} active={self._refresh_generation}")
            self._restore_thread = None
            self._restore_result = None
            return
        thread = self._restore_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_context_restore(token))
            return
        result = self._restore_result or {}
        self._restore_thread = None
        self._restore_result = None
        error = result.get("error")
        if error is not None:
            self._diag(f"context_restore error token={token}: {error}")
            self._refresh_in_progress = False
            self._cancel_refresh_watchdog()
            self.status_var.set("A07-kontekst kunne ikke lastes.")
            self.details_var.set(str(error))
            if self._pending_session_refresh:
                self._pending_session_refresh = False
                self._schedule_session_refresh()
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            self._diag(f"context_restore complete token={token}")
            self._apply_context_restore_payload(payload)

    def _apply_context_restore_payload(self, payload: dict[str, object]) -> None:
        self.workspace.gl_df = payload["gl_df"]
        self.tb_path = payload["tb_path"]
        self.workspace.source_a07_df = payload["source_a07_df"]
        self.workspace.a07_df = payload["a07_df"]
        self.a07_path = payload["a07_path"]
        self.workspace.mapping = payload["mapping"]
        self.mapping_path = payload["mapping_path"]
        self.workspace.groups = payload["groups"]
        self.groups_path = payload["groups_path"]
        self.workspace.locks = payload["locks"]
        self.locks_path = payload["locks_path"]
        self.workspace.project_meta = payload["project_meta"]
        self.project_path = payload["project_path"]
        self.workspace.basis_col = payload["basis_col"]
        self.basis_var.set(_BASIS_LABELS[self.workspace.basis_col])
        self.previous_mapping = payload["previous_mapping"]
        self.previous_mapping_path = payload["previous_mapping_path"]
        self.previous_mapping_year = payload["previous_mapping_year"]
        self.rulebook_path = payload["rulebook_path"]
        self._pending_focus_code = payload["pending_focus_code"]
        self._start_core_refresh()

    def _start_core_refresh(self) -> None:
        token = self._next_refresh_generation()
        self._diag(f"start_core_refresh token={token}")
        self._schedule_refresh_watchdog("core-refresh", token)
        client, year = self._session_context(session)
        source_a07_df = (
            self.workspace.source_a07_df.copy()
            if self.workspace.source_a07_df is not None
            else self.workspace.a07_df.copy()
        )
        gl_df = self.workspace.gl_df.copy()
        groups = copy.deepcopy(self.workspace.groups)
        mapping = dict(self.workspace.mapping)
        basis_col = str(self.workspace.basis_col or "Endring")
        locks = set(self.workspace.locks)

        self.status_var.set("Oppdaterer A07...")
        self.details_var.set("Beregner kjernevisningene i bakgrunnen...")

        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                rulebook_path = resolve_rulebook_path(client, year)
                matcher_settings = load_matcher_settings()
                (
                    previous_mapping,
                    previous_mapping_path,
                    previous_mapping_year,
                ) = load_previous_year_mapping_for_context(client, year)
                grouped_a07_df, membership = build_grouped_a07_df(source_a07_df, groups)
                effective_mapping = apply_groups_to_mapping(mapping, membership)
                effective_previous_mapping = apply_groups_to_mapping(previous_mapping, membership)

                suggestions = _empty_suggestions_df()

                control_gl_df = build_control_gl_df(gl_df, effective_mapping).reset_index(drop=True)
                a07_overview_df = build_a07_overview_df(grouped_a07_df, _empty_reconcile_df())
                control_df = build_control_queue_df(
                    a07_overview_df,
                    suggestions if suggestions is not None else _empty_suggestions_df(),
                    mapping_current=effective_mapping,
                    mapping_previous=effective_previous_mapping,
                    gl_df=gl_df,
                    locked_codes=locks,
                ).reset_index(drop=True)
                groups_df = build_groups_df(groups, locked_codes=locks).reset_index(drop=True)

                result_box["payload"] = {
                    "rulebook_path": rulebook_path,
                    "matcher_settings": matcher_settings,
                    "previous_mapping": previous_mapping,
                    "previous_mapping_path": previous_mapping_path,
                    "previous_mapping_year": previous_mapping_year,
                    "grouped_a07_df": grouped_a07_df.reset_index(drop=True),
                    "membership": membership,
                    "suggestions": suggestions,
                    "control_gl_df": control_gl_df,
                    "a07_overview_df": a07_overview_df,
                    "control_df": control_df,
                    "groups_df": groups_df,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07CoreRefresh-{token}", daemon=True)
        self._core_refresh_thread = thread
        self._core_refresh_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_core_refresh(token))

    def _poll_core_refresh(self, token: int) -> None:
        if token != self._refresh_generation:
            self._diag(f"poll_core_refresh stale token={token} active={self._refresh_generation}")
            self._core_refresh_thread = None
            self._core_refresh_result = None
            return
        thread = self._core_refresh_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_core_refresh(token))
            return
        result = self._core_refresh_result or {}
        self._core_refresh_thread = None
        self._core_refresh_result = None
        error = result.get("error")
        if error is not None:
            self._diag(f"core_refresh error token={token}: {error}")
            self._refresh_in_progress = False
            self._cancel_refresh_watchdog()
            self.status_var.set("A07-oppdatering feilet.")
            self.details_var.set(str(error))
            if self._pending_session_refresh:
                self._pending_session_refresh = False
                self._schedule_session_refresh()
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            self._diag(f"core_refresh complete token={token}")
            self._apply_core_refresh_payload(payload)

    def _apply_core_refresh_payload(self, payload: dict[str, object]) -> None:
        self.rulebook_path = payload["rulebook_path"]
        self.matcher_settings = payload["matcher_settings"]
        self.previous_mapping = payload["previous_mapping"]
        self.previous_mapping_path = payload["previous_mapping_path"]
        self.previous_mapping_year = payload["previous_mapping_year"]
        self.workspace.a07_df = payload["grouped_a07_df"]
        self.workspace.membership = payload["membership"]
        self.workspace.suggestions = payload["suggestions"]
        self.control_gl_df = payload["control_gl_df"]
        self.a07_overview_df = payload["a07_overview_df"]
        self.control_df = payload["control_df"]
        self.groups_df = payload["groups_df"]
        self.reconcile_df = _empty_reconcile_df()
        self.unmapped_df = _empty_unmapped_df()
        self.mapping_df = _empty_mapping_df()
        self.history_compare_df = _empty_history_df()

        self.control_suggestion_summary_var.set("Laster forslag...")
        self.control_suggestion_effect_var.set("Laster forslag...")
        self.control_accounts_summary_var.set("Laster mappede kontoer...")
        self._support_views_ready = False
        self._support_views_dirty = True
        self._loaded_support_tabs.clear()
        pending_focus_code = (self._pending_focus_code or "").strip()
        self._pending_focus_code = None

        def _sync_post_core_selection(target_code: str) -> None:
            self.workspace.selected_code = target_code or None
            self._update_history_details_from_selection()
            self._update_control_panel()
            self._update_control_transfer_buttons()

        def _finalize_core_refresh() -> None:
            diag = getattr(self, "_diag", lambda *_args, **_kwargs: None)
            cancel_watchdog = getattr(self, "_cancel_refresh_watchdog", lambda: None)
            try:
                diag("finalize_core_refresh start")
                self._fill_tree(self.tree_groups, self.groups_df, _GROUP_COLUMNS, iid_column="GroupId")
                self._fill_tree(self.tree_control_suggestions, _empty_suggestions_df(), _CONTROL_SUGGESTION_COLUMNS)
                self._fill_tree(
                    self.tree_control_accounts,
                    pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]),
                    _CONTROL_SELECTED_ACCOUNT_COLUMNS,
                    iid_column="Konto",
                )
                self._update_control_panel()
                self._update_control_transfer_buttons()
                self._update_summary()
                self.status_var.set("A07 oppdatert.")
                self.details_var.set("Velg konto og kode for aa jobbe videre. Forslag lastes ved behov.")
                try:
                    self._set_control_details_visible(False)
                except Exception:
                    pass

                target_code = ""
                try:
                    code_children = tuple(self.tree_a07.get_children())
                except Exception:
                    code_children = ()
                if code_children:
                    if pending_focus_code and pending_focus_code in code_children:
                        target_code = str(pending_focus_code)
                    else:
                        target_code = str(code_children[0])
                if target_code:
                    self._skip_initial_control_followup = True
                    try:
                        self._set_tree_selection(self.tree_a07, target_code)
                    except Exception:
                        pass
                    try:
                        _sync_post_core_selection(target_code)
                    except Exception:
                        pass
                self._pending_support_refresh = False
                if self._pending_session_refresh:
                    self._pending_session_refresh = False
                    if self._context_has_changed():
                        self._schedule_session_refresh()
                diag("finalize_core_refresh complete")
            except Exception as exc:
                diag(f"finalize_core_refresh error: {exc}")
                diag(traceback.format_exc())
                self.status_var.set("A07-oppdatering feilet i ferdigstilling.")
                self.details_var.set(str(exc))
            finally:
                self._refresh_in_progress = False
                cancel_watchdog()

        refresh_control_gl = getattr(self, "_refresh_control_gl_tree_chunked", None)
        refresh_a07 = getattr(self, "_refresh_a07_tree_chunked", None)
        if callable(refresh_control_gl) and callable(refresh_a07):
            refresh_control_gl(on_complete=lambda: refresh_a07(on_complete=_finalize_core_refresh))
            return
        self._refresh_control_gl_tree()
        self._refresh_a07_tree()
        _finalize_core_refresh()

    def _start_support_refresh(self) -> None:
        token = self._refresh_generation
        self._diag(f"start_support_refresh token={token}")
        client, year = self._session_context(session)
        gl_df = self.workspace.gl_df.copy()
        a07_df = self.workspace.a07_df.copy()
        effective_mapping = dict(self._effective_mapping())
        effective_previous_mapping = dict(self._effective_previous_mapping())
        basis_col = str(self.workspace.basis_col or "Endring")

        result_box: dict[str, object] = {"token": token}

        def _worker() -> None:
            try:
                rulebook_path = resolve_rulebook_path(client, year)
                matcher_settings = load_matcher_settings()
                suggestions = _empty_suggestions_df()
                if not a07_df.empty and not gl_df.empty:
                    suggestions = suggest_mapping_candidates(
                        a07_df=a07_df,
                        gl_df=gl_df,
                        mapping_existing=effective_mapping,
                        config=build_suggest_config(
                            rulebook_path,
                            matcher_settings,
                            basis_col=basis_col,
                        ),
                        mapping_prior=effective_previous_mapping,
                    ).reset_index(drop=True)
                mapping_df = mapping_to_assigned_df(
                    mapping=effective_mapping,
                    gl_df=gl_df,
                    include_empty=False,
                    basis_col=basis_col,
                ).reset_index(drop=True)
                history_compare_df = build_history_comparison_df(
                    a07_df,
                    gl_df,
                    mapping_current=effective_mapping,
                    mapping_previous=effective_previous_mapping,
                ).reset_index(drop=True)
                reconcile_df = _empty_reconcile_df()
                unmapped_df = _empty_unmapped_df()
                if not a07_df.empty and not gl_df.empty:
                    reconcile_df = reconcile_a07_vs_gl(
                        a07_df=a07_df,
                        gl_df=gl_df,
                        mapping=effective_mapping,
                        basis_col=basis_col,
                    ).reset_index(drop=True)
                    unmapped_df = unmapped_accounts_df(
                        gl_df=gl_df,
                        mapping=effective_mapping,
                        basis_col=basis_col,
                    ).reset_index(drop=True)
                result_box["payload"] = {
                    "suggestions": suggestions,
                    "mapping_df": mapping_df,
                    "history_compare_df": history_compare_df,
                    "reconcile_df": reconcile_df,
                    "unmapped_df": unmapped_df,
                }
            except Exception as exc:
                result_box["error"] = exc

        thread = threading.Thread(target=_worker, name=f"A07SupportRefresh-{token}", daemon=True)
        self._support_refresh_thread = thread
        self._support_refresh_result = result_box
        thread.start()
        self.after(25, lambda: self._poll_support_refresh(token))

    def _poll_support_refresh(self, token: int) -> None:
        diag = getattr(self, "_diag", lambda *_args, **_kwargs: None)
        if token != self._refresh_generation:
            diag(f"poll_support_refresh stale token={token} active={self._refresh_generation}")
            self._support_refresh_thread = None
            self._support_refresh_result = None
            self._support_views_ready = False
            return
        thread = self._support_refresh_thread
        if thread is not None and thread.is_alive():
            self.after(25, lambda: self._poll_support_refresh(token))
            return
        result = self._support_refresh_result or {}
        self._support_refresh_thread = None
        self._support_refresh_result = None
        error = result.get("error")
        if error is not None:
            diag(f"support_refresh error token={token}: {error}")
            self._support_views_ready = False
            self.status_var.set("A07-stottevisninger feilet.")
            self.details_var.set(str(error))
            return
        payload = result.get("payload")
        if isinstance(payload, dict):
            diag(f"support_refresh complete token={token}")
            self._apply_support_refresh_payload(payload)

    def _apply_support_refresh_payload(self, payload: dict[str, object]) -> None:
        self.workspace.suggestions = payload["suggestions"]
        self.mapping_df = payload["mapping_df"]
        self.history_compare_df = payload["history_compare_df"]
        self.reconcile_df = payload["reconcile_df"]
        self.unmapped_df = payload["unmapped_df"]

        self._support_views_ready = True
        self._support_views_dirty = False
        self._loaded_support_tabs.clear()
        def _apply_support_ui_updates() -> None:
            active_tab = self._active_support_tab_key()
            if bool(getattr(self, "_control_details_visible", False)):
                self._refresh_control_support_trees()
                if active_tab:
                    self._render_active_support_tab(force=True)
            self._update_history_details_from_selection()
            self._update_control_panel()
            self._update_control_transfer_buttons()
            self._update_summary()

        try:
            self.after_idle(_apply_support_ui_updates)
        except Exception:
            _apply_support_ui_updates()

    def _on_visible(self, _event: tk.Event | None = None) -> None:
        try:
            if _event is not None and getattr(_event, "widget", None) is not self:
                return
        except Exception:
            pass
        try:
            if not self.winfo_viewable():
                return
        except Exception:
            pass
        if self._refresh_in_progress:
            return
        try:
            if not self._context_has_changed():
                return
        except Exception:
            pass
        self._schedule_session_refresh(delay_ms=50)

    def _on_notebook_tab_changed(self, event: tk.Event | None = None) -> None:
        if event is None:
            return
        try:
            notebook = event.widget
            selected = notebook.nametowidget(notebook.select())
        except Exception:
            return
        if selected is self:
            if self._refresh_in_progress:
                return
            try:
                if not self._context_has_changed():
                    return
            except Exception:
                pass
            self._schedule_session_refresh(delay_ms=50)

    def _build_ui(self) -> None:
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(fill="x")

        ttk.Button(toolbar, text="Last A07", command=self._load_a07_clicked).pack(side="left")
        ttk.Button(toolbar, text="Oppdater", command=self._refresh_clicked).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Tryllestav", command=self._magic_match_clicked).pack(side="left", padx=(6, 0))
        ttk.Button(toolbar, text="Eksporter", command=self._export_clicked).pack(side="left", padx=(6, 0))
        ttk.Label(toolbar, text="Basis:").pack(side="right", padx=(12, 4))
        self.basis_widget = ttk.Combobox(
            toolbar,
            state="readonly",
            width=10,
            values=[_BASIS_LABELS[key] for key in _BASIS_LABELS],
            textvariable=self.basis_var,
        )
        self.basis_widget.pack(side="right")
        self.basis_widget.bind("<<ComboboxSelected>>", lambda _event: self._on_basis_changed())

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
        tools_menu.add_separator()
        tools_menu.add_command(label="Opprett A07-gruppe fra valgt kodeutvalg", command=self._create_group_from_selection)
        tools_menu.add_command(label="Oppløs valgt A07-gruppe", command=self._remove_selected_group)
        tools_menu.add_separator()
        tools_menu.add_command(label="Lås valgt kode", command=self._lock_selected_code)
        tools_menu.add_command(label="Lås opp valgt kode", command=self._unlock_selected_code)
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
        self.tab_control = tab_control

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

        # Use a real vertical pane split so the user gets a stable layout and
        # can reclaim workspace without the old double-geometry bug.
        control_vertical = ttk.Panedwindow(control_workspace, orient="vertical")
        control_vertical.pack(fill="both", expand=True)
        control_top_host = ttk.Frame(control_vertical)
        control_lower = ttk.Frame(control_vertical)
        control_vertical.add(control_top_host, weight=5)
        control_vertical.add(control_lower, weight=2)
        self.control_vertical_panes = control_vertical

        control_top = ttk.Panedwindow(control_top_host, orient="horizontal")
        control_top.pack(fill="both", expand=True)

        control_gl_panel = ttk.LabelFrame(control_top, text="1. Velg konto", padding=(8, 8))
        control_assign_panel = ttk.Frame(control_top, width=32, padding=(0, 2, 0, 0))
        control_a07_panel = ttk.LabelFrame(control_top, text="2. A07 avstemming", padding=(8, 8))
        control_top.add(control_gl_panel, weight=4)
        control_top.add(control_assign_panel, weight=0)
        control_top.add(control_a07_panel, weight=5)
        try:
            control_assign_panel.pack_propagate(False)
        except Exception:
            pass

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
            text="Kun aktive",
            variable=self.control_gl_active_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left")
        ttk.Checkbutton(
            control_gl_filters,
            text="Kun umappede",
            variable=self.control_gl_unmapped_only_var,
            command=self._on_control_gl_filter_changed,
        ).pack(side="left", padx=(8, 0))
        self.tree_control_gl = self._build_tree_tab(control_gl_panel, _CONTROL_GL_COLUMNS)
        try:
            self.tree_control_gl.tag_configure("control_gl_unmapped", background="#FFF3CD", foreground="#7A5B00")
            self.tree_control_gl.tag_configure("control_gl_mapped", background="#FFFFFF", foreground="#1F2430")
            self.tree_control_gl.tag_configure("control_gl_selected", background="#D9ECFF", foreground="#0B4F8A")
            self.tree_control_gl.tag_configure("control_gl_suggestion", background="#E8F6EA", foreground="#256D5A")
        except Exception:
            pass

        self.tree_a07 = self._build_tree_tab(control_a07_panel, _CONTROL_COLUMNS)
        self.tree_a07.configure(selectmode="extended")
        try:
            self.tree_a07.tag_configure("control_done", background="#E2F1EB", foreground="#256D5A")
            self.tree_a07.tag_configure("control_review", background="#FCEBD9", foreground="#9F5B2E")
            self.tree_a07.tag_configure("control_manual", background="#FCE4D6", foreground="#8A3B12")
            self.tree_a07.tag_configure("control_default", background="#FFFFFF", foreground="#1F2430")
        except Exception:
            pass

        groups_panel = ttk.LabelFrame(control_a07_panel, text="A07-grupper", padding=(8, 6))
        groups_panel.pack(fill="x", pady=(8, 0))
        groups_actions = ttk.Frame(groups_panel)
        groups_actions.pack(fill="x", pady=(0, 6))
        ttk.Button(groups_actions, text="Opprett gruppe", command=self._create_group_from_selection).pack(side="left")
        ttk.Button(groups_actions, text="Oppløs gruppe", command=self._remove_selected_group).pack(side="left", padx=(6, 0))
        self.tree_groups = self._build_tree_tab(groups_panel, _GROUP_COLUMNS)
        self.tree_groups.configure(height=4)

        self.btn_control_assign = ttk.Button(
            control_assign_panel,
            text="→",
            width=4,
            command=self._assign_selected_control_mapping,
        )
        self.btn_control_assign.pack(fill="x", pady=(28, 0))
        self.btn_control_clear = ttk.Button(
            control_assign_panel,
            text="←",
            width=4,
            command=self._clear_selected_control_mapping,
        )
        self.btn_control_clear.pack(fill="x", pady=(8, 0))
        for button in (self.btn_control_assign, self.btn_control_clear):
            button.state(["disabled"])
        self.control_lower_panel = control_lower

        control_status = ttk.LabelFrame(control_lower, text="Oppsummering", padding=(8, 4))
        control_status.pack(fill="x", pady=(4, 0))
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
        ).pack(anchor="w")

        control_actions = ttk.Frame(control_status)
        control_actions.grid(row=0, column=1, sticky="ne", padx=(12, 0))
        self.btn_control_best = ttk.Button(
            control_actions,
            text="Beste forslag",
            command=self._apply_best_suggestion_for_selected_code,
        )
        self.btn_control_best.pack(side="left")
        self.btn_control_history = ttk.Button(
            control_actions,
            text="Historikk",
            command=self._apply_history_for_selected_code,
        )
        self.btn_control_history.pack(side="left", padx=(6, 0))
        for button in (self.btn_control_best, self.btn_control_history):
            button.state(["disabled"])

        self.lbl_control_drag = ttk.Label(control_status, text="", style="Muted.TLabel")

        control_detail_panes = ttk.Panedwindow(control_lower, orient="vertical")
        control_detail_panes.pack(fill="x", expand=False, pady=(4, 0))
        self.control_detail_panes = control_detail_panes

        control_suggest_panel = ttk.LabelFrame(control_detail_panes, text="Forslag", padding=(8, 8))
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
        self.tree_control_suggestions = self._build_tree_tab(control_suggest_panel, _CONTROL_SUGGESTION_COLUMNS)
        self.tree_control_suggestions.configure(height=3)
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
            text="Mappede kontoer",
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
        self.tree_control_accounts.configure(height=3)

        control_support_nb = ttk.Notebook(control_lower)
        tab_history = ttk.Frame(control_support_nb)
        tab_suggestions = ttk.Frame(control_support_nb)
        tab_reconcile = ttk.Frame(control_support_nb)
        tab_unmapped = ttk.Frame(control_support_nb)
        tab_mapping = ttk.Frame(control_support_nb)
        self.tab_history = tab_history
        self.tab_suggestions = tab_suggestions
        self.tab_reconcile = tab_reconcile
        self.tab_unmapped = tab_unmapped
        self.tab_mapping = tab_mapping

        self.tree_history = self._build_tree_tab(tab_history, _HISTORY_COLUMNS)
        self.tree_history.configure(height=5)
        self.tree_suggestions = self._build_tree_tab(tab_suggestions, _SUGGESTION_COLUMNS)
        self.tree_suggestions.configure(height=5)
        try:
            self.tree_suggestions.tag_configure("suggestion_ok", background="#E2F1EB", foreground="#256D5A")
            self.tree_suggestions.tag_configure("suggestion_review", background="#FCEBD9", foreground="#9F5B2E")
            self.tree_suggestions.tag_configure("suggestion_default", background="#FFFFFF", foreground="#1F2430")
        except Exception:
            pass
        ttk.Label(
            tab_reconcile,
            text="A07 vs GL for valgt basis. Diff og antall kontoer brukes som primær avstemmingsflate.",
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).pack(anchor="w", fill="x", padx=8, pady=(8, 4))
        self.tree_reconcile = self._build_tree_tab(tab_reconcile, _RECONCILE_COLUMNS)
        self.tree_reconcile.configure(height=5)
        try:
            self.tree_reconcile.tag_configure("reconcile_ok", background="#E2F1EB", foreground="#256D5A")
            self.tree_reconcile.tag_configure("reconcile_diff", background="#FCE4D6", foreground="#8A3B12")
        except Exception:
            pass
        ttk.Label(
            tab_unmapped,
            text="Umappede GL-kontoer for valgt basis. Brukes til opprydding og drag/drop mot valgt kode.",
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).pack(anchor="w", fill="x", padx=8, pady=(8, 4))
        self.tree_unmapped = self._build_tree_tab(tab_unmapped, _UNMAPPED_COLUMNS)
        self.tree_unmapped.configure(height=5)
        ttk.Label(
            tab_mapping,
            textvariable=self.control_mapping_var,
            style="Muted.TLabel",
            wraplength=1180,
            justify="left",
        ).pack(anchor="w", fill="x", padx=8, pady=(8, 4))
        self.tree_mapping = self._build_tree_tab(tab_mapping, _MAPPING_COLUMNS)
        self.tree_mapping.configure(height=5)
        for detail_tab in (tab_history, tab_suggestions, tab_reconcile, tab_unmapped, tab_mapping):
            try:
                for child in detail_tab.winfo_children():
                    if isinstance(child, ttk.Label):
                        child.pack_forget()
            except Exception:
                pass

        control_support_nb.add(tab_history, text="Historikk")
        control_support_nb.add(tab_reconcile, text="Reconcile")
        control_support_nb.add(tab_unmapped, text="Umappede")
        control_support_nb.add(tab_mapping, text="Mapping")
        control_support_nb.add(tab_suggestions, text="Forslag+")
        self.control_support_nb = control_support_nb
        self.control_support_nb.bind("<<NotebookTabChanged>>", lambda _event: self._on_support_tab_changed(), add="+")

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
        self.tree_groups.bind("<<TreeviewSelect>>", lambda _event: self._on_group_selection_changed())
        self.tree_groups.bind("<Double-1>", lambda _event: self._focus_selected_group_code())
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
        try:
            self.after_idle(self._stabilize_control_layout)
        except Exception:
            pass

        ttk.Label(
            self,
            textvariable=self.status_var,
            style="Muted.TLabel",
            anchor="w",
            justify="left",
            padding=(10, 0, 10, 8),
        ).pack(fill="x")

    def _stabilize_control_layout(self) -> None:
        panes = getattr(self, "control_vertical_panes", None)
        if panes is None:
            return
        try:
            total_height = int(panes.winfo_height() or 0)
        except Exception:
            total_height = 0
        if total_height <= 0:
            return
        target = max(360, total_height - 280)
        try:
            panes.sashpos(0, target)
        except Exception:
            pass

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
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._pending_focus_code = code_s
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
            self._schedule_a07_refresh(
                delay_ms=1,
                on_complete=lambda code=code_s: self._focus_control_code(code),
            )
            return
        if code_s not in children:
            return
        if not self._set_tree_selection(self.tree_a07, code_s):
            return
        try:
            if code_s in self.tree_groups.get_children():
                self._set_tree_selection(self.tree_groups, code_s)
        except Exception:
            pass
        try:
            self.after_idle(self._on_control_selection_changed)
        except Exception:
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
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            selector(self.tree_control_accounts, konto_s)
            return
        try:
            self.tree_control_accounts.selection_set(konto_s)
            self.tree_control_accounts.focus(konto_s)
            self.tree_control_accounts.see(konto_s)
        except Exception:
            pass

    def _focus_selected_control_account_in_gl(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_accounts", None)):
            return
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
        self._set_tree_selection(self.tree_unmapped, konto_s)

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
                self._set_tree_selection(self.tree_control_gl, account)
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
        selector = getattr(self, "_set_tree_selection", None)
        if callable(selector):
            selector(self.tree_a07, code)
        else:
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
        conflicts = A07Page._locked_mapping_conflicts(self, [konto], target_code=kode)
        if A07Page._notify_locked_conflicts(self, conflicts, focus_widget=self.tree_a07):
            return
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
        conflicts = A07Page._locked_mapping_conflicts(self, accounts, target_code=code)
        if A07Page._notify_locked_conflicts(self, conflicts, focus_widget=self.tree_a07):
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
        conflicts = A07Page._locked_mapping_conflicts(self, accounts)
        if A07Page._notify_locked_conflicts(self, conflicts, focus_widget=self.tree_control_gl):
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
            conflicts = A07Page._locked_mapping_conflicts(self, accounts, target_code=code)
            if A07Page._notify_locked_conflicts(self, conflicts, focus_widget=self.tree_a07):
                return
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
            support_nb = getattr(self, "control_support_nb", None)
            if support_nb is not None:
                current_tab = support_nb.nametowidget(support_nb.select())
            else:
                current_tab = None
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
        self._support_requested = self._control_details_visible
        self._diag(f"set_control_details_visible visible={self._control_details_visible}")
        detail_panes = getattr(self, "control_detail_panes", None)
        support_nb = getattr(self, "control_support_nb", None)
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
        if support_nb is not None:
            try:
                if self._control_details_visible:
                    if not support_nb.winfo_manager():
                        support_nb.pack(fill="both", expand=True, pady=(4, 0))
                else:
                    if support_nb.winfo_manager():
                        support_nb.pack_forget()
            except Exception:
                pass
        if self._control_details_visible:
            try:
                if self._support_views_ready:
                    self.after_idle(lambda: self._refresh_control_support_trees())
                    self.after_idle(lambda: self._render_active_support_tab(force=True))
                else:
                    self._schedule_support_refresh()
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
        effective_mapping = self._effective_mapping()
        has_mapped_account = any(str(effective_mapping.get(account) or "").strip() for account in accounts)

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

    def _selected_basis(self) -> str:
        try:
            label = str(self.basis_widget.get() or "").strip()
        except Exception:
            label = ""

        for key, value in _BASIS_LABELS.items():
            if value == label:
                return key

        fallback = str(self.basis_var.get() or "").strip()
        return fallback if fallback in _BASIS_LABELS else "Endring"

    def _selected_control_codes(self) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        try:
            selection = self.tree_a07.selection()
        except Exception:
            selection = ()
        for item in selection or ():
            code = str(item or "").strip()
            if not code or code in seen:
                continue
            out.append(code)
            seen.add(code)
        return out

    def _selected_group_id(self) -> str | None:
        try:
            selection = self.tree_groups.selection()
        except Exception:
            selection = ()
        if not selection:
            return None
        group_id = str(selection[0] or "").strip()
        return group_id or None

    def _next_group_id(self, codes: Sequence[str]) -> str:
        code_tokens = [str(code).strip() for code in codes if str(code).strip()]
        slug = "+".join(code_tokens[:4]) or "group"
        base = f"A07_GROUP:{slug}"
        if base not in self.workspace.groups:
            return base
        idx = 2
        while f"{base}:{idx}" in self.workspace.groups:
            idx += 1
        return f"{base}:{idx}"

    def _effective_mapping(self) -> dict[str, str]:
        return apply_groups_to_mapping(self.workspace.mapping, self.workspace.membership)

    def _effective_previous_mapping(self) -> dict[str, str]:
        return apply_groups_to_mapping(self.previous_mapping, self.workspace.membership)

    def _locked_codes(self) -> set[str]:
        workspace = getattr(self, "workspace", None)
        locked = getattr(workspace, "locks", None)
        if not locked:
            return set()
        return {str(code).strip() for code in locked if str(code).strip()}

    def _locked_mapping_conflicts(
        self,
        accounts: Sequence[object] | None = None,
        *,
        target_code: object | None = None,
    ) -> list[str]:
        locked = A07Page._locked_codes(self)
        if not locked:
            return []

        workspace = getattr(self, "workspace", None)
        mapping = getattr(workspace, "mapping", None) or {}
        membership = getattr(workspace, "membership", None) or {}
        try:
            effective_mapping = A07Page._effective_mapping(self)
        except Exception:
            effective_mapping = {
                str(account).strip(): str(code).strip()
                for account, code in mapping.items()
                if str(account).strip()
            }
        conflicts: list[str] = []

        target_code_s = str(target_code or "").strip()
        if target_code_s and target_code_s in locked:
            conflicts.append(target_code_s)
        target_group_code = str(membership.get(target_code_s) or "").strip()
        if target_group_code and target_group_code in locked and target_group_code not in conflicts:
            conflicts.append(target_group_code)

        for account in accounts or ():
            account_s = str(account or "").strip()
            if not account_s:
                continue
            current_code = str(effective_mapping.get(account_s) or mapping.get(account_s) or "").strip()
            if current_code and current_code in locked and current_code not in conflicts:
                conflicts.append(current_code)

        return conflicts

    def _notify_locked_conflicts(
        self,
        conflicts: Sequence[object],
        *,
        focus_widget: object | None = None,
    ) -> bool:
        codes = [str(code).strip() for code in conflicts if str(code).strip()]
        if not codes:
            return False
        preview = ", ".join(codes[:3])
        if len(codes) > 3:
            preview += ", ..."
        self._notify_inline(
            f"Endringen berorer laaste koder: {preview}. Laas opp for du endrer mapping.",
            focus_widget=focus_widget,
        )
        return True

    def _notify_inline(self, message: str, *, focus_widget: object | None = None) -> None:
        self.status_var.set(str(message or "").strip())
        if focus_widget is None:
            return
        try:
            focus_widget.focus_set()
        except Exception:
            return

    def _control_gl_filter_state(self) -> tuple[str, bool, bool]:
        try:
            search_text = str(self.control_gl_filter_var.get() or "")
        except Exception:
            search_text = ""
        try:
            only_unmapped = bool(self.control_gl_unmapped_only_var.get())
        except Exception:
            only_unmapped = False
        try:
            active_only = bool(self.control_gl_active_only_var.get())
        except Exception:
            active_only = False
        return search_text, only_unmapped, active_only

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
        self._fill_tree(
            self.tree_a07,
            filtered,
            _CONTROL_COLUMNS,
            iid_column="Kode",
            row_tag_fn=lambda row: control_tree_tag(row.get("Arbeidsstatus")),
        )

        children = self.tree_a07.get_children()
        if not children:
            return

        target = selected_code if selected_code and selected_code in children else children[0]
        self._set_tree_selection(self.tree_a07, target)

    def _refresh_a07_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
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

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_a07.get_children()
                if children:
                    target = selected_code if selected_code and selected_code in children else children[0]
                    self._set_tree_selection(self.tree_a07, target)
            if on_complete is not None:
                on_complete()

        if filtered is None or len(filtered.index) <= 500:
            self._fill_tree(
                self.tree_a07,
                filtered,
                _CONTROL_COLUMNS,
                iid_column="Kode",
                row_tag_fn=lambda row: control_tree_tag(row.get("Arbeidsstatus")),
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_a07,
            filtered,
            _CONTROL_COLUMNS,
            iid_column="Kode",
            row_tag_fn=lambda row: control_tree_tag(row.get("Arbeidsstatus")),
            on_complete=_after_fill,
        )

    def _refresh_control_gl_tree(self) -> None:
        selected_account = self._selected_control_gl_account()
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
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
        self._set_tree_selection(self.tree_control_gl, target)

    def _refresh_control_gl_tree_chunked(self, *, on_complete: Callable[[], None] | None = None) -> None:
        selected_account = self._selected_control_gl_account()
        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )

        def _after_fill() -> None:
            if not bool(getattr(self, "_refresh_in_progress", False)):
                children = self.tree_control_gl.get_children()
                if children:
                    target = selected_account if selected_account and selected_account in children else children[0]
                    self._set_tree_selection(self.tree_control_gl, target)
            if on_complete is not None:
                on_complete()

        if filtered_gl_df is None or len(filtered_gl_df.index) <= 1200:
            self._fill_tree(
                self.tree_control_gl,
                filtered_gl_df,
                _CONTROL_GL_COLUMNS,
                iid_column="Konto",
                row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
            )
            _after_fill()
            return

        self._fill_tree_chunked(
            self.tree_control_gl,
            filtered_gl_df,
            _CONTROL_GL_COLUMNS,
            iid_column="Konto",
            row_tag_fn=lambda row: control_gl_tree_tag(row, selected_code, suggested_accounts),
            on_complete=_after_fill,
        )

    def _retag_control_gl_tree(self) -> bool:
        try:
            tree = self.tree_control_gl
            children = tuple(tree.get_children())
        except Exception:
            return False
        if not children:
            return False

        search_text, only_unmapped, active_only = self._control_gl_filter_state()
        filtered_gl_df = filter_control_gl_df(
            self.control_gl_df,
            search_text=search_text,
            only_unmapped=only_unmapped,
            active_only=active_only,
        )
        if filtered_gl_df is None or filtered_gl_df.empty:
            return False

        try:
            filtered_iids = [
                str(row.get("Konto") or "").strip()
                for _, row in filtered_gl_df.iterrows()
                if str(row.get("Konto") or "").strip()
            ]
            if tuple(filtered_iids) != children:
                return False
        except Exception:
            return False

        selected_code = self._selected_code_from_tree(self.tree_a07)
        suggested_accounts = self._selected_control_suggestion_accounts()
        try:
            for _, row in filtered_gl_df.iterrows():
                iid = str(row.get("Konto") or "").strip()
                if not iid:
                    continue
                tag = control_gl_tree_tag(row, selected_code, suggested_accounts)
                tree.item(iid, tags=((str(tag),) if tag else ()))
        except Exception:
            return False
        return True

    def _on_control_gl_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._schedule_control_gl_refresh()
        self._update_control_transfer_buttons()

    def _on_control_code_filter_changed(self) -> None:
        if bool(getattr(self, "_refresh_in_progress", False)):
            return
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)

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
        self._set_tree_selection(self.tree_suggestions, target)

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
            self._set_tree_selection(self.tree_control_suggestions, target)
        selected_row = self._selected_suggestion_row_from_tree(self.tree_control_suggestions)
        self.control_suggestion_summary_var.set(
            build_control_suggestion_summary(selected_code, control_suggestions, selected_row)
        )
        self.control_suggestion_effect_var.set(
            build_control_suggestion_effect_summary(
                selected_code,
                accounts_for_code(self._effective_mapping(), selected_code),
                selected_row,
            )
        )

        if self.control_gl_df is not None and not self.control_gl_df.empty and selected_code:
            selected_accounts = self.control_gl_df.loc[
                self.control_gl_df["Kode"].astype(str).str.strip() == str(selected_code).strip()
            ].copy()
            if selected_accounts.empty:
                self.control_selected_accounts_df = pd.DataFrame(
                    columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                )
            else:
                self.control_selected_accounts_df = selected_accounts[
                    [c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS]
                ].reset_index(drop=True)
        else:
            self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.control_accounts_summary_var.set(
            build_control_accounts_summary(
                self.control_selected_accounts_df,
                selected_code,
                basis_col=self.workspace.basis_col,
            )
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
            self._set_tree_selection(self.tree_control_accounts, target_account)

    def _active_support_tab_key(self) -> str | None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return None
        notebook = getattr(self, "control_support_nb", None)
        if notebook is None:
            return None
        try:
            current_tab = notebook.nametowidget(notebook.select())
        except Exception:
            return None
        if current_tab is self.tab_history:
            return "history"
        if current_tab is self.tab_reconcile:
            return "reconcile"
        if current_tab is self.tab_unmapped:
            return "unmapped"
        if current_tab is self.tab_mapping:
            return "mapping"
        if current_tab is self.tab_suggestions:
            return "suggestions"
        return None

    def _render_active_support_tab(self, *, force: bool = False) -> None:
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        tab_key = self._active_support_tab_key()
        if not tab_key:
            return
        if not force and tab_key in self._loaded_support_tabs:
            return
        def _mark_loaded(current_key: str = tab_key) -> None:
            self._loaded_support_tabs.add(current_key)
        if tab_key == "history":
            self._fill_tree_chunked(
                self.tree_history,
                self.history_compare_df,
                _HISTORY_COLUMNS,
                iid_column="Kode",
                on_complete=lambda: (_mark_loaded(), self._update_history_details_from_selection()),
            )
            return
        elif tab_key == "reconcile":
            self._fill_tree_chunked(
                self.tree_reconcile,
                self.reconcile_df,
                _RECONCILE_COLUMNS,
                row_tag_fn=reconcile_tree_tag,
                on_complete=_mark_loaded,
            )
            return
        elif tab_key == "unmapped":
            self._fill_tree_chunked(
                self.tree_unmapped,
                self.unmapped_df,
                _UNMAPPED_COLUMNS,
                iid_column="Konto",
                on_complete=_mark_loaded,
            )
            return
        elif tab_key == "mapping":
            self._fill_tree_chunked(
                self.tree_mapping,
                self.mapping_df,
                _MAPPING_COLUMNS,
                iid_column="Konto",
                on_complete=_mark_loaded,
            )
            return
        elif tab_key == "suggestions":
            self._refresh_suggestions_tree()
            _mark_loaded()
            return
        self._loaded_support_tabs.add(tab_key)

    def _update_history_details(self, code: str | None) -> None:
        self.history_details_var.set(
            build_mapping_history_details(
                code,
                mapping_current=self._effective_mapping(),
                mapping_previous=self._effective_previous_mapping(),
                previous_year=self.previous_mapping_year,
            )
        )

    def _update_history_details_from_selection(self) -> None:
        if bool(getattr(self, "_suspend_selection_sync", False)):
            return
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
            self.control_summary_var.set("Slik jobber du")
            self.control_meta_var.set("1. Velg konto og kode")
            self.control_match_var.set("2. Trykk -> eller dra konto til valgt kode")
            self.control_mapping_var.set("")
            self.control_history_var.set("")
            self.control_best_var.set("")
            self.control_next_var.set("Velg kode for aa starte.")
            self.control_drag_var.set("Vis detaljer bare ved behov for forslag og mappede kontoer.")
            self.control_suggestion_effect_var.set("Velg forslag for aa se effekt.")
            try:
                self.control_panel.configure(text="Oppsummering")
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
        current_accounts = accounts_for_code(self._effective_mapping(), code)
        history_accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        best_row = best_suggestion_row_for_code(
            self.workspace.suggestions,
            code,
            locked_codes=A07Page._locked_codes(self),
        )

        def _compact_accounts(values: Sequence[object]) -> str:
            tokens = [str(value).strip() for value in values if str(value).strip()]
            if not tokens:
                return "ingen"
            if len(tokens) <= 3:
                return ", ".join(tokens)
            return ", ".join(tokens[:3]) + ", ..."

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
        # Build one compact meta line: status, amount, GL diff
        meta_parts = [work_label, f"Basis {self.workspace.basis_col}", f"A07 {belop or '-'}"]
        if reconcile_row is not None:
            gl_belop = self._format_value(reconcile_row.get("GL_Belop"), "GL_Belop")
            diff_belop = self._format_value(reconcile_row.get("Diff"), "Diff")
            meta_parts.append(f"GL {gl_belop or '-'}")
            meta_parts.append(f"Diff {diff_belop or '-'}")
            antall = self._format_value(reconcile_row.get("AntallKontoer"), "AntallKontoer")
            meta_parts.append(f"Kontoer {antall or '-'}")
        if code in A07Page._locked_codes(self):
            meta_parts.append("Låst")
        compact_next = compact_control_next_action(next_action)
        if compact_next.casefold() != work_label.casefold():
            meta_parts.append(f"Neste {compact_next}")
        self.control_meta_var.set(" | ".join(meta_parts))
        mapping_text = _compact_accounts(current_accounts)
        history_text = _compact_accounts(history_accounts)
        info_parts = [f"Mapping {mapping_text}"]
        if history_text != "ingen":
            info_parts.append(f"Historikk {history_text}")
        self.control_match_var.set(" | ".join(info_parts))
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
            self.control_panel.configure(text=f"Aktiv kode: {code}")
            if best_row is not None and bool(best_row.get("WithinTolerance", False)):
                self.btn_control_best.state(["!disabled"])
            else:
                self.btn_control_best.state(["disabled"])
            if history_accounts:
                self.btn_control_history.state(["!disabled"])
            else:
                self.btn_control_history.state(["disabled"])
            if not self._current_drag_accounts():
                self.control_drag_var.set(f"Dra konto fra venstre til {code}, eller bruk ->.")
                self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        self._update_control_transfer_buttons()

    def _on_control_selection_changed(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)) or (
            callable(suppressed_check) and suppressed_check(getattr(self, "tree_a07", None))
        ):
            return
        self._diag(
            f"control_selection_changed code={self._selected_control_code()!r} "
            f"refresh_in_progress={self._refresh_in_progress} details_visible={getattr(self, '_control_details_visible', False)}"
        )
        if bool(getattr(self, "_skip_initial_control_followup", False)):
            self.workspace.selected_code = self._selected_control_code()
            self._update_history_details_from_selection()
            self._update_control_panel()
            self._update_control_transfer_buttons()
            return
        self.workspace.selected_code = self._selected_control_code()
        self._update_history_details_from_selection()
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._update_control_panel()
            self._update_control_transfer_buttons()
            return
        schedule_followup = getattr(self, "_schedule_control_selection_followup", None)
        if callable(schedule_followup):
            self._update_control_panel()
            self._update_control_transfer_buttons()
            schedule_followup()
            return
        if self._support_views_ready and self._active_support_tab_key() == "suggestions":
            self._refresh_suggestions_tree()
        if bool(getattr(self, "_control_details_visible", False)):
            self._refresh_control_support_trees()
        if bool(getattr(self, "_control_details_visible", False)) and not self._retag_control_gl_tree():
            self._refresh_control_gl_tree()
        self._update_control_panel()
        self._update_control_transfer_buttons()

    def _on_support_tab_changed(self) -> None:
        self._diag(
            f"support_tab_changed details_visible={getattr(self, '_control_details_visible', False)} "
            f"ready={self._support_views_ready} active={self._active_support_tab_key()!r}"
        )
        if not bool(getattr(self, "_control_details_visible", False)):
            return
        self._support_requested = True
        if self._support_views_ready:
            self._render_active_support_tab()
            return
        self._schedule_support_refresh()

    def _selected_control_code(self) -> str | None:
        return self._selected_code_from_tree(self.tree_a07)

    def _tree_selection_key(self, tree: ttk.Treeview | None) -> str:
        try:
            return str(tree) if tree is not None else ""
        except Exception:
            return ""

    def _release_tree_selection_suppression(self, tree: ttk.Treeview | None) -> None:
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.discard(key)

    def _is_tree_selection_suppressed(self, tree: ttk.Treeview | None) -> bool:
        key = self._tree_selection_key(tree)
        return bool(key) and key in self._suppressed_tree_select_keys

    def _set_tree_selection(self, tree: ttk.Treeview, target: str | None) -> bool:
        target_s = str(target or "").strip()
        if not target_s:
            return False
        key = self._tree_selection_key(tree)
        if key:
            self._suppressed_tree_select_keys.add(key)
        previous = bool(getattr(self, "_suspend_selection_sync", False))
        self._suspend_selection_sync = True
        try:
            tree.selection_set(target_s)
            tree.focus(target_s)
            tree.see(target_s)
            try:
                self.after_idle(lambda t=tree: self._release_tree_selection_suppression(t))
            except Exception:
                self._release_tree_selection_suppression(tree)
            return True
        except Exception:
            self._release_tree_selection_suppression(tree)
            return False
        finally:
            self._suspend_selection_sync = previous

    def _on_control_gl_selection_changed(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)) or (
            callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_gl", None))
        ):
            self._update_control_transfer_buttons()
            return
        account = self._selected_control_gl_account()
        if not account or self.control_gl_df is None or self.control_gl_df.empty:
            self._update_control_transfer_buttons()
            return
        if bool(getattr(self, "_refresh_in_progress", False)):
            self._sync_control_account_selection(account)
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
                self._schedule_a07_refresh(
                    delay_ms=1,
                    on_complete=lambda selected_code=code: self._focus_control_code(selected_code),
                )
                return
            if code in self.tree_a07.get_children():
                if code != self._selected_code_from_tree(self.tree_a07):
                    if self._set_tree_selection(self.tree_a07, code):
                        try:
                            self.after_idle(self._on_control_selection_changed)
                        except Exception:
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
        if code in A07Page._locked_codes(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
            return
        best_row = best_suggestion_row_for_code(
            self.workspace.suggestions,
            code,
            locked_codes=A07Page._locked_codes(self),
        )
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
        if code in A07Page._locked_codes(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_a07)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
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
        if code in A07Page._locked_codes(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker automatikk.", focus_widget=self.tree_a07)
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
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
            gl_df=self.workspace.gl_df,
        )
        if history_accounts:
            self._apply_history_for_selected_code()
            return

        best_row = best_suggestion_row_for_code(
            self.workspace.suggestions,
            code,
            locked_codes=A07Page._locked_codes(self),
        )
        if best_row is not None and bool(best_row.get("WithinTolerance", False)):
            self._apply_best_suggestion_for_selected_code()
            return

        try:
            self.entry_control_gl_filter.focus_set()
        except Exception:
            pass
        self.status_var.set(
            f"Ingen trygg automatikk for {code}. Velg konto(er) til venstre og bruk ->, eller bruk Avansert mapping under Mer."
        )

    def _on_suggestion_selected(self) -> None:
        suppressed_check = getattr(self, "_is_tree_selection_suppressed", None)
        if bool(getattr(self, "_suspend_selection_sync", False)):
            return
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_control_suggestions", None)):
            return
        if callable(suppressed_check) and suppressed_check(getattr(self, "tree_suggestions", None)):
            return
        self._update_selected_suggestion_details()
        if not self._retag_control_gl_tree():
            self._schedule_control_gl_refresh()
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
                    accounts_for_code(self._effective_mapping(), selected_code),
                    selected_row,
                )
            )
        self._update_history_details_from_selection()

    def _on_a07_filter_changed(self) -> None:
        self.a07_filter_var.set(self._selected_a07_filter())
        self._schedule_a07_refresh(on_complete=self._on_control_selection_changed)

    def _select_primary_tab(self) -> None:
        """No-op: arbeidsflaten bruker ikke interne tabs som kan byttes."""
        pass

    def _restore_context_state(self, client: str | None, year: str | None) -> None:
        self._refresh_in_progress = True
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        cancel_job = getattr(self, "_cancel_scheduled_job", None)
        if callable(cancel_job):
            cancel_job("_session_refresh_job")
        self._cancel_core_refresh_jobs()
        self._cancel_support_refresh()
        self._support_views_ready = False
        self._support_views_dirty = True
        self._loaded_support_tabs.clear()
        self.workspace.a07_df = _empty_a07_df()
        self.workspace.source_a07_df = _empty_a07_df()
        self.a07_overview_df = _empty_a07_df()
        self.control_df = _empty_control_df()
        self.control_gl_df = pd.DataFrame(columns=list(_CONTROL_GL_DATA_COLUMNS))
        self.control_selected_accounts_df = pd.DataFrame(columns=[c[0] for c in _CONTROL_SELECTED_ACCOUNT_COLUMNS])
        self.groups_df = _empty_groups_df()
        self.workspace.mapping = {}
        self.workspace.groups = {}
        self.workspace.locks = set()
        self.workspace.membership = {}
        self.workspace.project_meta = {}
        self.workspace.suggestions = _empty_suggestions_df()
        self.reconcile_df = _empty_reconcile_df()
        self.mapping_df = _empty_mapping_df()
        self.unmapped_df = _empty_unmapped_df()
        self.history_compare_df = _empty_history_df()
        self.a07_path = None
        self.mapping_path = None
        self.groups_path = None
        self.locks_path = None
        self.project_path = None
        self.rulebook_path = resolve_rulebook_path(client, year)
        self.previous_mapping = {}
        self.previous_mapping_path = None
        self.previous_mapping_year = None
        self.history_details_var.set("Velg en kode for aa se historikk.")
        self.control_summary_var.set("Velg kode i hoyre liste.")
        self.control_intro_var.set("Velg kode i høyre liste.")
        self.control_meta_var.set("")
        self.control_match_var.set("")
        self.control_mapping_var.set("")
        self.control_history_var.set("")
        self.control_best_var.set("")
        self.control_suggestion_summary_var.set("Velg kode i hoyre liste for aa se forslag.")
        self.control_suggestion_effect_var.set("")
        self.control_next_var.set("")
        self.control_drag_var.set("")
        self.control_bucket_var.set("Ferdig 0 | Vurdering 0 | Manuell 0")
        self.control_code_filter_var.set("")
        self._control_details_auto_revealed = False
        try:
            self._set_control_details_visible(False)
        except Exception:
            pass
        try:
            self.control_panel.configure(text="Oppsummering")
            self.lbl_control_drag.configure(style="Muted.TLabel")
        except Exception:
            pass
        self.a07_filter_var.set("neste")
        self.a07_filter_label_var.set(_CONTROL_VIEW_LABELS["neste"])
        self.basis_var.set(_BASIS_LABELS["Endring"])
        self.workspace.basis_col = "Endring"
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
        self._fill_tree(self.tree_control_gl, self.control_gl_df, _CONTROL_GL_COLUMNS)
        self._fill_tree(self.tree_a07, self.a07_overview_df, _A07_COLUMNS, iid_column="regnr")
        self._fill_tree(self.tree_groups, self.groups_df, _GROUP_COLUMNS, iid_column="group_id")
        for tab_key in tuple(self._loaded_support_tabs):
            if tab_key == "history":
                self._fill_tree(self.tree_history, _empty_history_df(), _HISTORY_COLUMNS, iid_column="Kode")
            elif tab_key == "reconcile":
                self._fill_tree(self.tree_reconcile, _empty_reconcile_df(), _RECONCILE_COLUMNS)
            elif tab_key == "unmapped":
                self._fill_tree(self.tree_unmapped, _empty_unmapped_df(), _UNMAPPED_COLUMNS, iid_column="Konto")
            elif tab_key == "mapping":
                self._fill_tree(self.tree_mapping, _empty_mapping_df(), _MAPPING_COLUMNS, iid_column="Konto")
            elif tab_key == "suggestions":
                self._fill_tree(self.tree_suggestions, _empty_suggestions_df(), _SUGGESTION_COLUMNS)
        self._update_selected_suggestion_details()
        self._update_control_panel()
        self._update_control_transfer_buttons()
        self._update_summary()

        self._context_snapshot = get_context_snapshot(client, year)
        self._start_context_restore(client, year)

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

    def _current_project_state(self) -> dict[str, object]:
        return {
            "basis_col": self.workspace.basis_col,
            "selected_code": self._selected_control_code(),
            "selected_group": self._selected_group_id(),
        }

    def _autosave_workspace_state(self) -> bool:
        client, year = self._session_context(session)
        client_s = _clean_context_value(client)
        year_s = _clean_context_value(year)
        if not client_s or not year_s:
            return False

        self.groups_path = default_a07_groups_path(client_s, year_s)
        self.locks_path = default_a07_locks_path(client_s, year_s)
        self.project_path = default_a07_project_path(client_s, year_s)
        save_a07_groups(self.workspace.groups, self.groups_path)
        save_locks(self.locks_path, self.workspace.locks)
        save_project_state(self.project_path, self._current_project_state())
        self._context_snapshot = get_context_snapshot(client_s, year_s)
        return True

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
        self._autosave_workspace_state()
        self._context_snapshot = get_context_snapshot(client, year)
        return True

    def _context_has_changed(self) -> bool:
        context = self._session_context(session)
        snapshot = get_context_snapshot(*context)
        return context != self._context_key or snapshot != self._context_snapshot

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
            self._context_snapshot = get_context_snapshot(client, year)
            self.workspace.source_a07_df = parse_a07_json(stored_path)
            self.workspace.a07_df = self.workspace.source_a07_df.copy()
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
            if client and year:
                try:
                    self.groups_path = default_a07_groups_path(client, year)
                    self.workspace.groups = load_a07_groups(self.groups_path)
                except Exception:
                    self.workspace.groups = {}
                try:
                    self.locks_path = default_a07_locks_path(client, year)
                    self.workspace.locks = load_locks(self.locks_path)
                except Exception:
                    self.workspace.locks = set()
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
            self._autosave_workspace_state()
            self.status_var.set(f"Lagret mapping til {self.mapping_path.name}.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke lagre mapping:\n{exc}")

    def _on_basis_changed(self) -> None:
        basis = self._selected_basis()
        if basis == self.workspace.basis_col:
            return
        self.workspace.basis_col = basis
        self._refresh_all()
        self._autosave_workspace_state()
        self.status_var.set(f"A07 bruker nå basis {basis}.")

    def _create_group_from_selection(self) -> None:
        codes = [code for code in self._selected_control_codes() if code and not code.startswith("A07_GROUP:")]
        if len(codes) < 2:
            self._notify_inline("Marker minst to A07-koder for å opprette en gruppe.", focus_widget=self.tree_a07)
            return

        default_name = " + ".join(codes[:3]) + (" ..." if len(codes) > 3 else "")
        name = simpledialog.askstring("A07-gruppe", "Navn på gruppen:", parent=self, initialvalue=default_name)
        if name is None:
            return

        group_id = self._next_group_id(codes)
        self.workspace.groups[group_id] = A07Group(
            group_id=group_id,
            group_name=str(name).strip() or default_name,
            member_codes=list(dict.fromkeys(codes)),
        )
        self._autosave_workspace_state()
        self._refresh_all()
        self._focus_control_code(group_id)
        self.status_var.set(f"Opprettet A07-gruppe {group_id}.")

    def _remove_selected_group(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            self._notify_inline("Velg en A07-gruppe først.", focus_widget=self.tree_groups)
            return
        in_use = [
            str(account).strip()
            for account, code in (self.workspace.mapping or {}).items()
            if str(code or "").strip() == group_id and str(account).strip()
        ]
        if in_use:
            account_label = "konto" if len(in_use) == 1 else "kontoer"
            self._notify_inline(
                f"Kan ikke oppløse gruppe som fortsatt brukes i mapping ({len(in_use)} {account_label}). Fjern eller flytt mapping først.",
                focus_widget=self.tree_groups,
            )
            self._focus_control_code(group_id)
            return
        self.workspace.groups.pop(group_id, None)
        self.workspace.locks.discard(group_id)
        self._autosave_workspace_state()
        self._refresh_all()
        self.status_var.set(f"Oppløste A07-gruppe {group_id}.")

    def _on_group_selection_changed(self) -> None:
        self._focus_selected_group_code()

    def _focus_selected_group_code(self) -> None:
        group_id = self._selected_group_id()
        if not group_id:
            return
        self._focus_control_code(group_id)

    def _lock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe å låse først.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.add(code)
        self._autosave_workspace_state()
        self._refresh_all()
        self._focus_control_code(code)
        self.status_var.set(f"Låste {code}.")

    def _unlock_selected_code(self) -> None:
        code = self._selected_control_code()
        if not code:
            self._notify_inline("Velg en kode eller gruppe å låse opp først.", focus_widget=self.tree_a07)
            return
        self.workspace.locks.discard(code)
        self._autosave_workspace_state()
        self._refresh_all()
        self._focus_control_code(code)
        self.status_var.set(f"Låste opp {code}.")

    def _export_clicked(self) -> None:
        if self.workspace.a07_df.empty or self.workspace.gl_df.empty:
            self._notify_inline(
                "Last A07 og bruk aktiv saldobalanse for valgt klient/aar for du eksporterer.",
                focus_widget=self,
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
            self._pending_focus_code = str(selected_code or "").strip() or None
            self._refresh_all()
            self.status_var.set("A07-kontroll og forslag er oppdatert.")
        except Exception as exc:
            messagebox.showerror("A07", f"Kunne ikke oppdatere A07-visningen:\n{exc}")

    def _apply_safe_history_mappings(self) -> tuple[int, int]:
        applied_codes = 0
        applied_accounts = 0
        effective_mapping = self._effective_mapping()
        effective_previous_mapping = self._effective_previous_mapping()
        codes = select_safe_history_codes(self.history_compare_df)
        for code in codes:
            if code in A07Page._locked_codes(self):
                continue
            accounts = safe_previous_accounts_for_code(
                code,
                mapping_current=effective_mapping,
                mapping_previous=effective_previous_mapping,
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
            self._effective_mapping(),
            min_score=0.85,
            locked_codes=A07Page._locked_codes(self),
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            code = str(row.get("Kode") or "").strip()
            if code in A07Page._locked_codes(self):
                continue
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
            self._effective_mapping(),
            unresolved_codes=unresolved_codes_list,
            locked_codes=A07Page._locked_codes(self),
        )
        for idx in row_indexes:
            row = self.workspace.suggestions.iloc[int(idx)]
            code = str(row.get("Kode") or "").strip()
            if code in A07Page._locked_codes(self):
                continue
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

        account_options = build_gl_picker_options(self.workspace.gl_df, basis_col=self.workspace.basis_col)
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
            if code in A07Page._locked_codes(self):
                self._notify_inline("Valgt kode er låst. Lås opp før du bruker forslag.", focus_widget=self.tree_a07)
                return
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
        if code in A07Page._locked_codes(self):
            self._notify_inline("Valgt kode er låst. Lås opp før du bruker historikk.", focus_widget=self.tree_history)
            return
        accounts = safe_previous_accounts_for_code(
            code,
            mapping_current=self._effective_mapping(),
            mapping_previous=self._effective_previous_mapping(),
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
            self._effective_mapping(),
            min_score=0.85,
            locked_codes=A07Page._locked_codes(self),
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
        conflicts = A07Page._locked_mapping_conflicts(self, selection)
        if A07Page._notify_locked_conflicts(self, conflicts, focus_widget=self.tree_mapping):
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
        if self._refresh_in_progress:
            self._pending_session_refresh = True
            return
        self._refresh_in_progress = True
        self._pending_session_refresh = False
        self._pending_support_refresh = False
        self._support_requested = False
        cancel_job = getattr(self, "_cancel_scheduled_job", None)
        if callable(cancel_job):
            cancel_job("_session_refresh_job")
        self._cancel_core_refresh_jobs()
        self._cancel_support_refresh()
        self._support_views_ready = False
        self._start_core_refresh()

    def _refresh_support_views(self) -> None:
        if (
            not bool(getattr(self, "_control_details_visible", False))
            or not bool(getattr(self, "_support_requested", True))
        ):
            self._pending_support_refresh = False
            return
        active_tab_getter = getattr(self, "_active_support_tab_key", None)
        loaded_tabs = getattr(self, "_loaded_support_tabs", set())
        if self._support_views_ready and not self._support_views_dirty:
            if not callable(active_tab_getter) or active_tab_getter() in loaded_tabs:
                self._render_active_support_tab()
            return
        if self._refresh_in_progress:
            self._pending_support_refresh = True
            return
        if self._support_refresh_thread is not None:
            return
        self._pending_support_refresh = False
        self._start_support_refresh()

    def _fill_tree(
        self,
        tree: ttk.Treeview,
        df: pd.DataFrame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        iid_column: str | None = None,
        row_tag_fn: Callable[[pd.Series], str | None] | None = None,
    ) -> None:
        start_ts = time.perf_counter()
        tree_name = self._tree_debug_name(tree)
        row_count = 0 if df is None else int(len(df.index))
        self._diag(f"fill_tree start tree={tree_name} rows={row_count}")
        children = tree.get_children()
        if children:
            tree.delete(*children)

        if df is None or df.empty:
            self._diag(
                f"fill_tree done tree={tree_name} rows=0 elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            return

        used_iids: set[str] = set()
        for idx, row in df.iterrows():
            values = [self._format_value(row.get(column_id), column_id) for column_id, *_rest in columns]
            iid = self._normalize_tree_iid(row, idx, iid_column, used_iids)
            tags: tuple[str, ...] = ()
            if row_tag_fn is not None:
                try:
                    tag = row_tag_fn(row)
                except Exception:
                    tag = None
                if tag:
                    tags = (str(tag),)
            self._insert_tree_row(tree, iid=iid, values=values, tags=tags)
        self._diag(
            f"fill_tree done tree={tree_name} rows={row_count} elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
        )

    def _tree_fill_key(self, tree: ttk.Treeview) -> str:
        try:
            return str(tree)
        except Exception:
            return f"tree-{id(tree)}"

    def _cancel_tree_fill(self, tree: ttk.Treeview) -> None:
        key = self._tree_fill_key(tree)
        job = self._tree_fill_jobs.pop(key, None)
        if job is None:
            return
        try:
            self.after_cancel(job)
        except Exception:
            pass

    def _normalize_tree_iid(
        self,
        row: pd.Series,
        idx: object,
        iid_column: str | None,
        used_iids: set[str],
    ) -> str:
        base_iid = str(idx)
        if iid_column:
            try:
                candidate = str(row.get(iid_column, "") or "").strip()
            except Exception:
                candidate = ""
            if candidate:
                base_iid = candidate

        iid = base_iid
        suffix = 2
        while iid in used_iids:
            iid = f"{base_iid}__{suffix}"
            suffix += 1
        used_iids.add(iid)
        return iid

    def _insert_tree_row(
        self,
        tree: ttk.Treeview,
        *,
        iid: str,
        values: Sequence[object],
        tags: tuple[str, ...],
    ) -> None:
        try:
            tree.insert("", "end", iid=iid, values=values, tags=tags)
        except Exception:
            try:
                tree.insert("", "end", values=values, tags=tags)
            except Exception:
                pass

    def _fill_tree_chunked(
        self,
        tree: ttk.Treeview,
        df: pd.DataFrame,
        columns: Sequence[tuple[str, str, int, str]],
        *,
        iid_column: str | None = None,
        row_tag_fn: Callable[[pd.Series], str | None] | None = None,
        on_complete: Callable[[], None] | None = None,
        batch_size: int = 60,
    ) -> None:
        start_ts = time.perf_counter()
        tree_name = self._tree_debug_name(tree)
        self._cancel_tree_fill(tree)
        key = self._tree_fill_key(tree)
        token = int(self._tree_fill_tokens.get(key, 0)) + 1
        self._tree_fill_tokens[key] = token

        children = tree.get_children()
        if children:
            tree.delete(*children)

        if df is None or df.empty:
            self._diag(
                f"fill_tree_chunked done tree={tree_name} rows=0 elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            if on_complete is not None:
                try:
                    self.after_idle(on_complete)
                except Exception:
                    on_complete()
            return

        total = len(df.index)
        self._diag(f"fill_tree_chunked start tree={tree_name} rows={total} batch_size={batch_size}")
        state = {"index": 0, "used_iids": set()}
        column_ids = [column_id for column_id, *_rest in columns]

        def _run_batch() -> None:
            if self._tree_fill_tokens.get(key) != token:
                self._tree_fill_jobs.pop(key, None)
                return
            start = int(state["index"])
            end = min(start + max(1, int(batch_size)), total)
            chunk = df.iloc[start:end]
            for idx, row in chunk.iterrows():
                values = [self._format_value(row.get(column_id), column_id) for column_id in column_ids]
                iid = self._normalize_tree_iid(row, idx, iid_column, state["used_iids"])
                tags: tuple[str, ...] = ()
                if row_tag_fn is not None:
                    try:
                        tag = row_tag_fn(row)
                    except Exception:
                        tag = None
                    if tag:
                        tags = (str(tag),)
                self._insert_tree_row(tree, iid=iid, values=values, tags=tags)
            state["index"] = end
            if end < total:
                self._tree_fill_jobs[key] = self.after(1, _run_batch)
                return
            self._tree_fill_jobs.pop(key, None)
            self._diag(
                f"fill_tree_chunked done tree={tree_name} rows={total} elapsed_ms={(time.perf_counter() - start_ts) * 1000:.1f}"
            )
            if on_complete is not None:
                try:
                    self.after_idle(on_complete)
                except Exception:
                    on_complete()

        try:
            self._tree_fill_jobs[key] = self.after_idle(_run_batch)
        except Exception:
            _run_batch()

    def _update_summary(self) -> None:
        client, year = self._session_context(session)
        ctx_parts = [x for x in (client, year) if x]
        context_text = " / ".join(ctx_parts) if ctx_parts else "ingen klientkontekst"

        suggestion_count = 0
        if bool(getattr(self, "_support_views_ready", False)) and self.workspace.suggestions is not None:
            suggestion_count = int(len(self.workspace.suggestions))
        unsolved_count = count_unsolved_a07_codes(self.a07_overview_df)
        self.summary_var.set(
            " | ".join(
                [
                    f"Kontekst {context_text}",
                    f"Koder {len(self.workspace.a07_df)}",
                    f"Uløste {unsolved_count}",
                    f"Umappede {len(self.unmapped_df)}",
                    f"Forslag {suggestion_count}",
                    f"Grupper {len(self.workspace.groups)}",
                    f"Låste {len(self.workspace.locks)}",
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
