"""A07 kontrolloppstillings-kilde.

Canonical adapter for building ``ControlStatementRow`` data from the modern
``AccountProfileDocument`` + ``AccountClassificationCatalog``, without going
through ``konto_klassifisering``.

Public API:
    load_current_catalog() -> AccountClassificationCatalog | None
    build_current_control_statement_rows(client, year, gl_df, *, include_unclassified=False)
        -> list[ControlStatementRow]
"""
from __future__ import annotations

import pandas as pd

import classification_config
from account_profile import AccountClassificationCatalog
from account_profile_catalog import load_account_classification_catalog
from account_profile_reporting import (
    ControlStatementRow,
    build_control_statement_rows,
)

from . import mapping_source


def load_current_catalog() -> AccountClassificationCatalog | None:
    """Load the active account classification catalog.

    Returns ``None`` if the catalog path cannot be resolved or the file fails
    to load. Callers should tolerate ``None`` and pass it straight through to
    ``build_control_statement_rows`` (which treats it as "no catalog").
    """
    try:
        path = classification_config.resolve_catalog_path()
    except Exception:
        return None
    try:
        return load_account_classification_catalog(path)
    except Exception:
        return None


def build_current_control_statement_rows(
    client: str | None,
    year: int | None,
    gl_df: pd.DataFrame | None,
    *,
    include_unclassified: bool = False,
) -> list[ControlStatementRow]:
    """Build control-statement rows for the current-year document + catalog.

    Returns ``[]`` when inputs are missing/invalid or when the profile
    document cannot be loaded. Catalog load failures degrade gracefully to
    ``catalog=None`` so rows are still produced (without catalog-driven
    filtering/ordering).
    """
    client_s = str(client or "").strip()
    if not client_s:
        return []
    if gl_df is None or not isinstance(gl_df, pd.DataFrame) or gl_df.empty:
        return []

    try:
        document = mapping_source.load_current_document(client_s, year=year)
    except Exception:
        return []

    catalog = load_current_catalog()

    return build_control_statement_rows(
        gl_df,
        document,
        catalog=catalog,
        include_unclassified=bool(include_unclassified),
    )


__all__ = [
    "load_current_catalog",
    "build_current_control_statement_rows",
]
