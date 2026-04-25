from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

import session
from page_analyse_rl import build_rl_pivot, load_rl_config, load_sb_for_session
from regnskap_data import ub_lookup

try:
    from page_analyse_rl import _load_current_client_account_overrides
except Exception:  # pragma: no cover - defensive fallback
    _load_current_client_account_overrides = None  # type: ignore[assignment]


BENCHMARK_KEYS = (
    "revenue",
    "gross_profit",
    "profit_before_tax",
    "total_assets",
    "equity",
)

BENCHMARK_LABELS: dict[str, str] = {
    "revenue": "Driftsinntekter",
    "gross_profit": "Bruttofortjeneste",
    "profit_before_tax": "Resultat før skatt",
    "total_assets": "Sum eiendeler",
    "equity": "Egenkapital",
}

BENCHMARK_PCT_RANGES: dict[str, tuple[float, float]] = {
    "revenue": (1.0, 2.0),
    "gross_profit": (1.5, 3.0),
    "profit_before_tax": (5.0, 10.0),
    "total_assets": (0.5, 1.0),
    "equity": (1.0, 5.0),
}

BENCHMARK_KEY_ALIASES: dict[str, str] = {
    "operating_result": "gross_profit",
}

_DEFAULT_AMOUNTS: dict[str, float] = {key: 0.0 for key in BENCHMARK_KEYS}


@dataclass(frozen=True)
class MaterialityCalculation:
    benchmark_key: str
    benchmark_amount: float
    om_pct: float
    pm_pct: float
    trivial_pct: float
    reference_pct_low: float
    reference_pct_high: float
    reference_amount_low: int
    reference_amount_high: int
    om: int
    pm: int
    trivial: int


def get_default_percentages(benchmark_key: str) -> tuple[float, float, float]:
    benchmark_key = normalize_benchmark_key(benchmark_key)
    lo, hi = BENCHMARK_PCT_RANGES.get(benchmark_key, (1.0, 2.0))
    return ((lo + hi) / 2.0, 75.0, 10.0)


def normalize_benchmark_key(benchmark_key: str) -> str:
    raw = str(benchmark_key or "").strip()
    return BENCHMARK_KEY_ALIASES.get(raw, raw)


def pick_default_benchmark(amounts: dict[str, float]) -> str | None:
    preference = (
        "profit_before_tax",
        "gross_profit",
        "revenue",
        "total_assets",
        "equity",
    )
    for key in preference:
        if float(amounts.get(key) or 0.0) > 0:
            return key
    return None


def calculate_materiality(
    benchmark_key: str,
    benchmark_amount: float,
    *,
    om_pct: float | None,
    pm_pct: float,
    trivial_pct: float,
    selected_om: float | None = None,
) -> MaterialityCalculation:
    benchmark_key = normalize_benchmark_key(benchmark_key)
    amount = abs(float(benchmark_amount or 0.0))
    ref_lo_pct, ref_hi_pct = BENCHMARK_PCT_RANGES.get(benchmark_key, (1.0, 2.0))
    ref_lo_amount = round(amount * (ref_lo_pct / 100.0))
    ref_hi_amount = round(amount * (ref_hi_pct / 100.0))

    explicit_om = None
    try:
        explicit_om = abs(float(selected_om)) if selected_om is not None else None
    except Exception:
        explicit_om = None

    if explicit_om is not None and explicit_om > 0.0:
        om = round(explicit_om)
        derived_om_pct = (om / amount * 100.0) if amount > 0.0 else float(om_pct or 0.0)
    else:
        derived_om_pct = float(om_pct or 0.0)
        om = round(amount * (derived_om_pct / 100.0))
    pm = round(om * (float(pm_pct or 0.0) / 100.0))
    trivial = round(pm * (float(trivial_pct or 0.0) / 100.0))
    return MaterialityCalculation(
        benchmark_key=benchmark_key,
        benchmark_amount=amount,
        om_pct=derived_om_pct,
        pm_pct=float(pm_pct or 0.0),
        trivial_pct=float(trivial_pct or 0.0),
        reference_pct_low=ref_lo_pct,
        reference_pct_high=ref_hi_pct,
        reference_amount_low=ref_lo_amount,
        reference_amount_high=ref_hi_amount,
        om=om,
        pm=pm,
        trivial=trivial,
    )


def build_benchmark_amounts_from_rl_df(rl_df: pd.DataFrame | None) -> dict[str, float]:
    if rl_df is None or rl_df.empty:
        return dict(_DEFAULT_AMOUNTS)

    lookup = ub_lookup(rl_df, "UB")
    revenue = abs(float(lookup.get(19) or 0.0))
    varekost = abs(float(lookup.get(20) or 0.0))
    gross_profit = abs(revenue - varekost)
    return {
        "revenue": revenue,
        "gross_profit": gross_profit,
        "profit_before_tax": abs(float(lookup.get(160) or 0.0)),
        "total_assets": abs(float(lookup.get(665) or 0.0)),
        "equity": abs(float(lookup.get(715) or 0.0)),
    }


def build_benchmark_amounts_for_session(sess: Any = session) -> dict[str, float]:
    intervals, regnskapslinjer = load_rl_config()
    if intervals is None or regnskapslinjer is None:
        return dict(_DEFAULT_AMOUNTS)

    try:
        hb_df = getattr(sess, "dataset", None)
    except Exception:
        hb_df = None
    if not isinstance(hb_df, pd.DataFrame):
        hb_df = pd.DataFrame()

    try:
        sb_df = getattr(sess, "tb_df", None)
    except Exception:
        sb_df = None
    if not isinstance(sb_df, pd.DataFrame) or sb_df.empty:
        sb_df = load_sb_for_session()

    if (hb_df is None or hb_df.empty) and isinstance(sb_df, pd.DataFrame) and not sb_df.empty:
        konto = sb_df.get("konto")
        if konto is not None:
            hb_df = pd.DataFrame({"Konto": konto.astype(str), "Beløp": 0.0})

    if hb_df is None or hb_df.empty:
        return dict(_DEFAULT_AMOUNTS)

    try:
        overrides = _load_current_client_account_overrides() if callable(_load_current_client_account_overrides) else {}
    except Exception:
        overrides = {}

    rl_df = build_rl_pivot(
        df_hb=hb_df,
        intervals=intervals,
        regnskapslinjer=regnskapslinjer,
        sb_df=sb_df,
        account_overrides=overrides,
    )
    return build_benchmark_amounts_from_rl_df(rl_df)
