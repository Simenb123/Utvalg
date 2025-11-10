from __future__ import annotations
from dataclasses import dataclass

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