from __future__ import annotations

import json
from pathlib import Path

from account_profile import AccountClassificationCatalog
from account_profile_bridge import build_legacy_default_catalog


def default_catalog_path() -> Path:
    return Path(__file__).resolve().parent / "config" / "account_classification_catalog.json"


def load_account_classification_catalog(path: str | Path | None = None) -> AccountClassificationCatalog:
    catalog_path = Path(path) if path is not None else default_catalog_path()
    if not catalog_path.exists():
        return build_legacy_default_catalog()
    with open(catalog_path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if not isinstance(payload, dict):
        raise ValueError("Account classification catalog must be a JSON object")
    return AccountClassificationCatalog.from_dict(payload)

