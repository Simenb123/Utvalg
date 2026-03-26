"""Fjorårssammenligning: last forrige års SB og beregn endringskolonner.

Ren beregningsmodul — ingen GUI-avhengigheter.

Produserer ekstra kolonner for RL-pivot:
  - UB_fjor:       UB fra forrige års saldobalanse
  - Endring_fjor:  UB (i år) − UB (i fjor), i beløp
  - Endring_pct:   Prosentvis endring fra fjor
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger("app")


def load_previous_year_sb(client: str, year: str | int) -> Optional[pd.DataFrame]:
    """Last SB for forrige år (year − 1) for gitt klient.

    Returnerer normalisert DataFrame (konto, kontonavn, ib, ub, netto) eller None.
    """
    try:
        prev_year = str(int(year) - 1)
    except (ValueError, TypeError):
        return None

    try:
        import client_store
        version = client_store.get_active_version(client, year=prev_year, dtype="sb")
        if version is None:
            log.debug("Ingen aktiv SB-versjon for %s/%s (fjor)", client, prev_year)
            return None

        sb_path = Path(version.path)
        if not sb_path.exists():
            log.warning("Fjorårs SB-fil finnes ikke: %s", sb_path)
            return None

        from trial_balance_reader import read_trial_balance
        df = read_trial_balance(sb_path)
        log.info("Fjorårs SB lastet: %s (%d kontoer)", sb_path.name, len(df))
        return df
    except Exception as exc:
        log.warning("load_previous_year_sb: %s", exc)
        return None


def add_previous_year_columns(
    pivot_df: pd.DataFrame,
    sb_prev: pd.DataFrame,
    intervals: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    *,
    account_overrides: Optional[dict[str, int]] = None,
) -> pd.DataFrame:
    """Legg til fjorårskolonner på en eksisterende RL-pivot DataFrame.

    Forventer at pivot_df har kolonnene: regnr, regnskapslinje, IB, Endring, UB, Antall.
    Legger til: UB_fjor, Endring_fjor, Endring_pct.

    Returnerer pivot_df med ekstra kolonner (NaN der fjorårsdata mangler).
    """
    from page_analyse_rl import _aggregate_sb_to_regnr

    if sb_prev is None or sb_prev.empty:
        return _add_empty_prev_cols(pivot_df)

    try:
        prev_ib_ub = _aggregate_sb_to_regnr(sb_prev, intervals, account_overrides=account_overrides)
    except Exception as exc:
        log.warning("add_previous_year_columns: aggregering feilet: %s", exc)
        return _add_empty_prev_cols(pivot_df)

    if prev_ib_ub.empty:
        return _add_empty_prev_cols(pivot_df)

    # prev_ib_ub har kolonner: regnr, IB, UB
    prev_ub = prev_ib_ub[["regnr", "UB"]].rename(columns={"UB": "UB_fjor"})
    prev_ub["regnr"] = prev_ub["regnr"].astype(int)

    # Beregn sumposter for fjorårsdata
    try:
        from regnskap_mapping import compute_sumlinjer, normalize_regnskapslinjer
        regn = normalize_regnskapslinjer(regnskapslinjer)
        if regn["sumpost"].any():
            base_values = {int(r): float(v) for r, v in zip(prev_ub["regnr"], prev_ub["UB_fjor"])}
            computed = compute_sumlinjer(base_values=base_values, regnskapslinjer=regn)
            sum_rows = pd.DataFrame([
                {"regnr": int(k), "UB_fjor": float(v)}
                for k, v in computed.items()
                if int(k) not in set(prev_ub["regnr"].tolist())
            ])
            if not sum_rows.empty:
                prev_ub = pd.concat([prev_ub, sum_rows], ignore_index=True)
    except Exception as exc:
        log.debug("Kunne ikke beregne sumposter for fjorårsdata: %s", exc)

    result = pivot_df.copy()
    result["regnr"] = result["regnr"].astype(int)
    result = result.merge(prev_ub, on="regnr", how="left")
    result["UB_fjor"] = result["UB_fjor"].fillna(0.0)
    result["Endring_fjor"] = result["UB"] - result["UB_fjor"]

    # Prosentvis endring — unngå div by zero
    result["Endring_pct"] = result.apply(
        lambda r: (r["Endring_fjor"] / abs(r["UB_fjor"]) * 100.0) if abs(r["UB_fjor"]) > 0.01 else None,
        axis=1,
    )

    return result


def _add_empty_prev_cols(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["UB_fjor"] = None
    result["Endring_fjor"] = None
    result["Endring_pct"] = None
    return result
