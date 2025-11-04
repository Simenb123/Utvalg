from __future__ import annotations
from dataclasses import dataclass

@dataclass
class Columns:
    konto: str = ""
    kontonavn: str = ""
    bilag: str = ""
    belop: str = ""
    tekst: str = ""
    dato: str = ""
    part: str = ""
    # Ekstra dato-felter (valgfritt)
    due: str = ""           # Forfallsdato
    periodestart: str = ""  # Periode-startkolonne
    periodeslutt: str = ""  # Periode-sluttkolonne
