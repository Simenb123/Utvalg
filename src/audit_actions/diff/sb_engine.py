"""SB-versjonsdiff: sammenlign to saldobalanse-versjoner konto for konto.

Ren beregningsmodul — ingen GUI-avhengigheter.

Klassifiserer konti som:
  - Nye (kun i versjon B)
  - Fjernede (kun i versjon A)
  - Endrede (finnes i begge, men ulik IB eller UB)
  - Uendrede (identiske saldoer)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


# Standardkolonner forventes via trial_balance_reader.read_trial_balance
# som normaliserer til: konto, kontonavn, ib, ub. Vi støtter også store
# bokstaver i tilfelle SB-fila er rådata.
_KONTO_KEYS = ("konto", "Konto", "KONTO")
_NAVN_KEYS = ("kontonavn", "Kontonavn", "navn", "Navn")
_IB_KEYS = ("ib", "IB", "Inngående", "InngåendeSaldo")
_UB_KEYS = ("ub", "UB", "Utgående", "UtgåendeSaldo")


@dataclass
class SBDiffResult:
    """Resultat fra sammenligning av to SB-versjoner."""

    added: pd.DataFrame       # Nye konti (kun i B): konto, kontonavn, ib, ub
    removed: pd.DataFrame     # Fjernede konti (kun i A): konto, kontonavn, ib, ub
    changed: pd.DataFrame     # Endrede saldoer: konto, kontonavn, ib_a, ib_b, diff_ib, ub_a, ub_b, diff_ub
    unchanged_count: int       # Antall konti som er identiske (IB+UB)
    summary: dict


def _pick_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> Optional[str]:
    """Finn første kolonnenavn som matcher en av kandidatene."""
    for c in candidates:
        if c in df.columns:
            return c
    # Case-insensitiv fallback
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _normalize_sb(df: pd.DataFrame) -> pd.DataFrame:
    """Bring SB-DataFrame til standardform med kolonnene konto/kontonavn/ib/ub.

    Toleranser:
      - Tomme konto-rader hoppes over
      - Tomme/manglende IB-/UB-kolonner blir 0.0
      - Manglende kontonavn blir tom string
    """
    konto_col = _pick_col(df, _KONTO_KEYS)
    if konto_col is None:
        raise ValueError("Fant ingen konto-kolonne i SB-DataFrame.")

    out = pd.DataFrame()
    out["konto"] = df[konto_col].astype("string").fillna("").str.strip()

    navn_col = _pick_col(df, _NAVN_KEYS)
    out["kontonavn"] = (
        df[navn_col].astype("string").fillna("").str.strip()
        if navn_col else ""
    )

    ib_col = _pick_col(df, _IB_KEYS)
    out["ib"] = (
        pd.to_numeric(df[ib_col], errors="coerce").fillna(0.0)
        if ib_col else 0.0
    )

    ub_col = _pick_col(df, _UB_KEYS)
    out["ub"] = (
        pd.to_numeric(df[ub_col], errors="coerce").fillna(0.0)
        if ub_col else 0.0
    )

    # Fjern tomme konto-rader og dedupliser (siste vinner hvis duplikat)
    out = out.loc[out["konto"].str.len() > 0].copy()
    out = out.drop_duplicates(subset=["konto"], keep="last")
    return out.reset_index(drop=True)


def diff_sb_versions(
    df_a: pd.DataFrame,
    df_b: pd.DataFrame,
    *,
    tolerance: float = 0.01,
) -> SBDiffResult:
    """Sammenlign to saldobalanse-DataFrames konto for konto.

    Args:
        df_a: Eldre versjon
        df_b: Nyere versjon
        tolerance: Beløpsavvik mindre enn denne regnes som "uendret"
            (håndterer øre-avrunding).

    Returnerer SBDiffResult med nye, fjernede og endrede konti.
    """
    a = _normalize_sb(df_a)
    b = _normalize_sb(df_b)

    konti_a = set(a["konto"])
    konti_b = set(b["konto"])

    new_konti = konti_b - konti_a
    removed_konti = konti_a - konti_b
    common_konti = konti_a & konti_b

    added_df = b.loc[b["konto"].isin(new_konti)].copy().reset_index(drop=True)
    removed_df = a.loc[a["konto"].isin(removed_konti)].copy().reset_index(drop=True)

    # Slå sammen felles konti og beregn diff
    merged = a.merge(
        b, on="konto", how="inner", suffixes=("_a", "_b"),
    )
    # Bruk navn fra B (nyeste) som "kontonavn" i diff-output
    merged["kontonavn"] = merged["kontonavn_b"].where(
        merged["kontonavn_b"].astype(str).str.len() > 0,
        merged["kontonavn_a"],
    )
    merged["diff_ib"] = merged["ib_b"] - merged["ib_a"]
    merged["diff_ub"] = merged["ub_b"] - merged["ub_a"]

    changed_mask = (
        merged["diff_ib"].abs() > tolerance
    ) | (
        merged["diff_ub"].abs() > tolerance
    )
    changed_df = merged.loc[changed_mask, [
        "konto", "kontonavn",
        "ib_a", "ib_b", "diff_ib",
        "ub_a", "ub_b", "diff_ub",
    ]].copy().reset_index(drop=True)

    unchanged_count = len(common_konti) - len(changed_df)

    summary = {
        "konti_a_total": len(konti_a),
        "konti_b_total": len(konti_b),
        "nye_konti": len(new_konti),
        "fjernede_konti": len(removed_konti),
        "endrede_konti": len(changed_df),
        "uendrede_konti": unchanged_count,
        "sum_ub_a": float(a["ub"].sum()),
        "sum_ub_b": float(b["ub"].sum()),
    }

    return SBDiffResult(
        added=added_df,
        removed=removed_df,
        changed=changed_df,
        unchanged_count=unchanged_count,
        summary=summary,
    )
