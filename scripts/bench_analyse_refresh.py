"""bench_analyse_refresh.py — mål tunge operasjoner i Analyse-pipelinen.

Genererer et syntetisk dataset av realistisk størrelse og kjører de tunge
kodepathene mot det:

  1. build_rl_pivot (én kjøring)
  2. build_rl_pivot × 3 (slik refresh_rl_pivot faktisk gjør for AO-sammenligning)
  3. add_previous_year_columns (fjorår-merging)
  4. _resolve_regnr_for_accounts (konto→regnr-mapping)

Bruk:
    python scripts/bench_analyse_refresh.py [--rows N] [--accounts N] [--repeats N]

Default: 100 000 transaksjoner, 300 kontoer, 3 repetisjoner per måling.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from statistics import mean, median

import numpy as np
import pandas as pd

# Legg repo-rot på path slik at vi kan importere uten å kjøre via app
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def make_synthetic_hb(n_rows: int, n_accounts: int, *, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    accounts = [f"{1000 + i}" for i in range(n_accounts)]
    return pd.DataFrame({
        "Konto": rng.choice(accounts, size=n_rows),
        "Kontonavn": "Konto",
        "Bilag": rng.integers(1, 50000, size=n_rows).astype(str),
        "Beløp": rng.normal(0, 10000, size=n_rows),
        "Dato": pd.Timestamp("2025-01-01") + pd.to_timedelta(rng.integers(0, 365, size=n_rows), unit="D"),
    })


def make_synthetic_sb(n_accounts: int, *, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "konto": [f"{1000 + i}" for i in range(n_accounts)],
        "kontonavn": [f"Konto {1000 + i}" for i in range(n_accounts)],
        "ib": rng.normal(0, 50000, size=n_accounts),
        "ub": rng.normal(0, 50000, size=n_accounts),
    })


def make_synthetic_intervals(n_accounts: int) -> pd.DataFrame:
    """Mapper kontoer 1000+i til regnr 10..150 i blokker."""
    blocks = [
        (1000, 1099, 10), (1100, 1199, 20), (1200, 1299, 30),
        (1300, 1399, 40), (1400, 1499, 50), (1500, 1599, 60),
        (1600, 1699, 70), (1700, 1799, 80), (1800, 1899, 90),
        (1900, 1999, 100), (2000, 2099, 110), (2100, 2199, 120),
        (2200, 2299, 130), (2300, 2399, 140), (2400, 9999, 150),
    ]
    rows = []
    for fra, til, regnr in blocks:
        rows.append({"fra": fra, "til": til, "regnr": regnr})
    return pd.DataFrame(rows)


def make_synthetic_regnskapslinjer() -> pd.DataFrame:
    """Lager 15 RL-er som matcher intervalls regnr."""
    return pd.DataFrame({
        "nr":             [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150],
        "regnskapslinje": [f"Linje {nr}" for nr in (10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150)],
        "sumpost":        ["nei"] * 15,
        "Formel":         [""] * 15,
    })


def time_it(label: str, fn, repeats: int = 3) -> dict:
    """Kjør fn() repeats ganger, returner timing-stats."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return {
        "label": label,
        "min_ms": min(times) * 1000,
        "median_ms": median(times) * 1000,
        "mean_ms": mean(times) * 1000,
        "max_ms": max(times) * 1000,
        "n": len(times),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=100_000, help="HB-transaksjoner (default 100 000)")
    ap.add_argument("--accounts", type=int, default=300, help="Kontoer (default 300)")
    ap.add_argument("--repeats", type=int, default=3, help="Repetisjoner pr måling (default 3)")
    args = ap.parse_args()

    print(f"=== Genererer syntetisk dataset: {args.rows:,} rader, {args.accounts} kontoer ===")
    t0 = time.perf_counter()
    df_hb = make_synthetic_hb(args.rows, args.accounts)
    df_sb = make_synthetic_sb(args.accounts)
    df_sb_prev = make_synthetic_sb(args.accounts, seed=99)
    intervals = make_synthetic_intervals(args.accounts)
    regnskapslinjer = make_synthetic_regnskapslinjer()
    print(f"  Generert på {(time.perf_counter() - t0)*1000:.0f} ms")

    # Importer kodepathene vi vil måle
    from page_analyse_rl_pivot import build_rl_pivot
    from page_analyse_rl_data import _resolve_regnr_for_accounts
    from previous_year_comparison import add_previous_year_columns

    konto_list = df_hb["Konto"].astype(str).unique().tolist()

    measurements = []

    # 1. build_rl_pivot — uten sb_prev
    measurements.append(time_it(
        "build_rl_pivot (uten fjor)",
        lambda: build_rl_pivot(df_hb, intervals, regnskapslinjer, sb_df=df_sb),
        args.repeats,
    ))

    # 2. build_rl_pivot — med sb_prev
    measurements.append(time_it(
        "build_rl_pivot (med fjor)",
        lambda: build_rl_pivot(df_hb, intervals, regnskapslinjer, sb_df=df_sb, sb_prev_df=df_sb_prev),
        args.repeats,
    ))

    # 3. build_rl_pivot × 3 — slik refresh_rl_pivot gjør for AO-sammenligning
    def _three_pivots():
        for _ in range(3):
            build_rl_pivot(df_hb, intervals, regnskapslinjer, sb_df=df_sb)
    measurements.append(time_it(
        "build_rl_pivot x3 (AO-sammenligning)",
        _three_pivots,
        args.repeats,
    ))

    # 4. _resolve_regnr_for_accounts (brukes av RL-pivot + min nye SB-tre-kolonne)
    measurements.append(time_it(
        "_resolve_regnr_for_accounts",
        lambda: _resolve_regnr_for_accounts(konto_list, intervals=intervals, regnskapslinjer=regnskapslinjer),
        args.repeats,
    ))

    # 5. add_previous_year_columns isolert
    base_pivot = build_rl_pivot(df_hb, intervals, regnskapslinjer, sb_df=df_sb)
    measurements.append(time_it(
        "add_previous_year_columns (full)",
        lambda: add_previous_year_columns(base_pivot, df_sb_prev, intervals, regnskapslinjer),
        args.repeats,
    ))

    # 5b. Bryt ned add_previous_year_columns
    from page_analyse_rl import _aggregate_sb_to_regnr
    measurements.append(time_it(
        "  -_aggregate_sb_to_regnr (fjor)",
        lambda: _aggregate_sb_to_regnr(df_sb_prev, intervals),
        args.repeats,
    ))

    from regnskap_mapping import compute_sumlinjer, normalize_regnskapslinjer
    regn_norm = normalize_regnskapslinjer(regnskapslinjer)
    prev_agg = _aggregate_sb_to_regnr(df_sb_prev, intervals)
    base_values = {int(r): float(v) for r, v in zip(prev_agg["regnr"], prev_agg["UB"])}
    measurements.append(time_it(
        "  -compute_sumlinjer (fjor)",
        lambda: compute_sumlinjer(base_values=base_values, regnskapslinjer=regn_norm),
        args.repeats,
    ))

    measurements.append(time_it(
        "  -normalize_regnskapslinjer",
        lambda: normalize_regnskapslinjer(regnskapslinjer),
        args.repeats,
    ))

    # Bryt ned _aggregate_sb_to_regnr ytterligere
    work = df_sb_prev[["konto", "ib", "ub"]].copy()
    work["konto"] = work["konto"].astype(str).str.strip()
    work["ib"] = pd.to_numeric(work["ib"], errors="coerce").fillna(0.0)
    work["ub"] = pd.to_numeric(work["ub"], errors="coerce").fillna(0.0)
    konto_list_sb = work["konto"].tolist()

    measurements.append(time_it(
        "  -_resolve_regnr_for_accounts (fra SB)",
        lambda: _resolve_regnr_for_accounts(konto_list_sb, intervals=intervals, regnskapslinjer=regnskapslinjer),
        args.repeats,
    ))

    regnr_lookup = _resolve_regnr_for_accounts(konto_list_sb, intervals=intervals, regnskapslinjer=regnskapslinjer)

    def _merge_step():
        mapped = work.merge(regnr_lookup, on="konto", how="left")
        return mapped.dropna(subset=["regnr"]).groupby("regnr", as_index=False).agg(IB=("ib", "sum"), UB=("ub", "sum"))

    measurements.append(time_it(
        "  -merge + groupby + agg",
        _merge_step,
        args.repeats,
    ))

    # Rapporter
    print()
    print(f"=== Resultater ({args.repeats} kjøringer pr operasjon) ===")
    print(f"{'Operasjon':<45} {'min':>9} {'median':>9} {'mean':>9} {'max':>9}")
    print("-" * 85)
    for m in measurements:
        print(f"{m['label']:<45} "
              f"{m['min_ms']:>7.0f}ms {m['median_ms']:>7.0f}ms "
              f"{m['mean_ms']:>7.0f}ms {m['max_ms']:>7.0f}ms")
    print()
    print("Tips: kjør med --rows 200000 eller --accounts 500 for å simulere større klient.")


if __name__ == "__main__":
    main()
