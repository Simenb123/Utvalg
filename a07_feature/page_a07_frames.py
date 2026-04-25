from __future__ import annotations

import pandas as pd

from .control.rf1022_contract import RF1022_OVERVIEW_COLUMNS as _RF1022_OVERVIEW_DATA_COLUMNS
from .page_a07_constants import (
    _CONTROL_COLUMNS,
    _CONTROL_EXTRA_COLUMNS,
    _CONTROL_STATEMENT_COLUMNS,
    _GROUP_COLUMNS,
    _HISTORY_COLUMNS,
    _MAPPING_COLUMNS,
    _RECONCILE_COLUMNS,
    _RF1022_ACCOUNT_COLUMNS,
    _RF1022_OVERVIEW_COLUMNS,
    _SUGGESTION_COLUMNS,
    _UNMAPPED_COLUMNS,
)


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
    columns = ["GroupId", *[c[0] for c in _GROUP_COLUMNS]]
    return pd.DataFrame(columns=list(dict.fromkeys(columns)))


def _empty_control_statement_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "Gruppe",
            "Navn",
            "IB",
            "Endring",
            "UB",
            "A07",
            "Diff",
            "Status",
            "AntallKontoer",
            "Kontoer",
            "Kilder",
        ]
    )


def _empty_rf1022_overview_df() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_RF1022_OVERVIEW_DATA_COLUMNS))


def _empty_rf1022_accounts_df() -> pd.DataFrame:
    return pd.DataFrame(columns=[c[0] for c in _RF1022_ACCOUNT_COLUMNS])


__all__ = [
    "_empty_a07_df",
    "_empty_control_df",
    "_empty_control_statement_df",
    "_empty_gl_df",
    "_empty_groups_df",
    "_empty_history_df",
    "_empty_mapping_df",
    "_empty_reconcile_df",
    "_empty_rf1022_accounts_df",
    "_empty_rf1022_overview_df",
    "_empty_suggestions_df",
    "_empty_unmapped_df",
]
