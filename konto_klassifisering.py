"""konto_klassifisering.py — Sub-klassifisering av kontoer.

Et ekstra klassifiseringslag mellom konto og regnskapslinje.
Brukes til MVA-analyse, lønnsanalyse og annen gruppert analyse.

Lagring: JSON via preferences, per klient.
Nøkkelformat: "konto_klassifisering.{safe_client}.mapping"
Verdien er en dict: {konto_str: gruppe_navn}

Standardgrupper er forhåndsdefinert men kan overstyres.
"""
from __future__ import annotations

from typing import Any

import preferences

# ---------------------------------------------------------------------------
# Forhåndsdefinerte gruppenavn (brukes i editor-dropdown)
# ---------------------------------------------------------------------------

DEFAULT_GROUPS: list[str] = [
    # MVA
    "Skyldig MVA",
    "Inngående MVA",
    "Utgående MVA",
    # Lønn og personal
    "Lønnskostnad",
    "Feriepenger",
    "Skyldig lønn",
    "Skyldig feriepenger",
    "Skyldig arbeidsgiveravgift",
    "Skyldig arbeidsgiveravgift av feriepenger",
    "Kostnadsført arbeidsgiveravgift",
    "Kostnadsført arbeidsgiveravgift av feriepenger",
    "Pensjonskostnad",
    "Skyldig pensjon",
    # Skatt
    "Betalbar skatt",
    "Utsatt skatt",
    "Skattetrekk",
    # Bank og likviditet
    "Driftskonto",
    "Skattetrekkskonto",
    "Sparekonto",
    # Kundefordringer og gjeld
    "Kundefordringer",
    "Leverandørgjeld",
    "Mellomværende konsern",
    "Ansvarlig lån",
    # Driftsmidler
    "Maskiner og utstyr",
    "Inventar",
    "IT-utstyr",
    "Biler",
    "Gevinst-/tapskonto",
    # Annet
    "Egenkapital",
    "Utbytte",
]


# ---------------------------------------------------------------------------
# Persistens
# ---------------------------------------------------------------------------

def _pref_key(client: str) -> str:
    safe = "".join(c if c.isalnum() else "_" for c in (client or "default"))
    return f"konto_klassifisering.{safe}.mapping"


def load(client: str) -> dict[str, str]:
    """Last konto→gruppe-mapping for gitt klient. Returnerer tom dict hvis ingen."""
    raw = preferences.get(_pref_key(client))
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v}
    return {}


def save(client: str, mapping: dict[str, str]) -> None:
    """Lagre konto→gruppe-mapping for gitt klient."""
    preferences.set(_pref_key(client), {str(k): str(v) for k, v in mapping.items() if v})


def get_group(mapping: dict[str, str], konto: str) -> str:
    """Hent gruppe for en konto, eller tom streng."""
    return mapping.get(str(konto).strip(), "")


def all_groups_in_use(mapping: dict[str, str]) -> list[str]:
    """Alle grupper som faktisk er brukt, sortert."""
    return sorted(set(v for v in mapping.values() if v))


def kontoer_for_group(mapping: dict[str, str], group: str) -> list[str]:
    """Alle kontoer som tilhører gitt gruppe, sortert."""
    return sorted(k for k, v in mapping.items() if v == group)


def build_group_lookup(
    mapping: dict[str, str],
    kontoer: list[str],
) -> dict[str, str]:
    """Bygg {konto: gruppe} for kun de kontoene som er i listen."""
    return {k: mapping[k] for k in kontoer if k in mapping}
