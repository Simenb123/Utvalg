"""Offisielle norske SAF-T StandardTaxCode (referansedata).

Kodelisten er hentet og verifisert mot Skatteetatens SAF-T Financial-
spesifikasjon (SAF-T Financial v1.10+) — sjekket mot faktisk
TaxTable-innhold i SAF-T-filer fra norske regnskapssystemer.

**Viktig:**
- Dette er ``StandardTaxCode`` slik den er definert av Skatteetaten.
- Enkelte regnskapssystemer (Tripletex, PowerOffice GO) bruker disse
  kodene direkte. Andre (Visma Business, Xledger m.fl.) har interne
  MVA-koder som må mappes til StandardTaxCode før analyse — se
  ``mva_system_defaults`` og ``regnskap_client_overrides``.
- Retningen (``direction``) beskriver om koden gjelder anskaffelser
  (**inngående**) eller inntekter/omsetning (**utgående**). Dette
  følger SAF-T-definisjonen, ikke bokføringsretningen (debet/kredit)
  i regnskapet.
"""

from __future__ import annotations


STANDARD_MVA_CODES: list[dict] = [
    # --- Inngående MVA (anskaffelser, med fradrag) ---
    {"code": "1",  "description": "Fradrag inngående avgift, høy sats",                "rate": 25.00, "direction": "inngående"},
    {"code": "11", "description": "Fradrag inngående avgift, middels sats",            "rate": 15.00, "direction": "inngående"},
    {"code": "12", "description": "Fradrag inngående avgift, råfisk",                   "rate": 11.11, "direction": "inngående"},
    {"code": "13", "description": "Fradrag inngående avgift, lav sats",                 "rate": 12.00, "direction": "inngående"},
    {"code": "14", "description": "Fradrag inngående avgift betalt ved innførsel, høy sats",     "rate": 25.00, "direction": "inngående"},
    {"code": "15", "description": "Fradrag inngående avgift betalt ved innførsel, middels sats", "rate": 15.00, "direction": "inngående"},
    # --- Innførsel (grunnlag, ingen fradrag) ---
    {"code": "20", "description": "Grunnlag, ingen inngående avgift ved innførsel",    "rate": 0.0,  "direction": "inngående"},
    {"code": "21", "description": "Grunnlag inngående avgift ved innførsel, høy sats", "rate": 0.0,  "direction": "inngående"},
    {"code": "22", "description": "Grunnlag inngående avgift ved innførsel, middels sats", "rate": 0.0, "direction": "inngående"},
    # --- Utgående MVA ---
    {"code": "3",  "description": "Utgående avgift, høy sats",                          "rate": 25.00, "direction": "utgående"},
    {"code": "31", "description": "Utgående avgift, middels sats",                      "rate": 15.00, "direction": "utgående"},
    {"code": "32", "description": "Utgående avgift, råfisk",                            "rate": 11.11, "direction": "utgående"},
    {"code": "33", "description": "Utgående avgift, lav sats",                          "rate": 12.00, "direction": "utgående"},
    # --- Omsetning uten avgift ---
    {"code": "5",  "description": "Ingen utgående avgift (innenfor mva-loven)",         "rate": 0.0,  "direction": "utgående"},
    {"code": "51", "description": "Avgiftsfri innlands omsetning med omvendt avgiftsplikt", "rate": 0.0, "direction": "utgående"},
    {"code": "52", "description": "Avgiftsfri utførsel av varer og tjenester",          "rate": 0.0,  "direction": "utgående"},
    {"code": "6",  "description": "Ingen utgående avgift (utenfor mva-loven)",          "rate": 0.0,  "direction": "utgående"},
    {"code": "7",  "description": "Ingen avgiftsbehandling (inntekter)",                "rate": 0.0,  "direction": "utgående"},
    # --- Innførsel varer (reverse charge) ---
    {"code": "81", "description": "Fradrag inngående avgift ved innførsel, høy sats",   "rate": 25.00, "direction": "inngående"},
    {"code": "82", "description": "Inngående avgift uten fradrag ved innførsel, høy sats", "rate": 25.00, "direction": "inngående"},
    {"code": "83", "description": "Fradrag inngående avgift ved innførsel, middels sats","rate": 15.00, "direction": "inngående"},
    {"code": "84", "description": "Inngående avgift uten fradrag ved innførsel, middels sats", "rate": 15.00, "direction": "inngående"},
    {"code": "85", "description": "Grunnlag, avgiftsfri innførsel",                     "rate": 0.0,  "direction": "inngående"},
    # --- Tjenester fra utlandet (reverse charge) ---
    {"code": "86", "description": "Fradrag inngående avgift ved kjøp av tjenester fra utlandet, høy sats", "rate": 25.00, "direction": "inngående"},
    {"code": "87", "description": "Kjøp av tjenester fra utlandet uten fradrag, høy sats",                 "rate": 25.00, "direction": "inngående"},
    {"code": "88", "description": "Fradrag inngående avgift ved kjøp av tjenester fra utlandet, lav sats", "rate": 12.00, "direction": "inngående"},
    {"code": "89", "description": "Kjøp av tjenester fra utlandet uten fradrag, lav sats",                 "rate": 12.00, "direction": "inngående"},
    # --- Klimakvoter / gull (reverse charge) ---
    {"code": "91", "description": "Fradrag inngående avgift ved kjøp av klimakvoter/gull", "rate": 25.00, "direction": "inngående"},
    {"code": "92", "description": "Kjøp av klimakvoter/gull uten avgiftskompensasjon",     "rate": 25.00, "direction": "inngående"},
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
    """Returner alle offisielle SAF-T StandardTaxCode."""
    return list(STANDARD_MVA_CODES)


def get_code_info(code: str) -> dict | None:
    """Slå opp info for en gitt SAF-T StandardTaxCode.  Returnerer None om ukjent."""
    return _CODE_INDEX.get(str(code).strip())


def standard_code_choices() -> list[str]:
    """Returner liste med ``'kode - beskrivelse'`` for bruk i combobox."""
    return [f"{c['code']} - {c['description']}" for c in STANDARD_MVA_CODES]


def is_deduction_code(code: object) -> bool:
    """Returner True hvis MVA-koden gir inngående fradrag.

    Fradrags-koder er inngående-retning der beskrivelsen starter med
    "Fradrag inngående". Det skiller dem fra ikke-fradragsberettiget
    inngående (kode 20-22, 82, 84, 87, 89, 92) og utgående (3, 31...).

    Brukes f.eks. av bilag-kontroll-flyten til å sjekke om fradrag er
    tatt på en leverandør som ikke er MVA-registrert.
    """
    info = get_code_info(str(code or "").strip())
    if not info:
        return False
    if info.get("direction") != "inngående":
        return False
    desc = str(info.get("description", ""))
    return desc.startswith("Fradrag inngående")
