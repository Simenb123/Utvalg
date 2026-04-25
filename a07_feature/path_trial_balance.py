from __future__ import annotations

from pathlib import Path

import pandas as pd

from trial_balance_reader import read_trial_balance

from . import from_trial_balance
from .path_shared import _clean_context_value, _safe_exists, client_store, session_module


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


def load_active_trial_balance_for_context(
    client: str | None,
    year: str | int | None,
) -> tuple[pd.DataFrame, Path | None]:
    client_s = _clean_context_value(client)
    year_s = _clean_context_value(year)
    if not client_s or not year_s:
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), None

    path = get_active_trial_balance_path_for_context(client_s, year_s)
    if path is None or not _safe_exists(path):
        tb_df = getattr(session_module, "tb_df", None) if session_module is not None else None
        if isinstance(tb_df, pd.DataFrame) and not tb_df.empty:
            return from_trial_balance(tb_df), None
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), path

    try:
        tb_df = read_trial_balance(path)
        return from_trial_balance(tb_df), path
    except Exception:
        return pd.DataFrame(columns=["Konto", "Navn", "IB", "Endring", "UB"]), path
