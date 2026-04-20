"""brreg_fjor_fallback.py — BRREG som fjor-fallback for RL-pivot.

Når egne fjorårs-SB-tall mangler, bruker denne modulen BRREG-linjer for
år N-1 (fra ``brreg_data["years"]``) til å fylle kolonnene
``UB_fjor`` / ``Endring_fjor`` / ``Endring_pct`` i RL-pivot.

Dette gir en brukbar sammenligning for nye klienter uten importert
historikk. Gjenbruker ``build_brreg_by_regnr`` slik at RL-mappingen er
konsistent med BRREG-sammenligningskolonnen (samme alias-index).
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from brreg_rl_comparison import build_brreg_by_regnr

log = logging.getLogger("app")


def _extract_year_data(brreg_data: Optional[dict], year: int) -> Optional[dict]:
    """Hent dict for spesifikt år fra brreg_data['years']."""
    if not isinstance(brreg_data, dict):
        return None
    years = brreg_data.get("years")
    if not isinstance(years, dict):
        return None
    return years.get(year) or years.get(str(year))


def has_brreg_for_year(brreg_data: Optional[dict], year: int) -> bool:
    """Returner True når brreg_data har tall for spesifikt år."""
    data = _extract_year_data(brreg_data, year)
    return isinstance(data, dict) and bool(data.get("linjer"))


def build_brreg_fjor_pivot_columns(
    pivot_df: pd.DataFrame,
    regnskapslinjer: pd.DataFrame,
    brreg_data: Optional[dict],
    fjor_year: int,
) -> pd.DataFrame:
    """Legg UB_fjor/Endring_fjor/Endring_pct til pivot_df basert på BRREG-år.

    Returnerer pivot med utvidet sett av kolonner. Linjer uten match i
    BRREG får None (tom celle i GUI) — konsistent med
    ``previous_year_comparison.add_previous_year_columns``.
    """
    result = pivot_df.copy() if pivot_df is not None else pd.DataFrame()

    if "regnr" not in result.columns or "UB" not in result.columns:
        result["UB_fjor"] = None
        result["Endring_fjor"] = None
        result["Endring_pct"] = None
        return result

    payload = _extract_year_data(brreg_data, fjor_year) or {}
    brreg_by_regnr = build_brreg_by_regnr(regnskapslinjer, payload)
    if not brreg_by_regnr:
        result["UB_fjor"] = None
        result["Endring_fjor"] = None
        result["Endring_pct"] = None
        return result

    try:
        regnr_int = result["regnr"].astype(int)
    except Exception:
        regnr_int = pd.Series([None] * len(result), index=result.index)

    result["UB_fjor"] = regnr_int.map(
        lambda r: brreg_by_regnr.get(int(r)) if pd.notna(r) else None
    )

    ub = pd.to_numeric(result.get("UB"), errors="coerce")
    ub_fjor_num = pd.to_numeric(result["UB_fjor"], errors="coerce")

    endring = ub - ub_fjor_num
    result["Endring_fjor"] = endring
    mask_nan = result["UB_fjor"].isna()
    result.loc[mask_nan, "Endring_fjor"] = None

    def _pct(u: object, uf: object) -> Optional[float]:
        if uf is None or pd.isna(uf):
            return None
        if abs(float(uf)) < 0.01:
            return None
        if u is None or pd.isna(u):
            return None
        return (float(u) - float(uf)) / abs(float(uf)) * 100.0

    result["Endring_pct"] = [
        _pct(
            ub.iloc[i] if i < len(ub) else None,
            ub_fjor_num.iloc[i] if i < len(ub_fjor_num) else None,
        )
        for i in range(len(result))
    ]
    return result
