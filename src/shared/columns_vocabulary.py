"""Kanonisk vokabular for kolonner på tvers av fanene.

Én kilde til sannhet for hva en intern kolonne-ID betyr og hvordan den
skal vises for brukeren. Bruk ``heading(col_id, year=…)`` overalt der en
brukerrettet overskrift trengs — slik unngår vi at samme konsept får
forskjellig tekst i ulike faner ("UB i fjor" vs "UB fjor",
"Bevegelse" vs "Bevegelse i år", osv.).

Semantisk skille å være obs på:
    Endring (intern ``Endring``)        — periode-bevegelse, UB − IB i år.
                                           Vises som "Bevegelse i år".
    Endring (intern ``Endring_fjor``)   — år-over-år, UB − UB_fjor.
                                           Vises som "Endring".

Se doc/architecture/columns_vocabulary.md for full referanse.
"""

from __future__ import annotations

from typing import Optional


LABELS_STATIC: dict[str, str] = {
    # Identitet / metadata
    "Konto":          "Konto",
    "Kontonavn":      "Kontonavn",
    "OK":             "OK",
    "OK_av":          "OK av",
    "OK_dato":        "OK dato",
    "Vedlegg":        "Vedlegg",
    "Gruppe":         "Gruppe",

    # Saldo / bevegelse
    "IB":             "IB",
    "Endring":        "Bevegelse i år",   # periode-bevegelse (UB - IB)
    "Endring_fjor":   "Endring",          # år-over-år (UB - UB_fjor)
    "Endring_pct":    "Endring %",
    "Antall":         "Antall",
    "Antall_bilag":   "Antall bilag",

    # Tilleggsposteringer (ÅO)
    "AO_belop":       "Tilleggspostering",
    "UB_for_ao":      "UB før ÅO",
    "UB_etter_ao":    "UB etter ÅO",

    # BRREG-sammenligning
    "BRREG":          "BRREG",
    "Avvik_brreg":    "Avvik mot BRREG",
    "Avvik_brreg_pct":"Avvik % mot BRREG",
}


def heading(
    col_id: str,
    *,
    year: Optional[int] = None,
    brreg_year: Optional[int] = None,
) -> str:
    """Returner kanonisk brukerrettet overskrift for en kolonne-ID.

    Dynamisk år injiseres for kolonner hvor det er meningsfullt:
        - ``Sum`` / ``UB``  → ``UB <år>`` når år er kjent, ellers ``UB``.
        - ``UB_fjor``       → ``UB <år-1>`` når år er kjent, ellers ``UB i fjor``.
        - ``BRREG``         → ``BRREG <år>`` når brreg_year er kjent, ellers ``BRREG``.

    Øvrige IDs slås opp i ``LABELS_STATIC``; ukjente returneres uendret.
    """
    if col_id in ("Sum", "UB"):
        return f"UB {year}" if year is not None else "UB"
    if col_id == "UB_fjor":
        return f"UB {year - 1}" if year is not None else "UB i fjor"
    if col_id == "BRREG":
        return f"BRREG {brreg_year}" if brreg_year is not None else "BRREG"
    return LABELS_STATIC.get(col_id, col_id)


def active_year_from_session() -> Optional[int]:
    """Les aktivt regnskapsår fra ``session.year`` som int, eller None.

    Kan brukes av faner som ikke allerede har en lokal year-getter.
    """
    try:
        import session as _session
        raw = getattr(_session, "year", None)
    except Exception:
        return None
    if raw is None:
        return None
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return None
