"""HB-versjonsdiff: sammenlign to hovedbok-versjoner bilag for bilag.

Ren beregningsmodul — ingen GUI-avhengigheter.

Klassifiserer bilag som:
  - Nye (kun i versjon B)
  - Fjernede (kun i versjon A)
  - Endrede (finnes i begge, men ulikt innhold/sum)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class HBDiffResult:
    """Resultat fra sammenligning av to HB-versjoner."""

    added: pd.DataFrame       # Nye bilag (kun i B)
    removed: pd.DataFrame     # Fjernede bilag (kun i A)
    changed: pd.DataFrame     # Endrede bilag (ulik sum/antall linjer)
    unchanged_count: int       # Antall bilag som er identiske
    summary: dict


def diff_hb_versions(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    *,
    bilag_col: str = "Bilag",
    konto_col: str = "Konto",
    belop_col: str = "Beløp",
) -> HBDiffResult:
    """Sammenlign to HB DataFrames bilag-for-bilag.

    Args:
        df_a: Eldre versjon (forrige import)
        df_b: Nyere versjon (gjeldende import)

    Returnerer HBDiffResult med nye, fjernede og endrede bilag.
    """
    # Valider kolonner
    for col in (bilag_col, konto_col, belop_col):
        if col not in df_a.columns:
            df_a[col] = ""
        if col not in df_b.columns:
            df_b[col] = ""

    # Aggreger per bilag: sum beløp, antall linjer
    agg_a = _aggregate_by_bilag(df_a, bilag_col, belop_col)
    agg_b = _aggregate_by_bilag(df_b, bilag_col, belop_col)

    bilag_a = set(agg_a["bilag"])
    bilag_b = set(agg_b["bilag"])

    # Nye bilag: kun i B
    new_bilag = bilag_b - bilag_a
    # Fjernede bilag: kun i A
    removed_bilag = bilag_a - bilag_b
    # Felles bilag: i begge
    common_bilag = bilag_a & bilag_b

    # Endrede bilag: felles bilag med ulik sum, antall linjer, eller innhold
    merged = agg_a.merge(agg_b, on="bilag", how="inner", suffixes=("_a", "_b"))
    changed_mask = (
        (merged["sum_a"] - merged["sum_b"]).abs() > 0.01
    ) | (
        merged["linjer_a"] != merged["linjer_b"]
    ) | (
        merged["fingerprint_a"] != merged["fingerprint_b"]
    )
    changed_bilag_ids = set(merged.loc[changed_mask, "bilag"])
    unchanged_count = len(common_bilag) - len(changed_bilag_ids)

    # Bygg detalj-DataFrames fra versjon B (for nye) / A (for fjernede)
    added_df = df_b.loc[df_b[bilag_col].astype(str).isin(new_bilag)].copy()
    removed_df = df_a.loc[df_a[bilag_col].astype(str).isin(removed_bilag)].copy()

    # Endrede: vis begge versjoner side om side (oppsummering per bilag)
    changed_detail = merged.loc[changed_mask].copy()
    changed_detail["diff_sum"] = changed_detail["sum_b"] - changed_detail["sum_a"]
    changed_detail["diff_linjer"] = changed_detail["linjer_b"] - changed_detail["linjer_a"]

    summary = {
        "bilag_a_total": len(bilag_a),
        "bilag_b_total": len(bilag_b),
        "nye_bilag": len(new_bilag),
        "fjernede_bilag": len(removed_bilag),
        "endrede_bilag": len(changed_bilag_ids),
        "uendrede_bilag": unchanged_count,
        "nye_transaksjoner": len(added_df),
        "fjernede_transaksjoner": len(removed_df),
    }

    return HBDiffResult(
        added=added_df,
        removed=removed_df,
        changed=changed_detail,
        unchanged_count=unchanged_count,
        summary=summary,
    )


def _aggregate_by_bilag(df: pd.DataFrame, bilag_col: str, belop_col: str) -> pd.DataFrame:
    """Aggreger DataFrame per bilag: sum beløp, antall linjer og innholds-fingerprint."""
    work = df[[bilag_col, belop_col]].copy()
    work[bilag_col] = work[bilag_col].astype(str).str.strip()
    work[belop_col] = pd.to_numeric(work[belop_col], errors="coerce").fillna(0.0)

    # Fjern tomme bilag
    work = work.loc[work[bilag_col].str.len() > 0]

    agg = work.groupby(bilag_col, sort=False).agg(
        sum=(belop_col, "sum"),
        linjer=(belop_col, "count"),
    ).reset_index()
    agg.columns = ["bilag", "sum", "linjer"]

    # Fingerprint: sortert liste av beløp per bilag → enkel hash
    fp = (
        work.sort_values(belop_col)
        .groupby(bilag_col, sort=False)[belop_col]
        .apply(lambda s: hashlib.md5(",".join(f"{v:.2f}" for v in s).encode()).hexdigest())
        .reset_index()
    )
    fp.columns = ["bilag", "fingerprint"]
    agg = agg.merge(fp, on="bilag", how="left")
    return agg
