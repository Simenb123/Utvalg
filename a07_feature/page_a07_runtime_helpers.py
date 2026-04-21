from __future__ import annotations

import json
import shutil
from pathlib import Path

import classification_config
import classification_workspace
import pandas as pd

from account_profile_legacy_api import AccountProfileLegacyApi
from a07_feature import AccountUsageFeatures, build_account_usage_features
from a07_feature import mapping_source
from a07_feature.page_paths import (
    bundled_default_rulebook_path as _bundled_default_rulebook_path,
    find_previous_year_context as _find_previous_year_context,
    find_previous_year_mapping_path as _find_previous_year_mapping_path,
    load_previous_year_mapping_for_context as _load_previous_year_mapping_for_context,
)
from a07_feature.suggest.models import EXCLUDED_A07_CODES

from . import page_a07_env as _env
from .payroll import profile_state as _payroll_profile_state


def _account_profile_api_for_a07() -> AccountProfileLegacyApi:
    return _payroll_profile_state._account_profile_api_for_a07(
        app_paths_module=_env.app_paths,
        classification_config_module=classification_config,
        account_profile_api_cls=AccountProfileLegacyApi,
    )


def _clean_context_value(value: object) -> str | None:
    return _payroll_profile_state._clean_context_value(value)


def _load_code_profile_state(
    client: str | None,
    year: str | int | None,
    mapping_current: dict[str, str] | None,
    gl_df: pd.DataFrame | None = None,
) -> dict[str, dict[str, object]]:
    return _payroll_profile_state._load_code_profile_state(
        client,
        year,
        mapping_current,
        gl_df=gl_df,
        account_profile_api_loader=_account_profile_api_for_a07,
        clean_context_value=_clean_context_value,
        konto_klassifisering_module=_env.konto_klassifisering,
    )


def _path_name(value: str | Path | None, *, empty: str = "ikke valgt") -> str:
    if not value:
        return empty
    try:
        return Path(str(value)).name or str(value)
    except Exception:
        return str(value)


def _build_usage_features_for_a07(df: object) -> dict[str, AccountUsageFeatures]:
    if isinstance(df, pd.DataFrame) and not df.empty:
        try:
            return build_account_usage_features(df)
        except Exception:
            return {}
    return {}


def _safe_exists(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        return path.exists()
    except Exception:
        return False


def _rulebook_has_rules(path: Path | None) -> bool:
    if not _safe_exists(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return False
    if not isinstance(data, dict):
        return False
    rules = data.get("rules", {})
    return isinstance(rules, dict) and bool(rules)


def default_global_rulebook_path() -> Path:
    try:
        return _env.app_paths.data_dir() / "a07" / "global_full_a07_rulebook.json"
    except Exception:
        return Path("a07") / "global_full_a07_rulebook.json"


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


def bundled_default_rulebook_path() -> Path | None:
    return _bundled_default_rulebook_path()


def ensure_default_rulebook_exists() -> Path | None:
    target = default_global_rulebook_path()
    if _rulebook_has_rules(target):
        return target

    source_candidates = (
        bundled_default_rulebook_path(),
        classification_config.repo_rulebook_path(),
    )
    source = None
    for candidate in source_candidates:
        candidate_path = Path(candidate) if candidate is not None else None
        try:
            same_target = candidate_path is not None and candidate_path.resolve() == target.resolve()
        except Exception:
            same_target = False
        if same_target:
            continue
        if _rulebook_has_rules(candidate_path):
            source = candidate_path
            break
    if source is None:
        return target if _safe_exists(target) else None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        return target
    except Exception:
        try:
            return source if source.exists() else None
        except Exception:
            return None


def resolve_rulebook_path(client: str | None, year: str | int | None) -> Path | None:
    _ = (client, year)
    return ensure_default_rulebook_exists()


def find_previous_year_mapping_path(
    client: str | None,
    year: str | int | None,
) -> tuple[Path | None, str | None]:
    return _find_previous_year_mapping_path(client, year)


def find_previous_year_context(
    client: str | None,
    year: str | int | None,
) -> str | None:
    return _find_previous_year_context(client, year)


def load_previous_year_mapping_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[dict[str, str], Path | None, str | None]:
    return _load_previous_year_mapping_for_context(client, year)


def count_unsolved_a07_codes(a07_overview_df: pd.DataFrame) -> int:
    if a07_overview_df is None or a07_overview_df.empty:
        return 0
    excluded = {str(code).strip() for code in EXCLUDED_A07_CODES}
    count = 0
    for _, row in a07_overview_df.iterrows():
        code = str(row.get("Kode", "") or "").strip()
        status = str(row.get("Status", "") or "").strip().lower()
        if not code or code in excluded:
            continue
        if status in {"ok", "ferdig", "ekskludert"}:
            continue
        count += 1
    return count


__all__ = [
    "Path",
    "_account_profile_api_for_a07",
    "_build_usage_features_for_a07",
    "_clean_context_value",
    "_load_code_profile_state",
    "_path_name",
    "_rulebook_has_rules",
    "_safe_exists",
    "copy_rulebook_to_storage",
    "count_unsolved_a07_codes",
    "default_global_rulebook_path",
    "ensure_default_rulebook_exists",
    "find_previous_year_context",
    "find_previous_year_mapping_path",
    "load_previous_year_mapping_for_context",
    "bundled_default_rulebook_path",
    "resolve_rulebook_path",
]
