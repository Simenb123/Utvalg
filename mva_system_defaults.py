"""Standard MVA-kode-mapping per regnskapssystem.

De fleste norske regnskapssystemer bruker SAF-T standard-koder direkte
(1:1-mapping).  Der et system avviker, dokumenteres forskjellene her.
"""

from __future__ import annotations

import mva_codes

# ---- Standard-koder som er vanlige på tvers av systemer ----

_COMMON_CODES: list[str] = [
    c["code"] for c in mva_codes.STANDARD_MVA_CODES
]

# 1:1-mapping (klientens kode == SAF-T standard-kode)
_IDENTITY_MAP: dict[str, str] = {code: code for code in _COMMON_CODES}


# ---- Per-system overstyringer ----
# De fleste systemer bruker identisk mapping.  Legg til avvik her
# ettersom de oppdages i praksis.

_SYSTEM_OVERRIDES: dict[str, dict[str, str]] = {
    # Eksempel: Visma Business bruker «MVA25» internt for kode 1
    # "Visma Business": {"MVA25": "1", "MVA15": "5", "MVA12": "6", ...},
}


def get_default_mapping(system: str) -> dict[str, str]:
    """Hent standard-mapping {klient_kode: saft_kode} for et system.

    Hvis systemet har spesifikke overstyringer brukes de.
    Ellers returneres 1:1-mapping med SAF-T standardkoder.
    """
    system = str(system or "").strip()
    overrides = _SYSTEM_OVERRIDES.get(system)
    if overrides is not None:
        return dict(overrides)
    return dict(_IDENTITY_MAP)


def supported_systems() -> list[str]:
    """Returner listen over kjente regnskapssystemer."""
    return list(mva_codes.ACCOUNTING_SYSTEMS)


def has_custom_defaults(system: str) -> bool:
    """Returnerer True hvis systemet har egne kode-avvik fra SAF-T standard."""
    return str(system or "").strip() in _SYSTEM_OVERRIDES
