"""Standard MVA-kode-mapping per regnskapssystem.

Viktig (verifisert mot faktiske SAF-T-filer):

- **Tripletex** og **PowerOffice GO** bruker SAF-T StandardTaxCode direkte
  (1:1-mapping).
- **Visma Business**, **Xledger**, **Visma eAccounting**, **Fiken**,
  **Uni Economy**, **24SevenOffice** m.fl. bruker interne MVA-kode-ID-er
  som må mappes eksplisitt til StandardTaxCode av revisor. For disse
  returneres en **tom** default slik at analysekoden ikke forutsetter
  en feilaktig 1:1-relasjon.
- **SAF-T Standard** er per definisjon 1:1.

Eksplisitte mappinger for enkeltklienter legges i
``regnskap_client_overrides.save_mva_code_mapping``.
"""

from __future__ import annotations

import mva_codes

# ---- Standard-koder som er vanlige på tvers av systemer ----

_COMMON_CODES: list[str] = [
    c["code"] for c in mva_codes.STANDARD_MVA_CODES
]

# 1:1-mapping (klientens kode == SAF-T standard-kode)
_IDENTITY_MAP: dict[str, str] = {code: code for code in _COMMON_CODES}


# Systemer som bruker SAF-T StandardTaxCode direkte (1:1).
_SYSTEMS_WITH_IDENTITY: set[str] = {
    "Tripletex",
    "PowerOffice GO",
    "SAF-T Standard",
}


# ---- Per-system overstyringer ----
# Ingen offentlig dokumentert full mapping for Visma Business / Xledger /
# Visma eAccounting / Fiken m.fl. ennå — må settes opp per klient via
# MVA-oppsett-dialogen. Tomt map = "ukjent" → analysekoden faller tilbake
# på rå-koden og advarer dersom den ikke finnes i StandardTaxCode.

_SYSTEM_OVERRIDES: dict[str, dict[str, str]] = {
    # Fyll ut per system etter hvert som bekreftede mappinger verifiseres.
    # Eksempel: "Visma Business": {"MVA25": "1", "MVA15K": "3", ...},
}


def get_default_mapping(system: str) -> dict[str, str]:
    """Hent standard-mapping {klient_kode: saft_kode} for et system.

    - Tripletex / PowerOffice GO / SAF-T Standard → 1:1-mapping.
    - System med eksplisitt overstyring i ``_SYSTEM_OVERRIDES`` → den.
    - Alle andre systemer → tom mapping (må konfigureres per klient).
    """
    system = str(system or "").strip()
    overrides = _SYSTEM_OVERRIDES.get(system)
    if overrides is not None:
        return dict(overrides)
    if system in _SYSTEMS_WITH_IDENTITY:
        return dict(_IDENTITY_MAP)
    return {}


def supported_systems() -> list[str]:
    """Returner listen over kjente regnskapssystemer."""
    return list(mva_codes.ACCOUNTING_SYSTEMS)


def has_custom_defaults(system: str) -> bool:
    """Returnerer True hvis systemet har egne kode-avvik fra SAF-T standard."""
    return str(system or "").strip() in _SYSTEM_OVERRIDES


def uses_saft_identity(system: str) -> bool:
    """Returnerer True hvis systemet bruker SAF-T StandardTaxCode direkte."""
    return str(system or "").strip() in _SYSTEMS_WITH_IDENTITY
