"""consolidation.elimination -- Eliminerings-hjelpefunksjoner.

Rene funksjoner for validering og konvertering av EliminationJournal
til DataFrames egnet for konsolideringsmotoren.

Prinsipp: Elimineringer er et justeringslag over raa TB — de muterer
aldri grunnlagsdata. Resultatet viser grunnlag + eliminering = konsolidert.
"""

from __future__ import annotations

import pandas as pd

from .models import EliminationJournal

_COLS = ["journal_id", "journal_name", "regnr", "company_id", "amount", "description"]


def validate_journal(journal: EliminationJournal) -> tuple[bool, float]:
    """Valider at en elimineringsjournal er balansert.

    Returns:
        (is_balanced, net_amount)
    """
    return journal.is_balanced, journal.net


_COLS_KONTO = ["journal_id", "journal_name", "regnr", "konto", "company_id", "amount", "description"]


def journals_to_dataframe(
    journals: list[EliminationJournal],
) -> pd.DataFrame:
    """Konverter elimineringsjournaler til flat DataFrame.

    Returns:
        DataFrame med kolonner:
        [journal_id, journal_name, regnr, konto, company_id, amount, description]
        Tom DataFrame med korrekte kolonner hvis ingen journaler/linjer.
    """
    rows: list[dict] = []
    for j in journals:
        for line in j.lines:
            rows.append({
                "journal_id": j.journal_id,
                "journal_name": j.display_label,
                "regnr": line.regnr,
                "konto": str(line.konto or ""),
                "company_id": line.company_id,
                "amount": line.amount,
                "description": line.description,
            })

    if not rows:
        return pd.DataFrame(columns=_COLS_KONTO)

    df = pd.DataFrame(rows, columns=_COLS_KONTO)
    df["regnr"] = df["regnr"].astype(int)
    df["amount"] = df["amount"].astype(float)
    return df


def aggregate_eliminations_by_regnr(
    journals: list[EliminationJournal],
) -> dict[int, float]:
    """Summer alle eliminerings-beloep per regnr paa tvers av journaler.

    Inkluderer kun linjer uten konto (regnskapslinje-nivå).
    Linjer med konto aggregeres separat via aggregate_eliminations_by_konto.

    Returns:
        dict mapping regnr -> total eliminert beloep.
    """
    totals: dict[int, float] = {}
    for j in journals:
        for line in j.lines:
            if str(line.konto or "").strip():
                continue  # konto-nivå, håndteres separat
            regnr = int(line.regnr)
            totals[regnr] = totals.get(regnr, 0.0) + float(line.amount)
    return totals


def aggregate_eliminations_by_konto(
    journals: list[EliminationJournal],
) -> dict[str, float]:
    """Summer alle eliminerings-beloep per konto paa tvers av journaler.

    Kun linjer der konto er satt (saldobalanse-nivå eliminering).

    Returns:
        dict mapping konto -> total eliminert beloep.
    """
    totals: dict[str, float] = {}
    for j in journals:
        for line in j.lines:
            konto = str(line.konto or "").strip()
            if not konto:
                continue
            totals[konto] = totals.get(konto, 0.0) + float(line.amount)
    return totals
