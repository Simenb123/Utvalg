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

    # Saldo / bevegelse — fallback-labels uten år. Med år får disse 4-sifret
    # årstall (UB 2025) for rene verdier, eller 2-sifret (Endr UB 25/24)
    # for endringskolonner. Se heading() for full formattering.
    "IB":             "IB",
    "HB":             "HB",                  # HB-aggregat (sum transaksjoner i HB)
    "Endring":        "Δ UB-IB",         # periode-bevegelse (UB - IB)
    "Endring_fjor":   "Δ UB",            # år-over-år (UB - UB_fjor)
    "Endring_pct":    "Δ % UB",          # år-over-år, prosentvis
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

    Formatkonvensjon:
        - Rene verdier   → 4-sifret år: "UB 2025", "IB 2025", "HB 2025"
        - Endringer      → Δ-prefiks + 2-sifret år: "Δ UB 25/24", "Δ UB-IB 25"
                           Δ er kompakt og signaliserer visuelt at kolonnen
                           er en beregnet differanse, ikke en råverdi.

    Spesielle behandlinger:
        - ``Sum`` / ``UB``    → ``UB <år>`` når år kjent, ellers ``UB``.
        - ``UB_fjor``         → ``UB <år-1>`` når år kjent, ellers ``UB i fjor``.
        - ``IB``              → ``IB <år>`` når år kjent, ellers ``IB``.
        - ``HB``              → ``HB <år>`` når år kjent, ellers ``HB``.
        - ``BRREG``           → ``BRREG <år>`` når brreg_year kjent.
        - ``Endring``         → ``Δ UB-IB <yy>`` (periode, UB minus IB).
        - ``Endring_fjor``    → ``Δ UB <yy>/<yy-1>`` (år-over-år).
        - ``Endring_pct``     → ``Δ % UB <yy>/<yy-1>``.

    Øvrige IDs slås opp i ``LABELS_STATIC``; ukjente returneres uendret.
    """
    # Rene verdier (4-sifret år)
    if col_id in ("Sum", "UB"):
        return f"UB {year}" if year is not None else "UB"
    if col_id == "UB_fjor":
        return f"UB {year - 1}" if year is not None else "UB i fjor"
    if col_id == "IB":
        return f"IB {year}" if year is not None else "IB"
    if col_id == "HB":
        return f"HB {year}" if year is not None else "HB"
    if col_id == "BRREG":
        return f"BRREG {brreg_year}" if brreg_year is not None else "BRREG"

    # Endringskolonner (Δ-prefiks + 2-sifret år)
    if year is not None:
        yy = year % 100
        py = (year - 1) % 100
        if col_id == "Endring":
            return f"Δ UB-IB {yy:02d}"
        if col_id == "Endring_fjor":
            return f"Δ UB {yy:02d}/{py:02d}"
        if col_id == "Endring_pct":
            return f"Δ % UB {yy:02d}/{py:02d}"

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
