from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class Columns:
    # Obligatoriske
    konto: str = ""
    kontonavn: str = ""
    bilag: str = ""
    belop: str = ""
    # Valgfrie
    dato: str = ""
    tekst: str = ""
    part: str = ""
    due: str = ""            # forfallsdato
    periodestart: str = ""   # periode-start
    periodeslutt: str = ""   # periode-slutt


@dataclass
class ScopeConfig:
    """
    Konfigurasjon for scope/populasjon ved eksport (brukes bl.a. av controller_export).

    NB: Denne er bevisst lagt i models.py for å unngå ImportError ved import av controller_export
    (som igjen importeres av views_selection_studio og dermed blokkerer pytest collection).

    Felt er holdt kompatible med typisk scope-logikk:
      - accounts_spec: "6000-7999, 7210, 73*"
      - direction: "Alle" | "Debet" | "Kredit"
      - basis: "signed" | "abs"
      - min_amount/max_amount: beløpsfilter
      - date_from/date_to: datofilter (Timestamp)
    """
    name: str = ""
    accounts_spec: str = ""
    direction: str = "Alle"
    basis: str = "signed"
    min_amount: Optional[float] = None
    max_amount: Optional[float] = None
    date_from: Optional[pd.Timestamp] = None
    date_to: Optional[pd.Timestamp] = None
