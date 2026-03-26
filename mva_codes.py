"""Norske SAF-T standard MVA-koder (referansedata).

Inneholder den komplette listen over standard MVA-koder som definert i
norsk SAF-T-format (SAF-T Financial v1.10+).  Alt er Python-konstanter
slik at modulen fungerer i frozen/onefile-builds uten ekstern fil.
"""

from __future__ import annotations


STANDARD_MVA_CODES: list[dict] = [
    # --- Ingen MVA ---
    {"code": "0",  "description": "Ingen MVA-behandling (anskaffelser)",  "rate": 0.0,  "direction": ""},
    # --- Utgående MVA ---
    {"code": "1",  "description": "Utgående MVA, 25 %",                  "rate": 25.0, "direction": "utgående"},
    {"code": "3",  "description": "Utgående MVA, 25 % (fiskeri/jordbruk)", "rate": 25.0, "direction": "utgående"},
    {"code": "5",  "description": "Utgående MVA, 15 % (næringsmiddel)",   "rate": 15.0, "direction": "utgående"},
    {"code": "6",  "description": "Utgående MVA, 12 % (transport, kultur m.m.)", "rate": 12.0, "direction": "utgående"},
    {"code": "7",  "description": "Utgående MVA, 0 % (fritatt omsetning)", "rate": 0.0, "direction": "utgående"},
    {"code": "8",  "description": "Utenfor MVA-loven",                    "rate": 0.0,  "direction": ""},
    {"code": "9",  "description": "Innførsel (import), 25 %",             "rate": 25.0, "direction": "utgående"},
    # --- Inngående MVA ---
    {"code": "11", "description": "Inngående MVA, 25 %",                  "rate": 25.0, "direction": "inngående"},
    {"code": "13", "description": "Inngående MVA, 25 % (fiskeri/jordbruk)", "rate": 25.0, "direction": "inngående"},
    {"code": "14", "description": "Inngående MVA, 15 % (næringsmiddel)",  "rate": 15.0, "direction": "inngående"},
    {"code": "15", "description": "Inngående MVA, 12 % (transport, kultur m.m.)", "rate": 12.0, "direction": "inngående"},
    # --- Omvendt avgiftsplikt / snudd avregning ---
    {"code": "21", "description": "Utgående MVA, 25 % (omvendt avgiftsplikt)", "rate": 25.0, "direction": "utgående"},
    {"code": "22", "description": "Utgående MVA, 12 % (omvendt avgiftsplikt)", "rate": 12.0, "direction": "utgående"},
    {"code": "23", "description": "Utgående MVA, 25 % (tjenester fra utlandet)", "rate": 25.0, "direction": "utgående"},
    {"code": "24", "description": "Utgående MVA, 12 % (tjenester fra utlandet)", "rate": 12.0, "direction": "utgående"},
    # --- Fradragsberettiget innførsel ---
    {"code": "31", "description": "Inngående MVA, 25 % (omvendt avgiftsplikt)", "rate": 25.0, "direction": "inngående"},
    {"code": "32", "description": "Inngående MVA, 12 % (omvendt avgiftsplikt)", "rate": 12.0, "direction": "inngående"},
    {"code": "33", "description": "Inngående MVA, 25 % (tjenester fra utlandet)", "rate": 25.0, "direction": "inngående"},
    {"code": "34", "description": "Inngående MVA, 12 % (tjenester fra utlandet)", "rate": 12.0, "direction": "inngående"},
    {"code": "36", "description": "Inngående MVA, 25 % (innførsel varer)", "rate": 25.0, "direction": "inngående"},
    # --- Særavgifter ---
    {"code": "51", "description": "Særavgift, utgående",                  "rate": 0.0,  "direction": "utgående"},
    {"code": "52", "description": "Særavgift, inngående",                 "rate": 0.0,  "direction": "inngående"},
    # --- Spesialkoder ---
    {"code": "86", "description": "Uttak / eget bruk, 25 %",              "rate": 25.0, "direction": "utgående"},
    {"code": "87", "description": "Uttak / eget bruk, 15 %",              "rate": 15.0, "direction": "utgående"},
    {"code": "88", "description": "Uttak / eget bruk, 12 %",              "rate": 12.0, "direction": "utgående"},
    {"code": "89", "description": "Tapte krav",                           "rate": 0.0,  "direction": ""},
    {"code": "91", "description": "Utgående MVA, 25 % (klimakvoter)",     "rate": 25.0, "direction": "utgående"},
    {"code": "92", "description": "Inngående MVA, 25 % (klimakvoter)",    "rate": 25.0, "direction": "inngående"},
]

# Indeksert oppslagstabell for rask tilgang
_CODE_INDEX: dict[str, dict] = {c["code"]: c for c in STANDARD_MVA_CODES}


ACCOUNTING_SYSTEMS: list[str] = [
    "Tripletex",
    "PowerOffice GO",
    "Xledger",
    "Visma Business",
    "Visma eAccounting",
    "Fiken",
    "Uni Economy",
    "24SevenOffice",
    "SAF-T Standard",
    "Annet",
]


def get_standard_codes() -> list[dict]:
    """Returner alle standard MVA-koder."""
    return list(STANDARD_MVA_CODES)


def get_code_info(code: str) -> dict | None:
    """Slå opp info for en gitt standard MVA-kode.  Returnerer None om ukjent."""
    return _CODE_INDEX.get(str(code).strip())


def standard_code_choices() -> list[str]:
    """Returner liste med ``'kode - beskrivelse'`` for bruk i combobox."""
    return [f"{c['code']} - {c['description']}" for c in STANDARD_MVA_CODES]
