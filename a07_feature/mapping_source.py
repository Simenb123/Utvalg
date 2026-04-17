"""A07 mapping-kilde adapter.

Canonical entry point for A07 runtime to read and write
``AccountProfileDocument`` via ``AccountProfileStore`` directly. Keeps
``konto_klassifisering``/``AccountProfileLegacyApi`` out of the A07 read path.

Public API:
    load_current_document(client, year=None) -> AccountProfileDocument
    save_current_document(client, year, document) -> Path
    mapping_from_document(document) -> dict[str, str]          # {konto: a07_code}
    document_with_updated_mapping(document, mapping) -> AccountProfileDocument
"""
from __future__ import annotations

from pathlib import Path

import app_paths
from account_profile import (
    AccountProfileDocument,
    AccountProfileSource,
    AccountProfileStore,
    normalize_profile_year,
)
from account_profile_bridge import (
    a07_mapping_from_document,
    replace_a07_codes_from_mapping,
)
from account_profile_legacy_api import account_profile_store_path, safe_client_slug


def _profiles_base_dir() -> Path:
    return Path(app_paths.data_dir()) / "konto_klassifisering_profiles"


def _resolve_store_path(client: str, year: int | None) -> Path:
    return account_profile_store_path(
        _profiles_base_dir(),
        client=client,
        year=year,
    )


def _store_for(client: str, year: int | None) -> AccountProfileStore:
    return AccountProfileStore(_resolve_store_path(client, year))


def current_document_path(client: str, year: int | None = None) -> Path:
    """Return the canonical JSON path for a client/year, without loading."""
    return _resolve_store_path(client, normalize_profile_year(year))


def load_current_document(
    client: str,
    year: int | None = None,
) -> AccountProfileDocument:
    """Load the canonical profile document for a client/year.

    Returns an empty document when the JSON file does not exist.
    """
    year_n = normalize_profile_year(year)
    store = _store_for(client, year_n)
    if not store.path.exists():
        return AccountProfileDocument(client=client, year=year_n)
    return store.load(client=client, year=year_n)


def save_current_document(
    client: str,
    year: int | None,
    document: AccountProfileDocument,
) -> Path:
    """Persist a document via ``AccountProfileStore`` at the canonical path."""
    year_n = normalize_profile_year(year)
    return _store_for(client, year_n).save(document)


def mapping_from_document(document: AccountProfileDocument) -> dict[str, str]:
    """Extract ``{konto: a07_code}`` from a document."""
    return a07_mapping_from_document(document)


def load_nearest_prior_document(
    client: str,
    current_year: int | None,
) -> tuple[AccountProfileDocument | None, int | None]:
    """Return (document, year) for the highest profile-doc year strictly below
    ``current_year`` that loads successfully, or ``(None, None)`` if none are
    loadable. Years whose JSON fails to parse are skipped so a corrupt newer
    document does not shadow an older valid one.
    """
    year_n = normalize_profile_year(current_year)
    if year_n is None:
        return None, None
    client_dir = _profiles_base_dir() / safe_client_slug(client)
    if not client_dir.exists():
        return None, None
    candidates: list[int] = []
    try:
        for child in client_dir.iterdir():
            if not child.is_dir():
                continue
            try:
                child_year = int(child.name)
            except Exception:
                continue
            if child_year >= year_n:
                continue
            if (child / "account_profiles.json").exists():
                candidates.append(child_year)
    except Exception:
        return None, None
    for prior_year in sorted(candidates, reverse=True):
        try:
            document = _store_for(client, prior_year).load(
                client=client, year=prior_year
            )
        except Exception:
            continue
        return document, prior_year
    return None, None


def document_with_updated_mapping(
    document: AccountProfileDocument,
    mapping: dict[str, str],
    *,
    source: AccountProfileSource = "manual",
    confidence: float | None = 1.0,
) -> AccountProfileDocument:
    """Return a new document where a07_code is replaced from ``mapping``."""
    return replace_a07_codes_from_mapping(
        document,
        mapping,
        source=source,
        confidence=confidence,
    )


__all__ = [
    "load_current_document",
    "save_current_document",
    "mapping_from_document",
    "document_with_updated_mapping",
    "current_document_path",
    "load_nearest_prior_document",
]


# Re-exported for tests that want to verify path resolution without
# touching app_paths internals directly.
def _store_path_for_testing(
    base_dir: str | Path,
    *,
    client: str,
    year: int | None = None,
) -> Path:
    return account_profile_store_path(base_dir, client=client, year=year)
