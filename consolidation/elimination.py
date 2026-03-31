"""consolidation.elimination -- Eliminerings-hjelpefunksjoner.

Rene funksjoner for validering og konvertering av EliminationJournal
til DataFrames egnet for konsolideringsmotoren.

Prinsipp: Elimineringer er et justeringslag over raa TB — de muterer
aldri grunnlagsdata. Resultatet viser grunnlag + eliminering = konsolidert.
"""

from __future__ import annotations

import pandas as pd

from consolidation.models import EliminationJournal

_COLS = ["journal_id", "journal_name", "regnr", "company_id", "amount", "description"]


def validate_journal(journal: EliminationJournal) -> tuple[bool, float]:
    """Valider at en elimineringsjournal er balansert.

    Returns:
        (is_balanced, net_amount)
    """
    return journal.is_balanced, journal.net


def journals_to_dataframe(
    journals: list[EliminationJournal],
) -> pd.DataFrame:
    """Konverter elimineringsjournaler til flat DataFrame.

    Returns:
        DataFrame med kolonner:
        [journal_id, journal_name, regnr, company_id, amount, description]
        Tom DataFrame med korrekte kolonner hvis ingen journaler/linjer.
    """
    rows: list[dict] = []
    for j in journals:
        for line in j.lines:
            rows.append({
                "journal_id": j.journal_id,
                "journal_name": j.display_label,
                "regnr": line.regnr,
                "company_id": line.company_id,
                "amount": line.amount,
                "description": line.description,
            })

    if not rows:
        return pd.DataFrame(columns=_COLS)

    df = pd.DataFrame(rows, columns=_COLS)
    df["regnr"] = df["regnr"].astype(int)
    df["amount"] = df["amount"].astype(float)
    return df


def aggregate_eliminations_by_regnr(
    journals: list[EliminationJournal],
) -> dict[int, float]:
    """Summer alle eliminerings-beloep per regnr paa tvers av journaler.

    Returns:
        dict mapping regnr -> total eliminert beloep.
    """
    totals: dict[int, float] = {}
    for j in journals:
        for line in j.lines:
            regnr = int(line.regnr)
            totals[regnr] = totals.get(regnr, 0.0) + float(line.amount)
    return totals
