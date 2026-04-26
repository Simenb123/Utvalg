"""consolidation.mapping -- Konto-mapping for konsolideringskontekst.

Wrapper rundt regnskap_mapping-funksjonene. Laster globale intervaller
og regnskapslinjer fra regnskap_config, og legger paa per-selskap
overstyringer fra ConsolidationProject.mapping_config.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class ConfigNotLoadedError(RuntimeError):
    """Kastes naar paakrevd regnskap-konfigurasjon ikke er importert."""

    pass


def load_shared_config() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Last og normaliser globale intervaller + regnskapslinjer.

    Returns:
        (intervals, regnskapslinjer) — begge normaliserte DataFrames.

    Raises:
        ConfigNotLoadedError: Hvis config-filer mangler.
    """
    from src.shared.regnskap.config import load_kontoplan_mapping, load_regnskapslinjer
    from src.shared.regnskap.mapping import normalize_intervals, normalize_regnskapslinjer

    try:
        raw_intervals = load_kontoplan_mapping()
    except FileNotFoundError as exc:
        raise ConfigNotLoadedError(
            "Kontoplan-mapping er ikke importert. "
            "Gaa til Innstillinger og importer kontoplan_mapping.xlsx foerst."
        ) from exc

    try:
        raw_rl = load_regnskapslinjer()
    except FileNotFoundError as exc:
        raise ConfigNotLoadedError(
            "Regnskapslinjer er ikke importert. "
            "Gaa til Innstillinger og importer regnskapslinjer.xlsx foerst."
        ) from exc

    intervals = normalize_intervals(raw_intervals)
    regnskapslinjer = normalize_regnskapslinjer(raw_rl)
    return intervals, regnskapslinjer


def map_company_tb(
    tb: pd.DataFrame,
    overrides: dict[str, int] | None = None,
    *,
    intervals: pd.DataFrame | None = None,
    regnskapslinjer: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """Map et selskaps TB til regnskapslinjer.

    Args:
        tb: Normalisert TB med kolonner [konto, kontonavn, ib, ub, netto].
        overrides: Valgfrie konto->regnr overstyringer for dette selskapet.
        intervals: Pre-loaded intervals (unngaar lasting fra config).
        regnskapslinjer: Pre-loaded regnskapslinjer (brukes for validering).

    Returns:
        (mapped_df, unmapped_accounts)
        mapped_df: TB med ekstra 'regnr' kolonne (Int64).
        unmapped_accounts: Sortert liste med kontoer uten mapping.
    """
    from src.shared.regnskap.mapping import apply_account_overrides, apply_interval_mapping

    if intervals is None or regnskapslinjer is None:
        intervals, regnskapslinjer = load_shared_config()

    result = apply_interval_mapping(tb, intervals, konto_col="konto")
    mapped_df = result.mapped
    unmapped = list(result.unmapped_konto)

    if overrides:
        mapped_df = apply_account_overrides(
            mapped_df, overrides, konto_col="konto",
        )
        # Recalculate unmapped after overrides
        still_unmapped = (
            mapped_df.loc[mapped_df["regnr"].isna(), "konto"]
            .astype(str)
            .unique()
            .tolist()
        )
        unmapped = sorted(still_unmapped)

    logger.info(
        "Mapped company TB: %d rows, %d unmapped accounts",
        len(mapped_df),
        len(unmapped),
    )
    return mapped_df, unmapped
