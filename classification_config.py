from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import app_paths


_ROOT_DIR = Path(__file__).resolve().parent
_REPO_CONFIG_DIR = _ROOT_DIR / "config" / "classification"

_LEGACY_CATALOG_PATH = _ROOT_DIR / "config" / "account_classification_catalog.json"

_APPDATA_THRESHOLDS_PATH = app_paths.data_dir() / "a07" / "matcher_settings.json"


def _path_exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def repo_dir() -> Path:
    return _REPO_CONFIG_DIR


def repo_catalog_path() -> Path:
    return repo_dir() / "account_classification_catalog.json"


def repo_rulebook_path() -> Path:
    return repo_dir() / "global_full_a07_rulebook.json"


def repo_thresholds_path() -> Path:
    return repo_dir() / "thresholds.json"


def repo_regnskapslinje_rulebook_path() -> Path:
    return repo_dir() / "regnskapslinje_rulebook.json"


def repo_account_detail_classification_path() -> Path:
    return repo_dir() / "account_detail_classification.json"


def resolve_catalog_path() -> Path:
    target = repo_catalog_path()
    if _path_exists(target):
        return target
    return _LEGACY_CATALOG_PATH


def resolve_rulebook_path() -> Path:
    return repo_rulebook_path()


def resolve_thresholds_path() -> Path:
    repo_target = repo_thresholds_path()
    if _path_exists(repo_target):
        return repo_target
    if _path_exists(_APPDATA_THRESHOLDS_PATH):
        return _APPDATA_THRESHOLDS_PATH
    return repo_target


def resolve_regnskapslinje_rulebook_path() -> Path:
    repo_target = repo_regnskapslinje_rulebook_path()
    if _path_exists(repo_target):
        return repo_target
    return repo_target


def resolve_account_detail_classification_path() -> Path:
    return repo_account_detail_classification_path()


def ensure_repo_dir() -> Path:
    target = repo_dir()
    target.mkdir(parents=True, exist_ok=True)
    return target


def load_json(path: str | Path, *, fallback: Any) -> Any:
    target = Path(path)
    try:
        with open(target, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return fallback


def save_json(path: str | Path, data: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return target


def load_catalog_document() -> dict[str, Any]:
    data = load_json(resolve_catalog_path(), fallback={})
    return data if isinstance(data, dict) else {}


def save_catalog_document(data: Any) -> Path:
    return save_json(repo_catalog_path(), data if isinstance(data, dict) else {})


def load_rulebook_document() -> dict[str, Any]:
    data = load_json(resolve_rulebook_path(), fallback={})
    return data if isinstance(data, dict) else {}


def save_rulebook_document(data: Any) -> Path:
    return save_json(repo_rulebook_path(), data if isinstance(data, dict) else {})


def load_thresholds_document(defaults: dict[str, float | int] | None = None) -> dict[str, float | int]:
    data = load_json(resolve_thresholds_path(), fallback={})
    out = dict(defaults or {})
    if isinstance(data, dict):
        out.update(data)
    return out


def save_thresholds_document(data: Any) -> Path:
    return save_json(repo_thresholds_path(), data if isinstance(data, dict) else {})


def load_regnskapslinje_rulebook_document() -> dict[str, Any]:
    data = load_json(resolve_regnskapslinje_rulebook_path(), fallback={})
    return data if isinstance(data, dict) else {}


def save_regnskapslinje_rulebook_document(data: Any) -> Path:
    return save_json(repo_regnskapslinje_rulebook_path(), data if isinstance(data, dict) else {})


def load_account_detail_classification_document() -> dict[str, Any]:
    """Les globalt detalj-klassifiseringsdokument. Seed hvis mangler/tom.

    Seed skrives til disk slik at første lesing produserer en redigerbar fil.
    """

    path = resolve_account_detail_classification_path()
    raw = load_json(path, fallback=None)
    if isinstance(raw, dict) and isinstance(raw.get("classes"), list) and raw["classes"]:
        return raw
    # Lazy import for å unngå sirkulær avhengighet ved import-tid.
    import account_detail_classification as _adc

    seed = {"classes": [dict(entry) for entry in _adc.SEED_CLASSES]}
    try:
        save_account_detail_classification_document(seed)
    except Exception:
        pass
    return seed


def save_account_detail_classification_document(data: Any) -> Path:
    payload = data if isinstance(data, dict) else {"classes": []}
    return save_json(repo_account_detail_classification_path(), payload)
