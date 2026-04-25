from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

import app_paths

from . import A07Group
from .path_shared import (
    _GROUP_DATA_COLUMNS,
    _clean_context_value,
    _context_path_slug,
    _safe_exists,
    client_store,
)


def get_a07_workspace_dir(client: str | None, year: str | int | None) -> Path:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)

    if client_store is not None and client_s and year_s:
        try:
            return client_store.years_dir(client_s, year=str(year_s)) / "a07"
        except Exception:
            pass

    if client_s and year_s:
        try:
            return app_paths.data_dir() / "a07" / _context_path_slug(client_s) / _context_path_slug(year_s)
        except Exception:
            return Path("a07") / _context_path_slug(client_s) / _context_path_slug(year_s)

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

    return Path("a07_mapping.json")


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


def resolve_context_source_path(
    client: str | None,
    year: str | int | None,
) -> Path | None:
    if not _clean_context_value(client) or not _clean_context_value(year):
        return None

    default_path = default_a07_source_path(client, year)
    if _safe_exists(default_path):
        return default_path

    return None


def resolve_context_mapping_path(
    a07_path: str | Path | None,
    *,
    client: str | None,
    year: str | int | None,
) -> Path | None:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if not client_s or not year_s:
        return None

    default_path = suggest_default_mapping_path(a07_path, client=client, year=year)
    if _safe_exists(default_path):
        return default_path

    return default_path


def _group_amounts_from_control_df(
    control_df: pd.DataFrame | None,
    *,
    group_id: str,
    members: list[str],
) -> dict[str, object]:
    if control_df is None or control_df.empty or "Kode" not in control_df.columns:
        return {"A07_Belop": None, "GL_Belop": None, "Diff": None}

    work = control_df.copy()
    work["__code"] = work["Kode"].fillna("").astype(str).str.strip()
    group_match = work.loc[work["__code"] == str(group_id or "").strip()]
    if not group_match.empty:
        row = group_match.iloc[0]
        return {
            "A07_Belop": row.get("A07_Belop", row.get("Belop")),
            "GL_Belop": row.get("GL_Belop"),
            "Diff": row.get("Diff"),
        }

    member_set = {str(code or "").strip() for code in members if str(code or "").strip()}
    if not member_set:
        return {"A07_Belop": None, "GL_Belop": None, "Diff": None}

    member_rows = work.loc[work["__code"].isin(member_set)]
    if member_rows.empty:
        return {"A07_Belop": None, "GL_Belop": None, "Diff": None}

    def _sum(column: str, fallback: str | None = None) -> object:
        source = column if column in member_rows.columns else fallback
        if not source or source not in member_rows.columns:
            return None
        values = pd.to_numeric(member_rows[source], errors="coerce").dropna()
        return float(values.sum()) if not values.empty else None

    return {
        "A07_Belop": _sum("A07_Belop", "Belop"),
        "GL_Belop": _sum("GL_Belop"),
        "Diff": _sum("Diff"),
    }


def build_groups_df(
    groups: dict[str, A07Group],
    *,
    locked_codes: set[str] | None = None,
    control_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
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
                **_group_amounts_from_control_df(control_df, group_id=str(group_id), members=members),
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
